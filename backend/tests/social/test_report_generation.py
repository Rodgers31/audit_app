"""Neutral report announcements carry real document evidence, never numeric stand-ins."""
from copy import deepcopy
from datetime import date
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import select, func

from test_domain_support import db, call
from test_generation import configure, consume
from social.generation.contracts import SourceObservation
from social.generation.models import SourceCursor, SourceEvent
from social.generation.service import render
from social.models import SocialPost, SocialPostRevision
from social.service import SocialError


def report_observation(version=1, *, published='2026-07-01', period='FY2025/26', end='2026-06-30', document=1, digest='a'):
    return {'schema_version': 1, 'source_type': 'cob', 'source_key': 'cob:county:1:reports',
        'evidence_version': version, 'ingestion_id': str(version), 'category': 'dataset_availability',
        'title': 'Controller of Budget report · Nairobi City County', 'committed': True,
        'fixture': False, 'quarantined': False, 'publishable': True, 'correction_pending': False,
        'facts': [], 'report': {'source_record_id': 1, 'authority_fingerprint': 'a'*64, 'entity_id': 1, 'entity': 'Nairobi City County', 'period': period,
            'period_start': '2025-07-01' if end=='2026-06-30' else '2026-07-01', 'period_end': end,
            'source_document_id': document, 'document_url': f'https://cob.go.ke/report-{document}.pdf',
            'document_checksum': digest*64, 'publisher': 'Controller of Budget', 'published_on': published,
            'retrieved_at': '2026-10-15T00:00:00Z', 'verified_at': '2026-10-15T00:00:01Z',
            'canonical_url': 'https://www.auditgava.com/counties/1', 'locator': 'PDF page 1; Publication date: '+published,
            'publication_extraction_id': version, 'qualification_extraction_id': version}}


def test_report_contract_has_no_synthetic_financial_fact():
    observation = SourceObservation.model_validate(report_observation())
    assert observation.facts == ()
    text = render(observation)
    assert 'Controller of Budget' in text and 'Nairobi City County' in text and 'FY2025/26' in text
    assert '1 July 2026' in text
    assert not any(term in text for term in ('KES', 'actual spending', '1 report', 'available on AuditGava'))


@pytest.mark.parametrize('mutation', ['mixed', 'financial_category', 'wrong_key', 'missing_date_proof', 'chronology'])
def test_report_contract_refuses_mixed_or_unbound_authority(mutation):
    value = report_observation()
    if mutation == 'mixed':
        from test_generation import observation
        value['facts'] = observation().model_dump(mode='json')['facts']
    if mutation == 'financial_category': value['category'] = 'budget_update'
    if mutation == 'wrong_key': value['source_key'] = 'invented-report-series'
    if mutation == 'missing_date_proof': value['report']['publication_extraction_id'] = None
    if mutation == 'chronology': value['report']['published_on'] = '2099-01-01'
    with pytest.raises(ValidationError): SourceObservation.model_validate(value)


def test_report_baseline_release_replay_and_artifact_refresh(db):
    configure(db)
    first = SourceObservation.model_validate(report_observation())
    assert consume(db, first)['status'] == 'baseline'
    baseline_refresh = SourceObservation.model_validate(report_observation(2, digest='b'))
    assert consume(db, baseline_refresh)['status'] == 'unchanged'
    assert db.scalar(select(func.count()).select_from(SocialPost)) == 0
    explicit = consume(db, baseline_refresh, backfill=True)
    assert explicit['status'] == 'draft_created'
    old_post = db.get(SocialPost, UUID(explicit['post_id']))
    old_revision = db.get(SocialPostRevision, old_post.current_revision_id)
    refresh = SourceObservation.model_validate(report_observation(3, digest='c'))
    assert consume(db, refresh)['status'] == 'unchanged'
    from social.generation.service import verify_generated_revision
    with pytest.raises(SocialError, match='SOURCE_REVIEW_REQUIRED'):
        verify_generated_revision(db, old_post, old_revision)
    db.rollback()
    newer = SourceObservation.model_validate(report_observation(4, published='2026-10-01', period='FY2026/27', end='2027-06-30', document=2, digest='d'))
    created = consume(db, newer)
    assert created['status'] == 'draft_created'
    assert consume(db, newer)['status'] == 'unchanged'
    assert db.scalar(select(func.count()).select_from(SocialPost)) == 2
    revision = db.get(SocialPostRevision, db.get(SocialPost, UUID(created['post_id'])).current_revision_id)
    assert revision.generator_metadata['template_version'] == 'report-availability-v4'
    assert revision.evidence_snapshot['source']['facts'] == []


def test_older_report_cannot_replace_current_series(db):
    configure(db)
    consume(db, SourceObservation.model_validate(report_observation()), backfill=True)
    older = report_observation(2, published='2025-07-01', period='FY2024/25', end='2025-06-30', document=2, digest='b')
    older['report']['period_start'] = '2024-07-01'
    with pytest.raises(SocialError, match='REPORT_RELEASE_REGRESSION'):
        consume(db, SourceObservation.model_validate(older))
    assert db.scalar(select(func.count()).select_from(SocialPost)) == 1


def test_report_row_anchors_deduplicate_and_authority_backfill_requires_fresh_event_version(db):
    from social.generation.service import semantic_fingerprint
    configure(db, [])
    def run(value, **kwargs): return consume(db, SourceObservation.model_validate(value), **kwargs)
    first = report_observation()
    other = deepcopy(first)
    other['report'].update(source_record_id=2, authority_fingerprint='b'*64, qualification_extraction_id=2)
    assert semantic_fingerprint(SourceObservation.model_validate(first)) == semantic_fingerprint(SourceObservation.model_validate(other))
    assert run(first)['status'] == 'baseline'
    assert run(other)['status'] == 'unchanged'
    current = report_observation(2, published='2026-11-01', period='FY2026/27', end='2027-06-30', document=2)
    current['report']['retrieved_at'] = current['report']['verified_at'] = '2026-11-02T00:00:00Z'
    # Keep fixture chronology inside the deterministic service clock.
    from unittest.mock import patch
    from datetime import datetime, timezone
    with patch('social.service.SocialService.now', return_value=datetime(2026,11,3,tzinfo=timezone.utc)):
        assert run(current)['status'] == 'draft_created'
        alternate = deepcopy(current)
        alternate['report'].update(source_record_id=2, authority_fingerprint='b'*64)
        assert run(alternate)['status'] == 'unchanged'
        with pytest.raises(SocialError) as error: run(alternate, backfill=True)
        assert error.value.code == 'EVIDENCE_VERSION_CONFLICT'
        alternate['evidence_version'], alternate['ingestion_id'] = 3, '3'
        assert run(alternate)['status'] == 'unchanged'
        assert run(alternate, backfill=True)['status'] == 'draft_created'

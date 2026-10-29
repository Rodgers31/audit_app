"""PR844 approval boundary regressions on owned offline PostgreSQL only."""
from copy import deepcopy
from uuid import UUID

import pytest
from sqlalchemy import select
from models import BudgetLine, Country, Entity, Extraction, FiscalPeriod, SourceDocument
from seeding.source_observations import (
    SourceObservationUnavailable, current_county_evidence,
    read_county_budget_observation, read_revenue_report_observation,
)
from social.models import SocialPost, SocialPostRevision
from social.generation.contracts import SourceObservation
from social.generation.service import consume_observation, verify_generated_revision
from social.service import SocialService, SocialError
from test_b83_generation_postgres import pg
from test_native_worker_authority import restricted, configure
from test_report_postgres import ingest as county_ingest
from test_kra_catalogue_postgres import ingest as catalogue_ingest
from test_native_financial_changes_postgres import ingest_revenue, read as financial_read


@pytest.mark.parametrize('dependency', ['document', 'country', 'entity', 'period', 'receipt'])
def test_county_qualification_reads_current_projected_context(restricted, tmp_path, dependency):
    factory, _, _, _ = restricted
    job = county_ingest(factory, tmp_path)
    with factory() as db:
        record = db.scalar(select(BudgetLine.id).order_by(BudgetLine.id))
    value = read_county_budget_observation(factory, record_id=record, ingestion_id=job)
    with factory() as db:
        row = db.get(BudgetLine, record)
        source = db.get(SourceDocument, row.source_document_id)
        model, pk = {
            'document': (SourceDocument, source.id),
            'country': (Country, source.country_id),
            'entity': (Entity, row.entity_id),
            'period': (FiscalPeriod, row.period_id),
            'receipt': (Extraction, row.provenance[0]['source_evidence'][0]['receipt']['extraction_id']),
        }[dependency]
        held = db.get(model, pk)
        with factory.begin() as other:
            changed = other.get(model, pk)
            if dependency == 'document':
                changed.publisher = 'Unrelated publisher'
            elif dependency == 'country':
                changed.iso_code = 'UGA'
            elif dependency == 'entity':
                changed.canonical_name = 'Different County'
            elif dependency == 'period':
                changed.label = 'FY1900/01'
            else:
                raw = deepcopy(changed.extracted_json)
                raw['response_receipt']['byte_check']['sha256'] = 'b' * 64
                changed.extracted_json = raw
        # The ordinary default qualification path already projects these columns,
        # so held ORM objects cannot hide a committed change in any dependency.
        if dependency == 'document':
            current = current_county_evidence(db, record_id=record, ingestion_id=job, report=False)
            assert current['facts'][0]['publisher'] == 'Unrelated publisher'
            assert current != value
            from social.generation.worker_authority import capture_worker_authority
            with pytest.raises(SocialError, match='SOURCE_REVIEW_REQUIRED'):
                capture_worker_authority(db, SourceObservation.model_validate(value).model_dump(mode='json'))
        else:
            with pytest.raises(SourceObservationUnavailable):
                current_county_evidence(db, record_id=record, ingestion_id=job, report=False)
        assert held in db


def observation(factory, tmp_path, monkeypatch, kind):
    configure(factory, monkeypatch, financial=kind == 'financial')
    if kind == 'county_financial':
        job = county_ingest(factory, tmp_path)
        with factory() as db:
            record = db.scalar(select(BudgetLine.id).order_by(BudgetLine.id))
        return read_county_budget_observation(factory, record_id=record, ingestion_id=job)
    if kind == 'report':
        job, record = catalogue_ingest(factory, tmp_path)
        return SourceObservation.model_validate(read_revenue_report_observation(
            factory, record_id=record, ingestion_id=job)).model_dump(mode='json')
    job, record = ingest_revenue(factory, tmp_path, monkeypatch)
    return financial_read(factory, job, record)


@pytest.mark.parametrize('kind', ['county_financial', 'report', 'financial'])
@pytest.mark.parametrize('missing', [True, False])
def test_approval_requires_bound_worker_witness(restricted, tmp_path, monkeypatch, kind, missing):
    from social.generation import worker_authority
    factory, _, _, _ = restricted
    value = observation(factory, tmp_path, monkeypatch, kind)
    with monkeypatch.context() as legacy:
        if missing:
            # Models the supported pre-install producer, without editing an
            # immutable historical revision or inventing authority for it.
            legacy.setattr(worker_authority, 'capture_worker_authority', lambda *args: None)
        with factory.begin() as db:
            created = consume_observation(SocialService(db), value, backfill=True)
    with factory.begin() as db:
        post = db.get(SocialPost, UUID(created['post_id']))
        revision = db.get(SocialPostRevision, post.current_revision_id)
        assert ('worker_authority' not in revision.evidence_snapshot) is missing
        if missing:
            with pytest.raises(SocialError, match='SOURCE_REVIEW_REQUIRED'):
                verify_generated_revision(db, post, revision)
        else:
            verify_generated_revision(db, post, revision)

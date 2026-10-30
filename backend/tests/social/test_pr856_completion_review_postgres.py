"""PR856 exact completion claims remain separate from observed chronology."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, func
from models import Entity, Loan, IngestionJob, IngestionStatus, SourceDocument, DocumentType
from seeding.types import DomainRunContext
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_retained_pdf
from social.generation.models import SourceCursor
from social.generation.preview import preview
from social.models import SocialPost
from test_b83_generation_postgres import pg, no_publication
from test_automatic_cohort_timeout_postgres import enabled, ingest_cohort, automatic


def root(db):
    return db.scalar(select(SourceCursor).where(SourceCursor.source_key.endswith(':baseline')))


def completed_claim(cursor):
    state = cursor.report_state
    # The old format implicitly claimed its mutable top-level dates completed.
    return deepcopy(state.get('completion') or {
        'evidence_version': cursor.evidence_version,
        **{k: state[k] for k in ('period_start', 'period_end', 'published_on')},
        'completed_count': state['completed_count'],
    })


@pytest.mark.parametrize('bad_count', [1, 45, 47, 1000])
def test_in_range_wrong_count_never_authorizes_a_new_county(pg, tmp_path, monkeypatch, bad_count):
    factory, _ = pg
    enabled(factory, monkeypatch)
    first = ingest_cohort(factory, tmp_path)
    assert automatic(factory, first)['baselines'] == 46
    with factory.begin() as db:
        cursor = root(db)
        cursor.report_state = {**cursor.report_state, 'completed_count': bad_count}
    newer = ingest_cohort(factory, tmp_path, retained=True, include_nandi=True)
    with factory() as db:
        record = db.scalar(select(Loan.id).join(Entity).where(Entity.canonical_name == 'Nandi County'))
    decision = preview(factory, dict(domain='pending_bills', record_ids=[record], ingestion_id=newer,
        reports=False, backfill=False))
    outcome = automatic(factory, newer)
    with factory() as db:
        posts = db.scalar(select(func.count()).select_from(SocialPost))
    assert decision['results'][0]['status'] == 'refused', (decision, outcome, posts)
    assert outcome['state'] != 'completed' and outcome['drafts_created'] == 0
    assert posts == 0
    no_publication(factory)


def test_partial_later_release_preserves_completed_claim_and_advances_observed_chronology(pg, tmp_path, monkeypatch):
    import social.generation.integration as integration
    from test_financial_review_regressions import ingest, dispatch
    factory, _ = pg
    enabled(factory, monkeypatch)
    first, _ = ingest(factory, tmp_path, monkeypatch, year=2023)
    assert dispatch(factory, first)['baselines'] == 5
    with factory() as db:
        before = completed_claim(root(db))
        before_fingerprint = root(db).fingerprint
    newer, _ = ingest(factory, tmp_path, monkeypatch, year=2024)
    consume = integration.consume_committed_native_financial
    calls = 0
    def interrupted(*args, **kwargs):
        nonlocal calls
        result = consume(*args, **kwargs)
        calls += 1
        if calls == 3:
            raise integration.GenerationDeadlineExceeded('Owned later release interruption before third commit')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(integration, 'consume_committed_native_financial', interrupted)
        partial = dispatch(factory, newer)
    assert partial['state'] == 'failed' and partial['processed'] == 2 and partial['drafts_created'] == 2
    with factory() as db:
        cursor = root(db)
        assert cursor.report_state['period_end'] == '2025-06-30'
        assert cursor.evidence_version == first and cursor.fingerprint == before_fingerprint
        assert completed_claim(cursor) == before
    resumed = dispatch(factory, newer)
    assert resumed['state'] == 'completed' and resumed['drafts_created'] == 3 and resumed['unchanged'] == 2
    with factory() as db:
        assert root(db).evidence_version == newer
        assert completed_claim(root(db)) != before
    again = dispatch(factory, newer)
    assert again['drafts_created'] == 0 and again['unchanged'] == 5
    no_publication(factory)


def test_retained_acquisition_refuses_report_collision_before_publisher_filter(pg, tmp_path, monkeypatch):
    factory, _ = pg
    enabled(factory, monkeypatch)
    ingest_cohort(factory, tmp_path)
    with factory.begin() as db:
        source = db.scalar(select(SourceDocument))
        db.add(SourceDocument(country_id=source.country_id, title='Owned conflicting report', url=source.url,
            publisher='Owned conflicting publisher', doc_type=DocumentType.REPORT,
            fetch_date=datetime.now(timezone.utc), meta={'owned_conflict': True}))
        job = IngestionJob(domain='pending_bills', status=IngestionStatus.RUNNING, dry_run=False,
            started_at=datetime.now(timezone.utc), errors=[], meta={'source_mode': 'live'})
        db.add(job);db.flush()
        with pytest.raises(ValueError, match='One retained native source required'):
            capture_retained_pdf(db, DomainRunContext(None, False, job.id),
                LocalReceiptStore(tmp_path/'receipts'), domain='pending_bills', url=source.url,
                body=(tmp_path/'report.pdf').read_bytes())
    no_publication(factory)


@pytest.mark.parametrize('change', ['member_id', 'member_key', 'completed_date', 'completed_job', 'missing', 'duplicate', 'reordered'])
def test_changed_completion_membership_or_scope_refuses_new_facts(pg, tmp_path, monkeypatch, change):
    factory, _ = pg
    enabled(factory, monkeypatch)
    first = ingest_cohort(factory, tmp_path)
    assert automatic(factory, first)['baselines'] == 46
    with factory.begin() as db:
        cursor = root(db)
        state = deepcopy(cursor.report_state)
        completion = state['completion']
        if change == 'member_id':
            completion['records'][0]['record_id'] += 10000
        elif change == 'member_key':
            completion['records'][0]['source_key'] = 'cob:financial:pending_bills:' + '0' * 64
        elif change == 'completed_date':
            completion['published_on'] = '2026-07-01'
        elif change == 'completed_job':
            completion['evidence_version'] += 1
        elif change == 'missing':
            del state['completion']
        elif change == 'duplicate':
            completion['records'][1] = deepcopy(completion['records'][0])
        else:
            completion['records'].reverse()
        cursor.report_state = state
    newer = ingest_cohort(factory, tmp_path, retained=True, include_nandi=True)
    with factory() as db:
        record = db.scalar(select(Loan.id).join(Entity).where(Entity.canonical_name == 'Nandi County'))
    decision = preview(factory, dict(domain='pending_bills', record_ids=[record], ingestion_id=newer,
        reports=False, backfill=False))
    assert decision['results'][0]['status'] == 'refused'
    outcome = automatic(factory, newer)
    assert outcome['state'] != 'completed' and outcome['drafts_created'] == 0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 0
    no_publication(factory)


def test_partial_marker_cannot_be_promoted_by_an_unbound_in_range_count(pg, tmp_path, monkeypatch):
    from test_first_cohort_recovery_postgres import first_partial
    factory, _ = pg
    first_partial(factory, tmp_path, monkeypatch)
    with factory.begin() as db:
        cursor = root(db)
        cursor.report_state = {**cursor.report_state, 'financial_baseline': 2, 'completed_count': 1}
    newer = ingest_cohort(factory, tmp_path, retained=True)
    outcome = automatic(factory, newer)
    assert outcome['state'] != 'completed' and outcome['drafts_created'] == 0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 0
    no_publication(factory)

"""Source qualification is independent of financial draft generation.

Only the assigned disposable PostgreSQL fixture is used. Publisher-shaped
source bodies are synthetic; this is not production source adoption.
"""
from decimal import Decimal
import pytest
from sqlalchemy import select, func

from models import RevenueBySource
from social.models import SocialPost, SocialPublication
from social.generation.models import SourceCursor
from seeding.generation_dispatch import dispatch_committed_generation
from seeding.source_observations import read_revenue_financial_observation, SourceObservationUnavailable
from test_b83_generation_postgres import pg
from test_native_financial_changes_postgres import ingest_revenue, enable


def ingest_native_refresh(factory, tmp_path, monkeypatch, domain, *, changed=False,
                          expect_publishable=True):
    """Actual writers with sealed owned inputs; no production acquisition."""
    from models import BudgetLine, Loan
    if domain == 'revenue_by_source':
        job, record = ingest_revenue(factory, tmp_path, monkeypatch,
            paye='561' if changed else '560', extra=b'<!-- owned refresh -->')
        return job, record, RevenueBySource, 'amount_billion_kes', Decimal('561' if changed else '560')
    if domain == 'national_budget':
        from test_financial_copy_postgres import national_ingestion
        amount = Decimal('1250000000' if changed else '1200000000')
        job = national_ingestion(factory, tmp_path, actual=str(amount))
        with factory() as db:
            record = db.scalar(select(BudgetLine.id))
        return job, record, BudgetLine, 'actual_spent', amount
    from test_automatic_cohort_timeout_postgres import ingest_cohort
    job = ingest_cohort(factory, tmp_path, correction='all' if changed else None,
                        expect_publishable=expect_publishable)
    with factory() as db:
        record = db.scalar(select(Loan.id).order_by(Loan.id))
    return job, record, Loan, 'outstanding', Decimal('12000000' if changed else '11000000')


@pytest.mark.parametrize('domain', ['revenue_by_source', 'national_budget', 'pending_bills'])
@pytest.mark.parametrize('changed', [False, True], ids=['same-values', 'corrected-value'])
def test_source_disabled_refresh_cannot_reuse_an_admitted_numeric_verdict(
    pg, tmp_path, monkeypatch, domain, changed,
):
    from seeding.native_financial_observations import read_native_financial_observation
    from seeding.native_financial_gate import REASON
    factory, _ = pg
    enable(factory, monkeypatch)
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', 'false')
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED', 'false')
    initial, record, model, measure, _ = ingest_native_refresh(factory, tmp_path, monkeypatch, domain)
    read_native_financial_observation(factory, record_id=record, ingestion_id=initial, domain=domain)
    with factory() as db:
        original = {row.id for row in db.scalars(select(model))}
        assert original and all(row.publishable is True for row in db.scalars(select(model)))

    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'false')
    # An ON financial ceiling in this disposable fixture cannot admit the new source job.
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', 'true')
    current, same_record, _, _, amount = ingest_native_refresh(factory, tmp_path, monkeypatch, domain,
        changed=changed, expect_publishable=False)
    assert current != initial and same_record == record
    with factory() as db:
        rows = list(db.scalars(select(model)))
        assert {row.id for row in rows} == original
        assert getattr(db.get(model, record), measure) == amount
        assert all(row.publishable is False for row in rows), 'Source-disabled refresh inherited an earlier native qualification'
        assert all(row.quarantine_reason in (None, REASON) for row in rows)
    with pytest.raises(SourceObservationUnavailable):
        read_native_financial_observation(factory, record_id=record, ingestion_id=current, domain=domain)
    outcome = dispatch_committed_generation(factory, domain=domain, ingestion_id=current,
        dry_run=False, include_reports=False)
    assert outcome['drafts_created'] == 0 and outcome['refused'] > 0, outcome
    with factory() as db:
        for state in (SocialPost, SocialPublication, SourceCursor):
            assert db.scalar(select(func.count()).select_from(state)) == 0

    # Only a later admitted writer can recover current evidence, with generation OFF.
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', 'false')
    recovered, same_record, _, _, _ = ingest_native_refresh(factory, tmp_path, monkeypatch, domain, changed=changed)
    assert same_record == record
    value = read_native_financial_observation(factory, record_id=record, ingestion_id=recovered, domain=domain)
    assert any(Decimal(fact['value']) == amount for fact in value['facts'])


def test_switching_admission_off_without_a_write_preserves_the_admitted_source(pg, tmp_path, monkeypatch):
    factory, _ = pg
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', 'false')
    job, record = ingest_revenue(factory, tmp_path, monkeypatch)
    before = read_revenue_financial_observation(factory, record_id=record, ingestion_id=job)
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'false')
    after = read_revenue_financial_observation(factory, record_id=record, ingestion_id=job)
    assert before == after
    with factory() as db:
        assert db.get(RevenueBySource, record).publishable is True


def test_disabled_refresh_and_later_readmission_preserve_operator_quarantine(pg, tmp_path, monkeypatch):
    factory, _ = pg
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', 'false')
    _, record = ingest_revenue(factory, tmp_path, monkeypatch)
    with factory.begin() as db:
        row = db.get(RevenueBySource, record)
        row.publishable = False
        row.quarantine_reason = 'operator withheld pending review'
    for admitted in ('false', 'true'):
        monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', admitted)
        job, same_record = ingest_revenue(factory, tmp_path, monkeypatch, paye='561')
        assert same_record == record
        with factory() as db:
            row = db.get(RevenueBySource, record)
            assert row.amount_billion_kes == 561 and row.publishable is False
            assert row.quarantine_reason == 'operator withheld pending review'
        with pytest.raises(SourceObservationUnavailable):
            read_revenue_financial_observation(factory, record_id=record, ingestion_id=job)


def test_failed_disabled_refresh_rolls_back_value_lineage_and_invalidation(pg, tmp_path, monkeypatch):
    import seeding.native_financial_gate as gate
    factory, _ = pg
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', 'false')
    job, record = ingest_revenue(factory, tmp_path, monkeypatch)
    before = read_revenue_financial_observation(factory, record_id=record, ingestion_id=job)
    original_gate = gate.qualify_native_financial_rows
    def abort_after_invalidation(db, rows, **kwargs):
        original_gate(db, rows, **kwargs)
        assert rows and all(row.publishable is False for row in rows)
        raise RuntimeError('owned rollback after disabled refresh')
    with monkeypatch.context() as patch:
        patch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'false')
        patch.setattr(gate, 'qualify_native_financial_rows', abort_after_invalidation)
        with pytest.raises(RuntimeError, match='owned rollback after disabled refresh'):
            ingest_revenue(factory, tmp_path, patch, paye='561')
    assert read_revenue_financial_observation(factory, record_id=record, ingestion_id=job) == before
    with factory() as db:
        assert db.get(RevenueBySource, record).publishable is True


@pytest.mark.parametrize('admit,generate,qualified', [
    ('true', 'false', True),
    ('false', 'true', False),
    ('false', 'false', False),
    ('true', 'true', True),
])
def test_financial_generation_does_not_grant_source_admission(
    pg, tmp_path, monkeypatch, admit, generate, qualified,
):
    factory, _ = pg
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', admit)
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', generate)
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'false')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED', 'false')
    job, record = ingest_revenue(factory, tmp_path, monkeypatch)
    with factory() as db:
        row = db.get(RevenueBySource, record)
        assert row.amount_billion_kes == 560
        assert row.publishable is qualified
    if qualified:
        value = read_revenue_financial_observation(factory, record_id=record, ingestion_id=job)
        assert Decimal(value['facts'][0]['value']) == Decimal('560')
    else:
        with pytest.raises(SourceObservationUnavailable):
            read_revenue_financial_observation(factory, record_id=record, ingestion_id=job)
    assert dispatch_committed_generation(factory, domain='revenue_by_source', ingestion_id=job, dry_run=False) is None
    with factory() as db:
        for model in (SocialPost, SocialPublication, SourceCursor):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_source_only_admission_cannot_open_a_live_generation_hook(pg, tmp_path, monkeypatch):
    factory, _ = pg
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', 'false')
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED', 'false')
    job, record = ingest_revenue(factory, tmp_path, monkeypatch)
    value = read_revenue_financial_observation(factory, record_id=record, ingestion_id=job)
    assert Decimal(value['facts'][0]['value']) == Decimal('560')
    result = dispatch_committed_generation(factory, domain='revenue_by_source', ingestion_id=job, dry_run=False)
    assert result['state'] == 'disabled' and result['reason'] == 'financial_environment_disabled'
    assert result['drafts_created'] == result['processed'] == 0
    with factory() as db:
        for model in (SocialPost, SocialPublication, SourceCursor):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_source_admission_cannot_turn_catalogue_date_into_financial_authority(pg, tmp_path, monkeypatch):
    from test_kra_catalogue_postgres import ingest
    from seeding.source_observations import read_revenue_report_observation
    factory, _ = pg
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', 'false')
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'false')
    job, report = ingest(factory, tmp_path)
    value = read_revenue_report_observation(factory, record_id=report, ingestion_id=job)
    assert value['report']['published_on'] is None
    assert value['report']['evidence_kind'] == 'publisher_catalogue'
    with factory() as db:
        rows = list(db.scalars(select(RevenueBySource)))
        assert rows and all(row.publishable is False for row in rows)
        records = [row.id for row in rows]
    for record in records:
        with pytest.raises(SourceObservationUnavailable):
            read_revenue_financial_observation(factory, record_id=record, ingestion_id=job)

"""Shared CoB PDF identity survives the ordinary budget-then-payables order."""
from datetime import date

import pytest

from sqlalchemy import func, select

from models import Country, DocumentType, Loan, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains.counties_budget.parser import BudgetRecord
from seeding.domains.counties_budget.writer import _ensure_source_document
from seeding.source_observations import read_native_financial_record_ids
from test_automatic_cohort_timeout_postgres import ingest_cohort
from test_b83_generation_postgres import pg, no_publication
from test_b86_native_postgres import enable


def test_budget_title_refresh_preserves_retained_payables_lineage(pg, tmp_path, monkeypatch):
    factory, _ = pg
    enable(factory, monkeypatch)
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', 'true')
    ingest_cohort(factory, tmp_path)
    with factory.begin() as db:
        source = db.scalar(select(SourceDocument))
        source_id, url = source.id, source.url
        original = dict(db.execute(select(Loan.id, Loan.outstanding)).all())
        record = BudgetRecord(
            entity_slug='nairobi', entity_name='Nairobi County',
            period_label='FY2025/26', start_date=date(2025, 7, 1), end_date=date(2026, 6, 30),
            category='Total', subcategory=None, allocated_amount=None, actual_amount=None,
            committed_amount=None, currency='KES', dataset_id=None, source_url=url,
            data_quality='official', source_label='Controller of Budget County BIRR FY2025/26',
            publisher='Office of the Controller of Budget (OCOB)',
        )
        refreshed = _ensure_source_document(db, db.scalar(select(Country.id)),
            SeedingSettings(_env_file=None), record)
        assert refreshed.id == source_id and refreshed.title == record.source_label

    # Actual retained acquisition, sealed parser evidence and atomic writer.
    # Before the fix, the title lookup creates a second source and the native
    # guard correctly refuses: "Exact retained PDF lineage required".
    current_job = ingest_cohort(factory, tmp_path, retained=True)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceDocument)) == 1
        assert set(db.scalars(select(Loan.source_document_id))) == {source_id}
        assert dict(db.execute(select(Loan.id, Loan.outstanding)).all()) == original
    assert len(read_native_financial_record_ids(factory, ingestion_id=current_job, domain='pending_bills')) == 46
    no_publication(factory)


@pytest.mark.parametrize('budget_publisher', ['Controller of Budget', 'Office of the Controller of Budget (OCOB)'])
def test_retained_pending_report_survives_unrelated_budget_row_for_same_pdf(pg, tmp_path, monkeypatch, budget_publisher):
    factory, _ = pg
    enable(factory, monkeypatch)
    monkeypatch.setenv('SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', 'true')
    ingest_cohort(factory, tmp_path)
    with factory.begin() as db:
        source = db.scalar(select(SourceDocument))
        report_id = source.id
        original = dict(db.execute(select(Loan.id, Loan.outstanding)).all())
        twin = SourceDocument(country_id=source.country_id, title=source.title, url=source.url,
            publisher=budget_publisher, doc_type=DocumentType.BUDGET, fetch_date=source.fetch_date,
            meta={'owned_unrelated_budget_lane': True})
        db.add(twin);db.flush();budget_id=twin.id
    current = ingest_cohort(factory, tmp_path, retained=True)
    with factory() as db:
        assert db.get(SourceDocument, budget_id).meta == {'owned_unrelated_budget_lane': True}
        assert db.scalar(select(func.count()).select_from(SourceDocument)) == 2
        assert set(db.scalars(select(Loan.source_document_id))) == {report_id}
        assert dict(db.execute(select(Loan.id, Loan.outstanding)).all()) == original
    assert len(read_native_financial_record_ids(factory, ingestion_id=current, domain='pending_bills')) == 46
    no_publication(factory)

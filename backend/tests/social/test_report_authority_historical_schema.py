"""Exact report-view acceptance on owned clean and prebaseline PostgreSQL.

The controller migrates each empty database from baseline, inserting only the
documented historical column shape before later migrations create the views.
Never accept an application, pooler or remote database as this fixture.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from social.worker.config import WorkerConfig, create_worker_engine
from social.worker.role_contract import install_worker_role, verify_worker_role, WorkerRoleError
from test_report_authority_role import test_digest_view_drift_refuses_readiness_and_install as _assert_drift


@pytest.fixture
def historical_report_role():
    value = os.getenv('B17_REPORT_ROLE_TEST_DB_URL')
    if not value:
        pytest.skip('Requires the owned B17 clean/historical PostgreSQL controller')
    url = make_url(value)
    if (url.drivername != 'postgresql+psycopg2' or url.host != '127.0.0.1'
            or url.port != 55439 or url.username != 'postgres' or url.query
            or url.database not in {'b17_view_clean', 'b17_view_historical'}):
        raise RuntimeError('Only the assigned owned B17 PostgreSQL fixture is allowed')
    role = url.database
    owner = create_engine(url, pool_size=2, max_overflow=0,
                          connect_args={'hostaddr': '127.0.0.1', 'connect_timeout': 5,
                                        'options': '-clock_timeout=2000 -cstatement_timeout=5000'})
    # Pin libpq's physical destination as well as its nominal host. Ambient
    # PGHOSTADDR must never redirect this superuser-only fixture connection.
    worker_url = url.set(username=role, query={'hostaddr': '127.0.0.1'})
    worker = create_worker_engine(WorkerConfig(str(worker_url), database_schema='public'))
    try:
        with owner.begin() as conn:
            assert conn.scalar(text('SELECT current_database()')) == url.database
            assert conn.scalar(text('SELECT version_num FROM alembic_version')) == 'e621b17a0001'
            assert conn.scalar(text('SELECT publishing_enabled FROM social_controls WHERE id=1')) is False
        install_worker_role(owner, role)
        verify_worker_role(worker, role)
        yield owner, worker, role
    finally:
        worker.dispose()
        owner.dispose()


def test_actual_login_accepts_reviewed_view_without_financial_access(historical_report_role):
    owner, worker, role = historical_report_role
    with worker.begin() as conn:
        assert list(conn.execute(text('SELECT * FROM social_report_source_authority'))) == []
    for query in ('SELECT * FROM budget_lines', 'SELECT * FROM source_documents',
                  'SELECT * FROM extractions', 'SELECT * FROM ingestion_jobs',
                  'SELECT * FROM social_report_source_authority_snapshot',
                  "UPDATE social_report_source_authority SET authority_fingerprint=repeat('a',64)"):
        with pytest.raises(Exception) as error:
            with worker.begin() as conn:
                conn.execute(text(query))
        assert error.value.orig.pgcode in {'42501', '55000'}
    verify_worker_role(worker, role)


@pytest.mark.parametrize('drift', ['definition', 'columns', 'options', 'owner', 'rewrite',
                                 'grant_option', 'unrelated_view', 'missing', 'literal'])
def test_existing_hostile_views_still_refuse(historical_report_role, drift):
    owner, worker, role = historical_report_role
    _assert_drift((None, owner, worker, role), drift)


def test_locked_variant_is_not_accepted_as_snapshot(historical_report_role):
    owner, worker, role = historical_report_role
    with owner.begin() as conn:
        original = conn.scalar(text("SELECT pg_get_viewdef('social_report_source_authority_snapshot'::regclass,true)"))
        locked = conn.scalar(text("SELECT pg_get_viewdef('social_report_source_authority'::regclass,true)"))
        conn.execute(text('CREATE OR REPLACE VIEW social_report_source_authority_snapshot WITH (security_barrier=true) AS '+locked))
    try:
        with pytest.raises(WorkerRoleError):
            verify_worker_role(worker, role)
        with pytest.raises(WorkerRoleError):
            install_worker_role(owner, role)
    finally:
        with owner.begin() as conn:
            conn.execute(text('CREATE OR REPLACE VIEW social_report_source_authority_snapshot WITH (security_barrier=true) AS '+original))
    verify_worker_role(worker, role)


def test_seeded_source_changes_invalidate_only_a_digest_witness(historical_report_role):
    """Synthetic source rows qualify the witness port, never publication/data gates."""
    from datetime import datetime, timezone
    from uuid import uuid4
    from sqlalchemy.orm import Session
    from models import (BudgetLine, Country, DocumentType, Entity, EntityType,
                        FiscalPeriod, IngestionJob, IngestionStatus, SourceDocument)
    owner, worker, _ = historical_report_role
    now = datetime.now(timezone.utc)
    rows = []
    try:
        with Session(owner, expire_on_commit=False) as db, db.begin():
            country = Country(iso_code='ZZZ', name='Synthetic owned view fixture', currency='KES',
                              timezone='UTC', default_locale='en')
            db.add(country); db.flush(); rows.append(country)
            entity = Entity(country_id=country.id, type=EntityType.COUNTY,
                            canonical_name='Synthetic owned county', slug='view-' + uuid4().hex)
            period = FiscalPeriod(country_id=country.id, label='Synthetic fixture period',
                                  start_date=now, end_date=now)
            document = SourceDocument(country_id=country.id, publisher='Synthetic fixture',
                                      title='Synthetic fixture', url='https://owned.invalid/synthetic-report.pdf',
                                      fetch_date=now, doc_type=DocumentType.REPORT)
            job = IngestionJob(domain='counties_budget', status=IngestionStatus.COMPLETED,
                               dry_run=True, started_at=now, finished_at=now, errors=[],
                               meta={'source_mode': 'fixture'})
            db.add_all([entity, period, document, job]); db.flush()
            rows.extend([entity, period, document, job])
            record = BudgetLine(entity_id=entity.id, period_id=period.id, category='Synthetic fixture',
                                currency='KES', source_document_id=document.id, notes='before',
                                publishable=False, provenance=[{'ingestion_job_id': job.id}])
            db.add(record); db.flush(); rows.append(record)
        query = text('SELECT record_id,ingestion_id,authority_fingerprint FROM '
                     'social_report_source_authority WHERE record_id=:record')
        def witness():
            with worker.begin() as conn:
                result = conn.execute(query, {'record': record.id}).mappings().one()
                assert dict(result).keys() == {'record_id', 'ingestion_id', 'authority_fingerprint'}
                assert result['ingestion_id'] == job.id
                assert len(result['authority_fingerprint']) == 64
                return result['authority_fingerprint']
        original = witness()
        with owner.begin() as conn:
            conn.execute(text("UPDATE budget_lines SET notes='after' WHERE id=:id"), {'id': record.id})
        changed = witness()
        assert changed != original
        with owner.begin() as conn:
            historical = conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_attribute WHERE "
                "attrelid='public.budget_lines'::regclass AND attname='validation_warnings' AND NOT attisdropped)"))
            if historical:
                conn.execute(text("UPDATE budget_lines SET validation_warnings='[\"synthetic change\"]'::jsonb WHERE id=:id"),
                             {'id': record.id})
        if historical:
            assert witness() != changed
        verify_worker_role(worker, historical_report_role[2])
    finally:
        # This test's committed synthetic rows only; never truncate fixture history.
        with Session(owner) as db, db.begin():
            for row in reversed(rows):
                value = db.get(type(row), row.id)
                if value is not None:
                    db.delete(value)
                    db.flush()

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
                          connect_args={'connect_timeout': 5,
                                        'options': '-clock_timeout=2000 -cstatement_timeout=5000'})
    worker = create_worker_engine(WorkerConfig(str(url.set(username=role)), database_schema='public'))
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

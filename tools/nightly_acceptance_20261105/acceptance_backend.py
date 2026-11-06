"""Supported PG adapter for the real canonical backend fixtures, with observations.

Only the known backend/conftest.py fixture is redirected. Its original table,
transaction and application behavior still runs in a new owned PostgreSQL schema.
"""
import os
from pathlib import Path
import sys

import pytest
from common import publish, require

PG_CASES = []
DATABASES = []


def pytest_sessionstart(session):
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    from tests.acceptance_owned_pg import _database, target_from_environment
    from acceptance_backend_config import FISCAL_URL
    url, token, args = target_from_environment()
    for database, target in [('auditgava_refresh_fixture', url), ('fiscal_fixture', FISCAL_URL)]:
        engine = create_engine(target, connect_args=dict(args, dbname=database), poolclass=NullPool)
        try:
            with engine.connect() as connection:
                DATABASES.append(list(_database(connection, token, database)))
        finally:
            engine.dispose()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_fixture_setup(fixturedef, request):
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from tests.acceptance_owned_pg import owned_schema
    source = Path(getattr(fixturedef.func, '__code__').co_filename).absolute()
    canonical = Path(__file__).absolute().parents[2] / 'backend/conftest.py'
    if fixturedef.argname == '_setup_tables' and source == canonical:
        module = sys.modules[fixturedef.func.__module__]
        manager = owned_schema()
        engine, _ = manager.__enter__()
        previous = module.engine, module.TestingSessionLocal
        module.engine = engine
        module.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        def close():
            try:
                manager.__exit__(None, None, None)
            finally:
                module.engine, module.TestingSessionLocal = previous
        # Registered before the original yield teardown, hence runs after it.
        request.addfinalizer(close)
    outcome = yield
    if fixturedef.argname == 'db_session' and source == canonical:
        db = outcome.get_result()
        require(db.get_bind().dialect.name == 'postgresql', 'canonical backend case did not use PostgreSQL')
        schema = db.scalar(text('SELECT current_schema()'))
        require(type(schema) is str and schema.startswith('acceptance_'), 'unowned backend fixture schema')
        PG_CASES.append(request.node.nodeid)
    if fixturedef.argname == 'seed_source_doc' and source == canonical:
        db = request.getfixturevalue('db_session')
        db.execute(text("SELECT setval(pg_get_serial_sequence('source_documents','id'),"
                        "(SELECT max(id) FROM source_documents),true)"))


def pytest_sessionfinish(session, exitstatus):
    from tests.acceptance_owned_pg import CLOSED_SCHEMAS
    from acceptance_inventory import ORIGINAL_PG, ORIGINAL_CONSTANT
    require(len(set(PG_CASES)) == len(PG_CASES), 'duplicate canonical PG case observation')
    if os.environ['NIGHTLY_ORIGINAL_FAMILY'] == 'original36':
        selected = {item.nodeid for item in session.items}
        require(set(ORIGINAL_PG) | {ORIGINAL_CONSTANT} <= selected, 'original36 selection incomplete')
        require(set(ORIGINAL_PG) <= set(PG_CASES) and ORIGINAL_CONSTANT not in PG_CASES,
                'original36 must contain exactly 35 actual PG cases and one constant')
    publish(Path(os.environ['NIGHTLY_BACKEND_REPORT']), {
        'schema': 'nightly-backend-observations-v1', 'exitstatus': int(exitstatus),
        'databases': DATABASES, 'canonical_pg_cases': sorted(PG_CASES),
        'closed_schemas': CLOSED_SCHEMAS,
        'schema_scope': 'isolated-model-fixtures-not-migrated-production',
        'original_family': os.environ['NIGHTLY_ORIGINAL_FAMILY']})

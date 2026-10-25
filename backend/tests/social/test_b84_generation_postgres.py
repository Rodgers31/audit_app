"""Current-schema review controls, using only the explicitly owned B83 fixture."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from test_b83_generation_postgres import pg, first_record, no_publication
from test_report_postgres import ingest, enabled
from models import BudgetLine, IngestionJob
from services.generation_outcome import safe_generation_outcome
from social.models import SocialPost

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('package', [False, True])
def test_current_reader_and_preview_execute_in_both_launch_modes(pg, tmp_path, monkeypatch, package):
    factory, _ = pg
    enabled(factory, monkeypatch)
    job = ingest(factory, tmp_path)
    record = first_record(factory, job)
    prefix = 'backend.' if package else ''
    script = f'''import importlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
prefix={prefix!r}
reader=importlib.import_module(prefix+'seeding.source_observations')
preview=importlib.import_module(prefix+'social.generation.preview').preview
model=importlib.import_module(prefix+'models')
social=importlib.import_module(prefix+'social.models')
assert model.Base is social.Base
assert reader.BudgetLine is model.BudgetLine
engine=create_engine({os.environ['B83_SOCIAL_TEST_DB_URL']!r},pool_size=1,max_overflow=0)
factory=sessionmaker(bind=engine,expire_on_commit=False)
try:
    value=reader.read_county_budget_observation(factory,record_id={record},ingestion_id={job})
    assert value['publishable'] is True and value['committed'] is True
    for reports in (False,True):
        result=preview(factory,dict(domain='counties_budget',record_ids=[{record}],ingestion_id={job},reports=reports))
        assert result['results'][0]['status']=='baseline',result
    if prefix:
        import sys
        assert 'models' not in sys.modules and 'seeding' not in sys.modules
finally:
    engine.dispose()
'''
    env = {k: v for k, v in os.environ.items() if not k.startswith(('PG', 'SOCIAL_')) and k not in {'PYTHONPATH', 'DATABASE_URL'}}
    env.update(PYTHONPATH=str(ROOT if package else ROOT/'backend'), PYTHON_DOTENV_DISABLED='1', DATABASE_URL='postgresql+psycopg2://inert:inert@127.0.0.1:1/unused')
    result = subprocess.run([sys.executable, '-c', script], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stderr
    no_publication(factory)


def test_current_pg_confirmed_refusal_survives_later_commit_uncertainty(pg, tmp_path, monkeypatch):
    import seeding.generation_dispatch as bridge
    from social.generation.preview import preview
    factory, engine = pg
    enabled(factory, monkeypatch)
    first = ingest(factory, tmp_path)
    bridge.dispatch_committed_generation(factory, domain='counties_budget', ingestion_id=first, dry_run=False)
    newer = ingest(factory, tmp_path, year=2024, published='2025-07-01')
    record = first_record(factory, newer)
    with factory.begin() as db:
        db.get(BudgetLine, record).actual_spent += 1
    refusal = preview(factory, dict(domain='counties_budget', record_ids=[record], ingestion_id=newer))['results'][0]
    assert refusal['status'] == 'refused'
    def lost(session):
        raise DBAPIError('COMMIT', {}, RuntimeError('inert lost acknowledgement'), connection_invalidated=True)
    original = bridge._invoke_reports
    monkeypatch.setattr(bridge, '_invoke_reports', lambda _factory, records, job: original(factory, records, job))
    telemetry = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    event.listen(factory.class_, 'after_commit', lost)
    try:
        result = bridge.dispatch_committed_report_generation(telemetry, domain='counties_budget', ingestion_id=newer, dry_run=False)
    finally:
        event.remove(factory.class_, 'after_commit', lost)
    assert result['execution_unverified'] is True and result['refused'] is None
    assert result['confirmed']['refused'] == 1
    assert result['refusal_reasons'] == {refusal['reason']: 1}
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 1
        persisted = safe_generation_outcome(db.get(IngestionJob, newer).meta['post_commit_report_generation'])
        assert persisted['refusal_reasons'] == result['refusal_reasons']
        assert persisted['processed'] is None
    no_publication(factory)


def test_preview_transaction_bounds_preserve_stricter_inherited_limits(pg, tmp_path, monkeypatch):
    from social.generation.preview import preview
    factory, engine = pg
    enabled(factory, monkeypatch)
    job = ingest(factory, tmp_path)
    record = first_record(factory, job)
    bounded = sessionmaker(bind=engine, expire_on_commit=False)
    def transaction_started(session, transaction, connection):
        connection.execute(text("SET LOCAL statement_timeout='1000ms'"))
        connection.execute(text("SET LOCAL lock_timeout='500ms'"))
    event.listen(bounded.class_, 'after_begin', transaction_started)
    statements = []
    def before_execute(connection, cursor, statement, parameters, context, executemany):
        if 'set_config' in statement:
            statements.append(statement)
    event.listen(engine, 'before_cursor_execute', before_execute)
    try:
        assert preview(bounded, dict(domain='counties_budget', record_ids=[record], ingestion_id=job))['results'][0]['status'] == 'baseline'
        with bounded() as db:
            # Actual PostgreSQL helper must keep, rather than relax, inherited limits.
            from social.generation.integration import _transaction_limits
            import time
            _transaction_limits(db, time.monotonic()+0.25)
            values = dict(db.execute(text("SELECT name,setting FROM pg_settings WHERE name IN ('statement_timeout','lock_timeout')")).all())
            assert 1 <= int(values['statement_timeout']) <= 250
            assert 1 <= int(values['lock_timeout']) <= 250
        assert len(statements) >= 4
    finally:
        event.remove(engine, 'before_cursor_execute', before_execute)
        event.remove(bounded.class_, 'after_begin', transaction_started)
    no_publication(factory)

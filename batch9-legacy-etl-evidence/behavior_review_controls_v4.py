"""Independent executable legacy boundary controls. Only owned SQLite files."""
import asyncio
import contextlib
import hashlib
import io
import json
import os
import platform
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['DATABASE_URL'] = 'sqlite:////tmp/batch9-legacy-behavior-bootstrap.sqlite'
os.environ['AWS_BUCKET_NAME'] = ''
os.environ['AWS_ACCESS_KEY_ID'] = ''
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT))
def no_network(*args, **kwargs):
    raise RuntimeError('External transports forbidden in independent owned SQLite controls')
socket.socket.connect = no_network
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from models import Base
from seeding.exclusion import DomainOwnershipError, enter_domain, reserve
from etl.database_loader import DatabaseLoader
from etl.writer_ownership import OwnedSession, check_ready, writer_scope
from uuid import uuid4

@compiles(JSONB, 'sqlite')
def sqlite_json(*args, **kwargs):
    return 'TEXT'

class CommitAfterEffect(sqlite3.Connection):
    fail_next = False
    def commit(self):
        super().commit()
        if type(self).fail_next:
            type(self).fail_next = False
            raise sqlite3.OperationalError('owned fixture: connection lost after commit')

def fixture(root, name, faulty=False):
    path = root / f'{name}.sqlite'
    if faulty:
        engine = create_engine('sqlite://', creator=lambda: sqlite3.connect(str(path), factory=CommitAfterEffect, check_same_thread=False))
    else:
        engine = create_engine(f'sqlite:///{path}')
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE inert_effects(value INTEGER)'))
    loader = DatabaseLoader(f'sqlite:///{path}')
    if faulty:
        loader.engine.dispose()
        loader.engine = engine
        loader.SessionLocal.configure(bind=engine)
    return engine, loader

def state(engine):
    with engine.connect() as conn:
        return dict(effects=conn.scalar(text('SELECT count(*) FROM inert_effects')),
                    active=conn.scalar(text('SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL')),
                    released=conn.scalar(text('SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NOT NULL')))

def attempt(function):
    try:
        value = function()
        return dict(returned=True, value=repr(value))
    except BaseException as exc:
        return dict(returned=False, error=type(exc).__name__, diagnostic=str(exc))

results = []
source_paths = [ROOT/'etl/writer_ownership.py', ROOT/'etl/database_loader.py', ROOT/'etl/kenya_pipeline.py', ROOT/'etl/monitored_runner.py', ROOT/'etl/scheduler.py']
start_source_sha256 = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
with tempfile.TemporaryDirectory(prefix='batch9-legacy-behavior-') as scratch:
    scratch = Path(scratch)
    engine, loader = fixture(scratch, 'normal')
    session = loader.get_db_session()
    session.execute(text('INSERT INTO inert_effects VALUES(1)'))
    session.commit()
    session.close()
    results.append(dict(control='normal_manual_session', outcome=state(engine)))
    results.append(dict(control='closed_session_reuse', outcome=attempt(lambda: session.execute(text('INSERT INTO inert_effects VALUES(1)'))), state=state(engine)))
    engine.dispose(); loader.engine.dispose()

    engine, loader = fixture(scratch, 'task')
    async def task_transfer():
        session = loader.get_db_session()
        calls = []
        async def other_task():
            calls.append(dict(api='Session.execute', outcome=attempt(lambda: session.execute(text('INSERT INTO inert_effects VALUES(1)')))))
            def core():
                conn = session.connection()
                conn.execute(text('INSERT INTO inert_effects VALUES(1)'))
                conn.commit()
            calls.append(dict(api='Session.connection().execute()/commit()', outcome=attempt(core)))
        await asyncio.create_task(other_task())
        session.close()
        return calls
    calls = asyncio.run(task_transfer())
    results.append(dict(control='cross_task_session_transfer', calls=calls, state=state(engine)))
    engine.dispose(); loader.engine.dispose()

    engine, loader = fixture(scratch, 'thread')
    session = loader.SessionLocal()
    calls = []
    def other_thread():
        calls.append(dict(api='Session.execute', outcome=attempt(lambda: session.execute(text('INSERT INTO inert_effects VALUES(1)')))))
        def core():
            conn = session.connection()
            conn.execute(text('INSERT INTO inert_effects VALUES(1)'))
            conn.commit()
        calls.append(dict(api='Session.connection().execute()/commit()', outcome=attempt(core)))
    thread = threading.Thread(target=other_thread)
    thread.start(); thread.join()
    session.close()
    results.append(dict(control='cross_thread_session_transfer', calls=calls, state=state(engine)))
    engine.dispose(); loader.engine.dispose()

    engine, loader = fixture(scratch, 'core_commit_uncertainty', faulty=True)
    session = loader.get_db_session()
    def raw_commit():
        conn = session.connection()
        conn.execute(text('INSERT INTO inert_effects VALUES(1)'))
        CommitAfterEffect.fail_next = True
        conn.commit()
    commit = attempt(raw_commit)
    close = attempt(session.close)
    before_next = state(engine)
    def later_effect():
        with loader.get_db_session() as later:
            later.execute(text('INSERT INTO inert_effects VALUES(2)'))
            later.commit()
    next_session = attempt(later_effect)
    results.append(dict(control='connection_commit_uncertainty', commit=commit, close=close, before_next=before_next, next_session=next_session, final=state(engine)))
    engine.dispose(); loader.engine.dispose()

    engine, loader = fixture(scratch, 'session_begin_uncertainty', faulty=True)
    session = loader.get_db_session()
    def transaction_commit():
        with session.begin():
            session.execute(text('INSERT INTO inert_effects VALUES(1)'))
            CommitAfterEffect.fail_next = True
    commit = attempt(transaction_commit)
    close = attempt(session.close)
    results.append(dict(control='session_begin_commit_uncertainty', commit=commit, close=close, final=state(engine)))
    engine.dispose(); loader.engine.dispose()

    engine, loader = fixture(scratch, 'interrupt')
    def interrupt():
        with writer_scope(loader.engine):
            with loader.get_db_session() as session:
                session.execute(text('INSERT INTO inert_effects VALUES(1)'))
                session.commit()
            raise KeyboardInterrupt('owned interruption after committed effect')
    outcome = attempt(interrupt)
    results.append(dict(control='baseexception_interrupt', outcome=outcome, final=state(engine)))
    engine.dispose(); loader.engine.dispose()

    engine = create_engine(f'sqlite:///{scratch / "missing.sqlite"}')
    results.append(dict(control='missing_schema_startup', outcome=attempt(lambda: check_ready(engine))))
    engine.dispose()
    for invalid in [None, SimpleNamespace(dialect=SimpleNamespace(name='mysql')), SimpleNamespace(dialect=None)]:
        results.append(dict(control='malformed_storage', input=repr(invalid), outcome=attempt(lambda: check_ready(invalid))))

    engine, loader = fixture(scratch, 'pipeline_refusal')
    with sessionmaker(bind=engine).begin() as session:
        assert reserve(session, 'audits', uuid4())
    import etl.kenya_pipeline as pipeline_module
    import etl.monitored_runner as monitored_module
    import etl.scheduler as scheduler_module
    original_init = pipeline_module.KenyaDataPipeline.__init__
    storage = scratch / 'pipeline-storage'
    storage.mkdir()
    doc = dict(url='https://fixture.invalid/owned.pdf', source_key='oag', title='Owned inert audit', source='Inert fixture', doc_type='audit')
    finding = dict(finding_text='inert finding', severity='info', entity=dict(canonical_name='Inert entity', type='agency'))
    def inert_init(self, *args, **kwargs):
        original_init(self, str(storage))
        if os.getenv('BATCH9_BEHAVIOR_KEEP_OPTIONAL_LOADER') != 'true':
            self.db_loader = loader
        self.discover_budget_documents = lambda source: [dict(doc)] if source == 'oag' else []
        self.http.get = lambda *a, **kw: SimpleNamespace(content=b'%PDF-owned-independent-control', headers={'content-type': 'application/pdf'}, raise_for_status=lambda: None)
        self.extractor.extract_with_fallback = lambda path: {'confidence': 1., 'tables': []}
        self.audit_parser.parse = lambda *a: [dict(finding)]
        self.data_validator.validate_audit_data = lambda item: SimpleNamespace(is_valid=True, confidence=1., warnings=[])
        self._maybe_upload_to_s3 = lambda *a: None
        self.scheduler = SimpleNamespace(get_schedule_summary=lambda: {'efficiency': {'skip_percentage': 0}}, should_run=lambda source: (True, 'Owned fixture'))
    pipeline_module.KenyaDataPipeline.__init__ = inert_init
    os.environ['DATABASE_URL'] = str(loader.engine.url)
    captured = io.StringIO()
    async def pipeline_controls():
        pipe = pipeline_module.KenyaDataPipeline()
        try:
            result = await pipe.download_and_process_document(dict(doc))
            results.append(dict(control='direct_pipeline_ownership_refusal', returned=True, result=result))
        except BaseException as exc:
            results.append(dict(control='direct_pipeline_ownership_refusal', returned=False, error=type(exc).__name__, diagnostic=str(exc)))
        monitor = monitored_module.ETLMonitor()
        try:
            full_result = await monitor.run_with_monitoring(pipe.run_full_pipeline)
            results.append(dict(control='full_pipeline_monitor_ownership_refusal', returned=True, result=full_result, monitor_success=monitor.success))
        except BaseException as exc:
            results.append(dict(control='full_pipeline_monitor_ownership_refusal', returned=False, error=type(exc).__name__, monitor_success=monitor.success))
        try:
            await scheduler_module.run_once()
            results.append(dict(control='scheduler_ownership_refusal', returned=True))
        except BaseException as exc:
            results.append(dict(control='scheduler_ownership_refusal', returned=False, error=type(exc).__name__))
    with contextlib.redirect_stdout(captured):
        results.append(dict(control='pipeline_controls_execution', outcome=attempt(lambda: asyncio.run(pipeline_controls()))))
    results.append(dict(control='pipeline_stdout', value=captured.getvalue()))
    results.append(dict(control='pipeline_refusal_financial_effects', state=state(engine)))
    os.environ['DATABASE_URL'] = 'owned_invalid_dialect://inert'
    os.environ['BATCH9_BEHAVIOR_KEEP_OPTIONAL_LOADER'] = 'true'
    async def optional_fallback_controls():
        pipe = pipeline_module.KenyaDataPipeline()
        results.append(dict(control='optional_loader_constructor', class_name=type(pipe.db_loader).__name__))
        try:
            value = await pipe.download_and_process_document(dict(doc))
            results.append(dict(control='optional_loader_direct_pipeline', returned=True, result=value))
        except BaseException as exc:
            results.append(dict(control='optional_loader_direct_pipeline', returned=False, error=type(exc).__name__))
        monitor = monitored_module.ETLMonitor()
        try:
            value = await monitor.run_with_monitoring(pipe.run_full_pipeline)
            results.append(dict(control='optional_loader_full_pipeline', returned=True, result=value, monitor_success=monitor.success))
        except BaseException as exc:
            results.append(dict(control='optional_loader_full_pipeline', returned=False, error=type(exc).__name__, monitor_success=monitor.success))
        try:
            await scheduler_module.run_once()
            results.append(dict(control='optional_loader_scheduler', returned=True))
        except BaseException as exc:
            results.append(dict(control='optional_loader_scheduler', returned=False, error=type(exc).__name__))
    with contextlib.redirect_stdout(captured):
        results.append(dict(control='optional_loader_execution', outcome=attempt(lambda: asyncio.run(optional_fallback_controls()))))
    results.append(dict(control='optional_loader_stdout', value=captured.getvalue()))
    os.environ.pop('BATCH9_BEHAVIOR_KEEP_OPTIONAL_LOADER')
    os.environ['DATABASE_URL'] = str(loader.engine.url)
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE etl_dispatch_domains'))
    results.append(dict(control='missing_dispatch_seam_startup', outcome=attempt(loader.check_ownership_ready)))
    async def missing_dispatch_controls():
        pipe = pipeline_module.KenyaDataPipeline()
        monitor = monitored_module.ETLMonitor()
        try:
            value = await monitor.run_with_monitoring(pipe.run_full_pipeline)
            results.append(dict(control='missing_dispatch_seam_full_pipeline', returned=True, result=value, monitor_success=monitor.success))
        except BaseException as exc:
            results.append(dict(control='missing_dispatch_seam_full_pipeline', returned=False, error=type(exc).__name__, monitor_success=monitor.success))
        try:
            await scheduler_module.run_once()
            results.append(dict(control='missing_dispatch_seam_scheduler', returned=True))
        except BaseException as exc:
            results.append(dict(control='missing_dispatch_seam_scheduler', returned=False, error=type(exc).__name__))
    with contextlib.redirect_stdout(captured):
        results.append(dict(control='missing_dispatch_seam_execution', outcome=attempt(lambda: asyncio.run(missing_dispatch_controls()))))
    results.append(dict(control='missing_dispatch_seam_stdout', value=captured.getvalue()))
    pipeline_module.KenyaDataPipeline.__init__ = original_init
    engine.dispose(); loader.engine.dispose()

receipt = dict(generated_by=str(Path(__file__).relative_to(ROOT)), generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               generated_at=datetime.now(timezone.utc).isoformat(), target_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               command=' '.join(sys.argv), executable=sys.executable, python=sys.version, sqlalchemy=sqlalchemy.__version__, platform=platform.platform(),
               start_source_sha256=start_source_sha256,
               source_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths},
               limitation='SQLite behavioral controls only; no PostgreSQL advisory-lock/race acceptance claim.', results=results)
target = Path(sys.argv[1])
target.write_text(json.dumps(receipt, indent=2))
readback = json.loads(target.read_text())
assert readback['generator_sha256'] == receipt['generator_sha256']
assert readback['results'] == receipt['results']
print(json.dumps(receipt, indent=2))

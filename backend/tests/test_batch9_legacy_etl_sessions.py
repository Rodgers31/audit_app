"""Portable behavior regressions for the public legacy Session boundary."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from models import Base
from seeding.exclusion import DomainOwnershipError, enter_domain

# Resolve native seeding first, then root ETL (backend also has an etl package).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from etl.database_loader import DatabaseLoader
from etl.writer_ownership import writer_scope


@compiles(JSONB, "sqlite")
def jsonb_sqlite(*args, **kwargs):
    return "TEXT"


@pytest.fixture
def loader(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    owned = DatabaseLoader("sqlite:///" + str(tmp_path / "legacy.sqlite"))
    Base.metadata.create_all(owned.engine)
    with owned.engine.begin() as conn:
        conn.execute(text("CREATE TABLE inert_effects(n integer)"))
    yield owned
    owned.engine.dispose()


def counts(loader):
    with loader.engine.connect() as conn:
        return (conn.scalar(text("SELECT count(*) FROM inert_effects")),
                conn.scalar(text("SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL")))


@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_manual_sessions_release_only_after_last_normal_close(loader, order):
    sessions = [loader.get_db_session(), loader.SessionLocal()]
    for session in sessions:
        session.execute(text("INSERT INTO inert_effects VALUES(1)"))
        session.commit()
    sessions[order[0]].close()
    assert counts(loader) == (2, 13)
    sessions[order[1]].close()
    assert counts(loader) == (2, 0)
    with loader.get_db_session() as session:
        session.execute(text("INSERT INTO inert_effects VALUES(1)"))
        session.commit()
    assert counts(loader) == (3, 0)


def test_external_transaction_bind_cannot_outlive_claim_release(loader):
    with loader.engine.connect() as conn:
        with conn.begin():
            with pytest.raises(DomainOwnershipError):
                loader.SessionLocal(bind=conn)
            assert counts(loader) == (0, 0)


def test_raw_connection_escape_and_transferred_sessions_refuse(loader):
    with loader.get_db_session() as session:
        with pytest.raises(DomainOwnershipError):
            session.connection()
        def transferred():
            with pytest.raises(DomainOwnershipError):
                session.execute(text("INSERT INTO inert_effects VALUES(1)"))
        with ThreadPoolExecutor(1) as pool:
            pool.submit(transferred).result(timeout=5)
        async def other_task():
            with pytest.raises(DomainOwnershipError):
                session.commit()
        asyncio.run(other_task())
        assert counts(loader) == (0, 13)
    assert counts(loader) == (0, 0)


def test_alternate_bind_arguments_cannot_escape_owned_engine(loader, tmp_path):
    other = create_engine("sqlite:///" + str(tmp_path / "other.sqlite"))
    try:
        with loader.get_db_session() as session:
            with other.connect() as conn:
                for bind in (other, conn):
                    with pytest.raises(DomainOwnershipError):
                        session.execute(text("SELECT 1"), bind_arguments={"bind": bind})
            with pytest.raises(DomainOwnershipError):
                session.bind_table(Base.metadata.tables["countries"], other)
            with pytest.raises(DomainOwnershipError):
                session.bind_mapper(__import__("models").Country, other)
        assert counts(loader) == (0, 0)
    finally:
        other.dispose()


@pytest.mark.parametrize("method", ["call", "configure", "mutated-default"])
def test_session_factory_refuses_another_engine_before_acquisition(loader, tmp_path, method):
    other = create_engine("sqlite:///" + str(tmp_path / "other.sqlite"))
    Base.metadata.create_all(other)
    try:
        with pytest.raises(DomainOwnershipError):
            if method == "call":
                with loader.SessionLocal(bind=other):
                    pass
            elif method == "configure":
                loader.SessionLocal.configure(bind=other)
            else:
                loader.SessionLocal.kw["bind"] = other
                with loader.SessionLocal():
                    pass
        with other.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM seeding_domain_claims")) == 0
        assert counts(loader) == (0, 0)
    finally:
        other.dispose()


def test_same_engine_factory_override_remains_supported(loader):
    with loader.SessionLocal(bind=loader.engine) as session:
        session.execute(text("INSERT INTO inert_effects VALUES(1)"))
        session.commit()
    assert counts(loader) == (1, 0)


def test_in_memory_sqlite_retains_schema_across_owned_sessions():
    owned = DatabaseLoader("sqlite:///:memory:")
    try:
        Base.metadata.create_all(owned.engine)
        with owned.engine.begin() as conn:
            conn.execute(text("CREATE TABLE inert_effects(n integer)"))
        with owned.get_db_session() as session:
            session.execute(text("INSERT INTO inert_effects VALUES(1)"))
            session.commit()
        assert counts(owned) == (1, 0)
    finally:
        owned.engine.dispose()


def test_worker_child_failure_reaches_scheduler_without_launching_next_job(monkeypatch):
    from etl import worker
    from subprocess import CalledProcessError
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ETL_RUN_ON_START", "true")
    monkeypatch.setattr(DatabaseLoader, "check_ownership_ready", lambda self: None)
    monkeypatch.setattr(worker, "load_config", lambda path: {"countries": {"KE": {"sources": {"oag": {}, "treasury": {}}}}})
    connection = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(worker.psycopg2, "connect", lambda url: connection)
    monkeypatch.setattr(worker, "pg_advisory_lock", lambda conn: True)
    unlocked = []
    monkeypatch.setattr(worker, "pg_advisory_unlock", lambda conn: unlocked.append(True))
    calls = []
    def failed(env):
        calls.append(env["BACKFILL_SOURCES"])
        raise CalledProcessError(1, ["inert-backfill"])
    monkeypatch.setattr(worker, "run_once", failed)
    monkeypatch.setattr(worker.time, "sleep", lambda delay: (_ for _ in ()).throw(RuntimeError("Scheduler continued after child failure")))
    with pytest.raises(CalledProcessError):
        worker.schedule_worker()
    assert calls == ["oag"]
    assert unlocked == [True]


def test_closed_session_cannot_commit_another_effect(loader):
    session = loader.get_db_session()
    session.close()
    with pytest.raises(Exception):
        session.execute(text("INSERT INTO inert_effects VALUES(1)"))
    assert counts(loader) == (0, 0)


def test_keyboard_interrupt_after_commit_retains_without_return_receipt(loader):
    session = loader.get_db_session()
    session.execute(text("INSERT INTO inert_effects VALUES(1)"))
    session.commit()
    with pytest.raises(DomainOwnershipError):
        try:
            raise KeyboardInterrupt()
        finally:
            session.close()
    assert counts(loader) == (1, 13)
    with loader.engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM seeding_domain_claims WHERE returned_at IS NOT NULL")) == 0
    with pytest.raises(DomainOwnershipError):
        loader.get_db_session()


def test_plain_synchronous_failure_releases_after_all_work_returns(loader):
    with pytest.raises(ValueError):
        with writer_scope(loader.engine):
            raise ValueError("inert caller failure")
    assert counts(loader) == (0, 0)
    with loader.get_db_session():
        pass


def test_refusal_observation_failure_still_propagates_ownership_error(loader):
    ownership = enter_domain(sessionmaker(bind=loader.engine), "audits", False)
    ownership.close()
    def unavailable_observation(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO ingestion_jobs"):
            raise OperationalError("inert observation", {}, RuntimeError("inert unavailable storage"))
    event.listen(loader.engine, "before_cursor_execute", unavailable_observation)
    try:
        with pytest.raises(DomainOwnershipError):
            asyncio.run(loader.ensure_country_exists())
    finally:
        event.remove(loader.engine, "before_cursor_execute", unavailable_observation)
    assert counts(loader) == (0, 1)
    with loader.engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM countries")) == 0


def test_missing_unique_active_domain_index_refuses_at_startup_and_write(loader):
    ownership = enter_domain(sessionmaker(bind=loader.engine), "audits", False)
    ownership.close()
    with loader.engine.begin() as conn:
        conn.execute(text("DROP INDEX uq_seeding_active_domain"))
    with pytest.raises(DomainOwnershipError):
        loader.check_ownership_ready()
    with pytest.raises(DomainOwnershipError):
        loader.get_db_session()
    assert counts(loader) == (0, 1)


def test_missing_dispatch_seam_table_refuses_startup_and_write(loader):
    with loader.engine.begin() as conn:
        conn.execute(text("DROP TABLE etl_dispatch_domains"))
    with pytest.raises(DomainOwnershipError):
        loader.check_ownership_ready()
    with pytest.raises(DomainOwnershipError):
        loader.get_db_session()
    assert counts(loader) == (0, 0)


@pytest.mark.parametrize("domain", ["learning_hub", "imf_weo"])
def test_independent_domains_and_summary_remain_available(loader, domain):
    independent = enter_domain(sessionmaker(bind=loader.engine), domain, False)
    try:
        with loader.get_db_session() as session:
            session.execute(text("INSERT INTO inert_effects VALUES(1)"))
            session.commit()
        assert counts(loader) == (1, 1)
        summary = asyncio.run(loader.get_data_summary())
        assert summary["countries"] == summary["source_documents"] == 0
    finally:
        independent.close()


def test_unavailable_writer_refuses_pipeline_and_monitor(loader, tmp_path, monkeypatch):
    from etl.kenya_pipeline import KenyaDataPipeline, UnavailableDatabaseLoader
    from etl.monitored_runner import ETLMonitor
    pipe = KenyaDataPipeline.__new__(KenyaDataPipeline)
    pipe.storage_path = tmp_path
    pipe.kenya_sources = {}
    pipe.processed_manifest = {}
    pipe._ssl_verify_for = lambda *args: True
    pipe.http = SimpleNamespace(get=lambda *args, **kwargs: SimpleNamespace(content=b"%PDF-owned-refusal", headers={"content-type": "application/pdf"}, raise_for_status=lambda: None))
    pipe._maybe_upload_to_s3 = lambda *args: None
    pipe.extractor = SimpleNamespace(extract_with_fallback=lambda *args: {"confidence": 1.})
    pipe.audit_parser = SimpleNamespace(parse=lambda *args: [{"finding_text": "inert"}])
    pipe.data_validator = SimpleNamespace(validate_audit_data=lambda *args: SimpleNamespace(is_valid=True, confidence=1., warnings=[]))
    pipe.db_loader = UnavailableDatabaseLoader()
    pipe.scheduler = SimpleNamespace(get_schedule_summary=lambda: {"efficiency": {"skip_percentage": 0}}, should_run=lambda source: (source == "oag", "inert"), get_next_run=lambda source: ("none", "inert"))
    pipe.discover_budget_documents = lambda *args: [{"url": "https://fixture.invalid/owned.pdf", "source_key": "oag", "title": "Inert", "source": "Owned", "doc_type": "audit"}]
    monitor = ETLMonitor()
    # Alerts are isolated from optional provider/storage configuration.
    async def no_alert(*args):
        return None
    monkeypatch.setattr(monitor, "_send_failure_alert", no_alert)
    with pytest.raises(DomainOwnershipError):
        asyncio.run(monitor.run_with_monitoring(pipe.run_full_pipeline))
    assert monitor.success is False

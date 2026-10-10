"""Real CLI and dedicated worker with actual parser/writer on owned PostgreSQL."""
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import database
import supabase_auth
from routers import etl_admin
from seeding.domains.cra import writer, source
from seeding.types import DomainRunContext
from batch11_native_sources_fixture.owned_postgres import postgres, command_environment

BACKEND = Path(__file__).resolve().parents[1]
AUTH = {"Authorization": "Bearer batch11-admin"}


@pytest.fixture(scope="module")
def cra_url(tmp_path_factory):
    with postgres(tmp_path_factory.mktemp("issue602-resources")) as url:
        yield url


@pytest.fixture
def cra_pg(cra_url, monkeypatch):
    name = "batch11_602_" + uuid4().hex
    admin = create_engine(cra_url, isolation_level="AUTOCOMMIT")
    template = make_url(cra_url).database
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{template}"'))
    url = make_url(cra_url).set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url)
    factory = sessionmaker(bind=engine)
    with engine.begin() as c:
        c.execute(text("INSERT INTO countries(iso_code,name,currency,timezone,default_locale) VALUES ('KEN','Kenya','KES','Africa/Nairobi','en') ON CONFLICT (iso_code) DO NOTHING"))
        c.execute(text("CREATE TABLE batch11_control(mode text); INSERT INTO batch11_control VALUES ('normal'); CREATE TABLE batch11_markers(stage text,claim_id uuid,command_id uuid)"))
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_SOURCES", "cra")
    monkeypatch.setenv("SEED_CRA_INGESTION_ENABLED", "true")
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(supabase_auth, "_decode_supabase_jwt", lambda token: {"sub": token})
    monkeypatch.setattr(supabase_auth, "_fetch_roles", lambda uid: ("batch11@example.invalid", ["admin"] if uid == "batch11-admin" else ["user"]))
    app = FastAPI()
    app.include_router(etl_admin.router)
    try:
        with TestClient(app) as client:
            yield client, factory, engine, url
    finally:
        engine.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@contextmanager
def process(tmp_path, url, module, *args, enabled=True):
    env = command_environment(url)
    env.update({"PYTHONPATH": os.pathsep.join([str(BACKEND / "tests/batch11_native_sources_fixture"), str(BACKEND / "tests"), str(BACKEND)]),
        "BATCH11_NATIVE_FIXTURE": "true", "SEED_CRA_INGESTION_ENABLED": "true" if enabled else "false",
        "ADMIN_ETL_DISPATCH_ENABLED": "true", "ADMIN_ETL_DISPATCH_SOURCES": "cra",
        "SUPABASE_URL": "https://owned.invalid", "SUPABASE_KEY": "inert", "SUPABASE_JWT_SECRET": "inert-only",
        "SEED_STORAGE_PATH": str(tmp_path / "storage"), "SEED_CACHE_PATH": str(tmp_path / "cache"),
        "SEED_LOG_PATH": str(tmp_path / "seed.jsonl")})
    path = tmp_path / (module + "-" + uuid4().hex + ".log")
    with path.open("xb") as log:
        child = subprocess.Popen([sys.executable, "-m", module, *args], cwd=BACKEND, env=env,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            yield child, path
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGINT)
                try: child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
            assert child.poll() is not None


def wait_for(read, predicate):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        value = read()
        if predicate(value): return value
        time.sleep(.03)
    raise AssertionError("Owned process barrier/receipt not observed")


def query(engine, sql, params=None):
    with engine.connect() as c:
        return c.execute(text(sql), params or {}).mappings().all()


def post(client, generation, source_name="cra", dry_run=False, key=None):
    return client.post("/api/v1/admin/etl/trigger/" + source_name, headers={**AUTH, "Idempotency-Key": key or str(uuid4())},
                       json={"dispatch_generation": generation, "dry_run": dry_run})


def receipt(client, identity):
    return client.get("/api/v1/admin/etl/commands/" + identity, headers=AUTH).json()


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("mode", ["normal", "failure", "malformed"])
def test_actual_native_cli_normal_dry_run_and_failure(cra_pg, tmp_path, dry_run, mode):
    _, _, engine, url = cra_pg
    with engine.begin() as c: c.execute(text("UPDATE batch11_control SET mode=:m"), {"m": mode})
    with process(tmp_path, url, "seeding.cli", "seed", "--domain", "cra", "--dry-run" if dry_run else "--no-dry-run") as (child, log):
        assert child.wait(timeout=20) == (0 if mode == "normal" else 1), log.read_text()
    jobs = query(engine, "SELECT status::text,dry_run,items_processed,metadata,errors FROM ingestion_jobs")
    assert len(jobs) == 1 and jobs[0]["dry_run"] is dry_run
    assert jobs[0]["status"] == ("COMPLETED" if mode == "normal" else "FAILED")
    if mode == "failure": assert "Owned source input unavailable" in log.read_text()
    if mode == "malformed": assert "CRA complete bounded PDF bytes required" in log.read_text()
    claims = query(engine, "SELECT id,entered_at,returned_at,released_at FROM seeding_domain_claims")
    assert len(claims) == 1 and claims[0]["entered_at"] and claims[0]["returned_at"] and claims[0]["released_at"]
    assert jobs[0]["metadata"]["seeding_claim_id"] == str(claims[0]["id"])
    assert query(engine, "SELECT claim_id FROM batch11_markers")[0]["claim_id"] == claims[0]["id"]
    docs = query(engine, "SELECT * FROM source_documents WHERE publisher='Commission on Revenue Allocation'")
    extractions = query(engine, "SELECT extracted_json,page_number FROM extractions")
    assert len(docs) == len(extractions) == (1 if mode == "normal" and not dry_run else 0)
    if docs:
        assert docs[0]["metadata"]["publication_stage"] == "recommendation" and docs[0]["url"] == source.URL
        assert extractions[0]["page_number"] == 39 and extractions[0]["extracted_json"]["artifact_sha256"] == "38189f669f7014cfd11d0cc7d7215332667772b5cc32a7ccb083ad9976b8498a"
    for table in ("budget_lines", "economic_indicators", "admin_audit_log"):
        assert not query(engine, "SELECT 1 FROM " + table)


def test_replay_is_source_bound_and_does_not_duplicate_observations(cra_pg, tmp_path):
    _, _, engine, url = cra_pg
    for _ in range(2):
        with process(tmp_path, url, "seeding.cli", "seed", "--domain", "cra", "--no-dry-run") as (child, log):
            assert child.wait(timeout=20) == 0, log.read_text()
    assert len(query(engine, "SELECT 1 FROM extractions")) == 1
    assert len(query(engine, "SELECT 1 FROM source_documents WHERE publisher='Commission on Revenue Allocation'")) == 1
    assert [r["items_created"] for r in query(engine, "SELECT items_created FROM ingestion_jobs ORDER BY id")] == [1, 0]


def test_direct_writer_without_durable_owner_refuses(cra_pg):
    _, factory, engine, _ = cra_pg
    with factory() as db:
        with pytest.raises(source.CraSourceRefused, match="owned native ingestion observation"):
            writer.require_ownership(db, DomainRunContext(since=None, dry_run=False))
    assert not query(engine, "SELECT 1 FROM source_documents WHERE publisher='Commission on Revenue Allocation'")


@pytest.mark.parametrize("mutation", ["duplicate", "tampered_provenance"])
def test_replay_refuses_ambiguous_or_changed_source_document(cra_pg, tmp_path, mutation):
    _, factory, engine, url = cra_pg
    with process(tmp_path, url, "seeding.cli", "seed", "--domain", "cra", "--no-dry-run") as (child, log):
        assert child.wait(timeout=20) == 0, log.read_text()
    if mutation == "duplicate":
        from models import SourceDocument
        with factory() as db:
            original = db.query(SourceDocument).filter_by(publisher="Commission on Revenue Allocation").one()
            values = {column.key: getattr(original, column.key) for column in SourceDocument.__mapper__.column_attrs if column.key != "id"}
            db.add(SourceDocument(**values))
            db.commit()
    else:
        with engine.begin() as c:
            c.execute(text("UPDATE source_documents SET md5='00000000000000000000000000000000' WHERE publisher='Commission on Revenue Allocation'"))
    before = query(engine, "SELECT id,md5,metadata FROM source_documents ORDER BY id")
    with process(tmp_path, url, "seeding.cli", "seed", "--domain", "cra", "--no-dry-run") as (child, log):
        assert child.wait(timeout=20) == 1 and "CRA existing source document" in log.read_text(), log.read_text()
    assert query(engine, "SELECT id,md5,metadata FROM source_documents ORDER BY id") == before
    assert len(query(engine, "SELECT 1 FROM extractions")) == 1
    assert query(engine, "SELECT status::text FROM ingestion_jobs ORDER BY id DESC LIMIT 1")[0]["status"] == "FAILED"


@pytest.mark.parametrize("name", ["opendata", "unknown", "cra:unregistered"])
def test_unknown_or_unavailable_native_inputs_have_zero_effects(cra_pg, tmp_path, name):
    _, _, engine, url = cra_pg
    with process(tmp_path, url, "seeding.cli", "seed", "--domain", name, "--dry-run") as (child, log):
        assert child.wait(timeout=20) == 1 and "Unknown domain(s) requested: " + name in log.read_text()
    for table in ("ingestion_jobs", "seeding_domain_claims", "batch11_markers", "admin_audit_log", "extractions"):
        assert not query(engine, "SELECT 1 FROM " + table)


@pytest.mark.parametrize("dry_run", [False, True])
def test_api_dedicated_worker_correlates_real_source_terminal_job(cra_pg, tmp_path, dry_run):
    client, _, engine, url = cra_pg
    with process(tmp_path, url, "admin_etl_dispatch_worker"):
        cap = wait_for(lambda: client.get("/api/v1/admin/etl/dispatch", headers=AUTH).json(), lambda v: v["available"])
        assert cap["sources"]["cra"]["available"] is True and cap["sources"]["opendata"]["available"] is False
        key = str(uuid4())
        accepted = post(client, cap["generation"], dry_run=dry_run, key=key)
        assert accepted.status_code == 202, accepted.text
        identity = accepted.json()["command"]["id"]
        final = wait_for(lambda: receipt(client, identity), lambda v: v["status"] == "completed")
        assert post(client, cap["generation"], dry_run=dry_run, key=key).json()["replayed"] is True
        assert post(client, cap["generation"], dry_run=not dry_run, key=key).status_code == 409
        assert post(client, cap["generation"], source_name="opendata").status_code == 503
        assert post(client, cap["generation"], source_name="unknown").status_code == 404
        rows = query(engine, "SELECT j.domain,j.status::text,j.dry_run,j.metadata,c.id,c.released_at FROM ingestion_jobs j JOIN seeding_domain_claims c ON c.id::text=j.metadata->>'seeding_claim_id' WHERE j.id=:id", {"id": final["job_id"]})
        assert len(rows) == 1 and rows[0]["domain"] == "cra" and rows[0]["status"] == "COMPLETED" and rows[0]["dry_run"] is dry_run
        assert rows[0]["metadata"]["dispatch_command_id"] == identity
        assert rows[0]["metadata"]["dispatch_claim_token"] == str(rows[0]["id"]) and rows[0]["released_at"]
        assert len(query(engine, "SELECT 1 FROM admin_audit_log")) == 1
        assert len(query(engine, "SELECT 1 FROM extractions")) == (0 if dry_run else 1)


def test_worker_input_failure_is_failed_with_exact_job_not_completed(cra_pg, tmp_path):
    client, _, engine, url = cra_pg
    with engine.begin() as c: c.execute(text("UPDATE batch11_control SET mode='failure'"))
    with process(tmp_path, url, "admin_etl_dispatch_worker"):
        cap = wait_for(lambda: client.get("/api/v1/admin/etl/dispatch", headers=AUTH).json(), lambda v: v["available"])
        accepted = post(client, cap["generation"])
        final = wait_for(lambda: receipt(client, accepted.json()["command"]["id"]), lambda v: v["status"] == "failed")
        assert final["job_id"] and final["outcome"] == "failed"
        assert query(engine, "SELECT status::text FROM ingestion_jobs")[0]["status"] == "FAILED"
        assert not query(engine, "SELECT 1 FROM extractions")


@pytest.mark.parametrize("phase,effects", [("before", 0), ("after", 1)])
def test_process_death_retains_cra_owner_and_native_successor_refuses(cra_pg, tmp_path, phase, effects):
    client, _, engine, url = cra_pg
    with engine.begin() as c: c.execute(text("UPDATE batch11_control SET mode=:m"), {"m": phase})
    with process(tmp_path, url, "admin_etl_dispatch_worker") as (worker, _):
        cap = wait_for(lambda: client.get("/api/v1/admin/etl/dispatch", headers=AUTH).json(), lambda v: v["available"])
        accepted = post(client, cap["generation"])
        identity = accepted.json()["command"]["id"]
        wait_for(lambda: query(engine, "SELECT 1 FROM batch11_markers WHERE stage=:s", {"s": phase}), bool)
        os.killpg(worker.pid, signal.SIGKILL)
        worker.wait(timeout=5)
    with engine.begin() as c:
        c.execute(text("UPDATE etl_dispatch_worker SET last_seen_at=clock_timestamp()-interval '2 seconds',expires_at=clock_timestamp()-interval '1 second'"))
        c.execute(text("UPDATE batch11_control SET mode='normal'"))
    assert receipt(client, identity)["status"] == "interrupted"
    with process(tmp_path, url, "seeding.cli", "seed", "--domain", "cra", "--no-dry-run") as (child, log):
        assert child.wait(timeout=20) == 1 and "Domain ownership unavailable; no handler started" in log.read_text()
    assert len(query(engine, "SELECT 1 FROM extractions")) == effects
    assert len(query(engine, "SELECT 1 FROM seeding_domain_claims WHERE released_at IS NULL AND domain='cra'")) == 1
    with process(tmp_path, url, "admin_etl_dispatch_worker"):
        new = wait_for(lambda: client.get("/api/v1/admin/etl/dispatch", headers=AUTH).json(), lambda v: v["available"] and v["generation"] != cap["generation"])
        queued = post(client, new["generation"]).json()["command"]["id"]
        assert receipt(client, queued)["status"] == "queued"
        assert len(query(engine, "SELECT 1 FROM seeding_domain_claims WHERE released_at IS NULL")) == 1


def test_default_off_worker_capability_refuses_cra_without_success_audit(cra_pg, monkeypatch):
    from admin_etl_dispatch_worker import register_worker
    client, _, engine, _ = cra_pg
    monkeypatch.setenv("SEED_CRA_INGESTION_ENABLED", "false")
    generation = register_worker(cra_pg[1])
    cap = client.get("/api/v1/admin/etl/dispatch", headers=AUTH).json()
    assert cap["available"] is False and cap["sources"]["cra"]["available"] is False
    assert post(client, str(generation)).status_code == 503
    assert not query(engine, "SELECT 1 FROM admin_audit_log")


def test_real_http_api_and_dedicated_process(cra_pg, tmp_path):
    import httpx
    _, _, engine, url = cra_pg
    port = int(os.environ.get("BATCH11_602_API_PORT", "18031"))
    assert port not in (18030, 18032, 18033, 18034, 13032, 13033, 13034, 55530, 55532, 55534)
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))
    with process(tmp_path, url, "uvicorn", "batch11_native_sources_fixture.api:app", "--host", "127.0.0.1", "--port", str(port)), process(tmp_path, url, "admin_etl_dispatch_worker"):
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, headers=AUTH) as client:
            def capability():
                try: return client.get("/api/v1/admin/etl/dispatch").json()
                except httpx.ConnectError: return {}
            cap = wait_for(capability, lambda v: v.get("available") is True)
            accepted = post(client, cap["generation"])
            assert accepted.status_code == 202, accepted.text
            final = wait_for(lambda: receipt(client, accepted.json()["command"]["id"]), lambda v: v["status"] == "completed")
            assert final["job_id"] and accepted.json()["audit_recorded"] is True
            assert len(query(engine, "SELECT 1 FROM extractions")) == 1


def test_flag_disabled_handler_gate_refuses_before_transport_with_zero_source_effects(cra_pg, tmp_path):
    # The owned fixture imports seeding.domains.cra to replace its transport, which
    # registers the handler in this child; the registry gate itself is proven in a
    # clean process below. Here the handler's own gate must refuse before transport.
    _, _, engine, url = cra_pg
    with process(tmp_path, url, "seeding.cli", "seed", "--domain", "cra", "--no-dry-run", enabled=False) as (child, log):
        assert child.wait(timeout=20) == 1 and "CRA ingestion is disabled" in log.read_text()
    for table in ("batch11_markers", "admin_audit_log", "extractions", "source_documents"):
        assert not query(engine, "SELECT 1 FROM " + table)
    assert [r["status"] for r in query(engine, "SELECT status::text FROM ingestion_jobs")] == ["FAILED"]
    assert not query(engine, "SELECT 1 FROM seeding_domain_claims WHERE released_at IS NULL")


@pytest.mark.parametrize("flag,expected", [("false", "False"), ("true", "True")])
def test_builtin_loader_imports_cra_only_when_explicitly_enabled(flag, expected):
    # A fresh process: importing seeding.domains.cra anywhere registers it, so the
    # loader's own decision is only observable before anything else imports it.
    env = command_environment()
    env.update({"PYTHONPATH": str(BACKEND), "SEED_CRA_INGESTION_ENABLED": flag})
    code = "from seeding.registries import REGISTRY, load_builtin_domains; load_builtin_domains(); print(REGISTRY.has('cra'))"
    result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0 and result.stdout.strip().splitlines()[-1] == expected, result.stderr


@pytest.mark.parametrize("flag", ["1", "yes", "TRUE", ""])
def test_malformed_flag_refuses_loader_instead_of_guessing(flag):
    env = command_environment()
    env.update({"PYTHONPATH": str(BACKEND), "SEED_CRA_INGESTION_ENABLED": flag})
    code = "from seeding.registries import load_builtin_domains; load_builtin_domains()"
    result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, text=True, capture_output=True, timeout=60)
    assert result.returncode != 0 and "CRA opt-in requires true or false" in result.stderr


@pytest.mark.parametrize("flag", ["1", "TRUE"])
def test_worker_readiness_names_an_invalid_cra_flag_instead_of_an_import_failure(monkeypatch, caplog, flag):
    from admin_etl_dispatch_adapter import ready_domains
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_SOURCES", "cra")
    monkeypatch.setenv("SEED_CRA_INGESTION_ENABLED", flag)
    with caplog.at_level("WARNING"):
        assert "cra" not in ready_domains()
    assert "dispatch_cra_flag_invalid" in caplog.text and "dispatch_domain_import_unavailable" not in caplog.text

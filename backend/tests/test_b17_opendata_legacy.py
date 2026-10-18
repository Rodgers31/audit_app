"""Every-writer coverage for OpenData: the real legacy loader against the real OpenData CLI.

Both writers run as separate OS processes on owned PostgreSQL: the legacy
loader through ``batch11_native_sources_fixture/legacy_entry.py`` (real
``etl.writer_ownership`` acquisition) and the native OpenData handler through
``python -m seeding.cli`` with the reviewed workbook bytes as its only input.
"""
import os
import signal
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import text

from batch11_native_sources_fixture.owned_postgres import command_environment
from test_b17_opendata_native import BACKEND, opendata_pg, opendata_url, process, query, wait_for  # noqa: F401

LEGACY_ENTRY = BACKEND / "tests/batch11_native_sources_fixture/legacy_entry.py"
ROOT = BACKEND.parent


def legacy_domains():
    # Read the enrolled set from the real module source without importing the
    # root legacy package into this backend-cohort test process.
    import ast
    tree = ast.parse((ROOT / "etl/writer_ownership.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "LEGACY_DOMAINS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("LEGACY_DOMAINS not found")


@pytest.fixture
def legacy_db(opendata_pg):
    client, factory, engine, url = opendata_pg
    with engine.begin() as c:
        c.execute(text("CREATE TABLE batch11_legacy_control(mode text); INSERT INTO batch11_legacy_control VALUES ('normal')"))
    return engine, url


def legacy(tmp_path, url):
    env = command_environment(url)
    log = tmp_path / ("legacy-" + uuid4().hex + ".log")
    handle = log.open("xb")
    child = subprocess.Popen([sys.executable, *(["-O"] if sys.flags.optimize else []), str(LEGACY_ENTRY)], cwd=BACKEND, env=env,
                             stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
    child._log, child._handle = log, handle
    return child


def stop(child):
    if child.poll() is None:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=5)
    child._handle.close()


def finish(child, timeout=30):
    try:
        return child.wait(timeout=timeout)
    finally:
        stop(child)


def set_mode(engine, table, value):
    with engine.begin() as c:
        c.execute(text(f"UPDATE {table} SET mode=:m"), {"m": value})


def legacy_effects(engine):
    return query(engine, "SELECT count(*) AS n FROM countries WHERE iso_code='ZZB'")[0]["n"]


def opendata_effects(engine):
    return (query(engine, "SELECT count(*) AS n FROM extractions")[0]["n"],
            query(engine, "SELECT count(*) AS n FROM source_documents WHERE publisher='Kenya National Bureau of Statistics'")[0]["n"])


def test_opendata_is_enrolled_in_the_legacy_claim_set():
    domains = legacy_domains()
    assert "opendata" in domains and list(domains) == sorted(domains) and len(domains) == len(set(domains)) == 15


@pytest.mark.parametrize("bounded", [False, True], ids=["default-pool", "pool-two-no-overflow"])
def test_all_legacy_domains_share_one_lock_backend(legacy_db, bounded):
    import importlib.util
    from sqlalchemy import create_engine, event
    engine, url = legacy_db
    spec = importlib.util.spec_from_file_location("b17_legacy_pool_probe", ROOT / "etl/writer_ownership.py")
    ownership = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ownership)
    probe = create_engine(url, pool_timeout=.1, **({"pool_size": 2, "max_overflow": 0} if bounded else {}))
    held = set()
    peak = [0]
    @event.listens_for(probe, "checkout")
    def checkout(connection, record, proxy):
        held.add(id(connection))
        peak[0] = max(peak[0], len(held))
    @event.listens_for(probe, "checkin")
    def checkin(connection, record):
        held.discard(id(connection))
    try:
        with ownership.writer_scope(probe) as scope:
            assert len(scope.executions) == 15
            assert len({e.pid for e in scope.executions}) == 1
            assert all(e.connection is scope.guard.connection and e.continuous() for e in scope.executions)
            with pytest.raises(ownership.DomainOwnershipError, match="complete scope receipt"):
                scope.executions[-1].acknowledge(scope.jobs[scope.executions[-1].domain])
            assert query(engine, "SELECT count(*) AS n FROM seeding_domain_claims WHERE released_at IS NULL")[0]["n"] == 15
        assert peak[0] <= 2 and not held
        assert query(engine, "SELECT count(*) AS n FROM seeding_domain_claims WHERE released_at IS NULL")[0]["n"] == 0
    finally:
        probe.dispose()


def test_legacy_claims_opendata_before_effects_and_blocks_native_opendata_then_next_run(legacy_db, tmp_path):
    engine, url = legacy_db
    set_mode(engine, "batch11_legacy_control", "before")
    child = legacy(tmp_path, url)
    try:
        wait_for(lambda: query(engine, "SELECT 1 FROM batch11_markers WHERE stage='legacy_entered'"), bool)
        held = query(engine, "SELECT c.domain,c.kind,j.status::text AS status,j.metadata->>'writer' AS writer FROM seeding_domain_claims c "
                             "JOIN ingestion_jobs j ON j.metadata->>'seeding_claim_id'=c.id::text WHERE c.released_at IS NULL ORDER BY c.domain")
        # Every enrolled domain, OpenData included, is owned before the loader's commit.
        assert [r["domain"] for r in held] == sorted(legacy_domains())
        assert all(r["kind"] == "native" and r["status"] == "RUNNING" and r["writer"] == "legacy_etl" for r in held)
        assert legacy_effects(engine) == 0
        with process(tmp_path, url, "seeding.cli", "seed", "--domain", "opendata", "--no-dry-run") as (native, log):
            assert native.wait(timeout=20) == 1 and "Domain ownership unavailable; no handler started" in log.read_text()
        # Refused before its handler: no transport marker, no OpenData observation.
        assert opendata_effects(engine) == (0, 0)
        assert not query(engine, "SELECT 1 FROM batch11_markers WHERE stage='before'")
        set_mode(engine, "batch11_legacy_control", "normal")
        assert finish(child) == 0, child._log.read_text()
    finally:
        stop(child)
    assert legacy_effects(engine) == 1
    assert not query(engine, "SELECT 1 FROM seeding_domain_claims WHERE released_at IS NULL")
    # Normal synchronous completion released every claim: the next run proceeds.
    with process(tmp_path, url, "seeding.cli", "seed", "--domain", "opendata", "--no-dry-run") as (native, log):
        assert native.wait(timeout=20) == 0, log.read_text()
    assert opendata_effects(engine) == (1, 1)


def test_native_opendata_owner_refuses_the_real_legacy_loader_then_both_complete(legacy_db, tmp_path):
    engine, url = legacy_db
    with engine.begin() as c:
        c.execute(text("UPDATE batch11_control SET mode='before'"))
    with process(tmp_path, url, "seeding.cli", "seed", "--domain", "opendata", "--no-dry-run") as (native, log):
        wait_for(lambda: query(engine, "SELECT 1 FROM batch11_markers WHERE stage='before'"), bool)
        child = legacy(tmp_path, url)
        assert finish(child) != 0
        assert "Legacy writer ownership refused" in child._log.read_text() or "Domain ownership unavailable" in child._log.read_text(), child._log.read_text()
        assert legacy_effects(engine) == 0 and opendata_effects(engine) == (0, 0)
        # The refused legacy scope released only its own partial acquisitions.
        retained = query(engine, "SELECT domain,kind FROM seeding_domain_claims WHERE released_at IS NULL")
        assert retained == [{"domain": "opendata", "kind": "native"}]
        with engine.begin() as c:
            c.execute(text("UPDATE batch11_control SET mode='normal'"))
        assert native.wait(timeout=20) == 0, log.read_text()
    assert opendata_effects(engine) == (1, 1)
    child = legacy(tmp_path, url)
    assert finish(child) == 0, child._log.read_text()
    assert legacy_effects(engine) == 1
    assert not query(engine, "SELECT 1 FROM seeding_domain_claims WHERE released_at IS NULL")


def test_retained_uncertain_opendata_claim_prevents_legacy_effects(legacy_db, tmp_path):
    engine, url = legacy_db
    with engine.begin() as c:
        c.execute(text("UPDATE batch11_control SET mode='before'"))
    with process(tmp_path, url, "seeding.cli", "seed", "--domain", "opendata", "--no-dry-run") as (native, _):
        wait_for(lambda: query(engine, "SELECT 1 FROM batch11_markers WHERE stage='before'"), bool)
        os.killpg(native.pid, signal.SIGKILL)
        native.wait(timeout=5)
    with engine.begin() as c:
        c.execute(text("UPDATE batch11_control SET mode='normal'"))
    claim = query(engine, "SELECT id FROM seeding_domain_claims WHERE released_at IS NULL")
    assert len(claim) == 1
    child = legacy(tmp_path, url)
    assert finish(child) != 0
    assert legacy_effects(engine) == 0 and opendata_effects(engine) == (0, 0)
    # Never auto-expired or auto-released by the refused successor.
    assert query(engine, "SELECT id FROM seeding_domain_claims WHERE released_at IS NULL AND domain='opendata'") == claim

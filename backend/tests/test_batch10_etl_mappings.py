"""Actual admin acceptance/worker/adapter/native CLI with owned inert effects."""
import os
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import database
import supabase_auth
from admin_etl_dispatch_worker import claim, finish, register_worker
from admin_etl_dispatch_adapter import execute
from models import EtlDispatchCommand, EtlDispatchDomain, SeedingDomainClaim, IngestionStatus
from routers import etl_admin
from seeding.registries import REGISTRY, load_builtin_domains
from seeding.types import DomainRunResult

MAPPINGS = {"oag": "audits", "treasury": "fiscal_summary", "cob": "counties_budget", "knbs": "population"}
AUTH = {"Authorization": "Bearer batch10-admin"}


@pytest.fixture(scope="module")
def mapping_url(tmp_path_factory):
    from batch10_etl_mappings_fixture.owned_postgres import postgres
    with postgres(tmp_path_factory.mktemp("batch10-mappings-resources")) as url:
        yield url


@pytest.fixture
def pg(monkeypatch, mapping_url):
    url = mapping_url
    engine = create_engine(url)
    factory = sessionmaker(bind=engine)
    with engine.begin() as c:
        c.execute(text("TRUNCATE seeding_domain_claims, etl_dispatch_domains, etl_dispatch_commands, etl_dispatch_worker, admin_audit_log, ingestion_jobs RESTART IDENTITY CASCADE"))
        c.execute(text("CREATE TABLE IF NOT EXISTS batch10_effects(domain text, job_id integer)"))
        c.execute(text("TRUNCATE batch10_effects"))
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_SOURCES", ",".join(MAPPINGS))
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(supabase_auth, "_decode_supabase_jwt", lambda token: {"sub": token})
    monkeypatch.setattr(supabase_auth, "_fetch_roles", lambda uid: ("batch10@example.invalid", ["admin"] if uid == "batch10-admin" else ["user"]))
    load_builtin_domains()
    def handler(domain):
        def run(session, settings, context):
            session.execute(text("INSERT INTO batch10_effects VALUES (:domain,:job)"), {"domain": domain, "job": context.job_id})
            return DomainRunResult(domain=domain, dry_run=context.dry_run, items_processed=1, items_created=1)
        return run
    monkeypatch.setattr(REGISTRY, "_handlers", {d: handler(d) for d in MAPPINGS.values()})
    app = FastAPI()
    app.include_router(etl_admin.router)
    try:
        with TestClient(app) as client:
            yield client, factory, engine
    finally:
        engine.dispose()


def post(client, generation, source, dry_run=False, key=None):
    return client.post("/api/v1/admin/etl/trigger/" + source,
        headers={**AUTH, "Idempotency-Key": str(key or uuid4())},
        json={"dry_run": dry_run, "dispatch_generation": str(generation)})


@pytest.mark.parametrize("source,domain", MAPPINGS.items())
@pytest.mark.parametrize("dry_run", [False, True])
def test_mapping_runs_real_cli_and_correlates_terminal_receipt(pg, source, domain, dry_run):
    client, factory, engine = pg
    generation = register_worker(factory)
    accepted = post(client, generation, source, dry_run)
    assert accepted.status_code == 202, accepted.text
    command_id = UUID(accepted.json()["command"]["id"])
    owned = claim(factory, generation)
    assert owned and owned[0] == command_id
    with factory() as db:
        assert db.get(EtlDispatchDomain, domain).command_id == command_id
        assert db.get(SeedingDomainClaim, owned[1]).domain == domain
    assert execute(factory, engine, *owned, generation) == 0
    assert execute(factory, engine, *owned, generation) == 1
    assert finish(factory, generation, *owned, 0) is True
    final = client.get("/api/v1/admin/etl/commands/" + str(command_id), headers=AUTH)
    assert final.status_code == 200 and final.json()["status"] == "completed", final.text
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM batch10_effects")) == (0 if dry_run else 1)
        job = c.execute(text("SELECT domain,dry_run,metadata->>'dispatch_command_id',metadata->>'dispatch_claim_token' FROM ingestion_jobs WHERE id=:id"), {"id": final.json()["job_id"]}).one()
        assert tuple(job) == (domain, dry_run, str(command_id), str(owned[1]))
        assert c.scalar(text("SELECT count(*) FROM admin_audit_log")) == 1
    with factory() as db:
        assert db.get(SeedingDomainClaim, owned[1]).released_at is not None
    successor = post(client, generation, source)
    assert str(claim(factory, generation)[0]) == successor.json()["command"]["id"]


def test_capabilities_match_each_registered_handler(pg, monkeypatch):
    client, factory, _ = pg
    monkeypatch.delitem(REGISTRY._handlers, "population")
    generation = register_worker(factory)
    response = client.get("/api/v1/admin/etl/dispatch", headers=AUTH)
    capabilities = response.json()["sources"]
    assert {s for s,c in capabilities.items() if c["available"]} == {"oag", "treasury", "cob"}
    for source in ("knbs", "opendata", "cra"):
        assert post(client, generation, source).status_code == 503
        assert capabilities[source]["reason"]
    assert post(client, generation, "unknown").status_code == 404
    with factory() as db:
        assert db.query(EtlDispatchCommand).count() == 0
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"


def test_independent_domains_progress_around_retained_owner(pg):
    client, factory, engine = pg
    generation = register_worker(factory)
    first = post(client, generation, "treasury")
    first_owned = claim(factory, generation)
    second = post(client, generation, "treasury")
    third = post(client, generation, "knbs")
    third_owned = claim(factory, generation)
    assert str(third_owned[0]) == third.json()["command"]["id"]
    assert execute(factory, engine, *third_owned, generation) == 0
    assert finish(factory, generation, *third_owned, 0) is True
    with factory() as db:
        assert db.get(EtlDispatchDomain, "fiscal_summary").command_id == first_owned[0]
        assert db.get(SeedingDomainClaim, first_owned[1]).released_at is None
        assert db.get(EtlDispatchCommand, UUID(second.json()["command"]["id"])).status == "queued"
    assert claim(factory, generation) is None
    assert execute(factory, engine, *first_owned, generation) == 0
    assert finish(factory, generation, *first_owned, 0) is True
    assert str(claim(factory, generation)[0]) == second.json()["command"]["id"]


@pytest.mark.parametrize("source", MAPPINGS)
@pytest.mark.parametrize("mutation", ["token", "generation", "command", "domain", "missing_owner", "missing_domain", "job", "job_claim"])
def test_wrong_claim_or_job_retains_exact_owner_without_success(pg, source, mutation):
    client, factory, engine = pg
    generation = register_worker(factory)
    accepted = post(client, generation, source)
    owned = claim(factory, generation)
    if mutation == "token":
        assert execute(factory, engine, owned[0], uuid4(), generation) == 1
        assert finish(factory, generation, owned[0], uuid4(), 0) is False
    elif mutation == "generation":
        assert execute(factory, engine, *owned, uuid4()) == 1
        assert finish(factory, uuid4(), *owned, 0) is False
    elif mutation == "command":
        assert execute(factory, engine, uuid4(), owned[1], generation) == 1
        assert finish(factory, generation, uuid4(), owned[1], 0) is False
    else:
        if mutation in ("job", "job_claim"):
            assert execute(factory, engine, *owned, generation) == 0
        with engine.begin() as c:
            if mutation == "domain":
                c.execute(text("UPDATE seeding_domain_claims SET domain='unrelated' WHERE id=:id"), {"id": owned[1]})
            elif mutation == "missing_owner":
                c.execute(text("DELETE FROM seeding_domain_claims WHERE id=:id"), {"id": owned[1]})
            elif mutation == "missing_domain":
                c.execute(text("DELETE FROM etl_dispatch_domains WHERE domain=:d"), {"d": MAPPINGS[source]})
            elif mutation == "job_claim":
                c.execute(text("UPDATE ingestion_jobs SET metadata=jsonb_set(metadata,'{seeding_claim_id}',to_jsonb(CAST(:claim AS text))) WHERE metadata->>'dispatch_command_id'=:id"), {"claim": str(uuid4()), "id": str(owned[0])})
            else:
                c.execute(text("UPDATE ingestion_jobs SET domain='unrelated' WHERE metadata->>'dispatch_command_id'=:id"), {"id": str(owned[0])})
        if mutation not in ("job", "job_claim"):
            assert execute(factory, engine, *owned, generation) == 1
        assert finish(factory, generation, *owned, 0) is False
    with factory() as db:
        assert db.get(EtlDispatchCommand, owned[0]).status != "completed"
        row = db.get(EtlDispatchDomain, MAPPINGS[source])
        assert (row is None if mutation == "missing_domain" else row.command_id == owned[0])
        ownership = db.get(SeedingDomainClaim, owned[1])
        assert ownership is None or ownership.released_at is None
    assert claim(factory, generation) is None


@pytest.mark.parametrize("unrelated", ["audits", "population", "national_debt", "economic_indicators"])
def test_healthy_mapping_runs_real_cli_despite_unrelated_import_failure(pg, monkeypatch, unrelated):
    import importlib
    client, factory, engine = pg
    real_import = importlib.import_module
    def bounded_failure(name, package=None):
        if name == "seeding.domains." + unrelated:
            raise RuntimeError("inert unrelated import failure")
        return real_import(name, package)
    monkeypatch.setattr(importlib, "import_module", bounded_failure)
    generation = register_worker(factory)
    capabilities = client.get("/api/v1/admin/etl/dispatch", headers=AUTH).json()["sources"]
    assert capabilities["treasury"]["available"] is True
    assert post(client, generation, "treasury").status_code == 202
    owned = claim(factory, generation)
    assert execute(factory, engine, *owned, generation) == 0
    assert finish(factory, generation, *owned, 0) is True
    with factory() as db:
        assert db.get(EtlDispatchCommand, owned[0]).status == "completed"
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM batch10_effects WHERE domain='fiscal_summary'")) == 1


@pytest.mark.parametrize("failure", [ImportError, RuntimeError])
def test_cold_shared_cli_prerequisite_failure_refuses_all_acceptance(pg, monkeypatch, failure):
    import importlib.abc
    import sys
    client, factory, engine = pg
    for name in tuple(sys.modules):
        if name == "seeding.domains.audits" or name.startswith("seeding.domains.audits."):
            monkeypatch.delitem(sys.modules, name)
    class BrokenCore(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == "seeding.domains.audits" or fullname.startswith("seeding.domains.audits."):
                raise failure("inert private core import failure")
    monkeypatch.setattr(sys, "meta_path", [BrokenCore(), *sys.meta_path])
    generation = register_worker(factory)
    capability = client.get("/api/v1/admin/etl/dispatch", headers=AUTH).json()
    assert capability["available"] is False
    assert all(s["available"] is False for s in capability["sources"].values())
    for source in MAPPINGS:
        refused = post(client, generation, source)
        assert refused.status_code == 503 and "inert private" not in refused.text
    assert claim(factory, generation) is None
    with engine.connect() as c:
        for table in ("etl_dispatch_commands", "admin_audit_log", "ingestion_jobs", "batch10_effects"):
            assert c.scalar(text("SELECT count(*) FROM " + table)) == 0


@pytest.mark.parametrize("source", MAPPINGS)
@pytest.mark.parametrize("status", [IngestionStatus.COMPLETED, IngestionStatus.FAILED, IngestionStatus.COMPLETED_WITH_ERRORS])
@pytest.mark.parametrize("tag", ["absent", "null", "empty", "wrong"])
def test_claim_tag_boundary_preserves_only_accepted_oag_failed_receipts(pg, source, status, tag):
    client, factory, engine = pg
    generation = register_worker(factory)
    assert post(client, generation, source).status_code == 202
    owned = claim(factory, generation)
    assert execute(factory, engine, *owned, generation) == 0
    with factory.begin() as db:
        from models import IngestionJob
        job = db.query(IngestionJob).one()
        job.status = status
        metadata = dict(job.meta)
        if tag == "absent":
            metadata.pop("seeding_claim_id")
        else:
            metadata["seeding_claim_id"] = {"null": None, "empty": "", "wrong": str(uuid4())}[tag]
        job.meta = metadata
    compatible = source == "oag" and tag == "absent" and status != IngestionStatus.COMPLETED
    assert finish(factory, generation, *owned, 0) is compatible
    with factory() as db:
        command = db.get(EtlDispatchCommand, owned[0])
        assert command.status == ("failed" if compatible else "interrupted")
        owner = db.get(SeedingDomainClaim, owned[1])
        assert (owner.released_at is not None) is compatible
        assert (db.get(EtlDispatchDomain, MAPPINGS[source]).command_id is None) is compatible


@pytest.mark.parametrize("source", MAPPINGS)
def test_native_admission_honors_retained_dispatch_row_without_shared_claim(pg, source):
    from seeding.exclusion import enter_domain, DomainOwnershipError
    client, factory, engine = pg
    generation = register_worker(factory)
    post(client, generation, source)
    owned = claim(factory, generation)
    with engine.begin() as c:
        c.execute(text("DELETE FROM seeding_domain_claims WHERE id=:id"), {"id": owned[1]})
    with pytest.raises(DomainOwnershipError, match="ownership unavailable"):
        enter_domain(factory, MAPPINGS[source], False)
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM batch10_effects")) == 0


def test_default_source_selection_and_invalid_shapes(pg, monkeypatch):
    from admin_etl_dispatch import selected_sources
    client, factory, _ = pg
    monkeypatch.delenv("ADMIN_ETL_DISPATCH_SOURCES")
    assert selected_sources() == ("oag",)
    register_worker(factory)
    capabilities = client.get("/api/v1/admin/etl/dispatch", headers=AUTH).json()["sources"]
    assert {s for s,c in capabilities.items() if c["available"]} == {"oag"}
    for value in ("", "oag,oag", "unknown", "oag,", " oag", "cra", "opendata"):
        monkeypatch.setenv("ADMIN_ETL_DISPATCH_SOURCES", value)
        with pytest.raises(ValueError, match="source selection"):
            selected_sources()


def test_handler_loss_heartbeat_updates_only_its_capability(pg, monkeypatch):
    from admin_etl_dispatch_worker import heartbeat
    client, factory, _ = pg
    generation = register_worker(factory)
    monkeypatch.delitem(REGISTRY._handlers, "population")
    assert heartbeat(factory, generation)
    capabilities = client.get("/api/v1/admin/etl/dispatch", headers=AUTH).json()["sources"]
    assert capabilities["knbs"]["available"] is False
    assert capabilities["treasury"]["available"] is True
    assert post(client, generation, "knbs").status_code == 503


@pytest.mark.parametrize("source", ["treasury", "cob", "knbs"])
def test_source_domain_database_mismatch_refuses_atomic_acceptance(pg, monkeypatch, source):
    from admin_etl_dispatch import SOURCE_DOMAINS
    client, factory, _ = pg
    generation = register_worker(factory)
    monkeypatch.setitem(SOURCE_DOMAINS, source, "audits")
    refused = post(client, generation, source)
    assert refused.status_code == 503 and "constraint" not in refused.text
    with factory() as db:
        assert db.query(EtlDispatchCommand).count() == 0
        assert db.scalar(text("SELECT count(*) FROM admin_audit_log")) == 0


@pytest.mark.parametrize("source", MAPPINGS)
def test_two_claimers_and_native_owner_serialize_exact_domain(pg, source):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from seeding.exclusion import enter_domain
    client, factory, _ = pg
    generation = register_worker(factory)
    native = enter_domain(factory, MAPPINGS[source], False)
    try:
        post(client, generation, source)
        assert claim(factory, generation) is None
    finally:
        native.close()  # Unacknowledged native ownership stays retained.
    with factory() as db:
        assert db.get(SeedingDomainClaim, native.identity).released_at is None
    # A distinct domain proceeds while the original native claim stays occupied.
    other_source = "oag" if source != "oag" else "knbs"
    other = post(client, generation, other_source).json()["command"]["id"]
    barrier = Barrier(2)
    def competing():
        barrier.wait(timeout=5)
        return claim(factory, generation)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: competing(), range(2)))
    assert sum(v is not None for v in results) == 1
    assert str(next(v for v in results if v)[0]) == other


@pytest.mark.parametrize("source", MAPPINGS)
def test_mapping_lost_ack_recovers_one_actor_audit_and_same_intent(pg, monkeypatch, source):
    from sqlalchemy.orm import Session
    client, factory, engine = pg
    generation, key = register_worker(factory), uuid4()
    class LostAck(Session):
        def commit(self):
            super().commit()
            raise RuntimeError("Inert lost acceptance acknowledgement")
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, class_=LostAck))
    assert post(client, generation, source, key=key).status_code == 503
    monkeypatch.setattr(database, "SessionLocal", factory)
    replay = post(client, uuid4(), source, key=key)
    assert replay.status_code == 202 and replay.json()["replayed"] is True
    assert post(client, generation, source, True, key).status_code == 409
    with factory() as db:
        assert db.query(EtlDispatchCommand).count() == 1
        assert db.scalar(text("SELECT count(*) FROM admin_audit_log WHERE actor_id='batch10-admin'")) == 1


@pytest.mark.parametrize("source", MAPPINGS)
def test_each_mapping_auth_generation_and_default_off_refuse_no_effect(pg, monkeypatch, source):
    client, factory, engine = pg
    generation = register_worker(factory)
    assert post(client, uuid4(), source).status_code == 409
    path = '/api/v1/admin/etl/trigger/' + source
    assert client.post(path, json={}).status_code == 401
    assert client.post(path, json={}, headers={'Authorization':'Bearer nonadmin'}).status_code == 403
    monkeypatch.delenv('ADMIN_ETL_DISPATCH_ENABLED')
    assert post(client, generation, source).status_code == 503
    with engine.connect() as c:
        for table in ('admin_audit_log','etl_dispatch_commands','batch10_effects'):
            assert c.scalar(text('SELECT count(*) FROM '+table)) == 0

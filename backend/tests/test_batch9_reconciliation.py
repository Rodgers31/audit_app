"""Owned direct PostgreSQL controls for audited plan/apply and legacy rows."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
from types import SimpleNamespace
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from models import IngestionJob, IngestionStatus
from seeding.exclusion import reserve
from seeding.reconciliation import (WRITERS, ReconciliationRefused, apply_plan,
                                    _context, canonical, digest, make_plan, target_identity)

ROOT = Path(__file__).resolve().parents[1]
URL = os.environ.get("BATCH9_RECONCILIATION_DATABASE_URL")


@pytest.fixture
def owned(request):
    assert URL and "@127.0.0.1:55493/batch9-reconciliation-" in URL, "Explicit owned database required; no skips"
    admin = create_engine(URL.rsplit("/", 1)[0] + "/postgres", poolclass=NullPool, isolation_level="AUTOCOMMIT")
    name = "batch9-reconciliation-" + uuid4().hex
    template = URL.rsplit("/", 1)[1]
    revision = getattr(request, "param", None)
    with admin.connect() as c:
        suffix = f' TEMPLATE "{template}"' if revision is None else ""
        c.execute(text(f'CREATE DATABASE "{name}"' + suffix))
    url = URL.rsplit("/", 1)[0] + "/" + name
    if revision is not None:
        import subprocess
        import sys
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision], cwd=ROOT,
            env={"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1",
                 "PYTHON_DOTENV_DISABLED": "1", "DATABASE_URL": url}, text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
    engine = create_engine(url, poolclass=NullPool)
    factory = sessionmaker(bind=engine)
    connection = engine.connect()
    connection.execute(text("SET search_path = public"))
    connection.execute(text("SET TimeZone = 'UTC'"))
    connection.commit()

    def admission(allowed):
        with admin.connect() as c:
            c.execute(text(f'ALTER DATABASE "{name}" ALLOW_CONNECTIONS ' + ("true" if allowed else "false")))

    value = SimpleNamespace(admin=admin, name=name, url=url, engine=engine,
                            factory=factory, connection=connection, admission=admission)
    try:
        yield value
    finally:
        connection.close()
        engine.dispose()
        admission(True)
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def native(db, domain="audits", running=True):
    identity = uuid4()
    with db.factory.begin() as session:
        assert reserve(session, domain, identity)
        if running:
            session.add(IngestionJob(domain=domain, status=IngestionStatus.RUNNING,
                meta={"seeding_claim_id": str(identity)}, errors=[]))
    return {"domain": domain, "claim_id": str(identity), "legacy_job_ids": []}


def legacy(db, domain="national_budget"):
    with db.factory.begin() as session:
        job = IngestionJob(domain=domain, status=IngestionStatus.RUNNING, meta={"original": "kept"}, errors=["original error"])
        session.add(job)
        session.flush()
        identity = job.id
    return {"domain": domain, "claim_id": None, "legacy_job_ids": [identity]}


def signed(db, selected, writer_state="stopped"):
    connection = db.connection
    target = target_identity(connection)
    now = connection.scalar(text("SELECT clock_timestamp()"))
    try:
        context_hash = digest(_context(connection, selected))
    except ReconciliationRefused:
        # Negative malformed-row controls deliberately submit a signed placeholder
        # context. The product must refuse the actual durable correlation first.
        context_hash = "0" * 64
    connection.rollback()
    keys = {name: Ed25519PrivateKey.generate() for name in ("operator", "host:owned", "scheduler:owned")}

    def public(key):
        return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    policy = {"version": 1, "target": target, "operators": {"operator": public(keys["operator"])},
              "scopes": {name: {"kind": name.split(":")[0], "public_key": public(keys[name])} for name in keys if name != "operator"}}
    artifact = {"target": target, "observed_at": now.isoformat(), "source": "owned inert fixture process and effects census",
                "content": "Local fixture only: independently tracked process groups stopped, launchers held; effects reconciled."}
    artifact_id = digest(artifact)
    evidence = {"version": 1, "target": target, "selector": selected, "who": "operator",
                "why": "Investigated interrupted fixture execution", "effects": "Owned inert effect census reconciled; no financial/provider calls",
                "effects_artifact": artifact_id, "context_sha256": context_hash,
                "artifacts": {artifact_id: artifact}, "statements": []}
    for scope in policy["scopes"]:
        payload = {"scope": scope, "target": target, "observed_at": now.isoformat(),
                   "hold_until": (now + timedelta(minutes=4)).isoformat(),
                   "fence_release": "explicit_operator_after_durable_audit",
                   "writers": {writer: writer_state for writer in WRITERS}, "artifact": artifact_id}
        evidence["statements"].append({"payload": payload, "signature": keys[scope].sign(canonical(payload)).hex()})
    evidence["signature"] = keys["operator"].sign(canonical(evidence)).hex()
    return policy, evidence, keys


def resign(evidence, keys):
    for statement in evidence["statements"]:
        statement["signature"] = keys[statement["payload"]["scope"]].sign(canonical(statement["payload"])).hex()
    evidence["signature"] = keys["operator"].sign(canonical({k: v for k, v in evidence.items() if k != "signature"})).hex()


def read(db, sql):
    result = db.connection.execute(text(sql)).mappings().all()
    db.connection.rollback()
    return result


def test_audited_native_reconciliation_and_subsequent_native_run(owned):
    selected = native(owned)
    policy, evidence, _ = signed(owned, selected)
    original = read(owned, "SELECT * FROM seeding_domain_claims")[0]
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    assert read(owned, "SELECT * FROM seeding_domain_claims")[0] == original
    result = apply_plan(owned.connection, policy, evidence, plan)
    claim = read(owned, "SELECT * FROM seeding_domain_claims")[0]
    assert result["status"] == "applied" and claim["released_at"] and claim["reconciled_by"] == "operator"
    for field in ("id", "acquired_at", "entered_at", "entry_id", "returned_at", "job_id"):
        assert claim[field] == original[field]
    job = read(owned, "SELECT * FROM ingestion_jobs")[0]
    assert job["status"] == "FAILED" and job["metadata"]["seeding_claim_id"] == selected["claim_id"]
    assert read(owned, "SELECT * FROM admin_audit_log")[0]["payload"]["evidence_sha256"] == digest(evidence)
    with pytest.raises(ReconciliationRefused, match="owner mismatch"):
        apply_plan(owned.connection, policy, evidence, plan)
    owned.admission(True)
    from seeding.exclusion import enter_domain
    execution = enter_domain(owned.factory, "audits", False)
    try:
        with owned.factory.begin() as session:
            job = IngestionJob(domain="audits", status=IngestionStatus.COMPLETED,
                started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
                meta={"seeding_claim_id": str(execution.identity)}, errors=[])
            session.add(job)
            session.flush()
            job_id = job.id
        execution.acknowledge(job_id)
    finally:
        execution.close()
    assert len(read(owned, "SELECT * FROM seeding_domain_claims WHERE released_at IS NOT NULL")) == 2


def test_legacy_observations_without_claim_are_exact_and_audited(owned):
    selected = legacy(owned)
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    apply_plan(owned.connection, policy, evidence, plan)
    assert read(owned, "SELECT * FROM seeding_domain_claims") == []
    job = read(owned, "SELECT * FROM ingestion_jobs")[0]
    assert job["status"] == "FAILED" and job["metadata"]["original"] == "kept" and job["errors"][0] == "original error"
    assert read(owned, "SELECT * FROM admin_audit_log")[0]["action"] == "seeding.reconcile"


@pytest.mark.parametrize("mutation", ["claim", "observation", "worker"])
def test_durable_snapshot_drift_is_refused(owned, mutation):
    selected = native(owned)
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    with owned.connection.begin():
        if mutation == "claim":
            owned.connection.execute(text("UPDATE seeding_domain_claims SET entry_id=:entry"), {"entry": uuid4()})
        elif mutation == "observation":
            owned.connection.execute(text("UPDATE ingestion_jobs SET items_created=3"))
        else:
            owned.connection.execute(text("INSERT INTO etl_dispatch_worker VALUES (1,:generation,now(),now()+interval '1 second',false)"), {"generation": uuid4()})
    with pytest.raises(ReconciliationRefused, match="changed since plan"):
        apply_plan(owned.connection, policy, evidence, plan)
    assert len(read(owned, "SELECT * FROM seeding_domain_claims WHERE released_at IS NULL")) == 1


@pytest.mark.parametrize("field", ["who", "why", "effects"])
@pytest.mark.parametrize("blank", ["\t\n", "\u2003\u00a0", "\u202f\u3000"])
def test_blank_operator_fields_refuse_even_authorized_signature(owned, field, blank):
    selected = native(owned)
    policy, evidence, keys = signed(owned, selected)
    evidence[field] = blank
    resign(evidence, keys)
    owned.admission(False)
    with pytest.raises(ReconciliationRefused, match="Nonblank"):
        make_plan(owned.connection, policy, evidence)


@pytest.mark.parametrize("case", ["signature", "missing_scope", "unknown_scope", "live", "unknown", "incomplete_writers", "artifact", "target", "time", "hold", "unsigned_operator"])
def test_incomplete_live_uncertain_or_unverified_evidence_refuses(owned, case):
    selected = native(owned)
    policy, evidence, keys = signed(owned, selected)
    payload = evidence["statements"][0]["payload"]
    if case == "signature":
        evidence["signature"] = "00" * 64
    elif case == "missing_scope":
        evidence["statements"].pop()
    elif case == "unknown_scope":
        payload["scope"] = "host:unknown"
    elif case in ("live", "unknown"):
        payload["writers"]["dedicated_adapter_orphans"] = case
    elif case == "incomplete_writers":
        payload["writers"].pop("legacy_etl")
    elif case == "artifact":
        next(iter(evidence["artifacts"].values()))["content"] = "changed"
    elif case == "target":
        evidence["target"] = {**evidence["target"], "database_oid": 0}
    elif case == "time":
        payload["observed_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    elif case == "hold":
        payload["hold_until"] = payload["observed_at"]
    else:
        policy["operators"] = {}
    if case not in ("signature", "unknown_scope"):
        resign(evidence, keys)
    owned.admission(False)
    with pytest.raises(ReconciliationRefused):
        make_plan(owned.connection, policy, evidence)
    assert read(owned, "SELECT * FROM admin_audit_log") == []


def test_open_admission_and_ordinary_application_session_refuse(owned):
    selected = native(owned)
    policy, evidence, _ = signed(owned, selected)
    with pytest.raises(ReconciliationRefused, match="admission"):
        make_plan(owned.connection, policy, evidence)
    application = owned.engine.connect()
    owned.admission(False)
    try:
        with pytest.raises(ReconciliationRefused, match="sessions"):
            make_plan(owned.connection, policy, evidence)
    finally:
        application.close()
    make_plan(owned.connection, policy, evidence)


@pytest.mark.parametrize("tag", ["bad-uuid", None, "other-domain"])
def test_legacy_mode_never_treats_invalid_claim_tags_as_unclaimed(owned, tag):
    selected = legacy(owned)
    with owned.factory.begin() as session:
        session.execute(text("UPDATE ingestion_jobs SET metadata=jsonb_build_object('seeding_claim_id',:tag)"), {"tag": tag})
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    if tag is None:
        # JSON null is still an explicit tag and must be investigated.
        with pytest.raises(ReconciliationRefused):
            make_plan(owned.connection, policy, evidence)
    else:
        with pytest.raises(ReconciliationRefused, match="owner tag"):
            make_plan(owned.connection, policy, evidence)


def test_release_failure_rolls_back_claim_observation_and_audit(owned):
    selected = native(owned)
    with owned.connection.begin():
        owned.connection.execute(text("CREATE FUNCTION batch9_reject_job() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'owned rollback control'; END $$"))
        owned.connection.execute(text("CREATE TRIGGER batch9_reject_job BEFORE UPDATE ON ingestion_jobs FOR EACH ROW EXECUTE FUNCTION batch9_reject_job()"))
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    with pytest.raises(DBAPIError):
        apply_plan(owned.connection, policy, evidence, plan)
    assert read(owned, "SELECT * FROM seeding_domain_claims")[0]["released_at"] is None
    assert read(owned, "SELECT * FROM ingestion_jobs")[0]["status"] == "RUNNING"
    assert read(owned, "SELECT * FROM admin_audit_log") == []


def test_wrong_and_expired_plan_refuse_then_valid_plan_applies(owned):
    selected = native(owned)
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    for field, value in (("planned_at", "2000-01-01T00:00:00+00:00"), ("backend", {"pid": -1}), ("policy_sha256", "0" * 64)):
        invalid = deepcopy(plan)
        invalid[field] = value
        with pytest.raises(ReconciliationRefused):
            apply_plan(owned.connection, policy, evidence, invalid)
    assert apply_plan(owned.connection, policy, evidence, plan)["status"] == "applied"


@pytest.mark.parametrize("status", ["RUNNING", "FAILED"])
def test_native_claim_with_dispatch_tags_is_not_reconcilable(owned, status):
    selected = native(owned)
    with owned.factory.begin() as session:
        session.execute(text("UPDATE ingestion_jobs SET status=:status, metadata=metadata || jsonb_build_object('dispatch_command_id',:id,'dispatch_claim_token',:token)"),
                        {"status": status, "id": str(uuid4()), "token": str(uuid4())})
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    with pytest.raises(ReconciliationRefused, match="correlation"):
        make_plan(owned.connection, policy, evidence)


def test_plan_refuses_effects_committed_after_operator_effects_census(owned):
    selected = native(owned)
    with owned.connection.begin():
        owned.connection.execute(text("CREATE TABLE batch9_effects (value integer)"))
    policy, evidence, _ = signed(owned, selected)
    with owned.connection.begin():
        owned.connection.execute(text("INSERT INTO batch9_effects VALUES (17)"))
    owned.admission(False)
    with pytest.raises(ReconciliationRefused, match="effects|census"):
        make_plan(owned.connection, policy, evidence)


@pytest.mark.parametrize("owned", ["ea1645a4c0b5"], indirect=True)
def test_preclaim_deployed_schema_legacy_observations_have_truthful_path(owned):
    selected = legacy(owned, "fiscal_summary")
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    assert not any(plan["snapshot"]["schema_presence"].values())
    apply_plan(owned.connection, policy, evidence, plan)
    assert read(owned, "SELECT * FROM ingestion_jobs")[0]["status"] == "FAILED"
    assert read(owned, "SELECT * FROM admin_audit_log")[0]["payload"]["selector"] == selected


def test_real_unicode_operator_evidence_is_within_durable_limit(owned):
    selected = native(owned)
    policy, evidence, keys = signed(owned, selected)
    evidence["effects"] = "核" * 1500
    evidence["why"] = "é" * 500
    resign(evidence, keys)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    assert apply_plan(owned.connection, policy, evidence, plan)["status"] == "applied"
    row = read(owned, "SELECT * FROM seeding_domain_claims")[0]
    assert len(row["reconciliation"]) <= 4000


def test_evidence_expiring_during_mutation_rolls_back(owned):
    selected = native(owned)
    with owned.connection.begin():
        owned.connection.execute(text("CREATE FUNCTION batch9_slow_job() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(1.5); RETURN NEW; END $$"))
        owned.connection.execute(text("CREATE TRIGGER batch9_slow_job BEFORE UPDATE ON ingestion_jobs FOR EACH ROW EXECUTE FUNCTION batch9_slow_job()"))
    policy, evidence, keys = signed(owned, selected)
    for statement in evidence["statements"]:
        observed = datetime.fromisoformat(statement["payload"]["observed_at"])
        statement["payload"]["hold_until"] = (observed + timedelta(seconds=1)).isoformat()
    resign(evidence, keys)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    with pytest.raises(ReconciliationRefused, match="Stale"):
        apply_plan(owned.connection, policy, evidence, plan)
    assert read(owned, "SELECT * FROM seeding_domain_claims")[0]["released_at"] is None
    assert read(owned, "SELECT * FROM admin_audit_log") == []


def dispatch_retained(db, returned=False, refusal=False):
    from admin_etl_dispatch import accept, TriggerBody
    from admin_etl_dispatch_worker import claim, register_worker
    from seeding.exclusion import DomainExecution, dispatch_scope, enter_domain
    generation = register_worker(db.factory)
    with db.factory() as session:
        accepted = accept(session, SimpleNamespace(id="operator", email="owned@example.invalid"), "oag",
                          TriggerBody(dispatch_generation=str(generation)), str(uuid4()))
    command_id, token = claim(db.factory, generation)
    execution = DomainExecution(db.factory, "audits", token, command_id, generation)
    if not refusal:
        with db.factory.begin() as session:
            session.execute(text("UPDATE etl_dispatch_commands SET execution_started=true"))
        execution.open()
        with dispatch_scope(execution):
            assert enter_domain(db.factory, "audits", False) is execution
    try:
        with db.factory.begin() as session:
            meta = {"dispatch_command_id": str(command_id), "dispatch_claim_token": str(token)}
            if refusal:
                meta["ownership_refused"] = True
            else:
                meta["seeding_claim_id"] = str(token)
            status = IngestionStatus.FAILED if refusal else (IngestionStatus.COMPLETED if returned else IngestionStatus.RUNNING)
            job = IngestionJob(domain="audits", status=status,
                started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc) if returned or refusal else None,
                meta=meta, errors=[])
            session.add(job)
            session.flush()
            job_id = job.id
        if returned:
            execution.acknowledge(job_id)
    finally:
        execution.close()
    with db.factory.begin() as session:
        session.execute(text("UPDATE etl_dispatch_worker SET ready=false"))
    assert command_id == accepted.command.id
    return {"domain": "audits", "claim_id": str(token), "legacy_job_ids": []}


@pytest.mark.parametrize("table", ["admin_audit_log", "seeding_domain_claims", "etl_dispatch_commands", "etl_dispatch_domains", "ingestion_jobs"])
def test_dispatch_claim_command_domain_observations_and_audit_are_atomic(owned, monkeypatch, table):
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    selected = dispatch_retained(owned)
    before = {name: read(owned, "SELECT * FROM " + name) for name in
              ("admin_audit_log", "seeding_domain_claims", "etl_dispatch_commands", "etl_dispatch_domains", "ingestion_jobs")}
    with owned.connection.begin():
        owned.connection.execute(text("CREATE FUNCTION batch9_reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'owned atomic control'; END $$"))
        event = "INSERT" if table == "admin_audit_log" else "UPDATE"
        owned.connection.execute(text(f"CREATE TRIGGER batch9_reject_mutation BEFORE {event} ON {table} FOR EACH ROW EXECUTE FUNCTION batch9_reject_mutation()"))
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    with pytest.raises(DBAPIError):
        apply_plan(owned.connection, policy, evidence, plan)
    for name, rows in before.items():
        assert read(owned, "SELECT * FROM " + name) == rows


@pytest.mark.parametrize("returned,refusal", [(True, False), (False, True)])
def test_dispatch_keeps_genuine_return_or_refusal_evidence(owned, monkeypatch, returned, refusal):
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    selected = dispatch_retained(owned, returned=returned, refusal=refusal)
    original = read(owned, "SELECT * FROM seeding_domain_claims")[0]
    observations = read(owned, "SELECT * FROM ingestion_jobs")
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    apply_plan(owned.connection, policy, evidence, plan)
    current = read(owned, "SELECT * FROM seeding_domain_claims")[0]
    for field in ("entered_at", "entry_id", "returned_at", "job_id"):
        assert current[field] == original[field]
    assert read(owned, "SELECT * FROM ingestion_jobs") == observations
    assert current["released_at"] and read(owned, "SELECT * FROM etl_dispatch_domains")[0]["claim_token"] is None


def test_new_owner_is_refused(owned, monkeypatch):
    monkeypatch.setenv("ADMIN_ETL_DISPATCH_ENABLED", "true")
    selected = native(owned)
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    with owned.connection.begin():
        owned.connection.execute(text("UPDATE seeding_domain_claims SET id=:id"), {"id": uuid4()})
    with pytest.raises(ReconciliationRefused, match="owner mismatch"):
        apply_plan(owned.connection, policy, evidence, plan)
    assert read(owned, "SELECT * FROM seeding_domain_claims")[0]["released_at"] is None


def test_autocommit_backend_cannot_release(owned):
    selected = native(owned)
    policy, evidence, _ = signed(owned, selected)
    owned.admission(False)
    plan = make_plan(owned.connection, policy, evidence)
    owned.connection.execution_options(isolation_level="AUTOCOMMIT")
    with pytest.raises(ReconciliationRefused, match="does not hold"):
        apply_plan(owned.connection, policy, evidence, plan)
    assert read(owned, "SELECT * FROM seeding_domain_claims")[0]["released_at"] is None

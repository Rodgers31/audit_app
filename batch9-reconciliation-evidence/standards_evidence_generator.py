"""Independent Standards boundary controls; owned files and inert SQLite only."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import traceback
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles

from models import (AdminAuditLog, EtlDispatchCommand, EtlDispatchDomain,
                    EtlDispatchWorker, IngestionJob, SeedingDomainClaim)
from seeding import reconciliation as subject

ROOT = Path(__file__).resolve().parents[1]
REPORT = Path(__file__).with_name("standards-review.md")
SOURCE_PATHS = [
    "backend/seeding/reconciliation.py", "backend/seeding/reconcile_operator.py",
    "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py", "backend/models.py",
    "batch9-reconciliation-evidence/operator-procedure.md", "batch9-reconciliation-evidence/read_only_census.sql",
    "batch9-reconciliation-evidence/writer-census.json", "batch9-reconciliation-evidence/inventory_receipt.py",
]


def hashes():
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_PATHS}


def fixture():
    """Keys/target are synthetic and only authorize this process's boundary fixture."""
    now = datetime.now(timezone.utc)
    target = {"database": "batch9-reconciliation-standards-inert", "maintenance_role": "postgres",
              "database_oid": 12345, "system_identifier": "INERT_STANDARDS_CONTROL", "revision": "e583b9c9a001"}
    keys = {name: Ed25519PrivateKey.from_private_bytes(sha256(("batch9-standards-inert-" + name).encode()).digest())
            for name in ("host", "scheduler", "operator")}
    public = {name: key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
              for name, key in keys.items()}
    policy = {"version": 1, "target": target, "scopes": {
        name: {"kind": name, "public_key": public[name]} for name in ("host", "scheduler")},
        "operators": {"fixture-operator": public["operator"]}}
    artifact = {"source": "Synthetic inert independent Standards fixture", "observed_at": now.isoformat(),
                "target": target, "content": "No host or production claim is asserted by this fixture."}
    artifact_id = subject.digest(artifact)
    evidence = {"version": 1, "target": target, "selector": {"domain": "standards-inert",
        "claim_id": "f53c2a89-328f-4de3-b2eb-d80e72c7252a", "legacy_job_ids": []},
        "who": "fixture-operator", "why": "Exercise independent boundary controls",
        "effects": "Synthetic SQLite only; no financial effects", "effects_artifact": artifact_id,
        "context_sha256": "0" * 64, "artifacts": {artifact_id: artifact}, "statements": [], "signature": ""}
    for name in ("host", "scheduler"):
        payload = {"scope": name, "target": target, "observed_at": now.isoformat(),
                   "hold_until": (now + timedelta(minutes=4)).isoformat(),
                   "fence_release": "explicit_operator_after_durable_audit",
                   "writers": {writer: "absent" for writer in subject.WRITERS}, "artifact": artifact_id}
        evidence["statements"].append({"payload": payload, "signature": keys[name].sign(subject.canonical(payload)).hex()})
    return now, target, policy, evidence, keys


def sign(evidence, keys):
    evidence["signature"] = keys["operator"].sign(subject.canonical({k: v for k, v in evidence.items() if k != "signature"})).hex()


@compiles(JSONB, "sqlite")
def jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def controls():
    now, target, policy, original, keys = fixture()
    outcomes = []
    cases = [
        ("valid_ascii", lambda e: None, True),
        ("valid_unicode_max_effects", lambda e: e.update(effects="核" * 1500), True),
        ("whitespace_only_why", lambda e: e.update(why="\t\n\u2003\u3000"), False),
        ("boolean_version", lambda e: e.update(version=True), False),
        ("artifact_wrong_container", lambda e: e.update(artifacts=[]), False),
        ("missing_effects_artifact", lambda e: e.update(effects_artifact="f" * 64), False),
        ("uncertain_writer", lambda e: e["statements"][0]["payload"]["writers"].update(native_manual="uncertain"), False),
        ("duplicate_scope", lambda e: e["statements"].__setitem__(1, deepcopy(e["statements"][0])), False),
    ]
    for name, mutate, expected in cases:
        evidence = deepcopy(original)
        mutate(evidence)
        for statement in evidence["statements"]:
            statement["signature"] = keys[statement["payload"]["scope"]].sign(subject.canonical(statement["payload"])).hex()
        sign(evidence, keys)
        try:
            subject.verify_evidence(policy, evidence, target, now)
            accepted, message = True, "accepted"
        except subject.ReconciliationRefused as error:
            accepted, message = False, str(error)
        assert accepted is expected, (name, accepted, expected)
        outcomes.append({"control": name, "expected_accepted": expected, "actual_accepted": accepted, "diagnostic": message})

    # Measure the actual durable representation used by apply_plan. This is a
    # storage boundary control, not a substituted CLI or ownership-race proof.
    evidence = deepcopy(original)
    evidence["effects"] = "核" * 1500
    sign(evidence, keys)
    subject.verify_evidence(policy, evidence, target, now)
    record = {"version": 1, "who": evidence["who"], "why": evidence["why"], "effects": evidence["effects"],
              "evidence_sha256": subject.digest(evidence), "plan_sha256": "a" * 64,
              "policy_sha256": subject.digest(policy), "target": target, "selector": evidence["selector"],
              "reconciled_at": now.isoformat()}
    durable_text = subject._record_text(record)
    engine = create_engine("sqlite://")
    for model in (AdminAuditLog, IngestionJob, EtlDispatchCommand, SeedingDomainClaim):
        model.__table__.create(engine)
    rejected = False
    try:
        with engine.begin() as connection:
            connection.execute(SeedingDomainClaim.__table__.insert().values(
                id=UUID(evidence["selector"]["claim_id"]), domain=evidence["selector"]["domain"], kind="native",
                acquired_at=now, entered_at=now, entry_id=UUID("e15fd386-02b7-4be0-9c65-4b1516a7c81b"),
                released_at=now, reconciled_by=evidence["who"], reconciliation=durable_text))
    except IntegrityError as error:
        rejected = True
        diagnostic = str(error.orig)
    else:
        diagnostic = "insert accepted"
    with engine.begin() as connection:
        retained_rows = connection.scalar(sqlalchemy.select(sqlalchemy.func.count()).select_from(SeedingDomainClaim.__table__))
        connection.execute(SeedingDomainClaim.__table__.delete())
    engine.dispose()
    assert retained_rows == (0 if rejected else 1), "Storage outcome disagrees with durable row count"
    outcomes.append({"control": "allowed_unicode_effects_durable_record", "evidence_validation": "accepted",
                     "durable_record_characters": len(durable_text), "constraint_limit": 4000,
                     "storage_rejected": rejected, "diagnostic": diagnostic, "durable_fixture_rows_before_cleanup": retained_rows,
                     "interpretation": "reproduced valid-evidence/storage-boundary defect" if rejected else "fixed representation"})
    return outcomes


def expiry_control():
    """Actual PostgreSQL commit that crosses a short attested hold window."""
    from sqlalchemy.orm import sessionmaker
    from seeding.exclusion import reserve

    database = "batch9-reconciliation-standards-expiry-a46a"
    admin_url = "postgresql+psycopg2://postgres:batch9-inert-local@127.0.0.1:55493/postgres"
    url = admin_url.rsplit("/", 1)[0] + "/" + database
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=sqlalchemy.pool.NullPool)
    engine = connection = None
    created = False
    try:
        with admin.connect() as client:
            assert client.scalar(text("SELECT NOT EXISTS (SELECT 1 FROM pg_database WHERE datname=:name)"), {"name": database})
            client.execute(text('CREATE DATABASE "' + database + '"'))
            created = True
        engine = create_engine(url, poolclass=sqlalchemy.pool.NullPool)
        for model in (AdminAuditLog, IngestionJob, EtlDispatchCommand, EtlDispatchWorker, EtlDispatchDomain, SeedingDomainClaim):
            model.__table__.create(engine)
        identity = uuid4()
        selected = {"domain": "standards-inert", "claim_id": str(identity), "legacy_job_ids": []}
        with sessionmaker(bind=engine).begin() as session:
            assert reserve(session, selected["domain"], identity)
            session.add(IngestionJob(domain=selected["domain"], status="RUNNING", errors=[],
                                     meta={"seeding_claim_id": str(identity)}))
        with engine.begin() as client:
            client.execute(text("CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)"))
            client.execute(text("INSERT INTO alembic_version VALUES ('e583b9c9a001')"))
            client.execute(text("CREATE FUNCTION batch9_standards_slow_job() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(4); RETURN NEW; END $$"))
            client.execute(text("CREATE TRIGGER batch9_standards_slow_job BEFORE UPDATE ON ingestion_jobs FOR EACH ROW EXECUTE FUNCTION batch9_standards_slow_job()"))
        connection = engine.connect()
        connection.execute(text("SET search_path=public"))
        connection.execute(text("SET TimeZone='UTC'"))
        connection.commit()
        with admin.connect() as client:
            client.execute(text('ALTER DATABASE "' + database + '" ALLOW_CONNECTIONS false'))
        inspected = subject.inspect_context(connection, selected)
        _, _, policy, evidence, keys = fixture()
        target = inspected["context"]["target"]
        now = connection.scalar(text("SELECT clock_timestamp()"))
        connection.rollback()
        hold_until = now + timedelta(seconds=3)
        policy["target"] = evidence["target"] = target
        evidence["selector"] = selected
        evidence["context_sha256"] = inspected["context_sha256"]
        artifact = next(iter(evidence["artifacts"].values()))
        artifact.update(target=target, observed_at=now.isoformat())
        artifact_id = subject.digest(artifact)
        evidence["effects_artifact"] = artifact_id
        evidence["artifacts"] = {artifact_id: artifact}
        for statement in evidence["statements"]:
            payload = statement["payload"]
            payload.update(target=target, observed_at=now.isoformat(), hold_until=hold_until.isoformat(), artifact=artifact_id)
            statement["signature"] = keys[payload["scope"]].sign(subject.canonical(payload)).hex()
        sign(evidence, keys)
        plan = subject.make_plan(connection, policy, evidence)
        try:
            result = subject.apply_plan(connection, policy, evidence, plan)
        except subject.ReconciliationRefused as error:
            result = {"status": "refused", "message": str(error)}
        after = connection.scalar(text("SELECT clock_timestamp()"))
        row = connection.execute(SeedingDomainClaim.__table__.select()).mappings().one()
        audits = connection.scalar(sqlalchemy.select(sqlalchemy.func.count()).select_from(AdminAuditLog.__table__))
        connection.rollback()
        return [{"control": "attestation_expires_during_actual_slow_postgres_update", "database": database,
                 "signed_hold_until": hold_until.isoformat(), "database_clock_after_apply": after.isoformat(),
                 "after_hold_window": after > hold_until, "actual_result": result,
                 "claim_released": row["released_at"] is not None, "durable_audit_count": audits,
                 "interpretation": "unsafe expired attestation accepted" if row["released_at"] is not None else "expired attestation rolled back"}]
    finally:
        if connection is not None:
            connection.close()
        if engine is not None:
            engine.dispose()
        if created:
            with admin.connect() as client:
                client.execute(text('ALTER DATABASE "' + database + '" ALLOW_CONNECTIONS true'))
                client.execute(text('DROP DATABASE "' + database + '"'))
        admin.dispose()


def adapter_child():
    """Actual adapter/CLI entry; only its registry handler is inert."""
    import socket
    from sqlalchemy.orm import sessionmaker
    import admin_etl_dispatch_adapter as adapter
    from seeding import registries
    import seeding.domains.audits.scope  # Real package registers before the fixture replaces its handler.

    original_connect = socket.socket.connect

    def loopback_only(sock, address):
        if type(address) is not tuple or address[0] not in ("127.0.0.1", "localhost") or address[1] != 55493:
            raise RuntimeError("Standards fixture forbids non-owned network connections")
        return original_connect(sock, address)

    socket.socket.connect = loopback_only

    def never_expected_handler(_session, _settings, context):
        raise AssertionError("Actual CLI refused entry must not call the inert handler")

    registries.REGISTRY._handlers = {"audits": never_expected_handler}
    registries.load_builtin_domains = lambda: None
    engine = create_engine(os.environ["DATABASE_URL"], poolclass=sqlalchemy.pool.NullPool)
    try:
        result = adapter.execute(sessionmaker(bind=engine), engine, *(UUID(item) for item in sys.argv[2:5]))
    finally:
        engine.dispose()
    print(json.dumps({"actual_adapter_returncode": result, "handler": "inert and expected uncalled"}))
    return result


def postgres_refusal_control():
    """Own sibling database; actual separate OS adapter/CLI process."""
    from sqlalchemy.orm import sessionmaker
    from admin_etl_dispatch import TriggerBody, accept
    from admin_etl_dispatch_worker import claim, register_worker
    from supabase_auth import AdminUser

    database = "batch9-reconciliation-standards-a46a"
    admin_url = "postgresql+psycopg2://postgres:batch9-inert-local@127.0.0.1:55493/postgres"
    url = admin_url.rsplit("/", 1)[0] + "/" + database
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=sqlalchemy.pool.NullPool)
    engine = None
    created = False
    try:
        with admin.connect() as connection:
            assert connection.scalar(text("SELECT NOT EXISTS (SELECT 1 FROM pg_database WHERE datname=:name)"), {"name": database})
            connection.execute(text('CREATE DATABASE "' + database + '"'))
            created = True
        engine = create_engine(url, poolclass=sqlalchemy.pool.NullPool)
        for model in (AdminAuditLog, IngestionJob, EtlDispatchCommand, EtlDispatchWorker, EtlDispatchDomain, SeedingDomainClaim):
            model.__table__.create(engine)
        factory = sessionmaker(bind=engine)
        generation = register_worker(factory)
        with factory() as db:
            accepted = accept(db, AdminUser(id="standards-inert-actor", email="inert@example.invalid", roles=["admin"]),
                              "oag", TriggerBody(dispatch_generation=str(generation)), str(uuid4()))
            assert accepted.accepted is True
        command_id, token = claim(factory, generation)
        # A real durable competing state change at the adapter->CLI boundary.
        # Product worker/adapter/CLI/acquisition code is never substituted.
        with engine.begin() as connection:
            connection.execute(text("""CREATE FUNCTION batch9_standards_fence_entry() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.execution_started AND NOT OLD.execution_started THEN
                        UPDATE etl_dispatch_worker SET ready=false WHERE id=1;
                    END IF;
                    RETURN NEW;
                END $$"""))
            connection.execute(text("CREATE TRIGGER batch9_standards_fence_entry BEFORE UPDATE ON etl_dispatch_commands FOR EACH ROW EXECUTE FUNCTION batch9_standards_fence_entry()"))
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_DOTENV_DISABLED": "1",
               "PYTHONPATH": str(ROOT / "backend"), "DATABASE_URL": url, "ADMIN_ETL_DISPATCH_ENABLED": "true"}
        command = [sys.executable, str(Path(__file__).resolve()), "--adapter", str(command_id), str(token), str(generation)]
        process = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=20)
        assert process.returncode == 1, (process.returncode, process.stdout, process.stderr)
        with factory() as db:
            assert db.query(IngestionJob).count() == 1, (process.stdout, process.stderr)
            row = db.query(IngestionJob).one()
            owner = db.get(SeedingDomainClaim, token)
            assert row.meta["ownership_refused"] is True and row.status.name == "FAILED"
            assert "seeding_claim_id" not in row.meta
            assert owner.entered_at is None and owner.returned_at is None and owner.released_at is None
            shape = {"id": row.id, "status": row.status.name, "metadata": row.meta,
                     "owner_entered_at": None, "owner_returned_at": None, "owner_released_at": None}
        with engine.connect() as connection:
            try:
                subject._snapshot(connection, {"domain": "audits", "claim_id": str(token), "legacy_job_ids": []})
            except subject.ReconciliationRefused as error:
                rejected, diagnostic = True, str(error)
            else:
                rejected, diagnostic = False, "snapshot accepted"
        return [{"control": "actual_separate_adapter_cli_terminal_refusal_snapshot", "database": database,
                 "command": command, "environment": env, "actual_process_exit_code": process.returncode,
                 "stdout": process.stdout, "stderr": process.stderr, "observation_shape": shape,
                 "reconciliation_snapshot_rejected": rejected, "diagnostic": diagnostic,
                 "interpretation": "confirmed legitimate-refusal boundary defect" if rejected else "fixed legitimate-refusal boundary"}]
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.execute(text('DROP DATABASE "' + database + '"'))
        admin.dispose()


def procedure_controls():
    """Readback/provenance checks supplement the manual procedure review."""
    census = json.loads((ROOT / "batch9-reconciliation-evidence/writer-census.json").read_text())
    generator = ROOT / census["generated_by"]
    mismatches = [name for name, expected in census["source_sha256"].items()
                  if sha256((ROOT / name).read_bytes()).hexdigest() != expected]
    assert not mismatches, mismatches
    assert sha256(generator.read_bytes()).hexdigest() == census["generator_sha256"]
    results = [{"control": "writer_census_provenance_readback", "source_count": len(census["source_sha256"]),
                "source_mismatches": mismatches, "generator_hash_matches": True,
                "registered_domain_count": len(census["registered_domains"]), "candidate_anchors": len(census["matches"]),
                "scope_limit": census["scope"]}]
    for name in ("final-current.json", "final-minimum.json"):
        path = ROOT / "batch9-reconciliation-evidence" / name
        receipt = json.loads(path.read_text())
        assert receipt["exit_code"] == 0 and "102 passed" in receipt["stdout"]
        assert receipt["source_sha256"]["backend/seeding/reconciliation.py"] == sha256((ROOT / "backend/seeding/reconciliation.py").read_bytes()).hexdigest()
        results.append({"control": "author_final_suite_receipt_readback", "receipt": str(path.relative_to(ROOT)),
                        "receipt_sha256": sha256(path.read_bytes()).hexdigest(), "runtime": receipt["runtime"],
                        "exit_code": receipt["exit_code"], "reported_passes": 102,
                        "execution_owner": "author; reviewer readback only", "command": receipt["command"]})
    return results


def main():
    source_hashes = hashes()
    failure = None
    try:
        if "--postgres-refusal" in sys.argv:
            results = postgres_refusal_control()
        elif "--expiry" in sys.argv:
            results = expiry_control()
        elif "--procedure" in sys.argv:
            results = procedure_controls()
        else:
            results = controls()
        assert hashes() == source_hashes, "Reviewed product changed during the control run; rerun"
    except Exception:
        results = []
        failure = traceback.format_exc()
    receipt = {"generated_at": datetime.now(timezone.utc).isoformat(), "generator": str(Path(__file__).relative_to(ROOT)),
               "generator_sha256": sha256(Path(__file__).read_bytes()).hexdigest(), "source_sha256": source_hashes,
               "base_commit": "9e97ca3f1ca43f103a8655447a86d889456a218a",
               "head_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "command": [sys.executable, *sys.argv],
               "environment": {name: os.environ.get(name) for name in ("PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHON_DOTENV_DISABLED")},
               "runtime": {"python": sys.version, "sqlalchemy": sqlalchemy.__version__, "platform": platform.platform()},
               "controls": results, "failure": failure,
               "verdict": "unsuccessful setup/control; no acceptance proven" if failure else "executed controls recorded"}
    section = "\n## Independent boundary receipt\n\n```json\n" + json.dumps(receipt, indent=2) + "\n```\n"
    with REPORT.open("a") as output:
        output.write(section)
    readback = REPORT.read_text()
    assert section in readback and receipt["generator_sha256"] in readback
    print(json.dumps({"receipt_written": str(REPORT), "readback_verified": True, "controls": results}, indent=2))
    if failure:
        print(failure, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--adapter":
        sys.exit(adapter_child())
    sys.exit(main())

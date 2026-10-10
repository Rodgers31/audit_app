"""Audited, PostgreSQL-only maintenance reconciliation. Never an expiry reclaim.

A retained direct connection must be opened BEFORE an independently authorized
operator closes database admission. This module neither closes admission nor
kills sessions. Signed evidence authenticates host/scheduler operator attestations;
it cannot discover remote hosts or prove their statements true. Deployment policy
and its keys must be established independently of submitted evidence.
"""
from datetime import datetime, timedelta
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import or_, select, text

from models import (AdminAuditLog, EtlDispatchCommand, EtlDispatchDomain,
                    EtlDispatchWorker, IngestionJob, SeedingDomainClaim)

VERSION = 1
MAX_BYTES = 65536
MAX_ROWS = 1000
EVIDENCE_VALIDITY = timedelta(minutes=5)
WRITERS = ("native_scheduled", "native_manual", "dedicated_supervisor",
           "dedicated_adapter_orphans", "legacy_etl", "bootstrap",
           "application_auto_seeder", "application_sessions", "parliament",
           "migrations_manual_scripts")


class ReconciliationRefused(RuntimeError):
    """Bounded diagnostic, never a provider/credential exception payload."""


def refuse(message):
    raise ReconciliationRefused(message)


def canonical(value):
    try:
        result = json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=True, allow_nan=False).encode()
    except (ValueError, TypeError):
        refuse("Invalid JSON shape")
    if len(result) > MAX_BYTES:
        refuse("Evidence or plan exceeds bound")
    return result


def digest(value):
    return sha256(canonical(value)).hexdigest()


def meaningful(value, limit):
    if type(value) is not str or not 1 <= len(value) <= limit or not value.strip() or "\x00" in value:
        refuse("Nonblank bounded text required")
    return value


def shape(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        refuse("Incomplete or unexpected fields")


def timestamp(value):
    meaningful(value, 40)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        refuse("Invalid evidence timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        refuse("UTC-aware evidence timestamp required")
    return parsed


def selector(value):
    shape(value, ("domain", "claim_id", "legacy_job_ids"))
    meaningful(value["domain"], 100)
    if value["domain"].strip() != value["domain"]:
        refuse("Exact domain required")
    identity = value["claim_id"]
    if identity is not None:
        try:
            if type(identity) is not str or str(UUID(identity)) != identity:
                refuse("Exact canonical claim identity required")
        except ValueError:
            refuse("Exact canonical claim identity required")
    ids = value["legacy_job_ids"]
    if (type(ids) is not list or len(ids) > MAX_ROWS or
            any(type(i) is not int or not 1 <= i <= 2147483647 for i in ids) or
            ids != sorted(set(ids)) or (identity is None) != bool(ids)):
        refuse("Select one exact claim or sorted legacy observation IDs")


def signature(public_key, sig, payload):
    try:
        if type(public_key) is not str or len(public_key) != 64 or type(sig) is not str or len(sig) != 128:
            refuse("Unverified evidence signature")
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(bytes.fromhex(sig), canonical(payload))
    except (InvalidSignature, ValueError, TypeError):
        refuse("Unverified evidence signature")


def verify_evidence(policy, evidence, target, now):
    canonical(policy)
    canonical(evidence)
    shape(policy, ("version", "target", "scopes", "operators"))
    shape(evidence, ("version", "target", "selector", "who", "why", "effects",
                     "effects_artifact", "context_sha256", "artifacts", "statements", "signature"))
    if type(policy["version"]) is not int or policy["version"] != VERSION or type(evidence["version"]) is not int or evidence["version"] != VERSION:
        refuse("Unsupported evidence version")
    if policy["target"] != target or evidence["target"] != target:
        refuse("Evidence target mismatch")
    selector(evidence["selector"])
    for field, limit in (("who", 64), ("why", 500), ("effects", 1500)):
        meaningful(evidence[field], limit)
    for field in ("effects_artifact", "context_sha256"):
        meaningful(evidence[field], 64)
        if len(evidence[field]) != 64 or any(c not in "0123456789abcdef" for c in evidence[field]):
            refuse("Exact evidence/context digest required")
    if type(policy["operators"]) is not dict or evidence["who"] not in policy["operators"]:
        refuse("Operator is not independently authorized")
    signature(policy["operators"][evidence["who"]], evidence["signature"],
              {k: v for k, v in evidence.items() if k != "signature"})
    scopes = policy["scopes"]
    statements, artifacts = evidence["statements"], evidence["artifacts"]
    if (type(scopes) is not dict or not 2 <= len(scopes) <= 100 or
            type(statements) is not list or len(statements) != len(scopes) or
            type(artifacts) is not dict or not 1 <= len(artifacts) <= 101):
        refuse("Complete host and scheduler scope evidence required")
    kinds, seen, used = set(), set(), {evidence["effects_artifact"]}
    for key, artifact in artifacts.items():
        shape(artifact, ("source", "observed_at", "target", "content"))
        meaningful(artifact["source"], 200)
        meaningful(artifact["content"], 12000)
        observed = timestamp(artifact["observed_at"])
        if not now - EVIDENCE_VALIDITY <= observed <= now or artifact["target"] != target or key != digest(artifact):
            refuse("Stale or mismatched evidence artifact")
    for statement in statements:
        shape(statement, ("payload", "signature"))
        payload = statement["payload"]
        shape(payload, ("scope", "target", "observed_at", "hold_until", "fence_release", "writers", "artifact"))
        scope = payload["scope"]
        if type(scope) is not str or scope not in scopes or scope in seen:
            refuse("Missing or duplicate deployment scope")
        config = scopes[scope]
        shape(config, ("kind", "public_key"))
        if config["kind"] not in ("host", "scheduler"):
            refuse("Invalid deployment scope")
        signature(config["public_key"], statement["signature"], payload)
        if payload["fence_release"] != "explicit_operator_after_durable_audit":
            refuse("Writer fences must remain held until explicit durable-audit verification")
        observed, hold = timestamp(payload["observed_at"]), timestamp(payload["hold_until"])
        if (payload["target"] != target or not now - EVIDENCE_VALIDITY <= observed <= now < hold or
                hold > observed + EVIDENCE_VALIDITY or payload["artifact"] not in artifacts or
                artifacts[payload["artifact"]]["observed_at"] != payload["observed_at"]):
            refuse("Stale, uncertain or mismatched scope evidence")
        writers = payload["writers"]
        shape(writers, WRITERS)
        if any(type(v) is not str or v not in ("stopped", "absent") for v in writers.values()):
            refuse("Live or uncertain writer evidence")
        used.add(payload["artifact"])
        seen.add(scope)
        kinds.add(config["kind"])
    if kinds != {"host", "scheduler"} or seen != set(scopes) or used != set(artifacts):
        refuse("Incomplete or unreferenced evidence")


def _serial(value):
    if isinstance(value, (UUID, datetime)):
        return str(value)
    if hasattr(value, "name"):
        return value.name
    return value


def _rows(connection, table, conditions=()):
    result = connection.execute(select(table).where(*conditions).order_by(*table.primary_key.columns).limit(MAX_ROWS + 1)).mappings().all()
    if len(result) > MAX_ROWS:
        refuse("Observation/history census exceeds bound; investigate explicitly")
    return [{k: _serial(v) for k, v in row.items()} for row in result]


def _exists(connection, name):
    return connection.scalar(text("SELECT to_regclass(:name) IS NOT NULL"), {"name": "public." + name})


def target_identity(connection):
    if connection.dialect.name != "postgresql" or connection.closed or connection.invalidated:
        refuse("Retained direct PostgreSQL connection required")
    if connection.scalar(text("SHOW search_path")) != "public":
        refuse("Explicit public schema path required")
    if connection.scalar(text("SHOW TimeZone")) != "UTC":
        refuse("Explicit UTC database timezone required")
    row = connection.execute(text("""SELECT current_database() AS database, current_user AS maintenance_role,
        (SELECT oid::bigint FROM pg_database WHERE datname=current_database()) AS database_oid,
        (SELECT system_identifier::text FROM pg_control_system()) AS system_identifier,
        (SELECT version_num FROM public.alembic_version) AS revision""")).mappings().one()
    return dict(row)


def _maintenance(connection, lock=False):
    if not connection.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")):
        refuse("Complete database visibility and maintenance privilege required")
    admission = connection.scalar(text("SELECT datallowconn FROM pg_database WHERE datname=current_database()" + (" FOR SHARE" if lock else "")))
    if admission is not False:
        refuse("Database admission is not independently fenced")
    connection.execute(text("SELECT pg_stat_clear_snapshot()"))
    if connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE datid=(SELECT oid FROM pg_database WHERE datname=current_database()) AND pid<>pg_backend_pid())")):
        refuse("Other database sessions or background writers remain")
    if connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_prepared_xacts WHERE database=current_database())")):
        refuse("Prepared transaction effects remain uncertain")


def _snapshot(connection, selected, lock=False):
    selector(selected)
    domain, identity = selected["domain"], selected["claim_id"]
    worker, dispatch, command, ownership = None, None, None, None
    present = {name: _exists(connection, name) for name in
               ("etl_dispatch_worker", "etl_dispatch_domains", "etl_dispatch_commands", "seeding_domain_claims")}
    if present["etl_dispatch_worker"]:
        worker_rows = _rows(connection, EtlDispatchWorker.__table__)
        worker = worker_rows[0] if worker_rows else None
        if worker is not None and worker["ready"] is not False:
            refuse("Dedicated supervisor is not stopped; elapsed lease is not proof")
    if present["etl_dispatch_domains"]:
        rows = _rows(connection, EtlDispatchDomain.__table__, (EtlDispatchDomain.domain == domain,))
        dispatch = rows[0] if rows else None
    if present["seeding_domain_claims"]:
        rows = _rows(connection, SeedingDomainClaim.__table__,
                     (SeedingDomainClaim.domain == domain, SeedingDomainClaim.released_at.is_(None)))
        if rows:
            ownership = rows[0]
    if (identity is None) != (ownership is None) or ownership is not None and ownership["id"] != identity:
        refuse("Exact retained owner mismatch")
    if ownership is not None and ownership["kind"] == "dispatch":
        from admin_etl_dispatch import mapped
        rows = _rows(connection, EtlDispatchCommand.__table__, (EtlDispatchCommand.id == UUID(ownership["command_id"]),))
        command = rows[0] if rows else None
        if (dispatch is None or command is None or not mapped(command["source"], domain) or
                dispatch["claim_token"] != identity or dispatch["command_id"] != ownership["command_id"] or
                command["claim_token"] != identity or command["domain"] != domain or
                command["status"] not in ("running", "interrupted", "completed", "failed")):
            refuse("Dispatch owner/correlation mismatch")
    elif dispatch is not None and dispatch["command_id"] is not None:
        refuse("Unrelated dispatch owner remains")
    if present["etl_dispatch_commands"]:
        running = _rows(connection, EtlDispatchCommand.__table__,
                        (EtlDispatchCommand.domain == domain, EtlDispatchCommand.status == "running"))
        if any(command is None or c["id"] != command["id"] for c in running):
            refuse("Unrelated running dispatch command remains")
    jobs = IngestionJob.__table__
    correlations = [jobs.c.domain == domain]
    if identity:
        correlations.append(jobs.c.metadata["seeding_claim_id"].astext == identity)
    if command:
        correlations += [jobs.c.metadata["dispatch_command_id"].astext == command["id"],
                         jobs.c.metadata["dispatch_claim_token"].astext == identity]
    observations = _rows(connection, jobs, (or_(*correlations),))
    relevant = []
    for job in observations:
        meta = job["metadata"]
        if type(meta) is not dict:
            if job["status"] == "RUNNING":
                refuse("Malformed RUNNING observation")
            continue
        related = identity is not None and (meta.get("seeding_claim_id") == identity or
                  command is not None and (meta.get("dispatch_command_id") == command["id"] or meta.get("dispatch_claim_token") == identity))
        if related:
            genuine_refusal = (command is not None and job["status"] == "FAILED" and
                               meta.get("ownership_refused") is True and "seeding_claim_id" not in meta)
            if (job["domain"] != domain or not genuine_refusal and meta.get("seeding_claim_id") != identity or
                    command is None and any(k in meta for k in ("dispatch_command_id", "dispatch_claim_token")) or
                    command is not None and (meta.get("dispatch_command_id") != command["id"] or
                    meta.get("dispatch_claim_token") != identity or job["dry_run"] != command["dry_run"])):
                refuse("Observation correlation mismatch")
            relevant.append(job)
        elif job["status"] == "RUNNING":
            if identity is not None or any(k in meta for k in
                    ("seeding_claim_id", "dispatch_command_id", "dispatch_claim_token")):
                refuse("Unreconciled or malformed RUNNING owner tag")
            relevant.append(job)
    if identity is None and [j["id"] for j in relevant] != selected["legacy_job_ids"]:
        refuse("Exact legacy RUNNING observation set changed")
    if lock:
        # Existing runtime order: worker -> selected domain -> command -> claim.
        for table, condition in (
                (EtlDispatchWorker.__table__, EtlDispatchWorker.id == 1),
                (EtlDispatchDomain.__table__, EtlDispatchDomain.domain == domain),
                (EtlDispatchCommand.__table__, EtlDispatchCommand.id == UUID(command["id"]) if command else text("false")),
                (SeedingDomainClaim.__table__, SeedingDomainClaim.id == UUID(identity) if identity else text("false"))):
            if present[table.name]:
                connection.execute(select(table).where(condition).with_for_update()).all()
        connection.execute(select(jobs).where(jobs.c.id.in_([j["id"] for j in relevant])).with_for_update()).all()
    return {"worker": worker, "dispatch": dispatch, "command": command, "claim": ownership,
            "observations": relevant, "schema_presence": present}


def _backend(connection):
    return dict(connection.execute(text("SELECT pg_backend_pid() AS pid, backend_start::text FROM pg_stat_activity WHERE pid=pg_backend_pid()")).mappings().one())


def generator_hash():
    return sha256(Path(__file__).read_bytes()).hexdigest()


def _record(evidence, policy, target, now, plan_hash):
    return {"version": VERSION, "who": evidence["who"], "why": evidence["why"],
            "effects": evidence["effects"], "evidence_sha256": digest(evidence),
            "plan_sha256": plan_hash, "policy_sha256": digest(policy), "target": target,
            "selector": evidence["selector"], "reconciled_at": now.isoformat()}


def _record_text(record):
    # Hash/signature canonicalization remains ASCII and unchanged. Durable text
    # preserves Unicode instead of multiplying each character into six escapes.
    value = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return meaningful(value, 4000)


def _effects(connection):
    """Exact, bounded hashes of ALL public tables, including out-of-seam effects.

    Return only counts/hashes. No financial/application row content is exported.
    Admission must be fenced; apply additionally freezes these tables. A changed
    row after the signed census invalidates the evidence, even for the same claim.
    """
    tables = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars().all()
    quote = connection.dialect.identifier_preparer.quote
    result = {}
    for table in tables:
        row = connection.execute(text("""SELECT count(*) AS rows,
            encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') AS sha256
            FROM (SELECT encode(sha256(convert_to(to_jsonb(r)::text,'UTF8')),'hex') AS h
            FROM public.""" + quote(table) + " AS r LIMIT 100001) AS hashes")).mappings().one()
        if row["rows"] > 100000:
            refuse("Effects census exceeds bound; require separately reviewed procedure")
        result[table] = dict(row)
    return result


def _context(connection, selected, snapshot=None):
    return {"target": target_identity(connection), "selector": selected,
            "snapshot_sha256": digest(snapshot if snapshot is not None else _snapshot(connection, selected)),
            "effects": _effects(connection)}


@contextmanager
def _read_only(connection):
    if connection.in_transaction():
        refuse("Clean retained connection required")
    transaction = connection.begin()
    try:
        connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        connection.execute(text("SET LOCAL statement_timeout = '10s'"))
        if connection.scalar(text("SHOW transaction_read_only")) != "on":
            refuse("Read-only plan transaction unverified")
        yield
    finally:
        transaction.rollback()


def inspect_context(connection, selected):
    """Collect exact fenced census BEFORE operators attest to its effects."""
    with _read_only(connection):
        target_identity(connection)
        _maintenance(connection)
        context = _context(connection, selected)
        return {"context": context, "context_sha256": digest(context),
                "observed_at": connection.scalar(text("SELECT clock_timestamp()")).isoformat()}


def make_plan(connection, policy, evidence):
    with _read_only(connection):
        target = target_identity(connection)
        now = connection.scalar(text("SELECT clock_timestamp()"))
        verify_evidence(policy, evidence, target, now)
        _maintenance(connection)
        snapshot = _snapshot(connection, evidence["selector"])
        context_sha256 = digest(_context(connection, evidence["selector"], snapshot))
        if evidence["context_sha256"] != context_sha256:
            refuse("Signed effects census differs from current database context")
        if snapshot["claim"]:
            _record_text(_record(evidence, policy, target, now, "0" * 64))
        result = {"version": VERSION, "generator_sha256": generator_hash(), "target": target,
                  "selector": evidence["selector"], "snapshot": snapshot,
                  "snapshot_sha256": digest(snapshot), "evidence_sha256": digest(evidence),
                  "policy_sha256": digest(policy), "context_sha256": context_sha256,
                  "planned_at": now.isoformat(), "backend": _backend(connection)}
        canonical(result)
        # Ending this read-only transaction changes no ownership. The retained
        # connection stays open for an explicit later apply request.
    return result


def apply_plan(connection, policy, evidence, plan):
    canonical(plan)
    shape(plan, ("version", "generator_sha256", "target", "selector", "snapshot", "snapshot_sha256",
                 "evidence_sha256", "policy_sha256", "context_sha256", "planned_at", "backend"))
    if connection.in_transaction():
        refuse("Clean retained connection required")
    with connection.begin():
        connection.execute(text("SET LOCAL lock_timeout = '2s'"))
        connection.execute(text("SET LOCAL statement_timeout = '10s'"))
        target = target_identity(connection)
        now = connection.scalar(text("SELECT clock_timestamp()"))
        verify_evidence(policy, evidence, target, now)
        if (type(plan["version"]) is not int or plan["version"] != VERSION or plan["generator_sha256"] != generator_hash() or
                plan["target"] != target or plan["selector"] != evidence["selector"] or
                plan["backend"] != _backend(connection) or not now - EVIDENCE_VALIDITY <= timestamp(plan["planned_at"]) <= now or
                plan["evidence_sha256"] != digest(evidence) or plan["policy_sha256"] != digest(policy) or
                plan["snapshot_sha256"] != digest(plan["snapshot"])):
            refuse("Stale or mismatched plan")
        _maintenance(connection, lock=True)
        key = int.from_bytes(sha256(("seeding:" + evidence["selector"]["domain"]).encode()).digest()[:8], "big") & ((1 << 63) - 1)
        if connection.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}) is not True:
            refuse("Domain execution still owns continuity lock")
        _continuity(connection, key)
        # All public effect/observation tables are frozen, even writers outside
        # native ownership. NOWAIT refuses uncertainty rather than waiting it out.
        tables = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars().all()
        quote = connection.dialect.identifier_preparer.quote
        for table in tables:
            connection.execute(text("LOCK TABLE public." + quote(table) + " IN SHARE ROW EXCLUSIVE MODE NOWAIT"))
        snapshot = _snapshot(connection, evidence["selector"], lock=True)
        if snapshot != plan["snapshot"]:
            refuse("Durable owner, generation or observation changed since plan")
        if plan["context_sha256"] != evidence["context_sha256"] or digest(_context(connection, evidence["selector"], snapshot)) != evidence["context_sha256"]:
            refuse("Effects changed since signed census; new operator review required")
        _maintenance(connection, lock=True)
        # Revalidate evidence's time window after acquiring locks, in this backend.
        now = connection.scalar(text("SELECT clock_timestamp()"))
        verify_evidence(policy, evidence, target, now)
        record = _record(evidence, policy, target, now, digest(plan))
        record_text = _record_text(record) if snapshot["claim"] else None
        audit_id = connection.scalar(AdminAuditLog.__table__.insert().values(
            actor_id=evidence["who"], action="seeding.reconcile", target_type="seeding_domain",
            target_id=evidence["selector"]["claim_id"], payload=record,
            created_at=now.replace(tzinfo=None)).returning(AdminAuditLog.__table__.c.id))
        if type(audit_id) is not int or audit_id <= 0:
            refuse("Reconciliation audit was not recorded")
        ownership, command = snapshot["claim"], snapshot["command"]
        if ownership:
            released = connection.execute(SeedingDomainClaim.__table__.update().where(
                SeedingDomainClaim.__table__.c.id == UUID(ownership["id"]),
                SeedingDomainClaim.__table__.c.domain == ownership["domain"],
                SeedingDomainClaim.__table__.c.released_at.is_(None)).values(
                    released_at=now, reconciled_by=evidence["who"], reconciliation=record_text))
            if released.rowcount != 1:
                refuse("Exact retained claim was not released")
        if command:
            if command["status"] == "running":
                interrupted = connection.execute(EtlDispatchCommand.__table__.update().where(
                    EtlDispatchCommand.__table__.c.id == UUID(command["id"]),
                    EtlDispatchCommand.__table__.c.claim_token == UUID(command["claim_token"]),
                    EtlDispatchCommand.__table__.c.status == "running").values(
                    status="interrupted", outcome="execution_unverified", finished_at=now, updated_at=now,
                    version=command["version"] + 1))
                if interrupted.rowcount != 1:
                    refuse("Exact retained command was not interrupted")
            cleared = connection.execute(EtlDispatchDomain.__table__.update().where(
                EtlDispatchDomain.__table__.c.domain == ownership["domain"],
                EtlDispatchDomain.__table__.c.command_id == UUID(command["id"]),
                EtlDispatchDomain.__table__.c.claim_token == UUID(ownership["id"])).values(command_id=None, claim_token=None))
            if cleared.rowcount != 1:
                refuse("Exact retained dispatch domain was not cleared")
        for job in snapshot["observations"]:
            if job["status"] != "RUNNING":
                continue
            if type(job["errors"]) is not list:
                refuse("Malformed observation errors; effects require investigation")
            meta = dict(job["metadata"])
            if "operator_reconciliation" in meta:
                refuse("Observation already contains reconciliation evidence")
            meta["operator_reconciliation"] = {"audit_id": audit_id, "evidence_sha256": digest(evidence), "who": evidence["who"]}
            updated = connection.execute(IngestionJob.__table__.update().where(
                IngestionJob.__table__.c.id == job["id"], IngestionJob.__table__.c.status == "RUNNING").values(
                status="FAILED", finished_at=now.replace(tzinfo=None),
                errors=job["errors"] + [f"Operator reconciliation audit {audit_id}: execution remains unverified"], metadata=meta))
            if updated.rowcount != 1:
                refuse("Exact retained observation was not reconciled")
        verify_evidence(policy, evidence, target, connection.scalar(text("SELECT clock_timestamp()")))
        _maintenance(connection, lock=True)
        _continuity(connection, key)
    # Report success only after this same admission/domain-lock transaction commits.
    # A connection/commit error propagates; never retry an ambiguous release.
    return {"status": "applied", "audit_id": audit_id, "record": record}


def _continuity(connection, key):
    if connection.scalar(text("""SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype='advisory'
            AND pid=pg_backend_pid() AND granted AND classid=:high AND objid=:low AND objsubid=1)"""),
            {"high": key >> 32, "low": key & 0xffffffff}) is not True:
        refuse("Committing backend transaction does not hold the domain lock")

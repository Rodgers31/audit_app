"""Read-only rollout observation and an immutable baseline migration plan.

This entry has no migration, fencing, reconciliation or activation operation.
Catalog observations are snapshots, never a certificate of quiescence.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[2]
BASELINE_SOURCE = "dfd18032b6f38d57bfaa6f66d0feac218189f54c"
BASELINE_TARGET = "e602b11a0001"
BASELINE_CORPUS_SHA256 = "6dd02de2b7357f6f28708e4b46276eb774ec871a21048beff2eb84212617625f"
TABLES = ("ingestion_jobs", "admin_audit_log", "etl_dispatch_commands",
          "etl_dispatch_worker", "etl_dispatch_domains", "seeding_domain_claims")
LIBPQ = ("PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD",
         "PGPASSFILE", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS", "PGSSLMODE",
         "PGSSLROOTCERT", "PGSSLCERT", "PGSSLKEY", "PGTARGETSESSIONATTRS")


class Refused(RuntimeError):
    """Fixed diagnostics; never interpolate database errors or credentials."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def migration_chain(root=ROOT):
    revisions = {}
    for path in sorted((root / "backend/alembic/versions").glob("*.py")):
        if path.is_symlink():
            raise Refused("migration_link")
        fields = {}
        try:
            for node in ast.parse(path.read_bytes()).body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    name = node.targets[0]
                    if isinstance(name, ast.Name) and name.id in ("revision", "down_revision"):
                        if name.id in fields:
                            raise Refused("migration_identity")
                        fields[name.id] = ast.literal_eval(node.value)
        except (SyntaxError, ValueError, TypeError):
            raise Refused("migration_identity") from None
        if "revision" in fields:
            revision = fields["revision"]
            parent = fields.get("down_revision")
            if (type(revision) is not str or not revision or revision in revisions
                    or "down_revision" not in fields
                    or (parent is not None and type(parent) is not str)):
                raise Refused("migration_identity")
            revisions[revision] = {"revision": revision, "parent": fields["down_revision"],
                "path": str(path.relative_to(root)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    chain = []
    cursor = BASELINE_TARGET
    while cursor is not None:
        if cursor not in revisions or cursor in {x["revision"] for x in chain} or len(chain) >= 64:
            raise Refused("baseline_ancestry")
        entry = revisions[cursor]
        if entry["parent"] is not None and type(entry["parent"]) is not str:
            raise Refused("baseline_parent")
        chain.append(entry)
        cursor = entry["parent"]
    chain.reverse()
    if digest(chain) != BASELINE_CORPUS_SHA256:
        raise Refused("immutable_baseline_changed")
    return chain


def endpoint_transport(parsed):
    mode = parsed.query.get("sslmode", "require")
    if type(mode) is not str or mode not in ("require", "verify-ca", "verify-full"):
        raise Refused("postgres_transport_required")
    # The existing owned test helper exports a passwordless literal loopback
    # profile. It is distinct from TLS endpoints and cannot downgrade one.
    if (not parsed.query and parsed.host == "127.0.0.1" and parsed.port in (55496, 55560)
            and parsed.username == "postgres" and parsed.password is None
            and re.fullmatch(r"batch9-(?:reconciliation|review-592)-[0-9a-f]{32}", parsed.database or "")):
        return "disable"
    return mode


def endpoint_fingerprint(url):
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import ArgumentError
    try:
        parsed = make_url(url)
        query = parse_qsl(urlsplit(url).query, keep_blank_values=True)
        if any(k == 'sslmode' and not v for k, v in query):
            raise Refused('postgres_transport_required')
        if (parsed.drivername not in ("postgresql", "postgresql+psycopg2") or
                not parsed.host or not parsed.username or not parsed.database or
                set(parsed.query) - {"sslmode"}):
            raise Refused("postgres_endpoint_required")
        return digest({"host": parsed.host.lower(), "port": parsed.port or 5432,
                       "database": parsed.database, "role": parsed.username,
                       "sslmode": endpoint_transport(parsed)})
    except (ArgumentError, ValueError, TypeError):
        raise Refused("postgres_endpoint_required") from None


def observe(url, expected_endpoint):
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    from sqlalchemy.exc import SQLAlchemyError
    if type(expected_endpoint) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected_endpoint):
        raise Refused("expected_endpoint_required")
    if any(os.environ.get(k) for k in LIBPQ):
        raise Refused("ambient_libpq_refused")
    if endpoint_fingerprint(url) != expected_endpoint:
        raise Refused("endpoint_mismatch")
    from sqlalchemy.engine import make_url
    parsed = make_url(url).set(drivername="postgresql+psycopg2")
    mode = endpoint_transport(parsed)
    parsed = parsed.update_query_dict({"sslmode": mode})
    engine = create_engine(parsed, poolclass=NullPool,
        connect_args={"connect_timeout": 10, "options": "-c default_transaction_read_only=on"})
    try:
        with engine.connect() as connection:
            connection.execute(text("BEGIN READ ONLY ISOLATION LEVEL REPEATABLE READ"))
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            connection.execute(text("SET LOCAL lock_timeout = '2s'"))
            connection.execute(text("SET LOCAL search_path = pg_catalog, public"))
            encrypted = connection.scalar(text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()"))
            if type(encrypted) is not bool or (mode != "disable" and encrypted is not True):
                raise Refused("postgres_transport_unverified")
            if connection.scalar(text("SHOW transaction_read_only")) != "on":
                raise Refused("read_only_unverified")
            identity = dict(connection.execute(text("""SELECT d.oid::bigint AS database_oid,
                current_database() AS database, current_user AS role, r.rolsuper AS superuser,
                r.rolbypassrls AS bypass_rls, d.datallowconn AS admission_open,
                pg_has_role(current_user,'pg_read_all_stats','MEMBER') AS full_stats,
                current_setting('server_version') AS server_version,
                pg_backend_pid() AS observer_pid
                FROM pg_database d JOIN pg_roles r ON r.rolname=current_user
                WHERE d.datname=current_database()""")).mappings().one())
            system_id = None
            try:
                with connection.begin_nested():
                    system_id = connection.scalar(text("SELECT system_identifier::text FROM pg_control_system()"))
            except SQLAlchemyError as error:
                # Permission denial is an explicit unavailable identity. Other
                # failures abort; they must not silently replace an identity.
                if getattr(error.orig, "pgcode", None) != "42501":
                    raise
            identity["system_identifier"] = system_id
            identity["cluster_identity_available"] = type(system_id) is str and bool(system_id)
            present = connection.execute(text("""SELECT c.relname, c.relrowsecurity
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relkind IN ('r','p')
                AND c.relname = ANY(:names) ORDER BY c.relname"""), {"names": list(TABLES)}).mappings().all()
            schema = {}
            for row in present:
                name = row["relname"]
                schema[name] = {"rls": row["relrowsecurity"], "columns": [dict(x) for x in
                    connection.execute(text("""SELECT a.attname AS name, format_type(a.atttypid,a.atttypmod) AS type,
                        a.attnotnull AS not_null FROM pg_attribute a
                        WHERE a.attrelid=to_regclass(:name) AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum"""),
                        {"name": "public." + name}).mappings()]}
            if connection.scalar(text("SELECT to_regclass('public.alembic_version')")) is None:
                revisions = []
            else:
                revisions = connection.execute(text("SELECT version_num FROM public.alembic_version ORDER BY version_num LIMIT 65")).scalars().all()
            jobs = []
            if "ingestion_jobs" in schema:
                jobs = [dict(x) for x in connection.execute(text("""SELECT id, domain, status::text,
                    metadata ? 'seeding_claim_id' AS claim_tag_present,
                    metadata ? 'dispatch_command_id' AS command_tag_present
                    FROM public.ingestion_jobs WHERE status::text='RUNNING' ORDER BY id LIMIT 1001""")).mappings()]
                if len(jobs) > 1000:
                    raise Refused("running_observation_bound")
            sessions = [dict(x) for x in connection.execute(text("""SELECT pid, backend_type, state,
                usename AS role FROM pg_stat_activity
                WHERE datid=(SELECT oid FROM pg_database WHERE datname=current_database())
                AND pid<>pg_backend_pid() ORDER BY pid LIMIT 201""")).mappings()]
            if len(sessions) > 200:
                raise Refused("session_bound")
            prepared = connection.scalar(text("SELECT count(*) FROM pg_prepared_xacts WHERE database=current_database()"))
            roles = [dict(x) for x in connection.execute(text("""SELECT rolname AS name, rolsuper AS superuser,
                rolbypassrls AS bypass_rls, rolcanlogin AS login FROM pg_roles ORDER BY rolname LIMIT 201""")).mappings()]
            if len(roles) > 200:
                raise Refused("role_bound")
            result = {"version": 1, "kind": "database_observation", "observed_at": datetime.now(timezone.utc).isoformat(),
                "read_only": True, "endpoint_sha256": expected_endpoint, "identity": identity,
                "revisions": list(revisions), "schema": schema, "running_observations": jobs,
                "other_sessions": sessions, "prepared_transactions": prepared, "roles": roles,
                "connection_mode": "unverified_from_catalogs", "sslmode": mode,
                "transport_encrypted": encrypted, "production_ready": False}
            connection.rollback()
            return result
    except SQLAlchemyError:
        raise Refused("database_observation_unavailable") from None
    finally:
        engine.dispose()


def validate_observation(value):
    def require(condition):
        if not condition:
            raise Refused("observation_shape")

    def label(item, nullable=False):
        return (nullable and item is None) or (type(item) is str and 0 < len(item) <= 512)

    def integer(item, minimum=0):
        return type(item) is int and minimum <= item <= 2**63 - 1

    def keys(item, expected):
        require(type(item) is dict and set(item) == set(expected.split()))

    require(type(value) is dict and type(value.get("version")) is int and value["version"] == 1)
    expected = set("version kind observed_at read_only production_ready endpoint_sha256 identity revisions schema running_observations other_sessions prepared_transactions roles connection_mode sslmode transport_encrypted".split())
    published = {"generated_by", "generator_sha256"}
    require(set(value) in (expected, expected | published))
    if set(value) == expected | published:
        require(value["generated_by"] == "backend/scripts/batch12_rollout.py" and
                value["generator_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    require(value.get("kind") == "database_observation" and value.get("read_only") is True)
    require(value.get("production_ready") is False and value.get("production_execution_authorized", False) is False)
    require(type(value.get("endpoint_sha256")) is str and re.fullmatch(r"[0-9a-f]{64}", value["endpoint_sha256"]))
    require(type(value.get("observed_at")) is str)
    try:
        observed = datetime.fromisoformat(value["observed_at"])
        age = (datetime.now(timezone.utc) - observed).total_seconds()
    except (ValueError, TypeError):
        raise Refused("observation_time") from None
    require(observed.utcoffset() is not None and observed.utcoffset().total_seconds() == 0 and -30 <= age <= 300)
    require(value.get("connection_mode") == "unverified_from_catalogs")
    require(value.get("sslmode") in ("disable", "require", "verify-ca", "verify-full")
            and type(value.get("transport_encrypted")) is bool
            and (value["sslmode"] == "disable" or value["transport_encrypted"] is True))
    identity = value.get("identity")
    keys(identity, "database role server_version database_oid observer_pid superuser bypass_rls admission_open full_stats cluster_identity_available system_identifier")
    for key in ("database", "role", "server_version"):
        require(label(identity.get(key)))
    for key in ("database_oid", "observer_pid"):
        require(integer(identity.get(key), 1))
    for key in ("superuser", "bypass_rls", "admission_open", "full_stats", "cluster_identity_available"):
        require(type(identity.get(key)) is bool)
    system_id = identity.get("system_identifier")
    require((identity["cluster_identity_available"] is False and system_id is None) or
            (identity["cluster_identity_available"] is True and type(system_id) is str and
             re.fullmatch(r"[0-9]{1,20}", system_id)))
    revisions = value.get("revisions")
    require(type(revisions) is list and len(revisions) <= 64 and
            all(type(x) is str and re.fullmatch(r"[a-zA-Z0-9_]{1,64}", x) for x in revisions) and
            len(set(revisions)) == len(revisions))
    schema = value.get("schema")
    require(type(schema) is dict and not set(schema) - set(TABLES))
    for table in schema.values():
        keys(table, "rls columns")
        require(type(table.get("rls")) is bool)
        columns = table.get("columns")
        require(type(columns) is list and 0 < len(columns) <= 200)
        for column in columns:
            keys(column, "name type not_null")
            require(label(column.get("name")) and
                    label(column.get("type")) and type(column.get("not_null")) is bool)
        require(len({x["name"] for x in columns}) == len(columns))
    jobs = value.get("running_observations")
    require(type(jobs) is list and len(jobs) <= 1000)
    for job in jobs:
        keys(job, "id domain status claim_tag_present command_tag_present")
        require(integer(job.get("id"), 1) and label(job.get("domain")) and
                job.get("status") == "RUNNING" and type(job.get("claim_tag_present")) is bool and
                type(job.get("command_tag_present")) is bool)
    require(len({x["id"] for x in jobs}) == len(jobs))
    sessions = value.get("other_sessions")
    require(type(sessions) is list and len(sessions) <= 200)
    for session in sessions:
        keys(session, "pid backend_type state role")
        require(integer(session.get("pid"), 1) and
                all(label(session.get(key), nullable=True) for key in ("backend_type", "state", "role")))
    require(len({x["pid"] for x in sessions}) == len(sessions))
    require(integer(value.get("prepared_transactions")))
    roles = value.get("roles")
    require(type(roles) is list and 0 < len(roles) <= 200)
    for role in roles:
        keys(role, "name superuser bypass_rls login")
        require(label(role.get("name")) and
                all(type(role.get(key)) is bool for key in ("superuser", "bypass_rls", "login")))
    require(len({x["name"] for x in roles}) == len(roles))
    current = [x for x in roles if x["name"] == identity["role"]]
    require(len(current) == 1 and current[0]["superuser"] == identity["superuser"] and
            current[0]["bypass_rls"] == identity["bypass_rls"])
    digest(value)


def build_plan(observation, root=ROOT):
    validate_observation(observation)
    revisions = observation.get("revisions")
    if type(revisions) is not list or len(revisions) != 1 or type(revisions[0]) is not str:
        raise Refused("one_observed_revision_required")
    return plan_for_revision(revisions[0], digest(observation), root)


def plan_for_revision(revision, observation_sha256, root=ROOT):
    chain = migration_chain(root)
    ordered = [x["revision"] for x in chain]
    if revision not in ordered:
        raise Refused("observed_revision_outside_baseline")
    pending = chain[ordered.index(revision) + 1:]
    return {"version": 1, "kind": "baseline_plan_only", "observation_sha256": observation_sha256,
        "baseline_source": BASELINE_SOURCE, "target": BASELINE_TARGET,
        "migration_corpus_sha256": BASELINE_CORPUS_SHA256,
        "from_revision": revision, "ordered_migrations": pending,
        "migration_argv": [sys.executable, "-m", "alembic", "upgrade", BASELINE_TARGET],
        "production_execution_authorized": False, "production_ready": False,
        "required_before_migration": ["independent target/secret identity", "reviewed exact source/image/runtime",
            "verified backup restore", "every writer and restart fence", "fenced separate migration connection"],
        "required_before_reconciliation": ["retained direct superuser session", "provider connection admission fence",
            "no other sessions or prepared transactions", "private independently provisioned policy/keys"],
        "reconciliation": "retained direct operator inspect/sign/plan/apply; exact effects and durable readback",
        "audit_storage_release": "separate exact frozen reviewed head; this plan excludes future descendants",
        "abort": "hold all fences on refusal, lost continuity, changed effects or unknown commit; investigate durable state"}


def validate_receipt(value):
    if type(value) is not dict or value.get("production_ready") is not False or value.get("production_execution_authorized", False) is not False:
        raise Refused("receipt_kind_or_authority")
    if value.get("kind") == "database_observation":
        validate_observation(value)
    elif value.get("kind") == "baseline_plan_only":
        fingerprint = value.get("observation_sha256")
        if type(fingerprint) is not str or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise Refused("plan_observation_identity")
        expected = plan_for_revision(value.get("from_revision"), fingerprint)
        if set(value) == set(expected) | {"generated_by", "generator_sha256"}:
            expected = {**expected, "generated_by": "backend/scripts/batch12_rollout.py",
                "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        if value != expected:
            raise Refused("plan_shape")
    else:
        raise Refused("receipt_kind_or_authority")


@contextmanager
def output_directory(path):
    # Hold the validated parent inode across observation/publication. A pathname
    # check followed by pathname creation is vulnerable to a parent-link swap.
    path = Path(path)
    if not path.is_absolute() or path.name in ("", ".", "..") or ".." in path.parts:
        raise Refused("absolute_output_required")
    parent = path.parent
    if parent.is_relative_to(ROOT.resolve()) or parent.resolve() != parent:
        raise Refused("fresh_external_output_required")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parent.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        try:
            os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise Refused("fresh_external_output_required")
        yield fd
    except OSError:
        raise Refused("fresh_external_output_required") from None
    finally:
        os.close(fd)


def write_new(path, value):
    validate_receipt(value)
    with output_directory(path) as fd:
        return _write_anchored(path, value, fd)


def _write_anchored(path, value, directory_fd):
    validate_receipt(value)
    path = Path(path)
    receipt = {**value, "generated_by": "backend/scripts/batch12_rollout.py",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    raw = json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n"
    fd = os.open(path.name, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, "w+") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
        stream.seek(0)
        if stream.read() != raw:
            raise Refused("receipt_readback")
        if os.fstat(stream.fileno()).st_ino != os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False).st_ino:
            raise Refused("receipt_replaced")
        if path.parent.resolve() != path.parent or os.stat(path.parent).st_ino != os.fstat(directory_fd).st_ino:
            raise Refused("output_parent_changed")
    os.fsync(directory_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    obs = sub.add_parser("observe")
    obs.add_argument("--expected-endpoint-sha256", required=True)
    obs.add_argument("--out", type=Path, required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--observation", type=Path, required=True)
    plan.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        with output_directory(args.out) as fd:
            if args.action == "observe":
                value = observe(os.environ["BATCH12_ROLLOUT_DATABASE_URL"], args.expected_endpoint_sha256)
            else:
                value = build_plan(json.loads(args.observation.read_text()))
            _write_anchored(args.out, value, fd)
        print(json.dumps({"status": "observed" if args.action == "observe" else "planned",
                          "production_ready": False, "target": BASELINE_TARGET}))
        return 0
    except (Refused, KeyError, OSError, ValueError, TypeError):
        print(json.dumps({"status": "refused", "production_ready": False,
                          "reason": "rollout_input_or_observation_unverified"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

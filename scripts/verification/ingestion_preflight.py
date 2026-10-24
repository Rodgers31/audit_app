#!/usr/bin/env python3
"""Bounded metadata inspection. Never ingestion, custody certification or write admission."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
from urllib.parse import unquote, urlsplit

# A read-only tool must not change the inspected source on ordinary imports.
sys.dont_write_bytecode = True
if __package__:
    from . import evaluate_social_operating_budget as budget
    from .social_operating_collect import IDENTITY_SQL
    from . import ingestion_preflight_worker as worker
else:
    import evaluate_social_operating_budget as budget
    from social_operating_collect import IDENTITY_SQL
    import ingestion_preflight_worker as worker

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "docs/admin/batch66/preflight-admission.json"
MAX_BYTES = 65_536
MAX_ROWS = 256
MAX_REQUESTS = 24  # Includes BEGIN/SET; one final rollback is separately bounded.
RUN_SECONDS = 30
OPTIONS = (
    "-c default_transaction_read_only=on -c statement_timeout=2000 "
    "-c lock_timeout=500 -c idle_in_transaction_session_timeout=3000 "
    "-c idle_session_timeout=5000 -c search_path=pg_catalog "
    "-c row_security=off -c max_parallel_workers_per_gather=0 -c work_mem=64kB"
)
TABLES = (
    "alembic_version",
    "etl_dispatch_commands",
    "etl_dispatch_domains",
    "etl_dispatch_worker",
    "ingestion_jobs",
    "seeding_domain_claims",
)
SOURCE_FILES = (
    "backend/models.py",
    "backend/seeding/cli.py",
    "backend/seeding/config.py",
    "backend/seeding/registries.py",
    "backend/services/receipt_manifest.py",
    "scripts/verification/evaluate_social_operating_budget.py",
    "scripts/verification/social_operating_collect.py",
    "scripts/verification/ingestion_preflight.py",
    "scripts/verification/ingestion_preflight_worker.py",
    "docs/admin/batch66/preflight-driver-requirements.txt",
)
SCHEMA_SQL = """
SELECT c.relname, c.relkind, c.relrowsecurity, c.relforcerowsecurity,
       a.attnum, a.attname, a.atttypid::bigint, a.atttypmod, a.attnotnull,
       c.relowner::bigint
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
WHERE n.nspname='public' AND c.relname=ANY(%s)
  AND a.attnum>0 AND NOT a.attisdropped
ORDER BY c.relname,a.attnum LIMIT 257
"""
GUARDS_SQL = """SELECT
 current_setting('default_transaction_read_only'), current_setting('transaction_read_only'),
 current_setting('transaction_isolation'), current_setting('statement_timeout'),
 current_setting('lock_timeout'), current_setting('idle_in_transaction_session_timeout'),
 current_setting('row_security'), current_setting('search_path'),
 pg_catalog.pg_has_role(current_user,'pg_read_all_stats','MEMBER'),
 (SELECT ssl FROM pg_catalog.pg_stat_ssl WHERE pid=pg_catalog.pg_backend_pid()),
 (SELECT oid::bigint FROM pg_catalog.pg_roles WHERE rolname=current_user),
 current_setting('max_parallel_workers_per_gather'), current_setting('work_mem'),
 current_setting('idle_session_timeout')"""
REVISION_SQL = (
    "SELECT pg_catalog.left(version_num::text,33) FROM public.alembic_version LIMIT 2"
)
# Only predicates/booleans, never private records, query text, tokens or credentials.
CHECKS = {
    "retained_claim": "SELECT EXISTS(SELECT 1 FROM public.seeding_domain_claims WHERE released_at IS NULL LIMIT 1)",
    "retained_dispatch": "SELECT EXISTS(SELECT 1 FROM public.etl_dispatch_domains WHERE command_id IS NOT NULL OR claim_token IS NOT NULL OR ready IS DISTINCT FROM FALSE LIMIT 1)",
    "worker_ready": "SELECT EXISTS(SELECT 1 FROM public.etl_dispatch_worker WHERE ready IS DISTINCT FROM FALSE LIMIT 1)",
    "nonterminal_or_unknown_command": "SELECT EXISTS(SELECT 1 FROM public.etl_dispatch_commands WHERE status IS NULL OR status NOT IN ('completed','failed') LIMIT 1)",
    "nonterminal_or_unknown_job": "SELECT EXISTS(SELECT 1 FROM public.ingestion_jobs WHERE status IS NULL OR status::text NOT IN ('COMPLETED','COMPLETED_WITH_ERRORS','FAILED') LIMIT 1)",
    # Active SELECT also refuses: query classification cannot prove a writer idle.
    "other_active_session": "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_stat_activity WHERE datid=(SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database()) AND pid<>pg_catalog.pg_backend_pid() AND backend_type='client backend' AND state IS DISTINCT FROM 'idle' LIMIT 1)",
    "prepared_transaction": "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_prepared_xacts WHERE database=current_database() LIMIT 1)",
}
_RUN_LOCK = threading.Lock()
_OWNED_DEADLINE = False
SESSION_COMMANDS = (
    "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY",
    "SET LOCAL statement_timeout='2s'",
    "SET LOCAL lock_timeout='500ms'",
    "SET LOCAL idle_in_transaction_session_timeout='3s'",
    "SET LOCAL idle_session_timeout='5s'",
    "SET LOCAL row_security=off",
    "SET LOCAL search_path=pg_catalog",
    "SET LOCAL max_parallel_workers_per_gather=0",
    "SET LOCAL work_mem='64kB'",
)


def require(condition, code):
    budget.require(condition, code)


def raw_file(path, limit=MAX_BYTES):
    """No links in any component, no devices/FIFOs, no unbounded reads."""
    require(isinstance(path, Path) and path.is_absolute(), "ABSOLUTE_PATH_REQUIRED")
    for part in (path, *path.parents):
        require(not part.is_symlink(), "FILE_LINK_REFUSED")
    with os.fdopen(
        os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW), "rb"
    ) as stream:
        info = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
            "REGULAR_SINGLE_FILE_REQUIRED",
        )
        require(0 < info.st_size <= limit, "FILE_SIZE_REFUSED")
        raw = stream.read(limit + 1)
    require(0 < len(raw) <= limit, "FILE_SIZE_REFUSED")
    return raw


def load(path, expected_sha256=None, *, receipt=None):
    raw = raw_file(path)
    if receipt is not None:
        receipt["policy_raw_sha256"] = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        budget.digest(expected_sha256)
        require(
            hashlib.sha256(raw).hexdigest() == expected_sha256,
            "ADMISSION_BYTES_MISMATCH",
        )
    return json.loads(
        raw,
        object_pairs_hook=budget._pairs,
        parse_constant=lambda _: require(False, "NONFINITE_JSON"),
    )


def check_config(config):
    require(type(config) is dict and len(config) == 9, "INVALID_SHAPE")
    budget.shape(
        config,
        {
            "version",
            "mode",
            "accepted",
            "execution_head",
            "source_files",
            "database",
            "schema_sha256",
            "revision",
            "receipt_authority",
        },
    )
    require(
        type(config["version"]) is int and config["version"] == 1,
        "CONFIG_VERSION_REFUSED",
    )
    require(
        type(config["mode"]) is str and config["mode"] in ("owned-local", "hosted"),
        "MODE_REFUSED",
    )
    require(
        type(config["accepted"]) is bool and config["accepted"], "ADMISSION_DISABLED"
    )
    budget.digest(config["execution_head"], 40)
    budget.shape(config["source_files"], SOURCE_FILES)
    for digest in config["source_files"].values():
        budget.digest(digest)
    budget.digest(config["schema_sha256"])
    require(
        type(config["revision"]) is str
        and re.fullmatch("[a-z0-9]{8,32}", config["revision"]),
        "REVISION_REQUIRED",
    )
    database = budget.shape(
        config["database"], {"host", "port", "name", "oid", "role", "role_oid", "tls"}
    )
    for key in ("name", "role"):
        require(
            type(database[key]) is str
            and re.fullmatch("[a-z][a-z0-9_]{0,62}", database[key]),
            "IDENTITY_REQUIRED",
        )
    for key in ("oid", "role_oid"):
        require(0 < budget.integer(database[key], 2**32 - 1), "IDENTITY_REQUIRED")
    if config["mode"] == "owned-local":
        require(
            database["host"] == "127.0.0.1"
            and type(database["port"]) is int
            and database["port"] == 56972
            and database["tls"] == "disable"
            and database["name"].startswith("b66_preflight_"),
            "OWNED_FIXTURE_REQUIRED",
        )
    else:
        require(
            type(database["host"]) is str
            and re.fullmatch(r"db\.[a-z]{20}\.supabase\.co", database["host"])
            and type(database["port"]) is int
            and database["port"] == 5432
            and database["tls"] == "verify-full",
            "HOSTED_TLS_IDENTITY_REQUIRED",
        )
    authority = budget.shape(config["receipt_authority"], {"state", "identity_sha256"})
    require(
        type(authority["state"]) is str and authority["state"] == "accepted",
        "RECEIPT_AUTHORITY_UNACCEPTED",
    )
    budget.digest(authority["identity_sha256"])
    require(len(budget.canonical(config)) <= MAX_BYTES, "CONFIG_TOO_LARGE")
    return config


def source_snapshot(root):
    require(isinstance(root, Path) and root.is_absolute(), "SOURCE_ROOT_REQUIRED")
    head = (
        subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            timeout=2,
        )
        .stdout.decode()
        .strip()
    )
    hashes = {
        name: hashlib.sha256(raw_file(root / name, 2_000_000)).hexdigest()
        for name in SOURCE_FILES
    }
    return {"head": head, "files_sha256": budget.content_hash(hashes)}


def source_identity(config, root):
    actual = source_snapshot(root)
    require(actual["head"] == config["execution_head"], "SOURCE_HEAD_MISMATCH")
    require(
        actual["files_sha256"] == budget.content_hash(config["source_files"]),
        "SOURCE_BYTES_MISMATCH",
    )
    return actual


def connection_parameters(config, credential):
    """DSN is data, never libpq options; nothing may supply options/service/cert paths."""
    require(
        type(credential) is str and 0 < len(credential) <= 4096, "CREDENTIAL_REQUIRED"
    )
    parsed = urlsplit(credential)
    require(
        parsed.scheme == "postgresql"
        and not parsed.query
        and not parsed.fragment
        and parsed.hostname is not None
        and parsed.username is not None
        and parsed.password is not None,
        "CREDENTIAL_FORMAT_REFUSED",
    )
    d = config["database"]
    require(
        (
            parsed.hostname,
            parsed.port or 5432,
            unquote(parsed.path[1:]),
            unquote(parsed.username),
        )
        == (d["host"], d["port"], d["name"], d["role"]),
        "CREDENTIAL_IDENTITY_MISMATCH",
    )
    password = unquote(parsed.password)
    require(
        0 < len(password) <= 1024 and "\x00" not in password,
        "CREDENTIAL_FORMAT_REFUSED",
    )
    return dict(
        host=d["host"],
        port=d["port"],
        dbname=d["name"],
        user=d["role"],
        password=password,
        sslmode=d["tls"],
        sslrootcert="system" if d["tls"] == "verify-full" else "",
        connect_timeout=3,
        application_name="b66-ingestion-preflight",
        options=OPTIONS,
        passfile="/dev/null",
    )


def _expired(_signum, _frame):
    raise budget.EvidenceError("WHOLE_RUN_TIMEOUT")


@contextmanager
def deadline():
    global _OWNED_DEADLINE
    require(
        threading.current_thread() is threading.main_thread(), "MAIN_THREAD_REQUIRED"
    )
    timer = signal.getitimer(signal.ITIMER_REAL)
    if _OWNED_DEADLINE:
        # CLI owns the earlier deadline. A nested supported API neither resets
        # nor extends it; an expired/lost outer deadline cannot admit a new run.
        require(
            timer[0] > 0 and signal.getsignal(signal.SIGALRM) is _expired,
            "DEADLINE_LOST",
        )
        yield
        return
    require(timer == (0.0, 0.0), "EXISTING_TIMER_REFUSED")
    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _expired)
    signal.setitimer(signal.ITIMER_REAL, RUN_SECONDS)
    _OWNED_DEADLINE = True
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        _OWNED_DEADLINE = False
        signal.signal(signal.SIGALRM, previous)


class Reads:
    """Only this module's fixed queries; no SQL supplied by config or CLI."""

    def __init__(self, cursor):
        self.cursor = cursor
        self.requests = 0
        self.read_requests = 0
        self.rows = 0
        self.bytes = 0

    def read(self, sql, params=None):
        allowed = (IDENTITY_SQL, SCHEMA_SQL, GUARDS_SQL, REVISION_SQL, *CHECKS.values())
        require(sql in allowed, "SQL_NOT_ALLOWLISTED")
        self.command(sql, params)
        self.read_requests += 1
        rows = self.cursor.fetchmany(MAX_ROWS + 1)
        require(type(rows) is list and len(rows) <= MAX_ROWS, "ROW_BUDGET_EXCEEDED")
        self.rows += len(rows)
        # Transport buffers are additionally bounded by fixed scalar/column types.
        self.bytes += len(
            budget.canonical(
                [
                    [v.isoformat() if type(v) is datetime else v for v in row]
                    for row in rows
                ]
            )
        )
        require(
            self.rows <= MAX_ROWS and self.bytes <= MAX_BYTES, "RESULT_BUDGET_EXCEEDED"
        )
        return rows

    def command(self, sql, params=None):
        require(
            sql
            in (
                *SESSION_COMMANDS,
                IDENTITY_SQL,
                SCHEMA_SQL,
                GUARDS_SQL,
                REVISION_SQL,
                *CHECKS.values(),
            ),
            "SQL_NOT_ALLOWLISTED",
        )
        self.requests += 1
        require(self.requests <= MAX_REQUESTS, "REQUEST_BUDGET_EXCEEDED")
        self.cursor.execute(sql, params)

    def one(self, sql, params=None):
        rows = self.read(sql, params)
        require(len(rows) == 1, "OBSERVATION_INCOMPLETE")
        return rows[0]


def inspect(connection, config):
    """Internal connection boundary still validates config and enforces READ ONLY."""
    check_config(config)
    connection.autocommit = True
    with connection.cursor() as cursor:
        reader = Reads(cursor)
        # Enforced even when called directly with an already-open connection.
        for command in SESSION_COMMANDS:
            reader.command(command)
        identity = reader.one(IDENTITY_SQL)
        require(len(identity) == 14, "OBSERVATION_INCOMPLETE")
        (
            _,
            database,
            oid,
            user,
            session,
            readonly,
            statement,
            lock,
            idle,
            version,
            *privileges,
        ) = identity
        expected = config["database"]
        require(
            database == expected["name"]
            and type(oid) is int
            and oid == expected["oid"]
            and user == session == expected["role"],
            "DATABASE_ROLE_MISMATCH",
        )
        require(
            all(type(x) is bool and x is False for x in privileges),
            "WRITER_ROLE_REFUSED",
        )
        require(
            readonly == "on"
            and statement == "2s"
            and lock == "500ms"
            and idle == "3s"
            and type(version) is int
            and 170000 <= version < 180000,
            "SESSION_GUARDS_MISMATCH",
        )
        guards = reader.one(GUARDS_SQL)
        require(len(guards) == 14, "OBSERVATION_INCOMPLETE")
        require(
            guards[:8]
            == ("on", "on", "repeatable read", "2s", "500ms", "3s", "off", "pg_catalog")
            and guards[8] is True
            and type(guards[9]) is bool
            and guards[9] == (expected["tls"] == "verify-full")
            and type(guards[10]) is int
            and guards[10] == expected["role_oid"]
            and guards[11:] == ("0", "64kB", "5s"),
            "TLS_OR_SESSION_UNVERIFIED",
        )
        schema = reader.read(SCHEMA_SQL, (list(TABLES),))
        require(
            {row[0] for row in schema} == set(TABLES)
            and all(row[1] == "r" for row in schema),
            "SCHEMA_INCOMPLETE",
        )
        require(
            budget.content_hash(schema) == config["schema_sha256"], "SCHEMA_MISMATCH"
        )
        require(reader.one(REVISION_SQL) == (config["revision"],), "REVISION_MISMATCH")
        observed = {}
        for name, sql in CHECKS.items():
            row = reader.one(sql)
            require(len(row) == 1 and type(row[0]) is bool, "OBSERVATION_INCOMPLETE")
            observed[name] = row[0]
        require(not any(observed.values()), "RETAINED_OR_ACTIVE_STATE")
        return {
            "checks": observed,
            "sql_commands": reader.requests,
            "read_requests": reader.read_requests,
            "rows": reader.rows,
            "decoded_result_bytes": reader.bytes,
            "schema_sha256": budget.content_hash(schema),
            "tls": expected["tls"],
            "server_version_num": version,
        }


def report():
    return {
        "version": 1,
        "status": "REFUSED",
        "production_authorized": False,
        "safe_to_write": False,
        "free_ready": False,
        "custody_operator_gate": "UNMET",
        "receipt_backend_gate": "NOT_OBSERVED",
        "observation": None,
        "errors": [],
        "generated_by": "scripts/verification/ingestion_preflight.py",
        "generator_sha256": hashlib.sha256(
            raw_file(Path(__file__).absolute(), 2_000_000)
        ).hexdigest(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {"python": ".".join(map(str, sys.version_info[:3])), "driver": None},
        "budgets": {
            "whole_run_seconds": RUN_SECONDS,
            "connect_seconds": 3,
            "statement_ms": 2000,
            "lock_ms": 500,
            "idle_transaction_ms": 3000,
            "idle_session_ms": 5000,
            "sql_commands": MAX_REQUESTS,
            "cleanup_rollbacks": 1,
            "total_rows": MAX_ROWS,
            "decoded_result_bytes": MAX_BYTES,
            "connections": 1,
            "process_concurrency": 1,
        },
        "config_sha256": None,
        "source": None,
        "policy_raw_sha256": None,
        "binding_errors": ["CONFIG_NOT_OBSERVED", "SOURCE_NOT_OBSERVED"],
        "worker_cleanup": None,
        "artifact_authentication": "UNVERIFIED_WHEN_IMPORTED",
    }


def _connection_run(config, credential, root, result):
    """Only the owned worker opens libpq. Parent owns the physical deadline."""
    connection = None
    failure = None
    try:
        check_config(config)
        before = source_identity(config, root)
        params = connection_parameters(config, credential)
        import psycopg2

        result["runtime"]["driver"] = psycopg2.__version__.split()[0]
        result["runtime"]["libpq"] = psycopg2.extensions.libpq_version()
        require(result["runtime"]["driver"] == "2.9.12", "DRIVER_UNSUPPORTED")
        connection = psycopg2.connect(**params)
        observation = inspect(connection, config)
        require(source_identity(config, root) == before, "SOURCE_CHANGED_DURING_RUN")
        result.update(status="OBSERVED_READ_CHECKS_ONLY", observation=observation)
    except budget.EvidenceError as error:
        failure = str(error)
    except Exception:
        # Deliberately discard driver/JSON/OS exception text and context.
        failure = "INSPECTION_FAILED"
    finally:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                failure = "CLEANUP_FAILED"
            try:
                connection.close()
            except Exception:
                failure = "CLEANUP_FAILED"
    if failure:
        result["status"] = "REFUSED"
        result["observation"] = None
        result["errors"] = [failure]
    return result


def _bind(result, config, root):
    result["source"] = source_snapshot(root)
    result["binding_errors"] = [
        x for x in result["binding_errors"] if x != "SOURCE_NOT_OBSERVED"
    ]
    try:
        raw = budget.canonical(config)
        require(len(raw) <= MAX_BYTES, "CONFIG_TOO_LARGE")
        result["config_sha256"] = hashlib.sha256(raw).hexdigest()
        result["binding_errors"] = [
            x for x in result["binding_errors"] if x != "CONFIG_NOT_OBSERVED"
        ]
    except budget.EvidenceError:
        raise
    except (ValueError, TypeError, RecursionError):
        result["binding_errors"].append("CONFIG_BINDING_UNAVAILABLE")


# Only fixed diagnostics may cross the private worker boundary. Unknown driver
# exceptions are already discarded by _connection_run, never serialized here.
WORKER_REFUSALS = frozenset(
    {
        "INSPECTION_FAILED",
        "CLEANUP_FAILED",
        "DRIVER_UNSUPPORTED",
        "SOURCE_HEAD_MISMATCH",
        "SOURCE_BYTES_MISMATCH",
        "SOURCE_CHANGED_DURING_RUN",
        "ABSOLUTE_PATH_REQUIRED",
        "FILE_LINK_REFUSED",
        "REGULAR_SINGLE_FILE_REQUIRED",
        "FILE_SIZE_REFUSED",
        "SOURCE_ROOT_REQUIRED",
        "SQL_NOT_ALLOWLISTED",
        "ROW_BUDGET_EXCEEDED",
        "RESULT_BUDGET_EXCEEDED",
        "REQUEST_BUDGET_EXCEEDED",
        "OBSERVATION_INCOMPLETE",
        "DATABASE_ROLE_MISMATCH",
        "WRITER_ROLE_REFUSED",
        "SESSION_GUARDS_MISMATCH",
        "TLS_OR_SESSION_UNVERIFIED",
        "SCHEMA_INCOMPLETE",
        "SCHEMA_MISMATCH",
        "REVISION_MISMATCH",
        "RETAINED_OR_ACTIVE_STATE",
        "INVALID_SHAPE",
        "INVALID_INTEGER",
        "INVALID_LABEL",
        "INVALID_HASH",
        "INVALID_JSON",
        "NONFINITE_JSON",
        "RESULT_TYPE_REFUSED",
    }
)


def _validate_worker_report(child, parent, config):
    """A complete internally consistent observation is required even on private IPC."""
    code = "WORKER_REPORT_INVALID"
    require(type(child) is dict and set(child) == set(parent), code)
    for key in (
        "version",
        "production_authorized",
        "safe_to_write",
        "free_ready",
        "custody_operator_gate",
        "receipt_backend_gate",
        "generated_by",
        "generator_sha256",
        "budgets",
        "config_sha256",
        "source",
        "policy_raw_sha256",
        "binding_errors",
        "artifact_authentication",
    ):
        # Canonical bytes distinguish bools from integers throughout nested data.
        require(budget.canonical(child[key]) == budget.canonical(parent[key]), code)
    require(child["worker_cleanup"] is None, code)
    require(
        type(child["status"]) is str
        and child["status"] in ("REFUSED", "OBSERVED_READ_CHECKS_ONLY"),
        code,
    )
    try:
        stamp = budget.instant(child["generated_at"])
        require(
            budget.instant(parent["generated_at"])
            <= stamp
            <= datetime.now(timezone.utc),
            code,
        )
    except (budget.EvidenceError, ValueError, TypeError):
        require(False, code)
    runtime = child["runtime"]
    require(
        type(runtime) is dict
        and set(runtime) in ({"python", "driver"}, {"python", "driver", "libpq"}),
        code,
    )
    require(runtime["python"] == parent["runtime"]["python"], code)
    require(runtime["driver"] is None or runtime["driver"] == "2.9.12", code)
    if "libpq" in runtime:
        require(
            type(runtime["libpq"]) is int and 100000 <= runtime["libpq"] <= 999999, code
        )
    if child["status"] == "REFUSED":
        require(
            child["observation"] is None
            and type(child["errors"]) is list
            and len(child["errors"]) == 1,
            code,
        )
        require(
            type(child["errors"][0]) is str and child["errors"][0] in WORKER_REFUSALS,
            code,
        )
        return
    require(child["errors"] == [] and type(child["errors"]) is list, code)
    require(runtime["driver"] == "2.9.12" and "libpq" in runtime, code)
    observation = child["observation"]
    require(
        type(observation) is dict
        and set(observation)
        == {
            "checks",
            "sql_commands",
            "read_requests",
            "rows",
            "decoded_result_bytes",
            "schema_sha256",
            "tls",
            "server_version_num",
        },
        code,
    )
    checks = observation["checks"]
    require(
        type(checks) is dict
        and set(checks) == set(CHECKS)
        and all(x is False for x in checks.values()),
        code,
    )
    for key, low, high in (
        (
            "sql_commands",
            len(SESSION_COMMANDS) + 4 + len(CHECKS),
            len(SESSION_COMMANDS) + 4 + len(CHECKS),
        ),
        ("read_requests", 4 + len(CHECKS), 4 + len(CHECKS)),
        # Ten one-row reads plus at least one schema row per required table.
        ("rows", 3 + len(CHECKS) + len(TABLES), MAX_ROWS),
        # Seven fixed false rows alone contribute these exact decoded bytes.
        (
            "decoded_result_bytes",
            len(CHECKS) * len(budget.canonical([[False]])),
            MAX_BYTES,
        ),
        ("server_version_num", 170000, 179999),
    ):
        require(type(observation[key]) is int and low <= observation[key] <= high, code)
    require(
        observation["schema_sha256"] == config["schema_sha256"]
        and observation["tls"] == config["database"]["tls"],
        code,
    )


def run(config, *, execute=False, credential=None, root=ROOT):
    """Supported API: same admission, bounded worker and cleanup as the CLI."""
    result = report()
    held = False
    try:
        held = _RUN_LOCK.acquire(blocking=False)
        require(held, "CONCURRENT_RUN_REFUSED")
        with deadline():
            _bind(result, config, root)
            check_config(config)
            config = json.loads(budget.canonical(config))
            check_config(config)
            require(type(execute) is bool and execute, "EXECUTION_NOT_AUTHORIZED")
            require(
                not any(k.startswith("PG") for k in os.environ), "AMBIENT_LIBPQ_REFUSED"
            )
            require(sys.version_info[:2] in ((3, 12), (3, 13)), "RUNTIME_UNSUPPORTED")
            source_identity(config, root)
            connection_parameters(config, credential)
            seconds = signal.getitimer(signal.ITIMER_REAL)[0]
            packet = budget.canonical(
                {
                    "version": 1,
                    "execute": True,
                    "config": config,
                    "credential": credential,
                    "root": str(root),
                }
            )
            observed = worker.bounded(packet, seconds=seconds)
            result["worker_cleanup"] = observed["cleanup"]
            require(observed["error"] is None, observed["error"] or "WORKER_FAILED")
            try:
                child = json.loads(
                    observed["payload"],
                    object_pairs_hook=budget._pairs,
                    parse_constant=lambda _: require(False, "WORKER_REPORT_INVALID"),
                )
                _validate_worker_report(child, result, config)
            except Exception:
                require(False, "WORKER_REPORT_INVALID")
            child["worker_cleanup"] = observed["cleanup"]
            result = child
    except budget.EvidenceError as error:
        result.update(status="REFUSED", observation=None, errors=[str(error)])
    except Exception:
        result.update(status="REFUSED", observation=None, errors=["INSPECTION_FAILED"])
    finally:
        if held:
            _RUN_LOCK.release()
    return result


def output_destination(destination):
    require(
        isinstance(destination, Path)
        and destination.is_absolute()
        and ".." not in destination.parts
        and destination.suffix == ".json",
        "OUTPUT_PATH_REFUSED",
    )
    for part in (destination, *destination.parents):
        require(not part.is_symlink(), "OUTPUT_LINK_REFUSED")
    require(
        not destination.exists() and not destination.resolve().is_relative_to(ROOT),
        "FRESH_EXTERNAL_OUTPUT_REQUIRED",
    )
    require(destination.parent.is_dir(), "OUTPUT_PARENT_REQUIRED")


def publish(result, destination):
    """Fresh bounded report only; no overwrite, links, source or input collision."""
    output_destination(destination)
    raw = budget.canonical(result)
    require(len(raw) <= MAX_BYTES, "OUTPUT_TOO_LARGE")
    with os.fdopen(
        os.open(
            destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        ),
        "wb",
    ) as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(raw_file(destination) == raw, "OUTPUT_READBACK_MISMATCH")


def _main(argv=None):
    result = report()
    try:
        result["source"] = source_snapshot(ROOT)
        result["binding_errors"] = [
            x for x in result["binding_errors"] if x != "SOURCE_NOT_OBSERVED"
        ]
        parser = budget.SafeParser(description=__doc__)
        parser.add_argument("--execute-read-only", action="store_true")
        parser.add_argument("--admit-only", action="store_true")
        parser.add_argument("--owned-local-config", type=Path)
        parser.add_argument("--reviewed-admission", type=Path)
        parser.add_argument("--expected-admission-sha256")
        parser.add_argument("--out", type=Path)
        args = parser.parse_args(argv)
        require(
            not (args.owned_local_config and args.reviewed_admission),
            "CONFIG_MODES_EXCLUSIVE",
        )
        require(
            bool(args.reviewed_admission) == bool(args.expected_admission_sha256),
            "ADMISSION_HASH_REQUIRED",
        )
        config = load(
            args.owned_local_config or args.reviewed_admission or CONFIG,
            args.expected_admission_sha256,
            receipt=result,
        )
        _bind(result, config, ROOT)
        check_config(config)
        if args.out:
            output_destination(args.out)
        if args.owned_local_config:
            require(config["mode"] == "owned-local", "LOCAL_MODE_REQUIRED")
        else:
            require(config["mode"] == "hosted", "HOSTED_MODE_REQUIRED")
        if args.admit_only:
            require(
                not args.execute_read_only and args.out is None,
                "ADMISSION_ARGUMENTS_REFUSED",
            )
            source_identity(config, ROOT)
            print('{"admitted_for_read_checks_only":true,"safe_to_write":false}')
            return 0
        raw_sha = result["policy_raw_sha256"]
        result = run(
            config,
            execute=args.execute_read_only,
            credential=os.environ.get("INGESTION_PREFLIGHT_DATABASE_URL"),
        )
        result["policy_raw_sha256"] = raw_sha
        if args.out:
            publish(result, args.out)
        print(budget.canonical(result).decode())
        return 0 if result["status"] == "OBSERVED_READ_CHECKS_ONLY" else 1
    except budget.EvidenceError as error:
        result.update(status="REFUSED", observation=None, errors=[str(error)])
        print(budget.canonical(result).decode())
        return 2
    except Exception:
        result["status"] = "REFUSED"
        result["observation"] = None
        result["errors"] = ["ADMISSION_OR_OUTPUT_REFUSED"]
        print(budget.canonical(result).decode())
        return 2


def main(argv=None):
    try:
        with deadline():
            return _main(argv)
    except Exception:
        result = report()
        result["errors"] = ["CLI_DEADLINE_OR_CONTEXT_REFUSED"]
        print(budget.canonical(result).decode())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

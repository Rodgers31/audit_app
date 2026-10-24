#!/usr/bin/env python3
"""Protocol 2: bounded metadata observation, never write or custody admission.

Session-pooler TLS terminates at the pooler. A new client connection is not a
promise of a fresh physical backend. This separate workload contract requires
one pinned backend, no temporary namespace, explicit READ ONLY transactions,
and fixed SQL. It does not claim that the credential lacks inherited TEMP.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from urllib.parse import unquote, urlsplit

sys.dont_write_bytecode = True
if __package__:
    from . import ingestion_preflight as v1
    from . import ingestion_metadata_contract as contract
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ingestion_preflight as v1
    import ingestion_metadata_contract as contract

budget, require = v1.budget, v1.require
ROOT = v1.ROOT
CONFIG = ROOT / "docs/admin/batch71/metadata-admission.json"
PROFILE = "clean-session-metadata-v2"
MAX_REQUESTS = 29
DRIVER = "2.9.13"
MANIFEST = "PREFLIGHT_SOURCE.json"
SOURCE_FILES = (
    *v1.SOURCE_FILES,
    "scripts/verification/ingestion_metadata_contract.py",
    "scripts/verification/ingestion_metadata_preflight.py",
    "docs/admin/batch71/metadata-driver-requirements.txt",
)
# CREATE remains refused. TEMP is separately observed and explicitly admitted
# for this workload only; v1's credential guarantee is deliberately unchanged.
IDENTITY_SQL = v1.IDENTITY_SQL.replace("'CREATE,TEMP'", "'CREATE'")
# Pin object identity as well as definition. A replacement relation with the
# same name/columns must not inherit the independently admitted schema hash.
SCHEMA_SQL = v1.SCHEMA_SQL.replace(
    "c.relowner::bigint", "c.relowner::bigint, n.oid::bigint, c.oid::bigint"
)
GUARDS_SQL = """SELECT
 current_setting('default_transaction_read_only'),current_setting('transaction_read_only'),
 current_setting('transaction_isolation'),current_setting('statement_timeout'),
 current_setting('lock_timeout'),current_setting('idle_in_transaction_session_timeout'),
 current_setting('idle_session_timeout'),current_setting('row_security'),
 current_setting('search_path'),current_setting('max_parallel_workers_per_gather'),
 current_setting('work_mem'),pg_catalog.pg_backend_pid(),pg_catalog.pg_my_temp_schema()::bigint,
 pg_catalog.pg_has_role(current_user,'pg_read_all_stats','MEMBER'),
 (SELECT oid::bigint FROM pg_catalog.pg_roles WHERE rolname=current_user),
 pg_catalog.has_database_privilege(current_user,current_database(),'TEMP')"""
SESSION_COMMANDS = (
    v1.SESSION_COMMANDS[0],
    "SET LOCAL default_transaction_read_only=on",
    *v1.SESSION_COMMANDS[1:],
)
SQL_READS = (
    IDENTITY_SQL,
    GUARDS_SQL,
    SCHEMA_SQL,
    contract.INTERFACE_SQL,
    contract.OBSERVE_SQL,
)


def check_config(config):
    budget.shape(
        config,
        {
            "version",
            "mode",
            "accepted",
            "profile",
            "execution_head",
            "source_files",
            "database",
            "schema_sha256",
            "revision",
            "receipt_authority",
            "interface",
            "source_kind",
            "source_manifest_sha256",
        },
    )
    require(
        type(config["version"]) is int and config["version"] == 2,
        "CONFIG_VERSION_REFUSED",
    )
    require(config["accepted"] is True, "ADMISSION_DISABLED")
    require(config["profile"] == PROFILE, "PROFILE_REFUSED")
    require(
        type(config["mode"]) is str and config["mode"] in ("hosted", "owned-local"),
        "MODE_REFUSED",
    )
    budget.digest(config["execution_head"], 40)
    require(
        type(config["source_kind"]) is str
        and config["source_kind"] in ("git-checkout", "reviewed-bundle"),
        "SOURCE_KIND_REFUSED",
    )
    if config["source_kind"] == "reviewed-bundle":
        budget.digest(config["source_manifest_sha256"])
    else:
        require(config["source_manifest_sha256"] is None, "SOURCE_KIND_REFUSED")
    budget.shape(config["source_files"], SOURCE_FILES)
    for digest in config["source_files"].values():
        budget.digest(digest)
    budget.digest(config["schema_sha256"])
    require(
        type(config["revision"]) is str
        and re.fullmatch("[a-z0-9]{8,32}", config["revision"]),
        "REVISION_REQUIRED",
    )
    d = budget.shape(
        config["database"],
        {
            "host",
            "port",
            "name",
            "oid",
            "role",
            "role_oid",
            "login_user",
            "tls",
            "rootcert",
            "rootcert_sha256",
            "temporary",
        },
    )
    for key in ("name", "role"):
        require(
            type(d[key]) is str and re.fullmatch("[a-z][a-z0-9_]{0,62}", d[key]),
            "IDENTITY_REQUIRED",
        )
    for key in ("oid", "role_oid"):
        require(0 < budget.integer(d[key], 2**32 - 1), "IDENTITY_REQUIRED")
    require(type(d["temporary"]) is bool, "TEMP_CONTRACT_REQUIRED")
    require(type(d["port"]) is int, "TRANSPORT_REFUSED")
    if config["mode"] == "owned-local":
        require(
            d["host"] == "127.0.0.1"
            and d["port"] == 56972
            and d["name"] == "b66_preflight_metadata"
            and d["role"] == d["login_user"] == "b71_preflight_reader"
            and d["tls"] == "disable"
            and d["rootcert"] is None
            and d["rootcert_sha256"] is None,
            "OWNED_FIXTURE_REQUIRED",
        )
    else:
        require(
            type(d["host"]) is str
            and re.fullmatch(r"aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com", d["host"])
            and d["port"] == 5432
            and d["tls"] == "verify-full"
            and d["role"] == "audit_app_audit_reader"
            and type(d["login_user"]) is str
            and re.fullmatch(r"audit_app_audit_reader\.[a-z]{20}", d["login_user"]),
            "SESSION_TLS_IDENTITY_REQUIRED",
        )
        require(
            type(d["rootcert"]) is str and Path(d["rootcert"]).is_absolute(),
            "CERTIFICATE_REQUIRED",
        )
        budget.digest(d["rootcert_sha256"])
    i = budget.shape(
        config["interface"],
        {"namespace_oid", "function_oid", "owner_oid", "body_sha256", "role_profile"},
    )
    for key in ("namespace_oid", "function_oid", "owner_oid"):
        require(0 < budget.integer(i[key], 2**32 - 1), "INTERFACE_IDENTITY_REQUIRED")
    require(
        i["owner_oid"] != d["role_oid"] and i["body_sha256"] == contract.BODY_SHA256,
        "INTERFACE_CONTRACT_REFUSED",
    )
    try:
        log_oid, grantor_oid = contract.profile_oids(i["role_profile"])
    except ValueError:
        require(False, "ROLE_PROFILE_REFUSED")
    if i["role_profile"] is not None:
        require(
            len({log_oid, grantor_oid, i["owner_oid"], d["role_oid"]}) == 4,
            "ROLE_PROFILE_REFUSED",
        )
    a = budget.shape(config["receipt_authority"], {"state", "identity_sha256"})
    require(a["state"] == "accepted", "RECEIPT_AUTHORITY_UNACCEPTED")
    budget.digest(a["identity_sha256"])
    require(len(budget.canonical(config)) <= v1.MAX_BYTES, "CONFIG_TOO_LARGE")
    return config


def source_snapshot(root, *, kind="git-checkout", manifest_sha256=None):
    require(isinstance(root, Path) and root.is_absolute(), "SOURCE_ROOT_REQUIRED")
    require(kind in ("git-checkout", "reviewed-bundle"), "SOURCE_KIND_REFUSED")
    manifest = None
    if kind == "git-checkout":
        require(manifest_sha256 is None, "SOURCE_KIND_REFUSED")
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
    else:
        # This manifest is independently hash-pinned in admission, not learned
        # from the target. No Git-less fallback or target self-admission.
        budget.digest(manifest_sha256)
        manifest = v1.load(root / MANIFEST, manifest_sha256)
        budget.shape(manifest, {"version", "execution_head", "source_files"})
        require(
            type(manifest["version"]) is int and manifest["version"] == 1,
            "SOURCE_MANIFEST_REFUSED",
        )
        head = manifest["execution_head"]
        budget.shape(manifest["source_files"], SOURCE_FILES)
    budget.digest(head, 40)
    hashes = {
        n: hashlib.sha256(v1.raw_file(root / n, 2_000_000)).hexdigest()
        for n in SOURCE_FILES
    }
    require(
        manifest is None or manifest["source_files"] == hashes,
        "SOURCE_MANIFEST_REFUSED",
    )
    return {
        "head": head,
        "files_sha256": budget.content_hash(hashes),
        "kind": kind,
        "manifest_sha256": manifest_sha256,
    }


def source_identity(config, root):
    actual = source_snapshot(
        root,
        kind=config["source_kind"],
        manifest_sha256=config["source_manifest_sha256"],
    )
    require(actual["head"] == config["execution_head"], "SOURCE_HEAD_MISMATCH")
    require(
        actual["files_sha256"] == budget.content_hash(config["source_files"]),
        "SOURCE_BYTES_MISMATCH",
    )
    return actual


def connection_parameters(config, credential):
    check_config(config)
    require(
        type(credential) is str and 0 < len(credential) <= 4096, "CREDENTIAL_REQUIRED"
    )
    p = urlsplit(credential)
    require(
        p.scheme == "postgresql"
        and not p.fragment
        and not p.query
        and p.username is not None
        and p.password is not None,
        "CREDENTIAL_FORMAT_REFUSED",
    )
    d = config["database"]
    require(
        (p.hostname, p.port or 5432, unquote(p.path[1:]), unquote(p.username))
        == (d["host"], d["port"], d["name"], d["login_user"]),
        "CREDENTIAL_IDENTITY_MISMATCH",
    )
    password = unquote(p.password)
    require(
        0 < len(password) <= 1024 and "\x00" not in password,
        "CREDENTIAL_FORMAT_REFUSED",
    )
    if config["mode"] == "hosted":
        require(
            hashlib.sha256(v1.raw_file(Path(d["rootcert"]), 2_000_000)).hexdigest()
            == d["rootcert_sha256"],
            "CERTIFICATE_MISMATCH",
        )
    return dict(
        host=d["host"],
        port=d["port"],
        dbname=d["name"],
        user=d["login_user"],
        password=password,
        sslmode=d["tls"],
        sslrootcert=d["rootcert"] or "",
        connect_timeout=3,
        application_name="b71-metadata-preflight",
        options=v1.OPTIONS,
        passfile="/dev/null",
    )


class Reads:
    def __init__(self, cursor):
        self.cursor, self.requests, self.records = cursor, 0, []

    def command(self, sql, params=None):
        require(sql in (*SQL_READS, *SESSION_COMMANDS), "SQL_NOT_ALLOWLISTED")
        self.requests += 1
        require(self.requests <= MAX_REQUESTS, "REQUEST_BUDGET_EXCEEDED")
        self.cursor.execute(sql, params)

    def read(self, sql, params=None):
        require(sql in SQL_READS, "SQL_NOT_ALLOWLISTED")
        self.command(sql, params)
        rows = self.cursor.fetchmany(v1.MAX_ROWS + 1)
        require(type(rows) is list and len(rows) <= v1.MAX_ROWS, "ROW_BUDGET_EXCEEDED")
        wire = [
            [x.isoformat() if type(x) is datetime else x for x in row] for row in rows
        ]
        self.records.append(wire)
        require(
            sum(map(len, self.records)) <= v1.MAX_ROWS
            and sum(len(budget.canonical(r)) for r in self.records) <= v1.MAX_BYTES,
            "RESULT_BUDGET_EXCEEDED",
        )
        return wire


def _one(rows, length):
    require(
        type(rows) is list
        and len(rows) == 1
        and type(rows[0]) is list
        and len(rows[0]) == length,
        "OBSERVATION_INCOMPLETE",
    )
    return rows[0]


def verify_metadata(config, records, client_tls):
    """Validate real catalog records before any privileged function invocation."""
    check_config(config)
    require(type(records) is list and len(records) in (4, 8), "OBSERVATION_INCOMPLETE")
    require(
        type(client_tls) is bool and client_tls == (config["mode"] == "hosted"),
        "CLIENT_TLS_UNVERIFIED",
    )
    d, i = config["database"], config["interface"]
    backend = None
    version = None
    for offset in range(0, len(records), 4):
        identity = _one(records[offset], 14)
        budget.instant(identity[0])
        require(
            identity[1:5] == [d["name"], d["oid"], d["role"], d["role"]]
            and type(identity[2]) is int,
            "DATABASE_ROLE_MISMATCH",
        )
        require(
            identity[5:9] == ["on", "2s", "500ms", "3s"]
            and type(identity[9]) is int
            and 170000 <= identity[9] <= 179999,
            "SESSION_GUARDS_MISMATCH",
        )
        require(all(x is False for x in identity[10:]), "WRITER_ROLE_REFUSED")
        require(version is None or version == identity[9], "DATABASE_ROLE_MISMATCH")
        version = identity[9]
        g = _one(records[offset + 1], 16)
        require(
            g[:11]
            == [
                "on",
                "on",
                "repeatable read",
                "2s",
                "500ms",
                "3s",
                "5s",
                "off",
                "pg_catalog",
                "0",
                "64kB",
            ]
            and type(g[11]) is int
            and 0 < g[11] <= 2**31 - 1
            and type(g[12]) is int
            and g[12] == 0
            and g[13] is False
            and type(g[14]) is int
            and g[14] == d["role_oid"]
            and type(g[15]) is bool
            and g[15] == d["temporary"],
            "CLEAN_SESSION_UNVERIFIED",
        )
        require(backend is None or backend == g[11], "SESSION_CHANGED")
        backend = g[11]
        schema = records[offset + 2]
        require(
            type(schema) is list
            and all(
                type(r) is list
                and len(r) == 12
                and v1._schema_row_valid(tuple(r[:10]))
                and all(type(x) is int and 0 < x <= 2**32 - 1 for x in r[10:])
                for r in schema
            )
            and {r[0] for r in schema} == set(v1.TABLES),
            "SCHEMA_INCOMPLETE",
        )
        require(
            budget.content_hash(schema) == config["schema_sha256"], "SCHEMA_MISMATCH"
        )
        f = _one(records[offset + 3], 20)
        require(
            all(
                type(f[x]) is int and f[x] == i[k]
                for x, k in (
                    (0, "namespace_oid"),
                    (1, "function_oid"),
                    (2, "owner_oid"),
                )
            )
            and f[3:9] == ["sql", True, "s", "f", 0, True]
            and type(f[4]) is bool
            and type(f[7]) is int
            and type(f[8]) is bool
            and f[9] is True
            and f[10] is True
            and f[11] == "u"
            and f[12] is False
            and f[13] is False
            and type(f[14]) is int
            and f[14] == i["owner_oid"]
            and f[15] is True
            and f[16] is True
            and f[17] is True
            and type(f[18]) is str
            and f[18] == contract.BODY
            and f[19] is True,
            "INTERFACE_DRIFT",
        )
    return version


def verify_records(config, records, client_tls):
    """Replay every actual fixed read in child and parent; no summary-only green."""
    require(type(records) is list and len(records) == 9, "OBSERVATION_INCOMPLETE")
    version = verify_metadata(config, records[:4] + records[5:], client_tls)
    observation = _one(records[4], 10)
    require(
        type(observation[0]) is int
        and observation[0] == 2
        and observation[1] == config["revision"],
        "REVISION_MISMATCH",
    )
    require(
        all(type(x) is bool for x in observation[2:]) and observation[-1] is True,
        "OBSERVATION_INCOMPLETE",
    )
    require(not any(observation[2:-1]), "RETAINED_OR_ACTIVE_STATE")
    rows = sum(map(len, records))
    size = sum(len(budget.canonical(r)) for r in records)
    require(rows <= v1.MAX_ROWS and size <= v1.MAX_BYTES, "RESULT_BUDGET_EXCEEDED")
    return {
        "checks": dict(zip(contract.CHECK_NAMES, observation[2:-1])),
        "complete_activity": True,
        "schema_sha256": config["schema_sha256"],
        "interface_sha256": contract.BODY_SHA256,
        "sql_commands": MAX_REQUESTS,
        "read_requests": 9,
        "rows": rows,
        "decoded_result_bytes": size,
        "server_version_num": version,
        "client_tls": client_tls,
        "temporary_capability": config["database"]["temporary"],
        "temporary_namespace_absent": True,
        "physical_backend_freshness": "NOT_CLAIMED",
        "profile": PROFILE,
    }


def inspect(connection, config):
    check_config(config)
    require(
        type(connection.get_transaction_status()) is int
        and connection.get_transaction_status() == 0,
        "DIRTY_TRANSACTION_REFUSED",
    )
    connection.autocommit = True
    tls = connection.info.ssl_in_use
    with connection.cursor() as cursor:
        reads = Reads(cursor)
        for phase in range(2):
            for sql in SESSION_COMMANDS:
                reads.command(sql)
            reads.read(IDENTITY_SQL)
            reads.read(GUARDS_SQL)
            reads.read(SCHEMA_SQL, (list(v1.TABLES),))
            reads.read(
                contract.INTERFACE_SQL,
                contract.interface_parameters(
                    config["database"]["role_oid"], config["interface"]["role_profile"]
                ),
            )
            # Validate metadata BEFORE invoking a privileged routine. Second
            # transaction observes persistent definition/schema/session drift.
            if phase == 0:
                verify_metadata(config, reads.records, tls)
                reads.read(contract.OBSERVE_SQL)
                rollback(connection)
        result = verify_records(config, reads.records, tls)
        require(reads.requests == MAX_REQUESTS, "OBSERVATION_INCOMPLETE")
        return result, reads.records


def rollback(connection):
    # psycopg2's rollback() alone does not end SQL-BEGIN transactions while
    # autocommit is true. Issue the fixed wire command before the next snapshot.
    connection.rollback()
    with connection.cursor() as cursor:
        cursor.execute("ROLLBACK")
    require(
        type(connection.get_transaction_status()) is int
        and connection.get_transaction_status() == 0,
        "DIRTY_TRANSACTION_REFUSED",
    )


def report(*, bind_generator=True):
    result = v1.report(bind_generator=False)
    result.update(
        version=2,
        generated_by="scripts/verification/ingestion_metadata_preflight.py",
        generator_sha256=hashlib.sha256(
            v1.raw_file(Path(__file__).absolute(), 2_000_000)
        ).hexdigest()
        if bind_generator
        else None,
        private_rows=None,
    )
    result["binding_errors"] = (
        [] if bind_generator else ["GENERATOR_NOT_OBSERVED"]
    ) + ["CONFIG_NOT_OBSERVED", "SOURCE_NOT_OBSERVED"]
    result["budgets"].update(
        sql_commands=MAX_REQUESTS,
        cleanup_rollbacks=2,
        process_census="linux-proc" if sys.platform == "linux" else "ps",
    )
    return result


def _bind(result, config, root):
    result["source"] = source_snapshot(
        root,
        kind=config.get("source_kind", "git-checkout"),
        manifest_sha256=config.get("source_manifest_sha256"),
    )
    raw = budget.canonical(config)
    require(len(raw) <= v1.MAX_BYTES, "CONFIG_TOO_LARGE")
    result["config_sha256"] = hashlib.sha256(raw).hexdigest()
    result["binding_errors"] = [
        x
        for x in result["binding_errors"]
        if x not in ("CONFIG_NOT_OBSERVED", "SOURCE_NOT_OBSERVED")
    ]


def _connection_run(config, credential, root, result):
    connection = None
    failure = None
    try:
        check_config(config)
        before = source_identity(config, root)
        params = connection_parameters(config, credential)
        import psycopg2

        result["runtime"].update(
            driver=psycopg2.__version__.split()[0],
            libpq=psycopg2.extensions.libpq_version(),
        )
        require(result["runtime"]["driver"] == DRIVER, "DRIVER_UNSUPPORTED")
        connection = psycopg2.connect(**params)
        observed, records = inspect(connection, config)
        require(source_identity(config, root) == before, "SOURCE_CHANGED_DURING_RUN")
        result.update(
            status="OBSERVED_READ_CHECKS_ONLY",
            observation=observed,
            private_rows=records,
        )
    except budget.EvidenceError as error:
        failure = str(error)
    except Exception:
        failure = "INSPECTION_FAILED"
    finally:
        if connection is not None:
            try:
                rollback(connection)
            except Exception:
                failure = "CLEANUP_FAILED"
            try:
                connection.close()
            except Exception:
                failure = "CLEANUP_FAILED"
    if failure:
        result.update(
            status="REFUSED", observation=None, private_rows=None, errors=[failure]
        )
    return result


REFUSALS = v1.WORKER_REFUSALS | frozenset(
    {
        "PROFILE_REFUSED",
        "TEMP_CONTRACT_REQUIRED",
        "TRANSPORT_REFUSED",
        "SESSION_TLS_IDENTITY_REQUIRED",
        "CERTIFICATE_REQUIRED",
        "CERTIFICATE_MISMATCH",
        "INTERFACE_IDENTITY_REQUIRED",
        "INTERFACE_CONTRACT_REFUSED",
        "CLIENT_TLS_UNVERIFIED",
        "CLEAN_SESSION_UNVERIFIED",
        "SESSION_CHANGED",
        "INTERFACE_DRIFT",
        "DIRTY_TRANSACTION_REFUSED",
        "SOURCE_KIND_REFUSED",
        "SOURCE_MANIFEST_REFUSED",
        "ADMISSION_BYTES_MISMATCH",
        "ROLE_PROFILE_REFUSED",
    }
)


def _validate_worker_report(child, parent, config):
    code = "WORKER_REPORT_INVALID"
    require(type(child) is dict and set(child) == set(parent), code)
    mutable = {
        "generated_at",
        "runtime",
        "status",
        "errors",
        "observation",
        "private_rows",
    }
    for key in set(parent) - mutable - {"worker_cleanup"}:
        require(budget.canonical(child[key]) == budget.canonical(parent[key]), code)
    require(child["worker_cleanup"] is None, code)
    require(
        budget.instant(parent["generated_at"])
        <= budget.instant(child["generated_at"])
        <= datetime.now(timezone.utc),
        code,
    )
    runtime = child["runtime"]
    require(
        type(runtime) is dict
        and set(runtime) in ({"python", "driver"}, {"python", "driver", "libpq"})
        and runtime["python"] == parent["runtime"]["python"]
        and runtime["driver"] in (None, DRIVER),
        code,
    )
    if "libpq" in runtime:
        require(
            type(runtime["libpq"]) is int and 100000 <= runtime["libpq"] <= 999999, code
        )
    if child["status"] == "REFUSED":
        require(
            child["observation"] is None
            and child["private_rows"] is None
            and type(child["errors"]) is list
            and len(child["errors"]) == 1
            and type(child["errors"][0]) is str
            and child["errors"][0] in REFUSALS,
            code,
        )
    else:
        require(
            child["status"] == "OBSERVED_READ_CHECKS_ONLY"
            and child["errors"] == []
            and runtime["driver"] == DRIVER
            and "libpq" in runtime,
            code,
        )
        expected = verify_records(
            config, child["private_rows"], config["mode"] == "hosted"
        )
        require(
            budget.canonical(expected) == budget.canonical(child["observation"]), code
        )


def run(config, *, execute=False, credential=None, root=ROOT):
    result, held = report(bind_generator=False), False
    try:
        held = v1._RUN_LOCK.acquire(blocking=False)
        require(held, "CONCURRENT_RUN_REFUSED")
        with v1.deadline():
            result = report()
            check_config(config)
            _bind(result, config, root)
            config = json.loads(budget.canonical(config))
            check_config(config)
            require(execute is True, "EXECUTION_NOT_AUTHORIZED")
            require(
                not any(k.startswith("PG") for k in os.environ), "AMBIENT_LIBPQ_REFUSED"
            )
            require(sys.version_info[:2] in ((3, 12), (3, 13)), "RUNTIME_UNSUPPORTED")
            source_identity(config, root)
            # The parent replays child evidence, so its own consumers must also
            # be the admitted bytes when an API caller supplies another root.
            require(
                all(
                    hashlib.sha256(v1.raw_file(ROOT / n, 2_000_000)).hexdigest()
                    == config["source_files"][n]
                    for n in SOURCE_FILES
                ),
                "SOURCE_BYTES_MISMATCH",
            )
            connection_parameters(config, credential)
            v1._check_deadline()
            packet = budget.canonical(
                dict(
                    version=2,
                    execute=True,
                    config=config,
                    credential=credential,
                    root=str(root),
                )
            )
            observed = v1.worker.bounded(
                packet,
                seconds=signal.getitimer(signal.ITIMER_REAL)[0],
                census=result["budgets"]["process_census"],
                source_root=root,
            )
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
            v1._RUN_LOCK.release()
    result.pop("private_rows", None)
    return result


def _main(argv=None):
    result = report()
    try:
        parser = budget.SafeParser(description=__doc__)
        parser.add_argument("--execute-read-only", action="store_true")
        parser.add_argument("--reviewed-admission", type=Path)
        parser.add_argument("--expected-admission-sha256")
        parser.add_argument("--out", type=Path)
        args = parser.parse_args(argv)
        require(
            bool(args.reviewed_admission) == bool(args.expected_admission_sha256),
            "ADMISSION_HASH_REQUIRED",
        )
        config = v1.load(
            args.reviewed_admission or CONFIG,
            args.expected_admission_sha256,
            receipt=result,
        )
        check_config(config)
        _bind(result, config, ROOT)
        if args.out:
            v1.output_destination(args.out)
        raw_sha = result["policy_raw_sha256"]
        result = run(
            config,
            execute=args.execute_read_only,
            credential=os.environ.get("INGESTION_PREFLIGHT_DATABASE_URL"),
        )
        result["policy_raw_sha256"] = raw_sha
        if args.out:
            v1.publish(result, args.out)
        return (0 if result["status"] == "OBSERVED_READ_CHECKS_ONLY" else 1), result
    except budget.EvidenceError as error:
        result.update(status="REFUSED", observation=None, errors=[str(error)])
    except Exception:
        result.update(
            status="REFUSED", observation=None, errors=["ADMISSION_OR_OUTPUT_REFUSED"]
        )
    result.pop("private_rows", None)
    return 2, result


def main(argv=None):
    try:
        with v1.deadline():
            code, result = _main(argv)
            raw = budget.canonical(result).decode()
    except Exception:
        result = report(bind_generator=False)
        result.pop("private_rows", None)
        result["errors"] = ["CLI_DEADLINE_OR_CONTEXT_REFUSED"]
        code, raw = 2, budget.canonical(result).decode()
    print(raw)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

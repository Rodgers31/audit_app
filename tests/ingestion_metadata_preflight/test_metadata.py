from copy import deepcopy
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from conftest import tool, ROOT


def test_real_private_worker(config, credential):
    result = tool.run(config, execute=True, credential=credential)
    assert result["status"] == "OBSERVED_READ_CHECKS_ONLY", result
    assert result["errors"] == []
    assert (
        result["safe_to_write"]
        is result["production_authorized"]
        is result["free_ready"]
        is False
    )
    assert result["worker_cleanup"]["reaped"] is True
    assert result["worker_cleanup"]["group_absent"] is True
    assert result["worker_cleanup"]["forced"] is False
    assert result["observation"]["sql_commands"] == 29
    assert result["observation"]["physical_backend_freshness"] == "NOT_CLAIMED"
    raw = json.dumps(result)
    assert "owned-reader-only" not in raw and "PRIVATE-RECORD" not in raw
    assert "private_rows" not in result


def test_role_is_execute_only(owner, connection):
    with connection.cursor() as c:
        for table in (*tool.v1.TABLES, "private_sentinel"):
            with pytest.raises(Exception):
                c.execute("SELECT * FROM public." + table)
        c.execute(
            "SELECT pg_has_role(current_user,'pg_read_all_stats','MEMBER'),"
            "has_database_privilege(current_database(),'TEMP')"
        )
        assert c.fetchone() == (False, True)
        with pytest.raises(Exception):
            c.execute("CREATE TABLE public.bad(id integer)")


@pytest.mark.parametrize(
    "table,columns,values",
    [
        ("seeding_domain_claims", "released_at", "NULL"),
        ("etl_dispatch_domains", "ready", "NULL"),
        (
            "etl_dispatch_domains",
            "command_id",
            "'00000000-0000-0000-0000-000000000001'",
        ),
        ("etl_dispatch_worker", "ready", "true"),
        ("etl_dispatch_worker", "ready", "NULL"),
        ("etl_dispatch_commands", "status", "NULL"),
        ("etl_dispatch_commands", "status", "'unknown'"),
        ("etl_dispatch_commands", "status", "'queued'"),
        ("ingestion_jobs", "status", "NULL"),
        ("ingestion_jobs", "status", "'running'"),
    ],
)
def test_hidden_retained_state_refuses(
    owner, config, credential, table, columns, values
):
    with owner.cursor() as c:
        c.execute(f"INSERT INTO public.{table}({columns}) VALUES({values})")
    try:
        result = tool.run(config, execute=True, credential=credential)
        assert result["status"] == "REFUSED"
        assert result["errors"] == ["RETAINED_OR_ACTIVE_STATE"], result
    finally:
        with owner.cursor() as c:
            c.execute("DELETE FROM public." + table)


def test_temp_from_earlier_transaction_refuses(connection, config):
    with connection.cursor() as c:
        c.execute("CREATE TEMP TABLE prior_temp(id integer)")
    with pytest.raises(tool.budget.EvidenceError, match="CLEAN_SESSION_UNVERIFIED"):
        tool.inspect(connection, config)


@pytest.mark.parametrize(
    "sql,undo",
    [
        (
            "GRANT EXECUTE ON FUNCTION audit_preflight_v2.observe() TO PUBLIC",
            "REVOKE EXECUTE ON FUNCTION audit_preflight_v2.observe() FROM PUBLIC",
        ),
        (
            "GRANT USAGE ON SCHEMA audit_preflight_v2 TO PUBLIC",
            "REVOKE USAGE ON SCHEMA audit_preflight_v2 FROM PUBLIC",
        ),
        (
            "ALTER FUNCTION audit_preflight_v2.observe() SET row_security=on",
            "ALTER FUNCTION audit_preflight_v2.observe() SET row_security=off",
        ),
        (
            "CREATE FUNCTION audit_preflight_v2.observe(integer) RETURNS boolean LANGUAGE sql AS 'SELECT false'",
            "DROP FUNCTION audit_preflight_v2.observe(integer)",
        ),
    ],
)
def test_actual_interface_drift_refuses(owner, config, credential, sql, undo):
    with owner.cursor() as c:
        c.execute(sql)
    try:
        result = tool.run(config, execute=True, credential=credential)
        assert result["status"] == "REFUSED" and result["observation"] is None, result
    finally:
        with owner.cursor() as c:
            c.execute(undo)


@pytest.mark.parametrize(
    "index,bad",
    [
        (0, None),
        (0, []),
        (1, []),
        (2, []),
        (3, []),
        (4, []),
        (5, []),
        (6, []),
        (7, []),
        (8, []),
    ],
)
def test_missing_reads_refuse(config, records, index, bad):
    records[index] = bad
    with pytest.raises((tool.budget.EvidenceError, TypeError, IndexError)):
        tool.verify_records(config, records, False)


@pytest.mark.parametrize(
    "index,value", [(0, True), (0, 0), (1, None), (2, 0), (2, None), (9, False), (9, 1)]
)
def test_malformed_observation(config, records, index, value):
    records[4][0][index] = value
    with pytest.raises(tool.budget.EvidenceError):
        tool.verify_records(config, records, False)


def test_backend_change_refuses(config, records):
    records[6][0][11] += 1
    with pytest.raises(tool.budget.EvidenceError, match="SESSION_CHANGED"):
        tool.verify_records(config, records, False)


@pytest.mark.parametrize("bad", [None, {}, [], True, float("nan"), float("inf")])
def test_bad_config_directly_refuses(bad):
    result = tool.run(bad, execute=True, credential="not-a-credential")
    assert result["status"] == "REFUSED" and result["observation"] is None


def test_disabled_has_no_connect(monkeypatch, config, credential):
    import psycopg2

    monkeypatch.setattr(
        psycopg2, "connect", lambda **_: pytest.fail("must not connect")
    )
    config["accepted"] = False
    result = tool.run(config, execute=True, credential=credential)
    assert result["errors"] == ["ADMISSION_DISABLED"]


@pytest.mark.parametrize(
    "key", ["safe_to_write", "production_authorized", "free_ready"]
)
def test_private_worker_cannot_promote_authority(config, records, key):
    parent = tool.report()
    tool._bind(parent, config, ROOT)
    child = deepcopy(parent)
    child.update(
        status="OBSERVED_READ_CHECKS_ONLY",
        private_rows=records,
        observation=tool.verify_records(config, records, False),
    )
    child["runtime"].update(driver=tool.DRIVER, libpq=170000)
    child[key] = True
    with pytest.raises(tool.budget.EvidenceError, match="WORKER_REPORT_INVALID"):
        tool._validate_worker_report(child, parent, config)


def test_summary_only_worker_refuses(config, records):
    parent = tool.report()
    tool._bind(parent, config, ROOT)
    child = deepcopy(parent)
    child.update(
        status="OBSERVED_READ_CHECKS_ONLY",
        private_rows=None,
        observation=tool.verify_records(config, records, False),
    )
    child["runtime"].update(driver=tool.DRIVER, libpq=170000)
    with pytest.raises(tool.budget.EvidenceError):
        tool._validate_worker_report(child, parent, config)


def test_v1_still_rejects_public_temporary(config):
    assert "CREATE,TEMP" in tool.v1.IDENTITY_SQL
    assert tool.v1.MAX_REQUESTS == 24
    with pytest.raises(tool.budget.EvidenceError, match="ADMISSION_DISABLED"):
        tool.v1.check_config(tool.v1.load(tool.v1.CONFIG))


@pytest.mark.parametrize(
    "grant,revoke",
    [
        (
            "GRANT pg_read_all_stats TO b71_preflight_reader",
            "REVOKE pg_read_all_stats FROM b71_preflight_reader",
        ),
        (
            "GRANT pg_write_all_data TO b71_preflight_reader",
            "REVOKE pg_write_all_data FROM b71_preflight_reader",
        ),
        (
            "GRANT INSERT ON private_sentinel TO b71_preflight_reader",
            "REVOKE INSERT ON private_sentinel FROM b71_preflight_reader",
        ),
    ],
)
def test_installer_refuses_effective_access(owner, grant, revoke):
    with owner.cursor() as c:
        c.execute("DROP SCHEMA audit_preflight_v2 CASCADE")
        c.execute(grant)
        try:
            with pytest.raises(
                Exception, match="PREFLIGHT_(READER_ACCESS|ROLE_GRAPH)_REFUSED"
            ):
                c.execute(tool.contract.installation_sql("b71_preflight_reader"))
        finally:
            c.execute("ROLLBACK")
            c.execute(revoke)
            c.execute("DROP SCHEMA IF EXISTS audit_preflight_v2 CASCADE")
            c.execute(tool.contract.installation_sql("b71_preflight_reader"))


@pytest.mark.parametrize(
    "suffix",
    ["?options=-c%20row_security=on", "?service=other", "?sslmode=disable", "#ignored"],
)
def test_dsn_options_refuse(config, credential, suffix):
    with pytest.raises(tool.budget.EvidenceError, match="CREDENTIAL_FORMAT_REFUSED"):
        tool.connection_parameters(config, credential + suffix)


def instrument_metadata_worker(monkeypatch, code):
    original = tool.v1.worker.Popen
    bootstrap = (
        "import sys,time\nfrom pathlib import Path\n"
        f"sys.path.insert(0,{str(ROOT/'scripts/verification')!r})\n"
        "import ingestion_metadata_preflight as metadata\n"
        "import ingestion_preflight_worker as worker\n"
        + code
        + "\nraise SystemExit(worker._child_main())\n"
    )

    def launch(command, **kwargs):
        assert Path(command[-1]) == Path(tool.v1.worker.__file__).absolute()
        return original([command[0], "-I", "-B", "-c", bootstrap], **kwargs)

    monkeypatch.setattr(tool.v1.worker, "Popen", launch)


def test_actual_timeout_kills_and_reaps_worker(config, credential, monkeypatch):
    instrument_metadata_worker(monkeypatch, "metadata.inspect=lambda *_: time.sleep(5)")
    monkeypatch.setattr(tool.v1, "RUN_SECONDS", 0.7)
    result = tool.run(config, execute=True, credential=credential)
    assert result["status"] == "REFUSED" and result["observation"] is None
    assert result["worker_cleanup"]["reaped"] is True
    assert result["worker_cleanup"]["group_absent"] is True
    assert result["worker_cleanup"]["forced"] is True


def test_missing_actual_worker_observations_refuse(config, credential, monkeypatch):
    instrument_metadata_worker(
        monkeypatch, "metadata.inspect=lambda *_: ({'checks':{}},[])"
    )
    result = tool.run(config, execute=True, credential=credential)
    assert result["status"] == "REFUSED" and result["errors"] == [
        "WORKER_REPORT_INVALID"
    ]
    assert result["worker_cleanup"]["group_absent"] is True


def test_actual_connection_cleanup_failure_refuses(config, credential, monkeypatch):
    instrument_metadata_worker(
        monkeypatch,
        """import psycopg2
original=psycopg2.connect
class Connection:
 def __init__(self,c): object.__setattr__(self,'c',c)
 def __getattr__(self,k): return getattr(self.c,k)
 def __setattr__(self,k,v): setattr(self.c,k,v)
 def close(self):
  self.c.close()
  raise ValueError('PRIVATE-DRIVER-DIAGNOSTIC')
psycopg2.connect=lambda **kwargs: Connection(original(**kwargs))
""",
    )
    result = tool.run(config, execute=True, credential=credential)
    assert result["status"] == "REFUSED" and result["errors"] == ["CLEANUP_FAILED"]
    assert "PRIVATE-DRIVER" not in json.dumps(result)


def test_second_transaction_detects_actual_definition_drift(owner, config, connection):
    class Connection:
        info = connection.info

        def get_transaction_status(self):
            return connection.get_transaction_status()

        def cursor(self):
            return connection.cursor()

        @property
        def autocommit(self):
            return connection.autocommit

        @autocommit.setter
        def autocommit(self, value):
            connection.autocommit = value

        def rollback(self):
            connection.rollback()
            with owner.cursor() as c:
                c.execute(
                    "ALTER FUNCTION audit_preflight_v2.observe() SET row_security=on"
                )

    try:
        with pytest.raises(tool.budget.EvidenceError, match="INTERFACE_DRIFT"):
            tool.inspect(Connection(), config)
    finally:
        connection.rollback()
        with owner.cursor() as c:
            c.execute(
                "ALTER FUNCTION audit_preflight_v2.observe() SET row_security=off"
            )


def test_sql_allowlist_and_row_ceiling():
    class Cursor:
        def execute(self, *args):
            pass

        def fetchmany(self, n):
            return [(False,)] * n

    reads = tool.Reads(Cursor())
    with pytest.raises(tool.budget.EvidenceError, match="SQL_NOT_ALLOWLISTED"):
        reads.command("CREATE TEMP TABLE forbidden(id integer)")
    with pytest.raises(tool.budget.EvidenceError, match="ROW_BUDGET_EXCEEDED"):
        reads.read(tool.contract.OBSERVE_SQL)


def test_cli_disabled_does_not_connect(capsys):
    assert tool.main([]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["errors"] == ["ADMISSION_DISABLED"]
    assert result["worker_cleanup"] is None and result["observation"] is None


def test_installer_rolls_back_unexpected_default_function_access(owner):
    with owner.cursor() as c:
        c.execute("DROP SCHEMA audit_preflight_v2 CASCADE")
        c.execute("CREATE ROLE b71_extra NOLOGIN")
        c.execute("ALTER DEFAULT PRIVILEGES GRANT EXECUTE ON FUNCTIONS TO b71_extra")
        try:
            with pytest.raises(Exception, match="PREFLIGHT_DEFAULT_ACCESS_REFUSED"):
                c.execute(tool.contract.installation_sql("b71_preflight_reader"))
            c.execute("ROLLBACK")
            c.execute("SELECT to_regnamespace('audit_preflight_v2')")
            assert c.fetchone() == (None,)
        finally:
            c.execute("ROLLBACK")
            c.execute(
                "ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM b71_extra"
            )
            c.execute("DROP SCHEMA IF EXISTS audit_preflight_v2 CASCADE")
            c.execute("DROP ROLE b71_extra")
            c.execute(tool.contract.installation_sql("b71_preflight_reader"))


def test_unexpected_reader_membership_refuses(owner, config, credential):
    with owner.cursor() as c:
        c.execute("CREATE ROLE b71_unexpected NOLOGIN")
        c.execute("GRANT b71_unexpected TO b71_preflight_reader")
    try:
        result = tool.run(config, execute=True, credential=credential)
        assert result["status"] == "REFUSED" and result["errors"] == [
            "INTERFACE_DRIFT"
        ], result
    finally:
        with owner.cursor() as c:
            c.execute("REVOKE b71_unexpected FROM b71_preflight_reader")
            c.execute("DROP ROLE b71_unexpected")


def test_preexisting_transaction_refuses(owner, connection, config):
    with connection.cursor() as c:
        c.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        c.execute("SELECT count(*) FROM pg_catalog.pg_class")
    with pytest.raises(tool.budget.EvidenceError, match="DIRTY_TRANSACTION_REFUSED"):
        tool.inspect(connection, config)
    tool.rollback(connection)


@pytest.fixture
def source_bundle(config, tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    for name in tool.SOURCE_FILES:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, root / name)
    manifest = dict(
        version=1,
        execution_head=config["execution_head"],
        source_files=config["source_files"],
    )
    raw = tool.budget.canonical(manifest)
    (root / tool.MANIFEST).write_bytes(raw)
    config["source_kind"] = "reviewed-bundle"
    config["source_manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    return root, config


def test_actual_bundled_cli_without_git(source_bundle, credential, tmp_path):
    root, config = source_bundle
    admission = tmp_path / "admission.json"
    admission.write_bytes(tool.budget.canonical(config))
    environment = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    environment.update(PATH="/nonexistent", INGESTION_PREFLIGHT_DATABASE_URL=credential)
    p = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(root / "scripts/verification/ingestion_metadata_preflight.py"),
            "--reviewed-admission",
            str(admission),
            "--expected-admission-sha256",
            hashlib.sha256(admission.read_bytes()).hexdigest(),
            "--execute-read-only",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=35,
    )
    result = json.loads(p.stdout)
    assert p.returncode == 0 and result["status"] == "OBSERVED_READ_CHECKS_ONLY", result
    assert result["source"]["kind"] == "reviewed-bundle"
    assert result["worker_cleanup"]["group_absent"] is True
    assert credential not in p.stdout


@pytest.mark.parametrize(
    "mutation",
    ["missing-manifest", "wrong-manifest-hash", "changed-file", "malformed-manifest"],
)
def test_reviewed_bundle_refuses_drift(source_bundle, mutation):
    root, config = source_bundle
    if mutation == "missing-manifest":
        (root / tool.MANIFEST).unlink()
    elif mutation == "wrong-manifest-hash":
        config["source_manifest_sha256"] = "0" * 64
    elif mutation == "changed-file":
        (root / tool.SOURCE_FILES[0]).write_text("changed")
    else:
        raw = b"{}"
        (root / tool.MANIFEST).write_bytes(raw)
        config["source_manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises((tool.budget.EvidenceError, FileNotFoundError)):
        tool.source_identity(config, root)


def test_recreated_relation_cannot_hide_retained_claim(owner, config, credential):
    with owner.cursor() as c:
        c.execute("INSERT INTO public.seeding_domain_claims VALUES(NULL)")
        c.execute(
            "ALTER TABLE public.seeding_domain_claims RENAME TO b72_original_claims"
        )
        c.execute("CREATE TABLE public.seeding_domain_claims(released_at timestamptz)")
        c.execute("ALTER TABLE public.seeding_domain_claims ENABLE ROW LEVEL SECURITY")
        c.execute(
            "CREATE POLICY hidden ON public.seeding_domain_claims FOR SELECT USING(false)"
        )
    try:
        result = tool.run(config, execute=True, credential=credential)
        assert result["status"] == "REFUSED" and result["errors"] == [
            "SCHEMA_MISMATCH"
        ], result
    finally:
        with owner.cursor() as c:
            c.execute("DROP TABLE public.seeding_domain_claims")
            c.execute(
                "ALTER TABLE public.b72_original_claims RENAME TO seeding_domain_claims"
            )
            c.execute("DELETE FROM public.seeding_domain_claims")


def test_api_worker_launches_from_reviewed_bundle(
    source_bundle, credential, monkeypatch
):
    root, config = source_bundle
    original = tool.v1.worker.Popen
    launched = []

    def launch(command, **kwargs):
        launched.append(command[-1])
        return original(command, **kwargs)

    monkeypatch.setattr(tool.v1.worker, "Popen", launch)
    result = tool.run(config, root=root, execute=True, credential=credential)
    assert result["status"] == "OBSERVED_READ_CHECKS_ONLY", result
    assert launched == [
        str(root / "scripts/verification/ingestion_preflight_worker.py")
    ]
    assert result["worker_cleanup"]["group_absent"] is True


@pytest.mark.parametrize("column", [10, 11])
@pytest.mark.parametrize("bad", [None, True, 0, -1, 2**32, "123", float("nan")])
def test_schema_object_identity_must_be_typed_oid(config, records, column, bad):
    # Even an independently supplied hash cannot admit malformed object IDs.
    records[2][0][column] = bad
    config["schema_sha256"] = "0" * 64
    with pytest.raises(tool.budget.EvidenceError, match="SCHEMA_INCOMPLETE"):
        tool.verify_records(config, records, False)


@pytest.mark.parametrize("phase", [2, 7])
@pytest.mark.parametrize("column", [10, 11])
def test_schema_identity_drift_refuses_either_snapshot(config, records, phase, column):
    records[phase][0][column] += 1
    with pytest.raises(tool.budget.EvidenceError, match="SCHEMA_MISMATCH"):
        tool.verify_records(config, records, False)


def test_api_rejects_unpinned_caller_before_worker(
    source_bundle, credential, monkeypatch
):
    root, config = source_bundle
    name = "scripts/verification/ingestion_metadata_preflight.py"
    (root / name).write_bytes((root / name).read_bytes() + b"\n# changed consumer\n")
    config["source_files"][name] = hashlib.sha256(
        (root / name).read_bytes()
    ).hexdigest()
    manifest = dict(
        version=1,
        execution_head=config["execution_head"],
        source_files=config["source_files"],
    )
    raw = tool.budget.canonical(manifest)
    (root / tool.MANIFEST).write_bytes(raw)
    config["source_manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(
        tool.v1.worker,
        "bounded",
        lambda *a, **k: pytest.fail("unpinned caller must not launch"),
    )
    result = tool.run(config, root=root, execute=True, credential=credential)
    assert result["status"] == "REFUSED" and result["errors"] == [
        "SOURCE_BYTES_MISMATCH"
    ]
    assert result["worker_cleanup"] is None

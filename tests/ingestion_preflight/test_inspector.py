from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import psycopg2
import pytest

from conftest import ROOT, tool


def capture(config, credential):
    return tool.run(config, execute=True, credential=credential)


def owned_snapshot(pg):
    """Fixture data/catalog/access oracle, excluding unrelated global WAL/stats."""
    with pg.cursor() as c:
        c.execute(
            "SELECT c.relname,c.relkind,c.relowner,c.relacl::text,c.relrowsecurity,c.relforcerowsecurity,a.attnum,a.attname,a.atttypid,a.atttypmod,a.attnotnull FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid WHERE n.nspname='public' AND a.attnum>0 ORDER BY c.relname,a.attnum"
        )
        schema = c.fetchall()
        c.execute(
            "SELECT rolname,rolsuper,rolcreaterole,rolcreatedb,rolcanlogin,rolreplication,rolbypassrls,rolconnlimit FROM pg_roles ORDER BY rolname"
        )
        roles = c.fetchall()
        c.execute(
            "SELECT roleid,member,grantor,admin_option FROM pg_auth_members ORDER BY roleid,member,grantor"
        )
        memberships = c.fetchall()
        tables = {}
        for name in (*tool.TABLES, "private_sentinel"):
            c.execute(
                "SELECT row_to_json(t)::text FROM public."
                + name
                + " t ORDER BY row_to_json(t)::text"
            )
            tables[name] = c.fetchall()
    return tool.budget.content_hash(
        {"schema": schema, "roles": roles, "memberships": memberships, "tables": tables}
    )


def test_actual_entrypoint_valid_readonly_and_no_database_mutation(
    config, credential, pg, tmp_path
):
    before = owned_snapshot(pg)
    with pg.cursor() as c:
        c.execute("SELECT * FROM public.private_sentinel")
        private = c.fetchall()
    config_path = tmp_path / "expected.json"
    config_path.write_text(json.dumps(config))
    out = tmp_path / "receipt.json"
    env = {"PATH": os.environ["PATH"], "INGESTION_PREFLIGHT_DATABASE_URL": credential}
    r = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "scripts/verification/ingestion_preflight.py"),
            "--owned-local-config",
            str(config_path),
            "--execute-read-only",
            "--out",
            str(out),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=35,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    result = json.loads(r.stdout)
    assert json.loads(out.read_bytes()) == result
    assert result["status"] == "OBSERVED_READ_CHECKS_ONLY"
    assert (
        result["safe_to_write"]
        is result["production_authorized"]
        is result["free_ready"]
        is False
    )
    assert (
        result["custody_operator_gate"] == "UNMET"
        and result["receipt_backend_gate"] == "NOT_OBSERVED"
    )
    assert result["observation"]["read_requests"] == 11
    assert result["observation"]["sql_commands"] == 19
    assert all(x is False for x in result["observation"]["checks"].values())
    assert (
        result["generator_sha256"]
        == hashlib.sha256(
            (ROOT / "scripts/verification/ingestion_preflight.py").read_bytes()
        ).hexdigest()
    )
    assert result["config_sha256"] == tool.budget.content_hash(config)
    with pg.cursor() as c:
        c.execute("SELECT * FROM public.private_sentinel")
        assert c.fetchall() == private
        c.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE application_name='b66-ingestion-preflight'"
        )
        assert c.fetchone()[0] == 0
    assert owned_snapshot(pg) == before
    assert credential not in r.stdout + r.stderr + out.read_text()
    assert "owned-reader-only" not in r.stdout + r.stderr + out.read_text()
    assert "PRIVATE-RECORD" not in r.stdout + r.stderr + out.read_text()


@pytest.mark.parametrize(
    "key,value,code",
    [
        ("oid", 123, "DATABASE_ROLE_MISMATCH"),
        ("role_oid", 123, "TLS_OR_SESSION_UNVERIFIED"),
        ("name", "b66_preflight_wrong", "CREDENTIAL_IDENTITY_MISMATCH"),
        ("role", "wrong_reader", "CREDENTIAL_IDENTITY_MISMATCH"),
        ("tls", "verify-full", "OWNED_FIXTURE_REQUIRED"),
    ],
)
def test_wrong_database_role_tls_refuses(config, credential, key, value, code):
    config["database"][key] = value
    result = capture(config, credential)
    assert result["status"] == "REFUSED" and result["errors"] == [code]


@pytest.mark.parametrize(
    "key,value,code",
    [
        ("execution_head", "0" * 40, "SOURCE_HEAD_MISMATCH"),
        ("schema_sha256", "0" * 64, "SCHEMA_MISMATCH"),
        ("revision", "wrongrevision", "REVISION_MISMATCH"),
    ],
)
def test_wrong_source_schema_revision(config, credential, key, value, code):
    config[key] = value
    assert capture(config, credential)["errors"] == [code]


@pytest.mark.parametrize(
    "bad", [None, {}, [], "", True, 0, 1, float("nan"), float("inf"), -1]
)
def test_malformed_config_never_calls_driver(monkeypatch, bad):
    monkeypatch.setattr(
        psycopg2, "connect", lambda **_: pytest.fail("must refuse before connecting")
    )
    result = tool.run(bad, execute=True, credential="TOY-SECRET")
    assert result["status"] == "REFUSED" and result["observation"] is None


@pytest.mark.parametrize(
    "field",
    [
        "version",
        "accepted",
        "execution_head",
        "source_files",
        "database",
        "schema_sha256",
        "revision",
        "receipt_authority",
    ],
)
@pytest.mark.parametrize(
    "bad", [None, {}, [], "", True, False, 0, -1, float("nan"), float("inf"), "failed"]
)
def test_boundary_shapes(config, credential, field, bad):
    config[field] = bad
    if field == "accepted" and bad is True:
        assert capture(config, credential)["status"] == "OBSERVED_READ_CHECKS_ONLY"
        return
    assert capture(config, credential)["status"] == "REFUSED"


@pytest.mark.parametrize("flag", [None, "true", "false", 1, 0, {}, [], False])
def test_direct_call_cannot_bypass_execute(config, credential, flag):
    result = tool.run(config, execute=flag, credential=credential)
    assert result["errors"] == ["EXECUTION_NOT_AUTHORIZED"]


def test_disabled_receipt_authority_and_unknowns_refuse(config, credential):
    config["receipt_authority"]["state"] = "disabled"
    assert capture(config, credential)["errors"] == ["RECEIPT_AUTHORITY_UNACCEPTED"]


def test_retained_uncertain_claim_refuses_without_releasing(config, credential, pg):
    with pg.cursor() as c:
        c.execute(
            "INSERT INTO public.seeding_domain_claims VALUES ('00000000-0000-0000-0000-000000000001','audits',NULL,now(),NULL,'UNCERTAIN-PRIVATE')"
        )
    try:
        result = capture(config, credential)
        assert result["errors"] == ["RETAINED_OR_ACTIVE_STATE"]
        assert "UNCERTAIN-PRIVATE" not in json.dumps(result)
        with pg.cursor() as c:
            c.execute("SELECT released_at FROM public.seeding_domain_claims")
            assert c.fetchall() == [(None,)]
    finally:
        with pg.cursor() as c:
            c.execute("DELETE FROM public.seeding_domain_claims")


def test_unrelated_active_writer_refuses(config, credential):
    writer = psycopg2.connect(
        host="127.0.0.1",
        port=56972,
        dbname="b66_preflight_owned",
        user="postgres",
        password="b66-owned-only",
    )
    with writer.cursor() as c:
        c.execute(
            "UPDATE public.private_sentinel SET secret_value='UNCOMMITTED-WRITER'"
        )
    try:
        assert capture(config, credential)["errors"] == ["RETAINED_OR_ACTIVE_STATE"]
    finally:
        writer.rollback()
        writer.close()


def test_real_query_lock_timeout_and_cleanup(config, credential, pg):
    # Simulate an unrelated schema writer locking the narrow retained-claim table.
    locker = psycopg2.connect(
        host="127.0.0.1",
        port=56972,
        dbname="b66_preflight_owned",
        user="postgres",
        password="b66-owned-only",
    )
    with locker.cursor() as c:
        c.execute("LOCK TABLE public.seeding_domain_claims IN ACCESS EXCLUSIVE MODE")
    start = time.monotonic()
    try:
        result = capture(config, credential)
        assert result["status"] == "REFUSED" and result["errors"] == [
            "INSPECTION_FAILED"
        ]
        assert time.monotonic() - start < 5
    finally:
        locker.rollback()
        locker.close()


def test_real_statement_timeout(config, credential, monkeypatch):
    original = tool.CHECKS["retained_claim"]
    # Test-only mutation of an allowlisted constant, never a public SQL parameter.
    monkeypatch.setitem(
        tool.CHECKS, "retained_claim", "SELECT pg_catalog.pg_sleep(3) IS NULL"
    )
    start = time.monotonic()
    result = capture(config, credential)
    assert result["status"] == "REFUSED" and time.monotonic() - start < 5


def test_real_readonly_blocks_write_independent_of_acl(
    config, credential, monkeypatch, pg
):
    # Owner connection proves READ ONLY, even when ACL would allow the DML.
    original = tool.Reads.one
    seen = []

    def attack(self, sql, params=None):
        if sql == tool.IDENTITY_SQL:
            try:
                self.cursor.execute(
                    "UPDATE public.private_sentinel SET secret_value='ILLEGAL'"
                )
            except psycopg2.Error as error:
                seen.append(error.pgcode)
                raise
        return original(self, sql, params)

    monkeypatch.setattr(tool.Reads, "one", attack)
    owner = psycopg2.connect(
        host="127.0.0.1",
        port=56972,
        dbname="b66_preflight_owned",
        user="postgres",
        password="b66-owned-only",
        options=tool.OPTIONS,
    )
    try:
        with pytest.raises(psycopg2.Error):
            tool.inspect(owner, config)
        assert seen == ["25006"]
    finally:
        owner.rollback()
        owner.close()
    with pg.cursor() as c:
        c.execute("SELECT secret_value FROM public.private_sentinel")
        assert c.fetchone() == ("PRIVATE-RECORD-MUST-NOT-APPEAR",)


def test_incomplete_observation_never_passes(config, credential, monkeypatch):
    original = tool.Reads.one
    monkeypatch.setattr(
        tool.Reads,
        "one",
        lambda self, sql, params=None: ()
        if sql == tool.GUARDS_SQL
        else original(self, sql, params),
    )
    assert capture(config, credential)["errors"] == ["OBSERVATION_INCOMPLETE"]


def test_toy_secret_in_driver_error_is_suppressed(config, credential, monkeypatch):
    def bad_connect(**_):
        raise RuntimeError(
            "postgresql://user:TOY-SECRET@private.invalid PRIVATE-RECORD"
        )

    monkeypatch.setattr(psycopg2, "connect", bad_connect)
    result = capture(config, credential)
    assert result["errors"] == ["INSPECTION_FAILED"]
    assert "TOY-SECRET" not in json.dumps(
        result
    ) and "PRIVATE-RECORD" not in json.dumps(result)


def test_source_hash_mismatch_before_connect(config, credential, monkeypatch):
    config["source_files"]["backend/models.py"] = "0" * 64
    monkeypatch.setattr(
        psycopg2, "connect", lambda **_: pytest.fail("must refuse first")
    )
    assert capture(config, credential)["errors"] == ["SOURCE_BYTES_MISMATCH"]


@pytest.mark.parametrize(
    "suffix",
    [
        "?sslmode=disable",
        "?options=-cdefault_transaction_read_only=off",
        "?service=anything",
        "#secret",
    ],
)
def test_libpq_options_not_imported(config, credential, suffix):
    assert capture(config, credential + suffix)["errors"] == [
        "CREDENTIAL_FORMAT_REFUSED"
    ]


def test_ambient_libpq_and_concurrency_refuse(config, credential, monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "TOY-SECRET")
    assert capture(config, credential)["errors"] == ["AMBIENT_LIBPQ_REFUSED"]
    monkeypatch.delenv("PGPASSWORD")
    with tool._RUN_LOCK:
        assert capture(config, credential)["errors"] == ["CONCURRENT_RUN_REFUSED"]


def test_shipped_admission_cannot_read_credentials(monkeypatch, capsys):
    monkeypatch.setenv("INGESTION_PREFLIGHT_DATABASE_URL", "TOY-SECRET")
    monkeypatch.setattr(psycopg2, "connect", lambda **_: pytest.fail("must refuse"))
    assert tool.main(["--execute-read-only"]) == 2
    output = capsys.readouterr().out
    assert "TOY-SECRET" not in output and json.loads(output)["status"] == "REFUSED"


def test_exclusive_bounded_regular_output_and_readback(tmp_path):
    destination = tmp_path / "fresh.json"
    value = tool.report()
    tool.publish(value, destination)
    assert tool.load(destination) == value
    with pytest.raises(tool.budget.EvidenceError):
        tool.publish(value, destination)
    link = tmp_path / "link.json"
    link.symlink_to(destination)
    with pytest.raises(tool.budget.EvidenceError):
        tool.load(link)
    fifo = tmp_path / "fifo.json"
    os.mkfifo(fifo)
    with pytest.raises(tool.budget.EvidenceError):
        tool.load(fifo)
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"x":1,"x":2}')
    with pytest.raises(tool.budget.EvidenceError):
        tool.load(duplicate)


def test_sql_not_allowlisted_refuses_before_execute():
    class Cursor:
        def execute(self, *_):
            pytest.fail("must refuse arbitrary SQL")

    with pytest.raises(tool.budget.EvidenceError, match="SQL_NOT_ALLOWLISTED"):
        tool.Reads(Cursor()).read("SELECT 1; DROP TABLE private_sentinel")


def test_output_dotdot_cannot_publish_inside_inspected_source():
    candidate = (
        ROOT.parent / ".." / ROOT.parent.name / ROOT.name / "refused-review-output.json"
    )
    assert candidate.resolve().is_relative_to(ROOT)
    with pytest.raises(tool.budget.EvidenceError, match="OUTPUT_PATH_REFUSED"):
        tool.output_destination(candidate)


@pytest.mark.parametrize("status", ["UNKNOWN", "PENDING", None])
def test_unknown_pending_or_null_job_never_passes(config, credential, pg, status):
    with pg.cursor() as c:
        c.execute(
            "INSERT INTO public.ingestion_jobs VALUES (1,%s,'audits','{}')", (status,)
        )
    try:
        assert capture(config, credential)["errors"] == ["RETAINED_OR_ACTIVE_STATE"]
    finally:
        with pg.cursor() as c:
            c.execute("DELETE FROM public.ingestion_jobs")


def test_unsupported_dispatch_status_never_passes(config, credential, pg):
    with pg.cursor() as c:
        c.execute(
            "INSERT INTO public.etl_dispatch_commands VALUES ('00000000-0000-0000-0000-000000000003','unknown',true)"
        )
    try:
        assert capture(config, credential)["errors"] == ["RETAINED_OR_ACTIVE_STATE"]
    finally:
        with pg.cursor() as c:
            c.execute("DELETE FROM public.etl_dispatch_commands")


def test_whole_run_deadline_is_an_executed_guard(monkeypatch):
    monkeypatch.setattr(tool, "RUN_SECONDS", 0.05)
    with pytest.raises(tool.budget.EvidenceError, match="WHOLE_RUN_TIMEOUT"):
        with tool.deadline():
            time.sleep(0.2)
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_supported_direct_call_deadline_covers_admission(monkeypatch):
    monkeypatch.setattr(tool, "RUN_SECONDS", 0.01)

    def slow_admission(_):
        time.sleep(0.1)
        pytest.fail("admission escaped deadline")

    monkeypatch.setattr(tool, "check_config", slow_admission)
    result = tool.run({}, execute=True, credential="TOY")
    assert result["errors"] == ["WHOLE_RUN_TIMEOUT"]


def test_bad_output_refuses_before_connection(
    config, credential, monkeypatch, tmp_path, capsys
):
    config_file = tmp_path / "expected.json"
    config_file.write_text(json.dumps(config))
    monkeypatch.setenv("INGESTION_PREFLIGHT_DATABASE_URL", credential)
    monkeypatch.setattr(
        psycopg2,
        "connect",
        lambda **_: pytest.fail("output must refuse before connection"),
    )
    assert (
        tool.main(
            [
                "--owned-local-config",
                str(config_file),
                "--execute-read-only",
                "--out",
                str(config_file),
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["status"] == "REFUSED"

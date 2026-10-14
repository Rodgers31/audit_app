"""Actual emitted SQL on a disposable PostgreSQL, including non-superuser use."""
import importlib.util
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from seeding import managed_legacy_release as release


@pytest.fixture
def store(monkeypatch):
    address = os.environ.get("MANAGED_RELEASE_TEST_DATABASE_URL")
    if not address:
        pytest.skip("explicit owned PostgreSQL fixture required")
    url = make_url(address)
    assert (
        url.host == "127.0.0.1"
        and url.port not in (None, 5432)
        and url.database == "codex_managed_release"
    )
    admin = create_engine(address)
    with admin.begin() as c:
        c.execute(
            text(
                "DO $$BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='managed_op') THEN CREATE ROLE managed_op NOLOGIN NOSUPERUSER BYPASSRLS CREATEROLE; END IF; END$$"
            )
        )
        c.execute(text("ALTER ROLE managed_op CREATEROLE"))
        c.execute(
            text(
                "DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION managed_op; GRANT USAGE ON SCHEMA public TO PUBLIC"
            )
        )
        c.execute(text("GRANT EXECUTE ON FUNCTION pg_control_system() TO managed_op"))
        c.execute(
            text("GRANT EXECUTE ON FUNCTION pg_control_checkpoint() TO managed_op")
        )
        c.execute(text("SET LOCAL ROLE managed_op"))
        c.exec_driver_sql(
            """CREATE TABLE alembic_version(version_num text PRIMARY KEY);
        INSERT INTO alembic_version VALUES('ea1645a4c0b5');
        CREATE TABLE ingestion_jobs(id serial PRIMARY KEY,domain text NOT NULL,status text NOT NULL,
        dry_run boolean NOT NULL,metadata jsonb NOT NULL,errors jsonb NOT NULL,
        started_at timestamp,finished_at timestamp,items_processed integer NOT NULL DEFAULT 0);
        CREATE TABLE admin_audit_log(id serial PRIMARY KEY,actor_id text,actor_email text,action text,
        target_type text,target_id text,payload jsonb,created_at timestamp);
        CREATE TABLE facts(id integer PRIMARY KEY,amount numeric NOT NULL);
        CREATE TABLE etl_dispatch_worker(ready boolean NOT NULL);
        INSERT INTO facts VALUES(1,42.75);
        INSERT INTO ingestion_jobs(domain,status,dry_run,metadata,errors,started_at)
        VALUES('national_budget','RUNNING',false,'{"since":null}','[]','2026-06-01'),
        ('fiscal_summary','RUNNING',false,'{"since":null}','[]','2026-07-04'),
        ('fiscal_summary','RUNNING',true,'{"since":null}','[]','2026-09-04');"""
        )
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        path = (
            Path(__file__).resolve().parents[1]
            / "alembic/versions/a611b12a0001_durable_admin_audit.py"
        )
        spec = importlib.util.spec_from_file_location("owned_audit_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with Operations.context(MigrationContext.configure(c)):
            migration.upgrade()
        c.execute(text("UPDATE alembic_version SET version_num='a611b12a0001'"))
    c = admin.connect()
    c.execute(text("SET ROLE managed_op; SET search_path=public; SET TimeZone='UTC'"))
    c.commit()
    try:
        yield c, admin
    finally:
        c.rollback()
        c.close()
        admin.dispose()


def policy_for(c):
    target = c.execute(
        text(
            """SELECT jsonb_build_object('database',current_database(),'database_oid',d.oid::bigint,
    'system_identifier',s.system_identifier::text,'maintenance_role',current_user,
    'revision',(SELECT version_num FROM public.alembic_version)) FROM pg_database d CROSS JOIN pg_control_system() s
    WHERE d.datname=current_database()"""
        )
    ).scalar_one()
    catalog = c.execute(text(release.CATALOG_SQL)).scalar_one()
    effects = {}
    for name in sorted(r["name"] for r in catalog if r["kind"] in ("r", "p")):
        quoted = c.dialect.identifier_preparer.quote(name)
        effects[name] = dict(
            c.execute(
                text(
                    """SELECT count(*) AS rows,
        encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') AS sha256
        FROM (SELECT encode(sha256(convert_to(to_jsonb(r)::text,'UTF8')),'hex') h FROM public."""
                    + quoted
                    + " r LIMIT 100001) x"
                )
            )
            .mappings()
            .one()
        )
    jobs = c.execute(
        text(
            "SELECT jsonb_agg(to_jsonb(j) ORDER BY id) FROM ingestion_jobs j WHERE status='RUNNING'"
        )
    ).scalar_one()
    now = c.scalar(text("SELECT clock_timestamp()"))
    c.rollback()
    return {
        "version": 2,
        "target": target,
        "catalog": catalog,
        "jobs": jobs,
        "effects": effects,
        "who": "owned-test-operator",
        "why": "Investigate exact interrupted fixture jobs",
        "effect_review": "Owned inert fixture only; no provider, financial publication or external effects.",
        "fences": {
            k: {
                "state": "absent",
                "artifact_sha256": "a" * 64,
                "description": "Owned inert fixture; launch and DDL custody held.",
            }
            for k in release.FENCES
        },
        "observed_at": now.isoformat(),
        "hold_until": (now + timedelta(minutes=4)).isoformat(),
    }


def compiled(policy, monkeypatch):
    monkeypatch.setenv("AUDIT_MANAGED_RELEASE_POLICY_SHA256", release.digest(policy))
    return release.compile_sql(policy)


def run(c, sql):
    try:
        c.exec_driver_sql(sql, execution_options={"no_parameters": True})
        c.commit()
    except Exception:
        c.rollback()
        raise


def test_non_superuser_with_another_reader_can_reconcile_exact_legacy_jobs(
    store, monkeypatch
):
    c, admin = store
    policy = policy_for(c)
    assert (
        c.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user"))
        is False
    )
    c.rollback()
    # Actual accepted old guard refuses the same nonsuperuser configuration.
    from seeding.reconciliation import ReconciliationRefused, _maintenance

    with pytest.raises(ReconciliationRefused, match="maintenance privilege"):
        _maintenance(c)
    c.rollback()
    with admin.connect() as reader:
        assert reader.scalar(text("SELECT count(*) FROM public.facts")) == 1
        run(c, compiled(policy, monkeypatch))
    result = c.execute(
        text("SELECT status,metadata,items_processed FROM ingestion_jobs ORDER BY id")
    ).all()
    assert len(result) == 3 and all(
        r.status == "FAILED" and r.items_processed == 0 for r in result
    )
    assert len({r.metadata["operator_reconciliation"]["audit_id"] for r in result}) == 1
    assert c.scalar(text("SELECT amount FROM facts")) == 42.75
    payload = c.scalar(text("SELECT payload FROM admin_audit_log"))
    assert payload["outcome"] == "execution_unverified" and payload["job_ids"] == [
        1,
        2,
        3,
    ]
    assert c.scalar(text("SELECT count(*) FROM admin_audit_provenance")) == 1
    c.rollback()
    with pytest.raises(DBAPIError):
        run(c, compiled(policy, monkeypatch))
    assert c.scalar(text("SELECT count(*) FROM admin_audit_log")) == 1


@pytest.mark.parametrize(
    "mutation",
    ["target", "extra_job", "changed_fact", "missing_job", "row_counter", "catalog"],
)
def test_changed_context_refuses_without_job_or_audit_writes(
    store, monkeypatch, mutation
):
    c, admin = store
    policy = policy_for(c)
    if mutation == "target":
        policy["target"]["database_oid"] += 1
    else:
        statement = {
            "extra_job": "INSERT INTO ingestion_jobs(domain,status,dry_run,metadata,errors) VALUES('fiscal_summary','RUNNING',false,'{}','[]')",
            "changed_fact": "UPDATE facts SET amount=99",
            "missing_job": "DELETE FROM ingestion_jobs WHERE id=1",
            "row_counter": "UPDATE ingestion_jobs SET items_processed=1 WHERE id=1",
            "catalog": "ALTER TABLE facts ADD COLUMN extra text",
        }[mutation]
        with admin.begin() as other:
            other.execute(text(statement))
    with pytest.raises(DBAPIError):
        run(c, compiled(policy, monkeypatch))
    assert c.scalar(text("SELECT count(*) FROM admin_audit_log")) == 0
    assert (
        c.scalar(text("SELECT count(*) FROM ingestion_jobs WHERE status='FAILED'")) == 0
    )


def test_competing_writer_and_domain_owner_refuse(store, monkeypatch):
    c, admin = store
    policy = policy_for(c)
    sql = compiled(policy, monkeypatch)
    with admin.connect() as other:
        other.execute(text("UPDATE facts SET amount=99"))
        with pytest.raises(DBAPIError):
            run(c, sql)
        other.rollback()
        key = int.from_bytes(
            release.sha256(b"seeding:fiscal_summary").digest()[:8], "big"
        ) & (2**63 - 1)
        other.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        with pytest.raises(DBAPIError):
            run(c, sql)
        other.rollback()
    assert c.scalar(text("SELECT count(*) FROM admin_audit_log")) == 0


@pytest.mark.parametrize("selected", [[0], [1, 2], [0, 1]])
def test_partial_job_set_refuses_even_when_selected_domains_are_complete(
    store, monkeypatch, selected
):
    c, _ = store
    policy = policy_for(c)
    policy["jobs"] = [policy["jobs"][i] for i in selected]
    with pytest.raises(DBAPIError, match="managed_release:jobs"):
        run(c, compiled(policy, monkeypatch))
    assert (
        c.scalar(text("SELECT count(*) FROM ingestion_jobs WHERE status='RUNNING'"))
        == 3
    )
    assert c.scalar(text("SELECT count(*) FROM admin_audit_log")) == 0


def test_reviewed_dollar_delimiters_and_template_markers_remain_literal(
    store, monkeypatch
):
    c, _ = store
    policy = policy_for(c)
    note = "Reviewed $managed_release$ and $census$ __POLICY__ 'quoted' \\ text"
    policy["why"] = note
    run(c, compiled(policy, monkeypatch))
    assert c.scalar(text("SELECT payload->>'why' FROM admin_audit_log")) == note
    assert (
        c.scalar(text("SELECT count(*) FROM ingestion_jobs WHERE status='FAILED'")) == 3
    )


@pytest.mark.parametrize(
    "drift", ["certified", "identity", "uncaptured", "old_revision"]
)
def test_unqualified_audit_epoch_refuses_without_repair_writes(
    store, monkeypatch, drift
):
    c, admin = store
    with admin.begin() as other:
        if drift == "certified":
            other.execute(text("UPDATE admin_audit_storage SET certified=true"))
        elif drift == "identity":
            other.execute(
                text("UPDATE admin_audit_storage SET system_identifier='123'")
            )
        elif drift == "uncaptured":
            other.execute(
                text("ALTER TABLE admin_audit_log DISABLE TRIGGER audit_log_capture")
            )
            other.execute(
                text("INSERT INTO admin_audit_log(action) VALUES('legacy.unknown')")
            )
            other.execute(
                text(
                    "ALTER TABLE admin_audit_log ENABLE ALWAYS TRIGGER audit_log_capture"
                )
            )
        else:
            other.execute(text("UPDATE alembic_version SET version_num='ea1645a4c0b5'"))
    policy = policy_for(c)
    if drift == "old_revision":
        with pytest.raises(release.ReleaseRefused, match="audit_revision"):
            compiled(policy, monkeypatch)
    else:
        with pytest.raises(
            DBAPIError, match="managed_release:(audit_epoch|unknown_audit_history)"
        ):
            run(c, compiled(policy, monkeypatch))
    assert (
        c.scalar(text("SELECT count(*) FROM ingestion_jobs WHERE status='RUNNING'"))
        == 3
    )
    assert (
        c.scalar(
            text(
                "SELECT count(*) FROM admin_audit_log WHERE action='seeding.reconcile.managed'"
            )
        )
        == 0
    )


def test_existing_captured_audit_and_provenance_are_preserved(store, monkeypatch):
    c, admin = store
    with admin.begin() as other:
        other.execute(text("INSERT INTO admin_audit_log(action) VALUES('owned.prior')"))
    prior = c.execute(
        text(
            "SELECT to_jsonb(a),to_jsonb(p) FROM admin_audit_log a JOIN admin_audit_provenance p ON p.audit_id=a.id"
        )
    ).one()
    c.rollback()
    run(c, compiled(policy_for(c), monkeypatch))
    assert (
        c.execute(
            text(
                "SELECT to_jsonb(a),to_jsonb(p) FROM admin_audit_log a JOIN admin_audit_provenance p ON p.audit_id=a.id WHERE action='owned.prior'"
            )
        ).one()
        == prior
    )
    assert c.scalar(text("SELECT count(*) FROM admin_audit_provenance")) == 2


@pytest.mark.parametrize("column", ["root_xid", "incarnation"])
def test_nullable_sidecar_cannot_be_admitted_as_the_capture_schema(
    store, monkeypatch, column
):
    c, admin = store
    with admin.begin() as other:
        other.execute(
            text(
                "ALTER TABLE admin_audit_provenance ALTER COLUMN "
                + column
                + " DROP NOT NULL"
            )
        )
    with pytest.raises(release.ReleaseRefused, match="audit_sidecar_columns"):
        compiled(policy_for(c), monkeypatch)
    assert c.scalar(text("SELECT count(*) FROM admin_audit_log")) == 0
    assert (
        c.scalar(text("SELECT count(*) FROM ingestion_jobs WHERE status='RUNNING'"))
        == 3
    )


def test_duplicate_sidecars_without_the_canonical_primary_key_are_refused(
    store, monkeypatch
):
    c, admin = store
    with admin.begin() as other:
        other.execute(text("INSERT INTO admin_audit_log(action) VALUES('owned.prior')"))
        other.execute(
            text(
                "ALTER TABLE admin_audit_provenance DROP CONSTRAINT admin_audit_provenance_pkey"
            )
        )
        other.execute(
            text(
                "INSERT INTO admin_audit_provenance SELECT * FROM admin_audit_provenance"
            )
        )
    with pytest.raises(release.ReleaseRefused, match="audit_sidecar_constraints"):
        compiled(policy_for(c), monkeypatch)
    assert c.scalar(text("SELECT count(*) FROM admin_audit_provenance")) == 2
    assert (
        c.scalar(text("SELECT count(*) FROM ingestion_jobs WHERE status='RUNNING'"))
        == 3
    )


def test_missing_positive_audit_id_constraint_is_refused(store, monkeypatch):
    c, admin = store
    with admin.begin() as other:
        other.execute(
            text(
                "ALTER TABLE admin_audit_log DROP CONSTRAINT ck_admin_audit_positive_id"
            )
        )
    with pytest.raises(release.ReleaseRefused, match="audit_sidecar_constraints"):
        compiled(policy_for(c), monkeypatch)
    assert c.scalar(text("SELECT count(*) FROM admin_audit_log")) == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_pin",
        "wrong_pin",
        "zero_jobs",
        "bool_id",
        "owner_tag_null",
        "bad_errors",
        "missing_fence",
        "live_fence",
        "expired",
        "trigger",
    ],
)
def test_compiler_rejects_unverified_inputs(store, monkeypatch, mutation):
    c, _ = store
    p = policy_for(c)
    if mutation == "zero_jobs":
        p["jobs"] = []
    elif mutation == "bool_id":
        p["jobs"][0]["id"] = True
    elif mutation == "owner_tag_null":
        p["jobs"][0]["metadata"]["seeding_claim_id"] = None
    elif mutation == "bad_errors":
        p["jobs"][0]["errors"] = {}
    elif mutation == "missing_fence":
        del p["fences"]["ddl"]
    elif mutation == "live_fence":
        p["fences"]["render"]["state"] = "running"
    elif mutation == "expired":
        p["hold_until"] = p["observed_at"]
    elif mutation == "trigger":
        next(r for r in p["catalog"] if r["name"] == "admin_audit_log")["triggers"] = [
            {"unreviewed": True}
        ]
    monkeypatch.setenv("AUDIT_MANAGED_RELEASE_POLICY_SHA256", release.digest(p))
    if mutation == "missing_pin":
        monkeypatch.delenv("AUDIT_MANAGED_RELEASE_POLICY_SHA256")
    if mutation == "wrong_pin":
        monkeypatch.setenv("AUDIT_MANAGED_RELEASE_POLICY_SHA256", "b" * 64)
    with pytest.raises(release.ReleaseRefused):
        release.compile_sql(p)

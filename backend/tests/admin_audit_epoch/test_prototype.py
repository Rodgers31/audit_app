"""Bounded design proof: actual root transactions, roles, API and storage."""

import importlib.util
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from database import get_db
from models import AdminAuditLog
from supabase_auth import AdminUser, get_current_user

PACKET = (
    Path(__file__).resolve().parents[3]
    / "docs/admin/implementation/batch11-issue-611-evidence"
)


def load(name):
    spec = importlib.util.spec_from_file_location(name, PACKET / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prototype = load("prototype")
launch = load("launch_probe")
# Identical retained test functions and inputs; only the provisioned reader
# fixture changes. The launch probe is archived without changing its bytes.
test_root_writer_late_lower_id_is_excluded = (
    launch.test_root_writer_late_lower_id_is_excluded
)
test_durable_capability_at_real_current_epoch = (
    launch.test_durable_capability_at_real_current_epoch
)


@pytest.fixture
def storage(request):
    if os.getenv("ISSUE611_OWNED_POSTGRES") != "1":
        pytest.skip("issue611 owned PostgreSQL on 55534 required")
    owner = create_engine("postgresql+psycopg2://inert:inert@127.0.0.1:55534/issue611")
    AdminAuditLog.__table__.create(owner)
    if getattr(request, "param", None) == "legacy":
        with sessionmaker(bind=owner)() as db:
            db.add(launch.item())
            db.commit()
    prototype.install_owned(owner)
    reader = create_engine(
        "postgresql+psycopg2://issue611_reader:inert@127.0.0.1:55534/issue611"
    )
    writer = create_engine(
        "postgresql+psycopg2://issue611_writer:inert@127.0.0.1:55534/issue611"
    )
    factory = sessionmaker(bind=writer)
    reader_factory = sessionmaker(bind=reader)
    app = FastAPI()
    app.include_router(prototype.router)
    app.dependency_overrides[get_current_user] = lambda: AdminUser(
        id="inert-admin", email=None, roles=["admin"]
    )

    def sessions():
        with reader_factory() as db:
            yield db

    app.dependency_overrides[get_db] = sessions
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield owner, factory, client, reader, writer, app
    finally:
        reader.dispose()
        writer.dispose()
        with owner.begin() as db:
            db.execute(
                text(
                    "DROP TABLE IF EXISTS public.admin_audit_log, public.issue611_capability"
                )
            )
            db.execute(
                text(
                    "DROP FUNCTION public.issue611_capture(), public.issue611_immutable()"
                )
            )
            for role in ("issue611_reader", "issue611_writer", "issue611_untrusted"):
                db.execute(text(f"DROP OWNED BY {role}"))
                db.execute(text(f"DROP ROLE {role}"))
        owner.dispose()


@pytest.fixture
def owned(storage):
    owner, factory, client, *_ = storage
    return owner, factory, client


def insert(factory):
    with factory() as db:
        db.add(launch.item())
        db.commit()


@pytest.mark.parametrize(
    "snapshot,xid,expected",
    [
        ("4294967294:4294967299:4294967295,4294967297", "4294967293", True),
        ("4294967294:4294967299:4294967295,4294967297", "4294967295", False),
        ("4294967294:4294967299:4294967295,4294967297", "4294967296", True),
        ("4294967294:4294967299:4294967295,4294967297", "4294967297", False),
        ("4294967294:4294967299:4294967295,4294967297", "4294967299", False),
        (
            "18446744073709551613:18446744073709551615:18446744073709551614",
            "18446744073709551614",
            False,
        ),
    ],
)
def test_postgres_xid8_wrap_boundary_predicate(storage, snapshot, xid, expected):
    owner, *_ = storage
    with owner.connect() as db:
        actual = db.scalar(
            text(
                "SELECT pg_visible_in_snapshot(CAST(:x AS xid8),CAST(:s AS pg_snapshot))"
            ),
            {"x": xid, "s": prototype.snapshot8(snapshot)},
        )
        assert actual is expected


def test_savepoint_lower_id_root_provenance(storage):
    owner, factory, client, *_ = storage
    with factory() as early:
        with early.begin_nested():
            early.add(launch.item())
            early.flush()
            root, xmin = early.execute(
                text("SELECT root_xid::text,xmin::text FROM admin_audit_log")
            ).one()
            assert root == early.scalar(text("SELECT pg_current_xact_id()::text"))
            assert int(root) % 2**32 != int(xmin), "Real subtransaction expected"
        insert(factory)
        first = client.get("/api/v1/admin/audit-log?days=0&page_size=1").json()
        assert first["total"] == 1
        early.commit()
    response = client.get(
        "/api/v1/admin/audit-log",
        params={
            "days": 0,
            "page": 2,
            "page_size": 1,
            **{k: first[k] for k in ("snapshot_id", "as_of", "visibility_snapshot")},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["entries"] == []


def test_raw_writer_and_provenance_spoofing(storage):
    owner, _, client, _, writer, _ = storage
    with writer.begin() as db:
        db.execute(
            text(
                "INSERT INTO admin_audit_log(actor_id,action,payload,created_at) VALUES('raw','etl.trigger','{}',now())"
            )
        )
        root = db.scalar(text("SELECT root_xid::text FROM admin_audit_log"))
        assert root == db.scalar(text("SELECT pg_current_xact_id()::text"))
    with pytest.raises(DBAPIError, match="permission denied"):
        with writer.begin() as db:
            db.execute(
                text(
                    "INSERT INTO admin_audit_log(actor_id,action,payload,created_at,root_xid) VALUES('raw','etl.trigger','{}',now(),'3')"
                )
            )
    with pytest.raises(DBAPIError, match="database assigned"):
        with owner.begin() as db:
            db.execute(
                text(
                    "INSERT INTO admin_audit_log(actor_id,action,payload,created_at,root_xid) VALUES('raw','etl.trigger','{}',now(),'3')"
                )
            )
    assert client.get("/api/v1/admin/audit-log?days=0").json()["total"] == 1


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE admin_audit_log SET action='changed'",
        "DELETE FROM admin_audit_log",
        "TRUNCATE admin_audit_log",
    ],
)
def test_append_only_acl_and_trigger(storage, sql):
    owner, factory, _, _, writer, _ = storage
    insert(factory)
    with pytest.raises(DBAPIError, match="permission denied"):
        with writer.begin() as db:
            db.execute(text(sql))
    with pytest.raises(DBAPIError, match="append only"):
        with owner.begin() as db:
            db.execute(text(sql))
    with owner.connect() as db:
        assert db.scalar(text("SELECT count(*) FROM admin_audit_log")) == 1


def test_untrusted_rls_and_anonymous_api(storage):
    owner, factory, client, _, _, app = storage
    insert(factory)
    with owner.begin() as db:
        db.execute(text("GRANT SELECT ON admin_audit_log TO issue611_untrusted"))
    untrusted = create_engine(
        "postgresql+psycopg2://issue611_untrusted:inert@127.0.0.1:55534/issue611"
    )
    try:
        with untrusted.connect() as db:
            assert db.scalar(text("SELECT count(*) FROM admin_audit_log")) == 0
    finally:
        untrusted.dispose()
    app.dependency_overrides[get_current_user] = lambda: AdminUser(
        id="citizen", email=None, roles=["citizen"]
    )
    response = client.get("/api/v1/admin/audit-log")
    assert response.status_code == 403
    assert response.headers["cache-control"] == "private, no-store"
    app.dependency_overrides.pop(get_current_user)
    assert client.get("/api/v1/admin/audit-log").status_code == 401


@pytest.mark.parametrize(
    "damage",
    [
        "DROP TABLE issue611_capability",
        "ALTER TABLE admin_audit_log DISABLE TRIGGER issue611_capture",
        "ALTER TABLE admin_audit_log DISABLE ROW LEVEL SECURITY",
        "GRANT UPDATE(action) ON admin_audit_log TO issue611_reader",
        "UPDATE issue611_capability SET ready=false",
        "ALTER POLICY issue611_read ON admin_audit_log USING (false)",
    ],
)
def test_missing_or_unsafe_capability_is_private_unavailable(storage, damage):
    owner, factory, client, *_ = storage
    insert(factory)
    with owner.begin() as db:
        db.execute(text(damage))
    response = client.get("/api/v1/admin/audit-log?days=0")
    assert response.status_code == 503
    assert response.json() == {"detail": "Audit evidence is unavailable."}
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"


def test_legacy_unknown_refuses_dataset(storage):
    owner, factory, client, *_ = storage
    insert(factory)
    with owner.begin() as db:
        db.execute(text("ALTER TABLE admin_audit_log DISABLE TRIGGER issue611_capture"))
        db.execute(
            text(
                "INSERT INTO admin_audit_log(actor_id,action,payload,created_at) VALUES('legacy','legacy','{}',now())"
            )
        )
        db.execute(
            text("ALTER TABLE admin_audit_log ENABLE ALWAYS TRIGGER issue611_capture")
        )
    assert client.get("/api/v1/admin/audit-log?days=0").status_code == 503
    with owner.connect() as db:
        assert (
            db.scalar(
                text("SELECT count(*) FROM admin_audit_log WHERE root_xid IS NULL")
            )
            == 1
        )


@pytest.mark.parametrize("storage", ["legacy"], indirect=True)
def test_preexisting_history_has_no_fabricated_provenance(storage):
    owner, _, client, *_ = storage
    with owner.connect() as db:
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM admin_audit_log WHERE id=1 AND root_xid IS NULL"
                )
            )
            == 1
        )
    response = client.get("/api/v1/admin/audit-log?days=0")
    assert response.status_code == 503
    assert response.json() == {"detail": "Audit evidence is unavailable."}


def test_actual_audit_helper_owns_independent_root_writer(storage, monkeypatch):
    import database
    from utils.audit import record_admin_action

    owner, factory, client, *_ = storage
    monkeypatch.setattr(database, "SessionLocal", factory)
    with factory() as caller:
        caller.add(launch.item())
        caller.flush()
        record_admin_action(
            caller,
            actor=AdminUser(id="helper", email=None, roles=["admin"]),
            action="etl.trigger",
            payload={"job_id": 2, "dry_run": True},
        )
        caller.rollback()
    with owner.connect() as db:
        rows = db.execute(
            text("SELECT actor_id,root_xid::text FROM admin_audit_log")
        ).all()
        assert len(rows) == 1 and rows[0].actor_id == "helper"
        assert int(rows[0].root_xid) > 2**32
    assert client.get("/api/v1/admin/audit-log?days=0").json()["total"] == 1


def test_unchanged_production_router_still_refuses_epoch_one(storage):
    from routers.admin_audit_log import router as launch_router

    _, factory, _, reader, *_ = storage
    insert(factory)
    app = FastAPI()
    app.include_router(launch_router)
    app.dependency_overrides[get_current_user] = lambda: AdminUser(
        id="inert-admin", email=None, roles=["admin"]
    )

    def sessions():
        with sessionmaker(bind=reader)() as db:
            yield db

    app.dependency_overrides[get_db] = sessions
    with TestClient(app) as client:
        for params in (
            {},
            {
                "snapshot_id": 1,
                "as_of": datetime.now(timezone.utc).isoformat(),
                "visibility_snapshot": "3:9:",
            },
        ):
            response = client.get("/api/v1/admin/audit-log", params=params)
            assert response.status_code == 503
            assert response.json() == {"detail": "Audit evidence is unavailable."}
            assert response.headers["cache-control"] == "private, no-store"


def test_freeze_and_table_rewrite_preserve_bookmark(storage):
    owner, factory, client, *_ = storage
    insert(factory)
    first = client.get("/api/v1/admin/audit-log?days=0").json()
    with owner.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
        before = db.execute(
            text("SELECT root_xid::text,payload::text FROM admin_audit_log")
        ).all()
        db.execute(text("VACUUM (FREEZE, ANALYZE) admin_audit_log"))
        db.execute(text("VACUUM FULL admin_audit_log"))
        after = db.execute(
            text("SELECT root_xid::text,payload::text FROM admin_audit_log")
        ).all()
        assert before == after
    response = client.get(
        "/api/v1/admin/audit-log",
        params={
            "days": 0,
            **{k: first[k] for k in ("snapshot_id", "as_of", "visibility_snapshot")},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["entries"] == first["entries"]


def test_expiry_old_scope_and_filter_transfer(storage):
    owner, factory, client, *_ = storage
    insert(factory)
    first = client.get("/api/v1/admin/audit-log?days=0").json()
    fields = {k: first[k] for k in ("snapshot_id", "as_of", "visibility_snapshot")}
    response = client.get(
        "/api/v1/admin/audit-log", params={"days": 0, "actor_id": "absent", **fields}
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["visibility_snapshot"] == fields["visibility_snapshot"]
    expired = client.get(
        "/api/v1/admin/audit-log",
        params={
            **fields,
            "as_of": (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat(),
        },
    )
    assert expired.status_code == 422
    assert "expired" in expired.json()["detail"]
    old = client.get(
        "/api/v1/admin/audit-log", params={**fields, "visibility_snapshot": "3:9:"}
    )
    assert old.status_code == 422
    with owner.begin() as db:
        db.execute(
            text(
                "UPDATE issue611_capability SET scope='61100000-0000-4000-8000-000000000002'"
            )
        )
    stale = client.get("/api/v1/admin/audit-log", params=fields)
    assert stale.status_code == 422
    assert "Refresh" in stale.json()["detail"]
    assert client.get("/api/v1/admin/audit-log").status_code == 200


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        1,
        float("nan"),
        {},
        [],
        "",
        "٣:٤:",
        "3:2:",
        "3:5:4,4",
        "3:5:5",
        "3:18446744073709551616:",
    ],
)
def test_hostile_snapshots(value):
    with pytest.raises(HTTPException) as error:
        prototype.snapshot8(value)
    assert error.value.status_code == 422

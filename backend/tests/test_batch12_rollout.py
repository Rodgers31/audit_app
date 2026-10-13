"""Operational plan/observation and exact baseline migration controls."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from models import IngestionJob, IngestionStatus

from test_batch9_reconciliation import owned, read, ROOT  # noqa: F401

SPEC = importlib.util.spec_from_file_location("batch12_rollout", ROOT / "scripts/batch12_rollout.py")
rollout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rollout)


def observation_fixture():
    return {"version": 1, "kind": "database_observation", "observed_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True, "production_ready": False, "endpoint_sha256": "1" * 64,
        "revisions": ["ea1645a4c0b5"], "identity": {"database": "owned", "role": "postgres",
            "database_oid": 5, "observer_pid": 100, "superuser": False, "bypass_rls": True,
            "admission_open": True, "full_stats": True, "server_version": "17.6",
            "system_identifier": "123456", "cluster_identity_available": True},
        "schema": {}, "running_observations": [], "other_sessions": [], "prepared_transactions": 0,
        "roles": [{"name": "postgres", "superuser": False, "bypass_rls": True, "login": True}],
        "connection_mode": "unverified_from_catalogs", "sslmode": "require", "transport_encrypted": True}


def migrate(db, revision):
    return subprocess.run([sys.executable, "-B", "-m", "alembic", "upgrade", revision], cwd=ROOT,
        env={"PATH": os.environ["PATH"], "PYTHON_DOTENV_DISABLED": "1",
             "PYTHONDONTWRITEBYTECODE": "1", "DATABASE_URL": db.url},
        text=True, capture_output=True, timeout=90)


def test_baseline_suffix_is_exact_and_never_future_head():
    observation = observation_fixture()
    plan = rollout.build_plan(observation)
    assert plan["target"] == "e602b11a0001"
    assert plan["migration_argv"][-2:] == ["upgrade", "e602b11a0001"]
    assert [x["revision"] for x in plan["ordered_migrations"]] == [
        "c415a10d2026", "f38c61a9d203", "c96d13e2f411", "a42b86e1d310", "b73e19a4f602",
        "d8f4a619b203", "e554d7c9a001", "e572b8c9a001", "e583b9c9a001", "e554b10a0001", "e602b11a0001"]
    assert plan["production_execution_authorized"] is False and plan["production_ready"] is False


@pytest.mark.parametrize("revision", [None, True, [], "future_audit_head", "a611b12a0001", "missing"])
def test_unknown_or_malformed_revision_refuses(revision):
    observation = observation_fixture()
    observation["revisions"] = [revision]
    with pytest.raises(rollout.Refused):
        rollout.build_plan(observation)


@pytest.mark.parametrize("url", ["sqlite:///toy", "postgresql://user@localhost/db?options=-c+role=other",
    "postgresql://user@localhost/db?host=elsewhere", "postgresql://localhost/db", "not-a-url"])
def test_endpoint_redirect_and_wrong_backend_refuse(url):
    with pytest.raises((rollout.Refused, ValueError)):
        rollout.endpoint_fingerprint(url)


def test_endpoint_fingerprint_omits_password():
    a = "postgresql://role:toy-secret@127.0.0.1:55560/owned"
    b = "postgresql+psycopg2://role:other-secret@127.0.0.1:55560/owned?sslmode=require"
    assert rollout.endpoint_fingerprint(a) == rollout.endpoint_fingerprint(b)
    assert rollout.endpoint_fingerprint(a) != rollout.endpoint_fingerprint(a.replace("55560", "55561"))


@pytest.mark.parametrize('mode', ['disable', 'allow', 'prefer', '', 'unknown', 'REQUIRE',
                               'require&sslmode=disable', 'require&sslmode=require'])
def test_insecure_or_ambiguous_tls_mode_refuses_before_connection(mode, monkeypatch):
    import sqlalchemy
    monkeypatch.setattr(sqlalchemy, 'create_engine', lambda *a, **k: pytest.fail('connection must not open'))
    url = 'postgresql://role:inert-secret@database.example/owned?sslmode=' + mode
    with pytest.raises(rollout.Refused, match='postgres_transport_required'):
        rollout.observe(url, '1' * 64)


def test_tls_mode_is_bound_and_default_is_encrypted():
    url = 'postgresql://role:inert-secret@database.example/owned'
    assert rollout.endpoint_fingerprint(url) == rollout.endpoint_fingerprint(url + '?sslmode=require')
    assert rollout.endpoint_fingerprint(url + '?sslmode=require') != rollout.endpoint_fingerprint(url + '?sslmode=verify-full')


def test_owned_loopback_profile_cannot_authorize_tls_downgrade():
    url = 'postgresql://postgres@127.0.0.1:55560/batch9-reconciliation-' + 'a' * 32
    assert rollout.endpoint_fingerprint(url) != rollout.endpoint_fingerprint(url + '?sslmode=require')
    with pytest.raises(rollout.Refused, match='postgres_transport_required'):
        rollout.endpoint_fingerprint(url + '?sslmode=disable')


@pytest.mark.parametrize('source', ['revision="bad"', 'revision=[]\ndown_revision=None',
                                   'revision="bad"\ndown_revision=[]', 'revision = ('])
def test_malformed_migration_is_sanitized_refusal(source, tmp_path):
    versions = tmp_path / 'backend/alembic/versions'
    versions.mkdir(parents=True)
    (versions / 'bad.py').write_text(source)
    with pytest.raises(rollout.Refused, match='migration_identity'):
        rollout.migration_chain(tmp_path)


def test_published_plan_can_be_validated_without_mutating_provenance(tmp_path):
    path = tmp_path / 'plan.json'
    rollout.write_new(path, rollout.build_plan(observation_fixture()))
    original = path.read_bytes()
    rollout.validate_receipt(json.loads(original))
    changed = json.loads(original)
    changed['generator_sha256'] = '0' * 64
    with pytest.raises(rollout.Refused, match='plan_shape'):
        rollout.validate_receipt(changed)
    assert path.read_bytes() == original


def test_receipt_is_exclusive_external_and_read_back(tmp_path):
    path = tmp_path / "observation.json"
    rollout.write_new(path, observation_fixture())
    value = json.loads(path.read_text())
    assert value["production_ready"] is False and len(value["generator_sha256"]) == 64
    original = path.read_bytes()
    with pytest.raises(rollout.Refused, match='fresh_external_output_required'):
        rollout.write_new(path, observation_fixture())
    assert path.read_bytes() == original


def test_source_output_and_symlink_refuse(tmp_path):
    source = ROOT / "scripts/batch12_rollout.py"
    original = source.read_bytes()
    with pytest.raises(rollout.Refused, match='fresh_external_output_required'):
        rollout.write_new(source, observation_fixture())
    assert source.read_bytes() == original
    link = tmp_path / "alias"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(rollout.Refused, match='fresh_external_output_required'):
        rollout.write_new(link / "new.json", observation_fixture())
    assert not (tmp_path / "new.json").exists()


@pytest.mark.parametrize("owned", ["ea1645a4c0b5"], indirect=True)
def test_legacy_observation_is_read_only_and_plans_actual_suffix(owned):
    with owned.factory.begin() as session:
        session.add(IngestionJob(domain="national_budget", status=IngestionStatus.RUNNING,
                                 dry_run=False, meta={}, errors=[]))
    before = read(owned, "SELECT * FROM ingestion_jobs")
    observation = rollout.observe(owned.url, rollout.endpoint_fingerprint(owned.url))
    assert observation["read_only"] is True and observation["production_ready"] is False
    assert observation['sslmode'] == 'disable' and observation['transport_encrypted'] is False
    assert observation["identity"]["superuser"] is True
    assert observation["identity"]["admission_open"] is True
    assert observation["identity"]["cluster_identity_available"] is True
    assert observation["revisions"] == ["ea1645a4c0b5"]
    assert set(observation["schema"]) == {"ingestion_jobs", "admin_audit_log"}
    assert observation["running_observations"][0]["claim_tag_present"] is False
    assert len(observation["other_sessions"]) >= 1  # retained fixture connection is visible
    assert read(owned, "SELECT * FROM ingestion_jobs") == before
    assert rollout.build_plan(observation)["from_revision"] == "ea1645a4c0b5"
    result = migrate(owned, rollout.BASELINE_TARGET)
    assert result.returncode == 0, result.stderr
    assert read(owned, "SELECT * FROM ingestion_jobs") == before
    after = rollout.observe(owned.url, rollout.endpoint_fingerprint(owned.url))
    assert after["revisions"] == [rollout.BASELINE_TARGET]
    assert set(after["schema"]) == set(rollout.TABLES)
    assert rollout.build_plan(after)["ordered_migrations"] == []
    result = migrate(owned, rollout.BASELINE_TARGET)
    assert result.returncode == 0, result.stderr
    assert read(owned, "SELECT * FROM ingestion_jobs") == before


@pytest.mark.parametrize("owned", ["base"], indirect=True)
def test_fresh_database_uses_real_entire_chain(owned):
    result = migrate(owned, rollout.BASELINE_TARGET)
    assert result.returncode == 0, result.stderr
    observation = rollout.observe(owned.url, rollout.endpoint_fingerprint(owned.url))
    assert observation["revisions"] == [rollout.BASELINE_TARGET]
    assert set(observation["schema"]) == set(rollout.TABLES)
    for name in rollout.TABLES[2:]:
        assert observation["schema"][name]["rls"] is True


@pytest.mark.parametrize("owned", ["ea1645a4c0b5"], indirect=True)
def test_partial_schema_aborts_transaction_without_stamping_or_repair(owned):
    with owned.connection.begin():
        owned.connection.execute(text("CREATE TABLE etl_dispatch_commands (wrong_column text)"))
    result = migrate(owned, rollout.BASELINE_TARGET)
    assert result.returncode != 0 and 'already exists' in result.stderr
    assert read(owned, "SELECT version_num FROM alembic_version") == [{"version_num": "ea1645a4c0b5"}]
    assert read(owned, "SELECT column_name FROM information_schema.columns WHERE table_name='etl_dispatch_commands'") == [{"column_name": "wrong_column"}]
    assert read(owned, "SELECT to_regclass('public.seeding_domain_claims') AS table_name") == [{"table_name": None}]


def test_endpoint_mismatch_refuses_before_connect(owned, monkeypatch):
    import sqlalchemy
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *a, **k: pytest.fail("connection must not open"))
    with pytest.raises(rollout.Refused, match="endpoint_mismatch"):
        rollout.observe(owned.url, "0" * 64)


def test_observer_cannot_write_even_with_superuser(owned):
    # Actual server boundary used by observe, including initial connection options.
    engine = create_engine(owned.url, poolclass=NullPool,
        connect_args={"options": "-c default_transaction_read_only=on"})
    try:
        with engine.connect() as c:
            c.execute(text("BEGIN READ ONLY"))
            assert c.scalar(text("SHOW transaction_read_only")) == "on"
            with pytest.raises(Exception, match="read-only transaction"):
                c.execute(text("INSERT INTO admin_audit_log(action,actor_id) VALUES ('inert','inert')"))
            c.rollback()
    finally:
        engine.dispose()
    assert read(owned, "SELECT count(*) AS n FROM admin_audit_log") == [{"n": 0}]


@pytest.mark.parametrize("case", ["missing", "stale", "boolean_identity", "false_ready_receipt"])
def test_malformed_observation_cannot_be_planned_or_stamped(case, tmp_path):
    observation = observation_fixture()
    if case == "missing":
        del observation["observed_at"]
    elif case == "stale":
        observation["observed_at"] = "2000-01-01T00:00:00+00:00"
    elif case == "boolean_identity":
        observation["identity"]["database"] = True
    else:
        observation["production_ready"] = True
        with pytest.raises(rollout.Refused):
            rollout.write_new(tmp_path / "false-ready.json", observation)
        assert not (tmp_path / "false-ready.json").exists()
        return
    with pytest.raises(rollout.Refused):
        rollout.build_plan(observation)


@pytest.mark.parametrize("field,bad", [("version", True), ("prepared_transactions", True),
    ("roles", []), ("other_sessions", [{}]), ("schema", {"unknown": {}}),
    ("endpoint_sha256", "no"), ("observed_at", "2999-01-01T00:00:00+00:00"),
    ("observed_at", "2026-10-12T00:00:00"), ("running_observations", [{}])])
def test_observation_field_types_and_bounds_refuse(field, bad):
    value = observation_fixture()
    value[field] = bad
    with pytest.raises(rollout.Refused):
        rollout.build_plan(value)


@pytest.mark.parametrize("value", [{}, {"production_ready": True},
    {"production_ready": False, "production_execution_authorized": True}])
def test_writer_does_not_stamp_arbitrary_or_authorizing_receipts(value, tmp_path):
    with pytest.raises(rollout.Refused):
        rollout.write_new(tmp_path / "refused.json", value)
    assert not (tmp_path / "refused.json").exists()


@pytest.mark.parametrize("case", ["missing", "file", "link"])
def test_cli_invalid_output_parent_refuses_before_observer(case, tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    if case == "file":
        parent.write_text("file")
    elif case == "link":
        parent.symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setattr(rollout, "observe", lambda *args: pytest.fail("observer must not run"))
    assert rollout.main(["observe", "--out", str(parent / "out.json"),
                         "--expected-endpoint-sha256", "1" * 64]) == 1


def test_parent_swap_cannot_redirect_receipt_into_source(tmp_path, monkeypatch):
    parent = tmp_path / "output"
    parent.mkdir()
    original = tmp_path / "original"
    miniature_source = tmp_path / "source"
    miniature_source.mkdir()
    monkeypatch.setattr(rollout, "ROOT", miniature_source)
    real_open = os.open

    def swap_on_create(path, flags, *args, **kwargs):
        if flags & os.O_CREAT:
            parent.rename(original)
            parent.symlink_to(miniature_source, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_on_create)
    with pytest.raises(rollout.Refused, match="output_parent_changed"):
        rollout.write_new(parent / "receipt.json", observation_fixture())
    assert not (miniature_source / "receipt.json").exists()
    assert (original / "receipt.json").exists()  # anchored private evidence, no success


@pytest.mark.parametrize("layer", ["top", "identity", "role", "session"])
def test_unrecognized_fields_or_missing_nullable_fields_refuse(layer):
    value = observation_fixture()
    if layer == "top":
        value["extra"] = "unobserved"
    elif layer == "identity":
        value["identity"]["extra"] = "unobserved"
    elif layer == "role":
        value["roles"][0]["extra"] = "unobserved"
    else:
        value["other_sessions"] = [{"pid": 101}]
    with pytest.raises(rollout.Refused):
        rollout.build_plan(value)

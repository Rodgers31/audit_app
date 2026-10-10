"""Actual additive migration, history, permissions and retained evidence controls."""
import importlib.util
import subprocess
import sys

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import CheckConstraint, MetaData, create_engine, text

from models import AdminAuditLog, EtlDispatchCommand, IngestionJob, SeedingDomainClaim
from test_batch9_reconciliation import native, read, ROOT
from test_batch9_reconciliation import owned  # noqa: F401 -- registers the owned pytest fixture
from test_batch9_reconciliation_constraints import jsonb_sqlite  # noqa: F401 -- registers SQLite JSONB DDL compiler

MIGRATION = ROOT / "alembic/versions/e583b9c9a001_reconciliation_evidence.py"
OLD_CHECK = "(reconciled_by IS NULL) = (reconciliation IS NULL) AND (reconciled_by IS NULL OR (released_at IS NOT NULL AND length(reconciled_by) <= 64 AND length(reconciliation) <= 4000 AND length(ltrim(rtrim(reconciled_by))) >= 1 AND length(ltrim(rtrim(reconciliation))) >= 1))"


def migrate(db, *args):
    result = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1",
             "PYTHON_DOTENV_DISABLED": "1", "DATABASE_URL": db.url}, text=True, capture_output=True)
    return result


@pytest.mark.parametrize("owned", ["e572b8c9a001"], indirect=True)
def test_actual_upgrade_preserves_claim_history_rls_and_grants(owned):
    selected = native(owned)
    original = read(owned, "SELECT * FROM seeding_domain_claims")[0]
    with owned.connection.begin():
        for role in ("anon", "authenticated"):
            owned.connection.execute(text(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN CREATE ROLE {role}; END IF; END $$"))
    result = migrate(owned, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    assert read(owned, "SELECT * FROM seeding_domain_claims")[0] == original
    assert read(owned, "SELECT version_num FROM alembic_version")[0]["version_num"] == "e583b9c9a001"
    assert read(owned, "SELECT relrowsecurity FROM pg_class WHERE oid='seeding_domain_claims'::regclass")[0]["relrowsecurity"] is True
    for role in ("anon", "authenticated"):
        privileges = read(owned, f"SELECT has_table_privilege('{role}','seeding_domain_claims','SELECT,INSERT,UPDATE,DELETE,TRUNCATE') AS allowed")[0]
        assert privileges["allowed"] is False
    assert read(owned, "SELECT coalesce(array_length(relacl,1),0) AS acl_size FROM pg_class WHERE oid='seeding_domain_claims'::regclass")[0]["acl_size"] == 1
    result = migrate(owned, "heads")
    assert result.returncode == 0 and result.stdout.count("(head)") == 1 and "e583b9c9a001" in result.stdout
    result = migrate(owned, "history", "-r", "e572b8c9a001:head")
    assert result.returncode == 0 and "e572b8c9a001 -> e583b9c9a001" in result.stdout
    result = migrate(owned, "downgrade", "e572b8c9a001")
    assert result.returncode != 0 and "cannot be weakened" in result.stderr
    assert read(owned, "SELECT * FROM seeding_domain_claims")[0] == original
    assert selected["claim_id"] == str(original["id"])


@pytest.mark.parametrize("owned", ["e572b8c9a001"], indirect=True)
def test_existing_invalid_release_refuses_upgrade_without_rewriting_evidence(owned):
    native(owned)
    with owned.connection.begin():
        owned.connection.execute(text("UPDATE seeding_domain_claims SET released_at=clock_timestamp(),reconciled_by=E'\\t',reconciliation=E'\\n'"))
    original = read(owned, "SELECT * FROM seeding_domain_claims")[0]
    result = migrate(owned, "upgrade", "head")
    assert result.returncode != 0 and "ck_seeding_claim_reconciliation" in result.stderr
    assert read(owned, "SELECT * FROM seeding_domain_claims")[0] == original
    assert read(owned, "SELECT version_num FROM alembic_version")[0]["version_num"] == "e572b8c9a001"


def test_sqlite_additive_upgrade_preserves_history_and_matches_model(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "batch9-reconciliation.sqlite"))
    metadata = MetaData()
    for model in (AdminAuditLog, IngestionJob, EtlDispatchCommand, SeedingDomainClaim):
        model.__table__.to_metadata(metadata)
    table = metadata.tables["seeding_domain_claims"]
    constraint = next(c for c in table.constraints if c.name == "ck_seeding_claim_reconciliation")
    table.constraints.remove(constraint)
    table.append_constraint(CheckConstraint(OLD_CHECK, name="ck_seeding_claim_reconciliation"))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO seeding_domain_claims(id,domain,kind,acquired_at,entered_at,entry_id) VALUES ('12345678123412341234123456781234','audits','native','2026-01-01','2026-01-01','23456781234123412341234567812345')"))
    module_spec = importlib.util.spec_from_file_location("batch9_owned_migration", MIGRATION)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    with engine.begin() as connection:
        before = connection.execute(text("SELECT * FROM seeding_domain_claims")).all()
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        assert connection.execute(text("SELECT * FROM seeding_domain_claims")).all() == before
        schema = connection.scalar(text("SELECT sql FROM sqlite_master WHERE name='seeding_domain_claims'"))
        assert "uq_seeding_active_domain" in connection.scalar(text("SELECT sql FROM sqlite_master WHERE name='uq_seeding_active_domain'"))
        assert "trim(reconciled_by," in schema
        model_check = next(c for c in SeedingDomainClaim.__table__.constraints if c.name == "ck_seeding_claim_reconciliation")
        assert str(model_check.sqltext) == module._CHECK
    engine.dispose()

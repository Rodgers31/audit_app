"""Exercise the actual API against the reusable local acceptance fixture."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[2]


def _sqlite_fixture_target(path):
    engine = create_engine(f"sqlite:///{path}")
    return SimpleNamespace(engine=engine, SessionLocal=sessionmaker(bind=engine))


def test_fixture_refuses_unrelated_database_before_creating_tables(tmp_path):
    from dev_fixtures import seed_local_fixture

    path = tmp_path / "other.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE private_data (value TEXT)")
        connection.execute("INSERT INTO private_data VALUES ('existing')")
    target = _sqlite_fixture_target(path)
    with pytest.raises(RuntimeError, match="refuses"):
        seed_local_fixture(target)
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"private_data"}
        assert connection.execute("SELECT value FROM private_data").fetchone() == ("existing",)


def test_fixture_refuses_extra_rows_in_marked_database(tmp_path):
    from dev_fixtures import seed_local_fixture
    from models import Entity, EntityType

    target = _sqlite_fixture_target(tmp_path / "fixture.sqlite")
    seed_local_fixture(target)
    with target.SessionLocal() as db:
        db.add(Entity(
            id=99, country_id=1, type=EntityType.COUNTY,
            canonical_name="Extra County", slug="extra",
        ))
        db.commit()
    with pytest.raises(RuntimeError, match="refuses"):
        seed_local_fixture(target)


@pytest.mark.parametrize(
    "model_name,pk,field,value",
    [
        ("Country", 1, "meta", {"fixture": "auditgava-local-dev-v1", "synthetic": False}),
        ("Entity", 1, "canonical_name", "Changed county"),
        ("FiscalPeriod", 1, "label", "FY2099/00"),
        ("SourceDocument", 1, "url", "https://production.example/budget.pdf"),
        ("SourceDocument", 2, "url", "https://production.example/audit.pdf"),
        ("SourceDocument", 2, "meta", {"synthetic": True, "extraction_stats": {"volume_kind": "assemblies"}}),
        ("BudgetLine", 1, "allocated_amount", 42),
        ("BudgetLine", 2, "publishable", False),
        ("Audit", 1, "entity_id", 1),
        ("Audit", 2, "publishable", True),
    ],
)
def test_fixture_refuses_changed_rows_with_the_same_counts(tmp_path, model_name, pk, field, value):
    import models
    from dev_fixtures import seed_local_fixture

    target = _sqlite_fixture_target(tmp_path / "fixture.sqlite")
    seed_local_fixture(target)
    with target.SessionLocal() as db:
        setattr(db.get(getattr(models, model_name), pk), field, value)
        db.commit()
    with pytest.raises(RuntimeError, match="refuses"):
        seed_local_fixture(target)


def test_fixture_reopens_after_the_approved_browser_budget_change(tmp_path):
    from dev_fixtures import seed_local_fixture
    from models import BudgetLine

    target = _sqlite_fixture_target(tmp_path / "fixture.sqlite")
    seed_local_fixture(target)
    with target.SessionLocal() as db:
        db.get(BudgetLine, 2).allocated_amount = 125_000_000_000
        db.commit()
    seed_local_fixture(target)


def _snapshot(database_path):
    script = r'''
import json
import sys
sys.path.insert(0, "backend/tests")
import browser_fixture_api as fixture
from fastapi.testclient import TestClient

client = TestClient(fixture.main.app)
paths = {
    "counties": "/api/v1/counties",
    "detail": "/api/v1/counties/nairobi",
    "older": "/api/v1/counties/nairobi?fiscal_year=2024/25",
    "years": "/api/v1/counties/fiscal-years",
    "findings": "/api/v1/counties/nairobi/audits/list",
    "withheld_year": "/api/v1/counties/nairobi/audits/list?year=FY2025/26%209M",
    "fiscal": "/api/v1/fiscal/summary",
}
responses = {name: client.get(path) for name, path in paths.items()}
assert all(response.status_code == 200 for response in responses.values())
print("LOCAL_FIXTURE_RESULT=" + json.dumps({name: response.json() for name, response in responses.items()}))
'''
    env = {
        k: v for k, v in os.environ.items()
        if k not in {"DATABASE_URL", "DB_HOST", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"}
    }
    env["AUDIT_BROWSER_FIXTURE_DB"] = str(database_path)
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.split("LOCAL_FIXTURE_RESULT=", 1)[1])


def test_persistent_fixture_preserves_county_year_audit_and_absence(tmp_path):
    database_path = tmp_path / "acceptance.sqlite"
    first = _snapshot(database_path)
    assert database_path.exists()
    second = _snapshot(database_path)
    assert second == first  # restart did not duplicate rows or change values

    counties = {row["name"]: row for row in first["counties"]}
    assert set(counties) == {"Nairobi", "Mombasa"}
    assert counties["Nairobi"]["total_budget"] == 100_000_000_000
    assert counties["Nairobi"]["audit_status"] == "qualified"
    assert counties["Mombasa"]["total_budget"] is None
    assert counties["Mombasa"]["audit_status"] == "pending"
    assert first["detail"]["total_budget"] == 100_000_000_000
    assert first["older"]["total_budget"] == 50_000_000_000
    assert first["years"]["default"] == "FY2025/26 9M"

    findings = first["findings"]
    assert findings["total"] == 1
    assert findings["items"][0]["description"].startswith("Synthetic finding:")
    assert findings["items"][0]["source"]["title"] == "Synthetic local audit findings"
    assert first["withheld_year"]["total"] == 0
    assert first["fiscal"]["status"] == "no_data"
    assert first["fiscal"]["current"] is None

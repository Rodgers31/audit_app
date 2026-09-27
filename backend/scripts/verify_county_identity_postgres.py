"""Run the five new lookup integration cases on an empty disposable PostgreSQL DB.

Set SESSION2_POSTGRES_URL to a localhost database named audit_app_session2*.
Never points at production. Creates synthetic identity rows, then runs the exact
pre-existing pytest nodes plus strict HTTP checks (the route sweep permits 500).
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if not __debug__:
    raise RuntimeError("Run without -O: this verification requires active assertions")
url = os.environ["SESSION2_POSTGRES_URL"]
parsed = urlparse(url)
assert parsed.scheme in {"postgresql", "postgresql+psycopg2"}
assert (
    not parsed.query and not parsed.fragment
), "Connection URL overrides are forbidden"
assert parsed.hostname in {"127.0.0.1", "localhost"}
assert parsed.path.startswith("/audit_app_session2")
os.environ["DATABASE_URL"] = url
os.environ["TEST_DATABASE_URL"] = url
os.environ["REDIS_URL"] = ""

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from datetime import datetime
from models import (
    Base,
    Country,
    Entity,
    EntityType,
    FiscalPeriod,
    SourceDocument,
    DocumentType,
    Audit,
    Severity,
)
from services.county_identity import OFFICIAL_COUNTY_CODES

engine = create_engine(url)
inspector = inspect(engine)
assert set(inspector.get_schema_names()) - {"information_schema"} == {
    "public"
}, "Use a fresh database"
assert not any(
    (
        inspector.get_table_names(),
        inspector.get_view_names(),
        inspector.get_materialized_view_names(),
        inspector.get_sequence_names(),
        inspector.get_enums(),
    )
), "Use a fresh empty disposable database"
Base.metadata.create_all(engine)
with Session(engine) as db:
    country = Country(
        id=1,
        name="Kenya",
        iso_code="KEN",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en-KE",
    )
    db.add(country)
    db.flush()
    db.add(
        Entity(
            id=1,
            country_id=1,
            type=EntityType.NATIONAL,
            canonical_name="National Government",
            slug="national-government",
        )
    )
    for code, name in OFFICIAL_COUNTY_CODES.items():
        db.add(
            Entity(
                id={"001": 4, "047": 3}.get(code, 100 + int(code)),
                country_id=1,
                type=EntityType.COUNTY,
                canonical_name=name + " County",
                slug=name.lower().replace(" ", "-").replace("'", "") + "-county",
            )
        )
    db.flush()
    period = FiscalPeriod(
        id=1,
        country_id=1,
        label="FY2025/26",
        start_date=datetime(2025, 7, 1),
        end_date=datetime(2026, 6, 30),
    )
    source = SourceDocument(
        id=1,
        country_id=1,
        title="Synthetic identity verification document",
        publisher="Test fixture",
        url="https://example.org/identity-test.pdf",
        doc_type=DocumentType.AUDIT,
        fetch_date=datetime(2026, 9, 27),
    )
    db.add_all([period, source])
    db.flush()
    for eid in (3, 4):
        db.add(
            Audit(
                entity_id=eid,
                period_id=1,
                source_document_id=1,
                finding_text=f"Synthetic route verification for entity {eid}",
                amount=eid,
                severity=Severity.WARNING,
                page_ref="p.1",
            )
        )
    db.commit()

import pytest

nodes = [
    "tests/integration/test_api.py::TestCountiesAPI::test_invalid_county_id",
    "tests/integration/test_api.py::TestDataValidation::test_sql_injection_prevention",
    "tests/integration/test_public_routes.py::test_public_get_routes[route17]",
    "tests/integration/test_public_routes.py::test_public_get_routes[route20]",
    "tests/integration/test_public_routes.py::test_public_get_routes[route21]",
]
os.chdir(ROOT)
status = pytest.main([*nodes, "-q", "--tb=short", "--capture=sys"])
assert status == 0, status

from fastapi.testclient import TestClient
from main import app, clear_all_caches
import logging

logging.disable(logging.CRITICAL)
app.dependency_overrides.clear()
client = TestClient(app)
for suffix in ("audits", "accountability", "summary"):
    clear_all_caches()
    missing = client.get(f"/api/v1/counties/1/{suffix}")
    assert missing.status_code == 404, (suffix, missing.status_code, missing.text)
    for identifier, expected_county in {
        "3": "Nairobi",
        "4": "Mombasa",
        "001": "Nairobi",
        "047": "Mombasa",
        "nairobi-county": "Nairobi",
        "mombasa-county": "Mombasa",
        "code:001": "Mombasa",
        "code:047": "Nairobi",
    }.items():
        clear_all_caches()
        response = client.get(f"/api/v1/counties/{identifier}/{suffix}")
        assert response.status_code == 200, (
            suffix,
            identifier,
            response.status_code,
            response.text,
        )
        assert response.json()["county_name"] == expected_county, (
            suffix,
            identifier,
            response.json(),
        )
print(
    "PostgreSQL: five exact integration nodes passed; national PK 1 rejected on three county routes; 24 valid identity-route controls returned 200 with the expected county."
)

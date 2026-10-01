"""#407: actual parser/writer and HTTP publication of legacy budget evidence.

The fixture is the unchanged ten Mandera rows captured from the callable
generator at 713e519, in an owned TemporaryDirectory. No official amounts are
asserted here. Set LEGACY_BUDGET_TEST_POSTGRES_URL for JSONB/Numeric coverage.
"""

import asyncio
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

import main
from models import Base, BudgetLine, Country, Entity, EntityType, FiscalPeriod
from seeding.config import SeedingSettings
from seeding.domains.counties_budget.parser import parse_budget_payload
from seeding.domains.counties_budget.writer import persist_budget_records
from seeding.types import DomainRunContext
from services.entity_financials import budget_line_is_unreported


@pytest.fixture
def legacy_db(db_session):
    url = os.environ.get("LEGACY_BUDGET_TEST_POSTGRES_URL")
    if not url:
        yield db_session
        return
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql"
    assert parsed.host in {"127.0.0.1", "localhost", "::1"}
    assert not parsed.query  # no alternate remote host via libpq options
    schema = "round7_session1_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        with sessionmaker(bind=engine)() as session:
            yield session
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@pytest.fixture
def legacy_client(legacy_db, monkeypatch):
    def get_db():
        yield legacy_db

    original_get_db = main.get_db
    monkeypatch.setattr(main, "get_db", get_db)
    monkeypatch.setattr(main, "DATABASE_AVAILABLE", True)
    main.app.dependency_overrides[original_get_db] = get_db
    # These handlers need no startup or external services.
    try:
        yield TestClient(main.app, raise_server_exceptions=False)
    finally:
        main.app.dependency_overrides.clear()
        main.clear_all_caches()


@pytest.fixture
def mandera(legacy_db):
    country = Country(
        iso_code="KEN",
        name="Kenya",
        currency="KES",
        timezone="UTC",
        default_locale="en",
    )
    legacy_db.add(country)
    legacy_db.flush()
    entity = Entity(
        country_id=country.id,
        type=EntityType.COUNTY,
        canonical_name="Mandera County",
        slug="mandera-county",
        meta={"code": "009"},
    )
    legacy_db.add(entity)
    legacy_db.commit()
    return entity


def _write(db, tmp_path, rows):
    stats = persist_budget_records(
        db,
        parse_budget_payload(rows),
        SeedingSettings(_env_file=None, cache_path=tmp_path),
        DomainRunContext(since=None, dry_run=False),
    )
    assert stats.errors == []
    db.commit()
    return stats


def _row(**changes):
    return {
        "entity_slug": "mandera-county",
        "entity": "Mandera County",
        "period_label": "2024/25",
        "start_date": "2024-07-01",
        "end_date": "2025-06-30",
        "category": "Total",
        "allocated_amount": 2000,
        "actual_amount": 1000,
        "currency": "KES",
        "source_url": "https://cob.go.ke/synthetic-session1.pdf",
        "publisher": "Controller of Budget",
        "source_label": "County Budget Implementation Review Report FY2024/25",
        "data_quality": "official",
        "page_ref": "PDF pp. 7",
        "artifact_sha256": "a" * 64,
        **changes,
    }


def _budget(client, route="mandera-county"):
    response = client.get(f"/api/v1/counties/{route}/budget")
    assert response.status_code == 200, response.text
    return response.json()


def test_generated_estimates_stay_archival_across_real_writer_and_all_readers(
    legacy_db,
    legacy_client,
    mandera,
    tmp_path,
):
    rows = json.loads(
        (
            Path(__file__).parent / "fixtures/legacy_generated_mandera_budget.json"
        ).read_text()
    )
    assert (
        len(rows) == 10
        and sum(row["allocated_amount"] for row in rows) == 8922097199.58
    )
    assert _write(legacy_db, tmp_path, rows).created == 10
    stored = legacy_db.query(BudgetLine).all()
    assert all(budget_line_is_unreported(row) for row in stored)
    assert all(row.provenance[0]["data_quality"] == "estimated" for row in stored)
    budget = _budget(legacy_client)
    assert budget["budget_2025"] is None
    assert budget["total_spent"] is None
    assert budget["budget_execution_rate"] is None
    assert (
        budget["financial_summary"]["absent_reasons"]["total_allocation"]
        == "no_reported_total"
    )
    detail = legacy_client.get("/api/v1/counties/mandera-county/comprehensive")
    assert detail.status_code == 200, detail.text
    listing = legacy_client.get("/api/v1/counties?limit=50")
    assert listing.status_code == 200, listing.text
    county = next(row for row in listing.json() if row["name"] == "Mandera")
    assert county["total_budget"] is detail.json()["budget"]["total_allocated"] is None
    assert county["total_spent"] is detail.json()["budget"]["total_spent"] is None


@pytest.mark.parametrize(
    "allocation,spent,rate,reason",
    [
        (2000, 1000, 50, None),
        (2000, None, None, "spending_not_reported"),
        (2000, 0, 0, None),
        (0, 0, None, "no_positive_allocation"),
        (None, 0, None, "no_positive_allocation"),
    ],
)
def test_source_total_preserves_absence_and_genuine_zero(
    legacy_db,
    legacy_client,
    mandera,
    tmp_path,
    allocation,
    spent,
    rate,
    reason,
):
    _write(
        legacy_db, tmp_path, [_row(allocated_amount=allocation, actual_amount=spent)]
    )
    result = _budget(legacy_client)
    assert result["budget_2025"] == allocation
    assert result["total_spent"] == spent
    assert result["budget_execution_rate"] == rate
    summary = result["financial_summary"]
    assert summary["sources"][0]["url"] == _row()["source_url"]
    assert summary["sources"][0]["page_refs"] == ["PDF pp. 7"]
    assert summary["fiscal_period"]["start_date"] == "2024-07-01T00:00:00"
    assert summary["currency"] == "KES"
    assert summary["accounting_basis"] == "reported_total"
    assert summary["absent_reasons"].get("execution_rate") == reason


def test_real_total_survives_unreported_classification_and_sector_noise(
    legacy_db,
    legacy_client,
    mandera,
    tmp_path,
):
    _write(legacy_db, tmp_path, [_row()])
    _write(
        legacy_db,
        tmp_path,
        [
            _row(
                category=category,
                allocated_amount=999999,
                actual_amount=999999,
                data_quality="estimated",
                source_url="https://www.crakenya.org/synthetic-session1",
            )
            for category in ("Recurrent", "Development", "Health")
        ],
    )
    result = _budget(legacy_client)
    assert result["budget_2025"] == 2000
    assert result["total_spent"] == 1000
    assert result["budget_execution_rate"] == 50
    assert result["financial_summary"]["budget_lines_count"] == 1


@pytest.mark.parametrize("value", [True, False, "NaN", "sNaN", "Infinity", "-Infinity"])
def test_malformed_amounts_through_parser_writer_never_become_zero_execution(
    legacy_db,
    legacy_client,
    mandera,
    tmp_path,
    value,
):
    _write(legacy_db, tmp_path, [_row(actual_amount=value)])
    assert legacy_db.query(BudgetLine).one().actual_spent is None
    result = _budget(legacy_client)
    assert result["budget_2025"] == 2000
    assert result["budget_execution_rate"] is None
    assert result["total_spent"] is None
    assert result["absent_reasons"]["execution_rate"] == "spending_not_reported"


def test_newer_estimates_do_not_displace_older_reported_account(
    legacy_db,
    legacy_client,
    mandera,
    tmp_path,
):
    _write(legacy_db, tmp_path, [_row()])
    _write(
        legacy_db,
        tmp_path,
        [
            _row(
                period_label="2025/26",
                start_date="2025-07-01",
                end_date="2026-06-30",
                data_quality="estimated",
                source_url="https://www.crakenya.org/synthetic-session1",
            )
        ],
    )
    result = _budget(legacy_client)
    assert result["budget_2025"] == 2000
    assert result["fiscal_period"]["start_date"] == "2024-07-01T00:00:00"
    detail = legacy_client.get("/api/v1/counties/mandera-county/comprehensive")
    assert detail.status_code == 200
    assert detail.json()["budget"]["fiscal_period"] == result["fiscal_period"]


@pytest.mark.parametrize(
    "route", ["009", "code:009", "Mandera", "mandera-county", "pk"]
)
def test_legacy_official_slug_and_entity_routes_and_direct_callable(
    legacy_db,
    legacy_client,
    mandera,
    tmp_path,
    route,
):
    _write(legacy_db, tmp_path, [_row()])
    route = str(mandera.id) if route == "pk" else route
    result = _budget(legacy_client, route)
    assert result["county_id"] == route and result["county_name"] == "Mandera"
    assert result["budget_2025"] == 2000
    assert asyncio.run(main.get_county_budget(route)) == result


def test_reported_classification_parts_survive_estimated_sector_noise(
    legacy_db,
    legacy_client,
    mandera,
    tmp_path,
):
    _write(
        legacy_db,
        tmp_path,
        [
            _row(category="Recurrent", allocated_amount=1200, actual_amount=0),
            _row(category="Development", allocated_amount=800, actual_amount=0),
        ],
    )
    _write(
        legacy_db,
        tmp_path,
        [
            _row(
                category="Health",
                allocated_amount=999999,
                actual_amount=999999,
                data_quality="estimated",
                source_url="https://www.crakenya.org/synthetic-session1",
            )
        ],
    )
    result = _budget(legacy_client)
    assert result["budget_2025"] == 2000 and result["budget_execution_rate"] == 0
    assert (
        result["financial_summary"]["accounting_basis"] == "recurrent_plus_development"
    )


@pytest.mark.parametrize("missing_field", ["allocated_amount", "actual_amount"])
def test_partial_classification_account_does_not_become_a_partial_total(
    legacy_db,
    legacy_client,
    mandera,
    tmp_path,
    missing_field,
):
    _write(
        legacy_db,
        tmp_path,
        [
            _row(category="Recurrent", allocated_amount=1200, actual_amount=600),
            _row(
                **{
                    "category": "Development",
                    "allocated_amount": 800,
                    "actual_amount": 400,
                    missing_field: None,
                }
            ),
        ],
    )
    result = _budget(legacy_client)
    assert result["budget_execution_rate"] is None
    if missing_field == "allocated_amount":
        assert result["budget_2025"] is None
        assert result["total_spent"] == 1000
        assert result["absent_reasons"]["total_allocation"] == "allocation_not_reported"
    else:
        assert result["budget_2025"] == 2000
        assert result["total_spent"] is None
        assert result["absent_reasons"]["total_spent"] == "spending_not_reported"


@pytest.mark.parametrize(
    "case,reason",
    [
        ("sector", "no_reported_total"),
        ("one_part", "incomplete_classification"),
        ("estimated_total", "not_reported_actuals"),
        ("conflicting_sources", "multiple_sources"),
        ("bad_dates", "no_valid_period"),
        ("mixed_currency", "incompatible_currencies"),
    ],
)
def test_unsupported_and_conflicting_accounts_are_withheld(
    legacy_db,
    legacy_client,
    mandera,
    tmp_path,
    case,
    reason,
):
    rows = [_row()]
    if case == "sector":
        rows = [_row(category="Health")]
    if case == "one_part":
        rows = [_row(category="Recurrent")]
    if case == "estimated_total":
        rows = [_row(data_quality="estimated")]
    if case == "conflicting_sources":
        rows = [
            _row(category="Recurrent"),
            _row(
                category="Development",
                source_url="https://cob.go.ke/other-session1.pdf",
            ),
        ]
    if case == "mixed_currency":
        rows = [
            _row(category="Recurrent"),
            _row(category="Development", currency="USD"),
        ]
    _write(legacy_db, tmp_path, rows)
    if case == "bad_dates":
        legacy_db.query(FiscalPeriod).one().end_date = date(2020, 1, 1)
        legacy_db.commit()
    result = _budget(legacy_client)
    assert result["budget_2025"] is None
    assert result["budget_execution_rate"] is None
    assert result["financial_summary"]["absent_reasons"]["total_allocation"] == reason


def test_same_start_annual_and_interim_period_use_the_same_account_as_detail(
    legacy_db,
    legacy_client,
    mandera,
    tmp_path,
):
    # Different source URLs avoid the writer's intentional stale-edition refusal.
    _write(
        legacy_db,
        tmp_path,
        [
            _row(
                period_label="2024/25 9M",
                end_date="2025-03-31",
                allocated_amount=999,
                source_url="https://cob.go.ke/interim-session1.pdf",
            )
        ],
    )
    _write(legacy_db, tmp_path, [_row()])
    result = _budget(legacy_client)
    assert result["budget_2025"] == 2000
    assert (
        result["financial_summary"]["fiscal_period"]["end_date"]
        == "2025-06-30T23:59:59.999999"
    )
    detail = legacy_client.get("/api/v1/counties/mandera-county/comprehensive")
    assert detail.status_code == 200
    assert detail.json()["budget"]["total_allocated"] == result["budget_2025"]


def test_no_lines_is_an_honest_success_and_unknown_county_is_404(
    legacy_client, mandera
):
    result = _budget(legacy_client)
    assert result["budget_2025"] is result["budget_execution_rate"] is None
    assert result["financial_summary"]["absent_reasons"]
    assert (
        legacy_client.get("/api/v1/counties/unknown-session1/budget").status_code == 404
    )


def test_db_unavailable_or_failed_cannot_publish_proxy_estimates(
    legacy_client, monkeypatch
):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Retired proxy must never be consulted")

    monkeypatch.setattr(main.InternalAPIClient, "get_county_financial_data", forbidden)
    monkeypatch.setattr(main.InternalAPIClient, "get_county_data", forbidden)
    monkeypatch.setattr(main, "DATABASE_AVAILABLE", False)
    assert legacy_client.get("/api/v1/counties/009/budget").status_code == 503
    monkeypatch.setattr(main, "DATABASE_AVAILABLE", True)

    def broken_db():
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr(main, "get_db", broken_db)
    assert legacy_client.get("/api/v1/counties/009/budget").status_code == 500


@pytest.mark.parametrize(
    "amount", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("-1")]
)
def test_postgres_hostile_numeric_is_withheld_at_http(
    legacy_db,
    legacy_client,
    mandera,
    tmp_path,
    amount,
):
    if legacy_db.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL Numeric special-value semantics")
    _write(legacy_db, tmp_path, [_row()])
    row = legacy_db.query(BudgetLine).one()
    row.allocated_amount = amount
    legacy_db.commit()
    result = _budget(legacy_client)
    assert result["budget_2025"] is None
    assert result["budget_execution_rate"] is None
    assert (
        result["financial_summary"]["absent_reasons"]["total_allocation"]
        == "allocation_not_reported"
    )

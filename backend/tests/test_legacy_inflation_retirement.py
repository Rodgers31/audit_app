"""Issue #474: actual public readers must not serve the retired MVP alias."""
import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from models import EconomicIndicator
from services.publication_gate import economic_publication_failure

LEGACY = "inflation_rate_cpi"
REASON = "retired unsupported inflation alias"


def _row(kind=LEGACY, *, value=6.3, date=None, entity_id=None, source_id=None):
    return EconomicIndicator(
        indicator_type=kind,
        indicator_date=date or datetime(2024, 1, 31),
        value=value,
        unit="percent",
        entity_id=entity_id,
        source_document_id=source_id,
        confidence=1,
        publishable=True,
        meta={"data_quality": "official", "source_label": "KNBS CPI"},
    )


def test_filtered_public_indicators_withhold_official_looking_legacy(
    client, db_session, seed_source_doc
):
    legacy = _row(source_id=seed_source_doc.id)
    db_session.add(legacy)
    db_session.commit()
    response = client.get(f"/api/v1/economic/indicators?indicator_type={LEGACY}&limit=1")
    assert response.status_code == 200
    assert response.json() == []
    assert response.headers["X-Economic-Withheld-Count"] == "1"
    assert response.headers["X-Economic-Withheld-Reasons"] == REASON
    # Reader retirement does not rewrite or remove the stored historical tuple.
    db_session.refresh(legacy)
    assert legacy.value == Decimal("6.30")
    assert legacy.source_document_id == seed_source_doc.id


def test_unfiltered_public_limit_skips_legacy_and_returns_maintained_precision(
    client, db_session
):
    db_session.add_all([
        _row(date=datetime(2026, 9, 30)),
        _row("inflation_rate_12m", value=6.85, date=datetime(2024, 1, 31)),
    ])
    db_session.commit()
    response = client.get("/api/v1/economic/indicators?limit=1")
    assert response.status_code == 200
    assert [(r["indicator_type"], r["value"]) for r in response.json()] == [
        ("inflation_rate_12m", 6.85)
    ]
    assert response.headers["X-Economic-Withheld-Count"] == "1"


def test_county_profile_withholds_legacy_with_reason(client, db_session, seed_entity):
    db_session.add(_row(date=datetime.now(), entity_id=seed_entity.id))
    db_session.commit()
    response = client.get(f"/api/v1/economic/counties/{seed_entity.id}/profile")
    assert response.status_code == 200
    profile = response.json()
    assert profile["economic_indicators"] == []
    assert profile["withheld_indicator_count"] == 1
    assert profile["indicator_publication_notes"] == [REASON]


@pytest.mark.parametrize(
    "kind,value",
    [("inflation_rate_12m", 0), ("inflation_rate_12m", 7.88),
     ("inflation_rate_12m", 3.28), ("inflation_rate", 4.49),
     ("cpi_index", 142.68)],
)
def test_maintained_measures_and_zero_still_publish(client, db_session, kind, value):
    db_session.add(_row(kind, value=value))
    db_session.commit()
    response = client.get(f"/api/v1/economic/indicators?indicator_type={kind}")
    assert response.status_code == 200
    assert [(r["indicator_type"], r["value"]) for r in response.json()] == [(kind, value)]
    assert response.headers["X-Economic-Withheld-Count"] == "0"


@pytest.mark.parametrize(
    "value", [None, True, Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")]
)
def test_nonfinite_gate_is_preserved(value):
    row = SimpleNamespace(value=value, indicator_type="inflation_rate_12m")
    assert economic_publication_failure(row, None) == "non-finite economic value"


def test_retired_alias_cannot_be_revived_by_case_or_official_claim():
    row = _row("INFLATION_RATE_CPI")
    assert economic_publication_failure(row, None) == REASON


def test_budget_zero_is_available_not_legacy_or_absent(client, db_session):
    db_session.add_all([_row(), _row("inflation_rate_12m", value=0)])
    db_session.commit()
    response = client.get("/api/v1/budget/enhanced")
    assert response.status_code == 200
    context = response.json()["economic_context"]
    assert context["inflation_pct"] == 0
    assert context["inflation_missing_reason"] is None


def test_summary_does_not_promote_legacy_only(client, db_session):
    db_session.add(_row())
    db_session.commit()
    response = client.get("/api/v1/economic/summary")
    assert response.status_code == 200
    assert response.json()["inflation_rate"] is None


def test_deprecated_fixture_generator_omits_retired_inflation(tmp_path):
    from seeding.domains.real_data_fetcher import RealDataFetcher

    records = RealDataFetcher(str(tmp_path)).fetch_knbs_economic_indicators()
    on_disk = json.loads((tmp_path / "economic_indicators.json").read_text())
    assert records == on_disk
    assert not any(row["indicator_type"] == LEGACY for row in records)

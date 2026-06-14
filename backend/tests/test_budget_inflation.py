"""Budget page inflation reads the live series, not the stale MVP key (audit §3.10).

`/budget/enhanced` economic_context showed inflation = 6.3% frozen at Jan-2024
because it read `inflation_rate_cpi` — a key written ONLY by the hardcoded MVP
seeder. The maintained `inflation_rate` series (the one /economic/summary uses)
carries the current value. These tests lock in that the budget page reads the
canonical series (so it self-updates and matches the rest of the site), and
falls back to the legacy key only when the series is absent.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from models import EconomicIndicator


@pytest.fixture()
def seed_inflation_series(db_session):
    db_session.add_all(
        [
            # Stale MVP leftover — must NOT be what the budget page shows.
            EconomicIndicator(
                indicator_type="inflation_rate_cpi",
                indicator_date=datetime(2024, 1, 31),
                value=6.3,
                unit="percent",
            ),
            # Canonical maintained series — latest by date wins.
            EconomicIndicator(
                indicator_type="inflation_rate",
                indicator_date=datetime(2024, 6, 30),
                value=4.6,
                unit="percent",
            ),
            EconomicIndicator(
                indicator_type="inflation_rate",
                indicator_date=datetime(2025, 1, 31),
                value=3.3,
                unit="percent",
            ),
        ]
    )
    db_session.commit()


def test_budget_inflation_uses_canonical_series_not_stale_cpi(client, seed_inflation_series):
    resp = client.get("/api/v1/budget/enhanced")
    assert resp.status_code == 200
    ec = resp.json()["economic_context"]
    # Latest `inflation_rate` (3.3, Jan-2025) — NOT the stale `inflation_rate_cpi` 6.3.
    assert ec["inflation_pct"] == 3.3
    assert ec["inflation_as_of"].startswith("2025-01")
    assert ec["inflation_source"] == "KNBS Consumer Price Index"


def test_budget_inflation_falls_back_to_legacy_key(client, db_session):
    # When the canonical series is absent, fall back to the dated legacy key.
    db_session.add(
        EconomicIndicator(
            indicator_type="inflation_rate_cpi",
            indicator_date=datetime(2024, 1, 31),
            value=6.3,
            unit="percent",
        )
    )
    db_session.commit()
    resp = client.get("/api/v1/budget/enhanced")
    assert resp.status_code == 200
    ec = resp.json()["economic_context"]
    assert ec["inflation_pct"] == 6.3
    assert ec["inflation_as_of"].startswith("2024-01")

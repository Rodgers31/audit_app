"""Regression tests for the GDP single-source-of-truth fix (audit §3.1).

Background: the headline debt-to-GDP read 82% because ``/debt/national``
divided current debt by a hardcoded GDP constant of 15.4T (the real
nominal GDP is ~16-18T). Two divergent hardcoded GDP series existed
(bootstrap = 15.4T, debt_timeline = 18.4T). These tests lock in:

  1. GDP is parsed from the World Bank API in raw KES.
  2. A failed live fetch degrades to the World Bank-sourced fixture
     (last-known-good), never a hardcoded estimate.
  3. No hardcoded national GDP series remains in code.
  4. The fixture denominator is plausible, so the computed ratio can no
     longer reach the old inflated 82%.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from seeding.config import SeedingSettings
from seeding.domains.national_gdp.fetcher import (
    _FIXTURE_URL,
    _parse_wb_gdp,
    fetch_national_gdp_kes,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURE_PATH = BACKEND_DIR / "seeding" / "real_data" / "national_gdp.json"


# ── 1. World Bank parse: raw KES, drop nulls ────────────────────────────
def test_parse_wb_gdp_returns_raw_kes_and_drops_nulls():
    payload = [
        {"page": 1, "pages": 1},  # WB metadata element
        [
            {"date": "2025", "value": None},  # not yet published → dropped
            {"date": "2024", "value": 16224478000000.0},
            {"date": "2023", "value": 15033610000000.0},
        ],
    ]
    result = _parse_wb_gdp(payload)
    assert result == {2024: 16224478000000, 2023: 15033610000000}
    # Raw KES, NOT billions (a unit slip here is exactly the kind of bug
    # the audit flagged).
    assert result[2024] > 1e13


def test_parse_wb_gdp_rejects_bad_shape():
    with pytest.raises(ValueError):
        _parse_wb_gdp({"not": "a list"})


# ── 2. Fixture fallback (last-known-good, never hardcoded) ──────────────
def test_fetch_falls_back_to_fixture_when_api_unavailable():
    class _BoomClient:
        def get(self, *a, **k):
            raise RuntimeError("simulated World Bank outage")

    settings = SeedingSettings(enrich_with_worldbank=True)
    gdp = fetch_national_gdp_kes(_BoomClient(), settings)
    # Fixture has 2018-2024 World Bank actuals.
    assert 2024 in gdp
    assert gdp[2024] == 16224478000000


def test_fixture_url_points_at_repo_fixture():
    assert _FIXTURE_URL.endswith("seeding/real_data/national_gdp.json")
    assert FIXTURE_PATH.exists()


# ── 3. No hardcoded GDP series remains in code ──────────────────────────
@pytest.mark.parametrize(
    "rel_path",
    [
        "bootstrap.py",
        "seeding/domains/national_gdp/__init__.py",
    ],
)
def test_no_hardcoded_gdp_series(rel_path):
    src = (BACKEND_DIR / rel_path).read_text(encoding="utf-8")
    assert "NATIONAL_GDP_SERIES = [" not in src, (
        f"{rel_path} still defines a hardcoded GDP series"
    )
    # The specific wrong constant that produced the 82% ratio.
    assert "15_400_000_000_000" not in src
    assert "14_800_000_000_000" not in src


# ── 4. Fixture denominator is plausible (kills the 82% inflation) ───────
def test_fixture_gdp_is_plausible_and_lowers_ratio():
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    rows = {int(r["year"]): int(r["gdp_kes"]) for r in data["gdp"]}
    latest_year = max(rows)
    latest_gdp = rows[latest_year]
    # Kenya nominal GDP is on the order of 15-18 trillion KES.
    assert 14e12 < latest_gdp < 20e12, latest_gdp

    # A ~12.66T debt stock against the OLD hardcoded 15.4T gave 82.2%.
    # Against the real World Bank denominator it must be materially lower,
    # i.e. the denominator inflation is gone.
    debt = 12_660_000_000_000
    old_ratio = debt / 15_400_000_000_000 * 100
    new_ratio = debt / latest_gdp * 100
    assert round(old_ratio, 1) == pytest.approx(82.2, abs=0.3)
    assert new_ratio < 80.0

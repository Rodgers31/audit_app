"""Fetch economic indicator payload.

Loads indicators from live sources first (World Bank API for GDP, inflation,
unemployment, CPI), then falls back to the configured fixture if live APIs
are unavailable.  Fixture data is used ONLY as a fallback, never as the
primary source.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource

logger = logging.getLogger("seeding.economic_indicators.fetcher")

# ── World Bank Indicator URLs (free, no auth required) ──────────────

_WB_BASE = "https://api.worldbank.org/v2/country/KEN/indicator"

# GDP & growth
_WB_INDICATORS = {
    "NY.GDP.MKTP.CN": {
        "indicator_type": "total_national_gdp",
        "unit": "KES_millions",
        "divisor": 1e6,
        "round_digits": 0,
        "description": "GDP current LCU",
    },
    "NY.GDP.MKTP.KD.ZG": {
        "indicator_type": "gdp_growth_rate",
        "unit": "percent",
        "divisor": 1,
        "round_digits": 1,
        "description": "GDP growth annual %",
    },
    # CPI / inflation
    "FP.CPI.TOTL.ZG": {
        "indicator_type": "inflation_rate",
        "unit": "percent",
        "divisor": 1,
        "round_digits": 1,
        "description": "Consumer price inflation annual %",
    },
    # Unemployment
    "SL.UEM.TOTL.ZS": {
        "indicator_type": "unemployment_rate",
        "unit": "percent",
        "divisor": 1,
        "round_digits": 1,
        "description": "Unemployment % of total labor force (ILO)",
    },
    # CPI index (2010 = 100)
    "FP.CPI.TOTL": {
        "indicator_type": "cpi_index",
        "unit": "index_2010_100",
        "divisor": 1,
        "round_digits": 1,
        "description": "Consumer price index (2010 = 100)",
    },
    # Government revenue as % of GDP
    "GC.REV.TOTL.GD.ZS": {
        "indicator_type": "govt_revenue_pct_gdp",
        "unit": "percent",
        "divisor": 1,
        "round_digits": 1,
        "description": "Government revenue % of GDP",
    },
    # Government expenditure as % of GDP
    "GC.XPN.TOTL.GD.ZS": {
        "indicator_type": "govt_expenditure_pct_gdp",
        "unit": "percent",
        "divisor": 1,
        "round_digits": 1,
        "description": "Government expenditure % of GDP",
    },
}


def _fetch_wb_indicators(client: SeedingHttpClient) -> list[dict[str, Any]]:
    """Fetch all economic indicators from the World Bank API.

    Returns a list of indicator dicts matching the economic_indicators
    fixture format (indicator_type, date, value, unit, source, etc.).
    Fetches multiple years per indicator for historical context.
    """
    all_indicators: list[dict[str, Any]] = []

    for indicator_code, meta in _WB_INDICATORS.items():
        try:
            url = f"{_WB_BASE}/{indicator_code}"
            logger.info(
                "Fetching World Bank indicator %s (%s)...",
                indicator_code,
                meta["description"],
            )

            resp = client.get(
                url,
                params={"format": "json", "per_page": "20", "date": "2015:2026"},
                raise_for_status=True,
            )
            wb_data = resp.json()

            if not isinstance(wb_data, list) or len(wb_data) < 2 or not wb_data[1]:
                logger.warning(
                    "World Bank API returned no data for %s", indicator_code
                )
                continue

            records = wb_data[1]
            fetched_count = 0

            for item in sorted(records, key=lambda x: x["date"], reverse=True):
                if item.get("value") is None:
                    continue

                year = int(item["date"])
                raw_value = item["value"]
                value = round(raw_value / meta["divisor"], meta["round_digits"])

                # For integer-rounded values, convert to int for cleaner output
                if meta["round_digits"] == 0:
                    value = int(value)

                all_indicators.append({
                    "indicator_type": meta["indicator_type"],
                    "date": f"{year}-12-31",
                    "value": value,
                    "unit": meta["unit"],
                    "source_url": (
                        f"https://data.worldbank.org/indicator/"
                        f"{indicator_code}?locations=KE"
                    ),
                    "source": (
                        f"World Bank Development Indicators – "
                        f"{meta['description']} ({year})"
                    ),
                    "data_quality": "official",
                    "notes": (
                        f"Live from World Bank API ({indicator_code}), "
                        f"year {year}"
                    ),
                })
                fetched_count += 1

            if fetched_count:
                logger.info(
                    "World Bank %s: fetched %d year(s) of data",
                    indicator_code,
                    fetched_count,
                )

        except Exception as exc:
            logger.warning(
                "Failed to fetch World Bank indicator %s: %s",
                indicator_code,
                exc,
            )

    return all_indicators


def _merge_indicators(
    base: list[dict[str, Any]], live: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge live indicators into base, preferring live data over fixture.

    For each (indicator_type, date) pair, live data takes precedence.
    Fixture entries are kept only if no live data exists for that
    indicator_type + date combination.
    """
    # Index live data by (indicator_type, date)
    live_keys: set[tuple[str, str]] = set()
    for item in live:
        key = (item.get("indicator_type", ""), item.get("date", ""))
        live_keys.add(key)

    # Keep fixture entries that don't overlap with live data
    merged = list(live)  # start with all live data
    kept_from_fixture = 0
    for item in base:
        key = (item.get("indicator_type", ""), item.get("date", ""))
        if key not in live_keys:
            merged.append(item)
            kept_from_fixture += 1

    logger.info(
        "Merged indicators: %d live + %d fixture-only = %d total",
        len(live),
        kept_from_fixture,
        len(merged),
    )

    return merged


def fetch_economic_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> list[dict[str, Any]]:
    """Fetch economic indicators, prioritizing live World Bank API data.

    Strategy:
    1. Fetch live indicators from World Bank API (GDP, inflation,
       unemployment, CPI, govt revenue/expenditure).
    2. Load fixture as fallback/supplement for indicators not available
       via World Bank (e.g., Kenya-specific metrics).
    3. Merge: live data takes precedence; fixture fills gaps.
    """
    live_indicators: list[dict[str, Any]] = []

    # Step 1: Try live World Bank API
    if settings.enrich_with_worldbank:
        try:
            live_indicators = _fetch_wb_indicators(client)
            if live_indicators:
                logger.info(
                    "Fetched %d live indicators from World Bank API",
                    len(live_indicators),
                )
        except Exception as exc:
            logger.warning("World Bank API fetch failed entirely: %s", exc)

    # Step 2: Load fixture as supplement
    try:
        fixture_data = load_json_resource(
            url=settings.economic_indicators_dataset_url,
            client=client,
            logger=logger,
            label="economic_indicators",
        )
        if not isinstance(fixture_data, list):
            fixture_data = []
    except Exception as exc:
        logger.warning("Failed to load economic indicators fixture: %s", exc)
        fixture_data = []

    # Step 3: Merge — live takes precedence
    if live_indicators:
        return _merge_indicators(fixture_data, live_indicators)
    elif fixture_data:
        logger.warning(
            "No live data available — using fixture as fallback "
            "(data may be stale)"
        )
        return fixture_data
    else:
        raise ValueError(
            "No economic indicators available from either live API or fixture"
        )

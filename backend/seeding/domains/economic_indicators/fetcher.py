"""Fetch economic indicator payload.

Loads indicators from the configured fixture/API, then optionally enriches
GDP data with the World Bank API for the latest available values.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource

logger = logging.getLogger("seeding.economic_indicators.fetcher")

# World Bank indicator: GDP in current LCU (KES for Kenya)
_WB_GDP_URL = (
    "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN"
    "?format=json&per_page=10"
)

# World Bank indicator: GDP growth (annual %)
_WB_GDP_GROWTH_URL = (
    "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.KD.ZG"
    "?format=json&per_page=10"
)


def _fetch_wb_gdp_indicators(client: SeedingHttpClient) -> list[dict[str, Any]]:
    """Fetch latest GDP indicators from World Bank API.

    Returns a list of indicator dicts matching the economic_indicators
    fixture format (indicator_type, date, value, unit, source, etc.).
    """
    extra_indicators: list[dict[str, Any]] = []

    # ── Nominal GDP (current LCU → KES millions) ──────────────────
    try:
        resp = client.get(_WB_GDP_URL, raise_for_status=True)
        wb_data = resp.json()
        if isinstance(wb_data, list) and len(wb_data) >= 2 and wb_data[1]:
            # Find most recent non-null value
            for item in sorted(wb_data[1], key=lambda x: x["date"], reverse=True):
                if item.get("value") is not None:
                    year = int(item["date"])
                    # WB value is in raw KES; convert to millions to match fixture
                    value_millions = round(item["value"] / 1e6)
                    extra_indicators.append({
                        "indicator_type": "total_national_gdp",
                        "date": f"{year}-12-31",
                        "value": value_millions,
                        "unit": "KES_millions",
                        "source_url": "https://data.worldbank.org/indicator/NY.GDP.MKTP.CN?locations=KE",
                        "source": f"World Bank National Accounts – GDP current LCU ({year})",
                        "data_quality": "official",
                        "notes": f"Nominal GDP from World Bank API (NY.GDP.MKTP.CN), year {year}",
                    })
                    logger.info("World Bank GDP (nominal): %s = %s million KES", year, value_millions)
                    break
    except Exception as exc:
        logger.warning("Failed to fetch World Bank nominal GDP: %s", exc)

    # ── GDP growth rate (annual %) ─────────────────────────────────
    try:
        resp = client.get(_WB_GDP_GROWTH_URL, raise_for_status=True)
        wb_data = resp.json()
        if isinstance(wb_data, list) and len(wb_data) >= 2 and wb_data[1]:
            for item in sorted(wb_data[1], key=lambda x: x["date"], reverse=True):
                if item.get("value") is not None:
                    year = int(item["date"])
                    growth = round(item["value"], 1)
                    extra_indicators.append({
                        "indicator_type": "gdp_growth_rate",
                        "date": f"{year}-12-31",
                        "value": growth,
                        "unit": "percent",
                        "source_url": "https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG?locations=KE",
                        "source": f"World Bank National Accounts – GDP growth ({year})",
                        "data_quality": "official",
                        "notes": f"Real GDP growth rate from World Bank API (NY.GDP.MKTP.KD.ZG), year {year}",
                    })
                    logger.info("World Bank GDP growth: %s = %s%%", year, growth)
                    break
    except Exception as exc:
        logger.warning("Failed to fetch World Bank GDP growth: %s", exc)

    return extra_indicators


def _merge_indicators(
    base: list[dict[str, Any]], extra: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge extra indicators into base, preferring more recent data.

    For each indicator_type, if the extra entry has a more recent date than
    the latest in base, the extra entry is appended.  Existing entries are
    never removed.
    """
    # Find latest date per indicator_type in base
    latest_dates: dict[str, str] = {}
    for item in base:
        itype = item.get("indicator_type", "")
        d = item.get("date", "")
        if itype not in latest_dates or d > latest_dates[itype]:
            latest_dates[itype] = d

    added = 0
    for item in extra:
        itype = item.get("indicator_type", "")
        d = item.get("date", "")
        if d > latest_dates.get(itype, ""):
            base.append(item)
            latest_dates[itype] = d
            added += 1

    if added:
        logger.info("Added %d newer indicator(s) from World Bank API", added)

    return base


def fetch_economic_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> list[dict[str, Any]]:
    """Fetch economic indicators from fixture, enriched with World Bank data.

    1. Loads base indicators from the configured
       ``economic_indicators_dataset_url``.
    2. Fetches latest GDP and GDP growth from World Bank API.
    3. Merges newer values into the payload (additive, no removals).
    4. Falls back gracefully to fixture-only data on API failure.
    """
    payload = load_json_resource(
        url=settings.economic_indicators_dataset_url,
        client=client,
        logger=logger,
        label="economic_indicators",
    )

    if not isinstance(payload, list):  # pragma: no cover - defensive check
        raise ValueError("economic indicators payload must be a list")

    # Enrich with World Bank GDP data (graceful fallback)
    if settings.enrich_with_worldbank:
        try:
            wb_indicators = _fetch_wb_gdp_indicators(client)
            if wb_indicators:
                payload = _merge_indicators(payload, wb_indicators)
        except Exception as exc:
            logger.warning("World Bank GDP enrichment failed: %s", exc)
    else:
        logger.debug("World Bank enrichment disabled via config")

    return payload

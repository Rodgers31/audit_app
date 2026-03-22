"""Fetcher for debt timeline data.

Loads base debt totals from the configured fixture/API, then enriches GDP
figures using the World Bank API for accurate debt-to-GDP ratios.
"""

from __future__ import annotations

import logging
from typing import Any

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource

logger = logging.getLogger("seeding.debt_timeline.fetcher")

# World Bank indicator: GDP in current LCU (KES for Kenya)
_WB_GDP_URL = (
    "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN"
    "?format=json&per_page=30"
)


def _fetch_wb_gdp(client: SeedingHttpClient) -> dict[int, int]:
    """Fetch Kenya GDP by year from World Bank API.

    Returns a mapping of ``{year: gdp_in_billions_kes}``.
    The World Bank value is in raw KES; we divide by 1e9 to match
    the fixture unit (billions KES).
    """
    resp = client.get(_WB_GDP_URL, raise_for_status=True)
    wb_data = resp.json()

    # World Bank JSON response: [metadata_dict, data_list]
    if not isinstance(wb_data, list) or len(wb_data) < 2:
        raise ValueError("Unexpected World Bank API response format")

    data_array = wb_data[1]
    if not isinstance(data_array, list):
        raise ValueError("World Bank data element is not a list")

    gdp_by_year: dict[int, int] = {}
    for item in data_array:
        if item.get("value") is not None:
            year = int(item["date"])
            gdp_by_year[year] = round(item["value"] / 1e9)  # → billions KES

    return gdp_by_year


def _enrich_with_wb_gdp(
    base: dict[str, Any], client: SeedingHttpClient
) -> dict[str, Any]:
    """Overlay World Bank GDP data onto the base debt timeline payload.

    Updates ``gdp`` and recalculates ``gdp_ratio`` for each year where
    World Bank data is available.  Falls back silently on any error.
    """
    try:
        gdp_by_year = _fetch_wb_gdp(client)
    except Exception as exc:
        logger.warning("World Bank GDP API unavailable, using fixture GDP: %s", exc)
        return base

    timeline = base.get("timeline", base) if isinstance(base, dict) else base
    if not isinstance(timeline, list):
        logger.warning("Cannot enrich non-list timeline structure")
        return base

    updated = 0
    for entry in timeline:
        year = entry.get("year")
        if year in gdp_by_year:
            entry["gdp"] = gdp_by_year[year]
            total = entry.get("total", 0)
            if gdp_by_year[year] > 0:
                entry["gdp_ratio"] = round(total / gdp_by_year[year] * 100, 1)
            updated += 1

    if updated:
        logger.info(
            "Enriched %d/%d timeline entries with World Bank GDP data",
            updated,
            len(timeline),
        )
    else:
        logger.info("World Bank GDP returned no overlapping years with timeline")

    return base


def fetch_debt_timeline_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> dict[str, Any]:
    """Fetch debt timeline data from CBK/Treasury fixture or API.

    1. Loads base debt totals from the configured ``debt_timeline_dataset_url``
       (file:// fixture or https:// endpoint).
    2. Enriches GDP values with World Bank API data for more accurate
       debt-to-GDP ratios.
    3. Falls back gracefully to fixture GDP if the World Bank API is
       unavailable.
    """
    base = load_json_resource(
        url=settings.debt_timeline_dataset_url,
        client=client,
        logger=logger,
        label="debt_timeline",
    )

    # Enrich with live World Bank GDP (graceful fallback on failure)
    if settings.enrich_with_worldbank:
        base = _enrich_with_wb_gdp(base, client)
    else:
        logger.debug("World Bank enrichment disabled via config")

    return base

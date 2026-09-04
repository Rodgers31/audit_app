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


def _overlay_cbk_public_debt(
    base: dict[str, Any], client: SeedingHttpClient, settings: SeedingSettings
) -> tuple[dict[str, Any], int]:
    """Overlay authoritative external/domestic/total from the CBK bulletin.

    Until now these three columns came from a git-tracked fixture: its 2025
    total said KES 12.50T where CBK's December 2025 Statistical Bulletin
    (Table 4.1.3) publishes 12.299T. The series was also the second, and
    disagreeing, source for a figure the loan register already carries
    (AUDIT_FINDINGS P3).

    Applied BEFORE the World Bank GDP pass so ``gdp_ratio`` is recomputed
    from the corrected totals rather than the fixture's.

    Payload values are BILLIONS (the fixture convention this pipeline reads
    and the writer converts from), while the parser returns raw KES — hence
    the /1e9. Getting that backwards would be a 10^9 error, so it is done in
    one place and asserted in tests.

    Returns ``(payload, years_overlaid)``; 0 means nothing live was applied.
    """
    try:
        from ..national_debt.cbk_bulletin import (
            fetch_public_debt_timeline_from_cbk_bulletin,
        )

        by_year = fetch_public_debt_timeline_from_cbk_bulletin(client, settings)
    except Exception as exc:
        logger.warning("CBK public-debt overlay unavailable: %s", exc)
        return base, 0
    if not by_year:
        return base, 0

    timeline = base.get("timeline", base) if isinstance(base, dict) else base
    if not isinstance(timeline, list):
        return base, 0

    applied = 0
    for entry in timeline:
        year = entry.get("year")
        live = by_year.get(year)
        if not live:
            continue
        before = entry.get("total")
        entry["external"] = float(live["external"]) / 1e9
        entry["domestic"] = float(live["domestic"]) / 1e9
        entry["total"] = float(live["total"]) / 1e9
        entry["source"] = "CBK Statistical Bulletin Table 4.1.3"
        applied += 1
        if before and abs(before - entry["total"]) > 1:
            logger.info(
                "CBK overlay corrected %d total: %.1fB -> %.1fB",
                year,
                before,
                entry["total"],
            )
    # INSERT years CBK publishes that the fixture does not carry.
    #
    # The loop above only ever mutates rows that already exist, so the series
    # could never move past the newest year someone had hand-added to the
    # fixture: when CBK publishes an annual figure for a new year, the overlay
    # would fetch it and silently drop it. That is exactly how the fiscal
    # summary froze at FY2025/26 until 6940446 taught it to insert.
    #
    # It has not bitten yet only because CBK's Table 4.1.3 currently ends at
    # 2025, the last completed calendar year, and so does the fixture.
    known = {e.get("year") for e in timeline}
    created = 0
    for year in sorted(y for y in by_year if y not in known):
        live = by_year[year]
        timeline.append(
            {
                "year": year,
                "external": float(live["external"]) / 1e9,
                "domestic": float(live["domestic"]) / 1e9,
                "total": float(live["total"]) / 1e9,
                # gdp/gdp_ratio are filled by the World Bank pass that runs
                # after this one; leaving them absent is correct until then.
                "gdp": None,
                "gdp_ratio": None,
                "source": "CBK Statistical Bulletin Table 4.1.3",
            }
        )
        created += 1
        logger.info(
            "CBK overlay ADDED %d: total %.1fB (not previously in the series)",
            year, float(live["total"]) / 1e9,
        )
    if created:
        timeline.sort(key=lambda e: e.get("year") or 0)

    logger.info(
        "CBK public-debt overlay: %d year(s) updated, %d added", applied, created
    )
    return base, applied + created


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

    # Authoritative debt stocks FIRST, so the GDP pass below recomputes
    # gdp_ratio from the corrected totals.
    base, overlaid = _overlay_cbk_public_debt(base, client, settings)

    # Enrich with live World Bank GDP (graceful fallback on failure)
    if settings.enrich_with_worldbank:
        base = _enrich_with_wb_gdp(base, client)
    else:
        logger.debug("World Bank enrichment disabled via config")

    # Record provenance: the series is only "live" when the debt figures
    # themselves came from the publisher. Live GDP over fixture debt is
    # still fixture debt, and saying otherwise is the false-green this
    # instrumentation exists to prevent.
    from ...freshness import mark_fixture, mark_live

    if overlaid:
        mark_live(
            "debt_timeline",
            detail=f"CBK Statistical Bulletin 4.1.3, {overlaid} year(s)",
        )
    else:
        mark_fixture(
            "debt_timeline",
            reason="cbk_bulletin_unavailable",
            detail="debt stocks remain fixture values; only GDP is live",
        )

    return base

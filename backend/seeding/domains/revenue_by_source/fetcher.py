"""Fetch revenue-by-source payload with live World Bank enrichment.

Strategy:
1. Try World Bank API for government revenue indicators (total revenue,
   tax revenue as % of GDP) to get authoritative headline figures.
2. Load fixture for the detailed tax-type breakdown (PAYE, VAT, Corp Tax,
   Excise Duty) which is only available from KRA annual reports.
3. Merge: live headline figures enrich the fixture breakdown.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource

logger = logging.getLogger("seeding.revenue_by_source.fetcher")

_WB_BASE = "https://api.worldbank.org/v2/country/KEN/indicator"

# World Bank revenue indicators
_WB_REVENUE_INDICATORS = {
    "GC.REV.TOTL.CN": {
        "revenue_type": "Total Government Revenue",
        "description": "Total revenue in current LCU (KES)",
    },
    "GC.TAX.TOTL.CN": {
        "revenue_type": "Total Tax Revenue",
        "description": "Total tax revenue in current LCU (KES)",
    },
    "GC.TAX.TOTL.GD.ZS": {
        "revenue_type": "Tax Revenue % of GDP",
        "description": "Tax revenue as share of GDP",
    },
}


def _fetch_wb_revenue(
    client: SeedingHttpClient, settings: SeedingSettings
) -> List[Dict[str, Any]]:
    """Fetch revenue data from World Bank API.

    Returns list of revenue records compatible with the fixture format.
    """
    records: List[Dict[str, Any]] = []

    for indicator_code, meta in _WB_REVENUE_INDICATORS.items():
        try:
            url = f"{_WB_BASE}/{indicator_code}"
            logger.info("Fetching World Bank %s ...", indicator_code)

            resp = client.get(
                url,
                params={"format": "json", "per_page": "20", "date": "2018:2026"},
                raise_for_status=True,
            )
            wb_data = resp.json()

            if not isinstance(wb_data, list) or len(wb_data) < 2 or not wb_data[1]:
                continue

            for item in wb_data[1]:
                if item.get("value") is None:
                    continue

                year = int(item["date"])
                value = item["value"]

                # Convert LCU to billions KES for monetary values
                if indicator_code.endswith(".CN"):
                    amount_billions = round(value / 1e9, 1)
                    records.append({
                        "fiscal_year": f"FY {year - 1}/{str(year)[-2:]}",
                        "revenue_type": meta["revenue_type"],
                        "amount_billion_kes": amount_billions,
                        "target_billion_kes": None,
                        "performance_pct": None,
                        "share_of_total_pct": None,
                        "yoy_growth_pct": None,
                        "source": f"World Bank ({indicator_code})",
                        "source_url": (
                            f"https://data.worldbank.org/indicator/"
                            f"{indicator_code}?locations=KE"
                        ),
                        "data_quality": "official",
                    })

        except Exception as exc:
            logger.warning(
                "Failed to fetch World Bank %s: %s", indicator_code, exc
            )

    return records


def fetch_revenue_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> list[dict[str, Any]]:
    """Fetch revenue data, trying live sources first.

    Strategy:
    1. Fetch headline revenue from World Bank API.
    2. Load fixture for detailed tax-type breakdown.
    3. Merge: live headline data supplements fixture detail.
    """
    live_records: List[Dict[str, Any]] = []

    # Step 1: Try World Bank API
    if settings.enrich_with_worldbank:
        try:
            live_records = _fetch_wb_revenue(client, settings)
            if live_records:
                logger.info(
                    "Fetched %d revenue records from World Bank", len(live_records)
                )
        except Exception as exc:
            logger.warning("World Bank revenue fetch failed: %s", exc)

    # Step 2: Load fixture
    try:
        fixture_payload = load_json_resource(
            url=settings.revenue_by_source_dataset_url,
            client=client,
            logger=logger,
            label="revenue_by_source",
        )
        if not isinstance(fixture_payload, list):
            fixture_payload = []
    except Exception as exc:
        logger.warning("Failed to load revenue fixture: %s", exc)
        fixture_payload = []

    # Step 3: Merge — fixture provides detail, live provides headline totals
    if live_records:
        # Index fixture by (fiscal_year, revenue_type)
        fixture_keys = {
            (r.get("fiscal_year", ""), r.get("revenue_type", ""))
            for r in fixture_payload
        }

        # Add live records that don't overlap with fixture detail
        merged = list(fixture_payload)
        for record in live_records:
            key = (record.get("fiscal_year", ""), record.get("revenue_type", ""))
            if key not in fixture_keys:
                merged.append(record)

        logger.info(
            "Merged revenue: %d fixture + %d new live = %d total",
            len(fixture_payload),
            len(merged) - len(fixture_payload),
            len(merged),
        )
        return merged

    if fixture_payload:
        logger.warning(
            "No live revenue data — using fixture as fallback (data may be stale)"
        )
        return fixture_payload

    raise ValueError(
        "No revenue data available from either live API or fixture"
    )

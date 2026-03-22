"""Fetcher for fiscal summary data.

Strategy (in order):
1. Try World Bank Indicators API for government expenditure, external debt,
   and debt service data — merge into the existing fixture payload.
2. Fall back to the static fixture / configured URL.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource

logger = logging.getLogger("seeding.fiscal_summary.fetcher")

# World Bank indicator codes for Kenya
_WB_INDICATORS: Dict[str, str] = {
    "GC.XPN.TOTL.CN": "government_expenditure_lcu",
    "DT.DOD.DECT.CD": "external_debt_stocks_usd",
    "DT.TDS.DECT.CD": "total_debt_service_usd",
    "GC.REV.TOTL.CN": "government_revenue_lcu",
}


def fetch_fiscal_summary_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> dict[str, Any]:
    """Fetch fiscal summary data, enriching fixture with World Bank API data."""
    # Always load the fixture as baseline
    payload = load_json_resource(
        url=settings.fiscal_summary_dataset_url,
        client=client,
        logger=logger,
        label="fiscal_summary",
    )

    # Try World Bank enrichment
    if settings.enrich_with_worldbank and settings.live_pdf_fetch_enabled:
        try:
            wb_data = _fetch_worldbank_fiscal_data(client, settings)
            if wb_data:
                payload = _merge_worldbank_data(payload, wb_data)
                logger.info(
                    "Enriched fiscal summary with World Bank data",
                    extra={"wb_years": list(wb_data.keys())},
                )
        except Exception as exc:
            logger.warning(
                "World Bank enrichment failed, using fixture only: %s", exc
            )

    return payload


def _fetch_worldbank_fiscal_data(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Dict[str, Dict[str, float]]:
    """Fetch Kenya fiscal indicators from World Bank API.

    Returns:
        Dict keyed by calendar year (str), each containing indicator values.
        E.g. {"2023": {"government_expenditure_lcu": 3200000000000, ...}}
    """
    base_url = settings.worldbank_api_base_url
    result: Dict[str, Dict[str, float]] = {}

    for indicator_code, field_name in _WB_INDICATORS.items():
        try:
            url = f"{base_url}/country/KEN/indicator/{indicator_code}"
            logger.info("Fetching World Bank indicator %s ...", indicator_code)

            response = client.get(
                url,
                params={
                    "format": "json",
                    "per_page": "20",
                    "date": "2018:2025",
                },
                raise_for_status=False,
            )

            if response.status_code != 200:
                logger.warning(
                    "World Bank API returned %d for %s",
                    response.status_code,
                    indicator_code,
                )
                continue

            data = response.json()
            # World Bank API returns [metadata, records]
            if not isinstance(data, list) or len(data) < 2:
                continue

            records = data[1]
            if not records:
                continue

            for record in records:
                year = record.get("date")
                value = record.get("value")
                if year and value is not None:
                    result.setdefault(str(year), {})[field_name] = float(value)

        except Exception as exc:
            logger.warning(
                "Failed to fetch World Bank indicator %s: %s",
                indicator_code,
                exc,
            )
            continue

    return result


def _calendar_year_to_fy(year: int) -> str:
    """Convert a calendar year to Kenya fiscal year label.

    Kenya FY runs July-June, so calendar year 2023 maps to FY 2022/23
    (the FY that *ends* in June 2023). World Bank annual data for 2023
    best maps to FY 2022/23.
    """
    return f"FY {year - 1}/{str(year)[-2:]}"


def _merge_worldbank_data(
    payload: Dict[str, Any],
    wb_data: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    """Merge World Bank data into the fixture payload.

    Only fills in None/missing fields — never overwrites existing fixture data
    which is more granular (from Treasury BPS).
    """
    fiscal_years: List[Dict[str, Any]] = payload.get("fiscal_years", [])
    fy_lookup = {fy["fiscal_year"]: fy for fy in fiscal_years}

    for cal_year_str, indicators in wb_data.items():
        try:
            cal_year = int(cal_year_str)
        except ValueError:
            continue

        fy_label = _calendar_year_to_fy(cal_year)
        fy_entry = fy_lookup.get(fy_label)

        if fy_entry is None:
            # Create a new fiscal year entry from WB data
            new_entry: Dict[str, Any] = {"fiscal_year": fy_label}

            # Map WB fields to our schema
            exp_lcu = indicators.get("government_expenditure_lcu")
            if exp_lcu:
                # WB data is in LCU (KES), our fixture is in billions
                new_entry["appropriated_budget"] = round(exp_lcu / 1e9, 1)

            rev_lcu = indicators.get("government_revenue_lcu")
            if rev_lcu:
                new_entry["total_revenue"] = round(rev_lcu / 1e9, 1)

            # Debt service in USD — convert at approximate rate
            ds_usd = indicators.get("total_debt_service_usd")
            if ds_usd:
                # Approximate KES/USD (use rough average)
                kes_rate = 130.0  # conservative average for 2018-2025
                new_entry["debt_service_cost"] = round(
                    ds_usd * kes_rate / 1e9, 1
                )

            ext_debt_usd = indicators.get("external_debt_stocks_usd")
            if ext_debt_usd:
                kes_rate = 130.0
                new_entry["actual_debt"] = round(
                    ext_debt_usd * kes_rate / 1e9, 1
                )

            if len(new_entry) > 1:  # has at least one data field
                new_entry["_source"] = "world_bank_api"
                fiscal_years.append(new_entry)
                fy_lookup[fy_label] = new_entry
        else:
            # Only fill gaps in existing entries
            if fy_entry.get("appropriated_budget") is None:
                exp_lcu = indicators.get("government_expenditure_lcu")
                if exp_lcu:
                    fy_entry["appropriated_budget"] = round(exp_lcu / 1e9, 1)

            if fy_entry.get("total_revenue") is None:
                rev_lcu = indicators.get("government_revenue_lcu")
                if rev_lcu:
                    fy_entry["total_revenue"] = round(rev_lcu / 1e9, 1)

    # Sort fiscal years chronologically
    fiscal_years.sort(key=lambda x: x.get("fiscal_year", ""))
    payload["fiscal_years"] = fiscal_years

    return payload

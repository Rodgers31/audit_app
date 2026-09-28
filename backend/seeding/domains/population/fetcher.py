"""Population domain fetcher with live World Bank API integration.

County observations are owned by the separate census table loader.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from .parser import _coerce_int

logger = logging.getLogger("seeding.population.fetcher")

# World Bank indicators for Kenya population data
_WB_BASE = "https://api.worldbank.org/v2/country/KEN/indicator"

_WB_POPULATION_INDICATORS = {
    "SP.POP.TOTL": "total_population",
    "SP.POP.TOTL.MA.IN": "male_population",
    "SP.POP.TOTL.FE.IN": "female_population",
}

# Additional useful indicators
_WB_SUPPLEMENTARY = {
    "SP.POP.GROW": "population_growth_rate",
    "SP.URB.TOTL.IN.ZS": "urban_population_pct",
    "SP.DYN.LE00.IN": "life_expectancy",
    "SP.DYN.TFRT.IN": "fertility_rate",
}


def _fetch_wb_national_population(
    client: SeedingHttpClient,
) -> List[Dict[str, Any]]:
    """Fetch national population from World Bank API.

    Returns list of population records in the same format as the fixture,
    one per year.
    """
    # Fetch all three core indicators and merge by year
    data_by_year: Dict[int, Dict[str, Any]] = {}

    for indicator_code, field_name in _WB_POPULATION_INDICATORS.items():
        try:
            url = f"{_WB_BASE}/{indicator_code}"
            logger.info("Fetching World Bank %s ...", indicator_code)

            resp = client.get(
                url,
                params={"format": "json", "per_page": "30", "date": "2010:2026"},
                raise_for_status=True,
            )
            wb_data = resp.json()

            if not isinstance(wb_data, list) or len(wb_data) < 2 or not wb_data[1]:
                logger.warning("No data returned for %s", indicator_code)
                continue

            for item in wb_data[1]:
                if item.get("value") is None:
                    continue

                year = _coerce_int(item.get("date"))
                value = _coerce_int(item["value"])
                if (
                    year is None
                    or not 1900 <= year <= 2100
                    or value is None
                    or value < 0
                ):
                    logger.warning(
                        "Invalid population observation for %s", indicator_code
                    )
                    continue

                if year not in data_by_year:
                    data_by_year[year] = {
                        "level": "national",
                        "entity": "Kenya",
                        "year": year,
                        "source": f"World Bank Development Indicators ({year})",
                        "source_url": (
                            "https://data.worldbank.org/indicator/"
                            "SP.POP.TOTL?locations=KE"
                        ),
                        "dataset_id": "SP.POP.TOTL",
                        "data_quality": "official",
                    }

                data_by_year[year][field_name] = value

        except Exception as exc:
            logger.warning("Failed to fetch World Bank %s: %s", indicator_code, exc)

    # Also fetch supplementary indicators (growth rate, urban %, etc.)
    for indicator_code, field_name in _WB_SUPPLEMENTARY.items():
        try:
            url = f"{_WB_BASE}/{indicator_code}"
            resp = client.get(
                url,
                params={"format": "json", "per_page": "30", "date": "2010:2026"},
                raise_for_status=True,
            )
            wb_data = resp.json()
            if isinstance(wb_data, list) and len(wb_data) >= 2 and wb_data[1]:
                for item in wb_data[1]:
                    if item.get("value") is not None:
                        year = int(item["date"])
                        if year in data_by_year:
                            data_by_year[year][field_name] = round(item["value"], 2)
        except Exception:
            pass  # supplementary data is best-effort

    # Convert to sorted list
    records = sorted(
        (r for r in data_by_year.values() if "total_population" in r),
        key=lambda r: r["year"],
    )
    logger.info(
        "World Bank: fetched national population for %d years (%s–%s)",
        len(records),
        records[0]["year"] if records else "?",
        records[-1]["year"] if records else "?",
    )
    return records


def fetch_population_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Any:
    """Fetch only World Bank national observations; counties use the census loader.

    No fixture is read on failure. The existing stored observations remain
    untouched until their owning source supplies a replacement.
    """
    from ...freshness import mark_partial, mark_refused

    if not settings.enrich_with_worldbank:
        mark_refused("population", reason="worldbank_disabled")
        return []
    records = _fetch_wb_national_population(client)
    if not records:
        mark_refused("population", reason="worldbank_returned_nothing")
        return []
    mark_partial(
        "population",
        reason="census_not_yet_loaded",
        detail=f"World Bank SP.POP.* national series for {len(records)} year(s)",
    )
    return records


__all__ = ["fetch_population_payload"]

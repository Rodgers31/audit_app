"""Population domain fetcher with live World Bank API integration.

Fetches population data from the World Bank API first, then supplements
with fixture data for county-level breakdowns not available via the API.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource

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

                year = int(item["date"])
                value = int(round(item["value"]))

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
    records = sorted(data_by_year.values(), key=lambda r: r["year"])
    logger.info(
        "World Bank: fetched national population for %d years (%s–%s)",
        len(records),
        records[0]["year"] if records else "?",
        records[-1]["year"] if records else "?",
    )
    return records


def _merge_population(
    fixture: Any, live_national: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Merge live national data with fixture county data.

    Live national data takes precedence over fixture national data.
    County-level data from fixture is preserved (World Bank doesn't
    provide sub-national breakdowns for Kenya).
    """
    # Normalize fixture format
    if isinstance(fixture, dict):
        fixture_records = fixture.get("records", fixture.get("data", []))
    elif isinstance(fixture, list):
        fixture_records = fixture
    else:
        fixture_records = []

    # Separate fixture into county vs national records
    county_records = []
    fixture_national_keys: set[int] = set()

    for record in fixture_records:
        level = record.get("level", "")
        entity = record.get("entity", "").lower()

        is_national = (
            level == "national"
            or entity in ("kenya", "national", "republic of kenya")
            or record.get("county", "").lower() in ("", "national", "kenya")
        )

        if is_national:
            fixture_national_keys.add(record.get("year", 0))
        else:
            county_records.append(record)

    # Live national data indexed by year
    live_years = {r["year"] for r in live_national}

    # Keep fixture national entries for years without live data
    for record in fixture_records:
        year = record.get("year", 0)
        level = record.get("level", "")
        entity = record.get("entity", "").lower()
        is_national = (
            level == "national"
            or entity in ("kenya", "national", "republic of kenya")
        )
        if is_national and year not in live_years:
            live_national.append(record)

    merged = live_national + county_records

    logger.info(
        "Merged population: %d live national + %d county fixture = %d total",
        len(live_national),
        len(county_records),
        len(merged),
    )

    return merged


def fetch_population_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Any:
    """Fetch population data, prioritizing live World Bank API.

    Strategy:
    1. Fetch national population time series from World Bank API.
    2. Load fixture for county-level data (47 counties from KNBS Census).
    3. Merge: live national data takes precedence; county data preserved.
    4. If World Bank fails entirely, fall back to fixture only.
    """
    live_national: List[Dict[str, Any]] = []

    # Step 1: Try live World Bank API
    if settings.enrich_with_worldbank:
        try:
            live_national = _fetch_wb_national_population(client)
        except Exception as exc:
            logger.warning("World Bank population fetch failed: %s", exc)

    # Step 2: Load fixture (always — we need county data from it)
    try:
        fixture = load_json_resource(
            url=settings.population_dataset_url,
            client=client,
            logger=logger,
            label="population",
        )
    except Exception as exc:
        logger.warning("Failed to load population fixture: %s", exc)
        fixture = []

    # Step 3: Merge
    if live_national:
        merged = _merge_population(fixture, live_national)
        # Wrap in the expected format for the parser
        return {"records": merged} if isinstance(fixture, dict) else merged
    else:
        if fixture:
            logger.warning(
                "No live population data — using fixture as fallback "
                "(data may be stale)"
            )
        return fixture


__all__ = ["fetch_population_payload"]

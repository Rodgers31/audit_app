"""Fetch Kenya nominal GDP (current KES) — the single source of truth for
the nominal-GDP denominator.

Primary: World Bank API indicator ``NY.GDP.MKTP.CN`` (GDP, current LCU,
which is Kenyan shillings for Kenya). Fallback: the in-repo
``national_gdp.json`` fixture, which is *also* World Bank-sourced — so a
failed live fetch degrades to the last-known-good World Bank actuals,
never a hardcoded estimate.

Returns raw KES (e.g. 16_224_478_000_000), matching ``GDPData.gdp_value``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource

logger = logging.getLogger("seeding.national_gdp.fetcher")

# World Bank indicator: GDP in current LCU (KES for Kenya). per_page large
# enough to cover the full available history in one page.
_WB_GDP_URL = (
    "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN"
    "?format=json&per_page=80"
)

# In-repo fallback (World Bank-sourced actuals). file:// resolves relative
# to backend/ via load_json_resource's path resolution.
_FIXTURE_URL = "file://seeding/real_data/national_gdp.json"


def _parse_wb_gdp(payload: Any) -> Dict[int, int]:
    """Parse a World Bank API response into ``{year: gdp_in_raw_kes}``.

    World Bank JSON shape: ``[metadata_dict, [ {date, value}, ... ]]``.
    Values are already in raw KES (current LCU); we keep them as-is.
    """
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError("Unexpected World Bank API response format")
    data_array = payload[1]
    if not isinstance(data_array, list):
        raise ValueError("World Bank data element is not a list")

    gdp_by_year: Dict[int, int] = {}
    for item in data_array:
        if item.get("value") is not None:
            gdp_by_year[int(item["date"])] = int(round(item["value"]))  # raw KES
    return gdp_by_year


def fetch_national_gdp_kes(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Dict[int, int]:
    """Return ``{year: nominal_gdp_kes}`` for Kenya.

    Tries the live World Bank API first (when enabled), then falls back to
    the World Bank-sourced fixture. Raises only if BOTH the live API and
    the fixture are unavailable — callers treat that as "keep the existing
    DB rows" (last-known-good), never substituting a hardcoded value.
    """
    from ...freshness import mark_fixture, mark_live

    fallback_reason = "worldbank_disabled"
    if settings.enrich_with_worldbank:
        try:
            resp = client.get(_WB_GDP_URL, raise_for_status=True)
            gdp = _parse_wb_gdp(resp.json())
            if gdp:
                logger.info(
                    "Fetched %d GDP year(s) from World Bank API (latest=%d)",
                    len(gdp),
                    max(gdp),
                )
                mark_live(
                    "national_gdp",
                    detail=(
                        f"World Bank NY.GDP.MKTP.CN: {len(gdp)} year(s), "
                        f"latest {max(gdp)}"
                    ),
                )
                return gdp
            logger.warning("World Bank GDP API returned no values; using fixture")
            fallback_reason = "worldbank_returned_nothing"
        except Exception as exc:  # network / shape / parse — degrade gracefully
            logger.warning("World Bank GDP API unavailable, using fixture: %s", exc)
            fallback_reason = f"worldbank_unreachable({type(exc).__name__})"

    fixture = load_json_resource(
        url=_FIXTURE_URL, client=client, logger=logger, label="national_gdp"
    )
    rows = fixture.get("gdp", []) if isinstance(fixture, dict) else []
    gdp_by_year = {
        int(r["year"]): int(r["gdp_kes"])
        for r in rows
        if r.get("gdp_kes") is not None
    }
    if not gdp_by_year:
        mark_fixture(
            "national_gdp",
            reason="no_source_available",
            detail=f"live path failed ({fallback_reason}) and the fixture is empty",
        )
        raise ValueError("No GDP data available from World Bank API or fixture")
    logger.info("Loaded %d GDP year(s) from fixture fallback", len(gdp_by_year))
    mark_fixture(
        "national_gdp",
        reason=fallback_reason,
        detail=(
            f"serving {len(gdp_by_year)} year(s) from the in-repo World "
            f"Bank-sourced fixture; the denominator every debt-to-GDP ratio "
            f"uses is NOT live this run"
        ),
    )
    return gdp_by_year

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
from decimal import Decimal
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

# ── Poverty indicators ──────────────────────────────────────────────
# Issue #137 P7. These replace POVERTY_SERIES, a Python constant of nine
# figures inserted at confidence 0.85. It was the surviving sibling of
# NATIONAL_GDP_SERIES — the hardcoded constant that published GDP 15.4T and an
# 82% debt-to-GDP ratio until it was pruned (tests/test_national_gdp_reconcile.py).
#
# What the constant published, against the World Bank's actual Kenya series:
#
#   row 2019  headcount 36.1, gini 0.408  = the World Bank's 2015 observation,
#                                           exactly, relabelled 2019
#   row 2021  headcount 36.1              = the 2015 value again, on a row
#                                           labelled "KNBS KIHBS 2021"; the
#                                           2021 observation is 38.6
#   row 2024  gini 0.408                  = the 2015 value again
#
# The World Bank reports no observation at all for 2019 or 2024.
#
# INDICATOR CHOICE, and one deliberate omission:
#
#   headcount -> SI.POV.NAHC   poverty headcount at NATIONAL poverty lines.
#                              Same definition the old constant claimed
#                              ("KNBS KIHBS"), so the years are comparable.
#   gini      -> SI.POV.GINI   reported 0-100; the column stores 0-1, so it
#                              is divided by 100 here, once, explicitly.
#   extreme   -> NOT FETCHED.  The World Bank's international extreme line is
#                              SI.POV.DDAY ($2.15/day 2017 PPP), which reads
#                              ~45% for Kenya. The constant's 8.5-10.2 is the
#                              national FOOD-poverty rate. Substituting one for
#                              the other would move a published figure fivefold
#                              while calling it a correction, so the column is
#                              left NULL with a reason until a KNBS food-poverty
#                              source is wired up. A null that says why beats a
#                              number that means something else.
_WB_POVERTY_URL = (
    "https://api.worldbank.org/v2/country/KEN/indicator/{indicator}"
    "?format=json&per_page=100"
)
_POVERTY_INDICATORS = {"headcount": "SI.POV.NAHC", "gini": "SI.POV.GINI"}

# Recorded on every row this path writes, so the absence is machine-readable
# rather than looking like "not measured".
EXTREME_POVERTY_OMITTED_REASON = (
    "no_source_for_national_food_poverty_line: the World Bank's SI.POV.DDAY is "
    "the $2.15/day international line, a different measure from the national "
    "food-poverty rate this column previously held"
)


def _parse_wb_series(payload: Any) -> Dict[int, float]:
    """``{year: value}`` for the observed years of one World Bank indicator."""
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError("Unexpected World Bank API response format")
    rows = payload[1]
    if not isinstance(rows, list):
        raise ValueError("World Bank data element is not a list")
    return {
        int(item["date"]): float(item["value"])
        for item in rows
        if item.get("value") is not None
    }


def fetch_kenya_poverty(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Dict[int, Dict[str, Decimal]]:
    """``{year: {"headcount": Decimal, "gini": Decimal}}``, observed years only.

    A year appears only if the World Bank actually reports it. There is no
    fixture fallback and no interpolation: the failure this replaces was a
    2015 observation republished under the labels 2019, 2021 and 2024, so
    inventing a year here would recreate it.

    Raises on a failed fetch. The caller keeps existing rows rather than
    pruning against an empty result.
    """
    series: Dict[str, Dict[int, float]] = {}
    for field, indicator in _POVERTY_INDICATORS.items():
        url = _WB_POVERTY_URL.format(indicator=indicator)
        series[field] = _parse_wb_series(client.get(url, raise_for_status=True).json())
        logger.info(
            "national_gdp: World Bank %s -> %d observed year(s)",
            indicator,
            len(series[field]),
        )

    out: Dict[int, Dict[str, Decimal]] = {}
    for year in sorted(set(series["headcount"]) | set(series["gini"]), reverse=True):
        row: Dict[str, Decimal] = {}
        if year in series["headcount"]:
            row["headcount"] = Decimal(str(round(series["headcount"][year], 2)))
        if year in series["gini"]:
            # 0-100 at the source, 0-1 in the column.
            row["gini"] = Decimal(str(round(series["gini"][year] / 100.0, 4)))
        if row:
            out[year] = row
    return out

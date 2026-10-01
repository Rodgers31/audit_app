"""Fetch economic indicator payload.

Loads indicators from live sources first — the World Bank API (annual GDP,
growth, annual-average inflation, unemployment, CPI) and the CBK
inflation-rates table (monthly 12-month CPI inflation, see
``cbk_inflation.py``) — then falls back to the configured fixture if live
APIs are unavailable.  Fixture data is used ONLY as a fallback, never as the
primary source.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource
from . import cbk_inflation

logger = logging.getLogger("seeding.economic_indicators.fetcher")

# ── World Bank Indicator URLs (free, no auth required) ──────────────

_WB_BASE = "https://api.worldbank.org/v2/country/KEN/indicator"
_WB_PUBLISHER = "World Bank"
_WB_SOURCE_LABEL = "World Bank, World Development Indicators"

# GDP & growth
_WB_INDICATORS = {
    "NY.GDP.MKTP.CN": {
        "indicator_type": "total_national_gdp",
        "unit": "KES_millions",
        "divisor": 1e6,
        "round_digits": 0,
        "description": "GDP current LCU",
        "measure": "GDP, current KES",
    },
    "NY.GDP.MKTP.KD.ZG": {
        "indicator_type": "gdp_growth_rate",
        "unit": "percent",
        "divisor": 1,
        "round_digits": 1,
        "description": "GDP growth annual %",
        "measure": "real GDP growth, annual",
    },
    # CPI / inflation
    "FP.CPI.TOTL.ZG": {
        "indicator_type": "inflation_rate",
        "unit": "percent",
        "divisor": 1,
        "round_digits": 1,
        "description": "Consumer price inflation annual %",
        "measure": "CPI inflation, annual average",
    },
    # Unemployment
    "SL.UEM.TOTL.ZS": {
        "indicator_type": "unemployment_rate",
        "unit": "percent",
        "divisor": 1,
        "round_digits": 1,
        "description": "Unemployment % of total labor force (ILO)",
        "measure": "unemployment, ILO modelled estimate",
    },
    # CPI index (2010 = 100)
    "FP.CPI.TOTL": {
        "indicator_type": "cpi_index",
        "unit": "index_2010_100",
        "divisor": 1,
        "round_digits": 1,
        "description": "Consumer price index (2010 = 100)",
        "measure": "consumer price index, 2010 = 100",
    },
    # Government revenue as % of GDP. The older code was
    # "GC.REV.TOTL.GD.ZS" ("Revenue and grants %"), which the World
    # Bank deprecated and now returns HTTP 200 with
    # ``"Invalid value: The provided parameter value is not valid"``
    # for any country query — that's what produced the
    # "World Bank API returned no data for GC.REV.TOTL.GD.ZS"
    # warning on every nightly run. The replacement
    # ``GC.REV.XGRT.GD.ZS`` ("Revenue, excluding grants, % of GDP")
    # is what fiscal analysts now use as the canonical
    # revenue-to-GDP ratio. Returns valid Kenya data through 2023:
    # 17.35%, 17.88%, 18.64% for 2021/2022/2023.
    "GC.REV.XGRT.GD.ZS": {
        "indicator_type": "govt_revenue_pct_gdp",
        "unit": "percent",
        "divisor": 1,
        "round_digits": 1,
        "description": "Government revenue (excl. grants) % of GDP",
        "measure": "government revenue excl. grants, % of GDP",
    },
    # Government expenditure as % of GDP
    "GC.XPN.TOTL.GD.ZS": {
        "indicator_type": "govt_expenditure_pct_gdp",
        "unit": "percent",
        "divisor": 1,
        "round_digits": 1,
        "description": "Government expenditure % of GDP",
        "measure": "government expenditure, % of GDP",
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
                    # Declared provenance, read verbatim by the API. The
                    # page's caption comes from here and nowhere else, so a
                    # World Bank figure can no longer be labelled KNBS.
                    "source_label": _WB_SOURCE_LABEL,
                    "publisher": _WB_PUBLISHER,
                    "measure": meta["measure"],
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


@dataclass
class EconomicPayload:
    """What one fetch produced, and what the live sources now OWN.

    ``coverage`` maps each indicator type a live source delivered this run to
    the exact ``YYYY-MM-DD`` dates it delivered. It is the supersession proof:
    within a year a live source covered, a row of that type at a date the
    source did NOT deliver was written by something else (a bootstrap
    literal, a fixture of a different measure) and cannot be right. See
    :func:`superseded_by_live`.
    """

    records: list[dict[str, Any]]
    coverage: dict[str, set[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _coverage(live: list[dict[str, Any]]) -> dict[str, set[str]]:
    cov: dict[str, set[str]] = {}
    for item in live:
        cov.setdefault(item["indicator_type"], set()).add(str(item["date"])[:10])
    return cov


def superseded_by_live(
    indicator_type: str, day: str, coverage: dict[str, set[str]]
) -> bool:
    """True when a live source owns this type across this date but skipped it.

    ``inflation_rate`` is the World Bank's annual-average series, one row per
    year at ``YYYY-12-31``. The fixture's ``inflation_rate`` 2025-01-31 = 3.3
    is a 12-month figure; bootstrap's 2024-06-30 = 4.6 is a literal. Both
    fall inside the span the owner delivered (2015-12-31 … 2025-12-31) at a
    date it does not deliver, so neither can be an observation of its measure.

    Only the delivered SPAN counts, never merely the year: a truncated CBK
    page serving just August 2026 would otherwise condemn January-July 2026.
    Outside the span, absence of coverage is not evidence against a row.
    """
    dates = coverage.get(indicator_type)
    if not dates:
        return False
    day = str(day)[:10]
    return day not in dates and min(dates) <= day <= max(dates)


def _merge_indicators(
    base: list[dict[str, Any]], live: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge live indicators into base, preferring live data over fixture.

    For each (indicator_type, date) pair, live data takes precedence. A
    fixture row is also dropped when a live source owns its type for that
    year (:func:`superseded_by_live`) — otherwise it would be written here
    and deleted again by the writer's supersession sweep on every run.
    """
    live_keys: set[tuple[str, str]] = set()
    for item in live:
        key = (item.get("indicator_type", ""), item.get("date", ""))
        live_keys.add(key)
    coverage = _coverage(live)

    merged = list(live)  # start with all live data
    kept_from_fixture = 0
    for item in base:
        key = (item.get("indicator_type", ""), item.get("date", ""))
        if key in live_keys:
            continue
        if superseded_by_live(key[0], key[1], coverage):
            continue
        merged.append(item)
        kept_from_fixture += 1

    logger.info(
        "Merged indicators: %d live + %d fixture-only = %d total",
        len(live),
        kept_from_fixture,
        len(merged),
    )

    return merged


def _fetch_cbk(client: SeedingHttpClient) -> tuple[list[dict[str, Any]], str, list[str]]:
    """CBK monthly inflation: ``(records, status for the detail, errors)``.

    A failure here is recorded as a run ERROR, not swallowed: the World Bank
    pull still succeeds, so without it the domain would report LIVE while the
    headline inflation figure silently stopped moving. The previous months'
    rows stay in the table and keep their own dates, so the page shows an
    older month, captioned as such — and the series gate in
    ``seeding/staleness.py`` fires once the newest month is over 60 days old.
    """
    try:
        result = cbk_inflation.fetch_cbk_inflation(client)
    except Exception as exc:
        msg = f"CBK inflation-rates fetch failed: {exc}"
        logger.error(msg)
        return [], f"cbk_inflation=failed({type(exc).__name__})", [msg]
    if not result.records:
        msg = "CBK inflation-rates page parsed but yielded no checked months"
        logger.error(msg)
        return [], "cbk_inflation=empty", [msg]
    for ref, why in result.rejected:
        if "fewer than 11" not in why:
            logger.warning("CBK inflation %s withheld: %s", ref, why)
    status = (
        f"CBK inflation: {len(result.records)} month(s), newest "
        f"{result.newest_month}, {len(result.rejected)} withheld"
    )
    return result.records, status, []


def fetch_economic_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> EconomicPayload:
    """Fetch economic indicators, prioritizing live sources.

    Strategy:
    1. World Bank API (GDP, growth, annual-average inflation, unemployment,
       CPI index, govt revenue/expenditure) — annual, about a year behind.
    2. CBK inflation-rates table — monthly 12-month CPI inflation (KNBS).
    3. Fixture as a supplement for anything neither source delivered.
    4. Merge: live takes precedence; fixture fills gaps it does not
       contradict.
    """
    wb_indicators: list[dict[str, Any]] = []

    if settings.enrich_with_worldbank:
        try:
            wb_indicators = _fetch_wb_indicators(client)
            if wb_indicators:
                logger.info(
                    "Fetched %d live indicators from World Bank API",
                    len(wb_indicators),
                )
        except Exception as exc:
            logger.warning("World Bank API fetch failed entirely: %s", exc)

    cbk_records, cbk_status, errors = _fetch_cbk(client)
    live_indicators = wb_indicators + cbk_records

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

    # CPI/cpi is an independently based monthly index, not WB cpi_index.
    # Retire the unsupported supplement even when a remote fixture is used.
    legacy_cpi = [r for r in fixture_data if isinstance(r, dict)
                  and str(r.get("indicator_type", r.get("type", ""))).lower() == "cpi"]
    if legacy_cpi:
        errors.append("Withheld legacy CPI supplement; source-bound review required")
        logger.error(errors[-1])
        fixture_data = [r for r in fixture_data if r not in legacy_cpi]

    # Provenance is recorded at EVERY branch. Until 2026-08-29 this domain
    # recorded none, so the nightly reported "provenance unknown" — which the
    # staleness gate correctly refuses to read as healthy, but which also
    # cannot distinguish a working World Bank pull from a year-old fixture.
    from ...freshness import mark_fixture, mark_live, mark_partial

    wb_status = (
        f"World Bank Indicators API: {len(wb_indicators)} live observation(s) "
        f"across {len(_WB_INDICATORS)} indicator(s)"
        if wb_indicators
        else "World Bank: nothing"
    )
    detail = f"{wb_status}; {cbk_status}"

    if wb_indicators:
        mark_live("economic_indicators", detail=detail)
    elif cbk_records:
        # GDP, growth and unemployment — most of what this domain publishes —
        # came from nowhere live this run; only monthly inflation did.
        mark_partial(
            "economic_indicators",
            reason=(
                "worldbank_disabled"
                if not settings.enrich_with_worldbank
                else "worldbank_returned_nothing"
            ),
            detail=detail,
        )
    elif fixture_data:
        logger.warning(
            "No live data available — using fixture as fallback "
            "(data may be stale)"
        )
        mark_fixture(
            "economic_indicators",
            reason=(
                "worldbank_disabled"
                if not settings.enrich_with_worldbank
                else "worldbank_returned_nothing"
            ),
            detail=f"serving {len(fixture_data)} fixture indicator(s); {cbk_status}",
        )
        return EconomicPayload(records=fixture_data, errors=errors)
    else:
        mark_fixture(
            "economic_indicators",
            reason="no_source_available",
            detail="neither the World Bank API, CBK nor the fixture yielded data",
        )
        raise ValueError(
            "No economic indicators available from either live API or fixture"
        )

    return EconomicPayload(
        records=_merge_indicators(fixture_data, live_indicators),
        coverage=_coverage(live_indicators),
        errors=errors,
    )

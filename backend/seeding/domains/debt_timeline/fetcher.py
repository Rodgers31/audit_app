"""Fetcher for debt timeline data.

Loads base debt totals from the configured fixture/API, then enriches GDP
figures using the World Bank API for accurate debt-to-GDP ratios.
"""

from __future__ import annotations

import logging
from typing import Any
from decimal import Decimal

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource

logger = logging.getLogger("seeding.debt_timeline.fetcher")


def _timeline(base):
    rows = base.get("timeline") if type(base) is dict else None
    if (type(rows) is not list or not 1 <= len(rows) <= 1000
            or any(type(row) is not dict or type(row.get("year")) is not int
                   or not 1900 <= row["year"] <= 9999 for row in rows)
            or len({row["year"] for row in rows}) != len(rows)):
        raise ValueError("Bounded distinct calendar years required for debt timeline")
    return rows

# World Bank indicator: GDP in current LCU (KES for Kenya)
_WB_GDP_URL = (
    "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN"
    "?format=json&per_page=100"
)


def _fetch_wb_gdp(client: SeedingHttpClient) -> dict[int, int]:
    """Fetch Kenya GDP by year from World Bank API.

    Returns raw KES with byte-bound evidence; the overlay converts to
    the payload billions convention without whole-billion rounding.
    """
    resp = client.get(_WB_GDP_URL, raise_for_status=True)
    from ...observations import worldbank_observations
    return worldbank_observations(resp, client, indicator="NY.GDP.MKTP.CN",
        measure="gdp", unit="KES", quantum="1", basis="current_prices")


def _enrich_with_wb_gdp(
    base: dict[str, Any], client: SeedingHttpClient
) -> dict[str, Any]:
    """Overlay World Bank GDP data onto the base debt timeline payload.

    Updates GDP only from a complete observed response and records coverage.
    """
    timeline = _timeline(base)
    for entry in timeline:
        entry["gdp_ratio"] = None
        entry["source_evidence"] = [item for item in entry.get("source_evidence", [])
            if isinstance(item, dict) and item.get("identity", {}).get("measure") not in ("gdp", "gdp_value")]
    try:
        gdp_by_year = _fetch_wb_gdp(client)
    except Exception as exc:
        logger.warning("World Bank GDP API unavailable, using fixture GDP: %s", exc)
        base.setdefault("metadata", {}).setdefault("refresh_components", {})["gdp"] = {
            "state": "unavailable", "reason": "worldbank_response_unavailable",
        }
        return base

    updated = 0
    missing = []
    for entry in timeline:
        year = entry.get("year")
        value = gdp_by_year.get(year)
        if (not isinstance(value, bool) and isinstance(value, (int, Decimal))
                and Decimal(value).is_finite() and value > 0):
            entry["gdp"] = value / Decimal("1e9")
            entry["source_evidence"] = [*(entry.get("source_evidence") or []), *getattr(gdp_by_year, "evidence", {}).get(year, [])]
            total = entry.get("total", 0)
            if entry["gdp"] > 0:
                entry["gdp_ratio"] = float((Decimal(str(total)) / entry["gdp"] * 100).quantize(Decimal("0.1")))
            updated += 1
        else:
            missing.append(year)

    base.setdefault("metadata", {}).setdefault("refresh_components", {})["gdp"] = {
        "state": "live" if updated and not missing else "partial" if updated else "unavailable",
        "observed_years": updated, "missing_years": missing,
    }

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
        entry.update(_stock_evidence(live))
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
                **_stock_evidence(live),
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


def _stock_evidence(observation):
    from urllib.parse import urlsplit
    from services.response_receipts import receipt_is_sealed

    evidence = list(observation.get("source_evidence") or [])
    result = {"source_evidence": evidence, "source_url": None}
    receipts = [item.get("_response_receipt") for item in evidence]
    if receipts and all(receipt_is_sealed(receipt) for receipt in receipts):
        urls = {receipt.get("request_url") for receipt in receipts}
        if len(urls) == 1:
            url = urls.pop()
            parsed = urlsplit(url)
            if (parsed.scheme == "https" and parsed.hostname in ("www.centralbank.go.ke", "centralbank.go.ke")
                    and parsed.username is None and parsed.password is None
                    and parsed.port in (None, 443)):
                result["source_url"] = url
    return result


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
    _timeline(base)
    base.setdefault("metadata", {})["refresh_components"] = {}

    # Authoritative debt stocks FIRST, so the GDP pass below recomputes
    # gdp_ratio from the corrected totals.
    base, overlaid = _overlay_cbk_public_debt(base, client, settings)
    # The old ratio belongs to the old stock/GDP pair. Recalculation below
    # requires a newly observed denominator, including when GDP is disabled.
    for entry in _timeline(base):
        entry["gdp_ratio"] = None
    required = len(_timeline(base))
    base["metadata"]["refresh_components"]["debt"] = {
        "state": "live" if overlaid == required else "partial" if overlaid else "unavailable",
        "observed_years": overlaid, "required_years": required,
    }

    # Enrich with live World Bank GDP (graceful fallback on failure)
    if settings.enrich_with_worldbank:
        base = _enrich_with_wb_gdp(base, client)
    else:
        logger.debug("World Bank enrichment disabled via config")
        base.setdefault("metadata", {}).setdefault("refresh_components", {})["gdp"] = {
            "state": "disabled", "reason": "worldbank_enrichment_disabled",
        }

    # Record provenance: the series is only "live" when the debt figures
    # themselves came from the publisher. Live GDP over fixture debt is
    # still fixture debt, and saying otherwise is the false-green this
    # instrumentation exists to prevent.
    from ...freshness import mark_fixture, mark_live, mark_partial

    if overlaid:
        detail = f"CBK Statistical Bulletin 4.1.3, {overlaid} year(s)"
        gdp = base.get("metadata", {}).get("refresh_components", {}).get("gdp", {})
        if gdp.get("state") == "live" and overlaid == required:
            mark_live("debt_timeline", detail=detail)
        else:
            reason = "debt_stock_refresh_incomplete" if overlaid != required else "gdp_refresh_unavailable"
            mark_partial("debt_timeline", reason=reason,
                         detail=f"{detail} of {required}; GDP refresh: {gdp.get('state', 'unavailable')}")
    else:
        gdp = base["metadata"]["refresh_components"]["gdp"]
        if gdp["state"] in ("live", "partial"):
            mark_partial("debt_timeline", reason="cbk_bulletin_unavailable",
                         detail=f"No current debt-stock observation; GDP refresh: {gdp['state']}")
        else:
            mark_fixture("debt_timeline", reason="cbk_bulletin_unavailable",
                         detail=f"No current debt-stock observation; GDP refresh: {gdp['state']}")

    return base

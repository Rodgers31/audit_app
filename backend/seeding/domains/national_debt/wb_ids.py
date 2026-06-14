"""Fetch Kenya per-creditor external public debt from the World Bank
International Debt Statistics (IDS) API.

Why WB IDS?
-----------
CBK has the raw per-loan data internally but doesn't publish it in
machine-readable form. Their Statistical Bulletin only shows
aggregates by instrument type (T-bills/T-bonds) and external by
country. The PDMO External Public Debt Register page is a
placeholder; their Monthly Bulletins haven't been updated since
2011.

Kenya is required to report loan-level external debt to the World
Bank's Debtor Reporting System (DRS) as part of WB lending
agreements. WB then republishes the per-creditor view via IDS at
https://api.worldbank.org/v2/. So the data ORIGINATES from CBK; WB
is just the public, machine-readable distribution layer.

Caveats
-------
* External debt only — domestic (T-bills, T-bonds held by Kenyan
  banks/funds) is NOT in IDS. Use CBK Statistical Bulletin for that.
* Annual cadence with ~12-month lag (2024 figures published mid
  2026). CBK Statistical Bulletin is more current at the aggregate
  level. We accept the lag in exchange for per-creditor granularity
  that no other live source publishes.
* Values in USD; we convert at a fixed rate (matches the convention
  in fiscal_summary/fetcher.py — easy to extract to settings later).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient

logger = logging.getLogger("seeding.national_debt.wb_ids")

# Same approximate USD→KES rate the fiscal_summary fetcher uses
# (130.0). Conservative average for 2018-2025; close enough for
# headline cards. Centralise in SeedingSettings if/when we need
# a market-tracking rate.
_USD_KES_RATE = Decimal("130.0")

_WB_BASE = "https://api.worldbank.org/v2/country/KEN/indicator"


# Curated WB IDS indicator codes mapped onto the lender names used in
# `seeding/real_data/national_debt.json`. The writer dedupes loans by
# (entity_id, lender, issue_date), so matching the fixture's lender
# strings means a successful WB IDS fetch UPDATES the existing row
# in-place rather than creating a parallel duplicate.
#
# `combine_with` lets us aggregate two IDS codes into a single fixture
# lender (IBRD + IDA both belong under the fixture's "World Bank"
# umbrella, since the fixture doesn't break them out).
# All codes verified to exist in the IDS source-6 catalog as of
# 2026-04. Codes I tried and discarded: DT.DOD.MIMF.CD (use DIMF
# instead — that's "Use of IMF credit"), DT.DOD.MAFD.CD (AfDB has no
# dedicated DOD line in IDS), DT.DOD.MOFT.CD (Other multilateral has
# no dedicated line either — derive from MLAT − MIBR − MIDA − DIMF if
# we want it), DT.DOD.PBND.CD (Bonds aren't broken out in modern IDS;
# the closest is PNGC for "PNG, commercial banks and other creditors"
# which bundles bonds + syndicated loans together).
#
# So the curated list below covers what IDS actually publishes for
# Kenya. The "Other multilateral" + Eurobonds-specific fixture rows
# stay on fixture data until/unless WB exposes them separately.
WB_IDS_CREDITORS: List[Dict[str, Optional[str]]] = [
    {
        "code": "DT.DOD.MIBR.CD",
        "combine_with": "DT.DOD.MIDA.CD",
        "lender": "Multilateral (World Bank / IDA / IBRD)",
        "debt_category": "external_multilateral",
    },
    {
        "code": "DT.DOD.DIMF.CD",
        "combine_with": None,
        "lender": "Multilateral (IMF — Extended Credit & Resilience Trust)",
        "debt_category": "external_multilateral",
    },
    # NOT INCLUDED:
    # * DT.DOD.PCBK.CD (commercial banks) — confirmed live as
    #   "indicator not found" for KEN today. Either Kenya doesn't
    #   classify any external debt under this code or WB hasn't
    #   processed it yet. Fixture entry stays.
    # * DT.DOD.BLAT.CD (bilateral total) — fixture already breaks
    #   bilateral down per-country (China/Japan/France/Other).
    #   Overlaying the aggregate would double-count. Per-country IDS
    #   breakouts use a different counterpart-area endpoint;
    #   follow-up PR.
]


def fetch_external_debt_from_wb_ids(
    client: SeedingHttpClient, settings: SeedingSettings
) -> List[Dict[str, Any]]:
    """Hit WB IDS once per curated creditor; return loan dicts in the
    same shape as ``national_debt.json``'s ``loans`` array.

    Failures are non-fatal at the per-creditor level — one indicator
    timing out doesn't kill the whole pull. Failures are logged at
    INFO/WARNING and that creditor's fixture entry stays in place.
    """
    out: List[Dict[str, Any]] = []
    for creditor in WB_IDS_CREDITORS:
        code = creditor["code"]
        primary = _fetch_latest(client, code)
        if primary is None:
            continue
        kes_value = Decimal(str(primary["value"])) * _USD_KES_RATE
        latest_year = primary["date"]
        if creditor["combine_with"]:
            secondary = _fetch_latest(
                client, creditor["combine_with"], at_year=latest_year
            )
            if secondary is None:
                # Skip the row entirely rather than write a misleading
                # partial. For combined indicators (IBRD + IDA), the
                # primary value alone undercounts the lender bucket by a
                # large factor — silently writing IBRD-only as "World
                # Bank" overwrote the fixture row with a 7x understatement
                # in a real prod run. Better to keep the fixture in place
                # than corrupt it; the next run will retry the secondary.
                logger.warning(
                    "WB IDS skipping %s: combine_with %s unavailable; "
                    "fixture row stays in place",
                    creditor["lender"], creditor["combine_with"],
                )
                continue
            kes_value += Decimal(str(secondary["value"])) * _USD_KES_RATE
        out.append(
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": creditor["lender"],
                "debt_category": creditor["debt_category"],
                # WB IDS DOD indicators report stock outstanding —
                # there's no separate principal series we can mirror,
                # so we use the same value for both. The frontend reads
                # `outstanding`; principal is bookkeeping.
                "principal": _format_decimal(kes_value),
                "outstanding": _format_decimal(kes_value),
                "interest_rate": None,
                # Aggregate over many loans, no single issue date —
                # use the fiscal-year-start of the WB IDS observation
                # so the writer's (entity, lender, issue_date) dedupe
                # key changes once per IDS publication.
                "issue_date": f"{latest_year}-01-01",
                "maturity_date": None,
                "currency": "KES",
                "notes": (
                    f"World Bank IDS, indicator {code}"
                    + (
                        f" + {creditor['combine_with']}"
                        if creditor["combine_with"]
                        else ""
                    )
                    + f" (year {latest_year}); "
                    f"converted at KES {_USD_KES_RATE}/USD."
                ),
            }
        )
    logger.info("WB IDS fetched %d creditor records", len(out))
    return out


def _fetch_latest(
    client: SeedingHttpClient, code: str, *, at_year: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Return the most recent non-null observation for `code`. If
    `at_year` is set, look only at that year (used when combining two
    indicators that must share a vintage). Returns ``None`` on any
    failure — caller decides whether to skip or fall back."""
    if at_year:
        date_range = at_year
        per_page = 2
    else:
        # Look back 5 years; the latest non-null wins.
        date_range = "2020:2025"
        per_page = 10
    url = (
        f"{_WB_BASE}/{code}"
        f"?format=json&date={date_range}&per_page={per_page}"
    )
    try:
        response = client.get(url, raise_for_status=True)
        body = response.json()
    except Exception as exc:
        logger.warning("WB IDS request failed for %s: %s", code, exc)
        return None
    if not isinstance(body, list) or len(body) < 2 or not body[1]:
        logger.info("WB IDS returned no data for %s", code)
        return None
    return next(
        (entry for entry in body[1] if entry.get("value") is not None),
        None,
    )


def _format_decimal(value: Decimal) -> str:
    """Render KES amounts as integer-string to match the fixture's
    ``"principal": "820000000000.00"`` shape (Decimal preserves it
    after parser.py wraps it back)."""
    return f"{value.quantize(Decimal('1'))}.00"


__all__ = ["fetch_external_debt_from_wb_ids", "WB_IDS_CREDITORS"]

"""Kenya's external debt broken down by individual creditor.

The last aggregate-only part of the debt register. ``wb_ids.py`` covers exactly
two creditors — the World Bank (IBRD+IDA) and the IMF — and its own comments
explain why the rest stayed on fixture data: "Bonds aren't broken out in modern
IDS", ``DT.DOD.PCBK.CD`` "confirmed live as 'indicator not found' for KEN", and
per-country bilateral breakouts "use a different counterpart-area endpoint;
follow-up PR".

This is that endpoint. IDS source 6 carries a **Counterpart-Area** dimension,
and against it every one of those series resolves for Kenya:

    DT.DOD.MLAT.CD   multilateral    13 creditors   USD 19.99bn
    DT.DOD.BLAT.CD   bilateral       17 creditors   USD  8.07bn
    DT.DOD.PBND.CD   bonds            1 (bondholders) USD 6.60bn
    DT.DOD.PCBK.CD   commercial banks 11 creditors   USD  0.92bn
                                                     ---------
    DT.DOD.DPPG.CD   PPG total                       USD 35.58bn

WHAT IT REPLACES, AND WHY THAT MATTERS
--------------------------------------
The fixture's external rows are round numbers that overstate the book. Against
IDS 2024 at KSh 130/USD:

    Eurobonds                      site 2,276Bn   IDS   858Bn   +165%
    Commercial banks (syndicated)  site   400Bn   IDS   120Bn   +234%

The Eurobond row alone put KSh 1.4 trillion of debt on the site that no
publisher reports — it implied a USD 17.5bn Eurobond stock against an actual
6.6bn. It also omits creditors entirely: the Eastern & Southern African Trade
& Development Bank lends Kenya USD 1.43bn and appears nowhere.

So a successful, gated pull REPLACES the external fixture rows rather than
overlaying onto them. Appending real creditors beside the old buckets would
double-count the same debt under two names — which is the failure mode the
lender treemap was withdrawn over.

GATES
-----
Three, and all three passed exactly when built (2026-09-03), which is what
makes them worth asserting rather than hoping:

1. Per series, the creditor rows sum to IDS's own ``World`` row.
2. The four component series sum to ``DT.DOD.DPPG.CD``.
3. Cross-publisher: the total sits within a band of CBK's published external
   debt. IDS is PPG-only and a year behind, so the band is wide and its job is
   to catch a units or FX error, not to certify agreement.

Any failure quarantines the whole pull. A partial creditor list is worse than
the aggregate it would replace.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient

logger = logging.getLogger("seeding.national_debt.wb_ids_creditors")

_IDS_BASE = "https://api.worldbank.org/v2/sources/6/country/KEN/series"

# IDS reports USD. Same rate wb_ids.py and fiscal_summary use; kept in one
# place here so a future market rate replaces one constant.
USD_KES_RATE = Decimal("130.0")

# IDS's aggregate row. Used as the identity check, never as a creditor.
WORLD_ROW = "World"

# series -> (debt_category, how to describe the creditor on screen)
SERIES: Dict[str, Tuple[str, str]] = {
    "DT.DOD.MLAT.CD": ("external_multilateral", "Multilateral"),
    "DT.DOD.BLAT.CD": ("external_bilateral", "Bilateral"),
    "DT.DOD.PBND.CD": ("external_commercial", "Bondholders"),
    "DT.DOD.PCBK.CD": ("external_commercial", "Commercial banks"),
}
TOTAL_SERIES = "DT.DOD.DPPG.CD"

# How far the IDS total may sit from CBK's published external debt. Wide on
# purpose: IDS is public-and-publicly-guaranteed only, annual, and roughly a
# year behind, so it should read somewhat LOW against a current CBK figure.
# This catches a units slip or an FX error, not a genuine vintage difference.
EXTERNAL_COVERAGE_BAND = (0.60, 1.15)


class IdsCreditorError(RuntimeError):
    """The pull did not hold together and must not be published."""


@dataclass
class Creditor:
    name: str
    counterpart_id: str
    series: str
    debt_category: str
    usd: float

    @property
    def kes(self) -> Decimal:
        return Decimal(str(self.usd)) * USD_KES_RATE


def _fetch_series(
    client: SeedingHttpClient, series: str, year: int
) -> Dict[str, Tuple[str, float]]:
    """{creditor name: (counterpart id, USD)} for one series and year."""
    url = (
        f"{_IDS_BASE}/{series}/counterpart-area/all/time/YR{year}"
        "?format=json&per_page=400"
    )
    resp = client.get(url)
    resp.raise_for_status()
    payload = resp.json()
    try:
        records = payload["source"]["data"]
    except (KeyError, TypeError) as exc:
        raise IdsCreditorError(f"{series}: unexpected IDS response shape") from exc

    out: Dict[str, Tuple[str, float]] = {}
    for record in records:
        if record.get("value") is None:
            continue
        dims = {v["concept"]: v for v in record.get("variable", [])}
        area = dims.get("Counterpart-Area")
        if not area:
            continue
        out[area["value"]] = (area["id"], float(record["value"]))
    return out


def latest_year_with_data(
    client: SeedingHttpClient, candidates: Optional[List[int]] = None
) -> Optional[int]:
    """Newest year IDS has published a PPG total for.

    Derived, not hardcoded: IDS runs about a year behind and the lag moves.
    Asking the API which year it has is the difference between a register that
    ages forward on its own and one that quietly freezes.
    """
    from datetime import date

    years = candidates or list(range(date.today().year, date.today().year - 6, -1))
    for year in years:
        try:
            if _fetch_series(client, TOTAL_SERIES, year).get(WORLD_ROW):
                return year
        except Exception as exc:  # noqa: BLE001 - try the next year
            logger.debug("IDS %s unavailable for %s: %s", TOTAL_SERIES, year, exc)
    return None


def fetch_creditors(
    client: SeedingHttpClient, year: int
) -> Tuple[List[Creditor], Dict[str, Any]]:
    """Every external creditor IDS publishes for Kenya, with its identity checks."""
    creditors: List[Creditor] = []
    checks: Dict[str, Any] = {"year": year, "series": {}}

    component_total = 0.0
    for series, (category, _label) in SERIES.items():
        rows = _fetch_series(client, series, year)
        world = rows.pop(WORLD_ROW, None)
        if world is None:
            raise IdsCreditorError(
                f"{series}: no World row for {year}; cannot verify the "
                "creditor rows sum to anything"
            )
        world_usd = world[1]

        # Gate 1: the parts are the whole.
        #
        # Decimal, and a ROUNDING-sized tolerance — not a percentage of the
        # portfolio. At 0.5% of a USD 20bn multilateral total this gate
        # tolerated ~USD 100m of missing detail, so real creditors (EEC, the
        # Nordic funds, BADEA) could be dropped while it still reported
        # "identity: ok". The whole point of the gate is to catch omitted rows,
        # and IDS publishes at currency precision, so the only slack it needs
        # is one unit of rounding per row.
        detail_d = sum(
            (Decimal(str(v)) for _cid, v in rows.values()), Decimal(0)
        )
        world_d = Decimal(str(world_usd))
        tolerance = Decimal(len(rows) + 1)
        if abs(detail_d - world_d) > tolerance:
            raise IdsCreditorError(
                f"{series}: creditor rows sum to {detail_d:,.0f} against IDS's "
                f"own World total {world_d:,.0f} "
                f"(difference {abs(detail_d - world_d):,.0f}, tolerance "
                f"{tolerance:,.0f} = one rounding unit per creditor row). "
                "A gap this size means rows are missing, not rounding."
            )
        detail = float(detail_d)

        checks["series"][series] = {
            "world_usd": world_usd,
            "creditor_count": len(rows),
            "identity": "ok",
        }
        component_total += world_usd
        for name, (cid, usd) in rows.items():
            creditors.append(
                Creditor(
                    name=name,
                    counterpart_id=cid,
                    series=series,
                    debt_category=category,
                    usd=usd,
                )
            )

    # Gate 2: the components are the PPG total.
    ppg = _fetch_series(client, TOTAL_SERIES, year).get(WORLD_ROW)
    if ppg is None:
        raise IdsCreditorError(f"{TOTAL_SERIES}: no World total for {year}")
    ppg_usd = ppg[1]
    if abs(component_total - ppg_usd) > max(1.0, ppg_usd * 0.005):
        raise IdsCreditorError(
            f"components sum to {component_total:,.0f} against DPPG "
            f"{ppg_usd:,.0f}"
        )
    checks["components_usd"] = component_total
    checks["ppg_total_usd"] = ppg_usd
    checks["components_identity"] = "ok"

    if not creditors:
        raise IdsCreditorError(f"IDS returned no creditors for {year}")
    return creditors, checks


def check_external_coverage(
    creditors: List[Creditor], published_external_kes: Optional[float]
) -> Dict[str, Any]:
    """Gate 3 — the IDS total against CBK's published external debt."""
    total_kes = float(sum(c.kes for c in creditors))
    if not published_external_kes:
        return {
            "total_kes": total_kes,
            "published_external_kes": None,
            "coverage_ratio": None,
            "status": "unchecked",
            "reason": "no published external total to compare against",
        }
    ratio = total_kes / published_external_kes
    low, high = EXTERNAL_COVERAGE_BAND
    ok = low <= ratio <= high
    return {
        "total_kes": total_kes,
        "published_external_kes": published_external_kes,
        "coverage_ratio": round(ratio, 4),
        "band": [low, high],
        "status": "within_band" if ok else "out_of_band",
        "reason": (
            None
            if ok
            else (
                f"IDS creditor total is {ratio:.0%} of CBK's published external "
                f"debt, outside the {low:.0%}-{high:.0%} band — likely a units "
                "or exchange-rate error rather than a vintage difference"
            )
        ),
    }


def to_loan_rows(creditors: List[Creditor], year: int) -> List[Dict[str, Any]]:
    """Creditors as loan dicts, in the shape ``national_debt.json`` uses.

    Each row carries its OWN source. The payload these rows are merged into is
    sourced to the CBK/National Treasury bulletin, and the parser reads source
    at payload level, so without this every IDS creditor persisted as though a
    CBK publication had reported it — free text in ``notes`` is not provenance.
    """
    row_source_url = f"{_IDS_BASE}/{TOTAL_SERIES}/counterpart-area/all/time/YR{year}"
    row_source_title = (
        f"World Bank International Debt Statistics {year} — Kenya external "
        "debt by creditor"
    )
    rows: List[Dict[str, Any]] = []
    for c in creditors:
        _category, label = SERIES[c.series]
        # "Bondholders" has one counterpart row and it is IDS's aggregate name,
        # so name it for what Kenya actually issued.
        display = (
            "Eurobonds and other international bonds"
            if c.series == "DT.DOD.PBND.CD"
            else f"{label} ({c.name})"
        )
        rows.append(
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": display,
                "source_url": row_source_url,
                "source_title": row_source_title,
                "publisher": "World Bank",
                "debt_category": c.debt_category,
                "principal": str(c.kes),
                "outstanding": str(c.kes),
                "interest_rate": None,
                "issue_date": f"{year}-12-31",
                "maturity_date": None,
                "currency": "KES",
                "notes": (
                    f"World Bank International Debt Statistics {year}, "
                    f"{c.series}, counterpart area {c.counterpart_id} "
                    f"({c.name}). USD {c.usd:,.0f} converted at "
                    f"{USD_KES_RATE} KES/USD. Public and publicly guaranteed "
                    "external debt only."
                ),
            }
        )
    return rows


def fetch_external_creditors(
    client: SeedingHttpClient,
    settings: Optional[SeedingSettings] = None,
    published_external_kes: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """The whole pull, gated. ``None`` means nothing may be published."""
    year = latest_year_with_data(client)
    if year is None:
        logger.warning("IDS has no PPG total for any recent year; skipping")
        return None
    try:
        creditors, checks = fetch_creditors(client, year)
    except IdsCreditorError as exc:
        logger.warning("IDS creditor pull failed its identity checks: %s", exc)
        return None

    coverage = check_external_coverage(creditors, published_external_kes)
    # Require a POSITIVE result, don't merely reject the negative one.
    # Quarantining only "out_of_band" let "unchecked" — which is what a missing
    # or malformed denominator returns — sail straight through, silently
    # disabling a gate this pull describes as mandatory.
    if coverage["status"] != "within_band":
        logger.warning(
            "IDS creditor pull quarantined (%s): %s",
            coverage["status"],
            coverage.get("reason") or "no independent total to check against",
        )
        return None

    logger.info(
        "IDS %s: %d external creditors, KES %.2fT (%s of CBK's published "
        "external debt)",
        year,
        len(creditors),
        coverage["total_kes"] / 1e12,
        f"{coverage['coverage_ratio']:.0%}" if coverage["coverage_ratio"] else "n/a",
    )
    return {
        "year": year,
        "source_url": (
            f"{_IDS_BASE}/{TOTAL_SERIES}/counterpart-area/all/time/YR{year}"
        ),
        "source_title": (
            f"World Bank International Debt Statistics {year} — Kenya external "
            "debt by creditor"
        ),
        "checks": checks,
        "coverage": coverage,
        "creditors": creditors,
        "loans": to_loan_rows(creditors, year),
    }

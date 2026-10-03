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

    DT.DOD.DIMF.CD   use of IMF credit 1 creditor   USD  4.96bn

— including ``DT.DOD.DIMF.CD``, which resolves to counterpart area 907,
"International Monetary Fund", for the same figure as its own World row.

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

WHAT ELSE IS IN KENYA'S EXTERNAL DEBT
------------------------------------
``DT.DOD.DPPG.CD`` is not Kenya's external debt. It is one component of
``DT.DOD.DECT.CD``, and IDS reports the others separately::

    DT.DOD.DPPG.CD  35.583bn   public & publicly guaranteed, long-term
    DT.DOD.DIMF.CD   4.958bn   use of IMF credit
    DT.DOD.DSTC.CD   2.008bn   short-term, all sectors
    DT.DOD.DPNG.CD   0.338bn   private non-guaranteed, long-term
                    ---------
    DT.DOD.DECT.CD  42.886bn   == the sum of the four, exactly (2024)

For twenty runs this module pulled only the DPPG components, and
``fetcher._replace_external_loans`` then dropped every external row the pull
did not name — including the IMF row ``wb_ids.py`` had just written. KSh ~668Bn
of a real national-government liability was deleted from the register on every
seed, and nothing said so, because the only check standing over it was a
coverage BAND: at 94.87% of CBK's published external debt the pull sat
comfortably inside 0.60-1.15 with a whole creditor class missing.

So every component of DECT is now DECLARED, in ``DECT_COMPONENTS`` below —
carried into the register, or excluded with a reason — and the declaration is
checked against IDS's own total. A component nobody declared makes that sum
short and fails the run.

GATES
-----
Four. The first three are identities that hold to the currency unit, which is
what makes them worth asserting rather than hoping:

1. Per series, the creditor rows sum to IDS's own ``World`` row.
2. Per carried component, its creditor series sum to the component's own total
   (``MLAT + BLAT + PBND + PCBK == DPPG``; ``DIMF == DIMF``).
3. The declared components — carried and excluded together — sum to
   ``DT.DOD.DECT.CD``. This is what makes the declaration exhaustive: it cannot
   be satisfied while a component of Kenya's external debt goes unnamed.
4. Cross-publisher: the total sits within a band of CBK's published external
   debt. A band, not an identity — different publisher, different vintage — so
   its job is to catch a units or FX error, and it is explicitly NOT the thing
   protecting the register from a missing creditor class. Gate 3 is.

Any failure quarantines the whole pull. A partial creditor list is worse than
the aggregate it would replace.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

from ...config import SeedingSettings
from .fx import rate_provenance, usd_kes_rate_for_year
from ...http_client import SeedingHttpClient
from ...observations import ObservedSeries
from services.response_receipts import capture_response
import json

logger = logging.getLogger("seeding.national_debt.wb_ids_creditors")

_IDS_BASE = "https://api.worldbank.org/v2/sources/6/country/KEN/series"

# IDS reports USD; the rate to convert it is fetched per IDS year from the
# World Bank's own PA.NUS.FCRF series — see fx.py. There is deliberately no
# module-level constant any more: a frozen rate multiplied every creditor and
# was 3.7% out against 2024 while looking like a checked number.

# IDS's aggregate row. Used as the identity check, never as a creditor.
WORLD_ROW = "World"

# series -> (debt_category, how to describe the creditor on screen)
SERIES: Dict[str, Tuple[str, str]] = {
    "DT.DOD.MLAT.CD": ("external_multilateral", "Multilateral"),
    "DT.DOD.BLAT.CD": ("external_bilateral", "Bilateral"),
    "DT.DOD.PBND.CD": ("external_commercial", "Bondholders"),
    "DT.DOD.PCBK.CD": ("external_commercial", "Commercial banks"),
    # IDS breaks IMF credit out by counterpart area like any other series:
    # World 4,958,198,572.8 and one creditor row, 907 "International Monetary
    # Fund", for the same figure. It passes gate 1 exactly.
    "DT.DOD.DIMF.CD": ("external_multilateral", "Multilateral"),
}
TOTAL_SERIES = "DT.DOD.DPPG.CD"

#: IDS's total external debt. The denominator of the declaration gate.
EXTERNAL_TOTAL_SERIES = "DT.DOD.DECT.CD"


@dataclass(frozen=True)
class DectComponent:
    """One component of ``DT.DOD.DECT.CD``, and what the register does with it.

    Every component is declared here. There is no third state: a component is
    carried into the register or excluded with a stated reason, and one that is
    neither cannot exist, because the declaration gate would then be short of
    IDS's own external total and fail the run.
    """

    series: str
    #: True -> its creditors go into the register. False -> excluded, and
    #: ``reason`` says why in terms a reader can check.
    carried: bool
    reason: str
    #: Counterpart-area series this component decomposes into. Carried only.
    creditor_series: Tuple[str, ...] = ()
    #: The basis sentence that goes on every loan row from this component, so
    #: a reader of one row knows what it is and is not. Carried only.
    row_note: str = ""


#: Every component of Kenya's external debt as IDS reports it. Order is the
#: order they are checked and logged in.
DECT_COMPONENTS: Tuple[DectComponent, ...] = (
    DectComponent(
        series=TOTAL_SERIES,
        carried=True,
        reason=(
            "public and publicly guaranteed long-term external debt — the "
            "national government's own borrowing and what it guarantees"
        ),
        creditor_series=(
            "DT.DOD.MLAT.CD",
            "DT.DOD.BLAT.CD",
            "DT.DOD.PBND.CD",
            "DT.DOD.PCBK.CD",
        ),
        row_note="Public and publicly guaranteed external debt only.",
    ),
    DectComponent(
        series="DT.DOD.DIMF.CD",
        carried=True,
        reason=(
            "use of IMF credit — a national-government liability that IDS "
            "reports OUTSIDE the PPG aggregate, so a register built from the "
            "DPPG components alone deletes it"
        ),
        creditor_series=("DT.DOD.DIMF.CD",),
        row_note=(
            "Use of IMF credit. IDS reports this outside the public and "
            "publicly guaranteed aggregate; it is carried here because it is a "
            "national-government liability."
        ),
    ),
    DectComponent(
        series="DT.DOD.DSTC.CD",
        carried=False,
        reason=(
            "short-term external debt, ALL SECTORS. IDS publishes no "
            "public/private split of it, and 93% of Kenya's sits under the "
            "'Other Multiple Lenders' counterpart, so carrying it would put "
            "private trade credit into a government register. Excluded, and "
            "its size is recorded here so the gap is visible rather than "
            "silent."
        ),
    ),
    DectComponent(
        series="DT.DOD.DPNG.CD",
        carried=False,
        reason=(
            "private non-guaranteed long-term debt — borrowing by private "
            "entities that the government has not guaranteed, so not a public "
            "liability at all"
        ),
    ),
)

# How far the IDS total may sit from CBK's published external debt.
#
# A BAND, and deliberately a wide one: different publisher, different vintage
# (IDS is annual and roughly a year behind), different valuation date for the
# FX conversion. Its job is to catch a units slip or an exchange-rate error.
#
# It is no longer the only thing between a missing creditor class and the
# homepage — that was the defect. With DPPG only, the pull read 94.87% of CBK's
# published 2024 external debt while the whole of IMF credit was absent, and
# 94.87% is a comfortable pass. The identity gates above are what catch that
# now; this one is a last cross-publisher sanity check.
#
# Carrying IMF credit moves the measured ratio from ~0.95 to ~1.08 for 2024,
# so there is roughly 6% of headroom left below the ceiling. A pull that
# breaches it quarantines and the fixture's external rows publish instead —
# loudly, in the log and in payload metadata (see fetcher.fetch_debt_payload).
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
    #: KES per USD for this creditor's IDS year. Required — there is no
    #: default, so a conversion cannot happen without a rate somebody fetched.
    usd_kes_rate: Decimal = None  # type: ignore[assignment]
    source_evidence: list | None = None

    @property
    def kes(self) -> Decimal:
        if self.usd_kes_rate is None:
            raise IdsCreditorError(
                f"no_usd_kes_rate: {self.name} — refusing to convert USD to "
                f"KES without a rate for its year"
            )
        return Decimal(str(self.usd)) * self.usd_kes_rate


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
    payload = json.loads(resp.content, parse_float=Decimal)
    receipt = resp.extensions.get("response_receipt")
    if not isinstance(receipt, dict) or "digest" not in receipt:
        receipt = capture_response(resp, getattr(client, "receipt_store", None))
    receipt = {**receipt, "parser_version": "wb-ids-creditor-v1"}
    try:
        records = payload["source"]["data"]
    except (KeyError, TypeError) as exc:
        raise IdsCreditorError(f"{series}: unexpected IDS response shape") from exc

    out: Dict[str, Tuple[str, float]] = ObservedSeries()
    for index, record in enumerate(records):
        if record.get("value") is None:
            continue
        dims = {v["concept"]: v for v in record.get("variable", [])}
        area = dims.get("Counterpart-Area")
        if not area:
            continue
        expected = {"Country": "KEN", "Series": series, "Time": f"YR{year}"}
        for concept, identity in expected.items():
            if concept in dims and dims[concept].get("id") != identity:
                raise IdsCreditorError(f"{series}: wrong {concept} in actual response")
        raw = record["value"]
        if isinstance(raw, bool) or not isinstance(raw, (int, Decimal)) or not Decimal(raw).is_finite() or raw < 0:
            raise IdsCreditorError(f"{series}: invalid monetary observation")
        if area["value"] in out:
            raise IdsCreditorError(f"{series}: duplicate counterpart area")
        out[area["value"]] = (area["id"], float(raw))
        out.evidence[area["value"]] = [{
            "version": 1, "source_kind": "api", "_response_receipt": receipt,
            "receipt": {"digest": receipt["digest"]},
            "identity": {"measure": "outstanding", "entity_id": None, "geography": "KEN", "period": str(year),
                "unit": "KES", "basis": "actual", "dimensions": {}},
            "raw_value": str(raw), "raw_unit": "USD", "unit": "KES", "value": None,
            "locator": {"json_path": f"$.source.data[{index}].value", "indicator": series,
                "country": "KEN", "date": str(year), "counterpart_area": area["id"]},
            "transformation": {"operation": "currency_conversion", "factor": None, "rounding": 2},
            "checks": {"identity": all(k in dims for k in expected), "value": False,
                "transport": resp.status_code == 200 and receipt.get("acquired_at") is not None and payload.get("pages") == 1,
                "bytes": receipt["byte_check"]["status"] == "matched", "locator": True},
            "reconciliation": {"status": "not_checked", "reason": "independent_fx_operand_not_checked"},
        }]
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
    client: SeedingHttpClient, year: int, usd_kes_rate: Decimal = None
) -> Tuple[List[Creditor], Dict[str, Any]]:
    """Every external creditor IDS publishes for Kenya, with its identity checks."""
    creditors: List[Creditor] = []
    checks: Dict[str, Any] = {"year": year, "series": {}, "components": {}}

    cache: Dict[str, Dict[str, Tuple[str, float]]] = {}

    def rows_for(series: str) -> Dict[str, Tuple[str, float]]:
        """One request per series per run; callers get their own copy to pop."""
        if series not in cache:
            cache[series] = _fetch_series(client, series, year)
        return dict(cache[series])

    def world_usd(series: str) -> Decimal:
        world = rows_for(series).get(WORLD_ROW)
        if world is None:
            raise IdsCreditorError(
                f"{series}: no World row for {year}; cannot verify the "
                "creditor rows sum to anything"
            )
        return Decimal(str(world[1]))

    declared_total = Decimal(0)
    carried_total = Decimal(0)

    for component in DECT_COMPONENTS:
        if not component.carried:
            # An excluded component IDS did not publish this year counts as
            # zero rather than stopping the run. Gate 3 is what decides: if it
            # really is zero the declaration still sums to DECT, and if it is
            # not, gate 3 fails and names the missing amount. Hard-failing here
            # would quarantine the whole register over a series we do not carry.
            missing = rows_for(component.series).get(WORLD_ROW) is None
            component_usd = Decimal(0) if missing else world_usd(component.series)
            declared_total += component_usd
            checks["components"][component.series] = {
                "disposition": "excluded",
                "world_usd": float(component_usd),
                "published": not missing,
                "reason": component.reason,
            }
            logger.info(
                "IDS %s: %s excluded (USD %.3fbn%s) — %s",
                year, component.series, float(component_usd) / 1e9,
                "" if not missing else ", not published for this year",
                component.reason,
            )
            continue

        component_usd = world_usd(component.series)
        declared_total += component_usd

        parts = Decimal(0)
        for series in component.creditor_series:
            category, _label = SERIES[series]
            rows = rows_for(series)
            world = rows.pop(WORLD_ROW, None)
            if world is None:
                raise IdsCreditorError(
                    f"{series}: no World row for {year}; cannot verify the "
                    "creditor rows sum to anything"
                )
            series_usd = Decimal(str(world[1]))

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
            tolerance = Decimal(len(rows) + 1)
            if abs(detail_d - series_usd) > tolerance:
                raise IdsCreditorError(
                    f"{series}: creditor rows sum to {detail_d:,.0f} against IDS's "
                    f"own World total {series_usd:,.0f} "
                    f"(difference {abs(detail_d - series_usd):,.0f}, tolerance "
                    f"{tolerance:,.0f} = one rounding unit per creditor row). "
                    "A gap this size means rows are missing, not rounding."
                )

            checks["series"][series] = {
                "world_usd": float(series_usd),
                "creditor_count": len(rows),
                "identity": "ok",
            }
            parts += series_usd
            for name, (cid, usd) in rows.items():
                creditors.append(
                    Creditor(
                        name=name,
                        counterpart_id=cid,
                        series=series,
                        debt_category=category,
                        usd=usd,
                        usd_kes_rate=usd_kes_rate,
                        source_evidence=getattr(cache.get(series), "evidence", {}).get(name),
                    )
                )

        # Gate 2: the creditor series ARE this component.
        #
        # Same rounding-unit tolerance as gate 1, for the same reason. This
        # used to allow 0.5% of DPPG — USD 178m, about KSh 24Bn — which is
        # large enough to hide a real creditor while reporting "identity: ok".
        tolerance = Decimal(len(component.creditor_series) + 1)
        if abs(parts - component_usd) > tolerance:
            raise IdsCreditorError(
                f"{component.series}: components sum to {parts:,.0f} against "
                f"IDS's own total {component_usd:,.0f} (difference "
                f"{abs(parts - component_usd):,.0f}, tolerance "
                f"{tolerance:,.0f} = one rounding unit per series)"
            )
        checks["components"][component.series] = {
            "disposition": "carried",
            "world_usd": float(component_usd),
            "creditor_series_usd": float(parts),
            "creditor_series": list(component.creditor_series),
            "identity": "ok",
            "reason": component.reason,
        }
        carried_total += component_usd

    # Gate 3: the declared components ARE Kenya's external debt.
    #
    # This is the check that makes DECT_COMPONENTS exhaustive rather than
    # merely well-intentioned. A component IDS publishes and nobody declared —
    # which is exactly what use of IMF credit was for twenty runs — leaves this
    # sum short of IDS's own total and stops the run. A coverage band cannot do
    # that: 94.87% of CBK's published external debt is a comfortable pass.
    external_total = world_usd(EXTERNAL_TOTAL_SERIES)
    tolerance = Decimal(len(DECT_COMPONENTS) + 1)
    if abs(declared_total - external_total) > tolerance:
        undeclared = external_total - declared_total
        raise IdsCreditorError(
            f"the declared components of {EXTERNAL_TOTAL_SERIES} sum to "
            f"{declared_total:,.0f} against IDS's own external total "
            f"{external_total:,.0f} — USD {undeclared:,.0f} of Kenya's "
            f"external debt is neither carried nor excluded by name. Every "
            f"component must be declared in DECT_COMPONENTS; add it there "
            f"with a disposition and a reason rather than letting the "
            f"register be short by an amount nobody named."
        )

    checks["external_total_usd"] = float(external_total)
    checks["declared_total_usd"] = float(declared_total)
    checks["carried_total_usd"] = float(carried_total)
    checks["excluded_total_usd"] = float(declared_total - carried_total)
    checks["declaration_identity"] = "ok"
    # Retained under their old names: the PPG sub-total and the sum of the
    # series that decompose it, which is what these keys have always meant.
    ppg = checks["components"].get(TOTAL_SERIES, {})
    checks["ppg_total_usd"] = ppg.get("world_usd")
    checks["components_usd"] = ppg.get("creditor_series_usd")
    checks["components_identity"] = ppg.get("identity")

    logger.info(
        "IDS %s external debt: carried USD %.3fbn of %.3fbn (%s), excluded "
        "USD %.3fbn (%s)",
        year,
        float(carried_total) / 1e9,
        float(external_total) / 1e9,
        ", ".join(c.series for c in DECT_COMPONENTS if c.carried),
        float(declared_total - carried_total) / 1e9,
        ", ".join(c.series for c in DECT_COMPONENTS if not c.carried),
    )

    if not creditors:
        raise IdsCreditorError(f"IDS returned no creditors for {year}")
    return creditors, checks


def check_external_coverage(
    creditors: List[Creditor], published_external_kes: Optional[float]
) -> Dict[str, Any]:
    """Gate 4 — the IDS total against CBK's published external debt.

    A cross-publisher sanity check, not an identity: different publisher,
    different vintage, different FX valuation date. It catches a units slip or
    an exchange-rate error. It cannot catch a missing creditor class — it
    reported 94.87% with the whole of IMF credit absent — which is why gates
    1-3 in ``fetch_creditors`` exist and run first.
    """
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


#: Stock series -> the series IDS publishes the year's INTEREST PAID under, on
#: the same counterpart-area dimension. Interest actually paid is a published
#: figure; a contractual rate per creditor is not something IDS reports, so
#: this is what the register's "annual cost" can honestly be for external debt.
INTEREST_SERIES: Dict[str, str] = {
    "DT.DOD.MLAT.CD": "DT.INT.MLAT.CD",
    "DT.DOD.BLAT.CD": "DT.INT.BLAT.CD",
    "DT.DOD.PBND.CD": "DT.INT.PBND.CD",
    "DT.DOD.PCBK.CD": "DT.INT.PCBK.CD",
    "DT.DOD.DIMF.CD": "DT.INT.DIMF.CD",
}

#: Why an external row carries no rate, in words a reader can check.
EXTERNAL_RATE_ABSENT_REASON = (
    "World Bank IDS reports the interest Kenya paid this creditor, not the "
    "interest rate on the loans, and no publisher this site reads gives one."
)


def fetch_interest_paid(
    client: SeedingHttpClient, year: int
) -> Tuple[Dict[Tuple[str, str], float], Dict[str, Any]]:
    """Interest paid in ``year``, per (stock series, creditor name), in USD.

    Gated like the stock pull: per series, the creditor rows must sum to IDS's
    own ``World`` row to one rounding unit per row, or the whole interest pull
    is refused. A creditor IDS gives no interest row for is simply absent from
    the result — not zero. Nobody reported a zero.
    """
    paid: Dict[Tuple[str, str], float] = {}
    checks: Dict[str, Any] = {"year": year, "series": {}}
    for stock_series, int_series in INTEREST_SERIES.items():
        rows = _fetch_series(client, int_series, year)
        world = rows.pop(WORLD_ROW, None)
        if world is None:
            raise IdsCreditorError(
                f"{int_series}: no World row for {year}; the creditor interest "
                "rows cannot be checked against anything"
            )
        world_usd = Decimal(str(world[1]))
        detail = sum((Decimal(str(v)) for _cid, v in rows.values()), Decimal(0))
        tolerance = Decimal(len(rows) + 1)
        if abs(detail - world_usd) > tolerance:
            raise IdsCreditorError(
                f"{int_series}: creditor interest rows sum to {detail:,.0f} "
                f"against IDS's own World total {world_usd:,.0f} — rows are "
                "missing, so no creditor's interest figure is published"
            )
        checks["series"][int_series] = {
            "world_usd": float(world_usd),
            "creditor_count": len(rows),
            "identity": "ok",
        }
        for name, (_cid, usd) in rows.items():
            paid[(stock_series, name)] = usd
    return paid, checks


def _interest_terms_for(
    creditor: Creditor,
    year: int,
    interest: Optional[Dict[Tuple[str, str], float]],
    interest_unavailable_reason: Optional[str],
) -> Dict[str, Any]:
    from .interest_terms import absent_terms, published_cost_terms

    if interest is None:
        return absent_terms(
            EXTERNAL_RATE_ABSENT_REASON,
            "World Bank IDS interest-paid figures were not available on this "
            f"run ({interest_unavailable_reason or 'not fetched'}).",
        )
    usd = interest.get((creditor.series, creditor.name))
    if usd is None:
        return absent_terms(
            EXTERNAL_RATE_ABSENT_REASON,
            f"World Bank IDS publishes no interest-paid figure for this "
            f"creditor for {year}.",
        )
    int_series = INTEREST_SERIES[creditor.series]
    return published_cost_terms(
        cost_kes=float(Decimal(str(usd)) * creditor.usd_kes_rate),
        label=f"Interest paid in {year}",
        source={
            "publisher": "World Bank",
            "title": (
                f"International Debt Statistics {year} — Kenya, interest paid "
                f"by creditor ({int_series})"
            ),
            "url": f"{_IDS_BASE}/{int_series}/counterpart-area/all/time/YR{year}",
            "as_of": str(year),
        },
        rate_reason=EXTERNAL_RATE_ABSENT_REASON,
    )


#: creditor series -> the DECT component it belongs to. Built from the
#: declaration so a row's basis sentence cannot drift from what the gates
#: actually carried.
_COMPONENT_OF_SERIES: Dict[str, DectComponent] = {
    series: component
    for component in DECT_COMPONENTS
    if component.carried
    for series in component.creditor_series
}


def to_loan_rows(
    creditors: List[Creditor],
    year: int,
    interest: Optional[Dict[Tuple[str, str], float]] = None,
    interest_unavailable_reason: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Creditors as loan dicts, in the shape ``national_debt.json`` uses.

    Each row carries its OWN source. The payload these rows are merged into is
    sourced to the CBK/National Treasury bulletin, and the parser reads source
    at payload level, so without this every IDS creditor persisted as though a
    CBK publication had reported it — free text in ``notes`` is not provenance.

    The basis sentence on each row comes from its component's declaration, so
    an IMF row does not claim to be public and publicly guaranteed debt when
    IDS reports it outside that aggregate.
    """
    # DECT, not DPPG: this endpoint lists every creditor the register carries,
    # IMF included. The precise series each row came from is in its notes.
    row_source_url = (
        f"{_IDS_BASE}/{EXTERNAL_TOTAL_SERIES}/counterpart-area/all/time/YR{year}"
    )
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
                "source_evidence": [{**e,
                    "identity": {**e["identity"], "dimensions": {"lender": display, "debt_category": c.debt_category}},
                    "value": str(c.kes),
                    "transformation": {**e["transformation"], "factor": str(c.usd_kes_rate)},
                } for e in c.source_evidence or []],
                "interest_rate": None,
                "interest_terms": _interest_terms_for(
                    c, year, interest, interest_unavailable_reason
                ),
                "issue_date": f"{year}-12-31",
                "maturity_date": None,
                "currency": "KES",
                "notes": (
                    f"World Bank International Debt Statistics {year}, "
                    f"{c.series}, counterpart area {c.counterpart_id} "
                    f"({c.name}). USD {c.usd:,.0f} "
                    f"{rate_provenance(year, c.usd_kes_rate)}. "
                    + _COMPONENT_OF_SERIES[c.series].row_note
                ),
            }
        )
    return rows


def fetch_external_creditors(
    client: SeedingHttpClient,
    settings: Optional[SeedingSettings] = None,
    published_external_kes_for_year: Optional[Callable[[int], Optional[float]]] = None,
) -> Optional[Dict[str, Any]]:
    """The whole pull, gated. ``None`` means nothing may be published.

    ``published_external_kes_for_year`` is resolved AFTER the IDS year is known,
    and must return a figure for that same year. A denominator of a different
    vintage is not a check: CBK's /public-debt/ page is frozen at 2021-12, so
    measuring a 2024 IDS pull against it gives a 1.20x ratio and quarantines
    every pull for a reason that has nothing to do with the data.
    """
    year = latest_year_with_data(client)
    if year is None:
        logger.warning("IDS has no PPG total for any recent year; skipping")
        return None

    # The rate is resolved for the IDS year BEFORE any conversion happens, and
    # its absence quarantines the pull. Falling back to a constant here is the
    # exact defect this replaced: it would be invisible, and wrong on every row.
    usd_kes_rate = usd_kes_rate_for_year(client, year)
    if usd_kes_rate is None:
        logger.warning(
            "IDS creditor pull quarantined: no USD/KES rate for %s, so the "
            "USD figures cannot be converted to shillings",
            year,
        )
        return None

    published_external_kes = (
        published_external_kes_for_year(year)
        if published_external_kes_for_year is not None
        else None
    )
    try:
        creditors, checks = fetch_creditors(client, year, usd_kes_rate)
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

    # Interest paid, same year, same creditors. A separate figure from the
    # stock, so its failure withholds only itself: the register is still
    # right without it, and every row then says why it has no annual cost.
    interest: Optional[Dict[Tuple[str, str], float]] = None
    interest_unavailable_reason: Optional[str] = None
    try:
        interest, interest_checks = fetch_interest_paid(client, year)
        checks["interest"] = interest_checks
    except Exception as exc:  # noqa: BLE001 - recorded on every row, not swallowed
        interest_unavailable_reason = f"{type(exc).__name__}: {exc}"[:200]
        checks["interest"] = {"status": "unavailable", "reason": interest_unavailable_reason}
        logger.warning(
            "IDS %s interest-paid pull refused; external rows publish no "
            "annual cost this run: %s",
            year,
            interest_unavailable_reason,
        )

    return {
        "year": year,
        "source_url": (
            f"{_IDS_BASE}/{EXTERNAL_TOTAL_SERIES}/counterpart-area/all/time/YR{year}"
        ),
        "source_title": (
            f"World Bank International Debt Statistics {year} — Kenya external "
            "debt by creditor"
        ),
        "checks": checks,
        "coverage": coverage,
        "creditors": creditors,
        "loans": to_loan_rows(creditors, year, interest, interest_unavailable_reason),
    }

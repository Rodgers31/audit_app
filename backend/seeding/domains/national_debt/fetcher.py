"""Fetcher for Kenya national-government debt data.

Strategy
--------
1. Load the fixture as the baseline payload — it covers every lender
   we display (multilateral, bilateral, commercial, domestic) with
   reasonable values that move slowly.

2. Overlay World Bank IDS rows on top of the baseline. WB IDS is the
   only machine-readable per-creditor source for Kenya external debt
   (see wb_ids.py for why CBK + Treasury PDF paths were retired).
   Any lender we successfully fetch from WB UPDATES the matching
   fixture row in-place; lenders WB doesn't break out (specific
   bilateral countries) keep their fixture values.

3. Overlay CBK Statistical Bulletin Table 4.1.4 ("Composition of
   Government Gross Domestic Debt by Instrument") on top, when the
   bulletin URL is configured. CBK is the only live source for the
   per-instrument domestic split (T-bills/T-bonds/overdraft). See
   ``cbk_bulletin.py`` for the parsing approach (text-mode regex
   because pdfplumber's table extractor smushes the cells).

Why we dropped the CBK PDF discovery path
-----------------------------------------
The original `_fetch_from_cbk_pdf` scraped
https://www.centralbank.go.ke/public-debt/ for "debt-bulletin"
PDFs. CBK's content reorganization left that page with five PDFs,
none of which are debt bulletins (auction rules, repo agreement,
diaspora remittances, etc.). The CBK Public Debt Statistical
Bulletin moved into the broader CBK Statistical Bulletin under
/releases/statistical-bulletin/ and the published format is now
aggregated by instrument type, not by lender — so even a successful
discovery wouldn't have given us the per-loan rows the original
parser expected. See PR #75 for the full investigation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource
from .cbk_bulletin import fetch_domestic_debt_from_cbk_bulletin
from .cbk_web_tables import check_bond_coverage, fetch_bond_register, partition_ambiguous
from .cbk_web_tables import fetch_public_debt_monthly
from .wb_ids_creditors import fetch_external_creditors
from .wb_ids import fetch_external_debt_from_wb_ids

logger = logging.getLogger("seeding.national_debt.fetcher")


# Domestic bond rows in the loans payload.
#
# Infrastructure and green bonds are Treasury bonds in CBK's own
# classification: they sit INSIDE the Table 4.1.4 "Treasury Bonds" line, and
# the fixture's own note on that row says so ("Includes infrastructure bonds",
# national_debt.json). The payload nonetheless carries a separate KES 300B
# "Domestic Infrastructure & Green Bonds" row, so matching it here added those
# bonds to the denominator a second time — inflating the published bond stock
# by 300B and able to flip the coverage gate's verdict.
#
# Match the inclusive Treasury-bonds aggregate only. Eurobonds are external
# commercial debt and must not appear here either.
_DOMESTIC_BOND_MARKERS = ("treasury bond", "domestic bond")
_NOT_A_DOMESTIC_BOND = ("eurobond", "external", "syndicated", "commercial bank")


# Categories the IDS creditor pull owns outright. When it succeeds, every
# fixture row in these categories is dropped: keeping them beside the real
# creditors would count the same debt twice.
_EXTERNAL_CATEGORIES = {
    "external_multilateral",
    "external_bilateral",
    "external_commercial",
}


def _cbk_published_external_kes(client, settings, year: int) -> float | None:
    """CBK's own external-debt total FOR ``year``, for the IDS coverage gate.

    The denominator must be independent of the thing it checks AND of the same
    vintage. Two sources, in order:

      1. CBK's monthly /public-debt/ table, if it carries that year. Every row
         there must satisfy CBK's own domestic + external = total before the
         parser will emit it.
      2. The CBK Statistical Bulletin series (Table 4.1.3) carried in
         debt_timeline.json, which is where 2022 onwards comes from and which
         cites its table and page per row.

    Returns ``None`` — which quarantines the pull — when neither publishes that
    year. That matters in practice: /public-debt/ is currently frozen at
    2021-12, so measuring a 2024 IDS pull against its newest row gives a 1.20x
    ratio and quarantines every pull for a reason that is about CBK's website,
    not about the data.
    """
    try:
        series = fetch_public_debt_monthly(client, settings)
        rows = [
            r
            for r in (series.get("rows") or [])
            if r.identity_holds() and r.year == year
        ]
        if rows:
            newest = max(rows, key=lambda r: r.month)
            logger.info(
                "IDS coverage denominator: CBK /public-debt/ external "
                "KES %.3fT as of %04d-%02d",
                newest.external_kes / 1e12, newest.year, newest.month,
            )
            return newest.external_kes or None
        logger.info(
            "CBK /public-debt/ does not publish %d (it covers %s); trying the "
            "Statistical Bulletin series",
            year, series.get("covers"),
        )
    except Exception as exc:
        logger.warning("CBK /public-debt/ unavailable: %s", exc)

    try:
        from pathlib import Path
        import json as _json

        path = Path(__file__).resolve().parents[2] / "real_data" / "debt_timeline.json"
        rows = _json.loads(path.read_text(encoding="utf-8")).get("timeline", [])
        match = next((r for r in rows if r.get("year") == year), None)
        if match and match.get("external") and "cbk" in str(match.get("source", "")).lower():
            # The fixture carries billions.
            external = float(match["external"]) * 1e9
            logger.info(
                "IDS coverage denominator: %s — external KES %.3fT for %d",
                match.get("source"), external / 1e12, year,
            )
            return external
    except Exception as exc:
        logger.warning("debt-timeline denominator unavailable: %s", exc)

    logger.warning(
        "No CBK external total published for %d, so the IDS pull has nothing "
        "independent of the same vintage to check against; quarantining", year
    )
    return None


def _replace_external_loans(
    payload: Dict[str, Any], creditor_rows: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Swap every external row for the IDS creditor rows, leaving domestic
    and pending-bill rows untouched."""
    kept = [
        loan
        for loan in payload.get("loans", [])
        if (loan.get("debt_category") or "") not in _EXTERNAL_CATEGORIES
    ]
    return {**payload, "loans": kept + list(creditor_rows)}


def _published_bond_stock_kes(payload: Dict[str, Any]) -> float | None:
    """CBK's own domestic Treasury-bond total from the loans payload.

    The denominator for the register's coverage gate. Read off the payload
    rather than hardcoded, so republishing the bond stock moves it instead of
    silently pushing the gate out of band.
    """
    total = 0.0
    for loan in payload.get("loans", []):
        lender = (loan.get("lender") or "").lower()
        if any(bad in lender for bad in _NOT_A_DOMESTIC_BOND):
            continue
        if any(marker in lender for marker in _DOMESTIC_BOND_MARKERS):
            try:
                total += float(loan.get("outstanding") or loan.get("principal") or 0)
            except (TypeError, ValueError):
                continue
    return total or None


def fetch_debt_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> dict[str, Any]:
    """Return a debt payload combining fixture baseline with live WB IDS."""

    # ── Baseline: fixture ──────────────────────────────────────────
    payload = load_json_resource(
        url=settings.national_debt_dataset_url,
        client=client,
        logger=logger,
        label="national_debt",
    )

    if not settings.live_pdf_fetch_enabled:
        logger.info("Live fetch disabled; using fixture for national debt")
        return payload

    # ── Overlay: World Bank IDS per-creditor external debt ─────────
    try:
        wb_loans = fetch_external_debt_from_wb_ids(client, settings)
    except Exception as exc:
        logger.warning("WB IDS fetch failed entirely: %s", exc)
        wb_loans = []

    if wb_loans:
        before = len(payload.get("loans", []))
        payload = _overlay_loans(payload, wb_loans)
        after = len(payload.get("loans", []))
        logger.info(
            "Merged %d WB IDS rows into national debt payload "
            "(loans: %d → %d)",
            len(wb_loans),
            before,
            after,
        )
        # Surface that we did the overlay so downstream consumers /
        # admin dashboards can show "data freshness: WB IDS YYYY".
        meta = dict(payload.get("metadata", {}))
        meta["wb_ids_overlay_applied"] = True
        meta["wb_ids_overlay_count"] = len(wb_loans)
        payload["metadata"] = meta

    # ── REPLACE: external debt, by individual creditor ─────────────
    # Not an overlay. A successful, gated IDS pull replaces every external
    # fixture row, because the two describe the same debt under different
    # names and appending would double-count it — which is what the lender
    # treemap was withdrawn over.
    #
    # The fixture's external rows are round numbers that overstate the book.
    # Against IDS 2024: Eurobonds 2,276Bn where IDS reports 858Bn (+165%),
    # syndicated banks 400Bn against 120Bn (+234%). It also has no row at all
    # for creditors like the Eastern & Southern African Trade & Development
    # Bank, which lends Kenya USD 1.43bn.
    external_creditors = None
    ids_skip_reason: str | None = None
    try:
        external_creditors = fetch_external_creditors(
            client,
            settings,
            published_external_kes_for_year=lambda yr: _cbk_published_external_kes(
                client, settings, yr
            ),
        )
        if not external_creditors:
            # fetch_external_creditors logs its own reason, but only inside
            # itself. Record one HERE too: on the 2026-09-04 nightly this
            # replacement did not run and left no trace at all in the log or
            # the payload, so there was no way to tell a quarantine from a
            # block that never executed.
            ids_skip_reason = "returned_no_creditors"
    except Exception as exc:
        ids_skip_reason = f"{type(exc).__name__}: {exc}"[:200]
        logger.warning("IDS creditor fetch failed entirely: %s", exc)

    if external_creditors:
        payload = _replace_external_loans(payload, external_creditors["loans"])
        meta = dict(payload.get("metadata", {}))
        meta["ids_creditor_replacement_applied"] = True
        meta["ids_creditor_year"] = external_creditors["year"]
        meta["ids_creditor_count"] = len(external_creditors["creditors"])
        meta["ids_creditor_coverage"] = external_creditors["coverage"]
        payload["metadata"] = meta
        logger.info(
            "Replaced the external fixture rows with %d IDS creditors (%s)",
            len(external_creditors["creditors"]),
            external_creditors["year"],
        )
    else:
        # A silent skip publishes the fixture's external rows, which this
        # module's own comment records as overstating the book (+165% on
        # Eurobonds against IDS). Say so, in the log AND in the payload, so a
        # run that quietly fell back is visible rather than looking healthy.
        meta = dict(payload.get("metadata", {}))
        meta["ids_creditor_replacement_applied"] = False
        meta["ids_creditor_skip_reason"] = ids_skip_reason or "not_attempted"
        payload["metadata"] = meta
        logger.warning(
            "IDS creditor replacement did NOT apply (%s) — external debt is "
            "being served from the fixture, which overstates it",
            ids_skip_reason or "not_attempted",
        )

    # ── Overlay: CBK Statistical Bulletin domestic debt ────────────
    # Disjoint from WB IDS — CBK covers the domestic instruments
    # (T-bills, T-bonds, overdraft) that IDS doesn't publish. Same
    # overlay merge: fixture lender names that match get replaced;
    # new lenders (Advances, Other) get appended.
    try:
        cbk_loans = fetch_domestic_debt_from_cbk_bulletin(client, settings)
    except Exception as exc:
        logger.warning("CBK bulletin fetch failed entirely: %s", exc)
        cbk_loans = []

    if cbk_loans:
        before = len(payload.get("loans", []))
        payload = _overlay_loans(payload, cbk_loans)
        after = len(payload.get("loans", []))
        logger.info(
            "Merged %d CBK bulletin rows into national debt payload "
            "(loans: %d → %d)",
            len(cbk_loans),
            before,
            after,
        )
        meta = dict(payload.get("metadata", {}))
        meta["cbk_bulletin_overlay_applied"] = True
        meta["cbk_bulletin_overlay_count"] = len(cbk_loans)
        payload["metadata"] = meta

    # ── Attach: instrument-level Treasury bond register ────────────
    # NOT an overlay. The register is a list of individual securities with
    # real maturities and coupons; it covers ~74% of CBK's published bond
    # stock, so summing it into the debt total would trade a correct total for
    # a lower wrong one. It rides alongside the loans payload as a maturity
    # and coupon profile, gated on coverage, and carries the ratio so no
    # consumer can mistake it for a stock measure.
    #
    # This is what the withdrawn maturity ladder needed: the loans payload has
    # three rows with a maturity date, and applied one assumed 14.5% coupon to
    # the entire bond book (credibility audit F24/F42).
    bond_register: Dict[str, Any] | None = None
    try:
        register = fetch_bond_register(client, settings)
        # Withhold the ISINs whose maturity this table cannot settle before
        # anything is measured or published. See partition_ambiguous.
        publishable, withheld = partition_ambiguous(register["securities"])
        published_bond_stock = _published_bond_stock_kes(payload)
        coverage = check_bond_coverage(publishable, published_bond_stock)
        if coverage["status"] == "out_of_band":
            logger.warning(
                "Treasury bond register quarantined: %s", coverage["reason"]
            )
        else:
            bond_register = {
                "source_url": register["source_url"],
                "source_title": register["source_title"],
                "retrieved_at": register["retrieved_at"],
                "as_of": register["as_of"],
                "tranche_rows": register["tranche_rows"],
                "coverage": coverage,
                "withheld_isins": withheld,
                "securities": [
                    {
                        "isin": s.isin,
                        "issue_no": s.issue_no,
                        "instrument_type": s.instrument_type,
                        "maturity_date": s.maturity_date.isoformat(),
                        "first_issued": s.first_issued.isoformat(),
                        "coupon_rate": s.coupon_rate,
                        "tenor_years": s.tenor_years,
                        "face_value_kes": s.face_value_kes,
                        "tranches": s.tranches,
                    }
                    for s in publishable
                ],
            }
            logger.info(
                "Treasury bond register: %d redemption lines from %d tranches "
                "(%d ISIN(s) withheld as ambiguous), %.0f%% of the published "
                "bond stock",
                len(bond_register["securities"]),
                register["tranche_rows"],
                len(withheld),
                (coverage["coverage_ratio"] or 0) * 100,
            )
    except Exception as exc:
        logger.warning("Treasury bond register fetch failed: %s", exc)

    if bond_register:
        payload = {**payload, "bond_register": bond_register}

    # Provenance: "live" requires that an authoritative overlay actually
    # landed. A fixture baseline with no overlay is fixture data, however
    # many creditors it lists.
    from ...freshness import mark_fixture, mark_live

    if cbk_loans or wb_loans:
        mark_live(
            "national_debt",
            detail=(
                f"CBK bulletin rows={len(cbk_loans)}, "
                f"WB IDS rows={len(wb_loans)}"
            ),
        )
    else:
        mark_fixture(
            "national_debt",
            reason="no_live_overlay_applied",
            detail="neither the CBK bulletin nor World Bank IDS returned rows",
        )

    return payload


def _overlay_loans(
    payload: Dict[str, Any], overlay: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Replace any baseline loan whose ``lender`` matches an overlay
    row, then append any overlay rows that didn't match. Lender
    matching is case-insensitive + whitespace-collapsed so cosmetic
    drift in the source name doesn't fork rows.
    """

    def _key(loan: Dict[str, Any]) -> str:
        return " ".join((loan.get("lender") or "").lower().split())

    overlay_by_key = {_key(l): l for l in overlay}
    base_loans: List[Dict[str, Any]] = list(payload.get("loans", []))
    out: List[Dict[str, Any]] = []
    matched_keys: set[str] = set()
    for loan in base_loans:
        k = _key(loan)
        if k in overlay_by_key:
            out.append(overlay_by_key[k])
            matched_keys.add(k)
        else:
            out.append(loan)
    # Append overlay rows that didn't match any baseline lender so a
    # newly-tracked WB IDS creditor still lands in the DB.
    for k, loan in overlay_by_key.items():
        if k not in matched_keys:
            out.append(loan)
    return {**payload, "loans": out}


__all__ = ["fetch_debt_payload"]

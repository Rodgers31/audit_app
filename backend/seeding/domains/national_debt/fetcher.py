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
from .wb_ids import fetch_external_debt_from_wb_ids

logger = logging.getLogger("seeding.national_debt.fetcher")


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

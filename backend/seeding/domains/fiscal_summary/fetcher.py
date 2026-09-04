"""Fetcher for fiscal summary data.

Strategy (in order):
1. Try World Bank Indicators API for government expenditure, external debt,
   and debt service data — merge into the existing fixture payload.
2. Fall back to the static fixture / configured URL.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource

logger = logging.getLogger("seeding.fiscal_summary.fetcher")

# ── The budget basis decision (2026-08-29) ───────────────────────────
# "The budget" has three legitimate, DIFFERENT values for FY2025/26:
#
#   COB original gross budget   4.69T  (gross ministerial + CFS)
#   COB original net estimates  4.43T  (excludes Appropriations-in-Aid)
#   Budget Policy Statement     4.19T  (what this fixture used to hold)
#
# The user chose GROSS, for current, future and past data. That decision is
# recorded HERE as the one basis a live figure may be promoted on, and in
# ``real_data/fiscal_summary.json`` as an explicit ``budget_basis`` on every
# row, backfilled from each year's COB report rather than relabelled.
CANONICAL_BUDGET_BASIS = "cob_gross"

# Whether a row that declares NO ``budget_basis`` may receive the live gross
# figure. Still FALSE after the basis decision, and deliberately so.
#
# Choosing gross as the house basis does not make an undeclared row gross;
# it makes an undeclared row a DEFECT. Every row in the shipped fixture now
# declares its basis, so "undeclared" can only mean a row arrived from
# somewhere that did not say what measure it holds — exactly the state in
# which a 4.19T Budget Policy Statement number sat one 12% tolerance away
# from being silently overwritten with a 4.69T gross one. Flipping this to
# True would restore that hazard for every future row while saving nothing:
# opting a row in costs one JSON key.
_ALLOW_UNDECLARED_BASIS = False

# World Bank indicator codes for Kenya
_WB_INDICATORS: Dict[str, str] = {
    "GC.XPN.TOTL.CN": "government_expenditure_lcu",
    "DT.DOD.DECT.CD": "external_debt_stocks_usd",
    "DT.TDS.DECT.CD": "total_debt_service_usd",
    "GC.REV.TOTL.CN": "government_revenue_lcu",
}


def fetch_fiscal_summary_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> dict[str, Any]:
    """Fetch fiscal summary data, enriching fixture with World Bank API data."""
    # Always load the fixture as baseline
    payload = load_json_resource(
        url=settings.fiscal_summary_dataset_url,
        client=client,
        logger=logger,
        label="fiscal_summary",
    )

    wb_applied = False
    wb_years = 0
    cob_status = "not_attempted"
    cob_promoted = False
    estimates_status = "not_attempted"
    estimates_applied = False
    revenue_status = "not_attempted"
    revenue_applied = False

    # Try World Bank enrichment
    if settings.enrich_with_worldbank and settings.live_pdf_fetch_enabled:
        try:
            wb_data = _fetch_worldbank_fiscal_data(client, settings)
            if wb_data:
                payload = _merge_worldbank_data(payload, wb_data)
                wb_applied = True
                wb_years = len(wb_data)
                logger.info(
                    "Enriched fiscal summary with World Bank data",
                    extra={"wb_years": list(wb_data.keys())},
                )
        except Exception as exc:
            logger.warning(
                "World Bank enrichment failed, using fixture only: %s", exc
            )

    # Live COB NG-BIRR headline overlay (recommendation #3): refine the
    # latest-year appropriated_budget from the authoritative Controller-of-
    # Budget report — but only through the plausibility + reconciliation
    # overlay, so the fixture remains the last-known-good fallback whenever the
    # parse is missing, implausible, or far from the known value.
    if settings.live_pdf_fetch_enabled:
        try:
            live_budget, live_revenue, report_fy = _fetch_cob_headlines(
                client, settings
            )
            payload, b_status = _overlay_live_budget_headline(
                payload, live_budget, fiscal_year=report_fy
            )
            payload, r_status = _overlay_live_revenue_headline(
                payload, live_revenue, fiscal_year=report_fy
            )
            cob_promoted = b_status == "promoted"
            cob_status = f"fy={report_fy} budget={b_status} revenue={r_status}"
            logger.info(
                "fiscal_summary COB overlay (%s): budget=%s revenue=%s",
                report_fy,
                b_status,
                r_status,
            )
        except Exception as exc:
            logger.warning("COB headline overlay skipped: %s", exc)

        # Treasury's approved Budget Estimates: the ONLY source that can put
        # a NEW fiscal year on the site. COB publishes at quarter-end + 45
        # days, so between 1 July and mid-November nothing else in this
        # pipeline knows the new year exists.
        #
        # Runs AFTER the COB overlay on purpose. The two never contend: this
        # step creates FY N in July/August from the enacted estimates, and
        # COB's first report on FY N does not exist until mid-November, by
        # which time the row is months old and the overlay writes onto it
        # normally. Ordering it second keeps the cheap, every-night COB
        # refresh ahead of a 29MB download that only misses its 30-day cache
        # once a year. If Treasury were unavailable all along, the COB
        # overlay's ``report_year_not_in_payload`` refusal is the correct
        # outcome — a missing row is not a licence to write the figure
        # somewhere else.
        try:
            estimates, estimates_status = _fetch_budget_estimates(client, settings)
            if estimates is not None:
                payload, apply_status = _apply_budget_estimates(payload, estimates)
                estimates_applied = apply_status in ("created", "updated")
                estimates_status = f"{estimates.fiscal_year}:{apply_status}"
            logger.info(
                "fiscal_summary Treasury budget estimates: %s", estimates_status
            )
        except Exception as exc:
            estimates_status = f"error({type(exc).__name__})"
            logger.warning("Treasury budget estimates step skipped: %s", exc)

        # Revenue for the SAME year, from the Budget Summary. Runs after the
        # budget books so the fiscal year already exists when it lands, and is
        # given the prior year's ordinary revenue off the payload as gate 3's
        # cross-vintage check.
        try:
            target_fy = None
            if estimates is not None:
                target_fy = estimates.fiscal_year
            else:
                rows = payload.get("fiscal_years") or []
                if rows:
                    target_fy = max(r.get("fiscal_year", "") for r in rows) or None
            if target_fy:
                prior_label = _previous_fy(target_fy)
                prior_row = next(
                    (
                        r
                        for r in payload.get("fiscal_years") or []
                        if r.get("fiscal_year") == prior_label
                    ),
                    None,
                )
                revenue_est, revenue_status = _fetch_revenue_estimates(
                    client,
                    settings,
                    target_fy,
                    known_prior_ordinary_billion=(prior_row or {}).get("total_revenue"),
                )
                if revenue_est is not None:
                    payload, rev_apply = _apply_revenue_estimates(payload, revenue_est)
                    revenue_applied = rev_apply == "applied"
                    revenue_status = f"{revenue_est.fiscal_year}:{rev_apply}"
            else:
                revenue_status = "no_target_fiscal_year"
            logger.info(
                "fiscal_summary Treasury revenue estimates: %s", revenue_status
            )
        except Exception as exc:
            revenue_status = f"error({type(exc).__name__})"
            logger.warning("Treasury revenue estimates step skipped: %s", exc)

    # Provenance, graded by WHAT actually moved. "live" is reserved for a run
    # in which a publisher replaced the headline budget; a World-Bank-only run
    # is still live data but says so precisely, because a mode of "live" on
    # its own would overstate what was refreshed.
    from ...freshness import mark_fixture, mark_live

    detail = (
        f"COB overlay: {cob_status}; Treasury estimates: {estimates_status}; "
        f"Treasury revenue: {revenue_status}; World Bank: {wb_years} year(s)"
    )
    if estimates_applied or cob_promoted or revenue_applied:
        # A headline budget figure was actually replaced from a publisher.
        mark_live("fiscal_summary", detail=detail)
    elif wb_applied:
        # World Bank enrichment is genuinely live and does move rows, but it
        # never touches the headline budget — so the DETAIL says plainly that
        # the budget is still the fixture's. "live" on its own would
        # overstate what was refreshed.
        mark_live(
            "fiscal_summary",
            detail=f"World Bank indicators only; headline budget unchanged. {detail}",
        )
    else:
        mark_fixture(
            "fiscal_summary",
            reason="no_live_overlay_applied",
            detail=detail,
        )

    return payload


def _fetch_budget_estimates(
    client: SeedingHttpClient, settings: SeedingSettings
):
    """Discover, download and parse Treasury's approved Budget Estimates.

    Returns ``(BudgetEstimates | None, status)``. Every failure path returns a
    SPECIFIC status slug rather than None-and-a-log-line, because "the site
    still shows last year" is precisely the class of bug that hides behind a
    generic warning.
    """
    import dataclasses
    from pathlib import Path

    from ...discovery import discover_latest_pdf, parse_fiscal_year
    from ...pdf_download import get_or_download_pdf
    from ...source_registry import SOURCE_REGISTRY
    from .budget_estimates import BudgetEstimatesError, extract_budget_estimates

    dataset = SOURCE_REGISTRY["treasury_budget_estimates"]
    page_url = settings.treasury_budget_books_page_url
    try:
        response = client.get(page_url, raise_for_status=True)
    except Exception as exc:
        return None, f"listing_unreachable({type(exc).__name__})"

    found = discover_latest_pdf(
        response.text,
        page_url,
        must_match=("/budget%20books/",) + dataset.match_keywords,
        # Supplementary estimates revise a budget mid-year and are a
        # DIFFERENT measure from the original gross budget COB reports on;
        # "draft" is not a published figure at all (see _is_publishable_doc).
        must_not_match=("supplementary", "supp-", "draft"),
    )
    if found is None:
        return None, "no_budget_book_discovered"

    fiscal_year = parse_fiscal_year(found.url)
    if not fiscal_year:
        return None, "budget_book_has_no_fiscal_year"

    try:
        pdf_path = get_or_download_pdf(
            client,
            found.url,
            cache_dir=Path(settings.cache_path) / "pdfs",
            ttl_seconds=settings.pdf_cache_ttl_seconds,
            max_seconds=settings.pdf_download_timeout_seconds,
            max_bytes=settings.pdf_download_max_bytes,
        )
    except Exception as exc:
        return None, f"download_failed({type(exc).__name__})"

    try:
        estimates = dataclasses.replace(
            extract_budget_estimates(pdf_path, fiscal_year), source_url=found.url
        )
    except BudgetEstimatesError as exc:
        logger.warning(
            "Treasury budget estimates QUARANTINED for %s: %s",
            fiscal_year,
            exc,
        )
        return None, f"quarantined:{exc.reason}"
    logger.info(
        "Treasury %s enacted gross budget: KSh %.1fB (voted %.1fB + CFS "
        "%.1fB). Checks: %s",
        estimates.fiscal_year,
        estimates.gross_budget_billion,
        float(estimates.voted_gross_kes) / 1e9,
        float(estimates.cfs_kes) / 1e9,
        "; ".join(estimates.checks),
    )
    return estimates, "parsed"


def _previous_fy(label: str):
    """``'FY 2026/27'`` -> ``'FY 2025/26'``; None when unparseable."""
    import re as _re

    m = _re.search(r"(\d{4})/(\d{2})", label or "")
    if not m:
        return None
    start = int(m.group(1)) - 1
    return f"FY {start}/{str(start + 1)[-2:]}"


def _fetch_revenue_estimates(
    client, settings, fiscal_year: str, known_prior_ordinary_billion=None
):
    """Discover, download and parse Treasury's Budget Summary for revenue.

    Returns ``(RevenueEstimates | None, status)``. Every failure path returns a
    reason rather than raising, so a bad run leaves the year's revenue absent
    instead of publishing a figure nothing verified.
    """
    from ...discovery import discover_latest_pdf
    from ...pdf_download import get_or_download_pdf
    from .revenue_estimates import RevenueEstimatesError, extract_revenue_estimates

    page_url = settings.treasury_budget_summary_page_url
    try:
        response = client.get(page_url, raise_for_status=True)
    except Exception as exc:
        return None, f"listing_unreachable({type(exc).__name__})"

    found = discover_latest_pdf(
        response.text,
        page_url,
        must_match=("budget", "summary"),
        # A draft is not a published figure, and a supplementary revises the
        # year mid-flight — neither is the approved estimate.
        must_not_match=("draft", "supplementary", "supp-"),
    )
    if found is None:
        return None, "no_budget_summary_discovered"

    try:
        pdf_path = get_or_download_pdf(
            client,
            found.url,
            max_seconds=settings.pdf_download_timeout_seconds,
            max_bytes=settings.pdf_download_max_bytes,
        )
    except Exception as exc:
        return None, f"download_failed({type(exc).__name__})"

    try:
        return (
            extract_revenue_estimates(
                pdf_path,
                fiscal_year,
                known_prior_ordinary_billion=known_prior_ordinary_billion,
                source_url=found.url,
            ),
            "ok",
        )
    except RevenueEstimatesError as exc:
        # Quarantine: the reason is recorded, the figure is not published.
        return None, f"quarantined({exc.reason})"


def _apply_revenue_estimates(payload, estimates):
    """Write a gated revenue estimate onto its fiscal year.

    Unlike ``_overlay_live_revenue_headline`` this may CREATE the year, which
    is the whole reason it exists: an overlay can only mutate a row that is
    already there, so a budget year that has never been seeded gets no revenue
    from the COB path no matter how healthy that path is.

    Pure and idempotent. Returns ``(payload, status)``.
    """
    if estimates is None:
        return payload, "no_estimates"
    fiscal_years = payload.setdefault("fiscal_years", [])
    row = next(
        (r for r in fiscal_years if r.get("fiscal_year") == estimates.fiscal_year), None
    )
    if row is None:
        row = {"fiscal_year": estimates.fiscal_year}
        fiscal_years.append(row)

    declared = row.get("revenue_basis")
    if declared is not None and declared != "ordinary_revenue_excl_aia":
        return payload, f"basis_mismatch(row={declared})"

    row["total_revenue"] = float(estimates.ordinary_revenue_billion)
    row["revenue_basis"] = "ordinary_revenue_excl_aia"
    # The split is NOT derivable from this table — it prints only the
    # ordinary/AiA/total triple — so it stays absent rather than being
    # back-filled from a different column that would contradict the total.
    row["tax_revenue"] = None
    row["non_tax_revenue"] = None
    row["revenue_source"] = {
        "title": "Budget Summary",
        "publisher": "The National Treasury",
        "url": estimates.source_url,
        "page": f"Table 2: Medium-Term Fiscal Framework, PDF p.{estimates.page_refs.get('fiscal_framework')}",
        "column": "Approved Budget",
        "measure": "Ordinary Revenue (tax + non-tax, excluding A-i-A and grants)",
        "total_revenue_incl_aia_billion": float(
            estimates.total_revenue_incl_aia_billion
        ),
        "ministerial_aia_billion": float(estimates.ministerial_aia_billion),
        "checks": list(estimates.checks),
    }
    row["_revenue_source"] = "treasury_budget_summary_live"
    return payload, "applied"


def _apply_budget_estimates(
    payload: Dict[str, Any], estimates
) -> tuple[Dict[str, Any], str]:
    """INSERT (or refresh) the fiscal year the enacted estimates describe.

    This is the one path in the domain that may CREATE a fiscal year. Every
    other overlay mutates ``max(fiscal_years)`` and therefore could never
    move the site onto a new fiscal year, no matter how current its source —
    which is why the homepage still read FY 2025/26 two months into FY
    2026/27.

    Pure and idempotent: re-running with the same estimates rewrites the same
    fields. Returns ``(payload, status)``.
    """
    if estimates is None:
        return payload, "no_estimates"
    fiscal_years = payload.setdefault("fiscal_years", [])
    budget = round(estimates.gross_budget_billion, 1)

    # The plausibility guard runs on the row that would be written, not on
    # the raw figure, so an implausible insert is refused the same way an
    # implausible overlay is.
    candidate = {"fiscal_year": estimates.fiscal_year, "appropriated_budget": budget}
    try:
        from services.trust_guards import check_fiscal_summary

        if check_fiscal_summary(candidate):
            return payload, "failed_plausibility"
    except Exception:  # guard unavailable — the parser's own gates still ran
        pass

    row = next(
        (r for r in fiscal_years if r.get("fiscal_year") == estimates.fiscal_year),
        None,
    )
    created = row is None
    if row is None:
        row = {"fiscal_year": estimates.fiscal_year}
        fiscal_years.append(row)

    declared = row.get("budget_basis")
    if declared is not None and declared != CANONICAL_BUDGET_BASIS:
        return payload, f"basis_mismatch(row={declared},live={CANONICAL_BUDGET_BASIS})"

    row["appropriated_budget"] = budget
    row["budget_basis"] = CANONICAL_BUDGET_BASIS
    # How much of the gross figure is rolling over maturing debt rather than
    # funding new spending. Published only when the book's own interest and
    # redemption sub-totals reconciled to their combined line, so an unproven
    # split never reaches the site. This is what lets the page explain why the
    # gross budget and the enacted headline differ.
    if estimates.debt_redemption_kes is not None:
        row["debt_redemption"] = round(
            float(estimates.debt_redemption_kes) / 1e9, 1
        )
    row["budget_basis_source"] = {
        "title": f"Programme Based Budget {estimates.fiscal_year} (Approved)",
        "publisher": "The National Treasury",
        "url": getattr(estimates, "source_url", None),
        "page": (
            f"voted total PDF p.{estimates.page_refs.get('voted_total')}; "
            f"CFS summary PDF p.{estimates.page_refs.get('cfs_summary')}"
        ),
        "composition": (
            f"gross voted expenditure "
            f"{float(estimates.voted_gross_kes) / 1e9:,.1f}B "
            f"+ Consolidated Fund Services "
            f"{float(estimates.cfs_kes) / 1e9:,.1f}B"
            + (
                f" (of which debt redemption "
                f"{float(estimates.debt_redemption_kes) / 1e9:,.1f}B)"
                if estimates.debt_redemption_kes is not None
                else ""
            )
        ),
        "checks": list(estimates.checks),
    }
    row["_budget_source"] = "treasury_budget_estimates_live"
    fiscal_years.sort(key=lambda r: str(r.get("fiscal_year", "")))
    return payload, ("created" if created else "updated")


def _fetch_cob_headlines(
    client: SeedingHttpClient, settings: SeedingSettings
) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """Discover + download the latest COB NG-BIRR ONCE and extract the headline
    ``(overall_budget, total_revenue, report_fiscal_year)``; money in KSh
    billion. Returns ``(None, None, None)`` on any failure — callers treat that
    as 'no live value' and keep the fixture."""
    import tempfile
    from pathlib import Path

    from ...cob_discovery import discover_latest_cob_pdf_url
    from ..national_budget.fetcher import _NG_BIRR_KEYWORDS
    from ..national_budget.headline import extract_cob_headlines

    resp = client.get(settings.cob_birr_page_url, raise_for_status=True)
    pdf_url = discover_latest_cob_pdf_url(
        resp.text, settings.cob_birr_page_url, keywords=_NG_BIRR_KEYWORDS
    )
    if not pdf_url:
        logger.info("No NG-BIRR PDF found for fiscal_summary headline overlay")
        return None, None, None

    pdf_resp = client.get(pdf_url, raise_for_status=True)
    tmp_path: Optional["Path"] = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="cob_fs_headline_"
        ) as tmp:
            tmp.write(pdf_resp.content)
            tmp_path = Path(tmp.name)
        budget, revenue, report_fy = extract_cob_headlines(tmp_path)
        return (
            float(budget) if budget is not None else None,
            float(revenue) if revenue is not None else None,
            report_fy,
        )
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _target_row(
    payload: Dict[str, Any], fiscal_year: Optional[str]
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """The row an overlay should write to, or ``(None, reason)``.

    When the source document names its own fiscal year, that row is the only
    legitimate target. ``max(fiscal_years)`` is the fallback and is only safe
    while the newest row happens to be the year the publisher just reported
    on — which stopped being true the moment Treasury's enacted FY2026/27
    estimates could be ingested months before COB's first FY2026/27 report.
    An unanchored overlay would then stamp COB's FY2025/26 headline onto the
    FY2026/27 row.
    """
    fiscal_years = payload.get("fiscal_years") or []
    if not fiscal_years:
        return None, "no_fixture"
    if fiscal_year:
        for row in fiscal_years:
            if str(row.get("fiscal_year")) == fiscal_year:
                return row, None
        return None, f"report_year_not_in_payload({fiscal_year})"
    return max(fiscal_years, key=lambda r: str(r.get("fiscal_year", ""))), None


def _overlay_live_budget_headline(
    payload: Dict[str, Any],
    live_budget_billion: Optional[float],
    *,
    tolerance_pct: float = 15.0,
    basis: str = "cob_gross",
    fiscal_year: Optional[str] = None,
) -> tuple[Dict[str, Any], str]:
    """Promote a live-parsed headline budget onto the latest fiscal year ONLY
    if it (a) passes the plausibility gate and (b) reconciles within
    ``tolerance_pct`` of the fixture's last-known value. Otherwise the fixture
    stands. Returns ``(payload, status)`` for logging/tests.

    Safe-by-construction: a missing / implausible / far-off live value is a
    no-op, so a bad COB parse can never replace good data. ``borrowing_pct_of_
    budget`` is left to the parser, which derives it from the (possibly
    overlaid) budget so the share stays consistent.
    """
    if live_budget_billion is None:
        return payload, "no_live_value"
    latest, reason = _target_row(payload, fiscal_year)
    if latest is None:
        return payload, reason or "no_fixture"
    try:
        live = float(live_budget_billion)
    except (TypeError, ValueError):
        return payload, "bad_live_value"
    if live <= 0:
        return payload, "bad_live_value"


    # (a) plausibility gate — substitute the live budget; it must stay
    # internally consistent (in band; spending still ≤ budget).
    try:
        from services.trust_guards import check_fiscal_summary

        if check_fiscal_summary({**latest, "appropriated_budget": live}):
            return payload, "failed_plausibility"
    except Exception:
        pass  # if the guard can't run, fall through to the tolerance check

    # (b) reconciliation — must be near the last-known fixture value.
    fixture_budget = latest.get("appropriated_budget")
    if fixture_budget:
        try:
            fb = float(fixture_budget)
            if fb > 0 and abs(live - fb) > (tolerance_pct / 100.0) * fb:
                return payload, "outside_tolerance"
        except (TypeError, ValueError):
            pass

    # ── Basis gate — LAST, so a more specific verdict wins ────────────
    # Ordering is sanity -> continuity -> identity. An implausible or
    # far-off figure must be reported as such; masking that behind
    # "basis_mismatch" would hide the more serious finding.
    #
    # "The budget" has three legitimate, DIFFERENT values for FY2025/26:
    #   COB original gross budget   4.69T  (includes A-I-A and CFS)
    #   COB original net estimates  4.43T
    #   Budget Policy Statement     4.19T  <- what this fixture holds
    # A numeric tolerance cannot separate a revision from a redefinition:
    # gross sits 12% from the fixture, INSIDE the 15% band, so it would be
    # promoted silently and the homepage headline would move from 4.19T to
    # 4.69T with nobody having chosen that.
    #
    # Promotion therefore requires the row to DECLARE the same basis. The
    # live value is recorded either way, so a refusal is inspectable rather
    # than invisible.
    incoming_basis = str(basis or CANONICAL_BUDGET_BASIS)
    declared_basis = latest.get("budget_basis")
    latest["_cob_live_budget_billion"] = round(live, 1)
    latest["_cob_live_budget_basis"] = incoming_basis
    if incoming_basis != CANONICAL_BUDGET_BASIS:
        # The house basis is gross. A net or BPS figure is a real number
        # from a real document and still must not land in this field.
        return payload, (
            f"basis_not_canonical(live={incoming_basis},"
            f"canonical={CANONICAL_BUDGET_BASIS})"
        )
    if declared_basis is not None and declared_basis != incoming_basis:
        return payload, (
            f"basis_mismatch(row={declared_basis},live={incoming_basis})"
        )
    if declared_basis is None and not _ALLOW_UNDECLARED_BASIS:
        return payload, f"basis_undeclared(live={incoming_basis})"

    latest["appropriated_budget"] = round(live, 1)
    latest["_budget_source"] = "cob_ng_birr_live"
    return payload, "promoted"


def _overlay_live_revenue_headline(
    payload: Dict[str, Any],
    live_revenue_billion: Optional[float],
    *,
    tolerance_pct: float = 15.0,
    fiscal_year: Optional[str] = None,
) -> tuple[Dict[str, Any], str]:
    """Promote a live-parsed TOTAL revenue onto the latest fiscal year ONLY if
    it (a) passes the plausibility gate and (b) reconciles within
    ``tolerance_pct`` of the fixture's last-known value. ``tax_revenue`` and
    ``non_tax_revenue`` are scaled proportionally so the components keep summing
    to the total (otherwise the #1 reconciliation check would reject the row).
    Otherwise the fixture stands. Safe-by-construction: missing / implausible /
    far-off → no-op.
    """
    if live_revenue_billion is None:
        return payload, "no_live_value"
    latest, reason = _target_row(payload, fiscal_year)
    if latest is None:
        return payload, reason or "no_fixture"
    try:
        live = float(live_revenue_billion)
    except (TypeError, ValueError):
        return payload, "bad_live_value"
    if live <= 0:
        return payload, "bad_live_value"

    fixture_total = latest.get("total_revenue")
    # Scale the tax/non-tax split proportionally to the new total so components
    # stay consistent (and the plausibility gate's reconciliation check passes).
    candidate = dict(latest)
    candidate["total_revenue"] = live
    if fixture_total:
        try:
            ratio = live / float(fixture_total)
            if latest.get("tax_revenue") is not None:
                candidate["tax_revenue"] = round(float(latest["tax_revenue"]) * ratio, 1)
            if latest.get("non_tax_revenue") is not None:
                candidate["non_tax_revenue"] = round(
                    float(latest["non_tax_revenue"]) * ratio, 1
                )
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    # (a) plausibility gate on the scaled candidate.
    try:
        from services.trust_guards import check_fiscal_summary

        if check_fiscal_summary(candidate):
            return payload, "failed_plausibility"
    except Exception:
        pass

    # (b) reconciliation — must be near the last-known fixture total.
    if fixture_total:
        try:
            ft = float(fixture_total)
            if ft > 0 and abs(live - ft) > (tolerance_pct / 100.0) * ft:
                return payload, "outside_tolerance"
        except (TypeError, ValueError):
            pass

    latest["total_revenue"] = round(live, 1)
    if "tax_revenue" in candidate:
        latest["tax_revenue"] = candidate["tax_revenue"]
    if "non_tax_revenue" in candidate:
        latest["non_tax_revenue"] = candidate["non_tax_revenue"]
    latest["_revenue_source"] = "cob_ng_birr_live"
    return payload, "promoted"


def _fetch_worldbank_fiscal_data(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Dict[str, Dict[str, float]]:
    """Fetch Kenya fiscal indicators from World Bank API.

    Returns:
        Dict keyed by calendar year (str), each containing indicator values.
        E.g. {"2023": {"government_expenditure_lcu": 3200000000000, ...}}
    """
    base_url = settings.worldbank_api_base_url
    result: Dict[str, Dict[str, float]] = {}

    for indicator_code, field_name in _WB_INDICATORS.items():
        try:
            url = f"{base_url}/country/KEN/indicator/{indicator_code}"
            logger.info("Fetching World Bank indicator %s ...", indicator_code)

            response = client.get(
                url,
                params={
                    "format": "json",
                    "per_page": "20",
                    "date": "2018:2025",
                },
                raise_for_status=False,
            )

            if response.status_code != 200:
                logger.warning(
                    "World Bank API returned %d for %s",
                    response.status_code,
                    indicator_code,
                )
                continue

            data = response.json()
            # World Bank API returns [metadata, records]
            if not isinstance(data, list) or len(data) < 2:
                continue

            records = data[1]
            if not records:
                continue

            for record in records:
                year = record.get("date")
                value = record.get("value")
                if year and value is not None:
                    result.setdefault(str(year), {})[field_name] = float(value)

        except Exception as exc:
            logger.warning(
                "Failed to fetch World Bank indicator %s: %s",
                indicator_code,
                exc,
            )
            continue

    return result


def _calendar_year_to_fy(year: int) -> str:
    """Convert a calendar year to Kenya fiscal year label.

    Kenya FY runs July-June, so calendar year 2023 maps to FY 2022/23
    (the FY that *ends* in June 2023). World Bank annual data for 2023
    best maps to FY 2022/23.
    """
    return f"FY {year - 1}/{str(year)[-2:]}"


def _merge_worldbank_data(
    payload: Dict[str, Any],
    wb_data: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    """Merge World Bank data into the fixture payload.

    Only fills in None/missing fields — never overwrites existing fixture data
    which is more granular (from Treasury BPS).
    """
    fiscal_years: List[Dict[str, Any]] = payload.get("fiscal_years", [])
    fy_lookup = {fy["fiscal_year"]: fy for fy in fiscal_years}

    for cal_year_str, indicators in wb_data.items():
        try:
            cal_year = int(cal_year_str)
        except ValueError:
            continue

        fy_label = _calendar_year_to_fy(cal_year)
        fy_entry = fy_lookup.get(fy_label)

        if fy_entry is None:
            # Create a new fiscal year entry from WB data
            new_entry: Dict[str, Any] = {"fiscal_year": fy_label}

            # Map WB fields to our schema
            exp_lcu = indicators.get("government_expenditure_lcu")
            if exp_lcu:
                # WB data is in LCU (KES), our fixture is in billions
                new_entry["appropriated_budget"] = round(exp_lcu / 1e9, 1)

            rev_lcu = indicators.get("government_revenue_lcu")
            if rev_lcu:
                new_entry["total_revenue"] = round(rev_lcu / 1e9, 1)

            # Debt service in USD — convert at approximate rate
            ds_usd = indicators.get("total_debt_service_usd")
            if ds_usd:
                # Approximate KES/USD (use rough average)
                kes_rate = 130.0  # conservative average for 2018-2025
                new_entry["debt_service_cost"] = round(
                    ds_usd * kes_rate / 1e9, 1
                )

            ext_debt_usd = indicators.get("external_debt_stocks_usd")
            if ext_debt_usd:
                kes_rate = 130.0
                new_entry["actual_debt"] = round(
                    ext_debt_usd * kes_rate / 1e9, 1
                )

            if len(new_entry) > 1:  # has at least one data field
                new_entry["_source"] = "world_bank_api"
                fiscal_years.append(new_entry)
                fy_lookup[fy_label] = new_entry
        else:
            # Only fill gaps in existing entries
            if fy_entry.get("appropriated_budget") is None:
                exp_lcu = indicators.get("government_expenditure_lcu")
                if exp_lcu:
                    fy_entry["appropriated_budget"] = round(exp_lcu / 1e9, 1)

            if fy_entry.get("total_revenue") is None:
                rev_lcu = indicators.get("government_revenue_lcu")
                if rev_lcu:
                    fy_entry["total_revenue"] = round(rev_lcu / 1e9, 1)

    # Sort fiscal years chronologically
    fiscal_years.sort(key=lambda x: x.get("fiscal_year", ""))
    payload["fiscal_years"] = fiscal_years

    return payload

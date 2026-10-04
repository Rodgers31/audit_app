"""Fetch national budget execution payload with live COB PDF integration.

Strategy (in order):
1. If live_pdf_fetch_enabled, discover on COB's NG-BIRR listing (a) the
   newest ANNUAL report — actual expenditure by sector — and (b) the newest
   report of any period — exchequer issues by sector — and parse both.
2. Fall back to the static fixture / configured URL.

National budget execution data comes from the Controller of Budget (COB)
quarterly NG-BIRR reports.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...cob_discovery import discover_latest_cob_pdf_url
from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource
from .sector_expenditure import (
    ALLOCATION_MEASURE,
    EXCHEQUER_MEASURE,
    EXPENDITURE_MEASURE,
)
from ...freshness import (
    mark_fixture,
    mark_live,
    mark_partial,
    record_publisher_edition,
)

logger = logging.getLogger("seeding.national_budget.fetcher")


def fetch_national_budget_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> list[dict[str, Any]]:
    """Fetch national budget execution, trying live COB PDFs first.

    Two live sources, both discovered on the same COB listing page:

    1. **The newest ANNUAL NG-BIRR -> actual expenditure by sector**
       (``sector_expenditure.py``). This is what the /budget execution panel
       publishes. Every row it produces declares ``measure: expenditure`` in
       its provenance; nothing else does.
    2. **The newest report of any period -> Exchequer Issues by sector**
       (``pdf_parser.NgBirrSectoralParser``), for quarterly reports. Skipped
       when the newest report IS the annual one: that report's expenditure
       rows supersede its exchequer proxies on the same period (#241).

    Falls back to the configured fixture only when neither yields anything.
    """
    if not settings.live_pdf_fetch_enabled:
        mark_fixture("national_budget", reason="live_pdf_fetch_disabled")
        return _load_fixture(client, settings)

    page_url = settings.cob_birr_page_url
    try:
        logger.info("Fetching COB NG-BIRR reports page: %s", page_url)
        html = client.get(page_url, raise_for_status=True).text
    except Exception as exc:
        logger.warning("COB NG-BIRR listing unreachable, falling back to fixture: %s", exc)
        mark_fixture(
            "national_budget", reason="live_fetch_failed", detail=str(exc)[:200]
        )
        return _load_fixture(client, settings)

    records: List[Dict[str, Any]] = []

    # ── 1. Annual report -> expenditure by sector ──
    annual = discover_latest_annual_ng_birr(html, page_url)
    annual_status = "no_annual_report_listed"
    if annual is not None:
        # Recorded BEFORE the download/parse, so a failure below still leaves
        # the evidence that COB has an edition we do not hold.
        record_publisher_edition(
            "national_budget",
            dataset=ANNUAL_DATASET,
            edition=annual.fiscal_year,
            url=annual.url,
        )
        try:
            expenditure, annual_status = _fetch_annual_sector_expenditure(
                client, settings, annual
            )
            records.extend(expenditure)
        except Exception as exc:
            logger.warning("Annual NG-BIRR expenditure parse failed: %s", exc)
            annual_status = f"error({type(exc).__name__}: {str(exc)[:120]})"

    # ── 2. Newest report of any period -> exchequer issues ──
    latest_url = _discover_latest_ng_birr_pdf(html, page_url)
    exchequer_status = "no_report_listed"
    if latest_url and annual is not None and latest_url == annual.url:
        exchequer_status = "skipped_newest_is_annual"
    elif latest_url:
        try:
            exchequer = _download_and_parse_ng_pdf(client, latest_url, settings) or []
            exchequer = [r for r in exchequer if "_metadata" not in r]
            records.extend(exchequer)
            exchequer_status = f"{len(exchequer)} rows"
        except Exception as exc:
            logger.warning("COB NG-BIRR exchequer parse failed: %s", exc)
            exchequer_status = f"error({type(exc).__name__})"

    detail = (
        f"annual expenditure: {annual_status}; latest-report exchequer: "
        f"{exchequer_status}"
    )
    logger.info("national_budget live sources — %s", detail)
    if annual_status.startswith("promoted"):
        mark_live("national_budget", detail=detail)
        return records
    if records:
        # Reached COB, but not for the figure the execution panel publishes.
        mark_partial(
            "national_budget",
            reason=f"annual_expenditure_not_promoted({annual_status})",
            detail=detail,
        )
        return records

    mark_fixture("national_budget", reason="parser_returned_nothing", detail=detail)
    return _load_fixture(client, settings)


def _load_fixture(
    client: SeedingHttpClient, settings: SeedingSettings
) -> list[dict[str, Any]]:
    logger.info("Using fixture/configured URL for national budget data")
    payload = load_json_resource(
        url=settings.national_budget_execution_dataset_url,
        client=client,
        logger=logger,
        label="national_budget_execution",
    )

    if not isinstance(payload, list):
        raise ValueError("national_budget_execution payload must be a list")

    # Skip metadata entries (first element may have _metadata key)
    return [r for r in payload if "_metadata" not in r]


# ─────────────────────────────────────────────────────────────────────────
# Annual NG-BIRR -> actual expenditure by sector (#241)
# ─────────────────────────────────────────────────────────────────────────

#: ``ingestion_jobs.meta.publisher_edition.dataset`` for this series.
ANNUAL_DATASET = "cob_ng_birr_annual"

# The measure every execution row declares lives in ``sector_expenditure``
# (EXPENDITURE_MEASURE / ALLOCATION_MEASURE): ``/budget/enhanced`` publishes
# only rows whose provenance says expenditure — never rows it has to guess
# about.

#: Subcategory of a sector's whole-year Total row (both votes combined).
TOTAL_SUBCATEGORY = "Recurrent & Development"

_WPDM_ANCHOR_RE = re.compile(
    r"""href=["'](?P<url>https?://[^"'\s]+/download/(?P<slug>[^/"'\s]+)/?\?"""
    r"""(?:[^"'\s]*&)?wpdmdl=\d+[^"'\s]*)["']""",
    re.IGNORECASE,
)
# "…-review-report-fy-2025-2026", "…-report-for-the-fy-2020-21",
# "…-report-fy-2022-23". The FY must END the slug: quarterly reports carry
# "first-six-months-fy-…", "first-quarter-fy-…" etc. before it.
_ANNUAL_SLUG_RE = re.compile(
    r"national-government-budget-implementation-review-report-"
    r"(?:for-the-)?fy-(?P<y1>(?:19|20)\d{2})-(?P<y2>\d{2,4})$",
    re.IGNORECASE,
)
_SUBPERIOD_WORDS = ("first", "quarter", "months", "half", "six", "nine", "three")


@dataclass(frozen=True)
class AnnualReport:
    url: str
    fiscal_year: str  # "FY 2025/26"
    start_year: int


def discover_latest_annual_ng_birr(html: str, base_url: str) -> Optional[AnnualReport]:
    """The newest ANNUAL NG-BIRR on COB's listing, ranked by the FY its slug
    names — not by upload id, which COB can bump by re-uploading an old
    report, and not by page order."""
    best: Optional[AnnualReport] = None
    for m in _WPDM_ANCHOR_RE.finditer(html or ""):
        slug = m.group("slug").lower()
        if any(w in slug for w in _SUBPERIOD_WORDS):
            continue
        sm = _ANNUAL_SLUG_RE.search(slug)
        if not sm:
            continue
        y1 = int(sm.group("y1"))
        raw = sm.group("y2")
        y2 = int(raw) if len(raw) == 4 else (y1 // 100) * 100 + int(raw)
        if y2 != y1 + 1:
            continue
        report = AnnualReport(
            url=m.group("url"),
            fiscal_year=f"FY {y1}/{str(y1 + 1)[-2:]}",
            start_year=y1,
        )
        if best is None or report.start_year > best.start_year:
            best = report
    if best:
        logger.info("Newest annual NG-BIRR on the listing: %s -> %s", best.fiscal_year, best.url)
    else:
        logger.warning("No annual NG-BIRR found on %s", base_url)
    return best


def _extract_page_texts(pdf_path: Path) -> List[Dict[str, Any]]:
    """Every page's text, 1-based. The slow step (~1 min for a 426-page
    report), and the only one the parse cache may skip — the verification in
    ``sector_expenditure`` runs fresh on every night's text."""
    import pdfplumber

    out: List[Dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            out.append({"page": i, "text": page.extract_text() or ""})
    return out


def report_period(pages: Dict[int, str]) -> Tuple[Optional[str], bool]:
    """``(fiscal_year, is_annual)`` from the cover pages, using the same
    descriptors as the quarterly parser — an annual report names none of
    "FIRST SIX MONTHS", "FIRST QUARTER", …"""
    from .pdf_parser import _PERIOD_DESCRIPTORS

    cover = "\n".join(pages.get(i, "") for i in (1, 2, 3)).upper()
    m = re.search(r"FY\s*(\d{4})\s*[/\-]\s*(\d{2,4})", cover)
    if not m:
        return None, False
    y1 = int(m.group(1))
    fy = f"FY {y1}/{str(y1 + 1)[-2:]}"
    is_annual = not any(d in cover for d, _, _ in _PERIOD_DESCRIPTORS)
    return fy, is_annual


def _fetch_annual_sector_expenditure(
    client: SeedingHttpClient, settings: SeedingSettings, report: AnnualReport
) -> Tuple[List[Dict[str, Any]], str]:
    """Download the annual report, parse and verify its Sector Summaries, and
    return ``(records, status)``. ``status`` starts with ``promoted`` only when
    at least one sector passed verification."""
    import pdfplumber

    from ...parse_cache import parse_with_cache
    from ...pdf_download import get_or_download_pdf
    from .sector_expenditure import parse_sector_expenditure

    cache_dir = Path(settings.cache_path) / "pdfs"
    pdf_path = get_or_download_pdf(
        client,
        report.url,
        cache_dir=cache_dir,
        ttl_seconds=settings.pdf_cache_ttl_seconds,
        max_seconds=settings.pdf_download_timeout_seconds,
        max_bytes=settings.pdf_download_max_bytes,
    )
    page_rows = parse_with_cache(
        pdf_path,
        cache_dir=cache_dir,
        kind="cob_ng_birr_page_text",
        parse_fn=lambda: _extract_page_texts(pdf_path),
        key_extra=f"pdfplumber=={pdfplumber.__version__}",
    )
    pages = {int(r["page"]): str(r["text"]) for r in page_rows}

    fy, is_annual = report_period(pages)
    if fy != report.fiscal_year or not is_annual:
        # The slug said annual FY X; the cover must agree, or we would write
        # one year's expenditure under another year's label.
        return [], (
            f"refused(cover says {fy or 'no FY'}"
            f"{'' if is_annual else ' sub-period'}; listing says {report.fiscal_year})"
        )

    result = parse_sector_expenditure(pages)
    for s in result.sectors:
        logger.info(
            "NG-BIRR %s %s: accepted=%s split=%s total=%s checks=%s problems=%s",
            report.fiscal_year, s.sector, s.accepted, s.split_published,
            s.total.as_dict() if s.total else None, s.checks, s.problems,
        )
    accepted = result.accepted
    if not accepted:
        return [], "no_sector_passed_verification"

    records = build_expenditure_records(result, report)
    from ...pdf_evidence import (
        receipt_for_pdf,
        cell_evidence,
        seal_pdf_observations,
        bind_parse_receipt,
    )

    receipt = receipt_for_pdf(client, settings, pdf_path, report.url, "cob-annual-sector-v1")
    receipt = bind_parse_receipt(receipt, page_rows)
    evidence = []
    for row, sector in zip(records, result.accepted):
        cells = []
        for measure, raw, column in (("allocated_amount", sector.total.gross, "Revised Gross"),
                                     ("actual_spent", sector.total.expenditure, "Expenditure")):
            locator = dict(sector.total_locator, cell=f"Sector Summary / Total / {column}") if sector.total_locator else None
            cells.append(cell_evidence(receipt=receipt, identity={
                "measure": measure, "entity_id": None, "geography": "KEN",
                "period": report.fiscal_year, "unit": "KES", "basis": "actual",
                "dimensions": {"category": row["category"], "subcategory": row["subcategory"], "line_type": None}},
                raw_value=raw, value=row[measure], raw_unit="KES billion", factor="1000000000",
                locator=locator, unit_checked=sector.unit_checked, rounding=0))
        row["provenance_extra"]["source_evidence"] = cells
        evidence.extend(cells)
    seal_pdf_observations(evidence)
    coverage = result.coverage()
    status = (
        f"promoted:{len(accepted)}/{coverage['sectors_expected']} sectors "
        f"{report.fiscal_year}"
    )
    if result.missing:
        status += f" missing={result.missing}"
    if coverage["reconciles"] is False:
        status += " coverage_gap"
    return records, status


def build_expenditure_records(result: Any, report: AnnualReport) -> List[Dict[str, Any]]:
    """One record per verified sector: its whole-year Total, with the evidence
    it was accepted on carried in the row's provenance."""
    from decimal import Decimal

    y1 = report.start_year
    coverage = result.coverage()
    billion = Decimal("1000000000")
    out: List[Dict[str, Any]] = []
    for s in result.accepted:
        split = None
        if s.split_published:
            split = {
                "development": s.development.as_dict(),
                "recurrent": s.recurrent.as_dict(),
            }
        page_ref = f"p.{s.summary_page}" if s.summary_page else None
        out.append(
            {
                "entity_slug": "national-government",
                "entity": "National Government of Kenya",
                "fiscal_year": report.fiscal_year,
                "start_date": f"{y1}-07-01",
                "end_date": f"{y1 + 1}-06-30",
                "category": s.sector,
                "subcategory": TOTAL_SUBCATEGORY,
                "allocated_amount": str((s.total.gross * billion).quantize(Decimal("1"))),
                "actual_spent": str((s.total.expenditure * billion).quantize(Decimal("1"))),
                "committed_amount": None,
                "source": f"CoB NG-BIRR {report.fiscal_year} (annual)",
                "source_url": report.url,
                "data_quality": "official",
                "page_ref": page_ref,
                "notes": (
                    f"{s.table} Sector Summary, {page_ref}: revised gross "
                    f"estimates {s.total.gross} bn, expenditure "
                    f"{s.total.expenditure} bn (Controller of Budget, annual "
                    f"NG-BIRR {report.fiscal_year})."
                ),
                "provenance_extra": {
                    "measure": EXPENDITURE_MEASURE,
                    "allocated_measure": ALLOCATION_MEASURE,
                    "period": "annual",
                    "table": s.table,
                    "summary_page": s.summary_page,
                    "prose_page": s.prose_page,
                    "prose_expenditure_bn": (
                        str(s.prose_expenditure_bn)
                        if s.prose_expenditure_bn is not None
                        else None
                    ),
                    "total": s.total.as_dict(),
                    "checks": s.checks,
                    "split": split,
                    "notes": s.problems or None,
                    "coverage": coverage,
                },
            }
        )
    return out


_NG_BIRR_KEYWORDS = (
    "ng-birr", "national-government-budget",
    "national_government_budget", "birr",
    "budget-implementation", "budget_implementation",
)


def _discover_latest_ng_birr_pdf(
    html: str, base_url: str
) -> Optional[str]:
    """Extract the most recent NG-BIRR PDF URL from the COB page.

    Delegates to the shared COB WPDM discovery helper — see
    ``seeding.cob_discovery`` for why direct ``.pdf`` regex stopped
    matching after COB migrated to the WordPress Download Manager
    plugin.
    """
    return discover_latest_cob_pdf_url(
        html, base_url, keywords=_NG_BIRR_KEYWORDS
    )


def _download_and_parse_ng_pdf(
    client: SeedingHttpClient, pdf_url: str, settings: SeedingSettings
) -> Optional[List[Dict[str, Any]]]:
    """Download a COB NG-BIRR PDF, parse it, return budget execution records.

    Uses ``NgBirrSectoralParser`` which targets Tables 2.5 (Sectoral
    Development) and 2.6 (Sectoral Recurrent) — see
    ``pdf_parser.py`` for why these tables and not the older
    ``CoBQuarterlyReportParser`` (which is anchored on the 47-county
    invariant and only matches the *Consolidated County* BIRR).

    Output dicts feed ``parse_national_budget_payload``, which is why
    they include ``start_date``/``end_date`` (the writer keys
    ``BudgetLine`` on entity+period+category+subcategory).
    """
    try:
        from .pdf_parser import NgBirrSectoralParser
        from ...pdf_download import get_or_download_pdf

        # get_or_download_pdf enforces a TOTAL wall-clock cap on the transfer
        # (not httpx's per-chunk timeout, which a slow-but-steady body never
        # trips) and reuses a cached copy across runs. So a slow-CDN night
        # either reuses the last good download or bails to the fixture,
        # instead of eating the 600s domain budget and aborting mid-parse
        # (issue #119) — same guard the counties_budget domain uses.
        logger.info("Starting COB NG-BIRR PDF download: %s", pdf_url)
        download_start = time.monotonic()
        pdf_path = get_or_download_pdf(
            client,
            pdf_url,
            cache_dir=Path(settings.cache_path) / "pdfs",
            ttl_seconds=settings.pdf_cache_ttl_seconds,
            max_seconds=settings.pdf_download_timeout_seconds,
            max_bytes=settings.pdf_download_max_bytes,
        )
        download_elapsed = time.monotonic() - download_start

        logger.info(
            "COB NG-BIRR PDF ready (%d bytes, %.1fs) at %s",
            pdf_path.stat().st_size, download_elapsed, pdf_path,
        )

        parser = NgBirrSectoralParser(pdf_path)
        period, sectoral_records = parser.parse()

        if not sectoral_records:
            logger.warning("NgBirrSectoralParser returned no records")
            return None

        # Convert to the dict shape parse_national_budget_payload expects.
        # Sector aggregates: net_estimates → allocated, exchequer_issues
        # → actual_spent (proxy: NG-BIRR publishes Exchequer Issues at
        # the sector level, not Expenditure — see pdf_parser.py
        # docstring).
        budget_records: List[Dict[str, Any]] = []
        from ...pdf_evidence import receipt_for_pdf, cell_evidence, seal_pdf_observations
        receipt = receipt_for_pdf(client, settings, pdf_path, pdf_url, "cob-sector-exchequer-v1")
        for r in sectoral_records:
            budget_records.append(
                {
                    "entity_slug": "national-government",
                    "entity": "National Government of Kenya",
                    "fiscal_year": period.label,
                    "start_date": period.start_date.isoformat(),
                    "end_date": period.end_date.isoformat(),
                    "category": r.sector,
                    "subcategory": r.subcategory,
                    "allocated_amount": str(r.net_estimates),
                    "actual_spent": str(r.exchequer_issues),
                    "committed_amount": None,
                    "source": f"CoB NG-BIRR {period.label}",
                    "source_url": pdf_url,
                    "data_quality": "official",
                    # Declared, so no reader has to guess: these are cash
                    # releases against net estimates, not expenditure.
                    "provenance_extra": {
                        "measure": EXCHEQUER_MEASURE,
                        "allocated_measure": "net_estimates",
                        "period": period.label,
                    },
                    "notes": (
                        "Sectoral aggregate from CoB NG-BIRR Tables 2.5 "
                        "(Development) / 2.6 (Recurrent). actual_spent "
                        "is Exchequer Issues — the closest sector-level "
                        "spending proxy CoB publishes."
                    ),
                }
            )
            row = budget_records[-1]
            cells = getattr(r, "source_cells", None) or {}
            evidence = []
            for measure, cell in cells.items():
                evidence.append(cell_evidence(receipt=receipt, identity={
                    "measure": measure, "entity_id": None, "geography": "KEN",
                    "period": period.label, "unit": "KES", "basis": "actual",
                    "dimensions": {"category": r.sector, "subcategory": r.subcategory, "line_type": None}},
                    raw_value=cell["raw_value"], value=row[measure], raw_unit="KES billion", factor="1000000000",
                    locator=cell["locator"], unit_checked=cell["unit_checked"]))
            if evidence:
                row["provenance_extra"]["source_evidence"] = evidence

        seal_pdf_observations([e for row in budget_records for e in row["provenance_extra"].get("source_evidence", [])])

        return budget_records or None

    except ImportError:
        logger.warning(
            "pdfplumber not available — install it for live NG-BIRR parsing"
        )
        return None
    # No temp-file cleanup: get_or_download_pdf() returns a path in the
    # persistent PDF cache (reused across runs), so it must NOT be unlinked.

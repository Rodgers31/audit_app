"""Fetchers for pending bills: national from the BROP, counties from the CoB.

National Government (``fetch_pending_bills_payload``), in order:
1. If live_pdf_fetch_enabled, discover the newest FINAL BROP on Treasury's
   listing (the configured ``treasury_brop_url`` is the fallback), download
   it and read the national pending-bills paragraph (para 18 in 2025, para 20
   in 2026). Its county table is not read: it reprints the Controller of
   Budget's. A run that read an older paper than the publisher has out is
   recorded PARTIAL, not LIVE (``brop_edition_behind``).
2. If pending_bills_dataset_url is configured, load from that
   fixture / API (the writer writes none of it).
3. Otherwise, run the live ETL extractor against COB website.

Counties (``fetch_county_payables_payload``): the trade payables table of the
Controller of Budget's newest full-year County Governments Budget
Implementation Review Report, stated at 30 June (#238).

Why not the COB NG-BIRR
-----------------------
The previous implementation downloaded the COB National Government
BIRR and ran it through ``CoBQuarterlyReportParser``, which is
anchored on the 47-county invariant of the *Consolidated County*
BIRR. The NG-BIRR has neither a 47-county table nor any pending-
bills tables (TOC search confirmed in the FY 2025/26 H1 issue).
On top of that, the fallback formula ``pending = allocated -
absorbed`` was a non-sequitur — that's unspent budget, not unpaid
obligations. Both issues are removed here.
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient

logger = logging.getLogger("seeding.pending_bills.fetcher")

#: What a Treasury Budget Review and Outlook Paper payload declares itself as.
#: ``services.publication_gate.NATIONAL_PENDING_BILLS_PUBLICATION`` is the
#: same string; it is the only publication the National Government's pending
#: bills are read from.
BROP_PUBLICATION = "treasury_brop"
BROP_PUBLISHER = "National Treasury"


@dataclass(frozen=True)
class BropDiscovery:
    """The paper discovery chose, and any newer one it could not match."""

    url: str
    published: date
    #: Non-draft links on the listing that look like a BROP, dated to a later
    #: year than ``url``, but which discovery's match did not accept. Empty
    #: when discovery is keeping up. This is how the 2026 paper looked to the
    #: literal "budget-review-and-outlook-paper" match: there, and invisible.
    newer_unmatched: List[str] = field(default_factory=list)


#: A link that names itself a Budget Review and Outlook Paper in any spelling,
#: for the newer-than-chosen check. Broader than discovery's own match on
#: purpose: it is what discovery would miss.
_BROP_LIKE_RE = re.compile(r"(?:^|-)brop(?:-|$)|budget-review|outlook-paper")


def _today() -> date:
    return date.today()


def _discover_brop(client, settings) -> Optional[BropDiscovery]:
    """Newest FINAL Budget Review and Outlook Paper on Treasury's listing page.

    Returns None on any failure so the caller falls back to the configured
    URL — discovery is an improvement on the hardcoded path, never a new
    single point of failure.
    """
    from ...discovery import (
        discover_latest_pdf,
        find_pdf_links,
        parse_document_date,
        separator_insensitive,
    )

    page_url = getattr(
        settings,
        "treasury_brop_page_url",
        "https://www.treasury.go.ke/budget-review-and-outlook-paper/",
    )
    try:
        response = client.get(page_url, raise_for_status=True)
    except Exception as exc:
        logger.warning("BROP listing unreachable (%s): %s", page_url, exc)
        return None
    # BROP is annual; older than ~2 years means the listing changed shape.
    found = discover_latest_pdf(
        response.text,
        page_url,
        must_match=("budget-review-and-outlook-paper",),
        # Every paper to 2025 was hyphenated ("2025-Budget-Review-and-Outlook-
        # Paper-1.pdf"); the 2026 final is "2026%20Budget%20Review%20and%20
        # Outlook%20Paper....pdf" in a "BROP%20-%20Budget%20Review%20Outlook%20
        # Paper" folder. The literal match could not see it, and the 2025
        # paper stayed "newest" for as long as the listing linked both.
        normalise_separators=True,
        # A DRAFT may not back a published figure. Decided 2026-08-29.
        #
        # Treasury publishes drafts for public comment beside the finals on
        # this very page ("Draft-2022-Budget-Review-and-Outlook-Paper.pdf",
        # "Draft-2023-Budget-Review-and-Outlook-Paper_F.pdf"), and the
        # "Draft 2026 Budget Review and Outlook Paper" is live right now on
        # the Treasury home page alongside a "Public Notice on the Draft
        # 2026 Budget Review and Outlook Paper" inviting comment. Because
        # discovery ranks by parsed date, a draft dated 2026 would outrank
        # the FINAL 2025 paper and start backing the published pending-bills
        # figure — a number the publisher has not yet stood behind, and one
        # that changes between draft and final.
        #
        # Preferring last year's FINAL over this year's DRAFT is the correct
        # trade: the staleness gate reports an ageing BROP loudly, whereas a
        # draft-sourced figure looks exactly like a real one. With
        # normalise_separators, "Draft%202027" and "DRAFT_2027" are refused
        # the same as "Draft-2027".
        must_not_match=("draft",),
        not_before=date.today() - timedelta(days=730),
    )
    if not found:
        return None

    newer: List[str] = []
    for absolute, href in find_pdf_links(response.text, page_url):
        folded = separator_insensitive(absolute)
        if absolute == found.url or "draft" in folded or not _BROP_LIKE_RE.search(folded):
            continue
        published, _how = parse_document_date(href.rsplit("/", 1)[-1])
        if published is None:
            published, _how = parse_document_date(absolute)
        if published is not None and published.year > found.published.year:
            newer.append(absolute)
    return BropDiscovery(found.url, found.published, newer)


#: The day after which a paper stated at 30 June of the same year is overdue.
#: The PFM Act 2012 (s.26) has the Treasury submit the BROP to Cabinet by 30
#: September; the 2025 paper's PDF was created on 8 October 2025 and the 2026
#: paper's on 7 September 2026. On 1 November, last year's paper is late.
_BROP_OVERDUE_AFTER = (10, 31)


def _newest_due_as_at(today: date) -> date:
    """The 30 June whose paper should be out by ``today``."""
    year = today.year if (today.month, today.day) > _BROP_OVERDUE_AFTER else today.year - 1
    return date(year, 6, 30)


def brop_edition_behind(
    as_at: date, discovery: Optional[BropDiscovery], today: date
) -> List[str]:
    """Why the paper read is older than the one the publisher has out, if it is.

    Two independent signs, either enough:

    * the listing links a newer non-draft paper discovery did not match — the
      2026 incident, visible the day the paper appeared;
    * the paper's national figure is stated before the newest 30 June whose
      paper is due — which still fires if the listing loses the link, or the
      listing is unreachable and the configured URL was used.
    """
    reasons: List[str] = []
    if discovery is not None and discovery.newer_unmatched:
        reasons.append(
            f"the listing links a newer paper than the one read "
            f"({discovery.url.rsplit('/', 1)[-1]}): "
            + ", ".join(u.rsplit("/", 1)[-1] for u in discovery.newer_unmatched)
        )
    due = _newest_due_as_at(today)
    if as_at < due:
        reasons.append(
            f"the national figure is stated at {as_at.isoformat()}, but the paper "
            f"stated at {due.isoformat()} was due by {_BROP_OVERDUE_AFTER[1]} "
            f"October {due.year}"
        )
    return reasons


def fetch_pending_bills_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> dict[str, Any]:
    """
    Fetch pending bills data.

    Strategy:
      1. Try live BROP fetch (if enabled + URL configured).
      2. If pending_bills_dataset_url is configured, load fixture/API.
      3. Otherwise, run the live ETL extractor against COB website.
    """
    # Strategy 1: Treasury BROP. ``treasury_brop_url`` ships with the
    # latest known BROP URL as its default and is overridable via
    # ``SEED_TREASURY_BROP_URL`` env var when the next BROP drops; an
    # operator can also explicitly set it to None to fall through to
    # the fixture path (Strategy 2). The ``getattr`` fallback to
    # ``None`` is defensive — older settings instances may not have
    # the field if a stale module is imported.
    brop_url = getattr(settings, "treasury_brop_url", None)
    discovery: Optional[BropDiscovery] = None
    if settings.live_pdf_fetch_enabled:
        # Prefer the CURRENT edition off Treasury's listing page. The
        # configured default is a hardcoded path: it works until the
        # next BROP drops, then silently keeps re-parsing last year's
        # document with nothing to show the data stopped advancing.
        # Discovery is attempted first and the hardcoded value becomes the
        # fallback, not the other way round.
        discovery = _discover_brop(client, settings)
        discovered = discovery.url if discovery else None
        if discovered and discovered != brop_url:
            logger.info(
                "Using DISCOVERED BROP %s (configured default was %s)",
                discovered,
                brop_url,
            )
        brop_url = discovered or brop_url
    if settings.live_pdf_fetch_enabled and brop_url:
        try:
            payload = _fetch_from_treasury_brop(client, brop_url)
            if payload and (
                payload.get("pending_bills") or payload.get("summary")
            ):
                logger.info(
                    "Successfully fetched pending bills from BROP "
                    "(%d records)",
                    len(payload.get("pending_bills") or []),
                )
                from ...freshness import mark_live, mark_partial

                as_at = date.fromisoformat(payload["summary"]["as_at_date"])
                behind = brop_edition_behind(as_at, discovery, _today())
                if behind:
                    # Written all the same — it is the newest paper this run
                    # could read, and a final — but not reported as current.
                    logger.error("BROP edition behind the publisher: %s", "; ".join(behind))
                    mark_partial(
                        "pending_bills",
                        reason="brop_edition_behind",
                        detail="; ".join(behind)[:400],
                    )
                else:
                    mark_live(
                        "pending_bills",
                        detail=(
                            f"Treasury BROP {payload['summary'].get('fiscal_year')}, "
                            f"national stated at {as_at.isoformat()}, "
                            f"{len(payload.get('pending_bills') or [])} records"
                        ),
                    )
                return payload
            logger.warning(
                "BROP fetch returned no pending bills, trying fixture"
            )
        except Exception as exc:
            logger.warning(
                "BROP fetch failed, trying fixture: %s", exc
            )
    elif settings.live_pdf_fetch_enabled:
        logger.info(
            "treasury_brop_url not configured; skipping live BROP fetch"
        )
    from ...freshness import get as _fresh_get
    from ...freshness import mark_fixture

    if _fresh_get("pending_bills").get("mode") != "live":
        mark_fixture("pending_bills", reason="brop_unavailable")

    # Strategy 2: Configured fixture / API URL. Its payload declares no
    # publication, so the writer writes none of it (#238 counties, #265
    # national): a night the BROP is unreachable leaves the published rows as
    # they are, and freshness reports the fallback.
    dataset_url = getattr(settings, "pending_bills_dataset_url", None)
    if dataset_url:
        logger.info("Fetching pending bills from configured URL: %s", dataset_url)
        from ...utils import load_json_resource

        payload = load_json_resource(
            url=dataset_url,
            client=client,
            logger=logger,
            label="pending_bills",
        )
        # Only the BROP path above may declare the BROP. A dataset that says
        # it is one is not believed.
        if isinstance(payload, dict):
            payload.pop("publication", None)
            payload.pop("publisher", None)
        return payload

    # Strategy 3: Live ETL extraction
    logger.info(
        "No pending_bills_dataset_url configured. Running live COB extraction..."
    )
    payload = _run_live_extraction()
    # Not the BROP either, whatever it says about itself.
    if isinstance(payload, dict):
        payload.pop("publication", None)
        payload.pop("publisher", None)
    return payload


def _fetch_from_treasury_brop(
    client: SeedingHttpClient, brop_url: str,
) -> Optional[Dict[str, Any]]:
    """Download the BROP PDF, parse it, return pending bills payload.

    file:// URLs are read from disk so tests and offline runs don't
    require a live HTTP path.
    """
    from .brop_parser import parse_brop_pdf

    logger.info("Downloading Treasury BROP PDF: %s", brop_url)
    tmp_path: Optional[Path] = None
    try:
        if brop_url.startswith("file://"):
            content = Path(brop_url[len("file://"):]).read_bytes()
        else:
            response = client.get(brop_url, raise_for_status=True)
            content = response.content

        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="treasury_brop_"
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        logger.info("Downloaded BROP PDF (%d bytes) to %s", len(content), tmp_path)
        # Counties are not read from the BROP (#238), so its county table is
        # not parsed at all: one this parser cannot read whole must not cost
        # the national paragraph, and with counties off that paragraph is
        # required.
        result = parse_brop_pdf(tmp_path, counties=False)

        return _brop_result_to_payload(result, brop_url)
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _brop_result_to_payload(
    result, brop_url: str,
) -> Dict[str, Any]:
    """Convert a ``BropParseResult`` into the dict shape
    ``parse_pending_bills_payload`` expects.

    Emits:
    * One ``state_corporation`` record for the SOEs aggregate.
    * One ``mda`` record for the MDAs aggregate.
    * A ``summary`` block with the national total.
    """
    pending_bills: List[Dict[str, Any]] = []
    fy_label = result.fiscal_year_label
    source_title = f"Treasury BROP {fy_label}"

    if result.national:
        nb = result.national
        as_at = nb.as_at_date.isoformat()
        # Stamped only when the paragraph printed it — see
        # NationalPendingBills.as_at_stated.
        stated_as_at = as_at if getattr(nb, "as_at_stated", False) else None
        paragraph = getattr(nb, "paragraph", None)
        cited = (
            f"Treasury BROP para {paragraph}" if paragraph
            else "Treasury BROP national pending-bills paragraph"
        )
        pending_bills.append(
            {
                "entity_name": "National Government — State Corporations",
                "entity_type": "national",
                "category": "state_corporation",
                "fiscal_year": fy_label,
                "total_pending": str(nb.state_corporations),
                "as_at": stated_as_at,
                "notes": f"{cited} aggregate as at {as_at}",
            }
        )
        pending_bills.append(
            {
                "entity_name": "National Government — MDAs",
                "entity_type": "national",
                "category": "mda",
                "fiscal_year": fy_label,
                "total_pending": str(nb.mdas),
                "as_at": stated_as_at,
                "notes": f"{cited} aggregate as at {as_at}",
            }
        )

    # No county records. The BROP's county table is a reprint of the
    # Controller of Budget's — Table 10 of the 2025 paper is the CoB's FY
    # 2024/25 table less Narok, Table 11 of the 2026 paper its nine-month
    # table — and counties are read from the CoB's year-end report directly
    # (fetch_county_payables_payload, #238).
    if result.counties:
        logger.info(
            "BROP: %d county row(s) not used — county pending bills are read "
            "from the Controller of Budget's year-end report",
            len(result.counties),
        )

    # Summary aggregates — useful for headline cards and as a
    # fallback if per-row writers drop records.
    summary: Dict[str, Any] = {"fiscal_year": fy_label}
    if result.national:
        summary["total_national"] = str(result.national.total)
        summary["as_at_date"] = result.national.as_at_date.isoformat()

    return {
        "pending_bills": pending_bills,
        "summary": summary,
        "source_url": brop_url,
        "source_title": source_title,
        # Declared here, where it is known, and never inferred downstream from
        # a title or URL. The writer and every reader key on it.
        "publication": BROP_PUBLICATION,
        "publisher": BROP_PUBLISHER,
    }


def _run_live_extraction() -> dict[str, Any]:
    """Run the pending bills ETL extractor against the COB website."""
    try:
        from etl.pending_bills_extractor import PendingBillsExtractor

        extractor = PendingBillsExtractor()
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(extractor.extract_all())
        finally:
            loop.close()

        if not result.get("pending_bills") and not result.get("summary", {}).get(
            "grand_total"
        ):
            logger.warning(
                "Live extraction returned no pending bills data. "
                "The COB reports may require Playwright for PDF download. "
                "Consider setting PLAYWRIGHT_ENABLED=1 and "
                "SEED_PENDING_BILLS_DATASET_URL to a fixture file."
            )
        return result

    except ImportError as exc:
        logger.error(
            "Cannot run live extraction: %s. "
            "Install required packages: pip install pdfplumber httpx beautifulsoup4",
            exc,
        )
        return {
            "pending_bills": [],
            "summary": {},
            "source_url": "https://cob.go.ke/publications/",
            "source_title": "Controller of Budget Reports",
            "extraction_error": str(exc),
        }
    except Exception as exc:
        logger.exception("Live extraction failed: %s", exc)
        return {
            "pending_bills": [],
            "summary": {},
            "source_url": "https://cob.go.ke/publications/",
            "source_title": "Controller of Budget Reports",
            "extraction_error": str(exc),
        }


# --------------------------------------------------------------------------
# counties: the Controller of Budget's year-end report
# --------------------------------------------------------------------------

#: What a county payables payload declares itself as. The same string as
#: ``services.publication_gate.COUNTY_PENDING_BILLS_PUBLICATION``.
COB_YEAR_END_PUBLICATION = "cob_cbirr_year_end"
COB_PUBLISHER = "Office of the Controller of Budget (OCOB)"

#: A county's chapter table and its Table 2.10 row are the same figure printed
#: twice, once in shillings and once in millions to the cent. Below KSh 1m the
#: difference is rounding (Vihiga 0.60m, Migori 0.25m); above it the report
#: disagrees with itself (Uasin Gishu 327.72m, Narok 57.00m) and says so here.
_CHAPTER_NOTE_THRESHOLD_MILLIONS = Decimal("1")

#: A slug that names a sub-period is a quarterly edition. Every full-year
#: edition on the listing names none — "for-the-financial-year-2025-26",
#: "fy-2024-25", "annual-...-fy-2020-21" — and every quarterly one names its
#: part of the year.
_SUB_PERIOD_SLUG_RE = re.compile(r"quarter|half|nine-months|months", re.IGNORECASE)


class CountyPayablesUnavailable(RuntimeError):
    """The year-end county payables could not be read this run."""


def year_end_cbirr_links(html: str) -> List[str]:
    """Full-year county CBIRR download links on a COB listing, newest first.

    Newest by WPDM id, which only ever grows. A quarterly edition is never
    returned: the county page publishes the stock at 30 June only, and the
    parser refuses any table stated at another date as well.
    """
    from ...cob_discovery import _WPDM_RE

    found: Dict[str, int] = {}
    for m in _WPDM_RE.finditer(html or ""):
        url = m.group("url")
        slug = url.lower()
        if "budget-implementation-review" not in slug or "county" not in slug:
            continue
        if _SUB_PERIOD_SLUG_RE.search(slug.split("?")[0]):
            continue
        found[url] = max(found.get(url, 0), int(m.group("id")))
    return [url for url, _id in sorted(found.items(), key=lambda kv: kv[1], reverse=True)]


def _reader_notes(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """What the report says about one county's figure, as note codes."""
    notes: List[Dict[str, Any]] = []
    if entry.get("cob_marked_inconsistent"):
        notes.append({"code": "cob_marked_inconsistent", "table": entry["table"]})
    if not entry.get("assembly_printed"):
        notes.append({"code": "assembly_not_printed", "table": entry["table"]})
    chapter = entry.get("chapter_total_millions")
    total = entry.get("total_millions")
    if chapter is not None and total is not None:
        if abs(Decimal(chapter) - Decimal(total)) >= _CHAPTER_NOTE_THRESHOLD_MILLIONS:
            notes.append(
                {
                    "code": "chapter_table_differs",
                    "table": entry["table"],
                    "chapter_table": entry.get("chapter_table"),
                    "chapter_page": entry.get("chapter_page"),
                    "chapter_total": str(Decimal(chapter) * Decimal(1_000_000)),
                }
            )
    return notes


def county_payables_payload(
    entries: List[Dict[str, Any]], pdf_url: str
) -> Dict[str, Any]:
    """The pending-bills payload for one year-end report's county table.

    One record per county the report states a figure for. A county it does
    not (Nandi at 30 June 2026) or whose row the parser withheld gets none,
    and the writer then stops publishing any older figure for it: absence,
    never last year's number.
    """
    records: List[Dict[str, Any]] = []
    fiscal_year = entries[0]["fiscal_year"] if entries else None
    county_table = {
        "as_at": entries[0]["as_at"] if entries else None,
        "table": entries[0]["table"] if entries else None,
        "not_reported": sorted(
            e["county"] for e in entries if e.get("status") == "not_reported"
        ),
        "withheld": {
            e["county"]: e.get("withheld_reason")
            for e in entries
            if e.get("status") == "withheld"
        },
    }
    for entry in entries:
        if entry.get("status") != "reported":
            logger.info(
                "county payables: no figure for %s (%s%s)",
                entry.get("county"),
                entry.get("status"),
                f": {entry['withheld_reason']}" if entry.get("withheld_reason") else "",
            )
            continue
        total_kes = Decimal(entry["total_millions"]) * Decimal(1_000_000)
        records.append(
            {
                "entity_name": f"{entry['county']} County",
                "entity_type": "county",
                "category": "county",
                "fiscal_year": entry["fiscal_year"],
                "total_pending": str(total_kes),
                "printed_zero": total_kes == 0,
                "as_at": entry["as_at"],
                "table": entry["table"],
                "page": entry["page"],
                "reader_notes": _reader_notes(entry),
                "notes": (
                    f"Controller of Budget CBIRR {entry['fiscal_year']}, "
                    f"{entry['table']} (PDF p.{entry['page']}), trade payables "
                    f"as at {entry['as_at']}"
                ),
            }
        )
    return {
        "pending_bills": records,
        "source_url": pdf_url,
        "source_title": (
            "Controller of Budget — County Governments Budget Implementation "
            f"Review Report, {fiscal_year}"
        ),
        "publication": COB_YEAR_END_PUBLICATION,
        "publisher": COB_PUBLISHER,
        "county_table": county_table,
    }


def fetch_county_payables_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Optional[Dict[str, Any]]:
    """County pending bills from the newest full-year CBIRR.

    Returns None when live PDF fetching is switched off — nothing is read and
    nothing is written, so the published rows stand. Raises
    :class:`CountyPayablesUnavailable` when the report cannot be found, fetched
    or read whole; the caller records it as a failure, because a night that
    publishes no new county figure must not look like one that did.

    Only the NEWEST full-year edition is tried. Falling back to an older one
    on a bad night would republish last year's stock as if it were current.
    """
    if not settings.live_pdf_fetch_enabled:
        logger.info("live_pdf_fetch_enabled is off; county payables not read")
        return None

    from ...parse_cache import parse_with_cache
    from ...pdf_download import get_or_download_pdf
    from ...pdf_parsers import CbirrYearEndPayablesParser
    from ..counties_budget.fetcher import (
        _BROWSER_UA,
        _COB_COUNTY_BIRR_URLS,
        _COB_HTML_HEADERS,
        _pdf_stack_versions,
    )

    links: List[str] = []
    reach_errors: List[str] = []
    for page_url in _COB_COUNTY_BIRR_URLS:
        try:
            response = client.get(
                page_url, raise_for_status=True, headers=_COB_HTML_HEADERS, timeout=60.0
            )
        except Exception as exc:
            reach_errors.append(f"{page_url}: {type(exc).__name__}: {exc}")
            continue
        links = year_end_cbirr_links(response.text)
        if links:
            break
    if not links:
        raise CountyPayablesUnavailable(
            "no full-year county CBIRR link found on the COB listing"
            + (f" ({'; '.join(reach_errors)})" if reach_errors else "")
        )

    pdf_url = links[0]
    logger.info("county payables: reading %s", pdf_url)
    try:
        pdf_path = get_or_download_pdf(
            client,
            pdf_url,
            cache_dir=Path(settings.cache_path) / "pdfs",
            ttl_seconds=settings.pdf_cache_ttl_seconds,
            max_seconds=settings.pdf_download_timeout_seconds,
            max_bytes=settings.pdf_download_max_bytes,
            headers={"User-Agent": _BROWSER_UA, "Accept": "application/pdf,*/*;q=0.8"},
        )
        parser = CbirrYearEndPayablesParser(pdf_path)
        entries = parse_with_cache(
            pdf_path,
            cache_dir=Path(settings.cache_path) / "pdfs",
            kind="cob_cbirr_year_end_payables",
            parse_fn=parser.parse,
            enabled=settings.parse_cache_enabled,
            key_extra=_pdf_stack_versions(),
        )
    except Exception as exc:
        raise CountyPayablesUnavailable(f"{pdf_url}: {type(exc).__name__}: {exc}") from exc

    check_county_payables_entries(entries, pdf_url)
    return county_payables_payload(entries, pdf_url)


def check_county_payables_entries(entries: List[Dict[str, Any]], pdf_url: str) -> None:
    """Refuse a parse the writer must not act on.

    * Not 47 counties.
    * No county stated. The writer would write nothing and retire nothing, so
      last year's rows would stand as current while the run reported success
      (adversarial pass, #238).
    * A table dated for another year than the edition the link names: a
      report that also lists last year's county table must not have it
      republished as this year's.
    """
    if len(entries) != 47:
        raise CountyPayablesUnavailable(
            f"{pdf_url}: parse returned {len(entries)} counties, not 47"
        )
    if not any(e.get("status") == "reported" for e in entries):
        raise CountyPayablesUnavailable(f"{pdf_url}: no county's figure could be read")
    fy = re.findall(r"(20\d{2})-(\d{2})(?!\d)", pdf_url.split("?")[0])
    if fy:
        expected_end = int(fy[-1][0]) + 1
        years = {str(e.get("as_at", ""))[:4] for e in entries}
        if years != {str(expected_end)}:
            raise CountyPayablesUnavailable(
                f"{pdf_url}: the link names FY {fy[-1][0]}/{fy[-1][1]} but the "
                f"county table is stated at {sorted(years)}"
            )

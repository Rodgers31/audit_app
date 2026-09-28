"""Which OAG county audit reports exist, for which fiscal year, of which kind.

WHY THIS EXISTS
---------------
The audits domain used to discover OAG documents through the WordPress media
API, one page of 100 per search term. That API is a dead end. Measured
2026-09-26::

    /wp-json/wp/v2/media?mime_type=application/pdf&search=county&per_page=100
    X-WP-Total: 783  X-WP-TotalPages: 8  -> page 1 returns 2 items, newest 2023-11-25
    /wp-json/wp/v2/media?search=green+book -> X-WP-Total: 6, 0 items returned

So every county report OAG published after November 2023 (FY2021/22 onwards)
was counted by the API and never returned. The nightly logged "5 known + 0
newly discovered" and went green, while every county finding on the site
stayed FY2020/21.

WHERE THE REPORTS ACTUALLY ARE
------------------------------
1. ``/county-executives-assemblies-reports/`` is plain HTML and links one
   page per fiscal year: ``/2024-2025-county-government-audit-reports/``.
2. Each year page links that year's combined volumes directly: one for all 47
   county executives and one for all 47 county assemblies, sometimes a
   summary, and for some years one PDF per county as well.
3. ``/wp-sitemap.xml`` -> ``wp-sitemap-posts-dlp_document-N.xml`` (Document
   Library Pro) enumerates the per-county PDFs and anything the year pages do
   not link. ``dlp_document`` is not exposed by the REST API.

THE FISCAL YEAR COMES FROM THE YEAR PAGE, NOT THE FILENAME
----------------------------------------------------------
``GREEN-BOOK-EXECUTIVES-2024-FINAL-5.3.2025-SIGNED.pdf`` is the FY2023/24
executives volume, and its name contains no fiscal-year span. OAG files it on
``/2023-2024-county-government-audit-reports/``, and that page is the
publisher's own statement of which year it covers. A filename span that
CONTRADICTS the page is a conflict, and the document is left without a year
rather than filed under a guess.

This module does no database work. It is imported by the audits domain and
is meant to be importable by anything else that needs "which OAG county
documents exist" (the stalled-projects corroboration, for one).
"""

from __future__ import annotations

import html as _html
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

logger = logging.getLogger("seeding.oag_discovery")

OAG_ORIGIN = "https://www.oagkenya.go.ke"
LISTING_URL = f"{OAG_ORIGIN}/county-executives-assemblies-reports/"
SITEMAP_INDEX_URL = f"{OAG_ORIGIN}/wp-sitemap.xml"

#: The first fiscal year the nightly ingests. Earlier years are still REPORTED
#: in ``listing_fiscal_years``, so the freshness gate and anyone reading the
#: job metadata can see what OAG publishes, but no document from them is
#: registered or fetched. FY2020/21 is already held, from its combined volumes.
FIRST_INGESTED_FISCAL_YEAR = "2021/2022"

KIND_EXECUTIVES = "executives"
KIND_ASSEMBLIES = "assemblies"
KIND_SUMMARY = "summary"
KIND_SINGLE_ENTITY = "single_entity"
KIND_OTHER = "other"

#: The kinds that carry audit findings for all 47 counties in one PDF.
VOLUME_KINDS = (KIND_EXECUTIVES, KIND_ASSEMBLIES)

FOUND_ON_YEAR_PAGE = "year_page"
FOUND_IN_SITEMAP = "dlp_sitemap"

_OAG_HOSTS = {"oagkenya.go.ke", "www.oagkenya.go.ke", "new01.oagkenya.go.ke"}

#: ``/2024-2025-county-government-audit-reports/`` -> (2024, 2025).
_YEAR_PAGE_RE = re.compile(
    r"/(?P<y1>20\d{2})-(?P<y2>20\d{2})-county-government-audit-reports/?$", re.I
)
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
#: A fiscal-year span in a filename: 2021-2022, 2021_2022, 2021-22.
_FY_SPAN_RE = re.compile(r"(?<!\d)(20\d{2})\s*[/_–-]\s*(20\d{2}|\d{2})(?!\d)")
#: ``/wp-content/uploads/2026/05/`` — the month the file was uploaded.
_UPLOAD_MONTH_RE = re.compile(r"/wp-content/uploads/(20\d{2})/(\d{2})/", re.I)

#: "County-Executive-of-Garissa-2021-2022-.pdf", "COUNTY-ASSEMBLY-OF-ISIOLO",
#: and OAG's own misspelling "County-Assemby-of-Garissa-2021-2022.pdf".
#: Anchored at the START of the name: "Elwak-Municipality-–-County-Government-
#: of-Mandera-2021-2022.pdf" is a municipality's report, not Mandera's.
_SINGLE_ENTITY_RE = re.compile(
    r"^county[-_\s]*(?P<kind>assem(?:bly|by|ly)|executive|government)[-_\s]*of[-_\s]*"
    r"(?P<name>[a-z][a-z'’\-_\s]*?)[-_\s]*(?:20\d{2}|\.pdf$)",
    re.I,
)


@dataclass(frozen=True)
class YearPage:
    fiscal_year: str  # "2024/2025"
    url: str


@dataclass(frozen=True)
class OagDocument:
    """One PDF OAG publishes, as discovered — before anything is downloaded."""

    url: str
    fiscal_year: Optional[str]  # "2024/2025"; None when it cannot be placed
    kind: str  # one of the KIND_* constants
    found_on: str  # FOUND_ON_YEAR_PAGE | FOUND_IN_SITEMAP
    listed_at: str  # the page or sitemap that linked it
    entity: Optional[str] = None  # "Garissa" for a single-entity report
    note: Optional[str] = None  # why fiscal_year is None, when it is

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]

    def as_meta(self) -> dict:
        """The discovery facts, in the shape stored on ``source_documents``."""
        return {
            "fiscal_year": self.fiscal_year,
            "kind": self.kind,
            "found_on": self.found_on,
            "listed_at": self.listed_at,
            "entity": self.entity,
            "note": self.note,
        }


@dataclass
class CountyAuditDiscovery:
    """Everything one discovery pass learned, including what went wrong."""

    #: Every fiscal year the OAG listing links a year page for, oldest first,
    #: INCLUDING years before FIRST_INGESTED_FISCAL_YEAR.
    listing_fiscal_years: List[str] = field(default_factory=list)
    year_pages: List[YearPage] = field(default_factory=list)
    documents: List[OagDocument] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    #: Sitemap entries that looked like county documents but carried no
    #: fiscal year in their name and were not on any year page, so could not
    #: be placed. Counted, not silently dropped.
    sitemap_unplaced: int = 0
    #: Sitemap PDFs whose name mentions a county but which are not a county
    #: government's audit (schools, municipalities, revenue funds). Counted,
    #: not registered.
    sitemap_not_county_audit: int = 0

    def volumes(self) -> List[OagDocument]:
        """Combined volumes, newest fiscal year first, executives first."""
        vols = [
            d
            for d in self.documents
            if d.kind in VOLUME_KINDS and d.fiscal_year is not None
        ]
        return sorted(
            vols,
            key=lambda d: (
                -fy_start(d.fiscal_year),
                VOLUME_KINDS.index(d.kind),
                d.url,
            ),
        )

    def volumes_by_fiscal_year(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for d in self.volumes():
            out.setdefault(d.fiscal_year, []).append(d.url)
        return out

    def as_meta(self) -> dict:
        """What the ingestion job records — read by the freshness gate."""
        return {
            "listing_url": LISTING_URL,
            "listing_fiscal_years": list(self.listing_fiscal_years),
            "volumes_by_fiscal_year": self.volumes_by_fiscal_year(),
            "documents_discovered": len(self.documents),
            "sitemap_unplaced": self.sitemap_unplaced,
            "sitemap_not_county_audit": self.sitemap_not_county_audit,
            "errors": list(self.errors),
        }


# ── pure helpers ─────────────────────────────────────────────────────────
def fy_start(label: str) -> int:
    """``"2024/2025"`` -> 2024."""
    return int(label[:4])


def fiscal_year_label(y1: int, y2: int) -> Optional[str]:
    """``(2024, 2025)`` -> ``"2024/2025"``; None unless the years are consecutive.

    The consecutive check is what stops an upload path (``/uploads/2023/11/``)
    or a strategic-plan span (``2019-2023``) from reading as a fiscal year.
    """
    return f"{y1}/{y2}" if y2 == y1 + 1 else None


def fiscal_years_in_name(name: str) -> frozenset[str]:
    """All distinct valid fiscal-year spans printed in a filename."""
    found = set()
    for m in _FY_SPAN_RE.finditer(name or ""):
        y1 = int(m.group(1))
        raw = m.group(2)
        y2 = int(raw) if len(raw) == 4 else (y1 // 100) * 100 + int(raw)
        label = fiscal_year_label(y1, y2)
        if label:
            found.add(label)
    return frozenset(found)


def fiscal_year_in_name(name: str) -> Optional[str]:
    """The single fiscal year a filename states, or None if absent/ambiguous."""
    found = fiscal_years_in_name(name)
    return next(iter(found)) if len(found) == 1 else None


def upload_month(url: str) -> Optional[Tuple[int, int]]:
    """``(2026, 5)`` for ``/wp-content/uploads/2026/05/...``, else None."""
    m = _UPLOAD_MONTH_RE.search(url or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def normalise_oag_url(href: str, base: str = OAG_ORIGIN) -> Optional[str]:
    """An absolute ``https://www.oagkenya.go.ke/...`` URL, or None if off-site.

    The sitemap writes the same document three ways: relative
    (``/wp-content/uploads/...``), with a ``#new_tab`` fragment, and on a
    retired staging host (``http://new01.oagkenya.go.ke/...``). Left as-is,
    one PDF would register as three documents.
    """
    if not href:
        return None
    href = _html.unescape(href.strip())
    try:
        absolute = urljoin(base, href)
        parts = urlsplit(absolute)
        host = (parts.hostname or "").lower()
    except ValueError:
        # OAG's sitemap really does contain
        # "http://]/wp-content/uploads/2022/02/Muranga-University-...pdf",
        # which urlsplit rejects as an invalid IPv6 host. One malformed entry
        # is one unusable URL. It must not abort the other 5,002.
        return None
    if host not in _OAG_HOSTS:
        return None
    return urlunsplit(("https", "www.oagkenya.go.ke", parts.path, parts.query, ""))


def classify_document(url: str) -> Tuple[str, Optional[str]]:
    """``(kind, entity)`` for a county-audit PDF, from its filename only.

    Order matters. A summary names both executives and assemblies. A
    single-entity report names "County Executive of X", which would otherwise
    read as the executives volume.
    """
    name = (url or "").rsplit("/", 1)[-1]
    low = name.lower()
    if "summary" in low:
        return KIND_SUMMARY, None
    m = _SINGLE_ENTITY_RE.search(name)
    if m:
        entity = re.sub(r"[-_\s]+", " ", m.group("name")).strip().title()
        return KIND_SINGLE_ENTITY, entity or None
    if "executive" in low:
        return KIND_EXECUTIVES, None
    # "ASSEMBLIES", and OAG's own "COUNTY-ASSEMBLES" (FY2021/22 volume 2).
    if re.search(r"assembl", low):
        return KIND_ASSEMBLIES, None
    return KIND_OTHER, None


def _is_pdf(url: str) -> bool:
    return urlsplit(url).path.lower().endswith(".pdf")


def parse_listing(html_text: str, base_url: str = LISTING_URL) -> List[YearPage]:
    """Year pages linked from the county listing, oldest first, de-duplicated."""
    seen: Dict[str, YearPage] = {}
    for href in _HREF_RE.findall(html_text or ""):
        url = normalise_oag_url(href, base_url)
        if not url:
            continue
        m = _YEAR_PAGE_RE.search(urlsplit(url).path)
        if not m:
            continue
        label = fiscal_year_label(int(m.group("y1")), int(m.group("y2")))
        if label and label not in seen:
            # One trailing slash, so the same page is not fetched twice.
            seen[label] = YearPage(label, url if url.endswith("/") else url + "/")
    return sorted(seen.values(), key=lambda p: fy_start(p.fiscal_year))


def parse_year_page(html_text: str, page: YearPage) -> Tuple[List[OagDocument], List[str]]:
    """Every PDF a year page links, filed under the page's fiscal year.

    Returns ``(documents, conflicts)``. A document whose own name states a
    DIFFERENT fiscal year from the page it sits on is kept with
    ``fiscal_year=None`` and a note. Two sources that disagree are not
    resolved by picking one.
    """
    docs: Dict[str, OagDocument] = {}
    conflicts: List[str] = []
    for href in _HREF_RE.findall(html_text or ""):
        url = normalise_oag_url(href, page.url)
        if not url or not _is_pdf(url) or url in docs:
            continue
        kind, entity = classify_document(url)
        named = fiscal_year_in_name(url.rsplit("/", 1)[-1])
        fy: Optional[str] = page.fiscal_year
        note = None
        if named and named != page.fiscal_year:
            fy = None
            note = (
                f"filename says {named}, year page says {page.fiscal_year}"
            )
            conflicts.append(f"{url}: {note}")
        docs[url] = OagDocument(
            url=url,
            fiscal_year=fy,
            kind=kind,
            found_on=FOUND_ON_YEAR_PAGE,
            listed_at=page.url,
            entity=entity,
            note=note,
        )
    return list(docs.values()), conflicts


def parse_sitemap_index(xml_text: str) -> List[str]:
    """The ``dlp_document`` sitemaps named by ``/wp-sitemap.xml``."""
    out = []
    for loc in _LOC_RE.findall(xml_text or ""):
        if "dlp_document" in loc:
            url = normalise_oag_url(loc)
            if url and url not in out:
                out.append(url)
    return out


def parse_sitemap_locs(xml_text: str) -> List[str]:
    return [_html.unescape(loc) for loc in _LOC_RE.findall(xml_text or "")]


def _is_county_document(url: str) -> bool:
    name = url.rsplit("/", 1)[-1].lower()
    return "county" in name or "green-book" in name


def documents_from_sitemap(
    locs: Iterable[str], sitemap_url: str
) -> Tuple[List[OagDocument], int, int]:
    """County audit PDFs the sitemap lists, placed by the fiscal year in their name.

    Returns ``(documents, unplaced, not_county_audit)``. A county PDF with no
    fiscal year in its name cannot be placed from the sitemap alone. It is
    counted in ``unplaced`` and not guessed at. If a year page links it, the
    year page places it instead (see :func:`merge`). A PDF that only
    MENTIONS a county ("Muhoho-High-School-Kiambu-County.pdf") is counted in
    ``not_county_audit`` and not returned.
    """
    docs: Dict[str, OagDocument] = {}
    unplaced = 0
    not_county_audit = 0
    for loc in locs:
        url = normalise_oag_url(loc)
        if not url or not _is_pdf(url) or not _is_county_document(url):
            continue
        if url in docs:
            continue
        kind, entity = classify_document(url)
        if kind == KIND_OTHER:
            not_county_audit += 1
            continue
        fy = fiscal_year_in_name(url.rsplit("/", 1)[-1])
        if fy is None:
            unplaced += 1
        docs[url] = OagDocument(
            url=url,
            fiscal_year=fy,
            kind=kind,
            found_on=FOUND_IN_SITEMAP,
            listed_at=sitemap_url,
            entity=entity,
            note=None if fy else "no fiscal year in the filename",
        )
    return list(docs.values()), unplaced, not_county_audit


def merge(
    year_page_docs: Iterable[OagDocument], sitemap_docs: Iterable[OagDocument]
) -> List[OagDocument]:
    """One entry per URL. The year page wins, since it is where OAG files the document."""
    out: Dict[str, OagDocument] = {}
    for d in year_page_docs:
        out.setdefault(d.url, d)
    for d in sitemap_docs:
        out.setdefault(d.url, d)
    return list(out.values())


def in_ingest_window(doc: OagDocument, first: str = FIRST_INGESTED_FISCAL_YEAR) -> bool:
    return doc.fiscal_year is not None and fy_start(doc.fiscal_year) >= fy_start(first)


# ── the network pass ─────────────────────────────────────────────────────
def discover_county_audit_documents(
    client, *, first_fiscal_year: str = FIRST_INGESTED_FISCAL_YEAR
) -> CountyAuditDiscovery:
    """Listing -> year pages -> documents, then the dlp sitemap.

    Never raises for a network or parse failure. Each one is recorded in
    ``errors``, and the caller decides what an incomplete pass means. An empty
    ``listing_fiscal_years`` means the listing was not read. It must never be
    read as "OAG has published nothing".

    Only documents in or after ``first_fiscal_year`` are returned. The
    listing's full span of years is reported regardless.
    """
    result = CountyAuditDiscovery()

    try:
        listing = client.get(LISTING_URL, raise_for_status=True).text
    except Exception as exc:
        result.errors.append(f"listing unreachable: {type(exc).__name__}: {exc}"[:300])
        listing = ""
    pages = parse_listing(listing)
    if listing and not pages:
        # A 200 that links no year page is not an empty listing. It is a WAF
        # challenge or a redesign, and must not read as "nothing published".
        result.errors.append(
            f"listing returned {len(listing)} bytes but linked no "
            "'<yyyy>-<yyyy>-county-government-audit-reports' page"
        )
    result.year_pages = pages
    result.listing_fiscal_years = [p.fiscal_year for p in pages]

    page_docs: List[OagDocument] = []
    for page in pages:
        if fy_start(page.fiscal_year) < fy_start(first_fiscal_year):
            continue
        try:
            body = client.get(page.url, raise_for_status=True).text
        except Exception as exc:
            result.errors.append(
                f"year page {page.fiscal_year} unreachable: {type(exc).__name__}: {exc}"[:300]
            )
            continue
        docs, conflicts = parse_year_page(body, page)
        if not docs:
            result.errors.append(
                f"year page {page.fiscal_year} linked no PDF ({page.url})"
            )
        result.errors.extend(f"fiscal-year conflict: {c}" for c in conflicts)
        page_docs.extend(docs)

    sitemap_docs: List[OagDocument] = []
    try:
        index = client.get(SITEMAP_INDEX_URL, raise_for_status=True).text
        sitemaps = parse_sitemap_index(index)
        if not sitemaps:
            result.errors.append("sitemap index names no dlp_document sitemap")
        for sm in sitemaps:
            try:
                locs = parse_sitemap_locs(client.get(sm, raise_for_status=True).text)
            except Exception as exc:
                result.errors.append(
                    f"sitemap {sm} unreachable: {type(exc).__name__}: {exc}"[:300]
                )
                continue
            docs, unplaced, other = documents_from_sitemap(locs, sm)
            sitemap_docs.extend(docs)
            result.sitemap_unplaced += unplaced
            result.sitemap_not_county_audit += other
    except Exception as exc:
        result.errors.append(
            f"sitemap index unreachable: {type(exc).__name__}: {exc}"[:300]
        )

    merged = merge(page_docs, sitemap_docs)
    placed_by_page = {d.url for d in page_docs}
    # An unplaced sitemap entry that a year page DID place is not unplaced.
    result.sitemap_unplaced -= sum(
        1 for d in sitemap_docs if d.fiscal_year is None and d.url in placed_by_page
    )
    result.documents = [d for d in merged if in_ingest_window(d, first_fiscal_year)]

    logger.info(
        "OAG county discovery: listing years %s; %d document(s) from %s on; "
        "%d volume(s); %d sitemap entr(ies) unplaced; %d error(s)",
        ", ".join(result.listing_fiscal_years) or "NONE",
        len(result.documents),
        first_fiscal_year,
        len(result.volumes()),
        result.sitemap_unplaced,
        len(result.errors),
    )
    for err in result.errors:
        logger.warning("OAG county discovery: %s", err)
    return result


__all__ = [
    "FIRST_INGESTED_FISCAL_YEAR",
    "FOUND_IN_SITEMAP",
    "FOUND_ON_YEAR_PAGE",
    "KIND_ASSEMBLIES",
    "KIND_EXECUTIVES",
    "KIND_OTHER",
    "KIND_SINGLE_ENTITY",
    "KIND_SUMMARY",
    "LISTING_URL",
    "SITEMAP_INDEX_URL",
    "VOLUME_KINDS",
    "CountyAuditDiscovery",
    "OagDocument",
    "YearPage",
    "classify_document",
    "discover_county_audit_documents",
    "documents_from_sitemap",
    "fiscal_year_in_name",
    "fiscal_year_label",
    "fy_start",
    "in_ingest_window",
    "merge",
    "normalise_oag_url",
    "parse_listing",
    "parse_sitemap_index",
    "parse_sitemap_locs",
    "parse_year_page",
    "upload_month",
]

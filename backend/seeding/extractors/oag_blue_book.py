"""Parser for the OAG consolidated national government report (Blue Book).

Document shape (verified against
``AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf``, 915 pages):

* A table of contents mapping ``<vote> <entity> ..... <printed page>``.
* Printed page numbers as the last text line of each body page; printed
  page 1 begins after the roman-numeral front matter.
* Per-vote chapters headed ``ENTITY NAME - VOTE NNNN`` (the vote number
  sometimes wraps to the next line, or reads ``VOTE - NNNN``).
* Within a chapter: sub-reports (financial statements / lawfulness /
  internal controls), opinion lines (Unmodified/Qualified/Adverse/
  Disclaimer), headings (Basis for …, Emphasis of Matter, Other Matter),
  and numbered finding paragraphs ``N. Title`` with amounts written
  ``Kshs.1,234,567``.

Everything extracted is verbatim report text plus its page number — the
extractor never rewords a finding (kenya-legal: fact-plus-source or it
does not ship).

Severity is mapped from the OAG's own structure, not from keywords:
paragraphs under a Basis for Adverse/Disclaimer heading are CRITICAL,
under Basis for Qualified/Basis for Conclusion are WARNING, and Emphasis
of Matter / Other Matter / Other Information context is INFO.

Text integrity (IMPLEMENTATION_PROMPT A.4): a page whose text is more
than 20% ``(cid:`` glyph codes carries an unmapped font. Such pages are
re-read via OCR when enabled; findings whose text still fails the check
are REJECTED at ingest, never stored (the old pipeline stored the cover
page of this very document as finding 902).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("seeding.extractors.oag_blue_book")

EXTRACTOR_ID = "oag_blue_book"  # recorded on every extractions row
#: The walk's version, stamped on the document beside ``extracted_md5``. Bump
#: it whenever a change to the walk changes what it would extract from bytes
#: it has already read: ``extract_blue_book`` re-reads a document whose stamp
#: differs, and replaces its rows (``replace_extractions``). A document with no
#: stamp was read by version 1.
#:
#: 2: paragraphs past 999, OAG's skipped numbers, prior-year tables, the
#:    appendix rule, and the clean-statement typos (FY2024/25 national book:
#:    813 rows, 329 of them table rows, became 1,882 findings).
#: 3: a standalone historical list after an unrelated finding is withheld
#:    from that finding; a prior-year finding still retains its own table.
EXTRACTOR_VERSION = 3

# ── text integrity ───────────────────────────────────────────────────
_CID_RE = re.compile(r"\(cid:\d+\)")
CID_REJECT_RATIO = 0.20


def cid_ratio(text: str) -> float:
    """Fraction of ``text`` occupied by ``(cid:NN)`` glyph codes."""
    if not text:
        return 0.0
    cid_chars = sum(len(m) for m in _CID_RE.findall(text))
    return cid_chars / len(text)


# ── document grammar ─────────────────────────────────────────────────
_TOC_RE = re.compile(r"^(\d{4})\s+(.+?)\s*\.{3,}\s*(\d+)\s*$")
#: The CONSOLIDATED COUNTY volumes number their entries 1..47 with a period,
#: not by 4-digit vote: "1. County Assembly of Mombasa ......... 1". Without
#: this, parse_toc returned 0 entries for Volume I (469pp, county executives)
#: and Volume II (232pp, county assemblies) — the two documents that carry
#: nearly all county audit data — so they were fetched and never read.
_TOC_COUNTY_RE = re.compile(r"^(\d{1,2})\.\s+(.+?)\s*\.{3,}\s*(\d+)\s*$")
_VOTE_RE = re.compile(r"VOTE\s*[-–]?\s*(\d{4})", re.IGNORECASE)
_SUBREPORT_RE = re.compile(
    r"^REPORT ON (THE FINANCIAL STATEMENTS|LAWFULNESS AND EFFECTIVENESS"
    r"|EFFECTIVENESS OF INTERNAL CONTROLS)",
    re.IGNORECASE,
)
_OPINION_RE = re.compile(
    r"^(Unmodified|Unqualified|Qualified|Adverse|Disclaimer of) Opinion\s*$",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(
    r"^(Basis for (?:Qualified|Adverse|Disclaimer of) Opinion"
    r"|Basis for (?:Qualified |Adverse |Disclaimer of )?Conclusion"
    r"|Emphasis of Matter|Other Matter|Other Information"
    r"|(?:Unqualified |Qualified |Adverse )?Conclusion)\s*$",
    re.IGNORECASE,
)
#: Four digits: OAG numbers the national book's paragraphs continuously
#: across every vote, 1 to 2819 in FY2024/25. It does not restart them per vote.
_FINDING_START_RE = re.compile(r"^(\d{1,4})\.\s+(\S.*)$")
#: OAG skips a number now and then (¶215 and ¶1813 exist nowhere in the
#: FY2024/25 national book). A step this small is a skip. A numbered list
#: inside a finding goes backwards, and a year at the start of a wrapped line
#: ("2019. The supplementary financing ...") lands far from the running number.
MAX_NUMBER_STEP = 3
_AMOUNT_RE = re.compile(r"Kshs?\.?\s*([\d][\d,]*(?:\.\d+)?)", re.IGNORECASE)
# "There were no material issues ...", and OAG's typos of it: "The were no
# material issues" (FY2024/25 p.488), "There were not material issues" (p.624).
_NO_ISSUE_RE = re.compile(
    r"^The(?:re)?\s+(?:was|were)\s+not?\s+material\s+issue", re.IGNORECASE
)
# The header of the table an "Unresolved Prior Year Matters" finding lists last
# year's issues in: "No. Audit Issues for 2023/2024", "No. Audit Issue".
_PRIOR_ISSUES_TABLE_RE = re.compile(r"^No\.?\s+Audit\s+Issues?\b", re.IGNORECASE)
# This is a standalone heading in the FY2024/25 Assemblies volume (PDF p.239),
# after paragraph 645's conclusion. It introduces a separate historical list,
# not paragraph 645's body. A finding about prior-year matters can instead own
# such a list as its evidence.
_PRIOR_ISSUES_LIST_RE = re.compile(
    r"^List of Unresolved Prior[\s\-–—]+Years? Matters:?\s*$", re.IGNORECASE
)
_PRIOR_YEAR_CONTEXT_RE = re.compile(r"\bprior[\s\-–—]+years?\b", re.IGNORECASE)
# Appendices (summary tables of opinions per MDA) follow the last chapter.
# Their numbered table rows are not findings — a chapter ends here. Only the
# HEADING ends it: "APPENDICES", "Appendix A: Unmodified Opinion". Findings
# cite the financial statements' appendices at the start of a line ("Appendix
# III to the financial statements discloses ..."), six times in the FY2024/25
# book, and each of those used to end its chapter there.
_APPENDIX_RE = re.compile(
    r"^(?:APPENDICES\s*$|Appendix\s+[A-Z0-9]{1,5}\s*[:–—-])", re.IGNORECASE
)
# An ALL-CAPS line inside a chapter marks a sub-entity (Consolidated Fund
# Services, donor-funded projects, …). Recorded for provenance fidelity.
_SUBSECTION_RE = re.compile(r"^[A-Z][A-Z0-9 ,'&()/.–-]{11,}$")

# Kenya FY span in the source URL/filename: "…-2024-2025.pdf"
_FY_SPAN_RE = re.compile(r"(20\d{2})\s*[/_–-]\s*(20\d{2}|\d{2})")


@dataclass
class PageText:
    page_number: int  # 1-based PDF page number
    text: str
    method: str  # "pdfplumber" | "ocr" | "rejected"


@dataclass
class BlueBookFinding:
    vote: int
    entity_name: str  # from the TOC — the authoritative name
    paragraph_no: int
    title: str
    finding_text: str  # verbatim paragraph, title included
    pdf_page: int  # 1-based page where the paragraph starts
    printed_page: int
    subreport: Optional[str]
    opinion: Optional[str]
    heading: Optional[str]
    sub_section: Optional[str]
    amounts: List[float] = field(default_factory=list)
    method: str = "pdfplumber"


@dataclass
class BlueBookResult:
    fiscal_year_label: Optional[str]  # "2024/2025"
    findings: List[BlueBookFinding]
    votes_seen: int
    rejected_cid: int  # findings rejected for failing text integrity
    ocr_pages: int
    skipped_votes: List[int] = field(default_factory=list)


# ── severity mapping (OAG structure -> app enum) ─────────────────────
def severity_for(heading: Optional[str], opinion: Optional[str]) -> str:
    h = (heading or "").lower()
    o = (opinion or "").lower()
    if "adverse" in h or "disclaimer" in h or "adverse" in o or "disclaimer" in o:
        return "CRITICAL"
    if h.startswith("basis for"):
        return "WARNING"
    return "INFO"


# ── pure parsing over page text ──────────────────────────────────────
def parse_toc(pages: List[PageText]) -> List[Tuple[int, str, int]]:
    """(code, entity, printed_page) from the TOC pages (front matter).

    ``code`` is the 4-digit vote in a national Blue Book and the 1..47
    sequence number in a consolidated county volume.

    The two forms are tried in ORDER, not together: a national book's front
    matter can contain short numbered lists ("1. Introduction ..... 3") that
    the county pattern would happily match, so the county form is only
    consulted when the vote form found nothing. That keeps a document with
    real votes from picking up front-matter noise as entities.
    """

    def scan(pattern) -> List[Tuple[int, str, int]]:
        out: List[Tuple[int, str, int]] = []
        for page in pages[:12]:  # TOC lives in the front matter
            for line in page.text.split("\n"):
                m = pattern.match(line.strip())
                if m:
                    out.append(
                        (int(m.group(1)), m.group(2).strip(), int(m.group(3)))
                    )
        return out

    return scan(_TOC_RE) or scan(_TOC_COUNTY_RE)


def find_offset(pages: List[PageText]) -> Optional[int]:
    """0-based index of the page whose printed page number is 1."""
    for i, page in enumerate(pages[:40]):
        lines = [l.strip() for l in page.text.split("\n") if l.strip()]
        if lines and lines[-1] == "1":
            return i
    return None


def fiscal_year_from_url(url: str) -> Optional[str]:
    for m in _FY_SPAN_RE.finditer(url or ""):
        y1 = int(m.group(1))
        y2_raw = m.group(2)
        y2 = int(y2_raw) if len(y2_raw) == 4 else (y1 // 100) * 100 + int(y2_raw)
        if y2 == y1 + 1:
            return f"{y1}/{y2}"
    return None


def _entity_in_head(entity: str, head: str) -> bool:
    """Is ``entity`` the heading of this page?

    Compared on letters only, because the TOC and the chapter heading differ
    in case, spacing and punctuation ("County Assembly of Nairobi City" vs
    "COUNTY ASSEMBLY OF NAIROBI CITY"). Requires the WHOLE entity name, so
    "County Assembly of Kilifi" cannot confirm a chapter headed
    "County Assembly of Kisumu".
    """
    norm = lambda t: re.sub(r"[^a-z]", "", (t or "").lower())
    needle, hay = norm(entity), norm(head)
    return bool(needle) and needle in hay


def segment_chapter(
    pages: List[PageText],
    vote: int,
    entity_name: str,
    start_printed: int,
    end_printed: int,
    offset: int,
    *,
    finding_start_re=None,
    stop_at_appendix: bool = True,
    max_number_step: int = MAX_NUMBER_STEP,
    skip_prior_issue_tables: bool = True,
) -> Tuple[List[BlueBookFinding], int]:
    """Findings for one vote's chapter. Returns (findings, rejected_cid).

    The defaults are the national walk. Each was measured on the FY2024/25
    national book (document 2392), whose 813 rows under the old defaults
    became 1,882 (every paragraph number 1-2818 accounted for: 1,882 findings,
    933 "no material issues" statements, ¶215 and ¶1813 absent from the PDF,
    and one wrapped prose line that is correctly not a paragraph). The
    FY2020/21 county volumes the same walk reads (documents 2395 and 2396)
    come out byte-identical under both.

    * ``finding_start_re``: up to four digits. OAG numbers paragraphs
      continuously across the whole book, to 2819. The three-digit pattern
      stopped at 999 (pdf p.312), after which the only numbered lines it could
      match were the 1, 2, 3 rows of prior-year tables: 329 of the 813 rows.
    * ``max_number_step``: OAG skips numbers. ¶1813 does not exist, and the
      strict ``prev + 1`` rule lost the rest of vote 1152 (51 findings). A
      numbered list inside a finding goes backwards, and a year opening a
      wrapped line ("2019. The supplementary ...") lands hundreds away from
      the running number, so neither passes. The four such lines in the year
      band 1990-2100 are all refused, and its 83 real paragraphs kept.
    * ``stop_at_appendix``: the end matter ("APPENDICES", "Appendix A:
      Unmodified Opinion") falls inside the LAST vote's page range, so the
      national walk still stops there. ``_APPENDIX_RE`` matches only that
      heading, not a finding that opens a line with "Appendix III to the
      financial statements ...". The county volumes turn it off: their
      chapter ends are fixed by the next chapter's heading.
    * ``skip_prior_issue_tables``: an "Unresolved Prior Year Matters" finding
      lists last year's issues as a table numbered 1, 2, 3 under a
      "No. Audit Issues for ..." header. Where the running paragraph numbers
      are low, those rows pass the continuity rule as body-less "findings",
      and the real findings after them then look like steps backwards and are
      dropped (FY2024/25 assemblies, Mombasa, p.14). With this on, numbered
      lines continuing the table's own 1, 2, 3 sequence stay in the prior-year
      finding's body. A separate "List of Unresolved Prior Years Matters"
      heading after an unrelated finding instead ends that finding and
      withholds the historical table. A structural heading resumes the walk;
      an unmarked low number is withheld because it could still be a row.
      This guards the low-numbered chapters where continuity alone cannot
      tell a table row from a paragraph.
    """
    finding_start_re = finding_start_re or _FINDING_START_RE
    lines: List[Tuple[int, str, str]] = []  # (pdf_page_1based, line, method)
    for printed in range(start_printed, end_printed + 1):
        idx = offset + printed - 1
        if idx >= len(pages):
            break
        page = pages[idx]
        if page.method == "rejected":
            continue
        page_lines = page.text.split("\n")
        if page_lines and page_lines[-1].strip().isdigit():
            page_lines = page_lines[:-1]  # printed page number footer
        for l in page_lines:
            lines.append((idx + 1, l.strip(), page.method))

    # The table title can wrap even when the body extraction is otherwise
    # readable. Join only the two lines that form this exact structural title.
    joined_lines = []
    position = 0
    while position < len(lines):
        page, line, method = lines[position]
        if position + 1 < len(lines):
            candidate = f"{line} {lines[position + 1][1]}"
            if _PRIOR_ISSUES_LIST_RE.fullmatch(candidate):
                joined_lines.append((page, candidate, method))
                position += 2
                continue
        joined_lines.append((page, line, method))
        position += 1
    lines = joined_lines

    findings: List[BlueBookFinding] = []
    rejected = 0
    subreport: Optional[str] = None
    opinion: Optional[str] = None
    heading: Optional[str] = None
    sub_section: Optional[str] = None
    cur: Optional[dict] = None
    prev_no: Optional[int] = None
    table_next: Optional[int] = None  # next row number while inside a table
    detached_prior_list = False  # historical document scope, not a finding
    detached_rows = 0
    detached_max_row = 0

    def flush() -> None:
        nonlocal cur, rejected
        if cur is None:
            return
        body = " ".join(cur["lines"]).strip()
        cur_out, cur = cur, None
        if _NO_ISSUE_RE.match(cur_out["title"]):
            return  # a clean statement, not a finding
        if cid_ratio(body) > CID_REJECT_RATIO:
            rejected += 1
            logger.warning(
                "REJECTED finding (text integrity: %.0f%% cid) vote %s para %s p.%s",
                cid_ratio(body) * 100,
                vote,
                cur_out["no"],
                cur_out["page"],
            )
            return
        amounts: List[float] = []
        for raw in _AMOUNT_RE.findall(body):
            try:
                amounts.append(float(raw.replace(",", "")))
            except ValueError:
                pass
        findings.append(
            BlueBookFinding(
                vote=vote,
                entity_name=entity_name,
                paragraph_no=cur_out["no"],
                title=cur_out["title"],
                finding_text=body,
                pdf_page=cur_out["page"],
                printed_page=cur_out["page"] - offset,
                subreport=subreport_of(cur_out),
                opinion=cur_out["opinion"],
                heading=cur_out["heading"],
                sub_section=cur_out["sub_section"],
                amounts=amounts,
                method=cur_out["method"],
            )
        )

    def subreport_of(c: dict) -> Optional[str]:
        return c["subreport"]

    for pdf_page, line, method in lines:
        if not line:
            continue
        if skip_prior_issue_tables and _PRIOR_ISSUES_LIST_RE.fullmatch(line):
            if cur is None or not _PRIOR_YEAR_CONTEXT_RE.search(cur["title"]):
                flush()
                table_next = None
                detached_prior_list = True
                detached_rows = 0
                detached_max_row = 0
                sub_section = None
                continue
        if detached_prior_list:
            # Page breaks, repeated year headers and wrapped rows stay in the
            # historical list. A report/section heading resumes the walk.
            # Without one, a paragraph may resume only after at least one
            # historical row, when its number continues the chapter sequence
            # and is well beyond every row number seen in the list. Close
            # numbers remain ambiguous and are withheld rather than fabricated.
            row = finding_start_re.match(line)
            structural = (
                _SUBREPORT_RE.match(line)
                or _OPINION_RE.match(line)
                or _HEADING_RE.match(line)
                or (stop_at_appendix and _APPENDIX_RE.match(line))
            )
            resumes_numbering = (
                row is not None
                and detached_rows > 0
                and prev_no is not None
                and prev_no < int(row.group(1)) <= prev_no + max_number_step
                and int(row.group(1)) > detached_max_row + max_number_step
                and prev_no - detached_max_row > max(20, 10 * max_number_step)
            )
            if not structural and not resumes_numbering:
                if row is not None:
                    detached_rows += 1
                    detached_max_row = max(detached_max_row, int(row.group(1)))
                continue
            detached_prior_list = False
        if skip_prior_issue_tables and cur is not None:
            if _PRIOR_ISSUES_TABLE_RE.match(line):
                table_next = 1
                cur["lines"].append(line)
                continue
            if table_next is not None:
                row = _FINDING_START_RE.match(line) or finding_start_re.match(line)
                if row and int(row.group(1)) == table_next:
                    table_next += 1
                    cur["lines"].append(line)
                    continue
                structural = (
                    row
                    or _HEADING_RE.match(line)
                    or _SUBREPORT_RE.match(line)
                    or _OPINION_RE.match(line)
                )
                if not structural:
                    # A row that wrapped onto a second line. Still the table.
                    cur["lines"].append(line)
                    continue
                table_next = None
        if stop_at_appendix and _APPENDIX_RE.match(line):
            break  # appendix tables are not findings
        if _SUBREPORT_RE.match(line):
            flush()
            subreport, opinion, heading = line, None, None
            continue
        if _OPINION_RE.match(line):
            flush()
            opinion = line
            continue
        if _HEADING_RE.match(line):
            flush()
            heading = line
            continue
        m = finding_start_re.match(line)
        if m:
            no = int(m.group(1))
            title = m.group(2).strip()
            # Paragraph numbering is continuous within a chapter. Accepting
            # only prev+1 (or the very first number seen) rejects numbered
            # list items inside a finding body masquerading as findings.
            is_next = prev_no is not None and prev_no < no <= prev_no + max_number_step
            is_first = prev_no is None
            if (is_next or is_first) and title and not title[0].islower():
                flush()
                cur = {
                    "no": no,
                    "title": title,
                    "page": pdf_page,
                    "opinion": opinion,
                    "heading": heading,
                    "subreport": subreport,
                    "sub_section": sub_section,
                    "lines": [title],
                    "method": method,
                }
                prev_no = no
                continue
        if cur is not None:
            if _SUBSECTION_RE.match(line) and len(line.split()) >= 3:
                flush()
                sub_section = line
                continue
            cur["lines"].append(line)
            if method == "ocr":
                cur["method"] = "ocr"
        elif _SUBSECTION_RE.match(line) and len(line.split()) >= 3:
            sub_section = line

    flush()
    return findings, rejected


def parse_blue_book(pages: List[PageText], source_url: str) -> BlueBookResult:
    """Pure parse of a whole Blue Book given per-page text."""
    toc = parse_toc(pages)
    offset = find_offset(pages)
    fy = fiscal_year_from_url(source_url)
    if not toc or offset is None:
        logger.warning(
            "Blue Book structure not recognised (toc=%d entries, offset=%s) — "
            "extracting nothing rather than guessing",
            len(toc),
            offset,
        )
        return BlueBookResult(fy, [], 0, 0, 0)

    # Chapter page ranges: this entry's printed start to the next entry's
    # start - 1 (TOC order is document order).
    all_findings: List[BlueBookFinding] = []
    rejected = 0
    skipped_votes = []
    last_printed = len(pages) - offset
    for i, (vote, entity, start_printed) in enumerate(toc):
        end_printed = (
            toc[i + 1][2] - 1 if i + 1 < len(toc) else last_printed
        )
        # Verify the chapter really starts where the TOC says: the vote
        # number must appear in the first lines of the start page.
        idx = offset + start_printed - 1
        if idx >= len(pages):
            skipped_votes.append(vote)
            continue
        head = "\n".join(pages[idx].text.split("\n")[:3])
        m = _VOTE_RE.search(head)
        confirmed = bool(m) and int(m.group(1)) == vote
        if not confirmed:
            # Consolidated COUNTY volumes carry no VOTE-nnnn header at all
            # (0 of 232 pages in Volume II) — the chapter is headed by the
            # entity name instead. Confirm on that, so the check still proves
            # the chapter is the one the TOC promised rather than being
            # skipped for lacking a marker this document class never has.
            confirmed = _entity_in_head(entity, head)
        if not confirmed:
            skipped_votes.append(vote)
            logger.warning(
                "TOC says vote %s starts on printed page %s but the page "
                "header does not confirm it — skipping this chapter rather "
                "than mis-attributing findings",
                vote,
                start_printed,
            )
            continue
        findings, rej = segment_chapter(
            pages, vote, entity, start_printed, end_printed, offset
        )
        all_findings.extend(findings)
        rejected += rej

    ocr_pages = sum(1 for p in pages if p.method == "ocr")
    return BlueBookResult(fy, all_findings, len(toc), rejected, ocr_pages, skipped_votes)


# ── PDF I/O (thin, impure shell around the pure parser) ──────────────
def read_pages(
    pdf_path: Path,
    *,
    ocr_enabled: bool,
    ocr_max_pages: int = 30,
    visible_only: bool = False,
) -> List[PageText]:
    """Per-page text with OCR fallback for unmappable-font pages.

    A page whose embedded text is empty or >20% ``(cid:`` is re-read via
    OCR (pdf2image + pytesseract) when enabled; if it still fails the
    integrity check it is marked ``rejected`` and contributes nothing.

    ``visible_only`` drops glyphs drawn outside the page's box before reading.
    The FY2021/22 county volumes carry the PREVIOUS page's entire text
    positioned off-canvas (x from -523) on every odd page from 17 onward: 262
    of 546 pages in volume 1. pdfplumber reads invisible glyphs like any
    others, so each such page came back as two pages' text interleaved, with a
    "2 3" footer. Off by default, so the national Blue Book reads exactly as
    before.
    """
    import pdfplumber

    pages: List[PageText] = []
    ocr_used = 0
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            source = page.within_bbox(page.bbox) if visible_only else page
            text = source.extract_text() or ""
            method = "pdfplumber"
            if not text.strip() or cid_ratio(text) > CID_REJECT_RATIO:
                if ocr_enabled and ocr_used < ocr_max_pages:
                    ocr_text = _ocr_page(pdf_path, i + 1)
                    ocr_used += 1
                    if ocr_text.strip() and cid_ratio(ocr_text) <= CID_REJECT_RATIO:
                        text, method = ocr_text, "ocr"
                    else:
                        method = "rejected"
                else:
                    method = "rejected"
            pages.append(PageText(page_number=i + 1, text=text, method=method))
    n_rej = sum(1 for p in pages if p.method == "rejected")
    if n_rej:
        logger.info(
            "%d/%d pages unreadable (no text or unmapped fonts%s)",
            n_rej,
            len(pages),
            "" if ocr_enabled else "; OCR disabled",
        )
    return pages


def _ocr_page(pdf_path: Path, page_number: int) -> str:
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        logger.warning(
            "OCR fallback requested but pytesseract/pdf2image not installed"
        )
        return ""
    try:
        images = convert_from_path(
            pdf_path, dpi=200, first_page=page_number, last_page=page_number
        )
        return "\n".join(pytesseract.image_to_string(img) for img in images)
    except Exception as exc:
        logger.warning("OCR failed on page %d: %s", page_number, exc)
        return ""


# ── Extraction-row writer (the Layer-3 output) ───────────────────────
def finding_to_extracted_json(f: BlueBookFinding, fy: Optional[str]) -> dict:
    return {
        "schema": "oag_blue_book/v1",
        "vote": f.vote,
        "entity_name": f.entity_name,
        "fiscal_year": fy,
        "paragraph_no": f.paragraph_no,
        "title": f.title,
        "finding_text": f.finding_text,
        "pdf_page": f.pdf_page,
        "printed_page": f.printed_page,
        "subreport": f.subreport,
        "opinion": f.opinion,
        "heading": f.heading,
        "sub_section": f.sub_section,
        "severity": severity_for(f.heading, f.opinion),
        "amounts": f.amounts,
        "extraction_method": f.method,
    }


def source_hash_of(extracted_json: dict) -> str:
    """sha256 over the canonical JSON — lets anyone re-check the row."""
    canonical = json.dumps(extracted_json, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ExtractionStillReferenced(RuntimeError):
    """A row a re-extraction would remove is cited by something besides audits."""


class EmptyReExtraction(RuntimeError):
    """A re-read found no finding in a document that has rows. Refused."""


#: Rows per ``IN (...)``. SQLite, which the tests run on, caps a statement at
#: 999 parameters.
_CHUNK = 500


def _chunks(ids: List[int]):
    for i in range(0, len(ids), _CHUNK):
        yield ids[i : i + _CHUNK]


def extraction_is_current(doc) -> bool:
    """Has this version of the walk already read these exact bytes?

    Fails closed. A missing md5 on either side, or a version stamp that is not
    exactly this walk's, means "re-read". ``True == 1`` in Python, so the
    stamp's type is checked, not only its value.
    """
    meta = doc.meta or {}
    version = meta.get("extractor_version")
    return bool(
        doc.md5
        and meta.get("extracted_md5") == doc.md5
        and type(version) is int
        and version == EXTRACTOR_VERSION
    )


def blue_book_row_key(payload: dict) -> tuple:
    """What makes two extractions of one document the same finding.

    Not the page: a re-issued PDF can move a paragraph to another page. The
    walk emits paragraph numbers in strictly increasing order within a vote,
    so the key is unique among the rows it writes.
    """
    return (payload.get("vote"), payload.get("paragraph_no"), payload.get("title"))


def replace_extractions(session, doc, extractor_id: str, rows: list, key, *, review=None) -> dict:
    """Atomically reconcile a validated candidate, preserving evidence on failure."""
    from .reconciliation import lock_reconciliation_source

    lock_reconciliation_source(session, doc)
    with session.begin_nested():
        session.refresh(doc)
        return _replace_extractions(session, doc, extractor_id, rows, key, review=review)


def _replace_extractions(session, doc, extractor_id: str, rows: list, key, *, review=None) -> dict:
    """Make ``doc``'s rows from ``extractor_id`` exactly ``rows``.

    ``audits.extraction_id`` is a foreign key, so the old way (delete every
    row, insert the new ones) failed on Postgres whenever a finding had been
    published from the document. The rows are reconciled instead, by
    ``key(extracted_json)``:

    * an old row with a new row's key is UPDATED in place. It keeps its id, so
      the audit that cites it keeps citing it, and the loader then rewrites
      that audit from the new payload.
    * a new row with no old match is inserted.
    * revisions and retirements require a source-checked review bound to the
      exact old rows, incoming rows and source file (reconciliation.py).
      Automatic runs preserve existing evidence when these disagree.

    Audits are the only facts loaded from these rows. If any other table
    cites a row that would be removed, nothing is changed and
    ``ExtractionStillReferenced`` is raised. Deleting evidence a published
    figure stands on is not this function's decision.

    Returns counts, plus the ids of inserted rows as ``fresh_extraction_ids``
    (the loader skips its confirming SELECT for rows created in this
    transaction).
    """
    from models import Audit, Base, Extraction
    from sqlalchemy import func, select

    from .reconciliation import validate_candidates, require_review, row_changed

    validate_candidates(doc, extractor_id, rows, key)
    old = (
        session.query(Extraction)
        .filter(
            Extraction.source_document_id == doc.id,
            Extraction.extractor == extractor_id,
        )
        .order_by(Extraction.id)
        .populate_existing()
        .with_for_update()
        .all()
    )
    by_key: Dict[tuple, list] = {}
    for row in old:
        by_key.setdefault(key(row.extracted_json or {}), []).append(row)

    matched: List[Tuple[object, object]] = []
    inserted: list = []
    for new in rows:
        candidates = by_key.get(key(new.extracted_json or {}))
        if candidates:
            matched.append((candidates.pop(0), new))
        else:
            inserted.append(new)
    vanished = [r for group in by_key.values() for r in group]
    vanished_ids = [r.id for r in vanished]

    # Other domains may cite either a retired row or a revised payload. This
    # function owns neither decision on their behalf, even with a review.
    affected_ids = vanished_ids + [r.id for r, new in matched if row_changed(r, new)]
    # Refuse before changing anything.
    for table in Base.metadata.sorted_tables:
        if table.name == Audit.__tablename__:
            continue
        for fk in table.foreign_keys:
            if fk.column.table.name != Extraction.__tablename__:
                continue
            cited = sum(
                session.execute(
                    select(func.count())
                    .select_from(table)
                    .where(fk.parent.in_(chunk))
                ).scalar_one()
                for chunk in _chunks(affected_ids)
            )
            if cited:
                raise ExtractionStillReferenced(
                    f"{table.name}.{fk.parent.name} cites {cited} of the "
                    f"{len(affected_ids)} {extractor_id} row(s) document {doc.id} "
                    "would change; nothing was replaced"
                )

    require_review(session, doc, extractor_id, old, rows, matched, vanished, review)

    # Through the ORM, not a bulk DELETE: a bulk delete leaves the deleted
    # audits live in the session, where the loader would meet them again.
    audits_removed = 0
    for chunk in _chunks(vanished_ids):
        for audit in session.query(Audit).filter(Audit.extraction_id.in_(chunk)):
            session.delete(audit)
            audits_removed += 1
    session.flush()
    for row in vanished:
        session.delete(row)
    session.flush()

    def same_confidence(a, b) -> bool:
        # Numeric column: it reads back as Decimal("0.90"), never == 0.9.
        return (a is None) == (b is None) and (a is None or float(a) == float(b))

    updated = 0
    for row, new in matched:
        changed = False
        for attr in ("extracted_json", "page_number"):
            if getattr(row, attr) != getattr(new, attr):
                setattr(row, attr, getattr(new, attr))
                changed = True
        if not same_confidence(row.confidence, new.confidence):
            row.confidence = new.confidence
            changed = True
        updated += changed
    for new in inserted:
        session.add(new)
    session.flush()

    return {
        "kept": len(matched) - updated,
        "updated": updated,
        "inserted": len(inserted),
        "removed": len(vanished),
        "audits_removed": audits_removed,
        "fresh_extraction_ids": [r.id for r in inserted],
    }


def extract_blue_book(session, doc, settings, *, review=None) -> dict:
    """Extract ``doc`` (a fetched Blue Book) into ``extractions`` rows.

    One row per finding, ``page_number`` = 1-based PDF page. Idempotent: when
    this version of the walk has already read these exact bytes
    (``extraction_is_current``), nothing is re-read. When the bytes moved or
    the walk changed, the rows are reconciled in place by
    ``replace_extractions``, so a finding that survives keeps its row and its
    published audit.

    Returns a stats dict (created / skipped / rejected_cid / votes_seen, and
    the reconciliation counts).
    """
    from models import Extraction

    if not doc.file_path or not Path(doc.file_path).exists():
        raise FileNotFoundError(
            f"source document {doc.id} has no local file — fetch it first"
        )

    existing = (
        session.query(Extraction)
        .filter(
            Extraction.source_document_id == doc.id,
            Extraction.extractor == EXTRACTOR_ID,
        )
        .count()
    )
    doc_meta = dict(doc.meta or {})
    if existing and extraction_is_current(doc):
        logger.info(
            "Document %s already extracted at md5 %s by walk version %s "
            "(%d rows) — skipping",
            doc.id,
            doc.md5,
            EXTRACTOR_VERSION,
            existing,
        )
        return {
            "created": 0,
            "existing": existing,
            "rejected_cid": 0,
            "votes_seen": 0,
            "skipped_unchanged": True,
        }

    pages = read_pages(
        Path(doc.file_path),
        ocr_enabled=getattr(settings, "audits_ocr_enabled", False),
        ocr_max_pages=getattr(settings, "audits_ocr_max_pages", 30),
    )
    result = parse_blue_book(pages, doc.url or "")

    if existing and not result.findings:
        # A walk that suddenly finds nothing in a document it used to read is
        # far likelier broken than the report empty. Replacing would delete
        # every published finding of the document.
        raise EmptyReExtraction(
            f"document {doc.id}: re-read found no finding where {existing} "
            f"row(s) exist (toc entries: {result.votes_seen}); rows kept"
        )

    from .reconciliation import IncompleteExtraction

    if result.rejected_cid or any(p.method == "rejected" for p in pages):
        raise IncompleteExtraction(f"document {doc.id}: unreadable source text; rows kept")
    if result.skipped_votes:
        raise IncompleteExtraction(f"document {doc.id}: skipped chapters {result.skipped_votes}; rows kept")

    rows = [
        Extraction(
            source_document_id=doc.id,
            page_number=f.pdf_page,
            extracted_json=finding_to_extracted_json(f, result.fiscal_year_label),
            extractor=EXTRACTOR_ID,
            confidence=0.90 if f.method == "pdfplumber" else 0.60,
        )
        for f in result.findings
    ]
    replaced = replace_extractions(
        session, doc, EXTRACTOR_ID, rows, key=blue_book_row_key, review=review
    )
    if existing:
        logger.warning(
            "Re-extracted document %s (%s): %d kept, %d updated, %d new, "
            "%d removed with %d audit row(s)",
            doc.id,
            "md5 changed"
            if doc_meta.get("extracted_md5") != doc.md5
            else f"walk version {doc_meta.get('extractor_version', 1)!r} -> "
            f"{EXTRACTOR_VERSION}",
            replaced["kept"],
            replaced["updated"],
            replaced["inserted"],
            replaced["removed"],
            replaced["audits_removed"],
        )

    doc_meta.update(doc.meta or {})  # Keep the accepted reconciliation receipt.
    doc_meta["extracted_md5"] = doc.md5
    doc_meta["extractor_version"] = EXTRACTOR_VERSION
    doc_meta["extraction_stats"] = {
        "findings": len(rows),
        "rejected_cid": result.rejected_cid,
        "votes_seen": result.votes_seen,
        "ocr_pages": result.ocr_pages,
        "fiscal_year": result.fiscal_year_label,
    }
    doc.meta = doc_meta
    session.flush()
    logger.info(
        "Extracted %d findings from document %s (%d votes, %d rejected for "
        "text integrity, %d OCR pages)",
        len(rows),
        doc.id,
        result.votes_seen,
        result.rejected_cid,
        result.ocr_pages,
    )
    return {
        "created": replaced["inserted"],
        "findings": len(rows),
        "kept": replaced["kept"],
        "updated": replaced["updated"],
        "removed": replaced["removed"],
        "audits_removed": replaced["audits_removed"],
        "existing": 0,
        "rejected_cid": result.rejected_cid,
        "votes_seen": result.votes_seen,
        "skipped_unchanged": False,
        "fresh_extraction_ids": replaced["fresh_extraction_ids"],
    }


__all__ = [
    "EXTRACTOR_ID",
    "EXTRACTOR_VERSION",
    "MAX_NUMBER_STEP",
    "EmptyReExtraction",
    "ExtractionStillReferenced",
    "blue_book_row_key",
    "extraction_is_current",
    "replace_extractions",
    "BlueBookFinding",
    "BlueBookResult",
    "PageText",
    "cid_ratio",
    "extract_blue_book",
    "fiscal_year_from_url",
    "find_offset",
    "finding_to_extracted_json",
    "parse_blue_book",
    "parse_toc",
    "read_pages",
    "segment_chapter",
    "severity_for",
    "source_hash_of",
]

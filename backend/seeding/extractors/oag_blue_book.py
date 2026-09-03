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
_FINDING_START_RE = re.compile(r"^(\d{1,3})\.\s+(\S.*)$")
_AMOUNT_RE = re.compile(r"Kshs?\.?\s*([\d][\d,]*(?:\.\d+)?)", re.IGNORECASE)
_NO_ISSUE_RE = re.compile(r"^There (?:was|were) no material issue", re.IGNORECASE)
# Appendices (summary tables of opinions per MDA) follow the last chapter.
# Their numbered table rows are not findings — a chapter ends here.
_APPENDIX_RE = re.compile(r"^Appendix\s+[A-Z0-9]", re.IGNORECASE)
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
    """(vote, entity, printed_page) from the TOC pages (front matter)."""
    toc: List[Tuple[int, str, int]] = []
    for page in pages[:12]:  # TOC lives in the front matter
        for line in page.text.split("\n"):
            m = _TOC_RE.match(line.strip())
            if m:
                toc.append((int(m.group(1)), m.group(2).strip(), int(m.group(3))))
    return toc


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


def segment_chapter(
    pages: List[PageText],
    vote: int,
    entity_name: str,
    start_printed: int,
    end_printed: int,
    offset: int,
) -> Tuple[List[BlueBookFinding], int]:
    """Findings for one vote's chapter. Returns (findings, rejected_cid)."""
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

    findings: List[BlueBookFinding] = []
    rejected = 0
    subreport: Optional[str] = None
    opinion: Optional[str] = None
    heading: Optional[str] = None
    sub_section: Optional[str] = None
    cur: Optional[dict] = None
    prev_no: Optional[int] = None

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
        if _APPENDIX_RE.match(line):
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
        m = _FINDING_START_RE.match(line)
        if m:
            no = int(m.group(1))
            title = m.group(2).strip()
            # Paragraph numbering is continuous within a chapter. Accepting
            # only prev+1 (or the very first number seen) rejects numbered
            # list items inside a finding body masquerading as findings.
            is_next = prev_no is not None and no == prev_no + 1
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
    last_printed = len(pages) - offset
    for i, (vote, entity, start_printed) in enumerate(toc):
        end_printed = (
            toc[i + 1][2] - 1 if i + 1 < len(toc) else last_printed
        )
        # Verify the chapter really starts where the TOC says: the vote
        # number must appear in the first lines of the start page.
        idx = offset + start_printed - 1
        if idx >= len(pages):
            continue
        head = "\n".join(pages[idx].text.split("\n")[:3])
        m = _VOTE_RE.search(head)
        if not m or int(m.group(1)) != vote:
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
    return BlueBookResult(fy, all_findings, len(toc), rejected, ocr_pages)


# ── PDF I/O (thin, impure shell around the pure parser) ──────────────
def read_pages(
    pdf_path: Path, *, ocr_enabled: bool, ocr_max_pages: int = 30
) -> List[PageText]:
    """Per-page text with OCR fallback for unmappable-font pages.

    A page whose embedded text is empty or >20% ``(cid:`` is re-read via
    OCR (pdf2image + pytesseract) when enabled; if it still fails the
    integrity check it is marked ``rejected`` and contributes nothing.
    """
    import pdfplumber

    pages: List[PageText] = []
    ocr_used = 0
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
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


def extract_blue_book(session, doc, settings) -> dict:
    """Extract ``doc`` (a fetched Blue Book) into ``extractions`` rows.

    One row per finding, ``page_number`` = 1-based PDF page. Idempotent:
    if rows from this extractor already exist for this document and the
    document's md5 has not changed since, nothing is re-written.

    Returns a stats dict (created / skipped / rejected_cid / votes_seen).
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
    if existing and doc_meta.get("extracted_md5") == doc.md5:
        logger.info(
            "Document %s already extracted at md5 %s (%d rows) — skipping",
            doc.id,
            doc.md5,
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

    if existing:
        # The document was re-issued (md5 moved): the old rows describe
        # bytes that no longer exist at the URL. Replace them.
        logger.warning(
            "Re-extracting document %s: md5 changed since last extraction "
            "(%d old rows replaced)",
            doc.id,
            existing,
        )
        session.query(Extraction).filter(
            Extraction.source_document_id == doc.id,
            Extraction.extractor == EXTRACTOR_ID,
        ).delete()

    created = 0
    for f in result.findings:
        payload = finding_to_extracted_json(f, result.fiscal_year_label)
        session.add(
            Extraction(
                source_document_id=doc.id,
                page_number=f.pdf_page,
                extracted_json=payload,
                extractor=EXTRACTOR_ID,
                confidence=0.90 if f.method == "pdfplumber" else 0.60,
            )
        )
        created += 1
    doc_meta["extracted_md5"] = doc.md5
    doc_meta["extraction_stats"] = {
        "findings": created,
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
        created,
        doc.id,
        result.votes_seen,
        result.rejected_cid,
        result.ocr_pages,
    )
    return {
        "created": created,
        "existing": 0,
        "rejected_cid": result.rejected_cid,
        "votes_seen": result.votes_seen,
        "skipped_unchanged": False,
    }


__all__ = [
    "EXTRACTOR_ID",
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

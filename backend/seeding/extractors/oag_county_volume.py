"""Layer 3: split an OAG combined county volume into 47 chapters, then findings.

WHY THIS EXISTS
---------------
From FY2021/22 onwards OAG publishes each year's county audits as two combined
volumes, one for all 47 county executives and one for all 47 county
assemblies. Run over the four years' eight volumes on 2026-09-26, the extractor
the FY2020/21 volumes went through got ZERO findings from three of them and
partial results from the rest. Every cause is a layout fact, and each one is a
test in ``tests/test_oag_county_volume.py``:

* **No printed "1" footer on the first chapter page** (FY2023/24 executives,
  both FY2021/22 volumes), so ``find_offset`` returned None and nothing at all
  was extracted. Chapters are located here by their own headings, so printed
  page arithmetic is never needed.
* **Table of contents variants.** The period after the number is sometimes
  missing ("18 County Executive of Nyandarua ....."). Leaders are sometimes
  the ellipsis character with no space ("19. County Assembly of Nyeri…………73").
  The FY2021/22 volumes print a contents page twice.
* **Off-canvas text** on every odd page of the FY2021/22 volumes. See
  ``oag_blue_book.read_pages(visible_only=True)``.
* **Paragraph numbers run on across the whole volume** past 1,000, skip
  numbers, and findings cite "Appendix VI ..." at the start of a line. See the
  keyword arguments of ``oag_blue_book.segment_chapter``.
* **Heading forms vary**: "COUNTY EXECUTIVE OF MOMBASA – NO.1", and also
  "NAIROBI CITY COUNTY ASSEMBLY – NO.47".

The walk inside a chapter (sub-reports, opinion lines, "Basis for ..."
headings, numbered paragraphs, cid rejection) is the Blue Book's
``segment_chapter``. One definition of what a finding is, not two.

THE GATES
---------
Each is a reason to refuse, never to guess:

1. A chapter is emitted only if its heading's number is in the table of
   contents AND the county named in the heading is the one the contents give
   for that number. "COUNTY ASSEMBLY OF KILIFI – NO.3" cannot be filed as
   Kisumu.
2. The county must resolve to one of the 47 county entities already held.
3. The fiscal year must be stated by at least one of: the volume's own title
   page ("FOR THE YEAR 2024/2025"), the OAG year page it was discovered on, or
   its filename. Every source that states one must agree.
4. The volume kind (executives/assemblies) likewise, from the title page and
   discovery.

This module is importable on its own: ``split_volume`` works on page text
alone, with no database, for anyone who needs "which pages are county X in
this volume" (the stalled-projects corroboration, for one).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .oag_blue_book import (
    BlueBookFinding,
    PageText,
    read_pages,
    replace_extractions,
    segment_chapter,
    severity_for,
)
from .oag_county_audit import CountyAuditError

logger = logging.getLogger("seeding.extractors.oag_county_volume")

EXTRACTOR_ID = "oag_county_volume"  # recorded on every extractions row
SCHEMA = "oag_county_volume/v1"

KIND_EXECUTIVES = "executives"
KIND_ASSEMBLIES = "assemblies"

#: "COUNTY EXECUTIVE OF MOMBASA – NO.1", "NAIROBI CITY COUNTY ASSEMBLY – NO.47".
#: Only ever the FIRST line of a page. It is never repeated as a running header.
_CHAPTER_HEAD_RE = re.compile(
    r"^(?P<auditee>[A-Z][A-Z'’/ .,&-]+?)\s*[–—-]\s*NO\.?\s*(?P<no>\d{1,2})\s*$"
)
#: "1. County Executive of Mombasa ....... 1", "18 County Executive of ... 177",
#: "19. County Assembly of Nyeri…………73".
_TOC_ENTRY_RE = re.compile(
    r"^(?P<no>\d{1,2})\.?\s+(?P<name>(?=[A-Za-z]).*?county.*?)\s*[.…·]{3,}\s*(?P<page>\d{1,4})\s*$",
    re.I,
)
#: County volumes number paragraphs continuously across all 47 chapters.
FINDING_START_RE = re.compile(r"^(\d{1,4})\.\s+(\S.*)$")
#: OAG skips a number now and then (1266, 1147, 798 exist nowhere in their
#: volumes). A step this small is a skip. A numbered list inside a finding goes
#: backwards, and a year at the start of a wrapped line ("2020. This was ...")
#: jumps by hundreds, so neither passes.
MAX_NUMBER_STEP = 3
_FY_TEXT_RE = re.compile(
    r"FOR\s+THE\s+YEAR\s+(?P<y1>20\d{2})\s*[/–-]\s*(?P<y2>20\d{2})", re.I
)
_KIND_TEXT_RE = re.compile(
    r"VOLUME\s+(?:\d|I{1,2})\s*[:–—-]?\s*COUNTY\s+(?P<kind>EXECUTIVES|ASSEMBLIES)", re.I
)
_GOVERNMENTS_RE = re.compile(r"COUNTY\s+GOVERNMENTS", re.I)
#: The end matter after the last chapter: the opinions appendix, then the back
#: cover.
_END_MATTER_RE = re.compile(r"^(APPENDIX\b|CONTACTS\b)", re.I)
_COUNTY_OF_RE = re.compile(
    r"county\s+(?:executive|assembly|government)\s+of\s+(?P<county>.+)$", re.I
)
_COUNTY_SUFFIX_RE = re.compile(
    r"^(?P<county>.+?)\s+county\s+(?:executive|assembly|government)$", re.I
)

#: Front matter holds the title page and the contents. 12 pages covers both in
#: every volume measured (contents end on page 7 at the latest).
HEAD_PAGES = 12
#: At least this many county contents entries before a document is treated as
#: a combined volume.
MIN_TOC_ENTRIES = 10


@dataclass(frozen=True)
class TocEntry:
    no: int
    name: str  # as printed: "County Executive of Taita/Taveta"
    printed_page: int


@dataclass(frozen=True)
class Chapter:
    no: int
    heading: str  # first line of the chapter, as printed
    toc_name: str
    county: str  # from the contents: "Taita/Taveta", "Nairobi City"
    start_page: int  # 1-based PDF page
    end_page: int  # 1-based PDF page, inclusive


@dataclass
class VolumeSplit:
    fiscal_year_in_text: Optional[str]
    kind_in_text: Optional[str]
    toc: Dict[int, TocEntry]
    chapters: List[Chapter]
    #: (number, reason) for every contents entry that did not become a chapter.
    refused: List[Tuple[int, str]] = field(default_factory=list)


def _letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", (text or "").lower())


def _first_line(text: str) -> str:
    for line in (text or "").split("\n"):
        if line.strip():
            return line.strip()
    return ""


def county_from_auditee(name: str) -> Optional[str]:
    """``"County Executive of Taita/Taveta"`` -> ``"Taita/Taveta"``.

    Also ``"Nairobi City County Assembly"`` -> ``"Nairobi City"``, the form
    that has no "of".
    """
    name = re.sub(r"\s+", " ", (name or "").strip())
    m = _COUNTY_OF_RE.search(name) or _COUNTY_SUFFIX_RE.match(name)
    return m.group("county").strip(" .,") if m else None


def parse_toc(pages: List[PageText]) -> Dict[int, TocEntry]:
    """``{number: entry}`` for the county entries in the contents.

    The first occurrence of a number wins. The FY2021/22 volumes print the
    second contents page twice, identically.
    """
    out: Dict[int, TocEntry] = {}
    for page in pages[:HEAD_PAGES]:
        for line in page.text.split("\n"):
            m = _TOC_ENTRY_RE.match(line.strip())
            if not m:
                continue
            no = int(m.group("no"))
            name = re.sub(r"\s+", " ", m.group("name")).strip()
            if county_from_auditee(name) is None:
                continue
            out.setdefault(no, TocEntry(no, name, int(m.group("page"))))
    return out


def fiscal_year_in_text(pages: List[PageText]) -> Optional[str]:
    """``"2024/2025"`` from the title page's "FOR THE YEAR 2024/2025"."""
    head = "\n".join(p.text for p in pages[:HEAD_PAGES])
    found = set()
    for m in _FY_TEXT_RE.finditer(head):
        y1, y2 = int(m.group("y1")), int(m.group("y2"))
        if y2 == y1 + 1:
            found.add(f"{y1}/{y2}")
    return found.pop() if len(found) == 1 else None


def kind_in_text(pages: List[PageText]) -> Optional[str]:
    """``executives`` or ``assemblies``, from "VOLUME 1 – COUNTY EXECUTIVES"."""
    head = re.sub(r"\s+", " ", "\n".join(p.text for p in pages[:HEAD_PAGES]))
    kinds = {m.group("kind").lower() for m in _KIND_TEXT_RE.finditer(head)}
    return kinds.pop() if len(kinds) == 1 else None


def looks_like_county_volume(pages: List[PageText]) -> bool:
    """A combined county volume, as opposed to a single-entity report."""
    head = "\n".join(p.text for p in pages[:HEAD_PAGES])
    return bool(_GOVERNMENTS_RE.search(head)) and len(parse_toc(pages)) >= MIN_TOC_ENTRIES


def split_volume(pages: List[PageText]) -> VolumeSplit:
    """Locate each chapter by its heading and check it against the contents.

    Pure: takes page text, touches no database.
    """
    toc = parse_toc(pages)
    anchors: List[Tuple[int, int, str]] = []  # (pdf_page, number, heading)
    seen = set()
    for page in pages:
        head = _first_line(page.text)
        m = _CHAPTER_HEAD_RE.match(head)
        if not m:
            continue
        no = int(m.group("no"))
        if no in seen:
            continue
        seen.add(no)
        anchors.append((page.page_number, no, head))
    anchors.sort()

    # The last chapter runs to the end matter, not to the back cover.
    last_start = anchors[-1][0] if anchors else len(pages)
    end_matter = next(
        (
            p.page_number
            for p in pages
            if p.page_number > last_start and _END_MATTER_RE.match(_first_line(p.text))
        ),
        len(pages) + 1,
    )

    chapters: List[Chapter] = []
    refused: List[Tuple[int, str]] = []
    for i, (start, no, heading) in enumerate(anchors):
        end = anchors[i + 1][0] - 1 if i + 1 < len(anchors) else end_matter - 1
        entry = toc.get(no)
        if entry is None:
            refused.append((no, "number_not_in_contents"))
            continue
        county = county_from_auditee(entry.name)
        # Letters only: "TAITA/TAVETA" vs "Taita/Taveta", "NAIROBI CITY" vs
        # "Nairobi City". The whole contents county must appear in the heading.
        if not county or _letters(county) not in _letters(heading):
            refused.append((no, "heading_does_not_match_contents"))
            continue
        chapters.append(Chapter(no, heading, entry.name, county, start, end))

    for no in sorted(set(toc) - seen):
        refused.append((no, "chapter_heading_not_found"))
    return VolumeSplit(
        fiscal_year_in_text=fiscal_year_in_text(pages),
        kind_in_text=kind_in_text(pages),
        toc=toc,
        chapters=chapters,
        refused=sorted(refused),
    )


def printed_page_numbers(pages: List[PageText]) -> Dict[int, int]:
    """``{pdf_page: printed_page}`` from each page's footer, where it has one."""
    out: Dict[int, int] = {}
    for p in pages:
        lines = [l.strip() for l in p.text.split("\n") if l.strip()]
        if lines and lines[-1].isdigit():
            out[p.page_number] = int(lines[-1])
    return out


def segment_volume(
    pages: List[PageText], split: VolumeSplit
) -> Tuple[List[Tuple[Chapter, BlueBookFinding]], int]:
    """Every finding in every accepted chapter, with the chapter it belongs to."""
    # The heading line is the chapter's identity, not a sub-section, so it is
    # dropped from the text the walk sees. Otherwise the ALL-CAPS rule would
    # record it as the first finding's sub_section.
    by_page = {p.page_number: p for p in pages}
    walked = list(pages)
    for ch in split.chapters:
        page = by_page[ch.start_page]
        body = page.text.split("\n")
        idx = next(i for i, l in enumerate(body) if l.strip())
        walked[ch.start_page - 1] = PageText(
            page.page_number, "\n".join(body[idx + 1 :]), page.method
        )

    out: List[Tuple[Chapter, BlueBookFinding]] = []
    rejected = 0
    for ch in split.chapters:
        findings, rej = segment_chapter(
            walked,
            ch.no,
            ch.toc_name,
            ch.start_page,
            ch.end_page,
            0,  # pdf page numbers throughout; the printed number is looked up
            finding_start_re=FINDING_START_RE,
            stop_at_appendix=False,
            max_number_step=MAX_NUMBER_STEP,
            skip_prior_issue_tables=True,
        )
        rejected += rej
        out.extend((ch, f) for f in findings)
    return out, rejected


def resolve_fiscal_year(
    *, in_text: Optional[str], discovered: Optional[str], in_filename: Optional[str]
) -> Tuple[str, List[str]]:
    """The one fiscal year every source that states one agrees on.

    Returns ``(label, sources)``. Raises ``CountyAuditError`` when no source
    states a year, or when two disagree. A volume filed under the wrong year
    publishes 1,000 findings against the wrong audit, so a conflict is not
    settled by preferring one source.
    """
    stated = {
        name: value
        for name, value in (
            ("title_page", in_text),
            ("oag_year_page", discovered),
            ("filename", in_filename),
        )
        if value
    }
    if not stated:
        raise CountyAuditError(
            "fiscal_year_not_found",
            "no fiscal year on the title page, the OAG year page or the filename",
        )
    if len(set(stated.values())) > 1:
        raise CountyAuditError("fiscal_year_conflict", repr(stated))
    return next(iter(stated.values())), sorted(stated)


def resolve_kind(*, in_text: Optional[str], discovered: Optional[str]) -> str:
    stated = {v for v in (in_text, discovered) if v in (KIND_EXECUTIVES, KIND_ASSEMBLIES)}
    if len(stated) != 1:
        raise CountyAuditError(
            "volume_kind_unresolved",
            f"title page says {in_text!r}, discovery says {discovered!r}",
        )
    return stated.pop()


def canonical_county(county: str, known_counties: Dict[str, str]) -> Optional[str]:
    """The held county a contents name refers to, or None.

    "Nairobi City" is the county the database holds as "Nairobi", so a
    trailing "City" is tried as an alias, the same rule the loader applies.
    """
    for probe in (county, re.sub(r"\s+city$", "", county or "", flags=re.I)):
        hit = known_counties.get(_letters(probe))
        if hit:
            return hit
    return None


def finding_to_extracted_json(
    ch: Chapter,
    f: BlueBookFinding,
    *,
    fiscal_year: str,
    fiscal_year_sources: List[str],
    kind: str,
    county: str,
    printed_page: Optional[int],
) -> dict:
    # The loader resolves entity_name to the county. "County Executive of X"
    # is the form it maps onto an existing county, never a new entity, and X is
    # the canonical name held in the database.
    role = "Executive" if kind == KIND_EXECUTIVES else "Assembly"
    return {
        "schema": SCHEMA,
        "volume_kind": kind,
        "chapter_no": ch.no,
        "auditee": ch.toc_name,
        "chapter_heading": ch.heading,
        "entity_name": f"County {role} of {county}",
        "county_name": county,
        "fiscal_year": fiscal_year,
        "fiscal_year_sources": fiscal_year_sources,
        "paragraph_no": f.paragraph_no,
        "title": f.title,
        "finding_text": f.finding_text,
        "pdf_page": f.pdf_page,
        "printed_page": printed_page,
        "subreport": f.subreport,
        "opinion": f.opinion,
        "heading": f.heading,
        "sub_section": f.sub_section,
        "severity": severity_for(f.heading, f.opinion),
        "amounts": f.amounts,
        "extraction_method": f.method,
    }


def read_head(pdf_path, n: int = HEAD_PAGES) -> List[PageText]:
    """The front matter only: enough to decide what the document is."""
    import pdfplumber

    try:
        with pdfplumber.open(pdf_path) as pdf:
            return [
                PageText(i + 1, p.within_bbox(p.bbox).extract_text() or "", "pdfplumber")
                for i, p in enumerate(pdf.pages[:n])
            ]
    except Exception as exc:
        raise CountyAuditError(
            "pdf_unreadable", f"{type(exc).__name__}: {str(exc)[:160]}"
        ) from exc


def county_volume_row_key(payload: dict) -> tuple:
    """What makes two extractions of one volume the same finding: chapter,
    paragraph and title. Not the page, which a re-issue can move."""
    return (payload.get("chapter_no"), payload.get("paragraph_no"), payload.get("title"))


def already_extracted(session, doc) -> int:
    """Rows this extractor holds for the document's CURRENT bytes; 0 if unknown.

    Fails closed. A missing md5 on either side means "re-read", the same rule
    ``oag_county_audit._delegate_rows_at_current_md5`` applies.
    """
    from models import Extraction

    if not doc.md5 or (doc.meta or {}).get("extracted_md5") != doc.md5:
        return 0
    return (
        session.query(Extraction)
        .filter(
            Extraction.source_document_id == doc.id,
            Extraction.extractor == EXTRACTOR_ID,
        )
        .count()
    )


def extract_county_volume(session, doc, settings, *, known_counties: Dict[str, str]) -> dict:
    """Extract a combined county volume into ``extractions`` rows.

    One row per finding, ``page_number`` = the 1-based PDF page it starts on.
    Idempotent on the document's md5. Raises ``CountyAuditError`` when the
    volume cannot say which year or which kind it is.
    """
    from models import Extraction

    from ..oag_discovery import fiscal_year_in_name

    if not doc.file_path or not Path(doc.file_path).exists():
        raise FileNotFoundError(f"county volume file missing: {doc.file_path!r}")
    if not known_counties:
        raise CountyAuditError(
            "no_county_reference",
            "no county entities held, so no chapter can be attributed",
        )

    existing = already_extracted(session, doc)
    if existing:
        return {
            "created": 0,
            "skipped": existing,
            "rejected_cid": 0,
            "reason": "already_extracted",
            "shape": "county_volume",
        }

    pages = read_pages(
        Path(doc.file_path),
        ocr_enabled=getattr(settings, "audits_ocr_enabled", False),
        ocr_max_pages=getattr(settings, "audits_ocr_max_pages", 30),
        visible_only=True,
    )
    if not looks_like_county_volume(pages):
        # Discovery named it a volume from its filename and year page. The
        # bytes disagree, and the bytes win.
        raise CountyAuditError(
            "not_a_county_volume",
            f"{len(parse_toc(pages))} county contents entries in the front matter",
        )
    split = split_volume(pages)
    discovery = (doc.meta or {}).get("oag_discovery") or {}
    fiscal_year, fy_sources = resolve_fiscal_year(
        in_text=split.fiscal_year_in_text,
        discovered=discovery.get("fiscal_year"),
        in_filename=fiscal_year_in_name((doc.url or "").rsplit("/", 1)[-1]),
    )
    kind = resolve_kind(in_text=split.kind_in_text, discovered=discovery.get("kind"))

    refused = list(split.refused)
    resolved: Dict[int, str] = {}
    for ch in split.chapters:
        held = canonical_county(ch.county, known_counties)
        if held is None:
            refused.append((ch.no, "county_not_resolved"))
        else:
            resolved[ch.no] = held
    if not resolved:
        raise CountyAuditError(
            "no_chapter_attributed",
            f"{len(split.toc)} contents entries, {len(split.chapters)} chapters, "
            f"refused: {refused[:5]}",
        )

    findings, rejected = segment_volume(pages, split)
    printed = printed_page_numbers(pages)

    created = 0
    per_chapter: Dict[int, int] = {}
    rows: List = []
    for ch, f in findings:
        county = resolved.get(ch.no)
        if county is None:
            continue
        payload = finding_to_extracted_json(
            ch,
            f,
            fiscal_year=fiscal_year,
            fiscal_year_sources=fy_sources,
            kind=kind,
            county=county,
            printed_page=printed.get(f.pdf_page),
        )
        # No source_hash inside the payload: the loader hashes the payload
        # onto audits.source_hash, and a hash stored inside the thing it
        # hashes could never be re-checked against it.
        rows.append(
            Extraction(
                source_document_id=doc.id,
                page_number=f.pdf_page,
                extracted_json=payload,
                extractor=EXTRACTOR_ID,
                confidence=0.90 if f.method == "pdfplumber" else 0.60,
            )
        )
        created += 1
        per_chapter[ch.no] = per_chapter.get(ch.no, 0) + 1

    # Re-issued bytes: rows from the old md5 describe a document that no
    # longer exists at the URL. They are reconciled, not deleted wholesale:
    # audits.extraction_id is a foreign key, so a row a published finding
    # cites keeps its id when the finding survives (the Blue Book walk does
    # the same).
    replaced = replace_extractions(
        session, doc, EXTRACTOR_ID, rows, key=county_volume_row_key
    )
    if replaced["kept"] + replaced["updated"] + replaced["removed"]:
        logger.warning(
            "Re-extracted county volume %s (md5 changed): %d kept, %d updated, "
            "%d new, %d removed with %d audit row(s)",
            doc.id,
            replaced["kept"],
            replaced["updated"],
            replaced["inserted"],
            replaced["removed"],
            replaced["audits_removed"],
        )

    empty = sorted(set(resolved) - set(per_chapter))
    meta = dict(doc.meta or {})
    meta["extracted_md5"] = doc.md5
    meta["extraction_stats"] = {
        "extractor": EXTRACTOR_ID,
        "findings": created,
        "fiscal_year": fiscal_year,
        "fiscal_year_sources": fy_sources,
        "volume_kind": kind,
        "contents_entries": len(split.toc),
        "chapters_attributed": len(resolved),
        "chapters_with_no_finding": empty,
        "refused": [list(r) for r in sorted(refused)],
        "rejected_cid": rejected,
        "pages": len(pages),
        "ocr_pages": sum(1 for p in pages if p.method == "ocr"),
    }
    doc.meta = meta
    session.flush()

    logger.info(
        "oag_county_volume: doc %s %s %s -> %d finding(s) across %d/%d chapter(s); "
        "refused %s; no finding in %s",
        doc.id,
        fiscal_year,
        kind,
        created,
        len(per_chapter),
        len(split.toc),
        refused or "none",
        empty or "none",
    )
    return {
        "created": created,
        "skipped": 0,
        "rejected_cid": rejected,
        "shape": "county_volume",
        "fiscal_year": fiscal_year,
        "volume_kind": kind,
        "chapters": len(per_chapter),
        "refused": [list(r) for r in sorted(refused)],
        # Created in this transaction and not yet committed. The loader may
        # skip its per-row existence check for exactly these. The caller pops
        # this before the stats reach the job metadata.
        "fresh_extraction_ids": replaced["fresh_extraction_ids"],
    }


__all__ = [
    "EXTRACTOR_ID",
    "FINDING_START_RE",
    "MAX_NUMBER_STEP",
    "SCHEMA",
    "Chapter",
    "TocEntry",
    "VolumeSplit",
    "already_extracted",
    "canonical_county",
    "county_volume_row_key",
    "county_from_auditee",
    "extract_county_volume",
    "finding_to_extracted_json",
    "fiscal_year_in_text",
    "kind_in_text",
    "looks_like_county_volume",
    "parse_toc",
    "printed_page_numbers",
    "read_head",
    "resolve_fiscal_year",
    "resolve_kind",
    "segment_volume",
    "split_volume",
]

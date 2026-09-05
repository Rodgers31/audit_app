"""Layer 3 — extract findings from a single-entity OAG county audit report.

WHY THIS EXISTS
---------------
``oag_county_audits`` was registered with ``parser_id=None`` — "county report
parser not yet implemented" — so its documents were fetched, registered, and
never read. The nightly said so plainly every run::

    oag_county_audits: 5 known + 0 newly discovered document(s)
      (no parser — fetch/register only)

The consequence was that county audit findings on the site came from
``apis/oag_audit_data.json``, a hand-maintained fixture 365 days old whose 25
national findings the publication gate already withholds for having no source
URL. There was no path from an OAG county report to a published finding at all.

WHAT THESE DOCUMENTS LOOK LIKE
------------------------------
Unlike the national Blue Book — one volume, a table of contents, hundreds of
votes — a county report covers ONE entity and runs ~10 pages::

    REPORT OF THE AUDITOR-GENERAL ON COUNTY ASSEMBLY OF HOMA BAY
    FOR THE YEAR ENDED 30 JUNE, 2022
    ...
    Basis for Qualified Opinion
    1. Exchequer Releases
    The statement receipts and payments ... reflects total exchequer releases
    of Kshs.1,122,267,322 which is at variance with ... Kshs.1,177,145,243
    resulting to an unreconciled or explained variance of Kshs.54,877,921.

So there is no TOC to walk and no vote numbers. The entity comes from the
title, the period from the "YEAR ENDED" line, the opinion from the "Basis for
… Opinion" heading, and each finding from a numbered heading plus the prose
under it until the next number.

THE GATES
---------
Nothing is emitted unless the document identifies itself. Each is a reason to
quarantine, never to guess, because a finding attributed to the wrong county
or year is worse than no finding:

1. The title must name an auditee, and it must resolve to a real county.
2. The report must state the year it covers.
3. The opinion must be one OAG actually issues.
4. Text integrity — a PDF whose glyphs decode to ``(cid:nn)`` is rejected
   rather than published as mojibake, the same rule the Blue Book applies.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("seeding.extractors.oag_county_audit")

EXTRACTOR_ID = "oag_county_audit"  # recorded on every extractions row

#: The opinions the Auditor-General issues. Anything else is a parse error,
#: not a new kind of opinion.
OPINIONS = ("Unqualified", "Qualified", "Adverse", "Disclaimer")

_TITLE_RE = re.compile(
    r"REPORT\s+OF\s+THE\s+AUDITOR[-\s]?GENERAL\s+ON\s+(?P<auditee>[A-Z0-9''\-\s,\.&]+?)"
    r"(?=\s*FOR\s+THE\s+(?:YEAR|PERIOD)\b)",
    re.I | re.S,
)
_YEAR_ENDED_RE = re.compile(
    r"FOR\s+THE\s+(?:YEAR|PERIOD)\s+ENDED\s+\d{1,2}\s+\w+,?\s+(?P<year>\d{4})", re.I
)
_OPINION_RE = re.compile(
    r"Basis\s+for\s+(?P<opinion>Qualified|Adverse|Disclaimer(?:\s+of)?)\s*Opinion", re.I
)
_UNQUALIFIED_RE = re.compile(
    r"\bunqualified\s+opinion\b|\bpresent\s+fairly\b(?!.{0,80}except)", re.I
)

#: A numbered finding heading at the start of a line: "1. Exchequer Releases".
#: Bounded to a short title so a numbered sentence inside prose is not mistaken
#: for a heading.
_FINDING_RE = re.compile(
    r"^(?P<no>\d{1,2})\.\s+(?P<title>[A-Z][^\n]{3,90})$", re.M
)

#: "Kshs.1,122,267,322" / "Kshs 54,877,921.50" / "KShs. 1.2 billion" is left
#: alone — only fully-written figures are captured, because a rounded phrase
#: is not the audited amount.
_AMOUNT_RE = re.compile(r"K\s?shs?\.?\s*([\d,]{4,}(?:\.\d{1,2})?)", re.I)

#: The report's three parts, each of which numbers its findings from 1. Without
#: capturing this, part A's finding 1 and part B's finding 1 are indistinguishable
#: — two different findings sharing a key.
_SECTION_RE = re.compile(
    r"^REPORT\s+ON\s+(?P<name>THE\s+FINANCIAL\s+STATEMENTS"
    r"|LAWFULNESS[^\n]*"
    r"|EFFECTIVENESS\s+OF\s+INTERNAL\s+CONTROLS[^\n]*)",
    re.I | re.M,
)
_SECTION_CODES = (
    ("financial statements", "A"),
    ("lawfulness", "B"),
    ("internal controls", "C"),
)

#: A consolidated volume titles itself "FOR THE COUNTY GOVERNMENTS", not
#: "ON <entity>". The two shapes need different machinery, and the registry
#: allows one parser_id per dataset, so the shape is detected here and the
#: consolidated case is delegated to the Blue Book walk.
_CONSOLIDATED_RE = re.compile(
    r"AUDITOR\s*[-–]?\s*GENERAL\s+FOR\s+THE\s+COUNTY\s+GOVERNMENTS", re.I | re.S
)

#: Blocks WITHIN a part that restart numbering — "Basis for Qualified Opinion"
#: then "Other Matter" both begin at 1. The Blue Book extractor carries the
#: same distinction as ``sub_section``, for the same reason.
_SUBSECTION_RE = re.compile(
    r"^(?P<name>Basis\s+for\s+\w+(?:\s+of)?\s*(?:Opinion|Conclusion)"
    r"|Other\s+Matter"
    r"|Emphasis\s+of\s+Matter"
    r"|Key\s+Audit\s+Matters)\s*$",
    re.I | re.M,
)

_CID_RE = re.compile(r"\(cid:\d+\)")

#: Above this share of undecodable glyphs the page is not text, it is a
#: rendering artefact. Same threshold the Blue Book extractor uses.
MAX_CID_RATIO = 0.02


class CountyAuditError(Exception):
    """A document that must be QUARANTINED, never published.

    Carries a machine-readable ``reason`` so the caller can record WHY a
    document produced nothing, instead of logging prose nobody gates on.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass
class CountyFinding:
    paragraph_no: int
    #: "A" financial statements / "B" lawfulness / "C" internal controls. The
    #: report restarts numbering in each part AND in each sub-section, so the
    #: key is (section, sub_section, paragraph_no).
    section: Optional[str]
    sub_section: Optional[str]
    title: str
    finding_text: str
    pdf_page: int
    amounts: List[float] = field(default_factory=list)
    method: str = "pdfplumber"


@dataclass
class CountyAuditResult:
    auditee: str  # "County Assembly of Homa Bay", as printed
    county_name: str  # "Homa Bay" — what resolves to an entity
    fiscal_year_label: str  # "2021/2022"
    opinion: str
    findings: List[CountyFinding]
    rejected_cid: int = 0


def cid_ratio(text: str) -> float:
    """Share of the text that is undecodable ``(cid:nn)`` glyph references."""
    if not text:
        return 0.0
    cid_chars = sum(len(m.group(0)) for m in _CID_RE.finditer(text))
    return cid_chars / len(text)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" ,.\n")


def parse_amounts(text: str) -> List[float]:
    """Every fully-written Kshs figure in ``text``, in order of appearance."""
    out: List[float] = []
    for raw in _AMOUNT_RE.findall(text or ""):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


def parse_auditee(text: str) -> Optional[str]:
    """The entity the report is about, from its title line."""
    m = _TITLE_RE.search(text or "")
    return _clean(m.group("auditee")).title() if m else None


def county_of(auditee: str, known_counties: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Map an auditee to the county it belongs to.

    "County Assembly of Homa Bay" and "County Government of Homa Bay" are two
    auditees of the SAME county, and both must land on it. The trailing name
    after "of" is the county; where the title has no "of", the whole auditee is
    tried. Returns None when it does not resolve — a finding filed against the
    wrong county is worse than one not filed.
    """
    if not auditee:
        return None
    # Case-insensitive: the title is Title-Cased upstream, so "of" is "Of".
    candidate = _clean(re.split(r"\bof\b", auditee, maxsplit=1, flags=re.I)[-1])
    for name in (candidate, _clean(auditee)):
        stripped = re.sub(
            r"^(County\s+(Assembly|Government|Executive)\s*)", "", name, flags=re.I
        ).strip()
        for probe in (stripped, name):
            if not probe:
                continue
            if known_counties is None:
                return probe.title()
            key = re.sub(r"[^a-z]", "", probe.lower())
            if key in known_counties:
                return known_counties[key]
    return None


def parse_fiscal_year(text: str) -> Optional[str]:
    """``"FOR THE YEAR ENDED 30 JUNE, 2022"`` -> ``"2021/2022"``.

    Kenya's fiscal year runs 1 July - 30 June, so a report for the year ended
    30 June 2022 covers FY2021/2022. Getting this wrong files a finding under
    the wrong year, which is why it is a gate rather than a default.
    """
    m = _YEAR_ENDED_RE.search(text or "")
    if not m:
        return None
    end = int(m.group("year"))
    return f"{end - 1}/{end}"


def parse_opinion(text: str) -> Optional[str]:
    """The opinion issued, from the "Basis for ... Opinion" heading."""
    m = _OPINION_RE.search(text or "")
    if m:
        word = _clean(m.group("opinion")).split()[0].title()
        return "Disclaimer" if word.startswith("Disclaimer") else word
    if _UNQUALIFIED_RE.search(text or ""):
        return "Unqualified"
    return None


def severity_for(opinion: Optional[str]) -> str:
    """Map an OAG opinion onto the app's severity enum."""
    if opinion in ("Adverse", "Disclaimer"):
        return "CRITICAL"
    if opinion == "Qualified":
        return "WARNING"
    return "INFO"


def parse_findings(pages: List[Tuple[int, str]]) -> Tuple[List[CountyFinding], int]:
    """Numbered findings across the report, with the page each starts on.

    A finding runs from its numbered heading to the next heading (or the end),
    so the text spans page breaks — which is why this takes the whole document
    rather than working page by page.
    """
    rejected = 0
    usable: List[Tuple[int, str]] = []
    for page_no, text in pages:
        if cid_ratio(text) > MAX_CID_RATIO:
            rejected += 1
            continue
        usable.append((page_no, text))

    # One string, remembering where each page began, so a finding's start
    # offset can be turned back into a page number.
    joined = ""
    starts: List[Tuple[int, int]] = []
    for page_no, text in usable:
        starts.append((len(joined), page_no))
        joined += (text or "") + "\n"

    def page_at(offset: int) -> int:
        page = starts[0][1] if starts else 1
        for begin, page_no in starts:
            if begin <= offset:
                page = page_no
            else:
                break
        return page

    # Where each part begins, so a finding can be told which one it is in.
    sections: List[Tuple[int, str]] = []
    for m in _SECTION_RE.finditer(joined):
        name = _clean(m.group("name")).lower()
        code = next((c for key, c in _SECTION_CODES if key in name), None)
        if code:
            sections.append((m.start(), code))

    subs: List[Tuple[int, str]] = [
        (m.start(), _clean(m.group("name"))) for m in _SUBSECTION_RE.finditer(joined)
    ]

    def sub_at(offset: int) -> Optional[str]:
        name = None
        for begin, n in subs:
            if begin <= offset:
                name = n
            else:
                break
        return name

    def section_at(offset: int) -> Optional[str]:
        code = None
        for begin, c in sections:
            if begin <= offset:
                code = c
            else:
                break
        return code

    matches = list(_FINDING_RE.finditer(joined))
    findings: List[CountyFinding] = []
    for n, match in enumerate(matches):
        end = matches[n + 1].start() if n + 1 < len(matches) else len(joined)
        body = joined[match.start() : end].strip()
        findings.append(
            CountyFinding(
                paragraph_no=int(match.group("no")),
                section=section_at(match.start()),
                sub_section=sub_at(match.start()),
                title=_clean(match.group("title")),
                finding_text=body,
                pdf_page=page_at(match.start()),
                amounts=parse_amounts(body),
            )
        )
    return findings, rejected


def build_result(
    pages: List[Tuple[int, str]],
    *,
    known_counties: Optional[Dict[str, str]] = None,
) -> CountyAuditResult:
    """Apply every gate and return the publishable result, or raise.

    Pure: takes page text and decides. Kept separate from the PDF walk so each
    gate has a test that makes it FIRE.
    """
    head = "\n".join(t for _, t in pages[:3])

    auditee = parse_auditee(head)
    if not auditee:
        raise CountyAuditError(
            "auditee_not_found",
            "no 'REPORT OF THE AUDITOR-GENERAL ON <entity>' title line",
        )

    county = county_of(auditee, known_counties)
    if not county:
        raise CountyAuditError(
            "county_not_resolved",
            f"{auditee!r} does not resolve to a known county",
        )

    fiscal_year = parse_fiscal_year(head)
    if not fiscal_year:
        raise CountyAuditError(
            "fiscal_year_not_found",
            "no 'FOR THE YEAR ENDED <d> <month>, <yyyy>' line; a finding "
            "without a year cannot be filed against one",
        )

    opinion = parse_opinion("\n".join(t for _, t in pages))
    if opinion not in OPINIONS:
        raise CountyAuditError(
            "opinion_not_recognised",
            f"{opinion!r} is not one of {OPINIONS}",
        )

    findings, rejected = parse_findings(pages)
    if not findings:
        raise CountyAuditError(
            "no_findings_extracted",
            f"{len(pages)} page(s) read, {rejected} rejected for cid glyphs, "
            f"no numbered finding headings matched",
        )

    return CountyAuditResult(
        auditee=auditee,
        county_name=county,
        fiscal_year_label=fiscal_year,
        opinion=opinion,
        findings=findings,
        rejected_cid=rejected,
    )


def finding_to_extracted_json(
    f: CountyFinding, result: CountyAuditResult
) -> dict:
    return {
        "schema": "oag_county_audit/v1",
        "auditee": result.auditee,
        "county_name": result.county_name,
        "entity_name": result.auditee,
        "fiscal_year": result.fiscal_year_label,
        "paragraph_no": f.paragraph_no,
        "section": f.section,
        "sub_section": f.sub_section,
        "title": f.title,
        "finding_text": f.finding_text,
        "pdf_page": f.pdf_page,
        "opinion": result.opinion,
        "severity": severity_for(result.opinion),
        "amounts": f.amounts,
        "extraction_method": f.method,
    }


def source_hash_of(extracted_json: dict) -> str:
    """sha256 over the canonical JSON — lets anyone re-check the row."""
    canonical = json.dumps(extracted_json, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _known_counties(session) -> Dict[str, str]:
    """{normalised county name: canonical name} for the resolution gate."""
    try:
        from models import Entity, EntityType

        rows = (
            session.query(Entity).filter(Entity.type == EntityType.COUNTY).all()
        )
    except Exception:  # pragma: no cover - resolution then falls back to None
        return {}
    out: Dict[str, str] = {}
    for e in rows:
        name = re.sub(r"\s+County$", "", e.canonical_name or "", flags=re.I).strip()
        if name:
            out[re.sub(r"[^a-z]", "", name.lower())] = name
    return out


def read_pages(pdf_path) -> List[Tuple[int, str]]:
    """(1-based page number, text) for every page.

    A file that is not a readable PDF quarantines with a reason rather than
    raising out of the domain. OAG rotates its URLs, and a 404 there returns
    an HTML error page which gets saved with a .pdf name — pdfminer then
    raises "No /Root object!", which without this would abort the whole audits
    run instead of skipping one document.
    """
    import pdfplumber

    try:
        with pdfplumber.open(pdf_path) as pdf:
            return [(n + 1, p.extract_text() or "") for n, p in enumerate(pdf.pages)]
    except CountyAuditError:
        raise
    except Exception as exc:
        raise CountyAuditError(
            "pdf_unreadable", f"{type(exc).__name__}: {str(exc)[:160]}"
        ) from exc


def is_consolidated(pages: List[Tuple[int, str]]) -> bool:
    """True for a multi-county volume rather than a single-entity report."""
    head = "\n".join(t for _, t in pages[:3])
    return bool(_CONSOLIDATED_RE.search(re.sub(r"\s+", " ", head)))


def extract_county_audit(session, doc, settings) -> dict:
    """Extract ``doc`` (a fetched county audit report) into extraction rows.

    One row per finding, ``page_number`` = 1-based PDF page. Idempotent: rows
    already written by this extractor for an unchanged document are left
    alone. Returns a stats dict; raises ``CountyAuditError`` when the document
    cannot identify itself, so the caller records a reason rather than
    publishing a guess.
    """
    from models import Extraction

    if not doc.file_path or not Path(doc.file_path).exists():
        raise FileNotFoundError(f"county audit file missing: {doc.file_path!r}")

    existing = (
        session.query(Extraction)
        .filter(
            Extraction.source_document_id == doc.id,
            Extraction.extractor == EXTRACTOR_ID,
        )
        .count()
    )
    if existing:
        return {
            "created": 0,
            "skipped": existing,
            "rejected_cid": 0,
            "reason": "already_extracted",
        }

    pages = read_pages(doc.file_path)

    if is_consolidated(pages):
        # 47 counties behind a table of contents — the Blue Book walk reads
        # this shape (it was taught the county TOC and heading forms); the
        # single-entity path below would refuse it with auditee_not_found.
        from .oag_blue_book import extract_blue_book

        logger.info(
            "oag_county_audit: %s is a consolidated volume — delegating to "
            "the Blue Book walk",
            doc.url or doc.id,
        )
        stats = extract_blue_book(session, doc, settings)
        stats["shape"] = "consolidated"
        return stats

    result = build_result(pages, known_counties=_known_counties(session))

    created = 0
    for f in result.findings:
        payload = finding_to_extracted_json(f, result)
        session.add(
            Extraction(
                source_document_id=doc.id,
                page_number=f.pdf_page,
                extracted_json=payload,
                extractor=EXTRACTOR_ID,
                confidence=0.90 if f.method == "pdfplumber" else 0.60,
                source_hash=source_hash_of(payload),
            )
        )
        created += 1

    logger.info(
        "oag_county_audit: %s %s (%s opinion) -> %d finding(s), %d page(s) "
        "rejected for cid glyphs",
        result.county_name,
        result.fiscal_year_label,
        result.opinion,
        created,
        result.rejected_cid,
    )
    return {
        "created": created,
        "skipped": 0,
        "rejected_cid": result.rejected_cid,
        "county": result.county_name,
        "fiscal_year": result.fiscal_year_label,
        "opinion": result.opinion,
        "shape": "single_entity",
    }

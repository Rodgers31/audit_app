"""
Heuristic audit parser for OAG/COB PDFs.
Extracts audit findings (queries) with fields suitable for persistence and caching.

Approach:
- Use text from pages and any extracted tables to find lines or rows that look like audit findings.
- Detect amounts (KES/USD), severity keywords, recommendations, and fiscal period.
- Infer entity (county) from document title or content.
- Extract audit opinion, classify query types, extract management responses.

This is a best-effort MVP parser; it favors recall over precision and adds confidence scores
and provenance for downstream review and triage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .normalizer import DataNormalizer
except Exception:  # pragma: no cover - fallback for script imports
    from normalizer import DataNormalizer

# Optional OCR
try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    pytesseract = None  # type: ignore
    Image = None  # type: ignore


# Minimal county list for entity inference; can be expanded or loaded from DB later
COUNTY_NAMES: List[str] = [
    "Nairobi",
    "Mombasa",
    "Kisumu",
    "Nakuru",
    "Kiambu",
    "Machakos",
    "Uasin Gishu",
    "Kajiado",
    "Kakamega",
    "Bungoma",
    "Kericho",
    "Bomet",
    "Turkana",
    "West Pokot",
    "Samburu",
    "Trans Nzoia",
    "Elgeyo Marakwet",
    "Nandi",
    "Baringo",
    "Laikipia",
    "Narok",
    "Siaya",
    "Homa Bay",
    "Migori",
    "Kisii",
    "Nyamira",
    "Busia",
    "Vihiga",
    "Embu",
    "Meru",
    "Tharaka Nithi",
    "Kitui",
    "Makueni",
    "Nyandarua",
    "Nyeri",
    "Kirinyaga",
    "Garissa",
    "Wajir",
    "Mandera",
    "Marsabit",
    "Isiolo",
    "Kilifi",
    "Tana River",
    "Lamu",
    "Taita Taveta",
]


SEVERITY_KEYWORDS = {
    "critical": [
        "irregular expenditure",
        "unsupported payment",
        "unaccounted",
        "embezzlement",
        "misappropriation",
        "fraud",
    ],
    "warning": [
        "non-compliance",
        "late submission",
        "procurement issue",
        "weak controls",
        "pending bills",
    ],
}

OAG_SECTION_CUES = [
    r"management responses?",
    r"audit findings?",
    r"recommendations?",
    r"basis of opinion",
    r"qualified opinion|adverse opinion|disclaimer",
]

# --- Opinion extraction ---
OPINION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bdisclaimer\s+of\s+opinion\b", re.I), "Disclaimer"),
    (re.compile(r"\badverse\s+opinion\b", re.I), "Adverse"),
    (re.compile(r"\bunqualified\s+opinion\b", re.I), "Unqualified"),
    (re.compile(r"\bqualified\s+opinion\b", re.I), "Qualified"),
]

# --- Query-type classification keywords ---
QUERY_TYPE_RULES: List[Tuple[str, List[str]]] = [
    (
        "Financial Irregularity",
        [
            "missing funds",
            "unaccounted",
            "irregular payment",
            "unsupported payment",
            "unsupported expenditure",
            "irregular expenditure",
            "misappropriation",
            "embezzlement",
            "fraud",
            "loss of funds",
        ],
    ),
    (
        "Asset Management",
        [
            "missing asset",
            "unverified asset",
            "disposal without authority",
            "asset register",
            "unaccounted assets",
            "idle assets",
            "asset management",
        ],
    ),
    (
        "Procurement",
        [
            "tender irregular",
            "single sourc",
            "price inflation",
            "procurement irregular",
            "procurement process",
            "direct procurement",
            "restricted tender",
            "procurement plan",
        ],
    ),
    (
        "Non-Compliance",
        [
            "non-compliance",
            "failure to comply",
            "contrary to",
            "violation of",
            "statutory requirement",
            "not in accordance",
            "failed to follow",
        ],
    ),
    (
        "Payroll/HR",
        [
            "ghost worker",
            "salary irregular",
            "unapproved allowance",
            "payroll",
            "staff cost",
            "personnel emolument",
            "human resource",
        ],
    ),
    (
        "Revenue Under-Collection",
        [
            "revenue under-collection",
            "own-source revenue",
            "revenue shortfall",
            "revenue target",
            "uncollected revenue",
            "below target",
        ],
    ),
    (
        "Cash Management",
        [
            "bank reconciliation",
            "overdraft",
            "cash management",
            "cash book",
            "unreconciled",
            "cash balance",
            "imprest",
        ],
    ),
    (
        "Weak Internal Controls",
        [
            "missing documentation",
            "approval gap",
            "weak internal control",
            "weak controls",
            "internal control",
            "lack of documentation",
            "inadequate documentation",
            "segregation of duties",
        ],
    ),
]

# --- KES amount patterns for structured extraction ---
KES_AMOUNT_PATTERNS: List[re.Pattern] = [
    re.compile(
        r"(?:KES|Ksh\.?|KSh\.?|Kshs\.?|K\.Sh\.?|Sh\.?)\s*([\d,]+(?:\.\d+)?)\s*(million|billion|thousand)?",
        re.I,
    ),
    re.compile(
        r"([\d,]+(?:\.\d+)?)\s*(?:million|billion|thousand)?\s*(?:KES|Ksh|KSh)",
        re.I,
    ),
]

MULTIPLIER_MAP = {
    "million": Decimal("1000000"),
    "billion": Decimal("1000000000"),
    "thousand": Decimal("1000"),
}

# --- Management response section headers ---
MGMT_RESPONSE_PATTERNS: List[re.Pattern] = [
    re.compile(
        r"^(?:management|entity|auditee)\s+response[s:]?",
        re.I | re.MULTILINE,
    ),
    re.compile(
        r"^(?:response\s+by\s+management|management\s+comment)[s:]?",
        re.I | re.MULTILINE,
    ),
]


@dataclass
class AuditFinding:
    finding_text: str
    severity: str
    amount: Optional[Dict[str, Any]]
    recommended_action: Optional[str]
    period: Optional[Dict[str, Any]]
    entity: Optional[Dict[str, Any]]
    provenance: Dict[str, Any]
    query_type: Optional[str] = None
    amount_kes: Optional[Decimal] = None
    management_response: Optional[str] = None


class AuditParser:
    def __init__(self) -> None:
        self.normalizer = DataNormalizer()

    # ------------------------------------------------------------------
    # Opinion extraction
    # ------------------------------------------------------------------
    def extract_opinion(self, full_text: str) -> Optional[str]:
        """Extract audit opinion from report text.

        Returns one of: "Unqualified", "Qualified", "Adverse", "Disclaimer"
        or None if no opinion pattern found.  Order matters — "Disclaimer of
        Opinion" is checked before "Qualified Opinion" so that "Disclaimer"
        wins when both might match partial text.
        """
        for pattern, label in OPINION_PATTERNS:
            if pattern.search(full_text):
                return label
        return None

    # ------------------------------------------------------------------
    # Structured KES amount extraction
    # ------------------------------------------------------------------
    def extract_kes_amount(self, text: str) -> Optional[Decimal]:
        """Parse the first KES-denominated amount from *text* into a Decimal value in KES."""
        for pat in KES_AMOUNT_PATTERNS:
            m = pat.search(text)
            if m:
                try:
                    raw = m.group(1).replace(",", "")
                    value = Decimal(raw)
                    # Check for multiplier word
                    multiplier_word = None
                    if m.lastindex and m.lastindex >= 2:
                        multiplier_word = m.group(2)
                    if multiplier_word:
                        value *= MULTIPLIER_MAP.get(
                            multiplier_word.lower(), Decimal("1")
                        )
                    elif re.search(r"\bmillion\b", text[m.end() : m.end() + 20], re.I):
                        value *= MULTIPLIER_MAP["million"]
                    elif re.search(r"\bbillion\b", text[m.end() : m.end() + 20], re.I):
                        value *= MULTIPLIER_MAP["billion"]
                    return value
                except (InvalidOperation, IndexError):
                    continue
        return None

    # ------------------------------------------------------------------
    # Query-type classification
    # ------------------------------------------------------------------
    def classify_query_type(self, text: str) -> Optional[str]:
        """Classify a finding into a query_type category using keyword matching."""
        tl = text.lower()
        for category, keywords in QUERY_TYPE_RULES:
            if any(kw in tl for kw in keywords):
                return category
        return None

    # ------------------------------------------------------------------
    # Management response extraction
    # ------------------------------------------------------------------
    def extract_management_responses(self, full_text: str) -> List[str]:
        """Extract management response sections from the full document text.

        Returns a list of response text blocks found.
        """
        responses: List[str] = []
        for pat in MGMT_RESPONSE_PATTERNS:
            for m in pat.finditer(full_text):
                start = m.end()
                # Grab text until the next section header or end of text (max 2000 chars)
                remaining = full_text[start : start + 2000]
                # Stop at next section header-like line
                end_m = re.search(
                    r"\n\s*(?:\d+\.?\s+)?[A-Z][A-Z ]{5,}",
                    remaining,
                )
                if end_m:
                    remaining = remaining[: end_m.start()]
                cleaned = remaining.strip()
                if cleaned:
                    responses.append(cleaned)
        return responses

    # ------------------------------------------------------------------
    # Recurring findings detection
    # ------------------------------------------------------------------
    @staticmethod
    def detect_recurring_findings(
        findings_by_year: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Flag findings where the same query_type appears in 2+ consecutive years.

        *findings_by_year* is a list of dicts each having at least:
          - "query_type": str
          - "audit_year": int (or "year")
          - any other fields (passed through)

        Returns a list of dicts with an added "recurring" boolean and
        "recurring_years" list for findings that are recurring.
        """
        if not findings_by_year:
            return []

        # Group by query_type
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for f in findings_by_year:
            qt = f.get("query_type")
            if not qt:
                continue
            by_type.setdefault(qt, []).append(f)

        recurring_keys: set = set()
        for qt, items in by_type.items():
            years = sorted(
                {int(it.get("audit_year") or it.get("year", 0)) for it in items}
            )
            years = [y for y in years if y > 0]
            # Check for consecutive years
            for i in range(len(years) - 1):
                if years[i + 1] - years[i] == 1:
                    recurring_keys.add(qt)
                    break

        result: List[Dict[str, Any]] = []
        for f in findings_by_year:
            enriched = dict(f)
            qt = f.get("query_type")
            if qt and qt in recurring_keys:
                enriched["recurring"] = True
                # Collect all years for this query_type
                enriched["recurring_years"] = sorted(
                    {
                        int(it.get("audit_year") or it.get("year", 0))
                        for it in by_type[qt]
                        if int(it.get("audit_year") or it.get("year", 0)) > 0
                    }
                )
            else:
                enriched["recurring"] = False
            result.append(enriched)
        return result

    # ------------------------------------------------------------------
    # Existing helpers (unchanged)
    # ------------------------------------------------------------------
    def infer_entity(
        self, title: str, pages: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        # Prefer title-based inference
        text = title or ""
        for county in COUNTY_NAMES:
            if county.lower() in text.lower():
                return {
                    "canonical_name": f"{county} County",
                    "type": "county",
                    "confidence": 0.9,
                    "raw_name": county,
                    "category": "counties",
                }

        # Fallback: first page text
        if pages:
            page_text = pages[0].get("text", "")
            for county in COUNTY_NAMES:
                if county.lower() in page_text.lower():
                    return {
                        "canonical_name": f"{county} County",
                        "type": "county",
                        "confidence": 0.6,
                        "raw_name": county,
                        "category": "counties",
                    }
        return None

    def classify_severity(self, text: str, amount_kes: Optional[float]) -> str:
        tl = text.lower()
        for sev, keys in SEVERITY_KEYWORDS.items():
            if any(k in tl for k in keys):
                return sev
        if amount_kes and amount_kes >= 50_000_000:  # >= 50M KES → critical
            return "critical"
        if amount_kes and amount_kes >= 5_000_000:
            return "warning"
        return "info"

    def extract_recommendation(self, text: str) -> Optional[str]:
        m = re.search(r"recommendation[:\-]\s*(.+)$", text, re.I)
        return m.group(1).strip() if m else None

    def parse_from_text_lines(
        self,
        text: str,
        page_number: int,
        period_hint: Optional[Dict[str, Any]],
        entity_hint: Optional[Dict[str, Any]],
    ) -> List[AuditFinding]:
        findings: List[AuditFinding] = []
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for ln in lines:
            # Heuristic: lines containing money plus an audit cue
            if (
                re.search(r"\b(KES|Ksh|KSh|US\$|USD|,\d{3})\b", ln, re.I)
                or re.search(
                    r"audit|query|finding|irregular|unaccounted|pending bills|procurement|unsupported|vouch|loss|embezzlement",
                    ln,
                    re.I,
                )
                or any(re.search(cue, ln, re.I) for cue in OAG_SECTION_CUES)
            ):
                try:
                    amt = self.normalizer.normalize_amount(ln) or None
                except Exception:
                    amt = None
                amount_kes_float = amt.get("base_amount") if amt else None
                sev = self.classify_severity(ln, amount_kes_float)
                rec = self.extract_recommendation(ln)
                kes_decimal = self.extract_kes_amount(ln)
                qt = self.classify_query_type(ln)
                findings.append(
                    AuditFinding(
                        finding_text=ln,
                        severity=sev,
                        amount=amt,
                        recommended_action=rec,
                        period=period_hint,
                        entity=entity_hint,
                        provenance={"page": page_number, "line": ln[:80]},
                        query_type=qt,
                        amount_kes=kes_decimal,
                    )
                )
        return findings

    def parse_tables(
        self,
        tables: List[Dict[str, Any]],
        period_hint: Optional[Dict[str, Any]],
        entity_hint: Optional[Dict[str, Any]],
    ) -> List[AuditFinding]:
        findings: List[AuditFinding] = []
        for t in tables:
            # Different extractors store differently
            page = t.get("page") or t.get("data", {}).get("page_number") or 1
            headers = t.get("headers") or t.get("data", {}).get("headers") or []
            rows = t.get("rows") or t.get("data", {}).get("rows") or []
            # Identify typical columns
            joined_headers = " ".join([str(h).lower() for h in headers])
            has_description = re.search(
                r"description|finding|query|issue", joined_headers
            )
            has_amount = re.search(r"amount|kes|ksh|value", joined_headers)
            for row in rows:
                cells = [str(c) for c in row]
                text_blob = " ".join(cells)
                if (
                    has_description
                    or has_amount
                    or re.search(r"audit|query|finding|issue", text_blob, re.I)
                ):
                    try:
                        amt = self.normalizer.normalize_amount(text_blob) or None
                    except Exception:
                        amt = None
                    amount_kes_float = amt.get("base_amount") if amt else None
                    sev = self.classify_severity(text_blob, amount_kes_float)
                    rec = self.extract_recommendation(text_blob)
                    kes_decimal = self.extract_kes_amount(text_blob)
                    qt = self.classify_query_type(text_blob)
                    findings.append(
                        AuditFinding(
                            finding_text=text_blob,
                            severity=sev,
                            amount=amt,
                            recommended_action=rec,
                            period=period_hint,
                            entity=entity_hint,
                            provenance={
                                "page": page,
                                "table_index": t.get("table_index", 0),
                            },
                            query_type=qt,
                            amount_kes=kes_decimal,
                        )
                    )
        return findings

    def detect_period(
        self, title: str, pages: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        # Title hint
        p = self.normalizer.normalize_fiscal_period(title)
        if p:
            return p
        # First 2 pages
        for pg in pages[:2]:
            p = self.normalizer.normalize_fiscal_period(pg.get("text", ""))
            if p:
                return p
        return None

    def parse(
        self, extraction_result: Dict[str, Any], doc_meta: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Return normalized audit findings ready for DB or cache."""
        pages = extraction_result.get("pages", [])
        # OCR fallback if no text extracted
        if not pages and pytesseract is not None and Image is not None:
            # Attempt naive OCR on first few pages if images are provided (out-of-scope here);
            # left as a hook for future enhancement where page images are available.
            pass
        tables = []
        # Normalize table listing across extractors
        for t in extraction_result.get("tables", []) or []:
            if "data" in t:
                d = t["data"]
                d["page"] = t.get("page") or d.get("page")
                d["table_index"] = t.get("table_index", d.get("table_index", 0))
                tables.append(d)
            else:
                tables.append(t)

        title = doc_meta.get("title") or Path(doc_meta.get("file_path", "")).name
        entity_hint = self.infer_entity(title, pages)
        period_hint = self.detect_period(title, pages)

        # Build full text for document-level extraction
        full_text = "\n".join(pg.get("text", "") for pg in pages)

        # Document-level: opinion and management responses
        audit_opinion = self.extract_opinion(full_text)
        mgmt_responses = self.extract_management_responses(full_text)

        findings: List[AuditFinding] = []
        # From text pages
        for pg in pages:
            text = pg.get("text", "")
            if text:
                findings.extend(
                    self.parse_from_text_lines(
                        text, pg.get("page_number", 1), period_hint, entity_hint
                    )
                )
        # From tables
        findings.extend(self.parse_tables(tables, period_hint, entity_hint))

        # Deduplicate by text+page
        seen = set()
        unique: List[Dict[str, Any]] = []
        for f in findings:
            key = (f.finding_text.strip(), f.provenance.get("page"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(
                {
                    "finding_text": f.finding_text,
                    "severity": f.severity,
                    "recommended_action": f.recommended_action,
                    "amount": f.amount,
                    "amount_kes": float(f.amount_kes) if f.amount_kes is not None else None,
                    "fiscal_period": f.period,
                    "entity": f.entity,
                    "provenance": f.provenance,
                    "confidence": 0.6,  # heuristic baseline
                    "query_type": f.query_type,
                    "audit_opinion": audit_opinion,
                    "management_response": f.management_response,
                }
            )

        # Assign management responses to findings (first response to first finding, etc.)
        for i, resp in enumerate(mgmt_responses):
            if i < len(unique):
                unique[i]["management_response"] = resp
            else:
                break

        return unique


if __name__ == "__main__":  # Simple smoke test scaffold
    ap = AuditParser()
    example = {
        "extractor": "pdfplumber",
        "pages": [
            {
                "page_number": 1,
                "text": (
                    "County Government of Nairobi\n"
                    "Financial Year 2022/23\n"
                    "Qualified Opinion\n"
                    "Finding: Unsupported payment of KES 12,345,678 for procurement...\n"
                    "Recommendation: Recover the amount.\n"
                    "Management Response:\n"
                    "The county government has initiated recovery proceedings."
                ),
            }
        ],
        "tables": [],
    }
    meta = {
        "title": "Nairobi County – Audit Report FY 2022/23",
        "file_path": "sample.pdf",
    }
    out = ap.parse(example, meta)
    print(f"Parsed findings: {len(out)}")
    for f in out:
        print(f"  Opinion: {f.get('audit_opinion')}")
        print(f"  Query type: {f.get('query_type')}")
        print(f"  Amount KES: {f.get('amount_kes')}")
        print(f"  Mgmt response: {f.get('management_response', '')[:60]}")

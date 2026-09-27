"""Actual expenditure by sector from the COB *annual* National Government BIRR.

Why this exists
---------------
The /budget "audit lens" asks, per sector, how much of the approved budget
was actually SPENT by year-end. The NG-BIRR tables the domain already parsed
(2.4/2.5 and 2.6, ``pdf_parser.py``) cannot answer that: they give Net
Estimates against **Exchequer Issues** — cash Treasury released — which is
not expenditure. For ARUD in FY 2025/26 the recurrent line reads 21.77 net /
21.71 exchequer, while the sector actually spent 35.94 against a revised
gross estimate of 45.39 (issue #241).

Every annual NG-BIRR carries the answer in Section 4: one
"Table 4.x: <SECTOR> Sector-Analysis of Exchequer Issues and Expenditure"
per sector, each closing with a **Sector Summary**::

    Sector Summary
                  Revised Gross  Revised Net  Exchequer  Expenditure  %Exch/Net  %Exp/Gross
    Development   72.02          65.64        64.57      68.04        98         94
    Recurrent     45.39          21.77        21.71      35.94        100        79
    Total         117.41         87.41        86.28      103.98       99         89

and a prose sentence restating the total ("The total expenditure for the
ARUD Sector amounted to Kshs.103.98 billion, representing 89 per cent…").

What is published, and on what evidence
---------------------------------------
Parsing is best-effort (pdfplumber interleaves wrapped header cells into the
rows, splits "377.50" as "377.5 0", and spills a summary onto the next page).
Publication is not. A sector's TOTAL is accepted only when:

* its printed ratios agree with its own figures — expenditure / gross within
  one point of COB's "% of Expenditure to Gross", exchequer / net within one
  point of "% of Exchequer to Net"; AND
* either the sector's prose states the same total expenditure, or
  Development + Recurrent reproduces the Total row.

The Development / Recurrent split is published only when it reproduces the
Total. It does not always: the FY 2025/26 report's National Security
Recurrent row (248.84 / 241.01 / 189.23 / 201.48) is the NINE-MONTH figure
carried over by mistake, while its Total (291.40 / … / 289.73) agrees with
the prose. That sector's total is published; its split is withheld, with
the reason.

A sector that fails is reported as missing — never filled with 0.

Coverage: the ten sectors are the entire ministerial (MDA) budget. Their
Totals are checked against Table 3.1's MDA recurrent + development
expenditure (FY 2025/26: 2,770.99 vs 2,771.02). Consolidated Fund Services
(debt service, pensions, constitutional salaries) are outside the sectors
and are named as excluded, not silently absent.

Units: Sector Summary figures are KSh billions (the tables say "Kshs. Bn";
the Table 3.1 reconciliation would expose a unit slip).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Mapping, Optional, Tuple

# COB's ten sectors: (code used in the Section-4 headings, canonical name).
# Canonical names are the ones ``pdf_parser`` already writes, so the same
# sector keeps one name across both parsers.
SECTORS: Tuple[Tuple[str, str], ...] = (
    ("ARUD", "Agriculture, Rural and Urban Development"),
    ("Education", "Education"),
    ("EIICT", "Energy, Infrastructure and ICT"),
    ("EPWNR", "Environment Protection, Water, and Natural Resources"),
    ("GECA", "General Economic and Commercial Affairs"),
    ("GJLO", "Governance, Justice, Law and Order"),
    ("Health", "Health"),
    ("National Security", "National Security"),
    ("PAIR", "Public Administration and International Relations"),
    ("SPCR", "Social Protection, Culture and Recreation"),
)
_CODE_TO_NAME = {code.lower(): name for code, name in SECTORS}

#: What an execution row DECLARES it measures (BudgetLine provenance). The
#: /budget/enhanced execution panel publishes only rows declaring
#: ``EXPENDITURE_MEASURE``; the quarterly parser's rows declare
#: ``EXCHEQUER_MEASURE`` against net estimates.
EXPENDITURE_MEASURE = "expenditure"
EXCHEQUER_MEASURE = "exchequer_issues"
ALLOCATION_MEASURE = "revised_gross_estimates"

#: How far a recomputed percentage may sit from COB's printed (integer) one.
RATIO_TOLERANCE_PCT = Decimal("1.0")
#: Development + Recurrent may differ from Total by this much (2-dp rounding
#: on three cells).
SPLIT_TOLERANCE_BN = Decimal("0.05")
#: Sector prose total vs the Total row — both printed to 2 dp.
PROSE_TOLERANCE_BN = Decimal("0.01")
#: Sum of sector Totals vs Table 3.1 MDA expenditure.
COVERAGE_TOLERANCE_BN = Decimal("1.0")

_HEADING_RE = re.compile(
    r"Table\s+(4\.\d+)\s*:\s*(ARUD|Education|EIICT|EPWNR|GECA|GJLO|Health|"
    r"National\s+Security|PAIR|SPCR)\b[^\n]*?Analysis\s+of\s+Exchequer\s+"
    r"Issues\s+and\s+Expenditure",
    re.IGNORECASE,
)
_PROSE_RE = re.compile(
    r"total\s+expenditure\s+(?:for|by|of|in)\s+the\s+(?P<who>.{2,80}?)\s+"
    r"amounted\s+to\s+Kshs?\.?\s*(?P<num>[\d,]+(?:\.\d+)?)\s*(?P<unit>billion|trillion)",
    re.IGNORECASE | re.DOTALL,
)
_RUNNING_HEADER_RE = re.compile(
    r"^\s*(?:NATIONAL GOVERNMENT BUDGET IMPLEMENTATION REVIEW REPORT.*"
    r"|FY\s*20\d\d\s*/\s*20?\d\d\s+[A-Z]+,\s*20\d\d(?:\s+\d{1,3})?"
    r"|\d{1,3}(?:\s+FY\s*20\d\d\s*/\s*20?\d\d\s+[A-Z]+,\s*20\d\d)?)\s*$",
)
_ROW_LABEL_RE = re.compile(r"^(Development|Recurrent|Total)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"^\(?-?[\d,]*\d(?:\.\d+)?\)?%?$")


@dataclass(frozen=True)
class SummaryRow:
    """One Sector Summary row, KSh billions / printed integer percentages."""

    gross: Decimal
    net: Decimal
    exchequer: Decimal
    expenditure: Decimal
    pct_exchequer_to_net: Decimal
    pct_expenditure_to_gross: Decimal

    def ratio_problems(self) -> List[str]:
        """Where the row's own ratios disagree with its printed percentages."""
        out: List[str] = []
        if self.gross <= 0 or self.net <= 0:
            out.append("non-positive estimate")
            return out
        exp_pct = self.expenditure / self.gross * 100
        exch_pct = self.exchequer / self.net * 100
        if abs(exp_pct - self.pct_expenditure_to_gross) > RATIO_TOLERANCE_PCT:
            out.append(
                f"expenditure/gross = {exp_pct:.1f}% but COB prints "
                f"{self.pct_expenditure_to_gross}%"
            )
        if abs(exch_pct - self.pct_exchequer_to_net) > RATIO_TOLERANCE_PCT:
            out.append(
                f"exchequer/net = {exch_pct:.1f}% but COB prints "
                f"{self.pct_exchequer_to_net}%"
            )
        return out

    def as_dict(self) -> Dict[str, str]:
        return {
            "revised_gross_bn": str(self.gross),
            "revised_net_bn": str(self.net),
            "exchequer_bn": str(self.exchequer),
            "expenditure_bn": str(self.expenditure),
            "pct_exchequer_to_net": str(self.pct_exchequer_to_net),
            "pct_expenditure_to_gross": str(self.pct_expenditure_to_gross),
        }


@dataclass
class SectorResult:
    code: str
    sector: str
    table: str
    heading_page: int
    summary_page: Optional[int] = None
    development: Optional[SummaryRow] = None
    recurrent: Optional[SummaryRow] = None
    total: Optional[SummaryRow] = None
    prose_expenditure_bn: Optional[Decimal] = None
    prose_page: Optional[int] = None
    checks: Dict[str, bool] = field(default_factory=dict)
    accepted: bool = False
    split_published: bool = False
    problems: List[str] = field(default_factory=list)


@dataclass
class AnnualSectorExpenditure:
    sectors: List[SectorResult]
    mda_expenditure_bn: Optional[Decimal] = None
    mda_gross_bn: Optional[Decimal] = None
    cfs_expenditure_bn: Optional[Decimal] = None
    table_3_1_page: Optional[int] = None

    @property
    def accepted(self) -> List[SectorResult]:
        return [s for s in self.sectors if s.accepted]

    @property
    def missing(self) -> List[str]:
        found = {s.sector for s in self.accepted}
        return [name for _, name in SECTORS if name not in found]

    def coverage(self) -> Dict[str, object]:
        """How much of Table 3.1's MDA expenditure the accepted sectors cover."""
        total = sum(
            (s.total.expenditure for s in self.accepted if s.total), Decimal("0")
        )
        out: Dict[str, object] = {
            "sectors_expected": len(SECTORS),
            "sectors_reported": len(self.accepted),
            "sectors_missing": self.missing,
            "sector_expenditure_bn": str(total),
            "mda_expenditure_bn": (
                str(self.mda_expenditure_bn) if self.mda_expenditure_bn is not None else None
            ),
            "cfs_expenditure_bn": (
                str(self.cfs_expenditure_bn) if self.cfs_expenditure_bn is not None else None
            ),
            "table_3_1_page": self.table_3_1_page,
        }
        if self.mda_expenditure_bn is None:
            # Unverified is not "reconciles": the reader must be able to tell.
            out["reconciles"] = None
        else:
            out["reconciles"] = (
                abs(total - self.mda_expenditure_bn) <= COVERAGE_TOLERANCE_BN
            )
        return out


# ─────────────────────────────────────────────────────────────────────────
# Text helpers
# ─────────────────────────────────────────────────────────────────────────


def _strip_running_lines(text: str) -> str:
    """Drop the report's running header/footer lines ("NATIONAL GOVERNMENT
    BUDGET IMPLEMENTATION REVIEW REPORT", "FY 2025/26 AUGUST, 2026 63", a
    bare page number) — they land mid-table when a summary spills over."""
    return "\n".join(
        line for line in (text or "").split("\n") if not _RUNNING_HEADER_RE.match(line)
    )


def _to_decimal(token: str) -> Optional[Decimal]:
    cleaned = token.strip().strip("()%").replace(",", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _numeric_tokens(text: str) -> List[str]:
    """Whitespace tokens that are numbers, with pdfplumber's split decimal
    ("377.5 0" for 377.50) re-joined. Every figure in these tables carries two
    decimals, so a one-decimal token followed by a lone digit is one cell."""
    raw = [t for t in text.split() if _NUMBER_RE.match(t)]
    out: List[str] = []
    i = 0
    while i < len(raw):
        tok = raw[i]
        if (
            re.fullmatch(r"\d[\d,]*\.\d", tok)
            and i + 1 < len(raw)
            and re.fullmatch(r"\d", raw[i + 1])
        ):
            out.append(tok + raw[i + 1])
            i += 2
            continue
        out.append(tok)
        i += 1
    return out


def _parse_summary_block(block: str) -> Dict[str, SummaryRow]:
    """``{"development"|"recurrent"|"total": SummaryRow}`` from the text between
    "Sector Summary" and "Source:". A label claims the next six numbers that
    follow it, reading across line breaks, until the next label."""
    rows: Dict[str, SummaryRow] = {}
    # Split into (label, text-after-label) segments.
    parts = re.split(r"\b(Development|Recurrent|Total)\b", block)
    # parts = [preamble, label1, body1, label2, body2, ...]
    for label, body in zip(parts[1::2], parts[2::2]):
        key = label.lower()
        if key in rows:
            continue
        nums = [_to_decimal(t) for t in _numeric_tokens(body)][:6]
        if len(nums) < 6 or any(n is None for n in nums):
            continue
        rows[key] = SummaryRow(*nums)  # type: ignore[arg-type]
    return rows


def _prose_for(sector_code: str, sector_name: str, text: str) -> Optional[Decimal]:
    """The sector's "total expenditure … amounted to Kshs.X billion" figure."""
    for m in _PROSE_RE.finditer(text):
        who = " ".join(m.group("who").split()).lower()
        if sector_code.lower() not in who and sector_name.lower() not in who:
            continue
        value = _to_decimal(m.group("num"))
        if value is None:
            continue
        if m.group("unit").lower() == "trillion":
            value *= 1000
        return value
    return None


# ─────────────────────────────────────────────────────────────────────────
# Table 3.1 — MDA / CFS expenditure for the coverage check
# ─────────────────────────────────────────────────────────────────────────


def _amounts(text: str) -> List[Decimal]:
    """The money cells in ``text``, in order. Amounts in these tables always
    carry decimals and percentages never do, which is what tells them apart
    when a wrapped row prints its percentages first."""
    out: List[Decimal] = []
    for tok in _numeric_tokens(text):
        if "." in tok:
            value = _to_decimal(tok)
            if value is not None:
                out.append(value)
    return out


def _parse_table_3_1(
    pages: Mapping[int, str],
) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal], Optional[int]]:
    """``(mda_gross, mda_expenditure, cfs_expenditure, page)`` for the report
    year from Table 3.1 "Overall Budget Performance".

    MDA expenditure = ": MDAs" recurrent row + the "Development" row (both are
    ministerial). Current-year columns come first: gross, net, exchequer,
    expenditure. Returns Nones when the table is not found or does not parse;
    the caller reports coverage as unverified rather than as reconciled.
    """
    for pno in sorted(pages):
        text = pages[pno] or ""
        # Table 3.1 in FY 2025/26, Table 3.4 in FY 2024/25 — anchor on the title.
        if not re.search(r"Table\s+3\.\d+\s*:\s*Overall\s+Budget\s+Performance", text):
            continue
        if "....." in text:
            continue  # the table of contents
        body = _strip_running_lines(text)
        mdas = re.search(r":\s*MDAs\s+(.*)", body)
        cfs = re.search(r":\s*CFS\s+(.*)", body)
        # "Devel-\n889.87 …" (FY 2025/26) or "Develop- 95 89\n612.98 …"
        # (FY 2024/25, the wrapped percentages print first): read on across
        # the break and take amounts only.
        dev = re.search(r"Devel[a-z]*-?(.*\n.*)", body)
        if not (mdas and dev):
            return None, None, None, pno
        m_nums = _amounts(mdas.group(1))
        d_nums = _amounts(dev.group(1))
        c_nums = _amounts(cfs.group(1)) if cfs else []
        if len(m_nums) < 4 or len(d_nums) < 4:
            return None, None, None, pno
        mda_gross = m_nums[0] + d_nums[0]  # type: ignore[operator]
        mda_exp = m_nums[3] + d_nums[3]  # type: ignore[operator]
        cfs_exp = c_nums[3] if len(c_nums) >= 4 else None
        return mda_gross, mda_exp, cfs_exp, pno
    return None, None, None, None


# ─────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────


def parse_sector_expenditure(pages: Mapping[int, str]) -> AnnualSectorExpenditure:
    """Parse and verify the ten Sector Summaries.

    ``pages`` maps 1-based PDF page number → extracted text. A sparse mapping
    is fine (tests pass the pages captured from the real report).
    """
    ordered = sorted(pages)
    headings: List[Tuple[int, str, str]] = []  # (page, table, code)
    for pno in ordered:
        text = pages[pno] or ""
        for m in _HEADING_RE.finditer(text):
            line_end = text.find("\n", m.start())
            line = text[m.start() : line_end if line_end != -1 else len(text)]
            if "....." in line:
                continue  # table-of-contents entry
            code = " ".join(m.group(2).split())
            headings.append((pno, f"Table {m.group(1)}", code))

    results: List[SectorResult] = []
    seen: set = set()
    for idx, (pno, table, code) in enumerate(headings):
        name = _CODE_TO_NAME.get(code.lower())
        if name is None or name in seen:
            continue
        seen.add(name)
        result = SectorResult(code=code, sector=name, table=table, heading_page=pno)

        # The summary lives on the heading page or the next two, never past
        # the next sector's heading.
        next_heading = headings[idx + 1][0] if idx + 1 < len(headings) else None
        window = [p for p in ordered if pno <= p <= pno + 2]
        if next_heading is not None:
            window = [p for p in window if p <= next_heading]
        joined = ""
        summary_page = None
        for p in window:
            chunk = _strip_running_lines(pages[p] or "")
            if p == pno:
                # Start at this sector's heading, not at the previous sector's
                # summary sharing the page.
                h = _HEADING_RE.search(chunk)
                chunk = chunk[h.start():] if h else chunk
            if summary_page is None and "Sector Summary" in chunk:
                summary_page = p
            joined += "\n" + chunk
        result.summary_page = summary_page

        start = joined.find("Sector Summary")
        if start == -1:
            result.problems.append("no Sector Summary found")
            results.append(result)
            continue
        end = joined.find("Source:", start)
        block = joined[start + len("Sector Summary") : end if end != -1 else None]
        rows = _parse_summary_block(block)
        result.development = rows.get("development")
        result.recurrent = rows.get("recurrent")
        result.total = rows.get("total")

        # Prose: usually the paragraph before the table (possibly a page
        # earlier); FY 2024/25 puts National Security's after its summary.
        prose_pages = [p for p in ordered if pno - 1 <= p <= (summary_page or pno) + 1]
        for p in prose_pages:
            v = _prose_for(code, name, pages[p] or "")
            if v is not None:
                result.prose_expenditure_bn, result.prose_page = v, p
                break

        _verify(result)
        results.append(result)

    mda_gross, mda_exp, cfs_exp, t31_page = _parse_table_3_1(pages)
    return AnnualSectorExpenditure(
        sectors=results,
        mda_expenditure_bn=mda_exp,
        mda_gross_bn=mda_gross,
        cfs_expenditure_bn=cfs_exp,
        table_3_1_page=t31_page,
    )


def _split_reconciles(r: SectorResult) -> bool:
    if not (r.development and r.recurrent and r.total):
        return False
    for attr in ("gross", "net", "exchequer", "expenditure"):
        combined = getattr(r.development, attr) + getattr(r.recurrent, attr)
        if abs(combined - getattr(r.total, attr)) > SPLIT_TOLERANCE_BN:
            return False
    return True


def _verify(r: SectorResult) -> None:
    """Decide what of ``r`` may be published. Mutates ``r``."""
    if r.total is None:
        r.problems.append("Total row did not parse")
        return

    ratio_problems = r.total.ratio_problems()
    r.checks["total_ratios_match_printed_pct"] = not ratio_problems
    r.problems.extend(f"Total: {p}" for p in ratio_problems)

    split_ok = _split_reconciles(r)
    r.checks["development_plus_recurrent_equals_total"] = split_ok

    if r.prose_expenditure_bn is None:
        r.checks["prose_total_matches"] = False
        prose_ok = False
    else:
        prose_ok = (
            abs(r.prose_expenditure_bn - r.total.expenditure) <= PROSE_TOLERANCE_BN
        )
        r.checks["prose_total_matches"] = prose_ok
        if not prose_ok:
            r.problems.append(
                f"prose states {r.prose_expenditure_bn} bn, Total row "
                f"{r.total.expenditure} bn"
            )

    r.accepted = (not ratio_problems) and (prose_ok or split_ok)
    if not r.accepted and not r.problems:
        r.problems.append("no independent confirmation of the Total row")

    if r.accepted:
        if split_ok:
            r.split_published = all(
                not row.ratio_problems() for row in (r.development, r.recurrent)  # type: ignore[union-attr]
            )
        if not r.split_published:
            r.problems.append(
                "Development/Recurrent split withheld: the rows do not "
                "reproduce the Total"
                if not split_ok
                else "Development/Recurrent split withheld: a row's ratios "
                "disagree with its printed percentages"
            )


__all__ = [
    "ALLOCATION_MEASURE",
    "EXCHEQUER_MEASURE",
    "EXPENDITURE_MEASURE",
    "AnnualSectorExpenditure",
    "SECTORS",
    "SectorResult",
    "SummaryRow",
    "parse_sector_expenditure",
]

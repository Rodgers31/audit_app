"""Read the enacted budget's split out of Treasury's Budget Summary.

WHY THIS EXISTS
---------------
``revenue_estimates`` reads Table 2 of the Budget Summary for ordinary
revenue, and that table prints only the ordinary / A-i-A / total triple. So
for FY 2026/27 the site had a budget, a revenue figure and a debt-service
figure, and nothing to say how the budget divides: borrowing, recurrent,
development, counties, and tax versus non-tax were all ``null``, and the four
surfaces that draw them showed "—".

The same document prints all of it in **Annex Table 2a, "Fiscal Framework
(KSh billion)"**: tax revenue by head, non-tax revenue, recurrent and
development spending, county transfers, the fiscal deficit and how it is
financed (net foreign and net domestic). It prints every year from two
settled years back to three projected years forward, so one document carries
the whole series, and the next year's edition carries the next year's
numbers without anyone touching a fixture.

WHICH BASIS
-----------
Everything this module returns is on ONE basis: Treasury's fiscal framework,
whose spending total is "Expenditure and Net Lending". For FY 2026/27 that is
4,785.2B, and the split reconciles to it exactly:

    recurrent 3,538.7 + development & net lending 749.0
        + county transfers 495.5 + contingency 2.0 = 4,785.2

It does NOT reconcile to ``appropriated_budget`` (5,485.7B, the Controller of
Budget's gross basis). That figure counts 1,061.6B of principal REDEMPTION,
which the fiscal framework treats as financing rather than spending, and it
excludes the county transfers. The two totals answer different questions, so
this module never divides one basis by the other. It returns its own total
alongside every split, and callers draw the split against that total.

"Debt service" is the other trap. On this basis the interest bill (1,254.2B)
sits inside recurrent and principal sits outside spending altogether. The
site's ``debt_service_cost`` (2,315.9B) is interest PLUS principal. Taking
that away from recurrent would take away 1,061.6B that recurrent never held.
The interest row is returned so a caller can split recurrent correctly.

WHICH COLUMN
------------
A budget year prints two columns (in FY 2026/27, the BPS projection and the
approved budget), and the header does not map onto the data columns in the
text layer. Two ways of identifying a column are used instead, and neither
depends on the layout.

1. **The narrative.** The Budget Summary restates the approved budget in its
   prose ("recurrent expenditure of KSh 3,538.7 billion; development
   expenditure of KSh 749.0 billion; transfers to County Governments of KSh
   495.5 billion ..."). The approved column is the one whose figures appear
   there, and it must beat every other column by a clear margin. This needs
   no per-year constant, which is what makes the NEXT edition work on its
   own: ``revenue_estimates`` needs a hand-entered BPS figure for every new
   year and refuses without one.
2. **The revenue join**, for every other year. ``revenue_estimates`` has
   already gated ordinary revenue for that year out of Table 2, so the
   matching column here is the one printing the same ordinary revenue. That
   keeps each row's split on the same vintage as its own revenue.

THE GATES
---------
Every published column must satisfy its own arithmetic. Any failure raises
``FiscalFrameworkError`` and the caller quarantines the year:

* ordinary revenue + ministerial A-i-A = total revenue
* recurrent + development & net lending + county transfers + contingency
  = expenditure and net lending
* total revenue + grants - expenditure = fiscal balance (incl. grants)
* net foreign + net domestic financing = total financing
* total financing = -balance (cash basis) + statistical discrepancy. Settled
  years print a non-zero discrepancy (FY 2023/24 actual: -16.8B); budget
  years print 0.0.

Tax versus non-tax has two more gates of its own (tax + non-tax = ordinary;
the five tax heads sum to tax). If those fail, only the tax split is
withheld: the spending split does not depend on it. Tolerances are exactly
what one-decimal rounding can produce, 0.05B per term plus 0.05B.

Anchors were read from the real editions on 2026-09-26, not from any
description of them: FY 2026/27 (1,390,375 bytes, sha256 1e24992d...550b,
annex PDF p.63, narrative pp.12-13) and FY 2023/24 (1,963,493 bytes, annex
PDF p.62, narrative p.10). The FY 2023/24 edition prints no "Tax Revenue" row,
so its tax split is withheld rather than assembled. The FY 2022/23 edition's
annex is a scanned image with no text layer and is refused as such.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("seeding.fiscal_summary.fiscal_framework")

#: The one basis every figure from this module is on. Declared on each row so
#: the page can say which total a split is drawn against.
FISCAL_FRAMEWORK_BASIS = "treasury_fiscal_framework"

#: Rows read from the annex, keyed by the label as the table prints it once
#: whitespace is collapsed and case folded. The FIRST line matching a pattern
#: wins, which matters for the three "Fiscal Balance (incl. grants)" variants.
_ROW_PATTERNS: Tuple[Tuple[str, str], ...] = (
    ("total_revenue", r"total revenue"),
    ("ordinary_revenue", r"ordinary revenue( \(tax ?\+ ?non-tax revenue\))?"),
    ("tax_revenue", r"tax revenue"),
    ("income_tax", r"income tax"),
    ("import_duty", r"import duty \(net\)"),
    ("excise_duty", r"excise duty"),
    ("vat", r"value added tax"),
    ("other_tax", r"other tax revenue"),
    ("non_tax_revenue", r"non-tax revenue"),
    ("ministerial_aia", r"ministerial appropriation in aid"),
    ("expenditure", r"expenditure and net lending"),
    ("recurrent", r"recurrent expenditure"),
    ("interest", r"interest payments"),
    ("development", r"development and net lending"),
    # Treasury's own spelling in both editions read: "County Tranfers".
    ("county_transfers", r"county trans?fers"),
    ("equitable_share", r"equitable share"),
    ("contingency", r"contingency fund"),
    ("grants", r"grants"),
    ("fiscal_balance", r"fiscal balance \(incl\. grants\)"),
    ("adjustment_to_cash_basis", r"adjustments? to cash basis"),
    ("fiscal_balance_cash", r"fiscal balance \(incl\. grants\) cash basis"),
    ("statistical_discrepancy", r"statistical discrepancy"),
    ("total_financing", r"total financing"),
    ("net_foreign_financing", r"net foreign financing"),
    ("net_domestic_financing", r"net domestic financing"),
    ("nominal_gdp", r"nominal gdp"),
)

#: A column cannot be published without these; every identity reads them.
REQUIRED_ROWS = (
    "total_revenue",
    "ordinary_revenue",
    "ministerial_aia",
    "expenditure",
    "recurrent",
    "development",
    "county_transfers",
    "contingency",
    "grants",
    "fiscal_balance",
    "adjustment_to_cash_basis",
    "fiscal_balance_cash",
    "statistical_discrepancy",
    "total_financing",
    "net_foreign_financing",
    "net_domestic_financing",
)

TAX_HEADS = ("income_tax", "import_duty", "excise_duty", "vat", "other_tax")

#: Rows whose figure the narrative restates for the approved budget. Used to
#: SCORE columns, never to publish: the published figure is the table's.
_NARRATIVE_ROWS = (
    "total_revenue",
    "ordinary_revenue",
    "ministerial_aia",
    "expenditure",
    "recurrent",
    "development",
    "county_transfers",
    "fiscal_balance",
    "net_foreign_financing",
    "net_domestic_financing",
)

#: The approved column must match at least this many narrative figures...
MIN_NARRATIVE_MATCHES = 6
#: ...and beat the runner-up by at least this many. In FY 2026/27 the
#: approved column matches 9 and the next best (FY 2025/26 Supplementary I,
#: which the prose quotes as the comparator) matches 4.
MIN_NARRATIVE_MARGIN = 3

_ANNEX_MARKER = "fiscalframework(kshbillion)"
_NUM = r"-?\(?[\d,]+\.\d+\)?|-?\d+"
_NUM_RE = re.compile(rf"^(?:{_NUM})$")
_AMOUNT_RE = re.compile(
    r"k\s?shs?\.?\s*([\d,]+(?:\.\d+)?)\s*(billion|trillion)", re.IGNORECASE
)


class FiscalFrameworkError(Exception):
    """A parse that must be QUARANTINED, never published."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _to_decimal(token: str) -> Decimal:
    t = token.strip()
    neg = t.startswith("-") or (t.startswith("(") and t.endswith(")"))
    t = t.strip("()-").replace(",", "")
    value = Decimal(t)
    return -value if neg else value


def _tolerance(terms: int) -> Decimal:
    """What one-decimal rounding can move a sum of ``terms`` figures by."""
    return Decimal("0.05") * terms + Decimal("0.05")


@dataclass(frozen=True)
class AnnexTable:
    """Annex Table 2a: each row's figures, left to right, in KSh billion."""

    rows: Dict[str, List[Decimal]]
    width: int
    page: int
    column_labels: Dict[int, str] = field(default_factory=dict)

    def column(self, index: int) -> Dict[str, Decimal]:
        return {k: v[index] for k, v in self.rows.items() if len(v) == self.width}


def parse_annex_lines(lines: Sequence[str], *, page: int) -> AnnexTable:
    """Rows of Annex Table 2a from the page's text lines.

    Each line is "<label> <n1> <n2> ... <nk>". A row is kept only if it
    prints a figure for EVERY column (the modal width). A short row such as
    "Road Maintenance Levy - Normal", which drops a cell, cannot be mapped to
    columns without guessing which cell is missing, and nothing required
    comes from such a row.
    """
    parsed: Dict[str, List[Decimal]] = {}
    widths: List[int] = []
    for raw in lines:
        tokens = raw.split()
        cut = len(tokens)
        while cut > 0 and _NUM_RE.match(tokens[cut - 1]):
            cut -= 1
        numbers = tokens[cut:]
        label = " ".join(tokens[:cut]).lower()
        if not numbers or not label:
            continue
        for key, pattern in _ROW_PATTERNS:
            if key in parsed:
                continue
            if re.fullmatch(pattern, label):
                parsed[key] = [_to_decimal(n) for n in numbers]
                widths.append(len(numbers))
                break

    if not widths:
        raise FiscalFrameworkError(
            "annex_has_no_rows",
            f"PDF p.{page} carries the Annex Table 2a title but no readable "
            f"rows (a scanned table has no text layer)",
        )
    width = max(set(widths), key=widths.count)
    rows = {k: v for k, v in parsed.items() if len(v) == width}
    missing = [k for k in REQUIRED_ROWS if k not in rows]
    if missing:
        raise FiscalFrameworkError(
            "rows_not_found",
            f"PDF p.{page}: no full-width row for {', '.join(missing)}",
        )
    # Recover only unambiguous, contiguous header cells. PDF text can reorder
    # the multi-line BPS/Approved headers, so an unfamiliar layout stays unknown.
    # This prefix is printed in the FY2026/27 Annex 2a; it is not inferred from
    # the age of a fiscal year (a past year can still be preliminary).
    labels = {}
    if any(re.match(r"^Act\.\s+Prel\.\s+Budget\s+Suppl\.1\s+Budget\s+BROP\b", line.strip()) for line in lines):
        labels = {0: "Actual", 1: "Preliminary", 3: "Supplementary I"}
    return AnnexTable(rows=rows, width=width, page=page, column_labels=labels)


def narrative_amounts(text: str) -> List[Decimal]:
    """Every "KSh N billion" (or trillion) figure in the prose, in billions."""
    out: List[Decimal] = []
    for m in _AMOUNT_RE.finditer(text or ""):
        value = Decimal(m.group(1).replace(",", ""))
        if m.group(2).lower() == "trillion":
            value *= 1000
        out.append(value)
    return out


def identify_approved_column(
    table: AnnexTable, amounts: Sequence[Decimal]
) -> Tuple[int, int, int]:
    """The column the narrative describes. Returns ``(index, score, runner_up)``.

    Scores each column by how many of its headline figures the prose quotes.
    Deficits are printed negative in the table and positive in the prose, so
    they are compared by magnitude.
    """
    pool = [abs(a) for a in amounts]

    def quoted(v: Decimal) -> bool:
        return any(abs(abs(v) - a) <= Decimal("0.05") for a in pool)

    scores = []
    for i in range(table.width):
        col = table.column(i)
        scores.append(sum(1 for k in _NARRATIVE_ROWS if k in col and quoted(col[k])))
    ranked = sorted(range(table.width), key=lambda i: scores[i], reverse=True)
    best = ranked[0]
    runner_up = scores[ranked[1]] if len(ranked) > 1 else 0
    if scores[best] < MIN_NARRATIVE_MATCHES:
        raise FiscalFrameworkError(
            "narrative_does_not_identify_a_column",
            f"best column matches {scores[best]} of {len(_NARRATIVE_ROWS)} "
            f"figures the prose quotes; {MIN_NARRATIVE_MATCHES} required",
        )
    if scores[best] - runner_up < MIN_NARRATIVE_MARGIN:
        raise FiscalFrameworkError(
            "narrative_ambiguous",
            f"best column matches {scores[best]}, runner-up {runner_up}; "
            f"a margin of {MIN_NARRATIVE_MARGIN} is required",
        )
    return best, scores[best], runner_up


@dataclass(frozen=True)
class FrameworkSplit:
    """One column of the fiscal framework, gated. All money in KSh billion."""

    fiscal_year: str
    column_index: int
    #: "approved_budget" when the narrative identified the column; otherwise
    #: "revenue_column", meaning the column whose ordinary revenue equals the
    #: figure ``revenue_estimates`` published for the year.
    identified_by: str
    values: Dict[str, Decimal]
    tax_split_ok: bool
    tax_split_reason: Optional[str]
    checks: List[str] = field(default_factory=list)
    column_label: Optional[str] = None


def _check(
    label: str, total: Decimal, parts: Sequence[Decimal], checks: List[str]
) -> None:
    got = sum(parts, Decimal("0"))
    tol = _tolerance(len(parts))
    if abs(got - total) > tol:
        raise FiscalFrameworkError(
            "does_not_reconcile",
            f"{label}: components sum to {got} against {total} (tolerance {tol})",
        )
    checks.append(f"{label}: {got} vs {total}")


def gate_column(
    table: AnnexTable, index: int, *, fiscal_year: str, identified_by: str
) -> FrameworkSplit:
    """Apply every identity to one column, or raise."""
    col = table.column(index)
    missing = [k for k in REQUIRED_ROWS if k not in col]
    if missing:
        raise FiscalFrameworkError("column_incomplete", ", ".join(missing))
    checks: List[str] = []
    _check(
        "ordinary + ministerial AiA = total revenue",
        col["total_revenue"],
        [col["ordinary_revenue"], col["ministerial_aia"]],
        checks,
    )
    _check(
        "recurrent + development + county transfers + contingency = expenditure",
        col["expenditure"],
        [col["recurrent"], col["development"], col["county_transfers"], col["contingency"]],
        checks,
    )
    _check(
        "total revenue + grants - expenditure = fiscal balance (incl. grants)",
        col["fiscal_balance"],
        [col["total_revenue"], col["grants"], -col["expenditure"]],
        checks,
    )
    _check(
        "fiscal balance + adjustment to cash basis = fiscal balance (cash basis)",
        col["fiscal_balance_cash"],
        [col["fiscal_balance"], col["adjustment_to_cash_basis"]],
        checks,
    )
    _check(
        "net foreign + net domestic = total financing",
        col["total_financing"],
        [col["net_foreign_financing"], col["net_domestic_financing"]],
        checks,
    )
    _check(
        "total financing = -fiscal balance (cash basis) + statistical discrepancy",
        col["total_financing"],
        [-col["fiscal_balance_cash"], col["statistical_discrepancy"]],
        checks,
    )
    if col["total_financing"] <= 0 or col["expenditure"] <= 0:
        raise FiscalFrameworkError(
            "implausible_sign",
            f"financing {col['total_financing']}, expenditure {col['expenditure']}",
        )

    # Tax versus non-tax: its own gates, and a failure withholds only this.
    tax_ok, tax_reason = True, None
    if "tax_revenue" not in col or "non_tax_revenue" not in col:
        tax_ok, tax_reason = False, "edition_prints_no_tax_or_non_tax_row"
    else:
        try:
            _check(
                "tax + non-tax = ordinary revenue",
                col["ordinary_revenue"],
                [col["tax_revenue"], col["non_tax_revenue"]],
                checks,
            )
            heads = [col[h] for h in TAX_HEADS if h in col]
            if len(heads) != len(TAX_HEADS):
                raise FiscalFrameworkError("tax_heads_missing")
            _check("five tax heads = tax revenue", col["tax_revenue"], heads, checks)
        except FiscalFrameworkError as exc:
            tax_ok, tax_reason = False, f"{exc.reason}: {exc.detail}"
    return FrameworkSplit(
        fiscal_year=fiscal_year,
        column_index=index,
        identified_by=identified_by,
        values=col,
        tax_split_ok=tax_ok,
        tax_split_reason=tax_reason,
        checks=checks,
        column_label=("Approved" if identified_by == "approved_budget" else table.column_labels.get(index)),
    )


def match_revenue_column(table: AnnexTable, ordinary_revenue: Decimal) -> int:
    """The column printing ``ordinary_revenue``, or raise.

    Several columns may print the same figure (forward projections repeat the
    BPS column). That is only accepted when those columns are identical on
    every row, so picking either publishes the same thing.
    """
    hits = [
        i
        for i in range(table.width)
        if abs(table.column(i).get("ordinary_revenue", Decimal("-1")) - ordinary_revenue)
        <= Decimal("0.05")
    ]
    if not hits:
        raise FiscalFrameworkError(
            "no_column_prints_this_revenue", f"ordinary revenue {ordinary_revenue}"
        )
    first = table.column(hits[0])
    if any(table.column(i) != first for i in hits[1:]):
        raise FiscalFrameworkError(
            "revenue_matches_several_different_columns",
            f"{ordinary_revenue} appears in columns {hits}",
        )
    return hits[0]


@dataclass(frozen=True)
class Edition:
    """One Budget Summary, read: its annex, and the column its prose names."""

    fiscal_year: str
    table: AnnexTable
    approved_index: int
    narrative_score: Tuple[int, int]
    narrative_pages: Tuple[int, int]


def _normalise_fy(label: str) -> Optional[str]:
    m = re.search(r"(20\d{2})\s*[/_-]\s*(\d{2})(?!\d)", label or "")
    return f"FY {m.group(1)}/{m.group(2)}" if m else None


def edition_fiscal_year(pages: Sequence[str], *, fiscal_year: Optional[str]) -> str:
    """The fiscal year an edition describes, from its link and its cover.

    Separate from :func:`read_edition` because the freshness gate needs the
    year even when the edition cannot be read: an unreadable newer edition is
    exactly the state it exists to report.
    """
    cover = " ".join(pages[:3])
    cover_fy = None
    m = re.search(
        r"budget\s+summary\s+for\s+the\s+(?:fy|fiscal\s+year)\s*(20\d{2}\s*/\s*\d{2})",
        cover,
        re.I,
    )
    if m:
        cover_fy = _normalise_fy(m.group(1))
    if fiscal_year and cover_fy and cover_fy != fiscal_year:
        raise FiscalFrameworkError(
            "cover_disagrees_with_link",
            f"link says {fiscal_year}, cover says {cover_fy}",
        )
    fy = fiscal_year or cover_fy
    if not fy:
        raise FiscalFrameworkError(
            "edition_year_unknown", "neither link nor cover names a year"
        )
    return fy


def extract_page_texts(pdf_path) -> List[dict]:
    """``[{"page": n, "text": ...}]`` for every page, via pdfplumber.

    Record-shaped so ``parse_cache.parse_with_cache`` can store it: the text
    layer of a ~70-page edition costs 6-9s to extract, and the listing
    carries several editions that do not change between nights.
    """
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        return [
            {"page": i + 1, "text": page.extract_text() or ""}
            for i, page in enumerate(pdf.pages)
        ]


def read_edition(pages: Sequence[str], *, fiscal_year: Optional[str]) -> Edition:
    """Read an edition from its pages' text (index 0 = PDF p.1).

    ``fiscal_year`` is the year the listing link names. It is confirmed
    against the document's own cover: a link that names one year and a cover
    that names another is refused, because a mislabelled edition would put
    one budget's split onto another budget's year.
    """
    fy = edition_fiscal_year(pages, fiscal_year=fiscal_year)

    annex_page = next(
        (i for i, t in enumerate(pages) if _ANNEX_MARKER in _squash(t) and "annextable2a" in _squash(t)),
        None,
    )
    if annex_page is None:
        raise FiscalFrameworkError("annex_table_2a_not_found")
    table = parse_annex_lines(pages[annex_page].splitlines(), page=annex_page + 1)

    # The narrative lives before the annexes. Only prose amounts ("KSh N
    # billion") are read, which the debt schedules in between do not print.
    front = "\n".join(pages[:annex_page])
    index, score, runner_up = identify_approved_column(table, narrative_amounts(front))
    return Edition(
        fiscal_year=fy,
        table=table,
        approved_index=index,
        narrative_score=(score, runner_up),
        narrative_pages=(1, annex_page),
    )


def split_for_fiscal_year(
    edition: Edition, fiscal_year: str, *, known_ordinary_revenue: Optional[float]
) -> FrameworkSplit:
    """The gated column for ``fiscal_year`` out of ``edition``, or raise.

    The edition's own year comes from the narrative-identified column, and if
    the row already carries revenue from ``revenue_estimates`` the two must
    agree (Table 2 and Annex 2a are the same document's two renderings of the
    same budget). Any other year needs ``known_ordinary_revenue`` and comes
    from the column printing it.
    """
    if fiscal_year == edition.fiscal_year:
        index = edition.approved_index
        split = gate_column(
            edition.table, index, fiscal_year=fiscal_year, identified_by="approved_budget"
        )
        if known_ordinary_revenue is not None:
            ordinary = split.values["ordinary_revenue"]
            if abs(ordinary - Decimal(str(known_ordinary_revenue))) > Decimal("0.05"):
                raise FiscalFrameworkError(
                    "revenue_column_disagrees",
                    f"approved column prints ordinary revenue {ordinary}, the "
                    f"row holds {known_ordinary_revenue} from Table 2",
                )
        score, runner = edition.narrative_score
        split.checks.insert(
            0,
            f"approved column identified by the narrative: {score} quoted "
            f"figures (runner-up {runner})",
        )
        return split

    if known_ordinary_revenue is None:
        raise FiscalFrameworkError(
            "no_revenue_to_join_on",
            f"{fiscal_year} has no Budget Summary revenue to identify its column",
        )
    index = match_revenue_column(edition.table, Decimal(str(known_ordinary_revenue)))
    if index == edition.approved_index:
        raise FiscalFrameworkError(
            "revenue_matches_the_approved_column",
            f"{fiscal_year}'s revenue matches {edition.fiscal_year}'s approved column",
        )
    split = gate_column(
        edition.table, index, fiscal_year=fiscal_year, identified_by="revenue_column"
    )
    split.checks.insert(
        0, f"column identified by its ordinary revenue {known_ordinary_revenue}"
    )
    return split


def framework_payload(split: FrameworkSplit, *, source_url: Optional[str], page: int) -> dict:
    """The row-level ``fiscal_framework`` object: one basis, one total, receipts."""
    v = split.values

    def b(key: str) -> Optional[float]:
        return float(v[key]) if key in v else None

    out = {
        "basis": FISCAL_FRAMEWORK_BASIS,
        "identified_by": split.identified_by,
        "total_expenditure_billion": b("expenditure"),
        "recurrent_billion": b("recurrent"),
        "interest_payments_billion": b("interest"),
        "development_billion": b("development"),
        "county_transfers_billion": b("county_transfers"),
        "county_equitable_share_billion": b("equitable_share"),
        "contingency_billion": b("contingency"),
        "total_revenue_incl_aia_billion": b("total_revenue"),
        "ordinary_revenue_billion": b("ordinary_revenue"),
        "ministerial_aia_billion": b("ministerial_aia"),
        "grants_billion": b("grants"),
        # Positive: the amount borrowed. The table prints the balance negative.
        "fiscal_deficit_incl_grants_billion": float(-v["fiscal_balance"]),
        # Both printed rows, so sources can be reconciled to spending in a
        # settled year without a computed residual:
        #   expenditure = total revenue + grants + financing
        #                 + adjustment to cash basis - statistical discrepancy
        # Budget years print 0.0 for both.
        "adjustment_to_cash_basis_billion": b("adjustment_to_cash_basis"),
        "statistical_discrepancy_billion": b("statistical_discrepancy"),
        "total_financing_billion": b("total_financing"),
        "net_foreign_financing_billion": b("net_foreign_financing"),
        "net_domestic_financing_billion": b("net_domestic_financing"),
        "nominal_gdp_billion": b("nominal_gdp"),
        "source": {
            "title": "Budget Summary",
            "publisher": "The National Treasury",
            "url": source_url,
            # Short: it can become ``fiscal_summaries.page_ref`` (50 chars).
            "page": f"Annex Table 2a, PDF p.{page}",
            "table": "Annex Table 2a: Fiscal Framework (KSh billion)",
            "column": split.column_label or "Vintage unconfirmed",
        },
        "checks": list(split.checks),
    }
    if split.tax_split_ok:
        out["tax_revenue_billion"] = b("tax_revenue")
        out["non_tax_revenue_billion"] = b("non_tax_revenue")
        out["tax_heads_billion"] = {h: b(h) for h in TAX_HEADS}
    else:
        out["tax_split_absent_reason"] = split.tax_split_reason
    return out

"""FY2026/27 Table 5.2, recommended column only, in raw KES.

The contract is the reviewed table itself, cell by cell: the five header rows,
every data row's label, row order and the positions of its nonempty cells. A
value is read only from the position the reviewed layout gives it, and each row
must satisfy the table's own arithmetic (baseline + adjustment = recommended;
the totals; the county adjustment's "of which" lines). A swapped, renamed,
negated or shifted column therefore refuses instead of relabelling baseline or
historical figures as current recommendations. Any other layout refuses.
"""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re

import pdfplumber

from .source import CraSourceRefused, MAX_BYTES

EXTRACTOR = "cra_table_5_2_v1"
PAGE = 39  # Printed page 32 in this reviewed edition.
PRINTED_PAGE = "32"
PAGE_COUNT = 61
WIDTH = 15
TITLE = ("COMMISSION ON REVENUE ALLOCATION Promoting an Equitable Society RECOMMENDATION ON THE BASIS FOR "
         "EQUITABLE SHARING OF REVENUE BETWEEN THE NATIONAL AND COUNTY GOVERNMENTS FOR FINANCIAL YEAR "
         "2026/2027 JANUARY, 2026")
TABLE_TITLE_LINES = ("Table 5.2: Recommended Equitable Share of Revenue to the two Levels of", "Government-Ksh. Billion")

# Nonempty cells of the reviewed header rows, by column position. Column 13 is
# the only recommendation column; column 7 is the FY2025/26 baseline.
HEADER = (
    {0: "Items", 7: "Baseline", 9: "Adjustment", 13: "Recommended"},
    {7: "Allocation for FY", 13: "Shareable"},
    {7: "2025/26 (Ksh.", 13: "Revenues for"},
    {7: "billion)", 13: "FY 2026/27"},
    {13: "(Ksh. billion)"},
)
# Data rows in reviewed order: label position and text, then the positions of
# baseline, adjustment and recommended values (None where the source is blank).
# pdfplumber reports the first two rows' value cells one column left of the
# header; that offset is part of the reviewed layout, not a tolerance.
ROWS = (
    ("national_government", 0, "National Government", 6, 9, 12),
    ("county_governments", 0, "County Government", 6, 9, 12),
    ("county_revenue_increment", 4, "Revenue increment", None, 10, None),
    ("county_uhc_workers", 4, "Remuneration of UHC workers", None, 10, None),
    ("equalisation_fund", 1, "Equalisation Fund", 7, 10, 13),
    ("total_shareable_revenue", 1, "Total Revenue", 7, None, 13),
)
# Text cells that sit beside the "of which" lines in the reviewed table.
EXTRA_TEXT = {2: {1: "Of which:"}}
PERSISTED = ("national_government", "county_governments", "equalisation_fund", "total_shareable_revenue")

# Bounded, exact numeric semantics for this publication (KES billion, at most two
# decimals). The largest reviewed value is 2,982.3; an integer part of at most six
# digits (< KES 1 quadrillion) leaves three orders of magnitude of headroom and
# keeps every value below 10**8 hundredths. Values are carried as integer
# hundredths of a billion, so reconciliation and the KES conversion
# (hundredths * 10**7) are exact integer arithmetic, with no Decimal context
# precision or rounding involved. Leading zeros, signs, exponents, spaces,
# non-ASCII digits and malformed comma groups are refused.
AMOUNT = re.compile(r"(0|[1-9][0-9]{0,5}|[1-9][0-9]{0,2},[0-9]{3})(?:\.([0-9]{1,2}))?")
KES_PER_HUNDREDTH = 10_000_000


def hundredths(value, *, positive=True):
    if type(value) is not str:
        raise CraSourceRefused("CRA amount is not a supported decimal cell")
    match = AMOUNT.fullmatch(value)
    if match is None:
        raise CraSourceRefused("CRA amount is outside the supported bounded decimal grammar")
    whole = int(match[1].replace(",", ""))
    fraction = int((match[2] or "").ljust(2, "0"))
    result = whole * 100 + fraction
    if positive and result <= 0:
        raise CraSourceRefused("CRA recommended amount must be positive")
    return result


def amount(value):
    """A positive recommended amount, in exact integer hundredths of KES billion."""
    return hundredths(value, positive=True)


def _cells(row):
    if type(row) is not list or len(row) != WIDTH or any(c is not None and type(c) is not str for c in row):
        raise CraSourceRefused("CRA recommendation table row has an unsupported shape")
    return {i: c for i, c in enumerate(row) if c is not None and c != ""}


def parse_table(table):
    """Validate the reviewed layout and arithmetic; return raw-KES strings."""
    if type(table) is not list or len(table) != len(HEADER) + len(ROWS):
        raise CraSourceRefused("CRA recommendation table missing or malformed")
    for row, expected in zip(table, HEADER):
        if _cells(row) != expected:
            raise CraSourceRefused("CRA recommendation table header differs from the reviewed edition")
    values = {}
    for index, (row, (key, label_at, label, base_at, adjust_at, recommend_at)) in enumerate(zip(table[len(HEADER):], ROWS)):
        cells = _cells(row)
        text = {label_at: label, **EXTRA_TEXT.get(index, {})}
        positions = {p for p in (base_at, adjust_at, recommend_at) if p is not None}
        if set(cells) != set(text) | positions or any(cells[p] != t for p, t in text.items()):
            raise CraSourceRefused("CRA recommendation row differs from the reviewed layout")
        values[key] = {
            "baseline": hundredths(cells[base_at], positive=False) if base_at is not None else None,
            "adjustment": hundredths(cells[adjust_at], positive=False) if adjust_at is not None else None,
            "recommended": amount(cells[recommend_at]) if recommend_at is not None else None,
        }
    allocations = ("national_government", "county_governments", "equalisation_fund")
    total = values["total_shareable_revenue"]
    if (any(values[k]["baseline"] + values[k]["adjustment"] != values[k]["recommended"] for k in allocations)
            or values["county_revenue_increment"]["adjustment"] + values["county_uhc_workers"]["adjustment"]
            != values["county_governments"]["adjustment"]
            or sum(values[k]["baseline"] for k in allocations) != total["baseline"]
            or sum(values[k]["recommended"] for k in allocations) != total["recommended"]):
        raise CraSourceRefused("CRA recommended allocations do not reconcile with the reviewed table")
    return {k: str(values[k]["recommended"] * KES_PER_HUNDREDTH) for k in PERSISTED}


def validate_page(page_count, title, text, tables):
    if type(page_count) is not int or page_count != PAGE_COUNT:
        raise CraSourceRefused("CRA unsupported document edition or page count")
    if type(title) is not str or " ".join(title.split()) != TITLE:
        raise CraSourceRefused("CRA unsupported publisher, title or fiscal year")
    lines = [line.strip() for line in text.split("\n")] if type(text) is str else []
    pairs = list(zip(lines, lines[1:]))
    if TABLE_TITLE_LINES not in pairs or "Source of data: CRA" not in lines or not lines or lines[-1] != PRINTED_PAGE:
        raise CraSourceRefused("CRA recommendation table title, units, attribution or printed page missing")
    if type(tables) is not list or len(tables) != 1:
        raise CraSourceRefused("CRA unique recommendation table required")
    amounts = parse_table(tables[0])
    # The table and the page text are separate extractions of the same page. Every
    # value cell must also appear in the text, so a table that disagrees with the
    # printed page (for example uniformly rescaled values) refuses.
    tokens = set(" ".join(lines).split())
    if any(cell not in tokens for row in tables[0][len(HEADER):] for i, cell in enumerate(row)
           if cell and AMOUNT.fullmatch(cell)):
        raise CraSourceRefused("CRA table values differ from the page text")
    return amounts


def parse_publication(payload):
    if type(payload) is not bytes or not 1 <= len(payload) <= MAX_BYTES or not payload.startswith(b"%PDF-") or b"%%EOF" not in payload[-1024:]:
        raise CraSourceRefused("CRA complete bounded PDF bytes required")
    try:
        with pdfplumber.open(BytesIO(payload)) as pdf:
            pages = pdf.pages
            if len(pages) != PAGE_COUNT:
                raise CraSourceRefused("CRA unsupported document edition or page count")
            page = pages[PAGE - 1]
            title, text, tables = pages[0].extract_text(), page.extract_text(), page.extract_tables()
    except CraSourceRefused:
        raise
    except Exception:
        raise CraSourceRefused("CRA PDF could not be read") from None
    amounts = validate_page(len(pages), title, text, tables)
    return {
        "schema_version": 1, "dataset": "cra_recommendations", "fiscal_year": "FY2026/27",
        "measure": "recommended_shareable_revenue_allocation", "currency": "KES",
        "publisher_units": "KES billion", "table": "5.2", "page_number": PAGE,
        "amounts_kes": amounts, "artifact_sha256": sha256(payload).hexdigest(),
        "parser_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
    }

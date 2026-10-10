"""Source semantics from actual CRA PDF bytes and hostile boundary cells."""
import copy
from decimal import Decimal
from pathlib import Path
import random
from types import SimpleNamespace

import httpx
import pdfplumber
import pytest

from seeding.domains.cra import parser, source
from seeding.config import SeedingSettings

PDF = Path(__file__).resolve().parents[2] / "docs/admin/implementation/batch11-issue-602-evidence/fixtures/cra-fy2026-27.pdf"
# The real page is read once with the real reader. Mutation cases change only the
# extracted table handed to the parser, so the actual title, page text, edition
# checks and PDF bytes stay the reviewed publication's.
with pdfplumber.open(PDF) as _pdf:
    REAL_PAGES = len(_pdf.pages)
    REAL_TITLE = _pdf.pages[0].extract_text()
    REAL_TEXT = _pdf.pages[38].extract_text()
    REAL_TABLE = _pdf.pages[38].extract_tables()[0]


def test_real_publisher_table_selects_recommended_column_and_raw_kes():
    actual = parser.parse_publication(PDF.read_bytes())
    assert actual["fiscal_year"] == "FY2026/27" and actual["page_number"] == 39
    assert actual["measure"] == "recommended_shareable_revenue_allocation"
    assert {k: Decimal(v) for k, v in actual["amounts_kes"].items()} == {
        "national_government": Decimal("2513760000000"), "county_governments": Decimal("458940000000"),
        "equalisation_fund": Decimal("9600000000"), "total_shareable_revenue": Decimal("2982300000000")}
    assert actual["artifact_sha256"] == "38189f669f7014cfd11d0cc7d7215332667772b5cc32a7ccb083ad9976b8498a"


@pytest.mark.parametrize("value", [True, False, None, 0, -1, float("nan"), float("inf"), float("-inf"), "NaN", "inf", "0", "-0.0", "-1", "", "1,23", "1.001", "1e9"])
def test_hostile_decimal_cell_refuses(value):
    with pytest.raises(source.CraSourceRefused):
        parser.amount(value)


@pytest.mark.parametrize("value", [None, b"", b"not a PDF", b"%PDF-1.7\n%%EOF", b"%PDF-" + b"a" * source.MAX_BYTES],
                         ids=["none", "empty", "not_pdf", "truncated_pdf", "oversized"])
def test_absent_malformed_or_oversized_pdf_refuses(value):
    with pytest.raises(source.CraSourceRefused):
        parser.parse_publication(value)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "nonreconciled", "unknown_shape", "bool"])
def test_incomplete_ambiguous_or_nonreconciling_recommendations_refuse(mutation):
    table = copy.deepcopy(REAL_TABLE)
    if mutation == "missing": table.pop()
    elif mutation == "duplicate": table.append(table[5])
    elif mutation == "nonreconciled": table[10][13] = "2,982.31"
    elif mutation == "unknown_shape": table[10].append("1")
    else: table[10][13] = True
    with pytest.raises(source.CraSourceRefused):
        parser.parse_table(table)


def test_nonreconciling_total_refuses_for_the_reconciliation_reason():
    table = copy.deepcopy(REAL_TABLE)
    table[10][13] = "2,982.31"
    with pytest.raises(source.CraSourceRefused, match="do not reconcile"):
        parser.parse_table(table)


def test_default_off_source_setting():
    assert SeedingSettings(_env_file=None).cra_ingestion_enabled is False


@pytest.mark.parametrize("value", [1, 0, None, "yes", "on", "1", "", float("nan"), float("inf")])
def test_cra_gate_requires_explicit_boolean(value):
    with pytest.raises(ValueError, match="CRA opt-in requires true or false"):
        SeedingSettings(cra_ingestion_enabled=value, _env_file=None)


@pytest.mark.parametrize("status,kind,body", [(404, "application/pdf", b"%PDF-"), (302, "application/pdf", b"%PDF-"), (200, "text/html", b"error"), (200, "application/pdf", b"a" * (source.MAX_BYTES + 1))], ids=['http_404', 'http_302', 'html_content_type', 'oversized_body'])
def test_real_transport_rejects_bad_response(monkeypatch, status, kind, body):
    actual_client = httpx.Client
    seen = []
    def response(request):
        seen.append(request)
        return httpx.Response(status, headers={"Content-Type": kind}, content=body)
    def client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return actual_client(**kwargs, transport=httpx.MockTransport(response))
    monkeypatch.setattr(httpx, "Client", client)
    with pytest.raises(source.CraSourceRefused): source.fetch_publication()
    assert len(seen) == 1 and str(seen[0].url) == source.URL


def parse_with_table(monkeypatch, table, text=REAL_TEXT):
    def page(number):
        if number == 0:
            return SimpleNamespace(extract_text=lambda: REAL_TITLE, extract_tables=lambda: [])
        return SimpleNamespace(extract_text=lambda: text, extract_tables=lambda: [copy.deepcopy(table)])
    class Reader:
        pages = [page(i) for i in range(REAL_PAGES)]
        def __enter__(self): return self
        def __exit__(self, *exc): return False
    monkeypatch.setattr(parser.pdfplumber, "open", lambda stream: Reader())
    return parser.parse_publication(PDF.read_bytes())


def swap(row, a, b):
    row[a], row[b] = row[b], row[a]


def header_negation(t): t[0][13] = "Not Recommended"
def header_historical(t): t[0][13] = "Previously Recommended"
def header_year_prefix(t): t[3][13] = "FY 2026/270"
def header_units(t): t[4][13] = "(Ksh. million)"
def header_complete_swap(t):
    # Retained reproduction: headers and values of baseline/recommended swapped.
    for row in t[:5]: swap(row, 7, 13)
    for row in t[5:7]: swap(row, 6, 12)
    for row in t[9:11]: swap(row, 7, 13)
def values_only_swap(t):
    # Headers intact; baseline values sit under "Recommended".
    for row in t[5:7]: swap(row, 6, 12)
    for row in t[9:11]: swap(row, 7, 13)
def recommended_shifted(t): swap(t[5], 12, 13)
def extra_cell(t): t[5][14] = "1.00"
def row_order(t): t[5], t[6] = t[6], t[5]
def label_changed(t): t[6][0] = "County Governments"
def of_which_missing(t): del t[7]
def of_which_changed(t): t[8][10] = "8.95"
def adjustment_wrong(t): t[5][9] = "298.67"
def baseline_total_wrong(t): t[10][7] = "2,639.8"
def width_changed(t): t[0].append(None)


@pytest.mark.parametrize("mutate", [header_negation, header_historical, header_year_prefix, header_units,
    header_complete_swap, values_only_swap, recommended_shifted, extra_cell, row_order, label_changed,
    of_which_missing, of_which_changed, adjustment_wrong, baseline_total_wrong, width_changed])
def test_reviewed_table_layout_and_column_identity_are_required(monkeypatch, mutate):
    table = copy.deepcopy(REAL_TABLE)
    mutate(table)
    with pytest.raises(source.CraSourceRefused):
        parse_with_table(monkeypatch, table)


def test_unchanged_real_table_through_the_same_seam_is_accepted(monkeypatch):
    # Positive control for the seam above: only a mutation makes a case refuse.
    actual = parse_with_table(monkeypatch, REAL_TABLE)
    assert actual["amounts_kes"] == parser.parse_publication(PDF.read_bytes())["amounts_kes"]


def test_printed_page_footer_is_part_of_the_reviewed_page(monkeypatch):
    with pytest.raises(source.CraSourceRefused):
        parse_with_table(monkeypatch, REAL_TABLE, text=REAL_TEXT.rstrip()[:-2] + "33")


def test_recommendations_are_exact_integer_kes_strings():
    amounts = parser.parse_publication(PDF.read_bytes())["amounts_kes"]
    assert amounts == {"national_government": "2513760000000", "county_governments": "458940000000",
                       "equalisation_fund": "9600000000", "total_shareable_revenue": "2982300000000"}


def test_retained_decimal_context_rounding_input_refuses():
    # Exact retained reviewer input: a 32-digit allocation and 33-digit total
    # reconciled only because the default Decimal context rounds both. This
    # 4-row shape now refuses on layout; the numeric bound itself is pinned by
    # test_oversized_amount_in_the_real_layout_refuses_without_rounding.
    table = [["National Government", "1", "1", "99999999999999999999999999999999"],
             ["County Government", "1", "1", "1"], ["Equalisation Fund", "1", "0", "1"],
             ["Total Revenue", "1", "100000000000000000000000000000000"]]
    with pytest.raises(source.CraSourceRefused):
        parser.parse_table(table)


@pytest.mark.parametrize("value", ["99999999999999999999999999999999", "1000000", "1,000,000", "1000000.00",
                                   "0.00", "0.0", "01", "1,000.5.0", " 1", "1 ", "1\n", "１"])
def test_out_of_bound_or_noncanonical_amounts_refuse(value):
    with pytest.raises(source.CraSourceRefused):
        parser.amount(value)


def test_oversized_amount_in_the_real_layout_refuses_without_rounding(monkeypatch):
    table = copy.deepcopy(REAL_TABLE)
    table[5][12] = "99999999999999999999999999999999"
    table[10][13] = "100000000000000000000000000000000"
    with pytest.raises(source.CraSourceRefused, match="bounded decimal grammar"):
        parse_with_table(monkeypatch, table)


def test_in_bound_amounts_convert_and_reconcile_exactly():
    # Seeded generated sweep plus boundaries: hundredths of a billion are carried
    # as integers; the KES value is exactly hundredths * 10**7, never rounded.
    rng = random.Random(602)
    cases = [1, 9, 10, 99, 100, 99_999_999] + [rng.randrange(1, 100_000_000) for _ in range(500)]
    for hundredths in cases:
        whole, cents = divmod(hundredths, 100)
        for text_value in (f"{whole}.{cents:02d}", f"{whole:,}.{cents:02d}"):
            if whole == 0 and text_value.startswith("0") and cents:
                assert parser.amount(text_value) == hundredths
            elif whole:
                assert parser.amount(text_value) == hundredths
        if cents == 0 and whole:
            assert parser.amount(f"{whole:,}") == hundredths


def test_uniformly_scaled_table_values_refuse_against_the_page_text(monkeypatch):
    # Spec-review observation: x10 on every value keeps layout and arithmetic.
    # The table and the page text are extracted separately; they must agree.
    table = copy.deepcopy(REAL_TABLE)
    scaled = {"2,215.1": "22,151", "298.66": "2,986.6", "2,513.76": "25,137.6", "415": "4,150", "43.94": "439.4",
              "458.94": "4,589.4", "35.00": "350.0", "8.94": "89.4", "9.6": "96", "0": "0", "9.60": "96.0",
              "2,639.7": "26,397", "2,982.3": "29,823"}
    for row in table[5:]:
        for i, cell in enumerate(row):
            if cell in scaled:
                row[i] = scaled[cell]
    with pytest.raises(source.CraSourceRefused, match="page text"):
        parse_with_table(monkeypatch, table)


@pytest.mark.parametrize("change", ["draft_title", "float_page_count", "garbage_pdf"])
def test_title_page_count_and_reader_errors_refuse(monkeypatch, change):
    if change == "garbage_pdf":
        with pytest.raises(source.CraSourceRefused, match="could not be read"):
            parser.parse_publication(b"%PDF-1.7\n" + b"x" * 64 + b"\n%%EOF")
    elif change == "draft_title":
        with pytest.raises(source.CraSourceRefused, match="title"):
            parser.validate_page(61, "DRAFT - NOT THE " + REAL_TITLE, REAL_TEXT, [REAL_TABLE])
    else:
        with pytest.raises(source.CraSourceRefused, match="page count"):
            parser.validate_page(61.0, REAL_TITLE, REAL_TEXT, [REAL_TABLE])

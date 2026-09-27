"""Publisher zero, unavailable targets, and lettered grant items (#238/#299)."""

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from models import BudgetLine, Entity, EntityType
from seeding.config import SeedingSettings
from seeding.domains.counties_budget import fetcher, parser, writer
from seeding.pdf_parsers import (
    ExtractedTable,
    county_revenue_receipts,
    group_revenue_tables_by_county,
)
from seeding.types import DomainRunContext


def _payload(**changes):
    return [{
        "entity_slug": "nairobi-county", "entity": "Nairobi County",
        "period_label": "2025/26", "start_date": "2025-07-01",
        "end_date": "2026-06-30", "category": "Revenue Receipts",
        "subcategory": "Total", "allocated_amount": 200, "actual_amount": 100,
        "source_url": "https://cob.go.ke/report.pdf", "data_quality": "official",
        **changes,
    }]


@pytest.mark.parametrize("field,attr", [
    ("allocated_amount", "allocated_amount"), ("actual_amount", "actual_amount"),
    ("committed_amount", "committed_amount"),
])
def test_printed_zero_survives_normalization(field, attr):
    record = parser.parse_budget_payload(_payload(**{field: 0}))[0]
    assert getattr(record, attr) == Decimal(0)


def test_canonical_zero_and_absence_do_not_take_alias_values():
    record = parser.parse_budget_payload(_payload(
        allocated_amount=None, allocated=999, actual_amount=0, actual_spent=777,
    ))[0]
    assert record.allocated_amount is None
    assert record.actual_amount == 0


def test_unavailable_pdf_target_preserves_receipts(tmp_path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF")
    raw = [{"county": "Nairobi", "category": "Revenue Receipts",
            "subcategory": "Total", "allocated": None, "absorbed": Decimal(100),
            "amounts_in": "kes", "fiscal_year": "2025/26", "quarter": None}]
    settings = SeedingSettings(cache_path=tmp_path)
    with patch("seeding.cob_cbirr.download_cbirr", return_value=SimpleNamespace(path=pdf)), patch(
        "seeding.parse_cache.parse_with_cache", return_value=raw,
    ):
        result = fetcher._download_and_parse_county_pdf(None, "https://cob.go.ke/x", settings)
    assert result[0]["allocated_amount"] is None
    assert result[0]["actual_amount"] == 100


def test_pdf_money_cells_keep_valid_thousands_separators(tmp_path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF")
    raw = [{"county": "Nairobi", "category": "Revenue Receipts",
            "subcategory": "Total", "allocated": "1,234.50", "absorbed": "1,000",
            "amounts_in": "kes", "fiscal_year": "2025/26", "quarter": None}]
    with patch("seeding.cob_cbirr.download_cbirr", return_value=SimpleNamespace(path=pdf)), patch(
        "seeding.parse_cache.parse_with_cache", return_value=raw,
    ):
        result = fetcher._download_and_parse_county_pdf(
            None, "https://cob.go.ke/x", SeedingSettings(cache_path=tmp_path),
        )
    assert result[0]["allocated_amount"] == 1234.5
    assert result[0]["actual_amount"] == 1000


def test_source_correction_clears_withdrawn_target(db_session, seed_country, tmp_path):
    db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                          slug="nairobi-county", canonical_name="Nairobi County"))
    db_session.flush()
    settings = SeedingSettings(cache_path=tmp_path)
    context = DomainRunContext(since=None, dry_run=False)
    writer.persist_budget_records(db_session, parser.parse_budget_payload(_payload()), settings, context)
    writer.persist_budget_records(db_session, parser.parse_budget_payload(_payload(allocated_amount=None)), settings, context)
    row = db_session.query(BudgetLine).one()
    assert row.actual_spent == 100
    assert row.allocated_amount is None


def _annual_tables():
    data = json.loads((Path(__file__).parent / "fixtures/cbirr_annual_revenue_sections.json").read_text())
    return group_revenue_tables_by_county(
        [ExtractedTable(**t) for t in data["tables"]],
        {int(k): v for k, v in data["captions"].items()},
    )


@pytest.mark.parametrize("county,grants,total", [
    ("Elgeyo Marakwet", "654611899", "8129336090"),
    ("Garissa", "1226402151", "11378721908"),
    ("Nairobi", "223815962", "37917986931"),
    ("Trans Nzoia", "745984665", "10003733417"),
])
def test_lettered_grant_items_stay_inside_their_section(county, grants, total):
    streams, why = county_revenue_receipts(_annual_tables()[county])
    assert why == ""
    assert streams["Additional Allocations"][1] == Decimal(grants)
    assert streams["Total"][1] == Decimal(total)


def test_mombasa_positive_control_keeps_cash_and_accrual_distinct():
    streams, why = county_revenue_receipts(_annual_tables()["Mombasa"])
    assert why == ""
    assert streams["Total"][1] == Decimal("15790774484")
    assert streams["Own Source Revenue"][1] == Decimal("3799700513")
    assert streams["Facility Improvement Financing"][1] == Decimal("2414889970")


def test_publisher_contradiction_still_withheld():
    streams, why = county_revenue_receipts(_annual_tables()["Kwale"])
    assert streams is None
    assert why.startswith("streams_do_not_sum_to_grand_total")


def test_grand_total_split_across_two_label_cells():
    streams, why = county_revenue_receipts(_annual_tables()["Baringo"])
    assert why == ""
    assert streams["Total"][1] == Decimal("9177515820")


def test_explicit_reconciled_zero_total_is_preserved():
    table = ExtractedTable(1, 0, ["No", "Revenue Stream", "Annual Target", "Actual Receipts"], [
        ["A", "Equitable Share", "", ""], ["1", "Equitable Share", "0", "0"],
        ["", "Grand Total", "0", "0"],
    ], (0, 0, 0, 0))
    streams, why = county_revenue_receipts([table])
    assert why == ""
    assert streams["Total"] == (Decimal(0), Decimal(0))


@pytest.mark.parametrize("missing", [".", "-", "–", "", None])
def test_unobserved_grand_total_cannot_become_a_printed_zero(missing):
    table = ExtractedTable(1, 0, ["No", "Revenue Stream", "Annual Target", "Actual Receipts"], [
        ["A", "Equitable Share", "0", "0"],
        ["", "Grand Total", "0", missing],
    ], (0, 0, 0, 0))
    streams, _why = county_revenue_receipts([table])
    assert streams is None

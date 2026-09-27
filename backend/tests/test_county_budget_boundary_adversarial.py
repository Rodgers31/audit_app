"""Independent county publication probes: reported zero, absence, provenance."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from models import BudgetLine, Entity, EntityType, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains.counties_budget import fetcher, parser, writer
from seeding.pdf_parsers import ExtractedTable, county_revenue_receipts
from seeding.types import DomainRunContext


def _payload(**changes):
    return [{
        "entity_slug": "nairobi-county", "entity": "Nairobi County",
        "period_label": "2024/25", "start_date": "2024-07-01",
        "end_date": "2025-06-30", "category": "Revenue Receipts",
        "subcategory": "Total", "allocated_amount": 2000000,
        "actual_amount": 1000000, "source_url": "https://cob.go.ke/report.pdf",
        "source_label": "Controller of Budget annual report FY2024/25",
        "data_quality": "official", "artifact_sha256": "a" * 64,
        "page_ref": "PDF pp. 7", **changes,
    }]


def _receipt_table(target):
    return ExtractedTable(7, 0,
        ["No", "Revenue Stream", "Annual Target", "Actual Receipts"],
        [["A", "Equitable Share", "", ""],
         ["1", "Equitable Share", target, "1000000"],
         ["", "Grand Total", target, "1000000"]], (0, 0, 0, 0))


@pytest.mark.parametrize("target", [None, "", "n/a"])
def test_absent_annual_target_is_not_a_publisher_zero(target):
    streams, reason = county_revenue_receipts([_receipt_table(target)])
    assert reason == ""
    assert streams["Total"] == (None, Decimal("1000000"))
    assert streams["Equitable Share"] == (None, Decimal("1000000"))


@pytest.mark.parametrize("target", ["0", "-"])
def test_explicit_annual_target_zero_keeps_positive_actual(target):
    streams, reason = county_revenue_receipts([_receipt_table(target)])
    assert reason == ""
    assert streams["Total"] == (Decimal(0), Decimal("1000000"))


@pytest.mark.parametrize("value", [True, False, "NaN", "sNaN", "Infinity", "-Infinity"])
def test_hostile_numbers_do_not_become_amounts(value):
    row = parser.parse_budget_payload(_payload(
        allocated_amount=value, actual_amount=value, committed_amount=value,
    ))[0]
    assert row.allocated_amount is None
    assert row.actual_amount is None
    assert row.committed_amount is None


def test_pdf_conversion_keeps_artifact_page_absence_and_zero(tmp_path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF")
    raw = [{"county": "Nairobi", "category": "Revenue Receipts",
            "subcategory": "Total", "allocated": None, "absorbed": Decimal(0),
            "amounts_in": "kes", "fiscal_year": "2024/25", "quarter": None,
            "page_ref": "PDF pp. 7"}]
    with patch("seeding.cob_cbirr.download_cbirr", return_value=SimpleNamespace(
        path=pdf, sha256="b" * 64,
    )), patch("seeding.parse_cache.parse_with_cache", return_value=raw):
        payload = fetcher._download_and_parse_county_pdf(
            None, "https://cob.go.ke/report.pdf", SeedingSettings(cache_path=tmp_path),
        )
    row = parser.parse_budget_payload(payload)[0]
    assert row.allocated_amount is None
    assert row.actual_amount == 0
    assert row.page_ref == "PDF pp. 7"
    assert row.artifact_sha256 == "b" * 64


def test_writer_withdrawal_and_reissued_artifact(db_session, seed_country, tmp_path):
    db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                          slug="nairobi-county", canonical_name="Nairobi County"))
    db_session.flush()
    settings = SeedingSettings(cache_path=tmp_path)
    context = DomainRunContext(since=None, dry_run=False)
    first = writer.persist_budget_records(db_session,
        parser.parse_budget_payload(_payload()), settings, context)
    db_session.flush()
    assert first.created == 1
    second = writer.persist_budget_records(db_session,
        parser.parse_budget_payload(_payload(allocated_amount=None,
            actual_amount=0, artifact_sha256="b" * 64, page_ref="PDF pp. 9")),
        settings, context)
    db_session.flush()
    assert second.errors == []
    row = db_session.query(BudgetLine).one()
    source = db_session.query(SourceDocument).one()
    assert row.allocated_amount is None
    assert row.actual_spent == 0
    assert row.page_ref == "PDF pp. 9"
    assert source.meta["sha256"] == "b" * 64
    assert row.provenance[-1]["artifact_sha256"] == "b" * 64
    assert row.provenance[-1]["page_ref"] == "PDF pp. 9"


def test_official_replacement_clears_current_metadata_but_keeps_history(
    db_session, seed_country, tmp_path,
):
    db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                          slug="nairobi-county", canonical_name="Nairobi County"))
    db_session.flush()
    settings = SeedingSettings(cache_path=tmp_path)
    context = DomainRunContext(since=None, dry_run=False)
    writer.persist_budget_records(db_session, parser.parse_budget_payload(
        _payload(notes="Preliminary cash basis")), settings, context)
    db_session.flush()
    row = db_session.query(BudgetLine).one()
    historical_provenance = dict(row.provenance[-1])
    assert historical_provenance["artifact_sha256"] == "a" * 64

    replacement = _payload(actual_amount=1500000)[0]
    replacement.pop("artifact_sha256")
    replacement.pop("page_ref")
    stats = writer.persist_budget_records(db_session,
        parser.parse_budget_payload([replacement]), settings, context)
    db_session.flush()
    db_session.expire_all()

    row = db_session.query(BudgetLine).one()
    source = db_session.query(SourceDocument).one()
    assert stats.errors == []
    assert row.actual_spent == 1500000
    assert (source.meta.get("sha256"), row.notes) == (None, None)
    assert source.meta["data_quality"] == "official"
    assert row.page_ref is None
    assert len(row.provenance) == 2
    assert row.provenance[0] == historical_provenance
    assert "artifact_sha256" not in row.provenance[-1]
    assert "page_ref" not in row.provenance[-1]

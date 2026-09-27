"""Offline preflight refuses absent evidence and preserves coverage receipts."""

import hashlib
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from models import BudgetLine, Entity, EntityType
from scripts import inspect_county_finance_publication as preflight
from seeding.config import SeedingSettings
from seeding.domains import counties_budget
from seeding.domains.pending_bills.brop_parser import NationalPendingBills
from seeding.pdf_parsers import KENYAN_COUNTIES, PDFCorruptedError
from seeding.types import DomainRunContext


def _files(tmp_path):
    cbirr, brop = tmp_path / "cbirr.pdf", tmp_path / "brop.pdf"
    cbirr.write_bytes(b"cbirr stand-in")
    brop.write_bytes(b"brop stand-in")
    return cbirr, brop, hashlib.sha256(cbirr.read_bytes()).hexdigest(), hashlib.sha256(brop.read_bytes()).hexdigest()


def _extractors(monkeypatch, budget_missing=False, payables_missing=False):
    budgets = [dict(county=c, category="Total", fiscal_year="2025/26",
                    allocated=Decimal(10), absorbed=Decimal(7)) for c in KENYAN_COUNTIES]
    pending = [dict(county=c, status="reported", total_millions="1") for c in KENYAN_COUNTIES]
    parser = SimpleNamespace(parse=lambda: [] if budget_missing else budgets,
                            revenue_coverage={c: dict(status="withheld", reason="no_supported_revenue_table", pages=[])
                                              for c in KENYAN_COUNTIES})
    monkeypatch.setattr(preflight, "CoBQuarterlyReportParser", lambda _: parser)
    monkeypatch.setattr(preflight, "cbirr_year_end_trade_payables", lambda _: [] if payables_missing else pending)
    monkeypatch.setattr(preflight, "CbirrStalledProjectsParser", lambda _: SimpleNamespace(parse=lambda: [dict(kind="edition", fiscal_year="2025/26")]))
    monkeypatch.setattr(preflight, "parse_brop_pdf", lambda *args, **kwargs: SimpleNamespace(
        national=NationalPendingBills(date(2026, 6, 30), Decimal(3), Decimal(1), Decimal(2))))
    return parser, budgets, pending


def test_absent_artifact_refuses_before_extracting(tmp_path, monkeypatch):
    args = _files(tmp_path)
    args[0].unlink()
    parse = MagicMock()
    monkeypatch.setattr(preflight, "CoBQuarterlyReportParser", parse)
    with pytest.raises(FileNotFoundError):
        preflight.inspect(*args)
    parse.assert_not_called()


@pytest.mark.parametrize("which", [2, 3])
def test_wrong_artifact_checksum_refuses_before_extracting(tmp_path, monkeypatch, which):
    args = list(_files(tmp_path))
    args[which] = "0" * 64
    parse = MagicMock()
    monkeypatch.setattr(preflight, "CoBQuarterlyReportParser", parse)
    with pytest.raises(ValueError, match="checksum mismatch"):
        preflight.inspect(*args)
    parse.assert_not_called()


@pytest.mark.parametrize("content", [b"", b"{}", b"%PDF-1.7\ntruncated"])
def test_real_empty_or_malformed_pdf_never_yields_receipt(tmp_path, content):
    args = list(_files(tmp_path))
    args[0].write_bytes(content)
    args[2] = hashlib.sha256(content).hexdigest()
    with pytest.raises(PDFCorruptedError):
        preflight.inspect(*args)


@pytest.mark.parametrize("missing", ["budget_missing", "payables_missing"])
def test_absent_extracted_county_evidence_refuses(tmp_path, monkeypatch, missing):
    _extractors(monkeypatch, **{missing: True})
    with pytest.raises(ValueError, match="all 47 counties"):
        preflight.inspect(*_files(tmp_path))


def test_complete_positive_control_still_marks_no_production_publication(tmp_path, monkeypatch):
    _extractors(monkeypatch)
    receipt = preflight.inspect(*_files(tmp_path))
    assert receipt["county_count"] == 47
    assert receipt["county_pending_count"] == 47
    assert receipt["county_pending_reported_sum_kes"] == Decimal(47000000)
    assert receipt["production_published"] is False
    assert receipt["revenue_counties_reconciled"] == 0
    assert receipt["combined_pending_total_kes"] is None
    assert all(r["revenue"]["status"] == "withheld" for r in receipt["coverage"])


def test_artifact_changed_during_extraction_refuses(tmp_path, monkeypatch):
    parser, budgets, _ = _extractors(monkeypatch)
    args = _files(tmp_path)
    def change():
        args[0].write_bytes(b"different edition")
        return budgets
    parser.parse = change
    with pytest.raises(ValueError, match="checksum mismatch"):
        preflight.inspect(*args)


def test_all_county_coverage_survives_normalization_and_persistence(db_session, seed_country, tmp_path, monkeypatch):
    payload = []
    for index, county in enumerate(KENYAN_COUNTIES):
        slug = county.lower().replace(" ", "-") + "-county"
        db_session.add(Entity(country_id=seed_country.id, type=EntityType.COUNTY,
                              slug=slug, canonical_name=county + " County"))
        coverage = dict(status="reconciled" if index == 0 else "withheld",
                        reason=None if index == 0 else "no_supported_revenue_table", pages=[index + 1])
        payload.append(dict(entity_slug=slug, entity=county + " County", period_label="2025/26",
                            start_date="2025-07-01", end_date="2026-06-30", category="Total",
                            allocated_amount=10000000, actual_amount=7000000,
                            source_url="https://cob.go.ke/report.pdf", data_quality="official",
                            artifact_sha256="a" * 64, revenue_coverage=coverage))
    db_session.flush()
    monkeypatch.setattr(counties_budget, "create_http_client", lambda _: MagicMock())
    monkeypatch.setattr(counties_budget.fetcher, "fetch_budget_payload", lambda *_: payload)
    result = counties_budget.run(db_session, SeedingSettings(cache_path=tmp_path), DomainRunContext(since=None, dry_run=False))
    db_session.flush()
    assert result.errors == []
    assert result.items_created == 47
    assert len(result.metadata["revenue_coverage"]) == 47
    assert sum(r["status"] == "withheld" for r in result.metadata["revenue_coverage"]) == 46
    persisted = db_session.query(BudgetLine).all()
    assert len(persisted) == 47
    assert sum(r.provenance[-1]["revenue_coverage"]["status"] == "withheld" for r in persisted) == 46

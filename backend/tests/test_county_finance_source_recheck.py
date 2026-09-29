"""A prior receipt must not silently authorize a false source recheck."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import recheck_county_finance_source as source_recheck
from scripts.recheck_county_finance_source import _validate_prior_coverage


PRIOR = Path(__file__).parents[2] / "docs/verification/2026-09-27-county-source-receipt.json"


def _coverage():
    return copy.deepcopy(json.loads(PRIOR.read_text())["coverage"])


def test_real_prior_has_exactly_47_valid_counties():
    assert len(_validate_prior_coverage(_coverage())) == 47


def test_conflicting_duplicate_cannot_hide_before_valid_county():
    rows = _coverage()
    altered = copy.deepcopy(rows[0])
    altered["budget_allocation_million_kes"] = "1"
    rows.insert(0, altered)
    with pytest.raises(ValueError, match="exactly once"):
        _validate_prior_coverage(rows)


@pytest.mark.parametrize("field,value", [
    ("budget_allocation_million_kes", "0"),
    ("budget_allocation_million_kes", "-100"),
    ("budget_allocation_million_kes", "Infinity"),
    ("period", "FY1920/21"),
])
def test_invalid_prior_budget_evidence_is_refused(field, value):
    rows = _coverage()
    rows[0][field] = value
    with pytest.raises(ValueError):
        _validate_prior_coverage(rows)


def test_invalid_prior_revenue_status_is_refused():
    rows = _coverage()
    rows[0]["revenue"]["status"] = "bogus"
    with pytest.raises(ValueError):
        _validate_prior_coverage(rows)


@pytest.mark.parametrize("value", ["Infinity", "-10"])
def test_invalid_prior_pending_amount_is_refused(value):
    rows = _coverage()
    rows[0]["pending_bills"]["total_millions"] = value
    with pytest.raises(ValueError):
        _validate_prior_coverage(rows)


def _synthetic_source_recheck(tmp_path, monkeypatch, records, pending=None):
    """Exercise receipt validation using an exact digest and prior evidence."""
    pdf = tmp_path / "cbirr.pdf"
    pdf.write_bytes(b"synthetic CoB annual source")
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    prior = json.loads(PRIOR.read_text())
    prior["cbirr_sha256"] = digest
    prior_path = tmp_path / "prior.json"
    prior_path.write_text(json.dumps(prior))

    class StubParser:
        def __init__(self, _path):
            self.revenue_coverage = {
                row["county"]: row["revenue"] for row in prior["coverage"]
            }

        def parse(self):
            return records

    monkeypatch.setattr(source_recheck, "CoBQuarterlyReportParser", StubParser)
    if pending is None:
        pending = [row["pending_bills"] for row in prior["coverage"]]
    monkeypatch.setattr(source_recheck, "cbirr_year_end_trade_payables", lambda _path: pending)
    return source_recheck.recheck(pdf, digest, prior_path)


def _current_records():
    records = []
    for row in _coverage():
        records.append({
            "county": row["county"], "category": "Total",
            "allocated": row["budget_allocation_million_kes"],
            "absorbed": row["budget_expenditure_million_kes"],
            "fiscal_year": "2025/26", "quarter": None,
        })
        if row["revenue"]["status"] == "reconciled":
            records.append({
                "county": row["county"], "category": "Revenue Receipts",
                "subcategory": "Total", "absorbed": row["revenue"]["total_kes"],
                "fiscal_year": "2025/26", "quarter": None,
            })
    return records


@pytest.mark.parametrize("category", ["Total", "Revenue Receipts"])
@pytest.mark.parametrize("mutation", ["wrong_year", "missing_year", "interim", "missing_quarter"])
def test_current_source_period_must_be_exact_annual_period(
    tmp_path, monkeypatch, category, mutation,
):
    records = _current_records()
    record = next(row for row in records if row["category"] == category)
    if mutation == "wrong_year":
        record["fiscal_year"] = "2024/25"
    elif mutation == "missing_year":
        record.pop("fiscal_year")
    elif mutation == "interim":
        record["quarter"] = "9M"
    else:
        record.pop("quarter")
    with pytest.raises(ValueError, match="Current .* period"):
        _synthetic_source_recheck(tmp_path, monkeypatch, records)


def test_other_budget_category_cannot_carry_a_mixed_period(tmp_path, monkeypatch):
    records = _current_records()
    records.append({
        "county": "Baringo", "category": "Recurrent", "allocated": "1",
        "absorbed": "1", "fiscal_year": "2024/25", "quarter": None,
    })
    with pytest.raises(ValueError, match="Current Recurrent period"):
        _synthetic_source_recheck(tmp_path, monkeypatch, records)


def test_current_payable_as_at_remains_pinned_to_prior_source_evidence(
    tmp_path, monkeypatch,
):
    records = _current_records()
    pending = [row["pending_bills"] for row in _coverage()]
    pending[0]["as_at"] = "2025-06-30"
    with pytest.raises(ValueError, match="Pending-bill source evidence changed"):
        _synthetic_source_recheck(tmp_path, monkeypatch, records, pending)

"""A prior receipt must not silently authorize a false source recheck."""

import copy
import json
from pathlib import Path

import pytest

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

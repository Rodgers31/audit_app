"""A nearby amount or arithmetic fit cannot establish a financial measure."""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest

from seeding.domains.fiscal_summary.fetcher import (
    _apply_budget_estimates,
    _merge_worldbank_data,
    _overlay_live_budget_headline,
    _overlay_live_revenue_headline,
)
from seeding.domains.national_budget.headline import extract_cob_headlines


def _pdf(monkeypatch, text):
    class Pdf:
        pages = [SimpleNamespace(extract_text=lambda: text)]
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setattr('pdfplumber.open', lambda path: Pdf())


@pytest.mark.parametrize('text', [
    'FY 2025/26 FY 2025/26. The approved budget was KSh 5.27 trillion.',
    'FY 2025/26 FY 2025/26. The revised original gross budget for FY 2025/26 was KSh 5.27 trillion.',
    'FY 2025/26 FY 2025/26. The original gross budget for FY 2024/25 was KSh 4.37 trillion.',
])
def test_native_headline_requires_original_measure_and_same_report_year(monkeypatch, text):
    _pdf(monkeypatch, text)
    budget, _, fy = extract_cob_headlines('owned.pdf', original_budget_only=True)
    assert fy == 'FY 2025/26'
    assert budget is None


def test_explicit_original_headline_still_qualifies(monkeypatch):
    _pdf(monkeypatch, "FY 2025/26 FY 2025/26. The National Government's original gross budget "
         'for FY 2025/26 amounts to KSh 4.69 trillion.')
    budget, _, fy = extract_cob_headlines('owned.pdf', original_budget_only=True)
    assert (budget, fy) == (Decimal('4690.00'), 'FY 2025/26')


def test_scalar_collection_cannot_change_annual_estimates_or_invent_split():
    payload = {'fiscal_years': [{'fiscal_year': 'FY 2025/26',
        'total_revenue': 2910, 'tax_revenue': 2560, 'non_tax_revenue': 350}]}
    before = deepcopy(payload)
    result, status = _overlay_live_revenue_headline(payload, 2968, fiscal_year='FY 2025/26')
    assert status == 'unqualified_revenue_headline'
    assert result == before


def test_budget_estimates_guard_exception_cannot_create_a_year(monkeypatch):
    from test_fiscal_headline_overlay import _Estimates
    def broken(*args):
        raise RuntimeError('owned unavailable guard')
    monkeypatch.setattr('services.trust_guards.check_fiscal_summary', broken)
    payload = {'fiscal_years': []}
    result, status = _apply_budget_estimates(payload, _Estimates())
    assert status == 'plausibility_unavailable'
    assert result == {'fiscal_years': []}


def test_worldbank_calendar_actuals_do_not_establish_an_original_appropriation():
    payload = {'fiscal_years': []}
    before = deepcopy(payload)
    result = _merge_worldbank_data(payload, {'2022': {
        'government_expenditure_lcu': 3_000_000_000_000,
        'government_revenue_lcu': 2_000_000_000_000}})
    assert result == before


def test_budget_guard_exception_cannot_authorize_overlay(monkeypatch):
    def broken(*args):
        raise RuntimeError('owned unavailable guard')
    monkeypatch.setattr('services.trust_guards.check_fiscal_summary', broken)
    payload = {'fiscal_years': [{'fiscal_year': 'FY 2025/26',
        'appropriated_budget': 4690, 'budget_basis': 'cob_gross'}]}
    before = deepcopy(payload)
    result, status = _overlay_live_budget_headline(payload, 4700)
    assert status == 'plausibility_unavailable'
    assert result == before

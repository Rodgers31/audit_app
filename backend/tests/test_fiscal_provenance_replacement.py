"""Replacing fiscal values also replaces the evidence for those values."""

import pytest
from models import FiscalSummary
from seeding.domains.fiscal_summary.parser import parse_fiscal_summary_payload
from seeding.domains.fiscal_summary.writer import write_fiscal_summary_records
from services.publication_gate import publishable_fiscal_summaries


@pytest.mark.parametrize("metadata", [
    {},
    {"fiscal_framework_absent_reason": "unreadable"},
    {"budget_basis": "cob_gross", "budget_basis_source": {"url": "https://example.org/new.pdf"}},
])
def test_partial_replacement_cannot_borrow_old_evidence(db_session, seed_country, metadata):
    def write(extra):
        records = parse_fiscal_summary_payload({"fiscal_years": [{
            "fiscal_year": "FY 2026/27", "appropriated_budget": 5000,
            "total_revenue": 3000, "total_borrowing": 1000, **extra,
        }]})
        write_fiscal_summary_records(db_session, records, {})

    write({"budget_basis": "cob_gross", "budget_basis_source": {"page": "PDF p.11"},
           "split_basis": "treasury_fiscal_framework",
           "fiscal_framework": {"total_expenditure_billion": 4000, "source": {"page": "PDF p.12"}}})
    row = db_session.query(FiscalSummary).one()
    assert publishable_fiscal_summaries([row]) == [row]
    write(metadata)
    db_session.refresh(row)
    assert row.meta == metadata
    assert row.page_ref is None
    assert publishable_fiscal_summaries([row]) == []

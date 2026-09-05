"""The /accountability/missing-funds publication gate (AUDIT_FINDINGS F5.3).

The endpoint used to serve three hardcoded cases naming Nairobi, Mombasa and
Kisumu from ``backend/data/reference/oag_audit_data.json`` — a file carrying no URL, publisher,
document title or page reference — under an on-page assurance that every case
traced to a published audit report.

These tests pin the gate in BOTH directions. A gate that only ever rejects is
indistinguishable from a broken endpoint, so the sourced case below is the
positive control: it must publish.
"""

from __future__ import annotations

import pytest

from main import missing_funds_provenance_failure


class FakeDoc:
    """Stands in for a SourceDocument row."""

    def __init__(self, doc_id: int, url=None):
        self.id = doc_id
        self.url = url


# The three cases that were live in production, verbatim from
# backend/data/reference/oag_audit_data.json. Each names a county and cites nothing.
UNSOURCED_PRODUCTION_CASES = [
    {
        "case_id": "MF_001",
        "county": "Nairobi",
        "description": "Unaccounted funds in county assembly operations",
        "amount": "KES 120M",
        "period": "FY 2023/24",
        "status": "active_investigation",
    },
    {
        "case_id": "MF_002",
        "county": "Mombasa",
        "description": "Missing funds from port levy collections",
        "amount": "KES 85M",
        "period": "FY 2023/24",
        "status": "recovery_ongoing",
    },
    {
        "case_id": "MF_003",
        "county": "Kisumu",
        "description": "Unaccounted emergency fund expenditure",
        "amount": "KES 45M",
        "period": "FY 2023/24",
        "status": "resolved",
    },
]


@pytest.mark.parametrize("case", UNSOURCED_PRODUCTION_CASES, ids=lambda c: c["case_id"])
def test_hardcoded_named_county_cases_are_withheld(case):
    """Regression fixture: the exact rows that shipped must never publish."""
    assert missing_funds_provenance_failure(case, {}) == "no_source_document"


def test_case_publishes_when_fully_sourced():
    """POSITIVE CONTROL — the gate must not be a permanent 'no'."""
    docs = {77: FakeDoc(77, url="https://www.oagkenya.go.ke/wp-content/uploads/x.pdf")}
    case = {
        "case_id": "OAG-2024-11",
        "county": "Nairobi",
        "amount": "KES 120M",
        "source_document_id": 77,
        "page_ref": "p. 23",
    }
    assert missing_funds_provenance_failure(case, docs) is None


def test_page_number_is_accepted_as_a_page_reference():
    docs = {77: FakeDoc(77, url="https://example.go.ke/report.pdf")}
    case = {"source_document_id": 77, "page_number": 23}
    assert missing_funds_provenance_failure(case, docs) is None


@pytest.mark.parametrize(
    "case,docs,expected",
    [
        # id points at a document that is not in the database
        ({"source_document_id": 999, "page_ref": "p. 1"}, {}, "source_document_not_found"),
        # document exists but a reader cannot open it — 48 such rows exist today
        (
            {"source_document_id": 77, "page_ref": "p. 1"},
            {77: FakeDoc(77, url=None)},
            "source_document_has_no_url",
        ),
        (
            {"source_document_id": 77, "page_ref": "p. 1"},
            {77: FakeDoc(77, url="   ")},
            "source_document_has_no_url",
        ),
        # document resolves, but the figure cannot be located on a page
        (
            {"source_document_id": 77},
            {77: FakeDoc(77, url="https://example.go.ke/r.pdf")},
            "no_page_reference",
        ),
        (
            {"source_document_id": 77, "page_ref": ""},
            {77: FakeDoc(77, url="https://example.go.ke/r.pdf")},
            "no_page_reference",
        ),
        # malformed ids must not slip through as truthy
        ({"source_document_id": "not-an-int"}, {}, "no_source_document"),
        ({"source_document_id": ""}, {}, "no_source_document"),
        ({"source_document_id": None}, {}, "no_source_document"),
        ({}, {}, "no_source_document"),
    ],
)
def test_each_broken_link_in_the_chain_is_rejected_with_its_own_reason(case, docs, expected):
    assert missing_funds_provenance_failure(case, docs) == expected

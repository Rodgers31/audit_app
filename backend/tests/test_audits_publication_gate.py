"""The audits publication gate (AUDIT_FINDINGS F5.4).

The /audits headline of KES 3.91T stood on 27 rows. 25 of them hang off
source_document 1836 — an OAG title whose ``url`` and ``md5`` are both NULL,
so no reader can open it — contributing KES 3.313T (84.8%). Only KES 592.06B
traces to a document that resolves.

The gate excludes a finding whose source document has no openable URL. Rows are
retained in the database, never deleted, and the count held back is reported on
the response so the omission is visible rather than inferred from a small number.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from models import (
    Audit,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    FiscalPeriod,
    Severity,
    SourceDocument,
)


@pytest.fixture()
def gate_fixture(db_session, seed_country, seed_source_doc):
    """One finding with a resolvable document, one without.

    ``seed_source_doc`` already carries a real URL. The second document
    reproduces source_document 1836: an authoritative-looking OAG title,
    status AVAILABLE, and no URL at all.
    """
    unopenable = SourceDocument(
        id=1836,
        country_id=seed_country.id,
        publisher="Office of the Auditor General",
        title=(
            "Report of the Auditor General on the Financial Statements of the "
            "National Government for FY 2023/2024"
        ),
        url=None,  # <- the defect: nothing for a citizen to open
        fetch_date=datetime(2024, 12, 15, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    county = Entity(
        id=300,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi",
        slug="nairobi-gate",
    )
    period = FiscalPeriod(
        id=300,
        country_id=seed_country.id,
        label="FY2023/24",
        start_date=datetime(2023, 7, 1),
        end_date=datetime(2024, 6, 30),
    )
    db_session.add_all([unopenable, county, period])
    db_session.flush()

    db_session.add_all(
        [
            # Traceable — must publish.
            Audit(
                entity_id=county.id,
                period_id=period.id,
                finding_text="Unsupported expenditure KES 592,062,382,245",
                severity=Severity.CRITICAL,
                source_document_id=seed_source_doc.id,
                query_type="financial_audit",
                amount=Decimal("592062382245"),
                status="Unresolved",
                audit_opinion="Adverse",
                audit_year=2025,
            ),
            # Untraceable, and a perfectly round 1.2T — must be withheld.
            Audit(
                entity_id=county.id,
                period_id=period.id,
                finding_text="Asset Management queries KES 1,200,000,000,000",
                severity=Severity.CRITICAL,
                source_document_id=unopenable.id,
                query_type="Asset Management",
                amount=Decimal("1200000000000"),
                status="Unresolved",
                audit_opinion="Adverse",
                audit_year=2023,
            ),
        ]
    )
    db_session.commit()


def test_untraceable_finding_is_excluded_from_the_headline(client, gate_fixture):
    r = client.get("/api/v1/audit/summary")
    assert r.status_code == 200
    d = r.json()

    # The 1.2T round-number row must not reach the total...
    assert d["total_unsupported_expenditure"] == pytest.approx(592_062_382_245.0)
    assert d["total_findings"] == 1
    # ...and its absence must be stated, not silent.
    assert d["withheld_findings"] == 1


def test_withheld_finding_is_retained_not_deleted(db_session, gate_fixture):
    """Quarantine, not DELETE — the row stays queryable in the database."""
    assert db_session.query(Audit).count() == 2
    assert (
        db_session.query(Audit)
        .filter(Audit.amount == Decimal("1200000000000"))
        .count()
        == 1
    )


def test_untraceable_finding_is_absent_from_the_findings_list(client, gate_fixture):
    r = client.get("/api/v1/audit/findings")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert "Asset Management" not in {i.get("query_type") for i in items}


def test_untraceable_finding_does_not_reach_trends(client, gate_fixture):
    """2023 exists only in the withheld row; it must not draw a trend point."""
    r = client.get("/api/v1/audit/trends")
    assert r.status_code == 200
    d = r.json()
    assert "2023" not in d["findings_per_year"]
    assert "2025" in d["findings_per_year"]


def test_gate_publishes_when_the_document_gains_a_url(client, db_session, gate_fixture):
    """POSITIVE CONTROL — the gate is a provenance test, not a blanket refusal.

    Give doc 1836 a URL and the same row publishes. Without this, a permanently
    empty response would be indistinguishable from a working gate.
    """
    doc = db_session.get(SourceDocument, 1836)
    doc.url = "https://www.oagkenya.go.ke/wp-content/uploads/2024/12/national.pdf"
    db_session.commit()

    d = client.get("/api/v1/audit/summary").json()
    assert d["total_findings"] == 2
    assert d["withheld_findings"] == 0
    assert d["total_unsupported_expenditure"] == pytest.approx(1_792_062_382_245.0)


def test_whitespace_only_url_does_not_count_as_a_source(client, db_session, gate_fixture):
    doc = db_session.get(SourceDocument, 1836)
    doc.url = "   "
    db_session.commit()

    d = client.get("/api/v1/audit/summary").json()
    assert d["total_findings"] == 1
    assert d["withheld_findings"] == 1

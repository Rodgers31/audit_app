"""Tests for the Amount-Questioned fix (audit §3.4 — Critical).

The /audits/federal headline summed every finding's amount (incl.
debt-service stock + asset valuations) into "Amount Questioned" = ~3.3T.
The fix uses the OAG report's own authoritative questioned total instead —
and since issue #233, when nothing extracts that total, null with a reason.
"""

from __future__ import annotations

import pytest


NAIVE_AMOUNT = 156_800_000_000.0


@pytest.fixture()
def seeded_federal(db_session, seed_country, seed_source_doc):
    """One federal finding whose source document resolves, so it publishes."""
    from datetime import datetime

    from models import Audit, Entity, EntityType, FiscalPeriod, Severity

    entity = Entity(
        id=800,
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Treasury and Economic Planning",
        slug="treasury-questioned",
    )
    period = FiscalPeriod(
        id=800,
        country_id=seed_country.id,
        label="FY2023/24",
        start_date=datetime(2023, 7, 1),
        end_date=datetime(2024, 6, 30),
    )
    db_session.add_all([entity, period])
    db_session.flush()
    db_session.add(
        Audit(
            entity_id=entity.id,
            period_id=period.id,
            finding_text="Consolidated Fund Reconciliation",
            severity=Severity.CRITICAL,
            source_document_id=seed_source_doc.id,
            amount=NAIVE_AMOUNT,
            audit_year=2023,
            provenance=[{"amount_involved": "KES 156.8B", "status": "pending"}],
            # Tier B (#137): a published finding cites a page.
            page_ref="p.409",
        )
    )
    db_session.commit()
    return {"naive_sum": NAIVE_AMOUNT}


def test_federal_headline_is_not_the_naive_sum_of_findings(client, seeded_federal):
    """The questioned headline is the report's own total or nothing.

    Nothing extracts the Auditor-General's questioned total. It used to come
    from ``oag_national_audit_data.json``, a hand-written file withheld on
    every request for citing only the OAG homepage; issue #233 retired it. So
    the headline is null with a reason, and in particular it is never the
    naive sum of finding amounts.
    """
    d = client.get("/api/v1/audits/federal").json()

    naive_sum = seeded_federal["naive_sum"]
    assert d["total_amount_in_findings"] == pytest.approx(naive_sum), (
        "the raw sum should still be exposed for transparency"
    )
    assert d["total_amount_questioned"] is None
    assert d["total_amount_questioned_reason"] == "not_extracted"
    # The label was a second copy of the figure that the page fell back to.
    assert "total_amount_questioned_label" not in d

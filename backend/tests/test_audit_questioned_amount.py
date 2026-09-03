"""Tests for the Amount-Questioned fix (audit §3.4 — Critical).

The /audits/federal headline summed every finding's amount (incl.
debt-service stock + asset valuations) into "Amount Questioned" = ~3.3T.
The fix uses the OAG report's own authoritative questioned total instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from main import _parse_kes_amount_str

BACKEND_DIR = Path(__file__).resolve().parent.parent

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
        )
    )
    db_session.commit()
    return {"naive_sum": NAIVE_AMOUNT}


@pytest.mark.parametrize(
    "value,expected",
    [
        ("KES 981.3B", 981_300_000_000.0),
        ("981.3B", 981_300_000_000.0),
        ("1.2T", 1_200_000_000_000.0),
        ("500M", 500_000_000.0),
        ("5K", 5_000.0),
        ("1,234.5B", 1_234_500_000_000.0),
        ("KES 0", 0.0),
        ("", None),
        (None, None),
        ("garbage", None),
    ],
)
def test_parse_kes_amount_str(value, expected):
    assert _parse_kes_amount_str(value) == expected


def test_federal_headline_is_not_the_naive_sum_of_findings(client, seeded_federal):
    """The two figures must be distinct, and the headline must not be the sum.

    Previously asserted by grepping main.py for a literal source string, which
    passes or fails on how the line is spelled rather than on what the endpoint
    returns — the pattern AUDIT_FINDINGS §P6 calls "testing the guard rails and
    not the thing being guarded". It broke when the field became a conditional
    expression while the behaviour was unchanged. Assert the response instead.
    """
    d = client.get("/api/v1/audits/federal").json()

    naive_sum = seeded_federal["naive_sum"]
    assert d["total_amount_in_findings"] == pytest.approx(naive_sum), (
        "the raw sum should still be exposed for transparency"
    )
    # The headline is the OAG report's own questioned total, not the sum.
    assert d["total_amount_questioned"] != d["total_amount_in_findings"]
    assert d["total_amount_questioned"] == _parse_kes_amount_str(
        d["total_amount_questioned_label"]
    )


def test_federal_headline_still_parses_the_authoritative_label(client, seeded_federal):
    """Whatever the label says, the numeric headline must agree with it."""
    d = client.get("/api/v1/audits/federal").json()
    label = d["total_amount_questioned_label"]
    if label:
        assert d["total_amount_questioned"] == _parse_kes_amount_str(label)

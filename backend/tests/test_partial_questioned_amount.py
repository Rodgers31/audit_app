"""A partial sum must be published WITH its coverage, or not at all.

Production, FY2024/25: the OAG report's own authoritative "amount questioned"
was never extracted, so ``total_amount_questioned`` is null and the audits page
shows an em-dash. That is correct — a naive sum of finding amounts is not the
questioned total, and an earlier version of this endpoint conflated the two and
published a misleading ~3.3T.

But the endpoint DOES compute an honest partial: 49 of the 813 published
findings state a figure, summing to KES 73.4B. Showing nothing hides a real,
sourced number; showing it bare would imply it is the total. It is surfaced
with its coverage attached, which is what makes it safe.

Two defects pinned here:

1. ``amount_numeric`` was ``0.0`` for the 764 findings that state no figure —
   a manufactured zero on a SOURCED, published finding, and the exact class
   PR #135 existed to remove. A client summing the array cannot tell "nothing
   was questioned" from "the report states no figure here".

2. The response gave no way to qualify the partial. ``total_amount_in_findings``
   alone cannot be rendered honestly, because a reader cannot tell whether it
   covers 49 findings or all 813.
"""

from __future__ import annotations

import pytest


class TestAbsentAmountsAreNull:
    def test_a_finding_with_no_stated_figure_reports_null_not_zero(
        self, client, db_session, seed_country, seed_source_doc
    ):
        """RED before the fix: ``amount_val`` initialised to 0.0 and stayed
        there, so the finding published ``amount_numeric: 0.0``."""
        from datetime import date

        from models import Audit, Entity, EntityType, FiscalPeriod, Severity

        entity = Entity(
            country_id=seed_country.id, type=EntityType.MINISTRY,
            canonical_name="State Department for Testing",
            slug="state-department-for-testing",
        )
        period = FiscalPeriod(
            country_id=seed_country.id, label="FY 2024/25",
            start_date=date(2024, 7, 1), end_date=date(2025, 6, 30),
        )
        db_session.add_all([entity, period])
        db_session.flush()

        # A real, publishable finding that states no dollar figure — the
        # ordinary case: 764 of production's 813 look exactly like this.
        db_session.add(
            Audit(
                entity_id=entity.id, period_id=period.id,
                source_document_id=seed_source_doc.id,
                finding_text="Lack of a Risk Management Policy",
                severity=Severity.INFO, page_ref="p.630", amount=None,
            )
        )
        db_session.commit()

        body = client.get("/api/v1/audits/federal").json()
        mine = [f for f in body.get("findings", [])
                if f.get("finding") == "Lack of a Risk Management Policy"]
        assert mine, "the finding was not published; fixture is not exercising the path"
        assert mine[0]["amount_numeric"] is None, (
            "a finding that states no figure published amount_numeric=0.0 — "
            "indistinguishable from a finding that questioned nothing"
        )


class TestThePartialCarriesItsCoverage:
    def test_the_response_says_how_many_findings_the_sum_covers(
        self, client, db_session
    ):
        """RED before the fix: no field reported the denominator, so
        ``total_amount_in_findings`` could not be rendered honestly."""
        body = client.get("/api/v1/audits/federal").json()
        assert "findings_with_amount" in body, (
            "no coverage count: a partial sum with no denominator cannot be "
            "distinguished from a total"
        )
        assert isinstance(body["findings_with_amount"], int)
        assert body["findings_with_amount"] <= body["total_findings"]

    def test_the_coverage_matches_the_findings_that_carry_a_figure(
        self, client, db_session
    ):
        """Anti-drift: the count must be derived from the same rows the sum
        is, not tallied separately."""
        body = client.get("/api/v1/audits/federal").json()
        counted = sum(
            1 for f in body.get("findings", []) if f.get("amount_numeric") is not None
        )
        assert body["findings_with_amount"] == counted

    def test_the_sum_equals_the_amounts_actually_published(self, client, db_session):
        total = client.get("/api/v1/audits/federal").json()
        published = sum(
            f["amount_numeric"] for f in total.get("findings", [])
            if f.get("amount_numeric") is not None
        )
        if total.get("total_amount_in_findings") is None:
            assert published == 0
        else:
            assert abs(total["total_amount_in_findings"] - published) < 1.0

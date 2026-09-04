"""Folding the Auditor-General's report-section headings (credibility audit F39).

`audits.query_type` holds whatever heading text the blue-book extractor
captured, truncated at different points and cased differently page to page.
Production carries TWELVE variants of the OAG's three standing sub-reports,
plus a raw `financial_audit` enum leaked from an earlier loader. Rendered as a
filter facet that is twelve near-identical options a reader cannot choose
between; as a bar chart it is twelve bars where there are three categories.

These pin the fold in both directions — an unrecognised heading must survive,
or the mapping is silently deciding things it has no basis for.
"""

from __future__ import annotations

import pytest
from services.oag_report_sections import (
    FINANCIAL_STATEMENTS,
    INTERNAL_CONTROLS,
    LAWFULNESS,
    canonical_section,
    group_counts,
    raw_variants_for,
)

# Every distinct query_type GET /api/v1/audit/summary returned on 2026-09-03.
LIVE_VARIANTS = {
    "REPORT ON THE FINANCIAL STATEMENTS": FINANCIAL_STATEMENTS,
    "financial_audit": FINANCIAL_STATEMENTS,
    "REPORT ON LAWFULNESS AND EFFECTIVENESS IN THE USE OF PUBLIC": LAWFULNESS,
    "REPORT ON LAWFULNESS AND EFFECTIVENESS IN USE OF PUBLIC": LAWFULNESS,
    "Report on Lawfulness and Effectiveness in Use of Public Resources and Report on": LAWFULNESS,
    "Report on Lawfulness and Effectiveness in Use of Public Resources, and Report on": LAWFULNESS,
    "Report on Lawfulness and Effectiveness in the Use of Public Resources and Report on": LAWFULNESS,
    "Report on Lawfulness and Effectiveness in the Use of Public Resources. Review of the": LAWFULNESS,
    "REPORT ON EFFECTIVENESS OF INTERNAL CONTROLS, RISK MANAGEMENT": INTERNAL_CONTROLS,
    "Report on Effectiveness of Internal Controls, Risk Management and Governance,": INTERNAL_CONTROLS,
    "Report on Effectiveness of Internal Controls, Risk Management and Governance.": INTERNAL_CONTROLS,
    "Report on Effectiveness of Internal Controls, Risk Management and Governance. Review": INTERNAL_CONTROLS,
}


@pytest.mark.parametrize("raw,expected", sorted(LIVE_VARIANTS.items()))
def test_every_live_variant_folds_to_its_section(raw, expected):
    assert canonical_section(raw) == expected


def test_twelve_variants_become_three_sections():
    counts = {raw: 1 for raw in LIVE_VARIANTS}
    grouped = group_counts(counts)
    assert len(counts) == 12
    assert set(grouped) == {FINANCIAL_STATEMENTS, LAWFULNESS, INTERNAL_CONTROLS}
    assert sum(grouped.values()) == 12, "folding must not lose or duplicate a finding"


def test_counts_are_preserved_when_folding():
    grouped = group_counts(
        {
            "REPORT ON THE FINANCIAL STATEMENTS": 400,
            "financial_audit": 5,
            "REPORT ON LAWFULNESS AND EFFECTIVENESS IN USE OF PUBLIC": 30,
            "Report on Lawfulness and Effectiveness in the Use of Public Resources. Review of the": 12,
        }
    )
    assert grouped[FINANCIAL_STATEMENTS] == 405
    assert grouped[LAWFULNESS] == 42


# ── The fold must not overreach ────────────────────────────────────────────

def test_a_lawfulness_heading_that_mentions_internal_controls_stays_lawfulness():
    # Several stored headings run "...Use of Public Resources and Report on
    # Effectiveness of Internal Controls...". Matching "internal controls"
    # anywhere in the string would file these under the wrong section.
    raw = (
        "Report on Lawfulness and Effectiveness in Use of Public Resources and "
        "Report on Effectiveness of Internal Controls, Risk Management and Governance"
    )
    assert canonical_section(raw) == LAWFULNESS


def test_an_unrecognised_heading_passes_through_unchanged():
    raw = "Report on Something The Extractor Has Not Seen Before"
    assert canonical_section(raw) == raw


def test_blank_and_null_are_not_invented_into_a_section():
    assert canonical_section(None) is None
    assert canonical_section("") is None
    assert canonical_section("   ") is None


# ── Filtering: a canonical value must expand back to the raw rows ─────────

def test_canonical_filter_expands_to_every_stored_variant():
    known = list(LIVE_VARIANTS)
    variants = raw_variants_for(LAWFULNESS, known)
    assert len(variants) == 6
    assert all(canonical_section(v) == LAWFULNESS for v in variants)


def test_an_exact_raw_heading_still_matches_itself():
    # Links made before the fold shipped carry a raw heading; they must not
    # start returning an empty page.
    known = list(LIVE_VARIANTS)
    raw = "REPORT ON THE FINANCIAL STATEMENTS"
    assert raw in raw_variants_for(raw, known)


# ── Recurrence must be decided on the folded section, not the raw heading ──

def test_variants_of_one_section_merge_into_a_single_recurring_row(
    client, db_session, seed_country, seed_source_doc
):
    """Two heading variants of one standing section, in two different years.

    Grouping on the raw query_type produced two rows carrying the same
    canonical label with the years split between them — and, because neither
    raw variant spanned 2 years on its own, the recurrence was missed
    altogether.
    """
    from datetime import datetime

    from models import Audit, Entity, EntityType, FiscalPeriod, Severity

    entity = Entity(
        id=610, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Mombasa County", slug="mombasa-county",
    )
    period = FiscalPeriod(
        id=6100, country_id=seed_country.id, label="FY2022/23",
        start_date=datetime(2022, 7, 1), end_date=datetime(2023, 6, 30),
    )
    db_session.add_all([entity, period])
    db_session.flush()

    # Two real variants of one standing section: differing case, a trailing
    # full stop, and truncated at different points.
    variants = [
        ("Report on Lawfulness and Effectiveness in the Use of Public Resources", 2022, 1_000_000),
        ("REPORT ON LAWFULNESS AND EFFECTIVENESS IN USE OF PUBLIC RESOURCES.", 2023, 2_000_000),
    ]
    assert (
        canonical_section(variants[0][0]) == canonical_section(variants[1][0])
    ), "fixture is only meaningful if these two headings fold together"

    for qt, year, amount in variants:
        db_session.add(
            Audit(
                entity_id=entity.id, period_id=period.id, query_type=qt,
                audit_year=year, amount=amount, severity=Severity.CRITICAL,
                finding_text=f"Finding recorded under {qt!r} for {year}.",
                source_document_id=seed_source_doc.id,
                created_at=datetime(year, 7, 1),
            )
        )
    db_session.commit()

    resp = client.get("/api/v1/audit/recurring")
    assert resp.status_code == 200, resp.text[:400]
    body = resp.json()
    rows = [
        r for r in body["recurring_findings"]
        if r["county_name"] == "Mombasa County"
    ]

    assert len(rows) == 1, (
        f"expected one merged row for the folded section, got {len(rows)}: "
        f"{[(r['query_type'], r['years_appeared']) for r in rows]}"
    )
    assert rows[0]["years_appeared"] == [2022, 2023], (
        "the recurrence spans two years only once the heading variants are "
        f"folded; got {rows[0]['years_appeared']}"
    )
    assert rows[0]["total_amount"] == 3_000_000
    assert len(rows[0]["finding_ids"]) == 2

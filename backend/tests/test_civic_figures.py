"""Tests for /learn/civic-figures — the live glossary figure registry.

Audit §2.7 / DESIGN §5.9. The Learn glossary used to hardcode fiscal
magnitudes (GDP "15.0T", budget "3.9T", debt "10T", equitable share
"400B") that silently went stale. These now resolve from their one
canonical DB source via this endpoint so the glossary self-updates.

These tests lock in:
  1. Each figure's value/period comes straight from the seeded DB row
     (change the row → change the response: no hardcoded magnitude).
  2. Public debt uses the outstanding stock and EXCLUDES pending bills,
     so it can't diverge from /debt/national.
  3. An empty DB returns available=False for every figure (the UI then
     shows a dated last-known fallback) and never 500s.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from models import (
    DebtCategory,
    Entity,
    EntityType,
    FiscalSummary,
    GDPData,
    Loan,
)


@pytest.fixture()
def seed_civic_data(db_session, seed_country, seed_source_doc):
    """Seed one canonical row per glossary figure plus an excluded pending bill."""
    national = Entity(
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Government",
        slug="national-government",
    )
    db_session.add(national)
    db_session.flush()

    # Nominal GDP — national series (entity_id NULL), latest year 2024.
    db_session.add(
        GDPData(
            entity_id=None,
            year=2024,
            gdp_value=16_224_478_000_000,
            currency="KES",
            source_document_id=seed_source_doc.id,
        )
    )

    # Fiscal summary — national budget + county equitable share.
    # NOTE: FiscalSummary stores BILLION-KES (4190 = KES 4.19T), unlike
    # GDPData/Loan which store raw KES. The endpoint must normalise to raw
    # KES; we seed billions here to lock that conversion (matches production).
    db_session.add(
        FiscalSummary(
            fiscal_year="FY2025/26",
            appropriated_budget=4190,
            county_allocation=405,
            source_document_id=seed_source_doc.id,
            # Tier B (#137): a published fiscal row cites a page.
            page_ref="s.3.2, report p.16 (PDF p.37)",
        )
    )

    # Two real debt loans (counted) + one pending bill (must be excluded).
    issued = datetime(2024, 7, 1, tzinfo=timezone.utc)
    db_session.add_all(
        [
            Loan(
                entity_id=national.id,
                lender="Eurobond",
                debt_category=DebtCategory.EXTERNAL_COMMERCIAL,
                principal=8_000_000_000_000,
                outstanding=8_000_000_000_000,
                currency="KES",
                issue_date=issued,
                source_document_id=seed_source_doc.id,
            ),
            Loan(
                entity_id=national.id,
                lender="Domestic bondholders",
                debt_category=DebtCategory.DOMESTIC_BONDS,
                principal=4_660_000_000_000,
                outstanding=4_660_000_000_000,
                currency="KES",
                issue_date=issued,
                source_document_id=seed_source_doc.id,
            ),
            Loan(
                entity_id=national.id,
                lender="Suppliers",
                debt_category=DebtCategory.PENDING_BILLS,
                principal=700_000_000_000,
                outstanding=700_000_000_000,
                currency="KES",
                issue_date=issued,
                source_document_id=seed_source_doc.id,
            ),
        ]
    )
    db_session.commit()
    return national


def test_civic_figures_resolve_from_db(client, seed_civic_data):
    resp = client.get("/api/v1/learn/civic-figures")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    figs = body["figures"]

    # GDP — exact seeded value, period = the data year (not a literal).
    assert figs["nominal_gdp"]["available"] is True
    assert figs["nominal_gdp"]["value"] == 16_224_478_000_000
    assert figs["nominal_gdp"]["period"] == "2024"

    # Budget + equitable share — exact seeded values, period = fiscal year.
    assert figs["national_budget"]["value"] == 4_190_000_000_000
    assert figs["national_budget"]["period"] == "FY2025/26"
    assert figs["equitable_share"]["value"] == 405_000_000_000
    assert figs["equitable_share"]["period"] == "FY2025/26"

    # Public debt — outstanding stock EXCLUDING the 700B pending bill.
    assert figs["public_debt"]["available"] is True
    assert figs["public_debt"]["value"] == 12_660_000_000_000
    assert figs["public_debt"]["value"] != 13_360_000_000_000  # would include PB


def test_civic_figures_track_the_db_not_a_constant(client, db_session, seed_civic_data):
    """Changing the seeded GDP row changes the response — proves no hardcoding."""
    from main import clear_all_caches

    row = (
        db_session.query(GDPData)
        .filter(GDPData.entity_id.is_(None), GDPData.year == 2024)
        .first()
    )
    row.gdp_value = 17_000_000_000_000
    db_session.commit()
    clear_all_caches()  # endpoint is @cached; drop the prior response

    resp = client.get("/api/v1/learn/civic-figures")
    assert resp.json()["figures"]["nominal_gdp"]["value"] == 17_000_000_000_000


def test_civic_figures_empty_db_is_unavailable_not_zero(client):
    resp = client.get("/api/v1/learn/civic-figures")
    assert resp.status_code == 200
    figs = resp.json()["figures"]
    for key in ("nominal_gdp", "national_budget", "public_debt", "equitable_share"):
        assert figs[key]["available"] is False
        assert figs[key]["value"] in (None, 0)


# ── The equitable share is not county transfers (#237 consolidation review) ──
#
# #260 redefines FiscalSummary.county_allocation as ALL county transfers (the
# Budget Summary's framework line: FY2026/27 495.5B) instead of the equitable
# share alone (420.0B). The glossary card renders this figure as "counties were
# allocated about KES {value} as their equitable share", so it must read the
# framework's own equitable-share line when a row carries one, and never
# publish transfers under that label.


def _framework_row(fy, county_transfers_b, equitable_share_b, page="Annex Table 2a, PDF p.63"):
    return FiscalSummary(
        fiscal_year=fy,
        appropriated_budget=5485.7,
        county_allocation=county_transfers_b,
        page_ref=page,
        meta={
            "split_basis": "treasury_fiscal_framework",
            "fiscal_framework": {
                "county_transfers_billion": county_transfers_b,
                "county_equitable_share_billion": equitable_share_b,
            },
        },
    )


def test_equitable_share_is_the_framework_line_not_the_transfers(client, db_session, seed_source_doc):
    row = _framework_row("FY2026/27", 495.5, 420.0)
    row.source_document_id = seed_source_doc.id
    db_session.add(row)
    db_session.commit()

    figs = client.get("/api/v1/learn/civic-figures").json()["figures"]
    assert figs["equitable_share"]["value"] == 420_000_000_000, figs["equitable_share"]
    assert figs["equitable_share"]["period"] == "FY2026/27"


def test_a_transfers_row_without_a_share_line_is_not_published_as_the_share(
    client, db_session, seed_source_doc
):
    older = FiscalSummary(
        fiscal_year="FY2022/23",
        appropriated_budget=3300,
        county_allocation=370,  # pre-#260 rows: the equitable share itself
        source_document_id=seed_source_doc.id,
        page_ref="p. 12",
    )
    newer = _framework_row("FY2026/27", 495.5, None)
    newer.source_document_id = seed_source_doc.id
    db_session.add_all([older, newer])
    db_session.commit()

    share = client.get("/api/v1/learn/civic-figures").json()["figures"]["equitable_share"]
    # Not 495.5B under the equitable-share label; the latest row that states
    # the share is the older, share-basis one.
    assert share["value"] == 370_000_000_000, share
    assert share["period"] == "FY2022/23"

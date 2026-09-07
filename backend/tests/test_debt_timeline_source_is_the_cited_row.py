"""``/debt/timeline`` must credit the document behind the figure it reports.

The endpoint took its ``source`` title from ``rows[0]`` — the **oldest** row in
a series ordered ``year.asc()`` — while ``last_updated`` came from ``rows[-1]``
and ``reconciliation.primary_value_kes`` is ``rows[-1].total``. Every other
top-level field describes the newest row; only the attribution described the
oldest.

The series runs 2013-2025, so production served::

    "source":       "CBK public debt table, December 2013"
    "last_updated": "2026-09-06T03:35:45"
    primary_value:  12,299.5Bn      (the 2025 row)

A December 2013 table for a 2025 figure. And the site says so twice, two
different ways: ``/provenance/verify/debt_timeline?year=2025`` resolves the
same number to a different document entirely. One number, two cited sources,
neither reader can tell which is the lie.

The fix is not a better guess at a series-wide title — the series genuinely
spans many documents. It is to attribute the figure the response leads with to
the document that figure came from, and to say plainly that the earlier years
came from elsewhere.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from models import (
    DebtTimeline,
    DocumentStatus,
    DocumentType,
    SourceDocument,
)


def timeline(client) -> dict:
    from main import clear_all_caches

    clear_all_caches()
    body = client.get("/api/v1/debt/timeline").json()
    assert body["status"] == "success", body
    return body


def _doc(db, country, doc_id, title, year):
    doc = SourceDocument(
        id=doc_id,
        country_id=country.id,
        publisher="Central Bank of Kenya",
        title=title,
        url=f"https://www.centralbank.go.ke/public-debt/{year}",
        fetch_date=datetime(year, 12, 31, tzinfo=timezone.utc),
        doc_type=DocumentType.REPORT,
        status=DocumentStatus.AVAILABLE,
    )
    db.add(doc)
    db.commit()
    return doc


@pytest.fixture()
def thirteen_year_series(db_session, seed_country):
    """The production shape: an old row and a current row, different documents."""
    oldest = _doc(db_session, seed_country, 700,
                  "CBK public debt table, December 2013", 2013)
    newest = _doc(db_session, seed_country, 701,
                  "CBK Statistical Bulletin Table 4.1.3", 2025)
    B = 1e9
    db_session.add_all([
        DebtTimeline(year=2013, external=1200.0 * B, domestic=1100.0 * B,
                     total=2300.0 * B, gdp_ratio=40.0, unit="KES",
                     source_document_id=oldest.id),
        DebtTimeline(year=2024, external=5057.0 * B, domestic=5868.3 * B,
                     total=10925.3 * B, gdp_ratio=67.3, unit="KES",
                     source_document_id=newest.id),
        DebtTimeline(year=2025, external=5462.0 * B, domestic=6837.5 * B,
                     total=12299.5 * B, gdp_ratio=70.0, unit="KES",
                     source_document_id=newest.id),
    ])
    db_session.commit()
    return {"oldest": oldest, "newest": newest}


def test_source_is_not_the_document_behind_the_oldest_row(
    client, thirteen_year_series
):
    """The exact production defect: a 2013 table credited for a 2025 figure."""
    body = timeline(client)
    assert body["source"] != "CBK public debt table, December 2013"


def test_source_is_the_document_behind_the_figure_the_response_leads_with(
    client, thirteen_year_series
):
    """``source``, ``last_updated`` and ``primary_value_kes`` describe one row."""
    body = timeline(client)
    assert body["source"] == "CBK Statistical Bulletin Table 4.1.3"
    assert body["reconciliation"]["primary_value_kes"] == pytest.approx(12299.5e9)


def test_the_attributed_year_is_stated_so_the_claim_is_checkable(
    client, thirteen_year_series
):
    """A reader must be able to see WHICH year the cited document covers.

    Without it the citation is unfalsifiable: any document title beside a
    13-year series reads as if it covered the whole series.
    """
    body = timeline(client)
    assert body["source_year"] == 2025


def test_earlier_years_are_declared_as_coming_from_other_documents(
    client, thirteen_year_series
):
    """The series spans documents; saying so is the honest part of the fix."""
    body = timeline(client)
    assert body["source_covers_full_series"] is False


def test_a_single_document_series_says_so(client, db_session, seed_country):
    """Positive control: when one document really does cover every row, the
    endpoint must not manufacture a caveat that does not apply."""
    only = _doc(db_session, seed_country, 702,
                "CBK Statistical Bulletin Table 4.1.3", 2025)
    B = 1e9
    db_session.add_all([
        DebtTimeline(year=2024, external=5057.0 * B, domestic=5868.3 * B,
                     total=10925.3 * B, unit="KES", source_document_id=only.id),
        DebtTimeline(year=2025, external=5462.0 * B, domestic=6837.5 * B,
                     total=12299.5 * B, unit="KES", source_document_id=only.id),
    ])
    db_session.commit()

    body = timeline(client)
    assert body["source"] == "CBK Statistical Bulletin Table 4.1.3"
    assert body["source_covers_full_series"] is True

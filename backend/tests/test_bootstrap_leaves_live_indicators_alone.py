"""Bootstrap must not write indicator values a live domain owns (issue #232).

``_seed_economic_indicators`` wrote literal ``inflation_rate`` and
``unemployment_rate`` rows on every backend start and every Sunday. The
economic_indicators domain's World Bank pull writes the same keys at the same
``YYYY-12-31`` dates, so the two overwrote each other; bootstrap's
``inflation_rate`` 2024-12-31 = 6.6 is December 2023's figure, and its update
path changed ``value`` without ``meta``, leaving a bootstrap number under
World Bank provenance.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import bootstrap
from models import EconomicIndicator
from seeding.domains.economic_indicators import writer


def _rows(db_session, kind):
    return (
        db_session.query(EconomicIndicator)
        .filter(EconomicIndicator.indicator_type == kind)
        .order_by(EconomicIndicator.indicator_date)
        .all()
    )


def test_bootstrap_writes_no_live_owned_indicator(db_session, seed_source_doc):
    bootstrap._seed_economic_indicators(
        db_session, source_document_id=seed_source_doc.id
    )
    db_session.flush()
    assert _rows(db_session, "inflation_rate") == []
    assert _rows(db_session, "unemployment_rate") == []
    # CPI also belongs to the dedicated economic_indicators domain.
    assert _rows(db_session, "CPI") == []


def test_bootstrap_does_not_overwrite_a_live_row(db_session, seed_source_doc):
    live_meta = {
        "source_label": "World Bank, World Development Indicators",
        "measure": "CPI inflation, annual average",
    }
    db_session.add(
        EconomicIndicator(
            indicator_type="inflation_rate",
            indicator_date=datetime(2024, 12, 31),
            value=Decimal("4.49"),
            unit="percent",
            meta=live_meta,
        )
    )
    db_session.flush()
    bootstrap._seed_economic_indicators(
        db_session, source_document_id=seed_source_doc.id
    )
    db_session.flush()
    (row,) = [
        r for r in _rows(db_session, "inflation_rate")
        if r.indicator_date == datetime(2024, 12, 31)
    ]
    assert float(row.value) == 4.49  # not bootstrap's 6.6
    assert row.meta == live_meta


def test_bootstrap_waits_for_live_coverage_before_retiring_legacy_rows(
    db_session, seed_source_doc, caplog
):
    db_session.add_all(
        [
            EconomicIndicator(
                indicator_type=kind,
                indicator_date=day,
                value=Decimal(value),
                unit="percent",
                source_document_id=seed_source_doc.id,
                meta={"source": "KNBS", "bootstrap": True},
            )
            for kind, day, value in [
                ("inflation_rate", datetime(2024, 6, 30), "4.6"),
                ("inflation_rate", datetime(2025, 1, 31), "3.3"),
                ("unemployment_rate", datetime(2022, 12, 31), "5.7"),
            ]
        ]
    )
    db_session.flush()
    bootstrap._seed_economic_indicators(
        db_session, source_document_id=seed_source_doc.id
    )
    db_session.flush()
    assert [
        row.indicator_date.date().isoformat()
        for row in _rows(db_session, "inflation_rate")
    ] == [
        "2024-06-30", "2025-01-31"
    ]
    original_ids = {row.id for row in _rows(db_session, "inflation_rate")}
    assert len(_rows(db_session, "unemployment_rate")) == 1
    assert "Preserved 3 legacy bootstrap economic-indicator rows" in caplog.text
    assert all(str(row_id) in caplog.text for row_id in original_ids)

    assert writer.remove_superseded_rows(db_session, {}) == ([], [])
    db_session.flush()
    assert {row.id for row in _rows(db_session, "inflation_rate")} == original_ids

    receipts = []
    removed, errors = writer.remove_superseded_rows(
        db_session,
        {"inflation_rate": {"2023-12-31", "2024-12-31", "2025-12-31"}},
        receipts=receipts,
    )
    db_session.flush()
    assert errors == []
    assert sorted(removed) == [
        ("inflation_rate", "2024-06-30", 4.6),
        ("inflation_rate", "2025-01-31", 3.3),
    ]
    assert {receipt["id"] for receipt in receipts} == original_ids
    assert all(
        receipt["source_document_id"] == seed_source_doc.id
        for receipt in receipts
    )
    assert sorted(receipt["date"] for receipt in receipts) == [
        "2024-06-30", "2025-01-31"
    ]
    assert _rows(db_session, "inflation_rate") == []
    assert len(_rows(db_session, "unemployment_rate")) == 1

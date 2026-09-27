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
    # The KNBS CPI index has no live owner and is still seeded.
    assert len(_rows(db_session, "CPI")) == 2


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


def test_bootstrap_removes_the_rows_it_created_before(db_session, seed_source_doc):
    db_session.add_all(
        [
            EconomicIndicator(
                indicator_type=kind,
                indicator_date=day,
                value=Decimal(value),
                unit="percent",
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
    assert _rows(db_session, "inflation_rate") == []
    assert _rows(db_session, "unemployment_rate") == []

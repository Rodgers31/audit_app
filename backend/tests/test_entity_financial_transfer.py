"""Financial summaries must not download unused document fields and row notes."""
from collections import defaultdict

import pytest
from sqlalchemy.orm import joinedload

from models import BudgetLine
from services.entity_financials import entity_financial_series, financial_summary
from test_entity_financial_accounting import accounts
from test_public_query_transfer import capture_selected


def legacy_series(db, ids):
    """Original one-snapshot query and aggregation, retained as differential oracle."""
    lines = db.query(BudgetLine).options(
        joinedload(BudgetLine.period), joinedload(BudgetLine.source_document),
    ).filter(BudgetLine.entity_id.in_(ids)).all()
    grouped = defaultdict(lambda: defaultdict(list))
    for line in lines:
        grouped[line.entity_id][line.period_id].append(line)
    return {
        eid: [financial_summary(rows, rows[0].period) for rows in sorted(
            periods.values(),
            key=lambda rows: (rows[0].period.start_date, rows[0].period.end_date, rows[0].period_id),
            reverse=True,
        )]
        for eid, periods in grouped.items()
    }


@pytest.mark.parametrize("meta", [
    {"data_quality": "official", "unused": "x" * 65536},
    {"data_quality": "projected", "unused": "x" * 65536},
    {"dataset_id": "bootstrap-v1", "unused": "x" * 65536},
    {"source": "bootstrap", "unused": "x" * 65536},
    None, False, 0, "projected", [],
    {"data_quality": {"unexpected": True}, "dataset_id": ["bootstrap"], "source": []},
])
def test_series_preserves_complete_output_without_unused_transfer(
    db_session, accounts, seed_source_doc, meta, record_property,
):
    entity, _ = accounts
    seed_source_doc.meta = meta
    seed_source_doc.file_path = "p" * 65536
    for line in db_session.query(BudgetLine):
        line.notes = "n" * 65536
        line.actual_spent = 0 if line.category == "Total" else None
    db_session.commit()
    ids = [entity.id]
    db_session.expunge_all()
    expected, before = capture_selected(db_session, lambda: legacy_series(db_session, ids))
    db_session.expunge_all()
    actual, after = capture_selected(db_session, lambda: entity_financial_series(db_session, ids))
    assert actual == expected
    assert actual[entity.id][0]["budget_lines_count"] == 1
    assert len(after) == 1, "Financial rows and publication context share one SQL snapshot"
    old_bytes, new_bytes = (sum(s["bytes"] for s in selections) for selections in (before, after))
    record_property("before_selected_value_bytes", old_bytes)
    record_property("after_selected_value_bytes", new_bytes)
    assert new_bytes < 15000, (old_bytes, new_bytes)
    assert new_bytes * 20 < old_bytes


def test_empty_series_does_not_query(db_session):
    result, selects = capture_selected(db_session, lambda: entity_financial_series(db_session, []))
    assert result == {} and selects == []

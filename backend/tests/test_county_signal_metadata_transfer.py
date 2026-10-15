"""A county signal must transfer shared source metadata once per statement."""
import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql

from models import Audit, SourceDocument
from services.county_financial_health import county_audit_signals, select_audit_signal
from test_county_evidence_selection import evidence, finding


def capture_signal_query(db, ids):
    queries = []

    def capture(state):
        if state.is_select and any(
            column.get("entity") is Audit
            for column in state.statement.column_descriptions
        ):
            queries.append(state.statement)

    event.listen(db, "do_orm_execute", capture)
    try:
        result = county_audit_signals(db, ids, display_grade=lambda row: True)
    finally:
        event.remove(db, "do_orm_execute", capture)
    assert len(queries) == 1
    return result, queries[0]


def full_metadata_control(statement):
    return statement.with_only_columns(*[
        SourceDocument.meta if column["name"] == "meta" else column["expr"]
        for column in statement.column_descriptions
    ], maintain_column_froms=True)


def test_shared_metadata_is_not_resent_for_every_finding(db_session, evidence, record_property):
    counties, periods, doc = evidence
    doc.meta = {"unused_context": "x" * 65536}
    for county in counties:
        for _ in range(12):
            finding(db_session, county, periods[2026], doc)
    ids = [county.id for county in counties]
    result, statement = capture_signal_query(db_session, ids)
    rows = db_session.execute(statement).all()
    control = db_session.execute(full_metadata_control(statement)).all()
    assert len(rows) == len(control) == 24
    assert sum(row.meta is not None for row in rows) == 1, "Shared metadata transferred once per finding"
    selected = sum(len(str(row.meta).encode()) for row in rows if row.meta is not None)
    old = sum(len(str(row.meta).encode()) for row in control if row.meta is not None)
    assert selected * 20 < old
    record_property("shared_metadata_selected_bytes", selected)
    record_property("full_metadata_selected_bytes", old)
    for county in counties:
        expected = select_audit_signal(
            [row for row in control if row.entity_id == county.id], county.canonical_name
        )
        assert result[county.id] == expected
    assert "row_number() OVER" in str(statement.compile(dialect=postgresql.dialect()))


@pytest.mark.parametrize("meta", [None, False, 0, "invalid", [], {},
    {"fiscal_year": "FY2023/24"}, {"extraction_stats": {"fiscal_year": "FY2023/24"}},
    {"auditee": "County Assembly of Mombasa"}])
def test_metadata_shape_and_conflict_refusals_are_preserved(db_session, evidence, meta):
    counties, periods, doc = evidence
    doc.meta = meta
    for county in counties:
        # The metadata carrier must be chosen within the selected row cohort.
        hidden = finding(db_session, county, periods[2026], doc)
        hidden.publishable = False
        for _ in range(3):
            finding(db_session, county, periods[2026], doc)
    db_session.flush()
    result, statement = capture_signal_query(db_session, [c.id for c in counties])
    control = db_session.execute(full_metadata_control(statement)).all()
    for county in counties:
        expected = select_audit_signal(
            [row for row in control if row.entity_id == county.id], county.canonical_name
        )
        assert result[county.id] == expected

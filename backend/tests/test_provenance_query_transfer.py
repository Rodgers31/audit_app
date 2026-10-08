"""Source vintage keeps its meaning without transferring unrelated evidence."""
from datetime import datetime

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql

from models import DocumentType, SourceDocument
from provenance import _naive, doc_vintage, resolve_data_vintage


@pytest.mark.parametrize(
    "metadata",
    [
        {"publication_date": "2026-09"},
        {"publication_date": "2026-09-03T12:00:00+03:00"},
        {"publication_date": {"invalid": "date"}},
        {"publication_date": None},
        ["not", "an", "object"],
    ],
)
def test_vintage_projection_matches_complete_documents(
    db_session, seed_country, metadata
):
    retained = metadata.copy() if isinstance(metadata, dict) else metadata
    if isinstance(retained, dict):
        retained["unrelated_evidence"] = "x" * 65536
    document = SourceDocument(
        country_id=seed_country.id,
        publisher="Controller of Budget",
        title="Retained evidence",
        url="https://cob.go.ke/report.pdf",
        file_path="x" * 65536,
        fetch_date=datetime(2026, 9, 2),
        doc_type=DocumentType.REPORT,
        meta=retained,
    )
    second = SourceDocument(
        country_id=seed_country.id,
        publisher="Controller of Budget",
        title="Earlier report",
        fetch_date=datetime(2026, 8, 1),
        doc_type=DocumentType.REPORT,
        meta={"publication_date": "2024"},
    )
    db_session.add_all([document, second])
    db_session.flush()
    ids = [document.id, second.id, -1, None]
    # Independent previous behavior: publication date before retrieval date,
    # then max by the same aware/naive comparison rule.
    expected = max([doc_vintage(document), doc_vintage(second)], key=_naive)

    selected = []
    connection = db_session.connection()

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selected.append((statement, parameters, context.compiled.statement))

    event.listen(connection, "after_cursor_execute", capture)
    try:
        actual = resolve_data_vintage(db_session, ids)
    finally:
        event.remove(connection, "after_cursor_execute", capture)
    assert actual == expected
    assert len(selected) == 1
    statement, parameters, clause = selected[0]
    values = connection.exec_driver_sql(statement, parameters).fetchall()
    assert len(values) == 2
    assert all(len(row) == 2 for row in values)
    assert sum(
        len(str(value).encode("utf-8"))
        for row in values for value in row if value is not None
    ) < 512
    compiled = str(clause.compile(dialect=postgresql.dialect()))
    assert "source_documents.file_path" not in compiled
    assert "source_documents.title" not in compiled
    assert document.meta == retained


def test_vintage_projection_missing_sources_stays_unknown(db_session):
    assert resolve_data_vintage(db_session, [-1]) is None

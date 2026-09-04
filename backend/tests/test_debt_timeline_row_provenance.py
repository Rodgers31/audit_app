"""Each debt-timeline year must trace to the document that actually contains it.

The series spans two different CBK publications — the /public-debt/ table for
2013-2021 and the Statistical Bulletin Table 4.1.3 for 2022-2025 — and the
fixture declares that per row. The parser had no ``source`` field and the writer
assigned one payload-level SourceDocument to every year, so half the series
cited a document that does not contain it and a reader could not follow any
given year back to its own table.
"""

from __future__ import annotations

from seeding.domains.debt_timeline.parser import parse_debt_timeline_payload
from seeding.domains.debt_timeline.writer import write_debt_timeline_records

PAYLOAD = {
    "metadata": {"source": "Generic payload-level title", "units": "billions_kes"},
    "timeline": [
        {
            "year": 2013, "external": 922.4, "domestic": 1189.2, "total": 2111.6,
            "gdp": 7381, "gdp_ratio": 28.6,
            "source": "CBK public debt table, December 2013",
        },
        {
            "year": 2025, "external": 5462.0, "domestic": 6837.5, "total": 12299.5,
            "gdp": 18382, "gdp_ratio": 66.9,
            "source": "CBK Statistical Bulletin Dec 2025, Table 4.1.3 (PDF p.56)",
        },
    ],
}


def test_the_parser_carries_each_row_source():
    records = parse_debt_timeline_payload(PAYLOAD)
    assert [r.source for r in records] == [
        "CBK public debt table, December 2013",
        "CBK Statistical Bulletin Dec 2025, Table 4.1.3 (PDF p.56)",
    ]


def test_two_series_persist_as_two_source_documents(db_session, seed_country):
    from models import DebtTimeline, SourceDocument

    records = parse_debt_timeline_payload(PAYLOAD)
    write_debt_timeline_records(db_session, records, PAYLOAD["metadata"])
    db_session.commit()

    rows = {r.year: r for r in db_session.query(DebtTimeline).all()}
    assert set(rows) == {2013, 2025}

    doc_2013 = db_session.query(SourceDocument).get(rows[2013].source_document_id)
    doc_2025 = db_session.query(SourceDocument).get(rows[2025].source_document_id)

    assert doc_2013.id != doc_2025.id, (
        "both years were written against a single document, so neither traces "
        "to the table that actually contains it"
    )
    assert "public debt table" in doc_2013.title
    assert "Statistical Bulletin" in doc_2025.title


def test_a_row_without_its_own_source_falls_back_to_the_payload_document(
    db_session, seed_country
):
    """Positive control: the fallback must still work."""
    from models import DebtTimeline, SourceDocument

    payload = {
        "metadata": {"source": "Generic payload-level title"},
        "timeline": [
            {"year": 2019, "external": 3.0, "domestic": 3.0, "total": 6.0,
             "gdp": 11.0, "gdp_ratio": 54.5},
        ],
    }
    records = parse_debt_timeline_payload(payload)
    assert records[0].source is None

    write_debt_timeline_records(db_session, records, payload["metadata"])
    db_session.commit()

    row = db_session.query(DebtTimeline).filter(DebtTimeline.year == 2019).one()
    doc = db_session.query(SourceDocument).get(row.source_document_id)
    assert doc.title == "Generic payload-level title"

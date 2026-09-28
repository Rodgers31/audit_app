"""Public audit reads must not transfer retained extraction diagnostics per row."""

from contextlib import contextmanager
from datetime import date, datetime, timezone
import json

from sqlalchemy import event

from models import (
    Audit,
    BudgetLine,
    DocumentType,
    Entity,
    EntityType,
    Extraction,
    Severity,
    SourceDocument,
)


DIAGNOSTIC = "retained-reconciliation-proposal-" + "X" * 220_000
URL = "https://oagkenya.go.ke/reports/counties.pdf"


@contextmanager
def selected_payload(db, sql_marker):
    """Measure values selected by the DB, including values the API discards.

    Re-execute matching SELECTs on the same isolated SQLite connection. A raw
    DBAPI cursor avoids recursively instrumenting the measurement query.
    """
    measurements = []
    engine = db.get_bind().engine
    markers = (sql_marker,) if isinstance(sql_marker, str) else sql_marker

    def capture(conn, cursor, statement, parameters, context, executemany):
        if not any(marker in statement.lower() for marker in markers) or not statement.lstrip().lower().startswith("select"):
            return
        probe = conn.connection.driver_connection.cursor()
        try:
            probe.execute(statement, parameters)
            rows = probe.fetchall()
            measurements.append(
                {
                    "columns": [column[0] for column in probe.description],
                    "bytes": sum(
                        len(str(value).encode("utf-8"))
                        for row in rows
                        for value in row
                        if value is not None
                    ),
                    "rows": len(rows),
                }
            )
        finally:
            probe.close()

    event.listen(engine, "before_cursor_execute", capture)
    try:
        yield measurements
    finally:
        event.remove(engine, "before_cursor_execute", capture)


def _doc(db, country, *, url=URL, meta=None):
    doc = SourceDocument(
        country_id=country.id,
        publisher="Office of the Auditor-General",
        title="County audit volume",
        url=url,
        fetch_date=datetime(2025, 12, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        meta=meta,
    )
    db.add(doc)
    db.flush()
    return doc


def _finding(db, entity, period, doc, *, payload=None, text="Finding body", amount=None):
    extraction = None
    if payload is not None:
        extraction = Extraction(
            source_document_id=doc.id,
            extractor="fixture",
            page_number=11,
            extracted_json=payload,
            confidence=0.8,
        )
        db.add(extraction)
        db.flush()
    audit = Audit(
        entity_id=entity.id,
        period_id=period.id,
        source_document_id=doc.id,
        extraction_id=extraction.id if extraction else None,
        finding_text=text,
        severity=Severity.WARNING,
        audit_year=2024,
        page_ref="p.11",
        amount=amount,
        external_reference="OAG-INTERNAL-11",
    )
    db.add(audit)
    db.flush()
    return audit


def test_findings_preserve_identity_links_and_pages_without_repeated_diagnostics(
    client, db_session, seed_country, seed_entity, seed_fiscal_period
):
    national = Entity(
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Government",
        slug="national-query-payload",
    )
    db_session.add(national)
    db_session.flush()
    large = _doc(
        db_session,
        seed_country,
        meta={
            "extraction_stats": {"volume_kind": "assemblies"},
            "last_extraction_attempt": {"proposal": DIAGNOSTIC},
        },
    )
    other = _doc(db_session, seed_country, meta=["malformed document metadata"])
    withheld_doc = _doc(db_session, seed_country, url=None)
    assembly = _finding(db_session, seed_entity, seed_fiscal_period, large, payload={})
    conflict = _finding(
        db_session,
        seed_entity,
        seed_fiscal_period,
        large,
        payload={"volume_kind": "executives"},
        amount=0,
    )
    nation = _finding(
        db_session,
        national,
        seed_fiscal_period,
        other,
        payload={"entity_name": "National Treasury", "auditee": "National Treasury"},
    )
    missing = _finding(db_session, seed_entity, seed_fiscal_period, other)
    _finding(db_session, seed_entity, seed_fiscal_period, withheld_doc)
    db_session.commit()

    with selected_payload(db_session, "source_documents") as selected:
        first = client.get("/api/v1/audit/findings?limit=2&page=1")
        second = client.get("/api/v1/audit/findings?limit=2&page=2")
    assert first.status_code == second.status_code == 200
    one, two = first.json(), second.json()
    assert (one["total"], two["total"], one["page"], two["page"]) == (4, 4, 1, 2)
    assert [row["id"] for row in one["items"] + two["items"]] == [
        missing.id, nation.id, conflict.id, assembly.id
    ]
    labels = {row["id"]: row["audited_entity_name"] for row in one["items"] + two["items"]}
    assert labels == {
        missing.id: None,
        nation.id: "National Treasury",
        conflict.id: None,
        assembly.id: "County Assembly of Nairobi",
    }
    assert all(row["source_document_url"] == URL + "#page=11" for row in two["items"])
    assert next(row for row in two["items"] if row["id"] == conflict.id)["amount"] == 0.0
    page_reads = [read for read in selected if read["rows"] == 2]
    assert len(page_reads) >= 2, selected
    assert sum(read["bytes"] for read in selected) < 10_000, selected


def test_unaccounted_cases_keep_citations_without_repeated_diagnostics(
    db_session, seed_country, seed_entity, seed_fiscal_period
):
    from services.audit_derived import derive_unaccounted_cases

    doc = _doc(
        db_session,
        seed_country,
        meta={
            "extraction_stats": {"volume_kind": "assemblies"},
            "last_extraction_attempt": {"proposal": DIAGNOSTIC},
        },
    )
    for title in ("Unaccounted for cash", "Loss of Funds"):
        _finding(
            db_session,
            seed_entity,
            seed_fiscal_period,
            doc,
            payload={"title": title, "finding_text": title + " was investigated", "heading": "Basis"},
            text=title + " was investigated",
        )
    db_session.commit()
    with selected_payload(db_session, "source_documents") as selected:
        result = derive_unaccounted_cases(db_session)
    assert len(result["cases"]) == 2
    assert result["withheld"] == {}
    assert {case["entity"] for case in result["cases"]} == {"County Assembly of Nairobi"}
    assert all(case["source"]["page_url"] == URL + "#page=11" for case in result["cases"])
    case_reads = [read for read in selected if read["rows"] == 2]
    assert case_reads, selected
    assert sum(read["bytes"] for read in selected) < 10_000, selected


def test_findings_select_only_extraction_identity_fields(
    client, db_session, seed_country, seed_entity, seed_fiscal_period
):
    doc = _doc(db_session, seed_country, meta={"extraction_stats": {"volume_kind": "assemblies"}})
    for _ in range(2):
        _finding(
            db_session,
            seed_entity,
            seed_fiscal_period,
            doc,
            payload={"auditee": "County Assembly of Nairobi", "unused_diagnostic": DIAGNOSTIC},
        )
    db_session.commit()
    with selected_payload(db_session, ("source_documents", "from extractions")) as selected:
        response = client.get("/api/v1/audit/findings")
    assert response.status_code == 200
    assert [row["audited_entity_name"] for row in response.json()["items"]] == [
        "County Assembly of Nairobi", "County Assembly of Nairobi"
    ]
    assert sum(read["bytes"] for read in selected) < 10_000, selected


def test_unaccounted_cases_select_only_extraction_context_fields(
    db_session, seed_country, seed_entity, seed_fiscal_period
):
    from services.audit_derived import derive_unaccounted_cases

    doc = _doc(db_session, seed_country, meta={"extraction_stats": {"volume_kind": "assemblies"}})
    for title in ("Unaccounted for cash", "Loss of Funds"):
        _finding(
            db_session,
            seed_entity,
            seed_fiscal_period,
            doc,
            payload={
                "title": title,
                "finding_text": title + " was investigated",
                "heading": "Basis",
                "unused_diagnostic": DIAGNOSTIC,
            },
            text=title + " was investigated",
        )
    db_session.commit()
    with selected_payload(db_session, ("source_documents", "from extractions")) as selected:
        result = derive_unaccounted_cases(db_session)
    assert len(result["cases"]) == 2
    assert {case["entity"] for case in result["cases"]} == {"County Assembly of Nairobi"}
    assert sum(read["bytes"] for read in selected) < 10_000, selected


def test_string_encoded_extraction_keeps_identity_and_title(
    client, db_session, seed_country, seed_entity, seed_fiscal_period
):
    from services.audit_derived import derive_unaccounted_cases

    doc = _doc(db_session, seed_country, meta={"extraction_stats": {"volume_kind": "assemblies"}})
    _finding(
        db_session,
        seed_entity,
        seed_fiscal_period,
        doc,
        payload=json.dumps(
            {
                "auditee": "County Assembly of Nairobi",
                "title": "Unaccounted for cash",
                "finding_text": "Unaccounted for cash was investigated",
            }
        ),
        text="Unaccounted for cash was investigated",
    )
    db_session.commit()
    finding = client.get("/api/v1/audit/findings").json()["items"][0]
    cases = derive_unaccounted_cases(db_session)["cases"]
    assert finding["audited_entity_name"] == "County Assembly of Nairobi"
    assert len(cases) == 1
    assert cases[0]["entity"] == finding["audited_entity_name"]
    assert cases[0]["source"]["page_url"] == finding["source_document_url"]


def test_bodyless_case_scans_only_table_row_fields(
    db_session, seed_country, seed_entity, seed_fiscal_period
):
    from services.audit_derived import derive_unaccounted_cases

    doc = _doc(db_session, seed_country, meta={"extraction_stats": {"volume_kind": "assemblies"}})
    # The bodyless finding makes table-row detection scan all extractions in
    # this report, including unrelated diagnostic-rich records.
    for paragraph in range(1, 5):
        db_session.add(
            Extraction(
                source_document_id=doc.id,
                extractor="fixture",
                page_number=10,
                extracted_json={
                    "pdf_page": 10,
                    "paragraph_no": paragraph,
                    "title": "Other issue",
                    "finding_text": "Other issue has body",
                    "last_extraction_attempt": DIAGNOSTIC,
                },
            )
        )
    _finding(
        db_session,
        seed_entity,
        seed_fiscal_period,
        doc,
        payload={
            "pdf_page": 11,
            "paragraph_no": 52,
            "title": "Unaccounted for cash",
            "finding_text": "Unaccounted for cash",
        },
        text="Unaccounted for cash",
    )
    db_session.commit()

    with selected_payload(db_session, "from extractions") as selected:
        result = derive_unaccounted_cases(db_session)
    assert len(result["cases"]) == 1
    assert result["excluded_table_rows"] == 0
    assert sum(read["bytes"] for read in selected) < 10_000, selected


def test_table_row_detection_preserves_string_encoded_extractions(
    db_session, seed_country
):
    from services.audit_derived import table_row_extraction_ids

    doc = _doc(db_session, seed_country)
    preceding = Extraction(
        source_document_id=doc.id,
        extractor="fixture",
        page_number=10,
        extracted_json=json.dumps(
            {"paragraph_no": 52, "title": "Earlier", "finding_text": "Earlier with body"}
        ),
    )
    table_row = Extraction(
        source_document_id=doc.id,
        extractor="fixture",
        page_number=11,
        extracted_json=json.dumps(
            {"paragraph_no": 2, "title": "Unaccounted cash", "finding_text": "Unaccounted cash"}
        ),
    )
    db_session.add_all([preceding, table_row])
    db_session.commit()
    assert table_row_extraction_ids(db_session, [doc.id]) == {table_row.id}


def test_publication_date_selects_only_date_from_accepted_document(
    db_session, seed_country, seed_entity, seed_fiscal_period
):
    from routers.data_freshness import _source_publication_date

    doc = _doc(
        db_session,
        seed_country,
        meta={
            "publication_date": "2025-03-12",
            "last_extraction_attempt": {"proposal": DIAGNOSTIC},
        },
    )
    db_session.add(
        BudgetLine(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            category="Total",
            allocated_amount=0,
            currency="KES",
            source_document_id=doc.id,
            publishable=True,
        )
    )
    db_session.commit()
    with selected_payload(db_session, "from source_documents") as selected:
        published = _source_publication_date(db_session, "Auditor%General", "budget")
    assert published == date(2025, 3, 12)
    date_reads = [read for read in selected if read["rows"] == 1]
    assert date_reads, selected
    assert date_reads[-1]["bytes"] < 1_000, date_reads[-1]

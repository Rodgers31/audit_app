"""Public-query SQL transfer guards using the existing owned SQLite fixture."""

from datetime import datetime, timedelta
import json

import pytest
from sqlalchemy import event

from models import Audit, BudgetLine, Entity, EntityType, Severity, SourceDocument


@pytest.fixture
def public_transfer_rows(db_session, seed_country, seed_fiscal_period, seed_source_doc):
    county = Entity(
        id=751, country_id=seed_country.id, type=EntityType.COUNTY,
        canonical_name="Baringo County", slug="baringo-transfer",
        meta={"unused_blob": "e" * 65536},
    )
    db_session.add(county)
    seed_source_doc.file_path = "p" * 65536
    seed_source_doc.meta = {"data_quality": "official", "unused_blob": "s" * 65536}
    db_session.flush()
    for category, allocated, spent, committed in [
        ("Total", 100, 50, None), ("Health", 80, 40, 70),
    ]:
        db_session.add(BudgetLine(
            entity_id=county.id, period_id=seed_fiscal_period.id,
            category=category, allocated_amount=allocated, actual_spent=spent,
            committed_amount=committed, currency="KES",
            source_document_id=seed_source_doc.id, page_ref="p. 42",
            notes="n" * 65536, provenance=[{"data_quality": "official"}],
        ))
    for index in range(12):
        db_session.add(Audit(
            entity_id=county.id, period_id=seed_fiscal_period.id,
            finding_text=f"Finding {index}: " + "f" * 4096,
            severity=Severity.WARNING, source_document_id=seed_source_doc.id,
            page_ref="p. 42", amount=None if index % 2 else 0,
            status="Open", provenance=[],
            recommended_action="a" * 65536,
            management_response="r" * 65536,
            created_at=datetime(2025, 12, 1) + timedelta(days=index),
        ))
    db_session.commit()
    return county.id


def capture_selected(db, operation):
    """Replay only captured SELECTs on the same fixture DBAPI connection."""
    connection = db.get_bind()
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    event.listen(connection, "before_cursor_execute", capture)
    try:
        result = operation()
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    selections = []
    cursor = connection.connection.driver_connection.cursor()
    try:
        for sql, parameters in statements:
            cursor.execute(sql, parameters)
            rows = cursor.fetchall()
            selections.append({
                "sql": sql,
                "columns": [column[0] for column in cursor.description],
                "rows": len(rows),
                "bytes": sum(
                    len(str(value).encode("utf-8"))
                    for row in rows for value in row if value is not None
                ),
            })
    finally:
        cursor.close()
    return result, selections


def transfer_receipt(operation, body, selections):
    print("PUBLIC_TRANSFER_RECEIPT " + json.dumps({
        "operation": operation, "body": body, "selections": selections,
        "selected_value_bytes": sum(s["bytes"] for s in selections),
    }, sort_keys=True))


@pytest.mark.parametrize("surface", ["county", "national", "batch"])
def test_money_flow_does_not_transfer_unused_budget_or_document_text(
    client, db_session, public_transfer_rows, surface,
):
    db_session.expunge_all()
    path = {
        "county": f"/api/v1/counties/{public_transfer_rows}/money-flow?year=2024/25",
        "national": "/api/v1/audit/money-flow/national?year=2024/25",
        "batch": "/api/v1/money-flow/all-counties?year=2024/25",
    }[surface]
    response, selections = capture_selected(db_session, lambda: client.get(path))
    assert response.status_code == 200, response.text
    body = response.json()
    transfer_receipt(f"money_flow:{surface}", body, selections)
    if surface == "batch":
        assert len(body) == 1
        body = body[0]
    assert body["stages"][0]["amount"] == 100
    assert body["stages"][1]["amount"] == 50
    if surface == "county":
        assert body["committed_amount"] == 70  # component cohort retained
    assert body["audit_amount_coverage"]["findings_with_amount"] == 6
    budget_selections = [
        s for s in selections if "budget_lines_category" in s["columns"]
    ]
    assert len(budget_selections) == 1
    assert budget_selections[0]["rows"] == 2  # no row-cohort shortcut
    assert "budget_lines_notes" not in budget_selections[0]["columns"]
    assert "budget_lines_source_hash" not in budget_selections[0]["columns"]
    assert all("source_documents_file_path" not in s["columns"] for s in selections)
    # County identity resolution retains its separate 64 KiB metadata; source
    # metadata remains complete because the existing evidence rule consumes it.
    assert sum(s["bytes"] for s in selections) < (150000 if surface == "county" else 100000)
    assert len(selections) <= 7  # bounded relationship batches, no deferred reads


@pytest.mark.parametrize("status", [None, "open"])
def test_county_findings_page_transfers_only_page_detail_rows(
    client, db_session, public_transfer_rows, status,
):
    db_session.expunge_all()
    path = f"/api/v1/counties/{public_transfer_rows}/audits/list?page=2&limit=2"
    if status:
        path += f"&status={status}"
    response, selections = capture_selected(db_session, lambda: client.get(path))
    assert response.status_code == 200, response.text
    body = response.json()
    transfer_receipt(f"county_page:{status}", body, selections)
    assert body["total"] == 12
    assert [item["description"].split(":", 1)[0] for item in body["items"]] == ["Finding 9", "Finding 8"]
    assert body["findings_reason"] is None
    detail_selections = [
        s for s in selections if "audits_finding_text" in s["columns"]
    ]
    assert sum(s["rows"] for s in detail_selections) == 2
    assert all("audits_management_response" not in s["columns"] for s in selections)
    assert all("audits_recommended_action" not in s["columns"] for s in selections)


def test_basic_county_detail_transfers_ten_short_issue_descriptions(
    client, db_session, public_transfer_rows,
):
    db_session.expunge_all()
    response, selections = capture_selected(
        db_session, lambda: client.get(f"/api/v1/counties/{public_transfer_rows}"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    transfer_receipt("county_basic_detail", body, selections)
    assert body["audit_findings_count"] == 12
    assert len(body["audit_issues"]) == 10
    assert all(len(item["description"]) == 200 for item in body["audit_issues"])
    # Other financial/evidence reads are outside this basic audit projection.
    audit_selections = [s for s in selections if any(c.startswith("audits_") for c in s["columns"])]
    assert all("audits_management_response" not in s["columns"] for s in audit_selections)
    assert all("audits_recommended_action" not in s["columns"] for s in audit_selections)
    assert all("audits_finding_text" not in s["columns"] for s in audit_selections)


@pytest.mark.parametrize("stored,provenance,expected", [
    ("Open", {"status": "closed"}, "Open"),
    ("", {"status": "Straße"}, "Straße"),
    (None, [{"status": "  Open  "}, {"status": "closed"}], "  Open  "),
    (None, [{"status": 7}, {"status": "open"}], None),
    (None, "garbage", None),
    (None, [], None),
    (None, {"status": "   "}, None),
    ("   ", {"status": "open"}, "   "),
])
def test_county_status_projection_preserves_full_item_fallback(
    stored, provenance, expected,
):
    from types import SimpleNamespace
    import main

    audit = SimpleNamespace(
        id=1, status=stored, provenance=provenance, source_document=None,
        page_ref=None, amount=None, finding_text="Finding", severity=None, period=None,
    )
    assert main._county_audit_item(audit, "Baringo")["status"] == expected


@pytest.mark.parametrize("stored,provenance,requested,matches", [
    ("Open", {"status": "closed"}, "open", True),
    ("", {"status": "Straße"}, "strasse", True),
    (None, [{"status": "  Open  "}, {"status": "closed"}], "open", False),
    (None, [{"status": "  Open  "}, {"status": "closed"}], "  open  ", True),
    (None, [{"status": 7}, {"status": "open"}], "open", False),
    (None, "garbage", "open", False),
    (None, {"status": "   "}, "   ", False),
    ("   ", {"status": "open"}, "   ", True),
])
def test_county_page_filters_exact_status_before_hydrating_details(
    client, db_session, public_transfer_rows, stored, provenance, requested, matches,
):
    rows = db_session.query(Audit).order_by(Audit.id).all()
    target = rows[-1]
    for row in rows:
        row.status = "Closed"
    target.status, target.provenance = stored, provenance
    target_id = target.id
    db_session.commit()
    db_session.expunge_all()
    response, selections = capture_selected(db_session, lambda: client.get(
        f"/api/v1/counties/{public_transfer_rows}/audits/list",
        params={"status": requested, "limit": 1},
    ))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == int(matches)
    assert [item["id"] for item in body["items"]] == ([target_id] if matches else [])
    assert sum(s["rows"] for s in selections if "audits_finding_text" in s["columns"]) == int(matches)


@pytest.mark.parametrize("status", [None, "open"])
def test_county_page_past_end_keeps_total_and_reason(client, public_transfer_rows, status):
    params = {"page": 99, "limit": 1}
    if status:
        params["status"] = status
    response = client.get(f"/api/v1/counties/{public_transfer_rows}/audits/list", params=params)
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []
    assert response.json()["total"] == 12
    assert response.json()["findings_reason"] is None


def test_county_page_withheld_count_precedes_status_facet(
    client, db_session, public_transfer_rows,
):
    withheld = db_session.query(Audit).order_by(Audit.id.desc()).first()
    withheld.page_ref = None
    withheld.status = "Closed"
    db_session.commit()
    response = client.get(
        f"/api/v1/counties/{public_transfer_rows}/audits/list?status=open&limit=1",
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 11
    assert len(body["items"]) == 1
    assert body["withheld_findings"] == 1
    other_status = client.get(f"/api/v1/counties/{public_transfer_rows}/audits/list?status=missing")
    assert other_status.status_code == 200, other_status.text
    assert other_status.json()["total"] == 0
    assert other_status.json()["withheld_findings"] == 1
    assert other_status.json()["findings_reason"] == "awaiting_sourced_data"


def test_basic_county_detail_applies_display_grade_before_ten_issue_selection(
    client, db_session, public_transfer_rows,
):
    newest = db_session.query(Audit).order_by(Audit.created_at.desc()).first()
    newest.provenance = {"data_quality": "modelled"}
    db_session.commit()
    response = client.get(f"/api/v1/counties/{public_transfer_rows}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["audit_findings_count"] == 11
    assert len(body["audit_issues"]) == 10
    assert body["audit_issues"][0]["description"].startswith("Finding 10:")
    assert body["audit_issues"][-1]["description"].startswith("Finding 1:")


def test_county_page_unknown_identity_never_reads_findings(client, db_session):
    response, selections = capture_selected(db_session, lambda: client.get(
        "/api/v1/counties/not-a-county/audits/list?limit=1",
    ))
    assert response.status_code == 404
    assert all("audits_finding_text" not in s["columns"] for s in selections)


def test_county_page_ties_keep_descending_id_order(client, db_session, public_transfer_rows):
    rows = db_session.query(Audit).order_by(Audit.id).all()
    for row in rows:
        row.created_at = datetime(2025, 12, 1)
    expected_ids = [row.id for row in rows[-4:-2]][::-1]
    db_session.commit()
    response = client.get(f"/api/v1/counties/{public_transfer_rows}/audits/list?page=2&limit=2")
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == expected_ids


def test_national_money_flow_batches_many_distinct_source_relationships(
    client, db_session, seed_country, seed_fiscal_period, seed_source_doc,
):
    for index in range(12):
        county = Entity(
            country_id=seed_country.id, type=EntityType.COUNTY,
            canonical_name=f"County {index}", slug=f"context-batch-{index}",
        )
        source = SourceDocument(
            country_id=seed_country.id, publisher=seed_source_doc.publisher,
            title=seed_source_doc.title, url=f"https://example.invalid/report-{index}.pdf",
            fetch_date=datetime(2025, 12, 1), doc_type=seed_source_doc.doc_type,
            meta={"data_quality": "official"}, file_path="x" * 65536,
        )
        db_session.add_all([county, source])
        db_session.flush()
        db_session.add(BudgetLine(
            entity_id=county.id, period_id=seed_fiscal_period.id,
            category="Total", allocated_amount=100, actual_spent=50,
            currency="KES", source_document_id=source.id,
            page_ref="p. 42", notes="x" * 65536,
        ))
    db_session.commit()
    db_session.expunge_all()
    response, selections = capture_selected(db_session, lambda: client.get(
        "/api/v1/audit/money-flow/national?year=2024/25",
    ))
    assert response.status_code == 200, response.text
    assert response.json()["county_count"] == 12
    assert response.json()["stages"][0]["amount"] == 1200
    assert response.json()["stages"][1]["amount"] == 600
    assert response.json()["source_document_url"] is None  # distinct accounts
    assert len(selections) <= 7
    assert sum(s["bytes"] for s in selections) < 10000

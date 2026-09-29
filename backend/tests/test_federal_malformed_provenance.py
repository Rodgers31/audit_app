"""Stored audit metadata shape cannot erase source-linked federal findings."""

from datetime import datetime, timezone

from sqlalchemy import event

from models import (
    Audit,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    Severity,
    SourceDocument,
)


def test_oversized_stored_numeric_string_is_invalid_without_crashing():
    from main import _federal_audit_metadata

    assert _federal_audit_metadata({"amount_involved": "9" * 1_000_001}) == (
        {},
        "invalid",
        None,
    )


def test_stored_amount_controls_display_when_legacy_metadata_disagrees(
    client, db_session, seed_country, seed_fiscal_period
):
    ministry = Entity(
        country_id=seed_country.id,
        type=EntityType.MINISTRY,
        canonical_name="Stored Amount Ministry",
        slug="stored-amount-ministry",
    )
    linked = SourceDocument(
        country_id=seed_country.id,
        publisher="Synthetic OAG",
        title="Linked report",
        url="https://example.invalid/linked.pdf#page=99",
        fetch_date=datetime(2025, 12, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    db_session.add_all([ministry, linked])
    db_session.flush()
    for label, stored_amount, metadata_amount, page in (
        ("stored zero", 0, "KES 123", "p. 7"),
        ("stored positive", 5.25, "KES 999", "p. 8"),
    ):
        db_session.add(
            Audit(
                entity_id=ministry.id,
                period_id=seed_fiscal_period.id,
                source_document_id=linked.id,
                finding_text=label,
                severity=Severity.WARNING,
                page_ref=page,
                provenance=[
                    {
                        "amount_involved": metadata_amount,
                        "source_url": "https://example.invalid/wrong.pdf",
                    }
                ],
                amount=stored_amount,
            )
        )
    db_session.commit()

    response = client.get("/api/v1/audits/federal")
    assert response.status_code == 200, response.text
    payload = response.json()
    rows = {row["finding"]: row for row in payload["findings"]}
    assert payload["total_amount_in_findings"] == 5.25
    assert payload["findings_with_amount"] == 2
    assert rows["stored zero"]["amount_numeric"] == 0
    assert rows["stored zero"]["amount_involved"] == "KES 0"
    assert rows["stored positive"]["amount_numeric"] == 5.25
    assert rows["stored positive"]["amount_involved"] == "KES 5.25"
    for row, page in ((rows["stored zero"], 7), (rows["stored positive"], 8)):
        assert row["provenance_metadata_status"] == "valid"
        assert row["source_url"] == "https://example.invalid/linked.pdf"
        assert (
            row["source_page_url"] == f"https://example.invalid/linked.pdf#page={page}"
        )


def test_federal_endpoint_handles_malformed_provenance_with_valid_rows(
    client,
    db_session,
    seed_country,
    seed_fiscal_period,
):
    ministry = Entity(
        country_id=seed_country.id,
        type=EntityType.MINISTRY,
        canonical_name="Synthetic Ministry",
        slug="synthetic-federal-metadata",
    )
    linked = SourceDocument(
        country_id=seed_country.id,
        publisher="Synthetic OAG",
        title="Linked report",
        url="https://example.invalid/linked.pdf#page=99",
        fetch_date=datetime(2025, 12, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    unlinked = SourceDocument(
        country_id=seed_country.id,
        publisher="Synthetic OAG",
        title="No URL",
        url=None,
        fetch_date=datetime(2025, 12, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    db_session.add_all([ministry, linked, unlinked])
    db_session.flush()

    cases = [
        (
            "valid list",
            [
                {
                    "title": "Real title",
                    "amount_involved": "KES 12",
                    "source_url": "https://example.invalid/wrong.pdf",
                }
            ],
            None,
            "valid",
            12,
        ),
        (
            "valid object",
            {"title": "Object title", "amount_involved": "KES 0"},
            None,
            "valid",
            0,
        ),
        ("null", None, None, "absent", None),
        ("empty list", [], None, "absent", None),
        ("list scalar", ["not an object"], None, "invalid", None),
        ("scalar string", "not an object", None, "invalid", None),
        ("scalar number", 7, None, "invalid", None),
        (
            "mixed list",
            ["bad", {"amount_involved": "KES 5", "date_raised": "2025-01-01"}],
            None,
            "invalid",
            None,
        ),
        (
            "invalid field",
            [{"amount_involved": {"amount": 20}, "date_raised": 2025}],
            None,
            "invalid",
            None,
        ),
        (
            "invalid second object",
            [{"amount_involved": "KES 5"}, {"date_raised": 2025}],
            None,
            "invalid",
            None,
        ),
        (
            "invalid second amount",
            [{"amount_involved": "KES 5"}, {"amount_involved": "KES 1,2,3"}],
            None,
            "invalid",
            None,
        ),
        (
            "invalid second date",
            [{"amount_involved": "KES 5"}, {"date_raised": "2025-99-99"}],
            None,
            "invalid",
            None,
        ),
        (
            "malformed grouping",
            [{"amount_involved": "KES 1,2,3"}],
            None,
            "invalid",
            None,
        ),
        ("nonfinite string", [{"amount_involved": "KES NaN"}], None, "invalid", None),
        ("oversized amount", [{"amount_involved": "9" * 308}], None, "invalid", None),
        (
            "underflowing amount",
            [{"amount_involved": "0." + "0" * 323 + "1"}],
            None,
            "invalid",
            None,
        ),
        ("impossible date", [{"date_raised": "2025-99-99"}], None, "invalid", None),
        ("valid date", [{"date_raised": "2025-01-01"}], None, "valid", None),
        ("stored zero", ["bad"], 0, "invalid", 0),
        ("stored amount", ["bad"], 8, "invalid", 8),
    ]
    for name, provenance, amount, _status, _number in cases:
        db_session.add(
            Audit(
                entity_id=ministry.id,
                period_id=seed_fiscal_period.id,
                source_document_id=linked.id,
                finding_text=name,
                severity=Severity.WARNING,
                page_ref="p. 7",
                provenance=provenance,
                amount=amount,
            )
        )
    db_session.add(
        Audit(
            entity_id=ministry.id,
            period_id=seed_fiscal_period.id,
            source_document_id=unlinked.id,
            finding_text="unsupported provenance URL",
            severity=Severity.WARNING,
            page_ref="p. 7",
            provenance=[{"source_url": "https://example.invalid/wrong.pdf"}],
        )
    )
    db_session.commit()

    statements = []

    def capture(_conn, _cursor, statement, _params, _ctx, _many):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement)

    engine = db_session.get_bind().engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get("/api/v1/audits/federal")
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    payload = response.json()
    rows = {row["finding"]: row for row in payload["findings"]}
    assert set(rows) == {case[0] for case in cases}
    assert payload["total_findings"] == len(cases)
    assert payload["withheld_findings"] == 1
    assert payload["total_amount_questioned"] is None
    assert payload["total_amount_in_findings"] == 20
    assert payload["findings_with_amount"] == 4
    for name, _provenance, _amount, status, number in cases:
        row = rows[name]
        assert row["provenance_metadata_status"] == status
        assert row["amount_numeric"] == number
        assert row["source_url"] == "https://example.invalid/linked.pdf"
        assert row["source_page"] == 7
        assert row["source_page_url"] == "https://example.invalid/linked.pdf#page=7"
        if status == "invalid":
            assert row["title"] is None
            assert row["date_raised"] == ""
    assert rows["valid list"]["title"] == "Real title"
    assert rows["valid object"]["title"] == "Object title"
    assert rows["stored zero"]["amount_involved"] == "KES 0"
    assert rows["null"]["amount_involved"] == ""
    assert len(statements) < 20
    finding_queries = [
        statement
        for statement in statements
        if "FROM audits JOIN entities" in statement
        and "audits.provenance" in statement.split("FROM audits", 1)[0]
        and "ORDER BY audits.severity DESC, audits.created_at DESC" in statement
    ]
    assert len(finding_queries) == 1
    selected = finding_queries[0].split("FROM audits", 1)[0]
    assert "audits.provenance" in selected
    assert "audits.management_response" not in selected
    assert "audits.external_reference" not in selected

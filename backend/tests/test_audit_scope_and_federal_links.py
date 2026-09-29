"""HTTP regressions for county attribution and federal finding citations."""

from datetime import datetime, timezone

from sqlalchemy import event

from models import (
    Audit,
    Country,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    FiscalPeriod,
    Severity,
    SourceDocument,
)


def _document(db, country_id, title, url):
    doc = SourceDocument(
        country_id=country_id,
        publisher="Synthetic OAG",
        title=title,
        url=url,
        fetch_date=datetime(2025, 12, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    db.add(doc)
    db.flush()
    return doc


def _finding(
    db,
    entity,
    period,
    doc,
    text,
    *,
    page="p. 7",
    provenance=None,
    severity=Severity.WARNING,
):
    finding = Audit(
        entity_id=entity.id,
        period_id=period.id,
        source_document_id=doc.id,
        finding_text=text,
        severity=severity,
        page_ref=page,
        provenance=provenance or [],
    )
    db.add(finding)
    db.flush()
    return finding.id


def test_county_list_never_uses_findings_from_another_institution(
    client, db_session, seed_country, seed_fiscal_period
):
    nairobi = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi County",
        slug="nairobi-scope",
    )
    kisumu = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Kisumu County",
        slug="kisumu-scope",
    )
    ministry = Entity(
        country_id=seed_country.id,
        type=EntityType.MINISTRY,
        canonical_name="National Treasury",
        slug="treasury-scope",
    )
    db_session.add_all([nairobi, kisumu, ministry])
    db_session.flush()
    doc = _document(
        db_session,
        seed_country.id,
        "Synthetic report",
        "https://example.invalid/audit.pdf",
    )
    warning_id = _finding(
        db_session,
        nairobi,
        seed_fiscal_period,
        doc,
        "Nairobi open warning",
        provenance=[{"status": "open"}],
    )
    critical_id = _finding(
        db_session,
        nairobi,
        seed_fiscal_period,
        doc,
        "Nairobi closed critical",
        provenance=[{"status": "closed"}],
        severity=Severity.CRITICAL,
    )
    own_ids = {warning_id, critical_id}
    kisumu_id = _finding(db_session, kisumu, seed_fiscal_period, doc, "Kisumu finding")
    ministry_id = _finding(
        db_session, ministry, seed_fiscal_period, doc, "National ministry finding"
    )
    db_session.commit()

    first = client.get("/api/v1/counties/001/audits/list?limit=1&page=1")
    second = client.get("/api/v1/counties/001/audits/list?limit=1&page=2")
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == second.json()["total"] == 2
    assert {first.json()["items"][0]["id"], second.json()["items"][0]["id"]} == own_ids
    assert {
        item["id"]
        for item in client.get(
            "/api/v1/counties/001/audits/list?severity=critical&status=closed&year=FY2024/25"
        ).json()["items"]
    } == {critical_id}
    assert (
        client.get("/api/v1/counties/001/audits/list?year=FY2023/24").json()["total"]
        == 0
    )
    assert {
        item["id"]
        for item in client.get("/api/v1/counties/042/audits/list").json()["items"]
    } == {kisumu_id}
    assert not own_ids.intersection({kisumu_id, ministry_id})

    # Known URL, no corresponding county entity: neither another county nor a
    # national ministry can become the requested county's result.
    absent = client.get("/api/v1/counties/003/audits/list")  # Kilifi has no entity
    assert absent.status_code == 200, absent.text
    assert absent.json() == {"total": 0, "page": 1, "limit": 20, "items": []}
    assert client.get("/api/v1/counties/999/audits/list").status_code == 404


def test_county_list_requires_county_entity_type(
    client, db_session, seed_country, seed_fiscal_period
):
    misleading = Entity(
        country_id=seed_country.id,
        type=EntityType.MINISTRY,
        canonical_name="Kisumu County",
        slug="misleading-ministry",
    )
    db_session.add(misleading)
    db_session.flush()
    doc = _document(
        db_session,
        seed_country.id,
        "Synthetic report",
        "https://example.invalid/audit.pdf",
    )
    _finding(db_session, misleading, seed_fiscal_period, doc, "Ministry finding")
    db_session.commit()
    response = client.get("/api/v1/counties/042/audits/list")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_county_list_does_not_borrow_a_foreign_same_named_county(
    client, db_session, seed_country, seed_fiscal_period
):
    tanzania = Country(
        iso_code="TZA",
        name="Tanzania",
        currency="TZS",
        timezone="Africa/Dar_es_Salaam",
        default_locale="sw_TZ",
    )
    db_session.add(tanzania)
    db_session.flush()
    foreign_period = FiscalPeriod(
        country_id=tanzania.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    foreign_county = Entity(
        country_id=tanzania.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi County",
        slug="nairobi-foreign",
    )
    db_session.add_all([foreign_period, foreign_county])
    db_session.flush()
    foreign_doc = _document(
        db_session, tanzania.id, "Foreign report", "https://example.invalid/tz.pdf"
    )
    foreign_id = _finding(
        db_session, foreign_county, foreign_period, foreign_doc, "Foreign finding"
    )
    db_session.commit()

    for county_id in ("001", "code:047"):
        response = client.get(f"/api/v1/counties/{county_id}/audits/list")
        assert response.status_code == 200, response.text
        assert response.json()["items"] == []
    for identifier in ("nairobi-foreign", str(foreign_county.id)):
        assert (
            client.get(f"/api/v1/counties/{identifier}/audits/list").status_code == 404
        )

    kenya_county = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi County",
        slug="nairobi-kenya",
    )
    db_session.add(kenya_county)
    db_session.flush()
    kenya_doc = _document(
        db_session, seed_country.id, "Kenya report", "https://example.invalid/ke.pdf"
    )
    kenya_id = _finding(
        db_session, kenya_county, seed_fiscal_period, kenya_doc, "Kenya finding"
    )
    db_session.commit()

    for county_id in ("001", "code:047", "nairobi-kenya", str(kenya_county.id)):
        response = client.get(f"/api/v1/counties/{county_id}/audits/list")
        assert response.status_code == 200, response.text
        assert {item["id"] for item in response.json()["items"]} == {kenya_id}
        assert foreign_id not in {item["id"] for item in response.json()["items"]}


def test_county_list_loads_source_documents_in_bounded_queries(
    client, db_session, seed_country, seed_fiscal_period
):
    county = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi County",
        slug="nairobi-many-sources",
    )
    db_session.add(county)
    db_session.flush()
    for number in range(12):
        doc = _document(
            db_session,
            seed_country.id,
            f"Synthetic report {number}",
            f"https://example.invalid/report-{number}.pdf",
        )
        _finding(db_session, county, seed_fiscal_period, doc, f"finding {number}")
    db_session.commit()

    statements = []

    def record_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement)

    engine = db_session.get_bind().engine
    event.listen(engine, "before_cursor_execute", record_sql)
    try:
        response = client.get("/api/v1/counties/001/audits/list?limit=20")
    finally:
        event.remove(engine, "before_cursor_execute", record_sql)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 12
    assert len(statements) < 8, "source documents and periods must be batch loaded"


def test_federal_links_use_the_linked_document_and_bounded_queries(
    client, db_session, seed_country, seed_fiscal_period
):
    engine = db_session.get_bind().engine

    ministry = Entity(
        country_id=seed_country.id,
        type=EntityType.MINISTRY,
        canonical_name="Synthetic Ministry",
        slug="synthetic-ministry",
    )
    db_session.add(ministry)
    db_session.flush()
    base = "https://example.invalid/federal.pdf?download=1#page=99&zoom=100"
    doc = _document(db_session, seed_country.id, "Federal report", base)
    absent_doc = _document(db_session, seed_country.id, "Unlinked report", None)
    for i in range(20):
        _finding(
            db_session,
            ministry,
            seed_fiscal_period,
            doc,
            f"document only {i}",
            page="p. 7",
        )
    _finding(
        db_session,
        ministry,
        seed_fiscal_period,
        doc,
        "conflicting link",
        provenance=[{"source_url": "https://example.org/wrong.pdf"}],
    )
    _finding(
        db_session, ministry, seed_fiscal_period, doc, "text locator", page="Annex VII"
    )
    _finding(
        db_session,
        ministry,
        seed_fiscal_period,
        doc,
        "malformed locator",
        page="p.38 garbage 73",
    )
    _finding(
        db_session,
        ministry,
        seed_fiscal_period,
        absent_doc,
        "provenance only is withheld",
        provenance=[{"source_url": base}],
    )
    _finding(
        db_session,
        ministry,
        seed_fiscal_period,
        absent_doc,
        "missing links are withheld",
    )
    db_session.commit()

    statements = []

    def record_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_sql)
    try:
        response = client.get("/api/v1/audits/federal")
    finally:
        event.remove(engine, "before_cursor_execute", record_sql)
    assert response.status_code == 200, response.text
    payload = response.json()
    by_text = {finding["finding"]: finding for finding in payload["findings"]}
    # The parallel citation-gate change may withhold the malformed locator.
    assert payload["total_findings"] in (22, 23)
    assert payload["withheld_findings"] in (2, 3)
    assert "provenance only is withheld" not in by_text
    assert "missing links are withheld" not in by_text
    assert len(statements) < 20, "the response must not query once per finding"
    for text in ("document only 0", "conflicting link"):
        assert by_text[text]["source_url"] == (
            "https://example.invalid/federal.pdf?download=1#zoom=100"
        )
        assert by_text[text]["source_page"] == 7
        assert by_text[text]["source_page_url"] == (
            "https://example.invalid/federal.pdf?download=1#zoom=100&page=7"
        )
    assert by_text["text locator"]["source_page"] == "Annex VII"
    assert (
        by_text["text locator"]["source_page_url"]
        == by_text["text locator"]["source_url"]
    )
    if "malformed locator" in by_text:
        assert by_text["malformed locator"]["source_page"] is None
        assert by_text["malformed locator"]["source_page_url"] is None

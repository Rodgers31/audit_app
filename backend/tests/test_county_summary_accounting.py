"""#238: the public county summary uses the same sourced account as entity pages."""
from datetime import datetime

import pytest
from sqlalchemy import event

from models import BudgetLine, Entity, EntityType, FigureBasis, FiscalPeriod, SourceDocument, DocumentType


@pytest.fixture
def county(db_session, seed_country, seed_source_doc):
    entity = Entity(
        country_id=seed_country.id,
        canonical_name="Mombasa County",
        slug="mombasa-county",
        type=EntityType.COUNTY,
    )
    db_session.add(entity)
    db_session.flush()
    periods = []
    for year in (2024, 2025):
        period = FiscalPeriod(
            country_id=seed_country.id,
            label=f"FY{year}/{str(year + 1)[2:]}",
            start_date=datetime(year, 7, 1),
            end_date=datetime(year + 1, 6, 30),
        )
        db_session.add(period)
        db_session.flush()
        periods.append(period)
    return entity, periods, seed_source_doc


def add_line(
    db, entity, period, source, category, allocated, spent,
    *, basis=None, quarantine_reason=None, provenance=None
):
    db.add(BudgetLine(
        entity_id=entity.id,
        period_id=period.id,
        source_document_id=source.id,
        category=category,
        allocated_amount=allocated,
        actual_spent=spent,
        currency="KES",
        page_ref="p.42",
        basis=basis,
        quarantine_reason=quarantine_reason,
        provenance=[] if provenance is None else provenance,
    ))
    db.flush()


def summary(client, identifier="047"):
    response = client.get(f"/api/v1/counties/{identifier}/summary")
    assert response.status_code == 200, response.text
    return response.json()


def test_latest_period_total_does_not_add_classifications_sectors_or_revenue(
    client, db_session, county
):
    entity, (older, latest), source = county
    add_line(db_session, entity, older, source, "Total", 80, 40)
    for category, allocated, spent in (
        ("Total", 100, 50),
        ("Recurrent", 60, 30),
        ("Development", 40, 20),
        ("Health", 10, 5),
        ("Own Source Revenue", 7, 3),
    ):
        add_line(db_session, entity, latest, source, category, allocated, spent)
    result = summary(client)
    assert (result["total_budget"], result["total_spent"]) == (100, 50)
    assert result["budget_accounting_basis"] == "reported_total"
    assert result["budget_fiscal_period"]["id"] == latest.id
    assert result["budget_sources"][0]["id"] == source.id
    assert summary(client, "mombasa-county")["total_budget"] == 100
    assert summary(client, f"code:001")["total_budget"] == 100


def test_complete_classification_without_total_is_additive(client, db_session, county):
    entity, (_, period), source = county
    add_line(db_session, entity, period, source, "Recurrent", 60, 30)
    add_line(db_session, entity, period, source, "Development", 40, 20)
    add_line(db_session, entity, period, source, "Health", 10, 5)
    result = summary(client)
    assert (result["total_budget"], result["total_spent"]) == (100, 50)
    assert result["budget_accounting_basis"] == "recurrent_plus_development"


def test_incomplete_classification_and_sector_only_are_absent(client, db_session, county):
    entity, (_, period), source = county
    add_line(db_session, entity, period, source, "Recurrent", 60, 30)
    add_line(db_session, entity, period, source, "Health", 10, 5)
    result = summary(client)
    assert result["total_budget"] is None
    assert result["total_spent"] is None
    assert result["budget_absent_reasons"]["total_allocation"] == "incomplete_classification"


def test_sourced_zero_and_unreported_spending_remain_distinct(client, db_session, county):
    entity, (_, period), source = county
    add_line(db_session, entity, period, source, "Total", 100, 0)
    assert summary(client)["total_spent"] == 0
    row = db_session.query(BudgetLine).one()
    row.actual_spent = None
    db_session.flush()
    result = summary(client, "mombasa-county")
    assert result["total_spent"] is None
    assert result["budget_absent_reasons"]["total_spent"] == "spending_not_reported"


def test_competing_sources_are_withheld(client, db_session, county, seed_country):
    entity, (_, period), source = county
    other = SourceDocument(
        country_id=seed_country.id,
        title="Other report",
        publisher="Controller of Budget",
        url="https://cob.go.ke/other.pdf",
        fetch_date=datetime(2026, 9, 29),
        doc_type=DocumentType.BUDGET,
    )
    db_session.add(other)
    db_session.flush()
    add_line(db_session, entity, period, source, "Recurrent", 60, 30)
    add_line(db_session, entity, period, other, "Development", 40, 20)
    result = summary(client)
    assert result["total_budget"] is None
    assert result["budget_absent_reasons"]["total_allocation"] == "multiple_sources"
    assert {s["id"] for s in result["budget_sources"]} == {source.id, other.id}


def test_annual_projection_does_not_replace_nine_months_report(client, db_session, county):
    entity, (_, annual), source = county
    nine_months = FiscalPeriod(
        country_id=annual.country_id,
        label="FY2025/26 9M",
        start_date=annual.start_date,
        end_date=datetime(2026, 3, 31),
    )
    db_session.add(nine_months)
    db_session.flush()
    add_line(db_session, entity, annual, source, "Health", 999, 888)
    add_line(db_session, entity, nine_months, source, "Total", 100, 50)
    result = summary(client)
    assert result["budget_fiscal_period"]["id"] == nine_months.id
    assert (result["total_budget"], result["total_spent"]) == (100, 50)


def test_full_year_report_wins_equal_start_date_over_nine_months(
    client, db_session, seed_country, seed_source_doc
):
    entity = Entity(
        country_id=seed_country.id,
        canonical_name="Mombasa County",
        slug="mombasa-county",
        type=EntityType.COUNTY,
    )
    db_session.add(entity)
    db_session.flush()
    nine_months = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2025/26 9M",
        start_date=datetime(2025, 7, 1),
        end_date=datetime(2026, 3, 31),
    )
    db_session.add(nine_months)
    db_session.flush()
    annual = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2025/26",
        start_date=nine_months.start_date,
        end_date=datetime(2026, 6, 30),
    )
    db_session.add(annual)
    db_session.flush()
    # Insert the 9M classification first to reproduce the planner's tie.
    add_line(db_session, entity, nine_months, seed_source_doc, "Total", 100, 50)
    add_line(db_session, entity, annual, seed_source_doc, "Total", 200, 120)
    result = summary(client)
    assert result["budget_fiscal_period"]["id"] == annual.id
    assert (result["total_budget"], result["total_spent"]) == (200, 120)


def test_modelled_annual_total_does_not_mask_reported_nine_months(
    client, db_session, seed_country, seed_source_doc
):
    entity = Entity(
        country_id=seed_country.id,
        canonical_name="Mombasa County",
        slug="mombasa-county",
        type=EntityType.COUNTY,
    )
    db_session.add(entity)
    db_session.flush()
    nine_months = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2025/26 9M",
        start_date=datetime(2025, 7, 1),
        end_date=datetime(2026, 3, 31),
    )
    annual = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2025/26",
        start_date=datetime(2025, 7, 1),
        end_date=datetime(2026, 6, 30),
    )
    db_session.add_all([nine_months, annual])
    db_session.flush()
    add_line(db_session, entity, nine_months, seed_source_doc, "Total", 100, 50)
    add_line(
        db_session, entity, annual, seed_source_doc, "Total", 200, 120,
        basis=FigureBasis.PROJECTED,
    )
    result = summary(client)
    assert result["budget_fiscal_period"]["id"] == nine_months.id
    assert (result["total_budget"], result["total_spent"]) == (100, 50)


def test_classification_whitespace_is_recognized_by_period_selector(
    client, db_session, county
):
    entity, (reported, projection), source = county
    add_line(db_session, entity, reported, source, " Total ", 100, 50)
    add_line(db_session, entity, projection, source, "Health", 20, 10)
    result = summary(client)
    assert result["budget_fiscal_period"]["id"] == reported.id
    assert result["total_budget"] == 100


def test_latest_period_probe_bounds_classification_row_payload(db_session, county):
    from main import _latest_county_actuals_period_ids

    entity, (_, latest), source = county
    source.meta = {"publisher_payload": "x" * 8192}
    for spaces in range(1, 66):
        add_line(db_session, entity, latest, source, "Total" + " " * spaces, 100, 50)
    db_session.flush()

    probes = []
    source_probes = []

    def measure(conn, cursor, statement, parameters, context, executemany):
        if not statement.lstrip().lower().startswith("select"):
            return
        is_line_query = "budget_lines.provenance" in statement
        is_source_query = "source_documents" in statement
        if not (is_line_query or is_source_query):
            return
        probe = conn.connection.driver_connection.cursor()
        try:
            probe.execute(statement, parameters)
            rows = probe.fetchall()
            measurement = {
                "columns": {column[0] for column in probe.description},
                "rows": len(rows),
                "bytes": sum(
                    len(str(value).encode("utf-8"))
                    for row in rows
                    for value in row
                    if value is not None
                ),
            }
            if is_line_query:
                probes.append(measurement)
            if is_source_query:
                source_probes.append(measurement)
        finally:
            probe.close()

    event.listen(db_session.bind, "before_cursor_execute", measure)
    try:
        assert _latest_county_actuals_period_ids(db_session) == [latest.id]
    finally:
        event.remove(db_session.bind, "before_cursor_execute", measure)

    assert probes, "The classification evidence query must be measured"
    assert max(probe["rows"] for probe in probes) <= 32, probes
    assert sum(probe["bytes"] for probe in probes) < 100_000, probes
    assert all(
        not any(
            column.endswith(("notes", "allocated_amount", "actual_spent", "url"))
            for column in probe["columns"]
        )
        for probe in probes
    ), probes
    assert source_probes, "Source metadata must be checked"
    assert sum(probe["rows"] for probe in source_probes) == 1, source_probes
    assert all(
        not any(column.endswith(("title", "url", "file_path")) for column in probe["columns"])
        for probe in source_probes
    ), source_probes


def test_latest_period_probe_reads_beyond_first_page(db_session, county):
    from main import _latest_county_actuals_period_ids

    entity, (older, latest), source = county
    add_line(db_session, entity, older, source, "Total", 80, 40)
    for spaces in range(1, 34):
        add_line(
            db_session, entity, latest, source, "Total" + " " * spaces,
            100, 50, provenance={"data_quality": "synthetic"},
        )
    add_line(db_session, entity, latest, source, " Recurrent ", 60, 30)

    assert _latest_county_actuals_period_ids(db_session) == [latest.id]


def test_latest_period_probe_keeps_source_metadata_and_actual_fallback(
    db_session, county, seed_country
):
    from main import _latest_county_actuals_period_ids

    entity, (older, latest), source = county
    add_line(db_session, entity, older, source, "Total", 80, 40)
    synthetic_source = SourceDocument(
        country_id=seed_country.id,
        title="Synthetic source",
        publisher="Test publisher",
        url="https://example.test/synthetic.pdf",
        fetch_date=datetime(2026, 9, 29),
        doc_type=DocumentType.BUDGET,
        meta={"data_quality": "synthetic"},
    )
    db_session.add(synthetic_source)
    db_session.flush()
    for spaces in range(1, 35):
        add_line(db_session, entity, latest, synthetic_source, "Total" + " " * spaces, 100, 50)
    assert _latest_county_actuals_period_ids(db_session) == [older.id]

    # Without any eligible classification, the historical positive-spend
    # fallback still chooses the newest period, even if its rows are synthetic.
    db_session.query(BudgetLine).filter(BudgetLine.period_id == older.id).delete()
    db_session.flush()
    assert _latest_county_actuals_period_ids(db_session) == [latest.id]


def test_latest_period_probe_fetches_shared_source_metadata_once(
    db_session, county, seed_country
):
    from main import _latest_county_actuals_period_ids

    entity, (older, latest), reported_source = county
    add_line(db_session, entity, older, reported_source, "Total", 80, 40)
    synthetic_source = SourceDocument(
        country_id=seed_country.id,
        title="Large synthetic metadata",
        publisher="Test publisher",
        url="https://example.test/synthetic.pdf",
        fetch_date=datetime(2026, 9, 29),
        doc_type=DocumentType.BUDGET,
        meta={"data_quality": "synthetic", "payload": "x" * 131_072},
    )
    db_session.add(synthetic_source)
    db_session.flush()
    for spaces in range(1, 97):
        add_line(db_session, entity, latest, synthetic_source, "Total" + " " * spaces, 100, 50)

    source_ids_fetched = []

    def measure(conn, cursor, statement, parameters, context, executemany):
        if not (
            statement.lstrip().lower().startswith("select")
            and "source_documents" in statement
            and "metadata" in statement
        ):
            return
        probe = conn.connection.driver_connection.cursor()
        try:
            probe.execute(statement, parameters)
            source_ids_fetched.extend(row[0] for row in probe.fetchall())
        finally:
            probe.close()

    event.listen(db_session.bind, "before_cursor_execute", measure)
    try:
        assert _latest_county_actuals_period_ids(db_session) == [older.id]
    finally:
        event.remove(db_session.bind, "before_cursor_execute", measure)

    assert source_ids_fetched.count(synthetic_source.id) == 1, source_ids_fetched


def test_latest_period_probe_skips_explicitly_unreported_rows_in_sql(db_session, county):
    from main import _latest_county_actuals_period_ids

    entity, (older, latest), source = county
    add_line(
        db_session, entity, older, source, "Total", 80, 40,
        basis=FigureBasis.ACTUAL, quarantine_reason="",
    )
    for spaces in range(1, 65):
        status = spaces % 3
        add_line(
            db_session, entity, latest, source, "Total" + " " * spaces, 100, 50,
            basis=(FigureBasis.MODELLED if status == 0 else FigureBasis.PROJECTED)
            if status != 2 else None,
            quarantine_reason="not source verified" if status == 2 else None,
        )

    evidence_rows_fetched = []

    def measure(conn, cursor, statement, parameters, context, executemany):
        if not (
            statement.lstrip().lower().startswith("select")
            and "budget_lines.provenance" in statement
        ):
            return
        probe = conn.connection.driver_connection.cursor()
        try:
            probe.execute(statement, parameters)
            evidence_rows_fetched.append(len(probe.fetchall()))
        finally:
            probe.close()

    event.listen(db_session.bind, "before_cursor_execute", measure)
    try:
        assert _latest_county_actuals_period_ids(db_session) == [older.id]
    finally:
        event.remove(db_session.bind, "before_cursor_execute", measure)

    assert sum(evidence_rows_fetched) == 1, evidence_rows_fetched


def test_no_rows_is_absent_not_a_zero_budget(client, county):
    result = summary(client)
    assert result["total_budget"] is None
    assert result["total_spent"] is None
    assert result["budget_sources"] == []
    assert result["budget_absent_reasons"]["total_allocation"] == "no_valid_period"

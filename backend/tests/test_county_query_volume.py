"""Cold county/federal reads keep their public contract without broad audit rows."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import event

from models import (
    Audit,
    BudgetLine,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    FiscalPeriod,
    PopulationData,
    Severity,
    SourceDocument,
)


@pytest.fixture()
def audit_query_data(db_session, seed_country, seed_source_doc):
    withheld_doc = SourceDocument(
        id=901,
        country_id=seed_country.id,
        publisher="OAG",
        title="Withheld report",
        url=None,
        fetch_date=datetime(2025, 8, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    mombasa = Entity(id=901, country_id=seed_country.id, type=EntityType.COUNTY,
                      canonical_name="Mombasa County", slug="mombasa-performance")
    kwale = Entity(id=902, country_id=seed_country.id, type=EntityType.COUNTY,
                   canonical_name="Kwale County", slug="kwale-performance")
    lamu = Entity(id=903, country_id=seed_country.id, type=EntityType.COUNTY,
                  canonical_name="Lamu County", slug="lamu-performance")
    ministry = Entity(id=904, country_id=seed_country.id, type=EntityType.MINISTRY,
                      canonical_name="Ministry of Test", slug="ministry-performance",
                      meta={"unpublished_detail": "e" * 10_000})
    old_period = FiscalPeriod(id=901, country_id=seed_country.id, label="FY2022/23",
                              start_date=datetime(2022, 7, 1), end_date=datetime(2023, 6, 30))
    budget_period = FiscalPeriod(id=902, country_id=seed_country.id, label="FY2024/25",
                                 start_date=datetime(2024, 7, 1), end_date=datetime(2025, 6, 30))
    db_session.add_all([withheld_doc, mombasa, kwale, lamu, ministry,
                        old_period, budget_period])
    db_session.flush()
    db_session.add_all([
        BudgetLine(entity_id=mombasa.id, period_id=budget_period.id,
                   category="Total", allocated_amount=1000, actual_spent=500,
                   currency="KES", source_document_id=seed_source_doc.id),
        PopulationData(entity_id=mombasa.id, year=2023, total_population=700_000),
        PopulationData(entity_id=kwale.id, year=2023, total_population=600_000),
        PopulationData(entity_id=lamu.id, year=2023, total_population=140_000),
    ])
    earlier_period = FiscalPeriod(id=903, country_id=seed_country.id, label="FY2021/22",
                                 start_date=datetime(2021, 7, 1), end_date=datetime(2022, 6, 30))
    # Source identity declares an executive volume. County association alone
    # cannot supply this institution under the current county-health policy.
    seed_source_doc.meta = {"extraction_stats": {"volume_kind": "executives"}}
    db_session.add(earlier_period)
    db_session.flush()

    def add_audit(entity, *, text, created, period=old_period, source=seed_source_doc,
                  provenance=None, severity=Severity.WARNING, amount=None,
                  opinion=None, audit_year=None):
        row = Audit(entity_id=entity.id, period_id=period.id, finding_text=text,
                    severity=severity, source_document_id=source.id,
                    provenance=provenance, amount=amount, audit_opinion=opinion,
                    audit_year=audit_year, page_ref="p.4", created_at=created,
                    management_response="r" * 10_000,
                    external_reference="x" * 10_000)
        db_session.add(row)
        return row

    add_audit(mombasa, text="withheld ahead of valid", source=withheld_doc,
              created=datetime(2026, 9, 2), severity=Severity.CRITICAL)
    add_audit(mombasa, text="synthetic ahead of valid", created=datetime(2026, 9, 1),
              provenance=[{"data_quality": "modelled"}], severity=Severity.CRITICAL)
    latest = add_audit(mombasa, text="valid latest " + "x" * 2000,
                       created=datetime(2025, 8, 1), provenance={"dataset_id": "official"},
                       severity=Severity.INFO, amount=Decimal("0"), audit_year=2023)
    for i in range(11):
        add_audit(mombasa, text=f"older {i} " + "y" * 2000,
                  period=earlier_period,
                  created=datetime(2024, 8, 1) if i < 2 else datetime(2024, 7, 31 - i),
                  provenance=["malformed", {"data_quality": "official"}],
                  severity=Severity.WARNING, audit_year=2022)

    add_audit(kwale, text="unknown peer " + "z" * 4000, created=datetime(2025, 1, 1),
              amount=None, opinion="qualified", audit_year=2023)
    add_audit(kwale, text="zero peer " + "z" * 4000, created=datetime(2024, 1, 1),
              amount=Decimal("0"), opinion="adverse", audit_year=2022)
    add_audit(kwale, text="stated peer " + "z" * 4000, created=datetime(2023, 1, 1),
              amount=Decimal("1000"), opinion="qualified", audit_year=2023)
    add_audit(lamu, text="unavailable peer", created=datetime(2025, 1, 1), amount=None)

    add_audit(ministry, text="federal missing " + "q" * 4000,
              created=datetime(2025, 1, 1), amount=None, provenance=[{}])
    add_audit(ministry, text="federal zero " + "q" * 4000,
              created=datetime(2024, 1, 1), amount=Decimal("0"),
              provenance=[{"amount_involved": "KES 0"}])
    add_audit(ministry, text="federal amount " + "q" * 4000,
              created=datetime(2023, 1, 1), amount=Decimal("100"),
              provenance=[{"amount_involved": "KES 100"}])
    add_audit(ministry, text="federal tied amount " + "q" * 4000,
              created=datetime(2026, 1, 1), period=budget_period,
              amount=Decimal("100"),
              provenance=[{"amount_involved": "KES 100"}])
    add_audit(ministry, text="withheld federal", source=withheld_doc,
              created=datetime(2026, 2, 1), amount=Decimal("900"))
    db_session.commit()
    return latest.id


@pytest.fixture()
def select_statements(db_session):
    engine = db_session.get_bind().engine
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_county_list_keeps_latest_display_grade_and_short_findings(
    client, audit_query_data, select_statements
):
    response = client.get("/api/v1/counties?fiscal_year=2024/25")
    assert response.status_code == 200, response.text
    county = next(row for row in response.json() if row["id"] == "047")
    assert county["audit_status"] == "clean"
    assert county["audit_findings_count"] == 12
    assert county["audit_issues"][0]["id"] == str(audit_query_data)
    assert county["audit_issues"][0]["description"] == ("valid latest " + "x" * 2000)[:200]
    assert len(county["audit_issues"]) == 10
    assert [issue["description"][:7] for issue in county["audit_issues"][1:3]] == [
        "older 0", "older 1"
    ]
    # Coverage is the selected executive FY end, not the ingestion timestamp.
    assert county["last_audit_date"] == "2023-06-30"
    assert county["audit_signal"]["source_period"] == "FY2022/23"
    assert county["audit_signal"]["official_opinion"] is False
    assert county["budget_2025"] == 1000
    audit_reads = [s for s in select_statements if "FROM audits" in s]
    # The source-bound health selector adds one batch of citation/period
    # metadata to the finding metadata + short-description batches.
    assert len(audit_reads) == 3
    assert sum("json_type(extractions.extracted_json)" in s for s in audit_reads) == 1
    assert sum("substr(audits.finding_text" in s.lower() for s in audit_reads) == 1
    assert not any("audits.finding_text AS audits_finding_text" in s for s in audit_reads)
    assert not any("audits.management_response" in s for s in audit_reads)
    assert any("substr(audits.finding_text" in s.lower() for s in audit_reads)


def test_peer_comparison_reads_only_metrics_and_preserves_zero(
    client, audit_query_data, select_statements
):
    response = client.get("/api/v1/counties/047/accountability")
    assert response.status_code == 200, response.text
    peer = response.json()["peer_comparison"]
    assert peer == {
        "region": "Coast",
        "region_avg_flagged_amount": 1000.0,
        "region_avg_grade": "D",
        "population_bracket": "500k-1M",
        "population_bracket_avg": 1000.0,
    }
    peer_reads = [s for s in select_statements if "FROM audits" in s and "audits.entity_id IN" in s]
    assert len(peer_reads) == 1
    selected = peer_reads[0].split("FROM audits", 1)[0]
    assert "audits.finding_text" not in selected
    assert "audits.provenance" not in selected
    assert "audits.management_response" not in selected


def test_county_list_does_not_infer_executive_identity_from_county_association(
    client, db_session, audit_query_data, seed_source_doc
):
    seed_source_doc.meta = {}
    db_session.commit()
    response = client.get("/api/v1/counties?fiscal_year=2024/25")
    assert response.status_code == 200, response.text
    county = next(row for row in response.json() if row["id"] == "047")
    assert county["audit_status"] == "pending"
    assert county["audit_signal"]["absent_reason"] == "missing_or_conflicting_audit_institution"
    assert county["last_audit_date"] is None
    assert county["audit_findings_count"] == 12
    assert county["budget_2025"] == 1000


def test_federal_full_and_top_contract_without_unused_audit_columns(
    client, audit_query_data, select_statements
):
    full_response = client.get("/api/v1/audits/federal")
    assert full_response.status_code == 200, full_response.text
    full = full_response.json()
    assert full["total_findings"] == 4
    assert full["withheld_findings"] == 1
    assert full["findings_with_amount"] == 3
    assert full["total_amount_in_findings"] == 200.0
    assert full["fiscal_years_covered"] == ["FY2024/25", "FY2022/23"]
    assert [f["finding"].split(" q")[0] for f in full["findings"]] == [
        "federal tied amount", "federal missing", "federal zero", "federal amount"
    ]
    top = client.get("/api/v1/audits/federal?top_findings=2").json()
    assert top["findings"] == [full["findings"][0], full["findings"][3]]
    assert {k: v for k, v in top.items() if k != "findings"} == {
        k: v for k, v in full.items() if k != "findings"
    }
    broad_reads = [
        s for s in select_statements
        if "FROM audits JOIN entities" in s
        and "audits.finding_text AS audits_finding_text" in s.split("FROM audits", 1)[0]
        and "ORDER BY audits.severity DESC, audits.created_at DESC" in s
    ]
    assert len(broad_reads) == 1
    assert "audits.management_response" not in broad_reads[0]
    assert "entities.metadata" not in broad_reads[0]
    assert "audits.external_reference" not in broad_reads[0]

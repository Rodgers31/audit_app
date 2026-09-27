"""County geography must not replace the institution actually audited."""
from datetime import datetime, timezone

from models import EntityType, Extraction
from test_audit_headline_derived import (
    _Seeder,
    _doc,
    _period,
    COUNTY_URL,
    national_report,
)


def test_assembly_and_executive_share_geography_not_institution(
    client, db_session, seed_country
):
    s = _Seeder(db_session)
    county = s.entity("Wajir County", EntityType.COUNTY)
    period = _period(db_session, 9500, "FY2020/21", 2020)
    for n, role in enumerate(("Assembly", "Executive")):
        doc = _doc(
            db_session,
            9500 + n,
            COUNTY_URL,
            f"County {role} report",
            datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        audit = s.finding(
            county,
            doc,
            period,
            title=f"Unaccounted {role} expenditure",
            page=38,
            body="This remains unresolved.",
        )
        extraction = db_session.get(Extraction, audit.extraction_id)
        payload = dict(extraction.extracted_json)
        payload.update(
            entity_name=f"County {role} of Wajir",
            volume_kind="assemblies" if n == 0 else "executives",
        )
        extraction.extracted_json = payload
    db_session.commit()
    response = client.get("/api/v1/accountability/missing-funds")
    assert response.status_code == 200, response.text
    data = response.json()
    assert {c["entity"] for c in data["cases"]} == {
        "County Assembly of Wajir",
        "County Executive of Wajir",
    }
    assert {c["county_name"] for c in data["cases"]} == {"Wajir County"}
    assert {c["entity_id"] for c in data["cases"]} == {county.id}
    assert data["affected_counties"] == 1
    assert all(c["source"]["page_url"].endswith("#page=38") for c in data["cases"])
    assert all("unresolved" in c["excerpt"] for c in data["cases"])


def test_old_report_fetched_later_does_not_supply_latest_year_headline(
    client, db_session, national_report
):
    from models import SourceDocument

    older = db_session.get(SourceDocument, 9000)
    older.fetch_date = datetime(2026, 9, 27, tzinfo=timezone.utc)
    db_session.commit()
    data = client.get("/api/v1/audits/federal").json()
    assert data["fiscal_year"] == "FY2024/25"
    assert data["headline"]["source_document"]["id"] == 9001


def test_unknown_institution_labels_do_not_collapse_distinct_national_entities(
    client, db_session, seed_country
):
    s = _Seeder(db_session)
    period = _period(db_session, 9500, "FY2020/21", 2020)
    doc = _doc(
        db_session,
        9500,
        COUNTY_URL,
        "National report",
        datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    for name in ("Ministry A", "Ministry B"):
        entity = s.entity(name)
        audit = s.finding(entity, doc, period, title="Unaccounted expenditure", page=38)
        extraction = db_session.get(Extraction, audit.extraction_id)
        payload = dict(extraction.extracted_json)
        payload.pop("entity_name")
        extraction.extracted_json = payload
    db_session.commit()
    data = client.get("/api/v1/accountability/missing-funds").json()
    assert data["affected_national_entities"] == 2
    assert len(data["cases"]) == 2
    assert all(c["entity"] is None for c in data["cases"])

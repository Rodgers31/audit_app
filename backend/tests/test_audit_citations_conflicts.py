"""Conflicting auditee declarations must withhold only the institution label."""

import json
from datetime import datetime, timezone

import pytest

from models import Extraction
from services.audit_citations import audited_institution
from test_audit_headline_derived import REPORT_URL, _Seeder, _doc, _period


@pytest.mark.parametrize("serialize", [lambda payload: payload, json.dumps])
def test_national_conflicting_declarations_have_no_preferred_label(serialize):
    payload = {
        "entity_name": "Ministry of Health",
        "auditee": "Ministry of Education",
    }
    assert audited_institution(serialize(payload)) is None


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"entity_name": "Ministry of Health"}, "Ministry of Health"),
        ({"auditee": "Ministry of Health"}, "Ministry of Health"),
        (
            {
                "entity_name": "  Ministry\t of  Health ",
                "auditee": "ministry OF health",
            },
            "Ministry of Health",
        ),
        ({"entity_name": "", "auditee": "Ministry of Health"}, "Ministry of Health"),
        ({"entity_name": True, "auditee": "Ministry of Health"}, "Ministry of Health"),
    ],
)
def test_nonconflicting_national_declarations_remain_publishable(payload, expected):
    assert audited_institution(payload) == expected


@pytest.mark.parametrize("payload", [None, {}, [], True, 1, float("nan"), "{", "[]"])
def test_absent_or_malformed_identity_does_not_invent_an_institution(payload):
    assert audited_institution(payload) is None


@pytest.mark.parametrize("county,printed", [
    ("Taita Taveta", "County Executive of Taita/Taveta"),
    ("Elgeyo Marakwet", "County Executive of Elgeyo/Marakwet"),
    ("Tharaka Nithi", "County Executive of Tharaka-Nithi"),
    ("Nairobi", "County Executive of Nairobi City"),
    ("Nairobi", "Nairobi City County Assembly"),
])
def test_current_county_volume_aliases_retain_printed_auditee(county, printed):
    role = "Assembly" if "Assembly" in printed else "Executive"
    payload = {"entity_name": f"County {role} of {county}", "auditee": printed}
    assert audited_institution(payload, county_name=f"{county} County") == printed


@pytest.mark.parametrize("printed", ["County Executive of Kilifi", "County Assembly of Taita/Taveta"])
def test_alias_resolution_does_not_hide_county_or_role_conflict(printed):
    payload = {"entity_name": "County Executive of Taita Taveta", "auditee": printed}
    assert audited_institution(payload, county_name="Taita Taveta County") is None


@pytest.mark.parametrize("conflicting", [True, False])
def test_national_api_keeps_finding_and_citation_when_only_label_is_conflicted(
    client, db_session, seed_country, conflicting
):
    seed = _Seeder(db_session)
    entity = seed.entity("Ministry of Health")
    period = _period(db_session, 9510, "FY2024/25", 2024)
    document = _doc(
        db_session,
        9510,
        REPORT_URL,
        "National report",
        datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    audit = seed.finding(
        entity, document, period, title="Unaccounted expenditure", page=38,
        body="The cited report retains this finding.",
    )
    extraction = db_session.get(Extraction, audit.extraction_id)
    payload = dict(extraction.extracted_json)
    payload["auditee"] = "Ministry of Education" if conflicting else "ministry OF health"
    extraction.extracted_json = payload
    db_session.commit()

    response = client.get("/api/v1/accountability/missing-funds")
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["cases"]) == 1
    case = data["cases"][0]
    assert case["entity"] == (None if conflicting else "Ministry of Health")
    assert case["entity_id"] == entity.id
    assert "The cited report retains this finding." in case["excerpt"]
    assert case["source"]["page_url"] == f"{REPORT_URL}#page=38"
    assert data["affected_national_entities"] == 1

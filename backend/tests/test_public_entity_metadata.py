"""Legacy JSON must not bypass publication rules on any public entity path."""

import pytest


CLAIM = "RETIRED_UNVERIFIED_CLAIM_322"


@pytest.fixture()
def legacy_entity(db_session, seed_entity, seed_source_doc, seed_fiscal_period):
    from models import Audit, Extraction, Severity

    seed_entity.canonical_name = "Nairobi County"
    ext = Extraction(
        source_document_id=seed_source_doc.id,
        extractor="oag_county_volume",
        page_number=23,
        extracted_json={
            "title": "Unresolved Prior Year Matters",
            "finding_text": "Genuine finding survives",
            "entity_name": "County Assembly of Nairobi",
        },
    )
    db_session.add(ext)
    db_session.flush()
    db_session.add(
        Audit(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            source_document_id=seed_source_doc.id,
            extraction_id=ext.id,
            page_ref="p.23",
            finding_text="Genuine finding survives",
            severity=Severity.WARNING,
        )
    )
    seed_entity.meta = {
        "metrics": {"FY2024/25": {"county_code": "001", "debt": CLAIM}},
        "county_code": "001",
        "governor": "Sourced Officeholder",
        "governor_provenance": {
            "source": "Council of Governors",
            "source_url": "https://cog.go.ke/current-governors/",
            "source_document_id": 77,
            "extractor": "cog_governors",
            "fetched_at": "2026-09-24T02:29:58+00:00",
            "extra_claim": CLAIM,
        },
        "stalled_projects": [{"name": CLAIM, "contracted_amount": 9}],
        "stalled_projects_count": 1,
        "missing_funds_cases": [
            {
                "description": CLAIM,
                "amount": "KES 99",
                "source_document_id": seed_source_doc.id,
                "page_ref": "p.23",
            }
        ],
        "audit_summary": {"claims": CLAIM},
        "economic_profile": {"major_issues": [CLAIM]},
        "future_unreviewed_key": CLAIM,
    }
    db_session.commit()
    return seed_entity


@pytest.mark.parametrize("path", ["/entities?limit=100", "/entities/1"])
def test_entity_routes_publish_only_reviewed_metadata(client, legacy_entity, path):
    response = client.get("/api/v1" + path)
    assert response.status_code == 200, response.text
    assert CLAIM not in response.text
    body = response.json()
    meta = (body[0] if isinstance(body, list) else body["entity"])["meta"]
    assert meta["metrics"] == {"FY2024/25": {"county_code": "001"}}
    assert meta["governor"] == "Sourced Officeholder"
    assert (
        meta["governor_provenance"]["source_url"]
        == "https://cog.go.ke/current-governors/"
    )
    assert meta["county_code"] == "001"


@pytest.mark.parametrize(
    "path",
    [
        "/counties",
        "/counties/1/comprehensive",
        "/counties/001/audits",
        "/audit/findings",
        "/accountability/missing-funds",
    ],
)
def test_normal_county_and_audit_paths_do_not_publish_retired_claims(
    client, legacy_entity, path
):
    response = client.get("/api/v1" + path)
    assert response.status_code == 200, response.text
    assert CLAIM not in response.text
    if path.endswith(("comprehensive", "audits", "findings")):
        assert "Genuine finding survives" in response.text


@pytest.mark.parametrize(
    "meta", [None, [], "legacy", {"metrics": [1]}, {"metrics": {"FY2024/25": CLAIM}}]
)
def test_malformed_metadata_is_not_a_public_claim(
    client, db_session, seed_entity, meta
):
    seed_entity.meta = meta
    db_session.commit()
    response = client.get("/api/v1/entities/1")
    assert response.status_code == 200, response.text
    assert response.json()["entity"]["meta"] == {}


@pytest.mark.parametrize(
    "meta",
    [
        True,
        1,
        "legacy",
        ["legacy"],
        {"metrics": {"FY2026/27": "legacy"}},
        {"metrics": {"FY2024/25": {"county_code": True}}},
        {"metrics": {"FY2024/25": {"county_code": CLAIM}}},
    ],
)
@pytest.mark.parametrize("path", ["/entities?limit=100", "/counties"])
def test_malformed_meta_cannot_hide_an_entity_or_leak_through_code(
    client, db_session, seed_entity, meta, path
):
    seed_entity.meta = meta
    db_session.commit()
    response = client.get("/api/v1" + path)
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert CLAIM not in response.text


@pytest.mark.parametrize(
    "path", ["/counties", "/counties/Nairobi", "/counties/1/comprehensive"]
)
def test_modelled_financial_metrics_cannot_bypass_the_metadata_contract(
    client, db_session, legacy_entity, path
):
    legacy_entity.meta = {
        "metrics": {
            "FY2024/25": {
                "county_code": "001",
                "transfers_received": 987654321.123,
                "development_budget": 987654321.123,
                "recurrent_budget": 987654321.123,
            }
        }
    }
    db_session.commit()
    response = client.get("/api/v1" + path)
    assert response.status_code == 200, response.text
    assert "987654321" not in response.text

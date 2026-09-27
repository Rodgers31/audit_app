"""Stored project evidence survives metadata sanitization without shape errors."""

import pytest


@pytest.mark.parametrize("metadata", [True, 1, "legacy", ["legacy"], {}, None, [], 0, False])
def test_malformed_metadata_does_not_hide_the_county(
    client, db_session, seed_entity, metadata
):
    seed_entity.canonical_name = "Nairobi County"
    seed_entity.meta = metadata
    db_session.commit()

    response = client.get("/api/v1/counties/1/comprehensive")
    assert response.status_code == 200, response.text
    block = response.json()["stalled_projects"]
    assert block["projects"] == []
    assert block["count"] is None
    assert block["reason"] == "no_evidence_backed_source"


def test_valid_project_metadata_reaches_the_evidence_gate(
    client, db_session, seed_entity
):
    seed_entity.canonical_name = "Nairobi County"
    sourced = {
        "project_name": "Synthetic sourced project positive control",
        "estimated_value_kes": 12500000,
        "amount_paid_kes": None,
        "source_url": "https://cob.go.ke/synthetic-test-project.pdf",
        "source_page": 23,
        "as_of": "2026-06-30",
        "reported_by": "County treasury, as reported to the Controller of Budget",
    }
    seed_entity.meta = {
        "stalled_projects": {
            "rows": [
                sourced,
                {"project_name": "UNSOURCED_PROJECT_MUST_BE_WITHHELD", "estimated_value_kes": 99999999},
            ]
        },
        "unreviewed_claim": "PRIVATE_METADATA_MUST_NOT_BE_PUBLISHED",
    }
    db_session.commit()

    response = client.get("/api/v1/counties/1/comprehensive")
    assert response.status_code == 200, response.text
    block = response.json()["stalled_projects"]
    assert block["count"] == 1
    assert block["projects"][0]["project_name"] == sourced["project_name"]
    assert block["projects"][0]["source_page"] == 23
    assert block["total_contracted_value"] == 12500000
    assert block["total_amount_paid"] is None
    assert block["withheld"] == {"count": 1, "by_reason": {"no_source_document": 1}}
    assert "UNSOURCED_PROJECT_MUST_BE_WITHHELD" not in response.text
    assert "PRIVATE_METADATA_MUST_NOT_BE_PUBLISHED" not in response.text

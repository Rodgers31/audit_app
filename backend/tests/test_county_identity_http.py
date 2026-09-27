"""Independent HTTP attacks on county identity, without network or production DB.

The expected codes come from the saved KNBS table, while amounts are deliberately
unique to each county. Correct-looking names cannot conceal crossed records.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from models import BudgetLine, Entity, EntityType


SOURCE_CODES = json.loads(
    (Path(__file__).parent / "fixtures/knbs_county_codes.json").read_text()
)["counties"]


def _canonical_name(source_name):
    # Exercise real accepted aliases rather than only the spelling in main.py.
    return source_name.replace("/", "-") + " County"


def _route(code):
    return {"001": "047", "047": "001"}.get(code, code)


@pytest.fixture(autouse=True)
def no_enhanced_network(monkeypatch):
    async def absent(_county_name):
        return None

    monkeypatch.setattr("main.InternalAPIClient.get_county_data", absent)


@pytest.fixture()
def all_counties(db_session, seed_country, seed_fiscal_period, seed_source_doc):
    rows = {}
    for code, source_name in SOURCE_CODES.items():
        entity = Entity(
            id={"001": 4, "047": 3}.get(code, 1000 + int(code)),
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name=_canonical_name(source_name),
            slug=source_name.lower().replace(" ", "-").replace("/", "-") + "-county",
            # Deliberately stale display metadata must not control identity.
            meta={"metrics": {"FY2024/25": {"county_code": _route(code)}}},
        )
        db_session.add(entity)
        db_session.flush()
        db_session.add(
            BudgetLine(
                entity_id=entity.id,
                period_id=seed_fiscal_period.id,
                category="Total",
                allocated_amount=int(code) * 1_000_000,
                actual_spent=int(code) * 500_000,
                currency="KES",
                source_document_id=seed_source_doc.id,
                page_ref=f"p.{int(code) + 1}",
            )
        )
        rows[code] = SimpleNamespace(
            id=entity.id, canonical_name=entity.canonical_name, slug=entity.slug
        )
    db_session.commit()
    return rows


@pytest.mark.parametrize(
    "identifier_kind", ["legacy", "official", "slug", "pk", "name"]
)
@pytest.mark.parametrize("view", ["detail", "comprehensive", "money-flow"])
def test_all_47_counties_round_trip_to_their_own_record(
    client, all_counties, identifier_kind, view
):
    problems = []
    for code, entity in all_counties.items():
        identifier = {
            "legacy": _route(code),
            "official": "code:" + code,
            "slug": entity.slug,
            "pk": str(entity.id),
            "name": entity.canonical_name.removesuffix(" County"),
        }[identifier_kind]
        suffix = {
            "detail": "",
            "comprehensive": "/comprehensive",
            "money-flow": "/money-flow?year=2024%2F25",
        }[view]
        response = client.get(f"/api/v1/counties/{quote(identifier, safe='')}{suffix}")
        if response.status_code != 200:
            problems.append((code, identifier, response.status_code, response.json()))
            continue
        body = response.json()
        if view == "money-flow":
            observed_name = body["county_name"]
            observed_amount = next(
                s["amount"] for s in body["stages"] if s["stage"] == "Allocated"
            )
            if body["county_id"] != entity.id:
                problems.append((code, "wrong PK", body["county_id"], entity.id))
        else:
            observed_name = body["name"] + " County"
            observed_amount = (
                body["total_budget"]
                if view == "detail"
                else body["budget"]["total_allocated"]
            )
            if view == "detail" and body["code"] != code:
                problems.append((code, "wrong official code", body["code"]))
        if (
            observed_name != entity.canonical_name
            or observed_amount != int(code) * 1_000_000
        ):
            problems.append(
                (code, "wrong identity/amount", observed_name, observed_amount)
            )
    assert not problems, problems


def test_all_47_map_links_and_entity_records_agree(client, all_counties):
    response = client.get("/api/v1/counties?limit=50")
    assert response.status_code == 200, response.text
    mapped = {row["code"]: row for row in response.json()}
    response = client.get("/api/v1/entities?entity_type=county&limit=100")
    assert response.status_code == 200, response.text
    listed = {row["id"]: row for row in response.json()}
    assert len(mapped) == len(listed) == 47
    for code, entity in all_counties.items():
        row = mapped[code]
        assert row["id"] == _route(code)
        assert row["name"] + " County" == entity.canonical_name
        assert row["total_budget"] == int(code) * 1_000_000
        assert listed[entity.id]["code"] == code
        assert listed[entity.id]["financial_summary"] == row["financial_summary"]
        detail = client.get(f"/api/v1/entities/{entity.id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["financial_time_series"][0] == row["financial_summary"]


@pytest.mark.parametrize("view", ["", "/comprehensive", "/money-flow?year=2024%2F25"])
def test_raw_pk_does_not_become_zero_padded_legacy_route(client, all_counties, view):
    assert all_counties["001"].id == 4
    response = client.get(f"/api/v1/counties/4{view}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (
        body.get("name", body.get("county_name")).removesuffix(" County") == "Mombasa"
    )


@pytest.mark.parametrize(
    "identifier",
    [
        "%",
        "Nairob%",
        "N_irobi",
        "001x",
        "code:",
        "code:1",
        "code:000",
        "code:048",
        "-1",
        "0",
        "null",
        "Nairobi Hospital",
        "Mombasa Water Company",
    ],
)
@pytest.mark.parametrize("view", ["", "/comprehensive", "/money-flow?year=2024%2F25"])
def test_invalid_or_institution_identifier_never_returns_a_county(
    client, all_counties, identifier, view
):
    response = client.get(f"/api/v1/counties/{quote(identifier, safe='')}{view}")
    assert response.status_code == 404, (
        identifier,
        response.status_code,
        response.text,
    )


@pytest.mark.parametrize("view", ["", "/comprehensive"])
def test_every_identifier_form_preserves_geographic_identity(
    client, all_counties, view
):
    # Official code001 and PK4 are Mombasa; neither may inherit Nairobi's
    # fallback coordinates simply because the URL differs from legacy047.
    baseline = client.get(f"/api/v1/counties/047{view}")
    assert baseline.status_code == 200, baseline.text
    expected = baseline.json()["coordinates"]
    for identifier in ["code:001", "4", "mombasa-county", "Mombasa"]:
        response = client.get(f"/api/v1/counties/{quote(identifier, safe='')}{view}")
        assert response.status_code == 200, response.text
        assert response.json()["coordinates"] == expected, (
            identifier,
            response.json()["coordinates"],
            expected,
        )


def test_explicit_official_code_endpoint_for_all_47(client, all_counties):
    for code, entity in all_counties.items():
        response = client.get(f"/api/v1/counties/code/{code}")
        assert response.status_code == 200, response.text
        assert response.json()["code"] == code
        assert response.json()["total_budget"] == int(code) * 1_000_000

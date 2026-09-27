"""The official county code is not an Entity PK or a legacy route ID (#306)."""
import json
from pathlib import Path

from models import Entity, EntityType


def test_all_47_public_codes_match_primary_source(client, db_session, seed_country):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/knbs_county_codes.json").read_text()
    )
    for code, name in fixture["counties"].items():
        # Use the historic display aliases handled by the app.
        name = (
            name.replace("/", " ").replace("-", " ").replace("Nairobi City", "Nairobi")
        )
        db_session.add(
            Entity(
                country_id=seed_country.id,
                canonical_name=name + " County",
                type=EntityType.COUNTY,
                slug=name.lower().replace(" ", "-"),
            )
        )
    db_session.commit()
    rows = client.get("/api/v1/counties?limit=50").json()
    assert len(rows) == 47
    expected = {
        name.replace("/", " ")
        .replace("-", " ")
        .replace("Nairobi City", "Nairobi"): code
        for code, name in fixture["counties"].items()
    }
    assert {r["name"]: r["code"] for r in rows} == expected
    by_name = {r["name"]: r for r in rows}
    assert by_name["Nairobi"]["id"] == "001"
    assert by_name["Mombasa"]["id"] == "047"


def test_official_code_does_not_change_legacy_links_or_foreign_keys(
    client, db_session, seed_country
):
    entities = []
    for name, pk, route in [("Nairobi", 101, "001"), ("Mombasa", 102, "047")]:
        entity = Entity(
            id=pk,
            country_id=seed_country.id,
            canonical_name=name + " County",
            type=EntityType.COUNTY,
            slug=name.lower() + "-" + route,
            meta={"metrics": {"FY2024/25": {"county_code": route}}},
        )
        db_session.add(entity)
        entities.append(entity)
    db_session.commit()
    from main import _resolve_county_entity

    for entity, route, code in zip(entities, ["001", "047"], ["047", "001"]):
        assert _resolve_county_entity(db_session, route).id == entity.id
        assert _resolve_county_entity(db_session, entity.slug).id == entity.id
        listing = client.get("/api/v1/entities?entity_type=county").json()
        assert next(row for row in listing if row["id"] == entity.id)["code"] == code


def test_migration_proposal_preserves_identity_and_all_other_metadata():
    from types import SimpleNamespace
    from copy import deepcopy
    import pytest
    from services.county_identity import OFFICIAL_COUNTY_CODES, legacy_county_route_id
    from services.county_code_migration import propose_county_code_changes

    entities = [
        SimpleNamespace(
            id=int(code) + 100,
            type="county",
            canonical_name=name + " County",
            slug=name.lower(),
            meta={
                "metrics": {"FY2024/25": {"county_code": legacy_county_route_id(name)}},
                "keep": {"test": 9},
            },
        )
        for code, name in OFFICIAL_COUNTY_CODES.items()
    ]
    original = deepcopy([e.meta for e in entities])
    changes = propose_county_code_changes(entities)
    assert len(changes) == 2
    assert [e.meta for e in entities] == original
    for change in changes:
        entity = next(e for e in entities if e.id == change["entity_id"])
        assert change["slug"] == entity.slug
        assert change["after"]["keep"] == entity.meta["keep"]
        entity.meta = change["after"]
    assert propose_county_code_changes(entities) == []
    with pytest.raises(ValueError, match="complete"):
        propose_county_code_changes(entities[:-1])
    entities[0].meta["county_code"] = "garbage"
    with pytest.raises(ValueError, match="Unexpected code"):
        propose_county_code_changes(entities)


def test_bootstrap_does_not_reintroduce_legacy_codes(monkeypatch):
    from tests.test_stored_county_metrics_are_cleared import seeded_from_scratch
    from services.county_identity import official_county_code

    fixture = seeded_from_scratch.__wrapped__(monkeypatch)
    try:
        entities = next(fixture)
        assert len(entities) == 47
        for entity in entities:
            metrics = entity.meta.get("metrics", {})
            assert metrics
            assert all(row["county_code"] == official_county_code(entity.canonical_name) for row in metrics.values())
    finally:
        fixture.close()

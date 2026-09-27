"""Executed hostile-input and relational checks for the county-code proposal."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from models import Audit, BudgetLine, Entity, EntityType, Loan, Severity
from services.county_code_migration import propose_county_code_changes
from services.county_identity import legacy_county_route_id, official_county_code


def _official():
    return json.loads(
        (Path(__file__).parent / "fixtures/knbs_county_codes.json").read_text()
    )["counties"]


def _snapshot():
    return [
        SimpleNamespace(
            id=100 + int(code),
            type="county",
            canonical_name=name + " County",
            slug=name.lower().replace(" ", "-") + "-county",
            meta={
                "code": legacy_county_route_id(name),
                "county_code": legacy_county_route_id(name),
                "metrics": {
                    "FY2024/25": {
                        "county_code": legacy_county_route_id(name),
                        "amount": 0,
                    }
                },
                "nested": {"preserve": [1, None, False]},
            },
        )
        for code, name in _official().items()
    ]


@pytest.mark.parametrize(
    "name",
    [
        None,
        True,
        1,
        47,
        {},
        [],
        float("nan"),
        "",
        "   ",
        "Nairobi Water Company",
        "Mombasa County Assembly",
        "Nairobi County Referral Hospital",
        "Ministry of Mombasa",
        "Nairob",
        "Nairobi County County",
        "Unlisted County",
    ],
)
def test_unknown_or_malformed_names_never_resolve(name):
    assert official_county_code(name) is None
    assert legacy_county_route_id(name) is None


def test_all_47_primary_source_names_and_common_aliases_resolve():
    for code, name in _official().items():
        for spelling in [
            name,
            name + " County",
            "  " + name.upper() + " COUNTY  ",
            name.replace("/", " ").replace("-", " ").replace("'", "’"),
        ]:
            assert official_county_code(spelling) == code
        assert legacy_county_route_id(name) == {"001": "047", "047": "001"}.get(
            code, code
        )


@pytest.mark.parametrize("size", [0, 1, 46])
def test_incomplete_snapshot_is_rejected(size):
    with pytest.raises(ValueError):
        propose_county_code_changes(_snapshot()[:size])


def test_duplicate_identity_is_rejected_even_with_47_rows():
    rows = _snapshot()
    rows[-1] = deepcopy(rows[0])
    with pytest.raises(ValueError):
        propose_county_code_changes(rows)


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        [],
        "",
        0,
        {"metrics": []},
        {"metrics": {"FY2024/25": None}},
        {"county_code": None},
        {"county_code": True},
        {"county_code": "002"},
    ],
)
def test_malformed_metadata_never_produces_a_proposal(metadata):
    rows = _snapshot()
    rows[0].meta = metadata
    with pytest.raises(ValueError):
        propose_county_code_changes(rows)


def test_noncounty_institution_cannot_participate_in_migration():
    rows = _snapshot()
    rows[0].type = "agency"
    with pytest.raises(ValueError):
        propose_county_code_changes(rows)


@pytest.mark.parametrize("identity", [None, True, -1, "101", float("nan")])
def test_invalid_primary_keys_never_produce_a_proposal(identity):
    rows = _snapshot()
    rows[0].id = identity
    with pytest.raises(ValueError):
        propose_county_code_changes(rows)


def test_duplicate_primary_keys_cannot_target_one_row_as_two_counties():
    rows = _snapshot()
    rows[-1].id = rows[0].id
    with pytest.raises(ValueError):
        propose_county_code_changes(rows)


def test_duplicate_slugs_are_rejected():
    rows = _snapshot()
    rows[-1].slug = rows[0].slug
    with pytest.raises(ValueError):
        propose_county_code_changes(rows)


def test_proposal_is_reversible_and_does_not_mutate_input():
    rows = _snapshot()
    original = deepcopy(rows)
    changes = propose_county_code_changes(rows)
    assert rows == original
    assert len(changes) == 2
    by_id = {row.id: row for row in rows}
    for change in changes:
        row = by_id[change["entity_id"]]
        assert (row.id, row.slug, row.canonical_name) == (
            change["entity_id"],
            change["slug"],
            change["canonical_name"],
        )
        assert row.meta == change["before"]
        assert change["after"]["nested"] == row.meta["nested"]
        assert change["after"]["metrics"]["FY2024/25"]["amount"] == 0
        row.meta = deepcopy(change["after"])
    assert propose_county_code_changes(rows) == []
    for change in changes:
        by_id[change["entity_id"]].meta = deepcopy(change["before"])
    assert rows == original


def test_proposed_metadata_changes_preserve_actual_relationships(
    client, db_session, seed_country, seed_fiscal_period, seed_source_doc
):
    from main import _resolve_county_entity

    rows = []
    for snapshot in _snapshot():
        row = Entity(
            id=snapshot.id,
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name=snapshot.canonical_name.replace("Nairobi City", "Nairobi"),
            slug=snapshot.slug.replace("nairobi-city", "nairobi"),
            meta=snapshot.meta,
        )
        db_session.add(row)
        rows.append(row)
    db_session.flush()
    relations = []
    for entity_id in (101, 147):
        common = dict(entity_id=entity_id, source_document_id=seed_source_doc.id)
        budget = BudgetLine(
            **common,
            period_id=seed_fiscal_period.id,
            category="Total",
            allocated_amount=entity_id,
            actual_spent=0,
            currency="KES",
            page_ref="p.1",
        )
        loan = Loan(
            **common,
            lender="Supplier",
            principal=entity_id,
            outstanding=entity_id,
            issue_date=datetime(2025, 6, 30),
            currency="KES",
        )
        audit = Audit(
            **common,
            period_id=seed_fiscal_period.id,
            finding_text="Unpaid invoice",
            severity=Severity.INFO,
            page_ref="p.1",
        )
        db_session.add_all([budget, loan, audit])
        relations.extend([budget, loan, audit])
    db_session.flush()
    before = [
        (type(row), row.id, row.entity_id, row.entity.canonical_name)
        for row in relations
    ]
    routes = {
        route: _resolve_county_entity(db_session, route).id for route in ("001", "047")
    }
    by_id = {row.id: row for row in rows}
    changes = propose_county_code_changes(rows)
    for change in changes:
        by_id[change["entity_id"]].meta = change["after"]
    db_session.flush()
    db_session.expire_all()
    assert [
        (
            kind,
            pk,
            db_session.get(kind, pk).entity_id,
            db_session.get(kind, pk).entity.canonical_name,
        )
        for kind, pk, _, _ in before
    ] == before
    assert {
        route: _resolve_county_entity(db_session, route).id for route in routes
    } == routes
    for route, code, name in [("001", "047", "Nairobi"), ("047", "001", "Mombasa")]:
        response = client.get(f"/api/v1/counties/{route}")
        assert response.status_code == 200, response.text
        assert response.json()["name"] == name
        assert response.json()["code"] == code


@pytest.mark.parametrize(
    "name,slug,route",
    [
        ("Nairobi City County", "nairobi-city-county", "001"),
        ("Taita/Taveta County", "taita-taveta-county", "006"),
        ("Elgeyo/Marakwet County", "elgeyo-marakwet-county", "028"),
    ],
)
def test_supported_authoritative_names_preserve_legacy_route_identity(
    client, db_session, seed_country, name, slug, route
):
    from main import _resolve_county_entity

    row = Entity(
        id=500,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name=name,
        slug=slug,
    )
    db_session.add(row)
    db_session.flush()
    assert official_county_code(name) is not None
    resolved = _resolve_county_entity(db_session, route)
    assert resolved is not None and resolved.id == row.id
    listed = client.get("/api/v1/counties").json()[0]
    assert listed["id"] == route


@pytest.mark.parametrize("unknown_name", ["%", "Nairob%", "N_irobi"])
def test_unknown_wildcard_names_do_not_resolve_to_real_county(
    db_session, seed_entity, unknown_name
):
    from main import _resolve_county_entity

    assert official_county_code(unknown_name) is None
    assert _resolve_county_entity(db_session, unknown_name) is None


def test_existing_institution_with_county_name_is_not_a_county(
    db_session, seed_country
):
    from main import _resolve_county_entity

    institution = Entity(
        id=500,
        country_id=seed_country.id,
        canonical_name="Nairobi County",
        slug="nairobi-county",
        type=EntityType.AGENCY,
    )
    db_session.add(institution)
    db_session.flush()
    for identifier in ("500", "001", "Nairobi", "nairobi-county"):
        assert _resolve_county_entity(db_session, identifier) is None

"""Conflicting auditee declarations must withhold only the institution label."""

import json

import pytest

from services.audit_citations import audited_institution


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



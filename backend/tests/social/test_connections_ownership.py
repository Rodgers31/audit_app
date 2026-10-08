"""Declared equality is not provider verification or callback authorization."""
from dataclasses import asdict, FrozenInstanceError, replace
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from social.connections.ownership import DeclaredCredentialOwnership, bind_declared_ownership
from social.connections.signed_requests import VerifiedSignedRequest
from test_connections_signed_requests import APP, SECRET, SUBJECT, signed, verify


@pytest.fixture
def inputs():
    request = verify(signed())
    credential_id = uuid4()
    declaration = DeclaredCredentialOwnership(APP, SUBJECT, credential_id, 7)
    expected = {"expected_app_id": APP, "expected_credential_id": credential_id, "expected_credential_version": 7}
    return request, declaration, expected


def assert_unverified(result):
    assert result.status == "unverified" and result.provider_verification_performed is False
    assert result.credential_id is None and result.credential_version is None


def test_exact_supplied_match_is_only_a_declared_binding(inputs):
    request, declaration, expected = inputs
    result = bind_declared_ownership(request, declaration, **expected)
    assert result.status == "declared_match" and result.provider_verification_performed is False
    assert result.credential_id == declaration.credential_id and result.credential_version == 7
    assert "app_id" not in asdict(result) and "app_scoped_user_id" not in asdict(result)
    with pytest.raises(FrozenInstanceError):
        result.provider_verification_performed = True
    with pytest.raises(FrozenInstanceError):
        declaration.app_id = "other"


@pytest.mark.parametrize("declaration", [None, {}, [], "legacy", 0, False,
    SimpleNamespace(external_user_id=SUBJECT), SimpleNamespace(app_id=APP, app_scoped_user_id=SUBJECT)])
def test_absent_legacy_and_untyped_ownership_is_unverified(inputs, declaration):
    request, _, expected = inputs
    assert_unverified(bind_declared_ownership(request, declaration, **expected))


@pytest.mark.parametrize("changes", [{"app_id": "111"}, {"app_id": None}, {"app_id": 123456789}, {"app_id": "01"},
    {"app_id": "１２３"}, {"app_scoped_user_id": "111"}, {"app_scoped_user_id": None},
    {"app_scoped_user_id": int(SUBJECT)}, {"app_scoped_user_id": True}, {"app_scoped_user_id": "0"},
    {"app_scoped_user_id": SUBJECT + "\n"}, {"app_scoped_user_id": "1" * 65}, {"credential_id": None},
    {"credential_id": uuid4()}, {"credential_id": UUID(int=0)}, {"credential_id": "uuid-string"},
    {"credential_version": 6}, {"credential_version": 0}, {"credential_version": -1}, {"credential_version": True},
    {"credential_version": 7.0}, {"credential_version": "7"}, {"credential_version": 2**63},
    {"credential_version": float("nan")}, {"credential_version": float("inf")}])
def test_declared_identity_and_version_must_match_exactly(inputs, changes):
    request, declaration, expected = inputs
    assert_unverified(bind_declared_ownership(request, replace(declaration, **changes), **expected))


@pytest.mark.parametrize("changes", [{"expected_app_id": "111"}, {"expected_app_id": None}, {"expected_app_id": True},
    {"expected_app_id": "0"}, {"expected_app_id": "01"}, {"expected_credential_id": uuid4()},
    {"expected_credential_id": None}, {"expected_credential_id": UUID(int=0)}, {"expected_credential_id": "uuid-string"},
    {"expected_credential_version": 8}, {"expected_credential_version": 0}, {"expected_credential_version": -1},
    {"expected_credential_version": True}, {"expected_credential_version": "7"}, {"expected_credential_version": 7.0},
    {"expected_credential_version": 2**63}, {"expected_credential_version": float("nan")},
    {"expected_credential_version": float("inf")}])
def test_expected_identity_is_also_strict(inputs, changes):
    request, declaration, expected = inputs
    assert_unverified(bind_declared_ownership(request, declaration, **{**expected, **changes}))


@pytest.mark.parametrize("candidate", [None, {}, [], True, "signed-request", SimpleNamespace(app_id=APP, app_scoped_user_id=SUBJECT)])
def test_request_requires_the_explicit_typed_shape(inputs, candidate):
    _, declaration, expected = inputs
    assert_unverified(bind_declared_ownership(candidate, declaration, **expected))


@pytest.mark.parametrize("changes", [{"app_id": "111"}, {"app_id": None}, {"app_id": True},
    {"app_scoped_user_id": "111"}, {"app_scoped_user_id": None}, {"app_scoped_user_id": True},
    {"payload_fingerprint": None}, {"payload_fingerprint": "A" * 64}, {"payload_fingerprint": "g" * 64},
    {"payload_fingerprint": "0" * 63}, {"payload_fingerprint": "0" * 64 + "\n"},
    {"issued_at": True}, {"issued_at": 0}, {"expires_at": -1}, {"expires_at": "1"},
    {"issued_at": 2, "expires_at": 1}])
def test_even_typed_request_fields_are_rechecked(inputs, changes):
    request, declaration, expected = inputs
    assert_unverified(bind_declared_ownership(replace(request, **changes), declaration, **expected))


def test_missing_fields_in_forged_instances_fail_closed(inputs):
    request, declaration, expected = inputs
    incomplete_request = object.__new__(VerifiedSignedRequest)
    incomplete_declaration = object.__new__(DeclaredCredentialOwnership)
    assert_unverified(bind_declared_ownership(incomplete_request, declaration, **expected))
    assert_unverified(bind_declared_ownership(request, incomplete_declaration, **expected))
    assert repr(incomplete_request) == "VerifiedSignedRequest()"
    assert repr(incomplete_declaration) == "DeclaredCredentialOwnership()"


@pytest.mark.parametrize("bad_int", [-1, 2**128, "malformed", True])
def test_corrupt_exact_uuid_instances_fail_closed(inputs, bad_int):
    request, declaration, expected = inputs
    identity = object.__new__(UUID)
    object.__setattr__(identity, "int", bad_int)
    declaration = replace(declaration, credential_id=identity)
    expected = {**expected, "expected_credential_id": identity}
    # Matching malformed UUIDs used to bypass the non-nil check and produce a
    # declared match. Recheck the internal integer even for the exact UUID type.
    assert_unverified(bind_declared_ownership(request, declaration, **expected))


def test_matching_constructed_declarations_do_not_become_provider_verification(inputs):
    request, declaration, expected = inputs
    supplied = VerifiedSignedRequest(request.app_id, request.app_scoped_user_id, request.payload_fingerprint)
    result = bind_declared_ownership(supplied, declaration, **expected)
    assert result.status == "declared_match" and result.provider_verification_performed is False
    # The helper checks supplied equality only; these inputs have not acquired
    # authority by passing through a dataclass constructor.


def test_representations_logs_and_results_do_not_expose_subject(inputs, caplog, capsys):
    request, declaration, expected = inputs
    result = bind_declared_ownership(request, declaration, **expected)
    for fragment in (APP, SUBJECT, SECRET, signed()):
        assert fragment not in repr(request) + repr(declaration) + repr(result) + repr(asdict(result)) + caplog.text
    assert capsys.readouterr() == ("", "")


def test_direct_calls_perform_no_external_lookup(inputs, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Privacy prerequisites must remain offline")
    monkeypatch.setattr("socket.socket", forbidden)
    monkeypatch.setattr("pathlib.Path.open", forbidden)
    monkeypatch.setattr("os.getenv", forbidden)
    request = verify(signed())
    _, declaration, expected = inputs
    assert bind_declared_ownership(request, declaration, **expected).status == "declared_match"

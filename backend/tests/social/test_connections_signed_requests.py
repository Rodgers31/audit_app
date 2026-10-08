"""Execute only offline signature fixtures; no callback or provider interaction."""
import base64
from dataclasses import FrozenInstanceError
import hashlib
import hmac
import json

import pytest

from social.connections.signed_requests import MAX_PAYLOAD_BYTES, MAX_SIGNED_REQUEST_BYTES, MAX_TIMESTAMP, SignedRequestError, verify_signed_request


SECRET = "fixture-app-secret-never-live"
APP = "123456789"
SUBJECT = "987654321"


def encode(value, *, padding=False):
    result = base64.urlsafe_b64encode(value).decode("ascii")
    return result if padding else result.rstrip("=")


def signed(payload=None, *, raw=None, padding=False, secret=SECRET, encoded=None):
    if raw is None:
        raw = json.dumps(payload if payload is not None else {"algorithm": "HMAC-SHA256", "user_id": SUBJECT},
            separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    encoded = encoded if encoded is not None else encode(raw, padding=padding)
    signature = hmac.digest(secret.encode("ascii"), encoded.encode("ascii"), "sha256")
    return encode(signature, padding=padding) + "." + encoded


def verify(value, **changes):
    return verify_signed_request(value, **{"app_secret": SECRET, "expected_app_id": APP, **changes})


@pytest.mark.parametrize("padding", [False, True])
@pytest.mark.parametrize("timestamps", [{}, {"issued_at": 1291836800}, {"expires": 1291840400},
    {"issued_at": 1291836800, "expires": 1291840400}])
def test_official_shape_and_original_segment_mac(padding, timestamps):
    raw = json.dumps({"algorithm": "HMAC-SHA256", "user_id": SUBJECT, "app_id": APP, **timestamps}, indent=2).encode()
    value = signed(raw=raw, padding=padding)
    result = verify(value)
    assert (result.app_id, result.app_scoped_user_id) == (APP, SUBJECT)
    assert result.issued_at == timestamps.get("issued_at") and result.expires_at == timestamps.get("expires")
    encoded_payload = value.split(".")[1]
    assert result.payload_fingerprint == hashlib.sha256(b"meta-signed-request-v1\0" + APP.encode() + b"\0" + encoded_payload.encode()).hexdigest()
    assert result == verify(value)
    with pytest.raises(FrozenInstanceError):
        result.app_scoped_user_id = "other"


def test_signature_authenticates_original_encoding_not_canonical_json():
    original = b'{ "user_id" : "987654321", "algorithm" : "HMAC-SHA256" }'
    value = signed(raw=original)
    assert verify(value).app_scoped_user_id == SUBJECT
    normalized = signed({"algorithm": "HMAC-SHA256", "user_id": SUBJECT}).split(".")[1]
    with pytest.raises(SignedRequestError):
        verify(value.split(".")[0] + "." + normalized)


@pytest.mark.parametrize("value", [None, b"encoded", True, 0, [], {}, "", ".", "a.b.c", "abc", "a." , ".a",
    "a" * (MAX_SIGNED_REQUEST_BYTES + 1), "\nabc.def", "abc.def\n", "é.def", " abc.def", "abc.def "])
def test_request_input_and_size_rejected(value):
    with pytest.raises(SignedRequestError):
        verify(value)


@pytest.mark.parametrize("signature", ["A", "***", "A=" , "A===", "AA==", "AA=", "AA\n", "+AAA", "/AAA",
    encode(b"x" * 31), encode(b"x" * 33)])
def test_signature_format_and_size_rejected(signature):
    with pytest.raises(SignedRequestError):
        verify(signature + "." + signed().split(".")[1])


def test_signature_noncanonical_padding_bits_rejected():
    value = signed()
    signature, payload = value.split(".")
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    index = alphabet.index(signature[-1])
    alias = signature[:-1] + alphabet[index + 1]
    assert base64.urlsafe_b64decode(alias + "=") == base64.urlsafe_b64decode(signature + "=")
    with pytest.raises(SignedRequestError):
        verify(alias + "." + payload)


@pytest.mark.parametrize("encoded", ["", "A", "AA=", "***", "AA===", "AA\n", "AA+", "AA/", "AB"])
def test_signed_invalid_payload_encoding_rejected(encoded):
    with pytest.raises(SignedRequestError):
        verify(signed(encoded=encoded))


@pytest.mark.parametrize("raw", [b"", b"{", b"null", b"[]", b"true", b"42", b'"text"', b"\xff",
    b'{"algorithm":"HMAC-SHA256","user_id":"987654321","user_id":"987654321"}',
    b'{"algorithm":"HMAC-SHA256","user_id":"987654321","expires":NaN}',
    b'{"algorithm":"HMAC-SHA256","user_id":"987654321","expires":Infinity}',
    b'{"algorithm":"HMAC-SHA256","user_id":"987654321","extra":{"a":1,"a":2}}',
    b"[" * 1500 + b"]" * 1500])
def test_signed_malformed_json_rejected(raw):
    with pytest.raises(SignedRequestError):
        verify(signed(raw=raw))


@pytest.mark.parametrize("changes", [{"algorithm": "hmac-sha256"}, {"algorithm": "HS256"}, {"algorithm": None},
    {"algorithm": True}, {"algorithm": []}, {"user_id": None}, {"user_id": 987654321}, {"user_id": True},
    {"user_id": "0"}, {"user_id": "01"}, {"user_id": "1" * 65}, {"user_id": " 987654321"}, {"user_id": "９８７"},
    {"user_id": "987654321\n"}, {"oauth_token": "fixture-hidden-token"}, {"code": "fixture-hidden-code"},
    {"app_id": "111"}, {"app_id": None}, {"app_id": 123456789}, {"app_id": "0123456789"}])
def test_signed_subject_algorithm_identity_and_unknown_fields_rejected(changes):
    with pytest.raises(SignedRequestError):
        verify(signed({"algorithm": "HMAC-SHA256", "user_id": SUBJECT, **changes}))


@pytest.mark.parametrize("field", ["algorithm", "user_id"])
def test_required_fields_are_explicit(field):
    payload = {"algorithm": "HMAC-SHA256", "user_id": SUBJECT}
    payload.pop(field)
    with pytest.raises(SignedRequestError):
        verify(signed(payload))


@pytest.mark.parametrize("name", ["issued_at", "expires"])
@pytest.mark.parametrize("value", [None, True, False, 0, -1, 1.5, "1291836800", float("nan"), float("inf"), MAX_TIMESTAMP + 1, [], {}])
def test_optional_timestamps_are_strict_and_bounded(name, value):
    with pytest.raises(SignedRequestError):
        verify(signed({"algorithm": "HMAC-SHA256", "user_id": SUBJECT, name: value}))


def test_timestamp_order_is_checked_without_freshness_claim():
    assert verify(signed({"algorithm": "HMAC-SHA256", "user_id": SUBJECT, "issued_at": 1, "expires": 2})).issued_at == 1
    assert verify(signed({"algorithm": "HMAC-SHA256", "user_id": SUBJECT, "expires": MAX_TIMESTAMP})).expires_at == MAX_TIMESTAMP
    with pytest.raises(SignedRequestError):
        verify(signed({"algorithm": "HMAC-SHA256", "user_id": SUBJECT, "issued_at": 2, "expires": 1}))


def test_decoded_payload_ceiling_is_enforced_with_valid_mac():
    minimal = b'{"algorithm":"HMAC-SHA256","user_id":"987654321"}'
    at_limit = minimal + b" " * (MAX_PAYLOAD_BYTES - len(minimal))
    assert verify(signed(raw=at_limit)).app_scoped_user_id == SUBJECT
    value = signed(raw=at_limit + b" ")
    assert len(value) < MAX_SIGNED_REQUEST_BYTES
    # Whitespace leaves the decoded JSON valid, so only the payload ceiling
    # rejects this otherwise authentic and well-shaped request.
    with pytest.raises(SignedRequestError):
        verify(value)


@pytest.mark.parametrize("changes", [{"expected_app_id": None}, {"expected_app_id": 123456789}, {"expected_app_id": "0"},
    {"expected_app_id": "01"}, {"expected_app_id": "123\n"}, {"app_secret": None}, {"app_secret": b"secret"},
    {"app_secret": ""}, {"app_secret": " "}, {"app_secret": "space secret"}, {"app_secret": "é"},
    {"app_secret": "x" * 257}, {"app_secret": "other-fixture-secret"}])
def test_injected_configuration_is_strict(changes):
    with pytest.raises(SignedRequestError):
        verify(signed(), **changes)


def test_representations_and_decoder_errors_hide_sensitive_material(caplog, capsys):
    value = signed()
    result = verify(value)
    for fragment in (value, SECRET, SUBJECT, APP):
        assert fragment not in repr(result)
    malformed = signed(raw=b'{"user_id":"987654321",')
    with pytest.raises(SignedRequestError) as caught:
        verify(malformed)
    error = caught.value
    assert error.code == "SIGNED_REQUEST_INVALID" and error.__context__ is None and error.__cause__ is None
    for fragment in (malformed, SECRET, SUBJECT, APP):
        assert fragment not in str(error) + repr(error) + repr(error.args) + caplog.text
    assert capsys.readouterr() == ("", "")


def test_parser_checks_mac_before_json(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unauthenticated JSON must not be parsed")
    monkeypatch.setattr("social.connections.signed_requests.json.loads", forbidden)
    with pytest.raises(SignedRequestError):
        verify(signed(secret="wrong-secret"))


def test_fingerprint_namespaces_expected_app_and_preserves_verbatim_payload():
    value = signed()
    first = verify(value)
    other = verify(value, expected_app_id="987123")
    assert first.payload_fingerprint != other.payload_fingerprint
    # Without app_id in the payload, namespace identity comes from the caller's
    # selected app secret; a MAC cannot discover the app's registered identity.
    assert other.app_id == "987123"

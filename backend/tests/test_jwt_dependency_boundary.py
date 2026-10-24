"""Exercise real token signatures and the replacement JWT library's boundaries."""

import base64
import hashlib
import hmac
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException

import supabase_auth as auth

SECRET = "inert-fixture-signing-secret-with-32-bytes"
SUBJECT = "11111111-1111-4111-8111-111111111111"


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def claims(**changes):
    return {
        "sub": SUBJECT,
        "aud": "authenticated",
        "exp": int(time.time()) + 300,
        **changes,
    }


def hmac_token(payload, algorithm="HS256", secret=SECRET.encode(), **headers):
    head = b64(json.dumps({"alg": algorithm, "typ": "JWT", **headers}).encode())
    body = b64(json.dumps(payload).encode())
    signed = f"{head}.{body}"
    digest = {"HS256": hashlib.sha256, "HS384": hashlib.sha384}[algorithm]
    return f"{signed}.{b64(hmac.new(secret, signed.encode(), digest).digest())}"


@pytest.fixture(params=["ES256", "RS256"])
def signing_key(request):
    import jwt

    algorithm = request.param
    private = (
        ec.generate_private_key(ec.SECP256R1())
        if algorithm == "ES256"
        else rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )
    implementation = (
        jwt.algorithms.ECAlgorithm
        if algorithm == "ES256"
        else jwt.algorithms.RSAAlgorithm
    )
    jwk = json.loads(implementation.to_jwk(private.public_key()))
    jwk.update(kid="fixture-key", alg=algorithm, use="sig", key_ops=["verify"])
    return algorithm, private, jwk


def signed_token(signing_key, payload=None):
    import jwt

    algorithm, private, _ = signing_key
    return jwt.encode(
        claims() if payload is None else payload,
        private,
        algorithm=algorithm,
        headers={"kid": "fixture-key"},
    )


def reject(token):
    with pytest.raises(HTTPException) as raised:
        auth._decode_supabase_jwt(token)
    assert raised.value.status_code == 401


def test_symmetric_jwks_key_cannot_enable_another_hmac_algorithm(monkeypatch):
    monkeypatch.setattr(
        auth,
        "_fetch_jwks",
        lambda **_: {
            "keys": [
                {
                    "kid": "fixture-key",
                    "kty": "oct",
                    "alg": "HS384",
                    "k": b64(SECRET.encode()),
                }
            ]
        },
    )
    reject(hmac_token(claims(), algorithm="HS384", kid="fixture-key"))


def test_legacy_hmac_uses_only_its_configured_secret(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(
        auth, "_fetch_jwks", lambda **_: pytest.fail("legacy HMAC must not fetch JWKS")
    )
    assert auth._decode_supabase_jwt(hmac_token(claims()))["sub"] == SUBJECT
    reject(hmac_token(claims(), secret=b"wrong-inert-secret"))


def test_unconfigured_hmac_is_rejected(monkeypatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    reject(hmac_token(claims()))


@pytest.mark.parametrize(
    "payload",
    [
        claims(aud="other-project"),
        claims(exp=1),
        claims(nbf=4102444800),
        claims(exp=None),
        claims(exp=[]),
        claims(exp=float("inf")),
        claims(exp=float("nan")),
        claims(sub=123),
    ],
)
def test_legacy_claim_validation_stays_enabled(monkeypatch, payload):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    reject(hmac_token(payload))


def test_supported_asymmetric_signature_and_audience(monkeypatch, signing_key):
    monkeypatch.setattr(auth, "_fetch_jwks", lambda **_: {"keys": [signing_key[2]]})
    assert auth._decode_supabase_jwt(signed_token(signing_key))["sub"] == SUBJECT
    reject(signed_token(signing_key, claims(aud="other-project")))
    reject(signed_token(signing_key, claims(exp=1)))


def test_jwk_algorithm_can_be_derived_from_key_type(monkeypatch, signing_key):
    jwk = dict(signing_key[2])
    jwk.pop("alg")
    monkeypatch.setattr(auth, "_fetch_jwks", lambda **_: {"keys": [jwk]})
    assert auth._decode_supabase_jwt(signed_token(signing_key))["sub"] == SUBJECT


def test_jwks_verification_rejects_private_key_material(monkeypatch, signing_key):
    import jwt

    algorithm, private, _ = signing_key
    implementation = (
        jwt.algorithms.ECAlgorithm
        if algorithm == "ES256"
        else jwt.algorithms.RSAAlgorithm
    )
    jwk = json.loads(implementation.to_jwk(private))
    jwk.update(kid="fixture-key", alg=algorithm, use="sig", key_ops=["verify"])
    monkeypatch.setattr(auth, "_fetch_jwks", lambda **_: {"keys": [jwk]})
    reject(signed_token(signing_key))


def test_asymmetric_payload_tampering_is_rejected(monkeypatch, signing_key):
    monkeypatch.setattr(auth, "_fetch_jwks", lambda **_: {"keys": [signing_key[2]]})
    parts = signed_token(signing_key).split(".")
    parts[1] = b64(
        json.dumps(claims(sub="22222222-2222-4222-8222-222222222222")).encode()
    )
    reject(".".join(parts))


def test_rotation_refresh_uses_the_new_matching_key(monkeypatch, signing_key):
    calls = []

    def fetch(*, force_refresh=False):
        calls.append(force_refresh)
        return {"keys": [signing_key[2]] if force_refresh else []}

    monkeypatch.setattr(auth, "_fetch_jwks", fetch)
    assert auth._decode_supabase_jwt(signed_token(signing_key))["sub"] == SUBJECT
    assert calls == [False, True]


@pytest.mark.parametrize(
    "changes",
    [
        {"alg": "HS256"},
        {"kty": "oct"},
        {"use": "enc"},
        {"key_ops": ["sign"]},
        {"key_ops": "verify"},
        {"key_ops": [None, "verify"]},
        {"kty": None},
    ],
)
def test_jwk_metadata_cannot_widen_algorithm_policy(monkeypatch, signing_key, changes):
    jwk = {**signing_key[2], **changes}
    monkeypatch.setattr(auth, "_fetch_jwks", lambda **_: {"keys": [jwk]})
    reject(signed_token(signing_key))


@pytest.mark.parametrize(
    "jwks", [None, [], {}, {"keys": None}, {"keys": {}}, {"keys": [None, True, []]}]
)
def test_malformed_jwks_is_not_an_authenticated_result(monkeypatch, signing_key, jwks):
    monkeypatch.setattr(auth, "_fetch_jwks", lambda **_: jwks)
    reject(signed_token(signing_key))


@pytest.mark.parametrize("token", ["", "bad", "a.b.c", None, True])
def test_malformed_tokens_fail_closed(token):
    reject(token)


def test_der_public_key_cannot_be_an_hmac_secret():
    import jwt
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    der = private.public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo
    )
    forged = hmac_token(claims(), secret=der)
    with pytest.raises(jwt.PyJWTError):
        jwt.decode(forged, der, algorithms=["HS256"], audience="authenticated")

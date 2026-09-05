"""The chain completer must refuse everything it cannot prove.

www.knbs.or.ke sends its leaf certificate without the intermediate that signs
it, so OpenSSL cannot build a path to a trusted root and the census download
fails. The fix fetches the missing issuers from the leaf's CA-Issuers pointer.

That pointer is a plain HTTP URL, and the only way Python can supply an extra
certificate — ``load_verify_locations(cadata=…)`` — makes it a trust ANCHOR.
So an unchecked fetch here would hand anyone who can answer that URL a way to
have their own certificates accepted for any site. Every test below is a way
that must fail; the one success case exists only to show the failures are not
vacuous.
"""

from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from seeding import tls_chain

NOW = datetime.now(timezone.utc)


def keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_cert(
    subject: str,
    issuer_name: str,
    issuer_key,
    *,
    ca: bool = True,
    not_before=None,
    not_after=None,
    key=None,
    aia: str | None = None,
):
    key = key or keypair()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_name)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before or NOW - timedelta(days=1))
        .not_valid_after(not_after or NOW + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    if aia:
        builder = builder.add_extension(
            x509.AuthorityInformationAccess(
                [
                    x509.AccessDescription(
                        x509.oid.AuthorityInformationAccessOID.CA_ISSUERS,
                        x509.UniformResourceIdentifier(aia),
                    )
                ]
            ),
            critical=False,
        )
    return builder.sign(issuer_key, hashes.SHA256()), key


@pytest.fixture()
def pki():
    """A tiny PKI: a trusted root, an intermediate, and a leaf under it."""
    root_key = keypair()
    root, _ = make_cert("Test Root", "Test Root", root_key, key=root_key)
    inter, inter_key = make_cert("Test Intermediate", "Test Root", root_key)
    leaf, _ = make_cert(
        "example.test", "Test Intermediate", inter_key, ca=False,
        aia="http://aia.test/inter.der",
    )
    roots = {root.subject.public_bytes(): root}
    return {"root": root, "roots": roots, "inter": inter, "leaf": leaf,
            "root_key": root_key, "inter_key": inter_key}


def serve(cert, monkeypatch):
    """Make the CA-Issuers URL return ``cert`` (or nothing)."""
    monkeypatch.setattr(tls_chain, "_fetch_der", lambda url: cert)


class TestItCompletesARealChain:
    def test_a_verifiable_intermediate_is_accepted(self, pki, monkeypatch):
        serve(pki["inter"], monkeypatch)

        chain = tls_chain.build_chain_to_a_trusted_root(pki["leaf"], pki["roots"])

        assert chain is not None
        assert [c.subject.rfc4514_string() for c in chain] == ["CN=Test Intermediate"]

    def test_a_leaf_already_under_a_trusted_root_needs_nothing(self, pki, monkeypatch):
        """No fetch at all when the issuer is already trusted."""
        direct, _ = make_cert(
            "example.test", "Test Root", pki["root_key"], ca=False
        )
        monkeypatch.setattr(
            tls_chain, "_fetch_der",
            lambda url: pytest.fail("should not have fetched anything"),
        )

        assert tls_chain.build_chain_to_a_trusted_root(direct, pki["roots"]) == []


class TestItRefuses:
    def test_a_certificate_signed_by_nobody_we_trust(self, pki, monkeypatch):
        """The attack this exists to stop: a rogue CA offered over HTTP."""
        rogue_key = keypair()
        rogue, _ = make_cert("Rogue CA", "Rogue Root", rogue_key)
        serve(rogue, monkeypatch)

        assert tls_chain.build_chain_to_a_trusted_root(pki["leaf"], pki["roots"]) is None

    def test_a_certificate_that_is_not_the_claimed_issuer(self, pki, monkeypatch):
        """CA-Issuers returning some other real CA must not be substituted."""
        other, _ = make_cert("Someone Else", "Test Root", pki["root_key"])
        serve(other, monkeypatch)

        assert tls_chain.build_chain_to_a_trusted_root(pki["leaf"], pki["roots"]) is None

    def test_a_certificate_that_did_not_actually_sign_the_leaf(self, pki, monkeypatch):
        """Right name, wrong key — the signature check is what catches it."""
        impostor, _ = make_cert("Test Intermediate", "Test Root", pki["root_key"])
        serve(impostor, monkeypatch)

        assert tls_chain.build_chain_to_a_trusted_root(pki["leaf"], pki["roots"]) is None

    def test_a_certificate_that_is_not_a_ca(self, pki, monkeypatch):
        not_a_ca, key = make_cert(
            "Test Intermediate", "Test Root", pki["root_key"], ca=False
        )
        leaf, _ = make_cert(
            "example.test", "Test Intermediate", key, ca=False,
            aia="http://aia.test/x.der",
        )
        serve(not_a_ca, monkeypatch)

        assert tls_chain.build_chain_to_a_trusted_root(leaf, pki["roots"]) is None

    def test_an_expired_certificate(self, pki, monkeypatch):
        expired, key = make_cert(
            "Test Intermediate", "Test Root", pki["root_key"],
            not_before=NOW - timedelta(days=800), not_after=NOW - timedelta(days=1),
        )
        leaf, _ = make_cert(
            "example.test", "Test Intermediate", key, ca=False,
            aia="http://aia.test/x.der",
        )
        serve(expired, monkeypatch)

        assert tls_chain.build_chain_to_a_trusted_root(leaf, pki["roots"]) is None

    def test_a_top_intermediate_the_root_did_not_sign(self, pki, monkeypatch):
        """The LAST hop needs checking too, not just the ones in between.

        A certificate can name a trusted root as its issuer and be signed by
        something else entirely. Without verifying that final signature the
        walk would accept a forged intermediate purely because it claimed the
        right parent — and everything below it would then be trusted.
        """
        rogue_key = keypair()
        forged, forged_key = make_cert(
            "Test Intermediate", "Test Root", rogue_key
        )
        leaf, _ = make_cert(
            "example.test", "Test Intermediate", forged_key, ca=False,
            aia="http://aia.test/x.der",
        )
        serve(forged, monkeypatch)

        assert tls_chain.build_chain_to_a_trusted_root(leaf, pki["roots"]) is None

    def test_a_leaf_that_names_no_issuer_to_fetch(self, pki):
        orphan, _ = make_cert("example.test", "Unknown CA", keypair(), ca=False)

        assert tls_chain.build_chain_to_a_trusted_root(orphan, pki["roots"]) is None

    def test_an_unreachable_ca_issuers_url(self, pki, monkeypatch):
        serve(None, monkeypatch)

        assert tls_chain.build_chain_to_a_trusted_root(pki["leaf"], pki["roots"]) is None

    def test_a_chain_that_never_reaches_a_root(self, pki, monkeypatch):
        """A pointer loop must not become an unbounded fetch."""
        # Self-issued and self-signed, so every check below the depth cap
        # passes and the walk would otherwise never terminate.
        loop_key = keypair()
        loop, _ = make_cert(
            "Loop CA", "Loop CA", loop_key, key=loop_key,
            aia="http://aia.test/loop.der",
        )
        leaf, _ = make_cert(
            "example.test", "Loop CA", loop_key, ca=False,
            aia="http://aia.test/loop.der",
        )
        calls = []

        def _fetch(url):
            calls.append(url)
            return loop

        monkeypatch.setattr(tls_chain, "_fetch_der", _fetch)

        assert tls_chain.build_chain_to_a_trusted_root(leaf, pki["roots"]) is None
        # An absolute bound, not MAX_AIA_DEPTH: asserting against the constant
        # would let the constant be raised to anything and still pass.
        assert len(calls) <= 10, f"followed {len(calls)} CA-Issuers hops"

    def test_no_context_is_built_when_the_chain_cannot_be_completed(
        self, pki, monkeypatch
    ):
        """Failure means the caller keeps its normal, verifying client."""
        monkeypatch.setattr(tls_chain, "leaf_certificate", lambda host, port=443: pki["leaf"])
        serve(None, monkeypatch)

        assert tls_chain.completed_ssl_context("example.test") is None


class TestScope:
    def test_only_declared_hosts_are_completed(self):
        assert tls_chain.needs_completion("https://www.knbs.or.ke/x.pdf")
        assert not tls_chain.needs_completion("https://www.treasury.go.ke/x.pdf")
        assert not tls_chain.needs_completion("https://evil.test/x.pdf")

    def test_a_lookalike_host_is_not_completed(self):
        """Substring matching would let knbs.or.ke.evil.test through."""
        assert not tls_chain.needs_completion("https://www.knbs.or.ke.evil.test/x")

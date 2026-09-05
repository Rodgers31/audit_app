"""Complete a TLS chain the publisher forgot to send.

THE PROBLEM
-----------
``www.knbs.or.ke`` presents ONLY its leaf certificate::

    0 s:/CN=knbs.or.ke
      i:/C=US/O=Let's Encrypt/CN=YE2

The YE2 intermediate that signs it is never sent, so a client has no path from
the leaf to a root it trusts. Browsers and macOS ``curl`` paper over this by
fetching the missing issuer from the leaf's Authority Information Access
extension; OpenSSL — and therefore httpx, and therefore this pipeline —
does not, and the download fails with::

    [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate

That is the publisher's misconfiguration, not a stale trust store: certifi
2026.06.17 already carries the ISRG root the intermediate chains to. It is
also not rare among the publishers this project reads, so the fix lives here
rather than in one domain.

WHY THIS IS SAFE
----------------
The AIA fetch is plain HTTP and therefore attacker-controllable, and Python's
only way to supply an extra certificate — ``load_verify_locations(cadata=…)``
— makes it a trust ANCHOR. Adding whatever that URL returns would hand an
attacker a way to have their own certificates accepted.

So nothing is trusted before it is checked. A fetched certificate is used only
if ALL of these hold:

1. It is a CA certificate (basicConstraints CA:TRUE).
2. It is currently within its validity window.
3. Its issuer is the subject of a root ALREADY in the trust store.
4. That root's public key actually verifies its signature.

After (3) and (4) the intermediate is one the trust store already vouches
for — it grants no authority that was not already there, which is the whole
point. Anything else is refused and the connection is left to fail.
"""

from __future__ import annotations

import logging
import ssl
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse

import certifi
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

logger = logging.getLogger("seeding.tls_chain")

#: Publishers known to send an incomplete chain. Kept explicit: this is a
#: workaround for a specific server's misconfiguration, not a blanket policy,
#: and every host here should be reported upstream and eventually removed.
INCOMPLETE_CHAIN_HOSTS = frozenset({"knbs.or.ke", "www.knbs.or.ke"})

#: The AIA fetch is a small DER file from a CA's own distribution point.
_MAX_CERT_BYTES = 16 * 1024
_FETCH_TIMEOUT = 20.0


def _load_roots() -> Dict[bytes, x509.Certificate]:
    """Trusted roots from certifi, indexed by subject."""
    roots: Dict[bytes, x509.Certificate] = {}
    with open(certifi.where(), "rb") as handle:
        for cert in x509.load_pem_x509_certificates(handle.read()):
            roots[cert.subject.public_bytes()] = cert
    return roots


def _signature_is_valid(child: x509.Certificate, issuer: x509.Certificate) -> bool:
    """Does ``issuer``'s key actually sign ``child``?"""
    key = issuer.public_key()
    try:
        if isinstance(key, rsa.RSAPublicKey):
            key.verify(
                child.signature,
                child.tbs_certificate_bytes,
                padding.PKCS1v15(),
                child.signature_hash_algorithm,
            )
        elif isinstance(key, ec.EllipticCurvePublicKey):
            key.verify(
                child.signature,
                child.tbs_certificate_bytes,
                ec.ECDSA(child.signature_hash_algorithm),
            )
        else:  # pragma: no cover - no other key type appears in a CA chain
            return False
    except (InvalidSignature, TypeError, ValueError):
        return False
    return True


def _is_usable_ca(cert: x509.Certificate) -> bool:
    """A CA certificate, currently valid. Anything else is refused."""
    try:
        constraints = cert.extensions.get_extension_for_class(
            x509.BasicConstraints
        ).value
    except x509.ExtensionNotFound:
        logger.warning("AIA certificate has no basicConstraints; refusing it")
        return False
    if not constraints.ca:
        logger.warning("AIA certificate is not a CA; refusing it")
        return False

    now = datetime.now(timezone.utc)
    if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
        logger.warning(
            "AIA certificate is outside its validity window (%s..%s); refusing it",
            cert.not_valid_before_utc, cert.not_valid_after_utc,
        )
        return False

    return True


#: How far to follow CA-Issuers before giving up. The real chain here is three
#: links (YE2 -> Root YE -> ISRG Root X2); a bound stops a loop or a hostile
#: pointer from turning this into an unbounded fetch.
MAX_AIA_DEPTH = 5


def build_chain_to_a_trusted_root(
    leaf: x509.Certificate, roots: Optional[Dict[bytes, x509.Certificate]] = None
) -> Optional[List[x509.Certificate]]:
    """The intermediates that connect ``leaf`` to a root already trusted.

    Returns None unless a COMPLETE path is built, every link of which is
    checked: each certificate must be a valid CA, must be the issuer it claims
    to be, and must actually have signed the certificate below it. The walk
    ends only at a root already in the trust store, which is what makes the
    result safe to add — see the module docstring.

    For knbs.or.ke that path is::

        leaf -> YE2 (Let's Encrypt) -> Root YE (ISRG) -> ISRG Root X2

    and ISRG Root X2 is in certifi, so nothing new is being trusted; the
    certificates in between are simply the ones the server should have sent.
    """
    roots = _load_roots() if roots is None else roots
    chain: List[x509.Certificate] = []
    current = leaf

    for _ in range(MAX_AIA_DEPTH):
        root = roots.get(current.issuer.public_bytes())
        if root is not None:
            if not _signature_is_valid(current, root):
                logger.warning(
                    "%s is not actually signed by the trusted root %s; "
                    "refusing the chain",
                    current.subject.rfc4514_string(),
                    root.subject.rfc4514_string(),
                )
                return None
            return chain  # every certificate below is verified

        urls = aia_urls(current)
        if not urls:
            logger.warning(
                "%s names no CA-Issuers and its issuer %s is not trusted",
                current.subject.rfc4514_string(),
                current.issuer.rfc4514_string(),
            )
            return None

        issuer = next(
            (c for c in (_fetch_der(u) for u in urls) if c is not None), None
        )
        if issuer is None:
            return None
        if issuer.subject.public_bytes() != current.issuer.public_bytes():
            logger.warning(
                "CA-Issuers returned %s, which is not the issuer %s claimed",
                issuer.subject.rfc4514_string(),
                current.subject.rfc4514_string(),
            )
            return None
        if not _is_usable_ca(issuer):
            return None
        if not _signature_is_valid(current, issuer):
            logger.warning(
                "%s did not sign %s; refusing the chain",
                issuer.subject.rfc4514_string(),
                current.subject.rfc4514_string(),
            )
            return None

        chain.append(issuer)
        current = issuer

    logger.warning("gave up after %d CA-Issuers hops", MAX_AIA_DEPTH)
    return None


def aia_urls(cert: x509.Certificate) -> List[str]:
    """The CA-Issuers URLs the certificate names, if any."""
    try:
        aia = cert.extensions.get_extension_for_class(
            x509.AuthorityInformationAccess
        ).value
    except x509.ExtensionNotFound:
        return []
    return [
        d.access_location.value
        for d in aia
        if d.access_method == x509.oid.AuthorityInformationAccessOID.CA_ISSUERS
        and isinstance(d.access_location, x509.UniformResourceIdentifier)
    ]


def _fetch_der(url: str) -> Optional[x509.Certificate]:
    import httpx

    try:
        response = httpx.get(url, timeout=_FETCH_TIMEOUT, follow_redirects=True)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - any failure means no completion
        logger.warning("could not fetch issuer from %s: %s", url, exc)
        return None
    raw = response.content[:_MAX_CERT_BYTES]
    for loader in (x509.load_der_x509_certificate, x509.load_pem_x509_certificate):
        try:
            return loader(raw)
        except Exception:  # noqa: BLE001 - try the other encoding
            continue
    logger.warning("%s did not return a certificate", url)
    return None


def leaf_certificate(host: str, port: int = 443) -> Optional[x509.Certificate]:
    """The leaf the host presents, fetched WITHOUT verifying it.

    Deliberately unverified: the certificate is not being trusted here, only
    read for the AIA pointer it carries. What comes back is checked by
    :func:`vouched_for_by_a_trusted_root` before it can affect anything.
    """
    context = ssl._create_unverified_context()  # noqa: SLF001
    try:
        import socket

        with socket.create_connection((host, port), timeout=_FETCH_TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                der = tls.getpeercert(binary_form=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read %s's certificate: %s", host, exc)
        return None
    return x509.load_der_x509_certificate(der) if der else None


def completed_ssl_context(host: str) -> Optional[ssl.SSLContext]:
    """A verifying context that can also chain ``host``'s incomplete reply.

    Returns None when nothing safe could be added, in which case the caller
    should use its normal context and let verification fail — a failed
    download is a recoverable, visible outcome; a weakened one is not.
    """
    leaf = leaf_certificate(host)
    if leaf is None:
        return None

    chain = build_chain_to_a_trusted_root(leaf)
    if not chain:
        return None

    context = ssl.create_default_context(cafile=certifi.where())
    context.load_verify_locations(
        cadata="".join(
            c.public_bytes(serialization.Encoding.PEM).decode() for c in chain
        )
    )
    logger.info(
        "completed %s's chain with %s (each link verified up to a trusted root)",
        host, ", ".join(c.subject.rfc4514_string() for c in chain),
    )
    return context


def needs_completion(url: str) -> bool:
    """Is this a host known to send an incomplete chain?"""
    host = (urlparse(url).hostname or "").lower()
    return host in INCOMPLETE_CHAIN_HOSTS

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

TRANSPORT AND TRUST
-------------------
Unverified AIA identifiers can select only two reviewed Let's Encrypt files,
retrieved over verified HTTPS with no redirects. Public DNS answers are checked
and pinned to the connection; DNS, reads and chain traversal share one deadline.
Both wire bytes and streamed certificate bytes are bounded before parsing.

Fetched certificates still require CA status, current validity, issuer identity
and signatures through to an existing certifi root. The eventual publisher
request uses ordinary OpenSSL chain and hostname verification. No incomplete
path is added to the context. This workaround remains limited to declared KNBS
hosts and fails closed when a publisher changes issuer distribution.
"""

from __future__ import annotations

import logging
import ssl
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlsplit

import certifi
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from . import issuer_transport

logger = logging.getLogger("seeding.tls_chain")

#: Publishers known to send an incomplete chain. Kept explicit: this is a
#: workaround for a specific server's misconfiguration, not a blanket policy,
#: and every host here should be reported upstream and eventually removed.
INCOMPLETE_CHAIN_HOSTS = frozenset({"knbs.or.ke", "www.knbs.or.ke"})

#: The AIA fetch is a small DER file from a CA's own distribution point.
_MAX_CERT_BYTES = issuer_transport.MAX_CERT_BYTES


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
    leaf: x509.Certificate, roots: Optional[Dict[bytes, x509.Certificate]] = None,
    *, deadline: Optional[float] = None,
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
    deadline = time.monotonic() + issuer_transport.MAX_SECONDS if deadline is None else deadline
    roots = _load_roots() if roots is None else roots
    chain: List[x509.Certificate] = []
    current = leaf
    visited: set[str] = set()

    for _ in range(MAX_AIA_DEPTH):
        try:
            issuer_transport.remaining(deadline)
        except issuer_transport.IssuerRefused:
            return None
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
            try:
                issuer_transport.remaining(deadline)
            except issuer_transport.IssuerRefused:
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

        issuer = None
        for url in urls:
            if url in visited:
                continue
            if len(visited) >= issuer_transport.MAX_FETCHES:
                return None
            visited.add(url)
            issuer = _fetch_der(url, deadline=deadline)
            if issuer is not None:
                break
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


def _fetch_der(url: str, *, deadline: Optional[float] = None) -> Optional[x509.Certificate]:
    deadline = time.monotonic() + issuer_transport.MAX_SECONDS if deadline is None else deadline
    try:
        raw = issuer_transport.fetch_issuer_bytes(url, deadline)
        for loader in (x509.load_der_x509_certificate, x509.load_pem_x509_certificate):
            try:
                return loader(raw)
            except ValueError:
                continue
    except Exception as exc:  # Any transport failure means no completion.
        # Untrusted URLs and transport exception strings can contain secrets.
        logger.warning("issuer retrieval refused (%s)", type(exc).__name__)
    return None


def leaf_certificate(host: str, port: int = 443, *, deadline: Optional[float] = None) -> Optional[x509.Certificate]:
    """Read only a declared publisher's leaf; it remains untrusted input."""
    if host not in INCOMPLETE_CHAIN_HOSTS or type(port) is not int or port != 443:
        return None
    deadline = time.monotonic() + issuer_transport.MAX_SECONDS if deadline is None else deadline
    context = ssl._create_unverified_context()  # Only inspect; never download content with it.
    try:
        with issuer_transport.connect_public(host, deadline) as sock:
            sock.settimeout(min(2.0, issuer_transport.remaining(deadline)))
            with context.wrap_socket(sock, server_hostname=host) as tls:
                issuer_transport.remaining(deadline)
                der = tls.getpeercert(binary_form=True)
        if der and len(der) <= _MAX_CERT_BYTES:
            return x509.load_der_x509_certificate(der)
    except Exception as exc:
        logger.warning("publisher leaf retrieval refused (%s)", type(exc).__name__)
    return None


def completed_ssl_context(host: str) -> Optional[ssl.SSLContext]:
    """A normal verifying context, augmented only with a completed trusted path."""
    if host not in INCOMPLETE_CHAIN_HOSTS:
        return None
    deadline = time.monotonic() + issuer_transport.MAX_SECONDS
    leaf = leaf_certificate(host, deadline=deadline)
    if leaf is None:
        return None
    chain = build_chain_to_a_trusted_root(leaf, deadline=deadline)
    if not chain:
        return None
    try:
        issuer_transport.remaining(deadline)
        context = ssl.create_default_context(cafile=certifi.where())
        # Python 3.13 enables partial chains by default. Added intermediates
        # supply missing links; ancestor constraints must still reach a root.
        context.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
        context.load_verify_locations(cadata="".join(
            c.public_bytes(serialization.Encoding.PEM).decode() for c in chain
        ))
        issuer_transport.remaining(deadline)
        return context
    except Exception as exc:
        logger.warning("chain completion refused (%s)", type(exc).__name__)
        return None


def needs_completion(url: str) -> bool:
    """Only canonical HTTPS publisher authorities use the workaround."""
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == 'https' and parsed.netloc.lower() in INCOMPLETE_CHAIN_HOSTS
                and not any(ord(c) <= 32 or ord(c) == 127 for c in url))
    except (ValueError, TypeError):
        return False


def verified_client(url: str, *, timeout, headers=None, follow_redirects=False):
    """Shared seeding/OpenData entry: failed completion keeps TLS verification."""
    import httpx

    context = completed_ssl_context(urlsplit(url).hostname) if needs_completion(url) else None
    return httpx.Client(verify=context if context is not None else True,
                        trust_env=False, timeout=timeout, headers=headers,
                        follow_redirects=follow_redirects)

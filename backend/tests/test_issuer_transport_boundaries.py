"""Issuer URLs are untrusted input, even when the returned certificate is valid."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import httpcore
import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from seeding import tls_chain

AIA = 'http://ye2.i.lencr.org/'
HTTPS = 'https://letsencrypt.org/certs/gen-y/int-ye2.der'


@pytest.fixture
def issuer_der():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Fixture issuer')])
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.DER))


@pytest.fixture
def transport(monkeypatch, issuer_der):
    """Bridge the old buffered transport and candidate streaming transport; no sockets."""
    state = {'calls': [], 'chunks': [issuer_der], 'status': 200, 'headers': [],
             'materialized': False, 'closed': False, 'consumed': 0}

    def old_get(url, **kwargs):
        state['calls'].append(url)
        if state['status'] == 302 and kwargs.get('follow_redirects'):
            state['calls'].append('http://127.0.0.1:9/refused-fixture')
        state['materialized'] = True
        return httpx.Response(200, content=b''.join(state['chunks']), request=httpx.Request('GET', url))

    class Response:
        @property
        def status(self): return state['status']
        @property
        def headers(self): return state['headers']
        def iter_stream(self):
            for chunk in state['chunks']:
                state['consumed'] += 1
                yield chunk

    class Pool:
        def __init__(self, **kwargs): state['pool_options'] = kwargs
        def __enter__(self): return self
        def __exit__(self, *args): state['closed'] = True
        @contextmanager
        def stream(self, method, url, **kwargs):
            state['calls'].append(url)
            try: yield Response()
            finally: state['closed'] = True

    monkeypatch.setattr(httpx, 'get', old_get)
    monkeypatch.setattr(httpcore, 'ConnectionPool', Pool)
    return state


@pytest.mark.parametrize('url', [
    'http://127.0.0.1:9/issuer', 'https://169.254.169.254/issuer',
    'https://evil.test/issuer', 'file:///tmp/issuer',
    'https://letsencrypt.org:444/certs/gen-y/int-ye2.der',
    'https://user:password@letsencrypt.org/certs/gen-y/int-ye2.der',
    HTTPS + '?redirect=private', HTTPS + '#fragment',
])
def test_unapproved_issuer_never_reaches_transport(url, transport):
    assert tls_chain._fetch_der(url) is None
    assert transport['calls'] == []


def test_legacy_aia_uses_only_the_reviewed_https_certificate(transport):
    assert tls_chain._fetch_der(AIA) is not None
    assert transport['calls'] == [HTTPS]
    assert transport['materialized'] is False


def test_redirect_is_refused_without_a_second_request(transport):
    transport['status'] = 302
    transport['headers'] = [(b'location', b'http://127.0.0.1:9/refused-fixture')]
    assert tls_chain._fetch_der(AIA) is None
    assert transport['calls'] == [HTTPS]
    assert transport['consumed'] == 0
    assert transport['closed']


@pytest.mark.parametrize('headers', [[], [(b'content-length', b'1')]])
def test_actual_stream_bytes_are_bounded_even_with_missing_or_false_length(transport, issuer_der, headers):
    transport['headers'] = headers
    transport['chunks'] = [issuer_der, b'x' * 16384, b'must not consume']
    assert tls_chain._fetch_der(AIA) is None
    assert transport['consumed'] == 2
    assert transport['materialized'] is False
    assert transport['closed']

"""Execute DNS admission, pinned sockets, parser streaming and elapsed budgets."""
import json
import socket
import ssl
import subprocess
import time
from types import SimpleNamespace

import httpcore
import pytest

from seeding import issuer_transport as transport, tls_chain
from test_issuer_transport_boundaries import AIA, HTTPS, issuer_der, transport as response_transport


@pytest.mark.parametrize('addresses', [
    ['127.0.0.1'], ['10.0.0.1'], ['169.254.169.254'], ['::1'], ['fe80::1'],
    ['::ffff:127.0.0.1'], ['224.0.0.1'], ['8.8.8.8', '192.168.1.1'], [],
    ['8.8.8.8'] * 17, ['not an address'],
])
def test_private_mixed_or_invalid_dns_never_connects(monkeypatch, addresses):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=json.dumps(addresses)))
    monkeypatch.setattr(socket, 'socket', lambda *a: pytest.fail('socket opened before DNS admission'))
    with pytest.raises((transport.IssuerRefused, ValueError)):
        transport.connect_public('letsencrypt.org', time.monotonic() + 1)


def test_connection_uses_admitted_numeric_address_without_reresolving(monkeypatch):
    calls, sockets = [], []
    def resolve(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout=b'["8.8.8.8", "9.9.9.9"]')
    class Socket:
        def __init__(self, *args): sockets.append(self); self.closed = False
        def settimeout(self, timeout): assert 0 < timeout <= 1
        def connect(self, address):
            self.address = address
            if address[0] == '8.8.8.8': raise ConnectionRefusedError('fixture')
        def close(self): self.closed = True
    monkeypatch.setattr(subprocess, 'run', resolve)
    monkeypatch.setattr(socket, 'socket', Socket)
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: pytest.fail('second DNS resolution'))
    result = transport.connect_public('letsencrypt.org', time.monotonic() + 1)
    try:
        assert len(calls) == 1 and calls[0][1]['env'] == {}
        assert result.address == ('9.9.9.9', 443) and sockets[0].closed
    finally: result.close()
    assert all(s.closed for s in sockets)


def test_stalled_dns_child_is_killed_and_reaped(monkeypatch):
    children = []
    original = subprocess.Popen
    def create(*args, **kwargs):
        child = original(*args, **kwargs); children.append(child); return child
    monkeypatch.setattr(subprocess, 'Popen', create)
    monkeypatch.setattr(transport, '_RESOLVE', 'import time; time.sleep(5)')
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        transport.connect_public('letsencrypt.org', started + .08)
    assert time.monotonic() - started < 1
    assert len(children) == 1 and children[0].poll() is not None


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), 0, True])
def test_invalid_deadline_denies_before_io(monkeypatch, value):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('invalid deadline reached DNS'))
    with pytest.raises(transport.IssuerRefused): transport.connect_public('letsencrypt.org', value)


class Socket:
    def __init__(self, chunks=()): self.chunks = iter(chunks); self.closed = False; self.timeouts = []
    def settimeout(self, timeout): self.timeouts.append(timeout)
    def recv(self, size): return next(self.chunks, b'')[:size]
    def send(self, buffer): return len(buffer)
    def close(self): self.closed = True


def test_drip_reads_share_a_deadline_instead_of_resetting_it(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(transport.time, 'monotonic', lambda: clock[0])
    class Drip(Socket):
        def recv(self, size): clock[0] += .4; return b'x'
    sock = Drip(); stream = transport._DeadlineStream(sock, 1)
    try:
        assert stream.read(65536) == b'x'
        assert stream.read(65536) == b'x'
        with pytest.raises(transport.IssuerRefused): stream.read(65536)
        assert sock.timeouts == pytest.approx([1, .6, .2])
    finally: stream.close()
    assert sock.closed


def test_oversize_headers_and_framing_are_also_bounded():
    sock = Socket([b'x' * 1024] * 34)
    stream = transport._DeadlineStream(sock, time.monotonic() + 1)
    try:
        for _ in range(32): stream.read(65536)
        with pytest.raises(transport.IssuerRefused): stream.read(65536)
        assert stream.received == 32769  # One extra byte detects overflow.
    finally: stream.close()


@pytest.mark.parametrize('mode', ['unverified', 'wrong_sni', 'tls_error'])
def test_tls_guard_and_handshake_failure_close_socket(mode):
    sock = Socket(); stream = transport._DeadlineStream(sock, time.monotonic() + 1)
    class Context:
        check_hostname = mode != 'unverified'
        verify_mode = ssl.CERT_REQUIRED if mode != 'unverified' else ssl.CERT_NONE
        def wrap_socket(self, *a, **kw): raise ssl.SSLError('inert handshake refusal')
    with pytest.raises((transport.IssuerRefused, ssl.SSLError)):
        stream.start_tls(Context(), server_hostname='evil.test' if mode == 'wrong_sni' else 'letsencrypt.org')
    assert sock.closed


@pytest.mark.parametrize('headers', [
    [(b'content-length', b'16385')], [(b'content-length', b'-1')],
    [(b'content-encoding', b'gzip')], [(b'content-encoding', b'br')],
    [(b'content-encoding', b'gzip'), (b'content-encoding', b'identity')],
    [(b'content-encoding', b'br'), (b'content-encoding', b'identity')],
])
def test_refused_headers_do_not_consume_body(response_transport, headers):
    response_transport['headers'] = headers
    assert tls_chain._fetch_der(AIA) is None
    assert response_transport['consumed'] == 0 and response_transport['closed']


def test_real_http_parser_streams_certificate_without_decoding(monkeypatch, issuer_der):
    # Real HTTP/1.1 parser and framing. Only the network backend is local.
    backend = httpcore.MockBackend([b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n',
        f'{len(issuer_der):x}\r\n'.encode() + issuer_der + b'\r\n0\r\n\r\n'])
    monkeypatch.setattr(transport, '_IssuerBackend', lambda deadline: backend)
    cert = tls_chain._fetch_der(AIA)
    assert cert is not None and cert.subject.rfc4514_string() == 'CN=Fixture issuer'


def test_many_aia_pointers_share_a_request_budget(monkeypatch):
    calls = []
    monkeypatch.setattr(tls_chain, 'aia_urls', lambda cert: [f'https://refused.test/{i}' for i in range(100)])
    monkeypatch.setattr(tls_chain, '_fetch_der', lambda url, **kw: calls.append((url, kw['deadline'])))
    leaf = SimpleNamespace(issuer=SimpleNamespace(public_bytes=lambda: b'unknown'))
    assert tls_chain.build_chain_to_a_trusted_root(leaf, roots={}) is None
    assert len(calls) == 5 and len({deadline for _, deadline in calls}) == 1


@pytest.mark.parametrize('url', ['http://www.knbs.or.ke/x', 'https://www.knbs.or.ke:444/x',
    'https://user@www.knbs.or.ke/x', 'https://www.knbs.or.ke.evil.test/x',
    'https://www.knbs.or.ke\n/x'])
def test_publisher_authority_refused_before_leaf_io(monkeypatch, url):
    monkeypatch.setattr(tls_chain, 'leaf_certificate', lambda *a, **kw: pytest.fail('unapproved leaf I/O'))
    assert not tls_chain.needs_completion(url)
    assert tls_chain.completed_ssl_context(url) is None


@pytest.mark.parametrize('completed', [None, ssl.create_default_context()])
def test_shared_client_always_verifies_tls_and_disables_ambient_proxies(monkeypatch, completed):
    import httpx
    calls = []
    monkeypatch.setattr(tls_chain, 'completed_ssl_context', lambda host: completed)
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: calls.append(kwargs) or kwargs)
    tls_chain.verified_client('https://www.knbs.or.ke/x', timeout=10)
    assert calls[0]['trust_env'] is False
    assert calls[0]['verify'] is (completed if completed is not None else True)

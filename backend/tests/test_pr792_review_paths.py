"""Actual HTTPcore and OpenSSL review controls, using owned loopback only.

These prove the supported dependency call shape and socket handshake deadlines.
They do not contact a publisher or certify hard real-time CPU/OS scheduling.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import socket
import ssl
import threading
import time

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from seeding import issuer_transport as transport, tls_chain


def _certificate(name, key, *, issuer=None, issuer_key=None, ca=False):
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(subject)
        .issuer_name(issuer.subject if issuer is not None else subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(True, False, False, False, False, ca, ca, False, False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(
            (issuer_key or key).public_key()), critical=False))
    if not ca:
        builder = builder.add_extension(x509.SubjectAlternativeName([
            x509.DNSName(name)]), critical=False)
    return builder.sign(issuer_key or key, hashes.SHA256())


@pytest.fixture
def owned_tls(tmp_path):
    root_key, leaf_key = (ec.generate_private_key(ec.SECP256R1()) for _ in range(2))
    root = _certificate('Owned review root', root_key, ca=True)
    leaf = _certificate('letsencrypt.org', leaf_key, issuer=root, issuer_key=root_key)
    cert_file, key_file = tmp_path / 'leaf.pem', tmp_path / 'leaf-key.pem'
    cert_file.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(cert_file, key_file)
    client = ssl.create_default_context(
        cadata=root.public_bytes(serialization.Encoding.PEM).decode())
    assert client.check_hostname and client.verify_mode == ssl.CERT_REQUIRED
    return server, client


@contextmanager
def _owned_server(context, *, drip=False):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    listener.settimeout(2)
    address = listener.getsockname()
    state = {'accepted': False, 'chunks': 0}
    stop = threading.Event()

    def serve():
        try:
            connection, _ = listener.accept()
            state['accepted'] = True
            with connection:
                connection.settimeout(2)
                if drip:
                    incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
                    peer = context.wrap_bio(incoming, outgoing, server_side=True)
                    incoming.write(connection.recv(65536))
                    try:
                        peer.do_handshake()
                    except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                        pass
                    wire = outgoing.read()
                    # Keep transport progress occurring well inside each socket
                    # timeout, while the complete handshake needs much longer.
                    for offset in range(0, len(wire), 7):
                        if stop.is_set():
                            break
                        connection.sendall(wire[offset:offset + 7])
                        state['chunks'] += 1
                        stop.wait(.015)
                else:
                    with context.wrap_socket(connection, server_side=True) as channel:
                        request = b''
                        while b'\r\n\r\n' not in request:
                            block = channel.recv(1024)
                            if not block:
                                break
                            request += block
                        state['request'] = request.split(b'\r\n', 1)[0]
                        channel.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n'
                            b'Connection: close\r\n\r\nca')
        except (OSError, ssl.SSLError):
            pass  # A deadline refusal normally closes the owned peer socket.
        finally:
            listener.close()

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        yield address, state
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=3)
        assert not thread.is_alive(), 'Owned TLS server did not stop'


def test_real_connection_pool_calls_backend_with_host_and_port(owned_tls, monkeypatch):
    server, client = owned_tls
    calls = []
    actual_connect_tcp = transport._IssuerBackend.connect_tcp

    def observe(self, *args, **kwargs):
        calls.append((args, kwargs))
        return actual_connect_tcp(self, *args, **kwargs)

    with _owned_server(server) as (address, state):
        def connect(host, deadline):
            assert host == 'letsencrypt.org'
            return socket.create_connection(address, timeout=1)

        monkeypatch.setattr(transport, 'connect_public', connect)
        monkeypatch.setattr(transport.ssl, 'create_default_context', lambda **kwargs: client)
        monkeypatch.setattr(transport._IssuerBackend, 'connect_tcp', observe)
        assert transport.fetch_issuer_bytes('http://ye2.i.lencr.org/',
            time.monotonic() + 1) == b'ca'
        assert len(calls) == 1
        args, kwargs = calls[0]
        assert not args and kwargs['host'] == 'letsencrypt.org' and kwargs['port'] == 443
        assert 'origin' not in kwargs
        assert state['accepted'] and state['request'] == b'GET /certs/gen-y/int-ye2.der HTTP/1.1'


@pytest.mark.parametrize('path', ['issuer', 'publisher_leaf'])
def test_real_tls_handshake_drips_do_not_reset_shared_deadline(owned_tls, monkeypatch, path):
    server, client = owned_tls
    with _owned_server(server, drip=True) as (address, state):
        def connect(host, deadline):
            assert host == ('letsencrypt.org' if path == 'issuer' else 'www.knbs.or.ke')
            return socket.create_connection(address, timeout=1)

        monkeypatch.setattr(transport, 'connect_public', connect)
        started = time.monotonic()
        deadline = started + .15
        if path == 'issuer':
            stream = transport._DeadlineStream(connect('letsencrypt.org', deadline), deadline)
            try:
                with pytest.raises((TimeoutError, ssl.SSLError, transport.IssuerRefused)):
                    stream.start_tls(client, server_hostname='letsencrypt.org')
            finally:
                stream.close()
        else:
            assert tls_chain.leaf_certificate('www.knbs.or.ke', deadline=deadline) is None
        elapsed = time.monotonic() - started
        # Scheduling slack is intentional: this distinguishes the shared .15s
        # budget from a reset 1–2s socket timeout, not strict real-time latency.
        assert .04 < elapsed < .8
        assert state['accepted'] and state['chunks'] >= 2

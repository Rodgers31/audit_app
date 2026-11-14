"""Treasury transport qualification for #868; no live requests or financial claims.

The retained incident reports certificate expiry, not a missing issuer. Preserve
ordinary OpenSSL verification and the health check's complete-transfer verdict.
Synthetic certificates below are test peers, never official-source acceptance.
"""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shlex
import shutil
import ssl
import subprocess
import threading
import time

import certifi
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest
import yaml

from seeding import issuer_transport, tls_chain
from seeding.config import SeedingSettings
from seeding.http_client import SeedingHttpClient


TREASURY = (
    ('Treasury Budget Books', '/budget-books/', True),
    ('Treasury Budget Policy Statement', '/budget-policy-statement/', False),
    ('Treasury BROP', '/budget-review-and-outlook-paper/', False),
)
HOST = 'www.treasury.go.ke'
REPO = Path(__file__).resolve().parents[2]


def _certificate(name, key, *, issuer=None, issuer_key=None, ca=False, expired=False):
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    builder = (
        x509.CertificateBuilder().subject_name(subject)
        .issuer_name(issuer.subject if issuer is not None else subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=3))
        .not_valid_after(now + timedelta(days=-1 if expired else 1))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(True, False, False, False, False, ca, ca, False, False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(
            (issuer_key or key).public_key()), critical=False)
    )
    if not ca:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
    return builder.sign(issuer_key or key, hashes.SHA256())


def _handshake(context, server):
    """Run the selected client's actual TLS context without opening a socket."""
    client_in, client_out, peer_in, peer_out = (ssl.MemoryBIO() for _ in range(4))
    client = context.wrap_bio(client_in, client_out, server_hostname=HOST)
    peer = server.wrap_bio(peer_in, peer_out, server_side=True)
    done = set()
    for _ in range(20):
        for label, endpoint in (('client', client), ('peer', peer)):
            if label not in done:
                try:
                    endpoint.do_handshake()
                    done.add(label)
                except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                    pass
        if client_out.pending:
            peer_in.write(client_out.read())
        if peer_out.pending:
            client_in.write(peer_out.read())
        if len(done) == 2:
            return
    raise AssertionError('fixture TLS handshake did not complete')


@pytest.mark.parametrize('path', [row[1] for row in TREASURY])
@pytest.mark.parametrize('failure,verify_code', [
    (None, None), ('leaf_expired', 10), ('issuer_expired', 10),
    ('wrong_hostname', 62), ('missing_issuer', 20), ('untrusted_root', None),
])
def test_treasury_client_requires_valid_chain_and_hostname(monkeypatch, tmp_path, path, failure, verify_code):
    # httpx consults these before certifi when trust_env=True. Own fixture trust.
    monkeypatch.delenv('SSL_CERT_FILE', raising=False)
    monkeypatch.delenv('SSL_CERT_DIR', raising=False)
    root_key, issuer_key, leaf_key = (ec.generate_private_key(ec.SECP256R1()) for _ in range(3))
    root = _certificate('Synthetic Treasury Test Root', root_key, ca=True)
    issuer = _certificate('Synthetic Treasury Test Issuer', issuer_key, issuer=root,
                          issuer_key=root_key, ca=True, expired=failure == 'issuer_expired')
    leaf = _certificate('wrong.invalid' if failure == 'wrong_hostname' else HOST,
                        leaf_key, issuer=issuer, issuer_key=issuer_key,
                        expired=failure == 'leaf_expired')
    pem = lambda cert: cert.public_bytes(serialization.Encoding.PEM)
    trusted_root = root
    if failure == 'untrusted_root':
        other_key = ec.generate_private_key(ec.SECP256R1())
        trusted_root = _certificate('Other Synthetic Test Root', other_key, ca=True)
    trust_file = tmp_path / 'roots.pem'
    trust_file.write_bytes(pem(trusted_root))
    monkeypatch.setattr(certifi, 'where', lambda: str(trust_file))

    def no_completion(*args, **kwargs):
        pytest.fail('Treasury must not use the KNBS issuer-completion path')

    monkeypatch.setattr(tls_chain, 'completed_ssl_context', no_completion)
    cert_file, key_file = tmp_path / 'peer.pem', tmp_path / 'peer-key.pem'
    cert_file.write_bytes(pem(leaf) + (b'' if failure == 'missing_issuer' else pem(issuer)))
    key_file.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(cert_file, key_file)

    with SeedingHttpClient(SeedingSettings()) as seeder:
        selected = seeder._client_for('https://' + HOST + path)
        assert selected is seeder._client
        # Inspect the context the real httpx transport would use, not a new test context.
        context = selected._transport._pool._ssl_context
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        if failure is None:
            _handshake(context, server)
        else:
            with pytest.raises(ssl.SSLCertVerificationError) as error:
                _handshake(context, server)
            if verify_code is not None:
                assert error.value.verify_code == verify_code


@pytest.mark.parametrize('host', ['treasury.go.ke', HOST])
def test_treasury_is_not_admitted_to_issuer_inspection(monkeypatch, host):
    def no_dns(*args, **kwargs):
        pytest.fail('unapproved publisher must be refused before DNS')
    monkeypatch.setattr(issuer_transport, '_public_addresses', no_dns)
    with pytest.raises(issuer_transport.IssuerRefused, match='unapproved certificate host'):
        issuer_transport.connect_public(host, time.monotonic() + 5)


@pytest.mark.parametrize('scheme', ['http', 'https'])
def test_sectigo_aia_is_not_an_approved_issuer_download(monkeypatch, scheme):
    def no_pool(*args, **kwargs):
        pytest.fail('unapproved issuer must be refused before network setup')
    monkeypatch.setattr(issuer_transport.httpcore, 'ConnectionPool', no_pool)
    with pytest.raises(issuer_transport.IssuerRefused, match='unapproved issuer URL'):
        issuer_transport.fetch_issuer_bytes(
            scheme + '://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt',
            time.monotonic() + 5,
        )


def _health_script(tmp_path, host=HOST):
    from seeding.source_plan import LEGACY_DOMAINS, SourcePlan, health_source_lines
    workflow = yaml.safe_load((REPO / '.github/workflows/seed.yml').read_text())
    step, = [s for s in workflow['jobs']['healthcheck']['steps']
             if s.get('name') == 'Check data source URLs']
    script = step['run']
    assert '${{' not in script
    assert 'HC_SOURCE_INVENTORY' in script
    # The source plan now owns the actual fetched URLs. BPS is a legacy
    # citation, not an acquisition endpoint; BROP is required pending-bill data.
    actual = [line.split('|') for line in health_source_lines(
        SourcePlan(LEGACY_DOMAINS, False, False),
        SeedingSettings(_env_file=None),
    ).splitlines()]
    for path in ('/budget-books/', '/budget-review-and-outlook-paper/'):
        assert any(row[1:3] == [f'https://{HOST}{path}', 'true'] for row in actual)
    assert not any(row[1] == f'https://{HOST}/budget-policy-statement/' for row in actual)
    # Controlled required/optional peers exercise the unchanged production
    # shell's full transfer/TLS verdicts through its actual inventory seam.
    inventory = '\n'.join(
        f'{name}|https://{host}{path}|{str(critical).lower()}'
        for name, path, critical in TREASURY
    )
    inventory_file = tmp_path / 'seed-health-inventory'
    inventory_file.write_text(inventory + '\n')
    inventory_file.chmod(0o600)
    return 'export RUNNER_TEMP=' + shlex.quote(str(tmp_path)) + '\n' + script


@pytest.mark.parametrize('curl_exit,outcome', [(0, '200'), (60, 'TLS certificate verification failed'),
                                            (18, 'incomplete response'), (28, 'timeout')])
def test_treasury_health_requires_successful_complete_transfer(tmp_path, curl_exit, outcome):
    """A misleading HTTP 200 must not hide certificate or body-transfer failure."""
    script = _health_script(tmp_path)
    curl = tmp_path / 'curl'
    curl.write_text('#!/bin/sh\nprintf "__CALL__\\n" >> "$CURL_CALLS"\n'
                    'printf "%s\\n" "$@" >> "$CURL_CALLS"\nprintf 200\nexit "$CURL_EXIT"\n')
    curl.chmod(0o700)
    outputs, calls = tmp_path / 'outputs', tmp_path / 'calls'
    result = subprocess.run(['/bin/bash', '-e', '-c', script], capture_output=True, text=True,
        timeout=20, env={'PATH': str(tmp_path) + ':/usr/bin:/bin', 'HOME': str(tmp_path),
            'LC_ALL': 'C', 'CURL_CALLS': str(calls), 'CURL_EXIT': str(curl_exit),
            'GITHUB_OUTPUT': str(outputs), 'GITHUB_STEP_SUMMARY': str(tmp_path / 'summary'),
            'HC_ATTEMPT_MAX_TIME': '1', 'HC_SOURCE_BUDGET': '15',
            'HC_JOB_BUDGET': '60', 'HC_RETRY_DELAY': '0'})
    assert result.returncode == 0, result.stdout + result.stderr
    output = outputs.read_text()
    assert 'unprobed=0\n' in output
    assert f'has_failures={str(curl_exit != 0).lower()}\n' in output
    assert f'critical_reachable={str(curl_exit == 0).lower()}\n' in output
    for name, path, critical in TREASURY:
        severity = 'OK' if curl_exit == 0 else ('CRITICAL' if critical else 'WARNING')
        assert f'{severity}|{name}|{outcome}\n' in output
    if curl_exit:
        assert '[OK]' not in result.stdout
    arguments = calls.read_text().splitlines()
    assert not any(arg == '--insecure' or
                   (arg.startswith('-') and not arg.startswith('--') and 'k' in arg)
                   for arg in arguments)
    assert set('https://' + HOST + path for _, path, _ in TREASURY).issubset(arguments)


@pytest.mark.parametrize('expired', [False, True], ids=['valid-peer', 'expired-peer'])
def test_health_curl_verifies_a_real_local_https_peer(tmp_path, expired):
    """Actual curl/OpenSSL execution catches verification bypass flags and aliases."""
    assert shutil.which('curl'), 'curl is required for this transport boundary'
    root_key, leaf_key = (ec.generate_private_key(ec.SECP256R1()) for _ in range(2))
    root = _certificate('Synthetic Health Root', root_key, ca=True)
    leaf = _certificate('localhost', leaf_key, issuer=root, issuer_key=root_key, expired=expired)
    root_file, peer_file, key_file = (tmp_path / name for name in ('root.pem', 'peer.pem', 'key.pem'))
    root_file.write_bytes(root.public_bytes(serialization.Encoding.PEM))
    peer_file.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            requests.append(self.path)
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'ok')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(peer_file, key_file)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output_file = tmp_path / 'outputs'
    try:
        result = subprocess.run(['/bin/bash', '-e', '-c', _health_script(tmp_path, f'localhost:{server.server_port}')],
            capture_output=True, text=True, timeout=20,
            env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(tmp_path),
                 'LC_ALL': 'C', 'CURL_CA_BUNDLE': str(root_file),
                 'GITHUB_OUTPUT': str(output_file), 'GITHUB_STEP_SUMMARY': str(tmp_path / 'summary'),
                 'HC_ATTEMPT_MAX_TIME': '1', 'HC_SOURCE_BUDGET': '15',
                 'HC_JOB_BUDGET': '60', 'HC_RETRY_DELAY': '0'})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert not thread.is_alive()
    assert result.returncode == 0, result.stdout + result.stderr
    output = output_file.read_text()
    assert 'unprobed=0\n' in output
    assert f'has_failures={str(expired).lower()}\n' in output
    assert f'critical_reachable={str(not expired).lower()}\n' in output
    assert sorted(requests) == ([] if expired else sorted(row[1] for row in TREASURY))
    for name, path, critical in TREASURY:
        severity = ('CRITICAL' if critical else 'WARNING') if expired else 'OK'
        outcome = 'TLS certificate verification failed' if expired else '200'
        assert f'{severity}|{name}|{outcome}\n' in output

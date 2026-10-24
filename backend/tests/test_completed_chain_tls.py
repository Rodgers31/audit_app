"""Real OpenSSL handshakes: completed chains still require trust and hostname."""
from datetime import datetime, timedelta, timezone
import ssl

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from seeding import tls_chain


def certificate(name, key, *, issuer=None, issuer_key=None, ca=False, constraints=None,
                path_length=None, expired=False):
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(subject)
        .issuer_name(issuer.subject if issuer is not None else subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=3))
        .not_valid_after(now + timedelta(days=-1 if expired else 1))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=path_length), critical=True)
        .add_extension(x509.KeyUsage(True, False, False, False, False, ca, ca, False, False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key((issuer_key or key).public_key()), critical=False))
    if constraints is not None:
        builder = builder.add_extension(constraints, critical=True)
    if not ca:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
        builder = builder.add_extension(x509.AuthorityInformationAccess([
            x509.AccessDescription(x509.oid.AuthorityInformationAccessOID.CA_ISSUERS,
                                  x509.UniformResourceIdentifier('http://ye2.i.lencr.org/'))]), critical=False)
    return builder.sign(issuer_key or key, hashes.SHA256())


def handshake(context, server, hostname):
    client_in, client_out, server_in, server_out = (ssl.MemoryBIO() for _ in range(4))
    client = context.wrap_bio(client_in, client_out, server_hostname=hostname)
    peer = server.wrap_bio(server_in, server_out, server_side=True)
    complete = set()
    for _ in range(20):
        for name, obj in [('client', client), ('server', peer)]:
            if name not in complete:
                try: obj.do_handshake(); complete.add(name)
                except (ssl.SSLWantReadError, ssl.SSLWantWriteError): pass
        if client_out.pending: server_in.write(client_out.read())
        if server_out.pending: client_in.write(server_out.read())
        if len(complete) == 2: return
    raise AssertionError('local TLS handshake did not complete')


@pytest.mark.parametrize('hostname,root_only,root_mode', [
    ('www.knbs.or.ke', False, None), ('wrong-host.invalid', False, None),
    ('www.knbs.or.ke', True, None), ('www.knbs.or.ke', False, 'name'),
    ('www.knbs.or.ke', False, 'path_length'), ('www.knbs.or.ke', False, 'expired'),
])
def test_completed_context_keeps_normal_openssl_verification(monkeypatch, tmp_path, hostname, root_only, root_mode):
    root_key, inter_key, leaf_key = (ec.generate_private_key(ec.SECP256R1()) for _ in range(3))
    root = certificate('Fixture Root', root_key, ca=True,
        constraints=x509.NameConstraints([x509.DNSName('allowed.invalid')], None) if root_mode == 'name' else None,
        path_length=0 if root_mode == 'path_length' else None, expired=root_mode == 'expired')
    inter = certificate('Fixture Issuer', inter_key, issuer=root, issuer_key=root_key, ca=True)
    leaf = certificate('www.knbs.or.ke', leaf_key, issuer=inter, issuer_key=inter_key)
    pem = lambda cert: cert.public_bytes(serialization.Encoding.PEM)
    real_context = ssl.create_default_context
    def fixture_trust(**kwargs):
        return real_context(cadata=pem(root).decode())
    monkeypatch.setattr(tls_chain.ssl, 'create_default_context', fixture_trust)
    monkeypatch.setattr(tls_chain, '_load_roots', lambda: {root.subject.public_bytes(): root})
    monkeypatch.setattr(tls_chain, 'leaf_certificate', lambda host, **kw: leaf)
    monkeypatch.setattr(tls_chain, '_fetch_der', lambda url, **kw: inter)
    context = tls_chain.completed_ssl_context('www.knbs.or.ke')
    assert context is not None and context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    if root_only: context = fixture_trust()
    cert_file, key_file = tmp_path / 'leaf.pem', tmp_path / 'leaf-key.pem'
    cert_file.write_bytes(pem(leaf))  # Server deliberately omits the intermediate.
    key_file.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(cert_file, key_file)
    if root_only or hostname != 'www.knbs.or.ke' or root_mode is not None:
        with pytest.raises(ssl.SSLCertVerificationError): handshake(context, server, hostname)
    else: handshake(context, server, hostname)

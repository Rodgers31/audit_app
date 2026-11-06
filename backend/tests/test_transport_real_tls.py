"""Actual TLS handshakes on an owned loopback server; verification stays on."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import ipaddress
import ssl
import threading
import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from seeding.http_client import SeedingHttpClient
from test_transport_recovery_contract import settings

@contextmanager
def server(tmp_path,case):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    now=datetime.now(timezone.utc)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'owned test CA')])
    ca=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=2)).not_valid_after(now+timedelta(days=2)).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(ca_key,hashes.SHA256())
    san=x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.2' if case=='hostname' else '127.0.0.1'))])
    cert=x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'owned localhost')])).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=2)).not_valid_after(now-timedelta(days=1) if case=='expired' else now+timedelta(days=1)).add_extension(san,critical=False).sign(ca_key,hashes.SHA256())
    cert_path=tmp_path/'server.pem'; key_path=tmp_path/'key.pem'; ca_path=tmp_path/'ca.pem'
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM));ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM));key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path);self.send_response(200);self.end_headers();self.wfile.write(b'%PDF-1.7\n%%EOF\n')
        def log_message(self,*args): pass
    owned=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert_path,key_path)
    owned.socket=context.wrap_socket(owned.socket,server_side=True)
    thread=threading.Thread(target=owned.serve_forever,daemon=True);thread.start()
    trust=ssl.create_default_context() if case=='chain' else ssl.create_default_context(cafile=str(ca_path))
    try:yield f'https://127.0.0.1:{owned.server_port}/source.pdf',trust,seen
    finally:
        owned.shutdown();owned.server_close();thread.join(timeout=2)
        assert not thread.is_alive()
        for path in (cert_path,key_path,ca_path):path.unlink()

@pytest.mark.parametrize('case',['hostname','expired','chain','valid'])
def test_actual_certificate_refusal_and_positive_control(tmp_path,case):
    with server(tmp_path,case) as (url,trust,seen):
        with SeedingHttpClient(settings(tmp_path),client=httpx.Client(verify=trust,trust_env=False)) as client:
            if case=='valid':
                assert client.download_to_file(url,tmp_path/'out.pdf',max_seconds=2)>0
                assert seen==['/source.pdf']
            else:
                with pytest.raises(httpx.ConnectError,match='CERTIFICATE_VERIFY_FAILED'):
                    client.download_to_file(url,tmp_path/'out.pdf',max_seconds=2,resume_part=tmp_path/'bad.part')
                assert seen==[]
                assert not (tmp_path/'bad.part').exists()
                assert not (tmp_path/'out.pdf').exists()

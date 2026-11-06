"""Verified TLS and real sockets in the test runner's offline namespace.

Only the DNS answer is replaced: the real httpx/httpcore client still connects,
performs hostname/certificate verification, and reads the HTTP stream. These
local editions are inert fixtures, never evidence of a publisher observation.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import ssl
import threading

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


@contextmanager
def official_peer(tmp_path, monkeypatch, *, host="www.oagkenya.go.ke", aliases=(), respond):
    """Owned TLS/HTTP endpoints; all other DNS answers refuse before connection."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Owned transport fixture")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName(host), x509.DNSName("cross-origin.invalid"),
            *[x509.DNSName(alias) for alias in aliases]]), critical=False)
        .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "peer.pem", tmp_path / "peer-key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_tls.load_cert_chain(cert_path, key_path)
    trust = ssl.create_default_context(cafile=str(cert_path))
    seen, foreign, lookups = [], [], []

    class Official(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            try:
                respond(self)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                pass  # The deadline/refusal controls intentionally close early.

        def log_message(self, *args):
            pass

    class Foreign(BaseHTTPRequestHandler):
        def do_GET(self):
            foreign.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.end_headers()
            self.wfile.write(b"%PDF-1.7\nOwned inert audit edition\n%%EOF")

        def log_message(self, *args):
            pass

    class OwnedServer(ThreadingHTTPServer):
        daemon_threads = False
        block_on_close = True

    official = OwnedServer(("127.0.0.1", 0), Official)
    other = OwnedServer(("127.0.0.1", 0), Foreign)
    internal = OwnedServer(("127.0.0.1", 0), Foreign)
    official.socket = server_tls.wrap_socket(official.socket, server_side=True)
    other.socket = server_tls.wrap_socket(other.socket, server_side=True)
    threads = [threading.Thread(target=s.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
               for s in (official, other, internal)]
    real_dns = socket.getaddrinfo

    def controlled_dns(name, port, *args, **kwargs):
        label = name.decode() if isinstance(name, bytes) else name
        lookups.append(label)
        if label in (host, *aliases) and port == 443:
            return real_dns("127.0.0.1", official.server_port, *args, **kwargs)
        if label == "cross-origin.invalid" and port == 443:
            return real_dns("127.0.0.1", other.server_port, *args, **kwargs)
        if label in ("127.0.0.1", "::1", "localhost"):
            return real_dns(name, port, *args, **kwargs)
        raise socket.gaierror(socket.EAI_NONAME, "non-fixture DNS refused")

    for thread in threads:
        thread.start()
    monkeypatch.setattr(socket, "getaddrinfo", controlled_dns)
    try:
        yield dict(trust=trust, seen=seen, foreign=foreign, lookups=lookups,
                   url=f"https://{host}", foreign_url="https://cross-origin.invalid/unsafe",
                   internal_url=f"http://127.0.0.1:{internal.server_port}/internal")
    finally:
        for server in (official, other, internal):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)
            if thread.is_alive():
                raise RuntimeError("Owned loopback server did not stop")
        cert_path.unlink()
        key_path.unlink()

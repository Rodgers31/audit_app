"""Inert TLS Graph/S3 endpoints on a Docker internal network. No public routing."""
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from functools import lru_cache
import json
import os
from pathlib import Path
import ssl
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from PIL import Image

R2 = 'a' * 32 + '.r2.cloudflarestorage.com'
ROOT = Path('/evidence')


def image_object():
    # Stable, incompressible pixels exercise a multi-MiB transfer, rather than
    # a tiny constructor/thumbnail workload. Neither pixels nor bytes leave the
    # internal fixture network.
    return Image.frombytes('RGB', (3000, 3000), hashlib.shake_256(b'b15-worker-image').digest(3000 * 3000 * 3))


@lru_cache(maxsize=1)
def image():
    buffer = BytesIO()
    image_object().save(buffer, format='JPEG')
    return buffer.getvalue()


class Endpoint(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    caption = 'Verified announcement'
    sequence = 777
    posts = {}

    def log_message(self, *_):
        pass  # URLs contain inert signed credentials; inventory below omits them.

    def respond(self, head=False):
        length = int(self.headers.get('Content-Length', '0'))
        if length > 11 * 1024 * 1024:
            self.send_error(413)
            return
        body = self.rfile.read(length)
        path = urlsplit(self.path).path
        request_id = uuid4().hex
        binding = dict(run_id=os.environ['B15_ENDPOINT_RUN_ID'], case=(ROOT / 'endpoint-case').read_text())
        delay = float((ROOT / 'endpoint-delay').read_text())
        print(json.dumps(dict(**binding, request_id=request_id, method=self.command, path=path, input_bytes=length,
                              started=time.monotonic())), flush=True)
        if self.command == 'POST':
            if (ROOT / 'provider-gated').exists():
                while not (ROOT / 'provider-release').exists():
                    time.sleep(0.02)
            time.sleep(delay)
        if self.headers['Host'] == R2:
            data = image()
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('ETag', '"' + hashlib.md5(data).hexdigest() + '"')
            self.send_header('x-amz-meta-sha256', hashlib.sha256(data).hexdigest())
            self.end_headers()
            if not head:
                self.wfile.write(data)
            output = len(data) if not head else 0
        else:
            form = parse_qs(body.decode()) if 'multipart' not in self.headers.get('Content-Type', '') else {}
            if self.headers['Host'] == 'auth.fixture.test' and path == '/rest/v1/profiles':
                value = [{'id': '11111111-1111-4111-8111-111111111111',
                          'email': 'operator@example.test', 'roles': ['admin']}]
            elif self.command == 'POST' and path.endswith('/feed'):
                Endpoint.sequence += 1
                identifier = '901_' + str(Endpoint.sequence)
                Endpoint.posts[identifier] = form.get('message', [''])[0]
                value = {'id': identifier}
            elif self.command == 'POST' and path.endswith('/photos'):
                value = {'id': '401'}
            elif self.command == 'GET' and path == '/v26.0/401':
                value = {'id': '401', 'from': {'id': '901'}}
            elif self.command == 'GET' and path.removeprefix('/v26.0/') in Endpoint.posts:
                identifier = path.removeprefix('/v26.0/')
                value = {'id': identifier, 'from': {'id': '901'}, 'is_published': True,
                         'is_hidden': False, 'privacy': {'value': 'EVERYONE'},
                         'message': Endpoint.posts[identifier],
                         'permalink_url': 'https://www.facebook.com/901/posts/' + identifier.split('_')[1] + '/',
                         'attachments': {'data': [{'target': {'id': '401'}}]}}
            else:
                self.send_error(400)
                raise RuntimeError('Unexpected inert Graph request: ' + self.command + ' ' + path)
            data = json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            output = len(data)
        print(json.dumps(dict(**binding, request_id=request_id, method=self.command, path=path, output_bytes=output,
                              completed=time.monotonic())), flush=True)

    def do_GET(self):
        self.respond()

    def do_POST(self):
        self.respond()

    def do_HEAD(self):
        self.respond(head=True)


def main():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'b15-worker-inert')])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('graph.facebook.com'),
                                                       x509.DNSName(R2), x509.DNSName('auth.fixture.test')]), critical=False)
            .sign(key, hashes.SHA256()))
    (ROOT / 'ca.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    private = Path('/tmp/inert-key.pem')
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                         serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ROOT / 'ca.pem', private)
    server = ThreadingHTTPServer(('0.0.0.0', 443), Endpoint)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print('INERT_ENDPOINT_READY', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()

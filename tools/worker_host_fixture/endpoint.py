"""Lean synthetic TLS endpoint; protocol class matches the qualified B27 helper.

Image/certificate generation runs beforehand in a short-lived preparation process.
The resident helper serves exactly those retained bytes using only the stdlib.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from functools import lru_cache
import json
import os
from pathlib import Path
import ssl
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

R2 = 'a' * 32 + '.r2.cloudflarestorage.com'
ROOT = Path('/evidence')


@lru_cache(maxsize=1)
def image():
    data = (ROOT / 'endpoint-image.jpg').read_bytes()
    if not 1024 * 1024 <= len(data) <= 11 * 1024 * 1024:
        raise RuntimeError('Actual prepared JPEG size outside fixture bounds')
    return data


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
    image()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ROOT / 'ca.pem', '/tmp/inert-key.pem')
    server = ThreadingHTTPServer(('127.0.0.4', 8443), Endpoint)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print('INERT_ENDPOINT_READY', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()

"""Lean synthetic TLS endpoint preserving the qualified B27 wire behavior.

Image/certificate generation runs beforehand in a short-lived preparation process.
The resident helper serves exactly those prepared bytes using only the stdlib.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

R2 = 'a' * 32 + '.r2.cloudflarestorage.com'
ROOT = Path('/evidence')


def image():
    data = (ROOT / 'endpoint-image.jpg').read_bytes()
    if not 1024 * 1024 <= len(data) <= 11 * 1024 * 1024:
        raise RuntimeError('Actual prepared JPEG size outside fixture bounds')
    return data


def serve_image(handler, *, head):
    if type(head) is not bool:
        raise ValueError('Explicit image response mode required')
    # Keep only small blocks beside the actual native download/inspection.
    # Hash the same opened file, rewind, and verify the bytes really written.
    with (ROOT / 'endpoint-image.jpg').open('rb') as stream:
        size, md5, sha = 0, hashlib.md5(), hashlib.sha256()
        while block := stream.read(16384):
            size += len(block)
            if size > 11 * 1024 ** 2:
                raise RuntimeError('Prepared JPEG exceeds fixture bound')
            md5.update(block); sha.update(block)
        if not 1024 ** 2 <= size <= 11 * 1024 ** 2:
            raise RuntimeError('Prepared JPEG outside fixture bound')
        handler.send_response(200)
        handler.send_header('Content-Length', str(size))
        handler.send_header('Content-Type', 'image/jpeg')
        handler.send_header('ETag', '"' + md5.hexdigest() + '"')
        handler.send_header('x-amz-meta-sha256', sha.hexdigest())
        handler.end_headers()
        if head:
            return 0
        stream.seek(0)
        sent, delivered = 0, hashlib.sha256()
        while block := stream.read(16384):
            if sent + len(block) > size:
                raise RuntimeError('Prepared JPEG changed during response')
            written = handler.wfile.write(block)
            if type(written) is not int or written != len(block):
                raise RuntimeError('Incomplete image response write')
            sent += len(block); delivered.update(block)
        if sent != size or delivered.digest() != sha.digest():
            raise RuntimeError('Prepared JPEG changed during response')
        return sent


class Endpoint(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    caption = 'Verified announcement'
    sequence = 777
    posts = {}

    def log_message(self, *_):
        pass  # URLs contain inert signed credentials; inventory below omits them.

    def respond(self, head=False):
        lengths = (self.headers.get_all('Content-Length', [])
                   if hasattr(self.headers, 'get_all') else
                   [self.headers['Content-Length']] if 'Content-Length' in self.headers else [])
        if ('Transfer-Encoding' in self.headers or len(lengths) > 1
                or (self.command == 'POST' and not lengths)):
            self.send_error(400)
            return
        declared = lengths[0] if lengths else '0'
        if (not declared or len(declared) > 16
                or any(character not in '0123456789' for character in declared)):
            self.send_error(400)
            return
        length = int(declared)
        if not 0 <= length <= 11 * 1024 * 1024:
            self.send_error(413)
            return
        if 'multipart' in self.headers.get('Content-Type', ''):
            # This synthetic Graph endpoint ignores multipart contents, as the
            # original helper did. Consume the identical actual SDK/TLS bytes
            # without keeping another whole image beside the real inspector.
            remaining = length
            while remaining:
                limit = min(65536, remaining)
                chunk = self.rfile.read(limit)
                if type(chunk) is not bytes or not 0 < len(chunk) <= limit:
                    raise RuntimeError('Incomplete bounded multipart input')
                remaining -= len(chunk)
            body = b''
        else:
            chunks = []
            remaining = length
            while remaining:
                limit = min(65536, remaining)
                chunk = self.rfile.read(limit)
                if type(chunk) is not bytes or not 0 < len(chunk) <= limit:
                    raise RuntimeError('Incomplete bounded form input')
                chunks.append(chunk)
                remaining -= len(chunk)
            body = b''.join(chunks)
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
            output = serve_image(self, head=head)
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

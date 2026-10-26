"""Exercise synthetic Graph framing on an owned loopback TLS server."""
import contextlib
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


class EndpointFramingTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            'framing_endpoint', Path(__file__).resolve().parents[1] / 'endpoint.py')
        self.endpoint = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.endpoint)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        (root / 'endpoint-case').write_text('framing')
        (root / 'endpoint-delay').write_text('0')
        self.image = b'x' * 1024**2
        (root / 'endpoint-image.jpg').write_bytes(self.image)
        self.stack.enter_context(patch.object(self.endpoint, 'ROOT', root))
        self.stack.enter_context(patch.dict('os.environ', B15_ENDPOINT_RUN_ID='framing'))
        self.events = self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(1)
                .not_valid_before(now - timedelta(minutes=1))
                .not_valid_after(now + timedelta(hours=1))
                .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), False)
                .sign(key, hashes.SHA256()))
        (root / 'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (root / 'key.pem').write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(root / 'cert.pem', root / 'key.pem')
        class Server(self.endpoint.ThreadingHTTPServer):
            daemon_threads = False
            def handle_error(self, *_):
                pass  # Refused EOF must close without a successful event.
        self.server = Server(('127.0.0.1', 0), self.endpoint.Endpoint)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01})
        thread.start()
        self.addCleanup(self.stop, thread)
        self.plain_server = Server(('127.0.0.1', 0), self.endpoint.Endpoint)
        plain_thread = threading.Thread(target=self.plain_server.serve_forever, kwargs={'poll_interval': .01})
        plain_thread.start()
        self.addCleanup(self.stop_plain, plain_thread)
        self.client_context = ssl.create_default_context(cafile=str(root / 'cert.pem'))

    def stop(self, thread):
        self.server.shutdown()
        self.server.server_close()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def stop_plain(self, thread):
        self.plain_server.shutdown()
        self.plain_server.server_close()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def request(self, method, path, body=b'', *, headers=None, host='graph.facebook.com', eof=False):
        fields = [('Host', host), ('Connection', 'close')]
        fields += headers if headers is not None else [('Content-Length', str(len(body))),
                    ('Content-Type', 'application/x-www-form-urlencoded')]
        wire = (f'{method} {path} HTTP/1.1\r\n' + ''.join(
            f'{key}: {value}\r\n' for key, value in fields) + '\r\n').encode() + body
        address = self.plain_server.server_address if eof else self.server.server_address
        with socket.create_connection(address, timeout=2) as raw:
            transport = contextlib.nullcontext(raw) if eof else self.client_context.wrap_socket(raw, server_hostname='localhost')
            with transport as client:
                client.settimeout(2)
                client.sendall(wire)
                if eof:
                    client.shutdown(socket.SHUT_WR)
                data = bytearray()
                while block := client.recv(65536):
                    data.extend(block)
                return bytes(data)

    def test_truncated_form_has_no_success_event_or_post_effect(self):
        response = self.request('POST', '/v26.0/901/feed', b'message=partial',
            headers=[('Content-Length', '99'), ('Content-Type', 'application/x-www-form-urlencoded')], eof=True)
        self.assertNotIn(b'200 OK', response)
        self.assertEqual(self.endpoint.Endpoint.posts, {})
        self.assertEqual(self.endpoint.Endpoint.sequence, 777)
        self.assertEqual(self.events.getvalue(), '')

    def test_invalid_framing_has_no_success_event_or_effect(self):
        for fields in ([('Content-Length', '-1')], [('Content-Length', 'bad')],
                       [('Content-Length', '1'), ('Content-Length', '1')],
                       [('Transfer-Encoding', 'chunked')],
                       [('Content-Length', '0'), ('Transfer-Encoding', 'chunked')],
                       [('Content-Length', str(11 * 1024**2 + 1))]):
            with self.subTest(fields=fields):
                self.endpoint.Endpoint.posts.clear()
                self.events.seek(0); self.events.truncate()
                response = self.request('POST', '/v26.0/901/feed', b'x', headers=fields)
                self.assertNotIn(b'200 OK', response)
                self.assertEqual(self.endpoint.Endpoint.posts, {})
                self.assertEqual(self.events.getvalue(), '')

    def test_valid_seven_route_tls_contract(self):
        def accepted(method, path, body=b'', **kwargs):
            response = self.request(method, path, body, **kwargs)
            self.assertIn(b'200 OK', response)
            return response.split(b'\r\n\r\n', 1)[1]
        profile = accepted('GET', '/rest/v1/profiles', host='auth.fixture.test')
        self.assertEqual(json.loads(profile)[0]['roles'], ['admin'])
        post = json.loads(accepted('POST', '/v26.0/901/feed', b'message=verified%20text'))['id']
        self.assertEqual(json.loads(accepted('GET', '/v26.0/' + post))['message'], 'verified text')
        self.assertEqual(json.loads(accepted('POST', '/v26.0/901/photos', b'--inert\r\n--inert--',
            headers=[('Content-Length', '18'), ('Content-Type', 'multipart/form-data; boundary=inert')])), {'id': '401'})
        self.assertEqual(json.loads(accepted('GET', '/v26.0/401'))['from']['id'], '901')
        self.assertEqual(accepted('HEAD', '/media/fixture.jpg', host=self.endpoint.R2), b'')
        self.assertEqual(accepted('GET', '/media/fixture.jpg', host=self.endpoint.R2), self.image)
        events = [json.loads(line) for line in self.events.getvalue().splitlines()]
        self.assertEqual(len(events), 14)

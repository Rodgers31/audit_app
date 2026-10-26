"""Transport controls, including true streamed reads and a private HTTP socket."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from services import peer_transport as peers


class Stream(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.read = 0
        self.closed = False
    def __iter__(self):
        for chunk in self.chunks:
            self.read += len(chunk)
            yield chunk
    def close(self):
        self.closed = True


def mock_stream(monkeypatch, *, chunks, headers=None, status=200):
    stream = Stream(chunks)
    requests = []
    real_client = httpx.Client
    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers=headers, stream=stream)
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(peers.httpx, 'Client', lambda **kw: real_client(transport=transport, **kw))
    return stream, requests


def test_valid_stream_reads_actual_json_and_closes(monkeypatch):
    stream, requests = mock_stream(monkeypatch, chunks=[b'{"value":', b'0}'])
    assert peers.read_json('https://fixture.invalid/') == {'value': 0}
    assert stream.closed and len(requests) == 1
    assert requests[0].headers['accept-encoding'] == 'identity'


@pytest.mark.parametrize('headers', [{'content-length': '1048577'}, {'content-length': '-1'},
    {'content-length': 'nan'}, {'content-length': '1, 2'}, {'content-encoding': 'gzip'},
    {'content-encoding': 'br'}, {'content-encoding': 'deflate'}])
def test_header_budget_refusal_precedes_body_read(monkeypatch, headers):
    stream, _ = mock_stream(monkeypatch, chunks=[b'{}'], headers=headers)
    with pytest.raises(ValueError, match='budget'):
        peers.read_json('https://fixture.invalid/')
    assert stream.read == 0 and stream.closed


@pytest.mark.parametrize('declared', [None, '1'])
def test_streaming_cap_does_not_trust_missing_or_false_length(monkeypatch, declared):
    headers = {} if declared is None else {'content-length': declared}
    stream, _ = mock_stream(monkeypatch, chunks=[b' ' * 16384] * 100, headers=headers)
    with pytest.raises(ValueError, match='byte budget'):
        peers.read_json('https://fixture.invalid/')
    assert stream.closed and stream.read == peers.MAX_BYTES + 16384


def test_redirect_is_not_followed(monkeypatch):
    stream, requests = mock_stream(monkeypatch, chunks=[], headers={'location': 'https://another.invalid/'}, status=302)
    with pytest.raises(httpx.HTTPStatusError):
        peers.read_json('https://fixture.invalid/')
    assert len(requests) == 1 and stream.closed


def test_shared_deadline_rejects_trickle_stream_with_fake_clock(monkeypatch):
    clock = [10.0]
    class Trickle(Stream):
        def __iter__(self):
            for part in (b'{', b'"x":', b'0}'):
                clock[0] += .6
                yield part
    stream = Trickle([])
    real_client = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
    monkeypatch.setattr(peers.httpx, 'Client', lambda **kw: real_client(transport=transport, **kw))
    monkeypatch.setattr(peers.time, 'monotonic', lambda: clock[0])
    token = peers.peer_deadline.set(11.0)
    try:
        with pytest.raises(httpx.ReadTimeout, match='time budget'):
            peers.read_json('https://fixture.invalid/')
        assert stream.closed
    finally:
        peers.peer_deadline.reset(token)


def test_private_loopback_socket_slow_headers_timeout_and_alive_control(monkeypatch):
    # OS sandbox has no external route; this binds only its private loopback.
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/slow': time.sleep(.15)
            try:
                body = b'{"alive":true}'
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except BrokenPipeError:
                pass  # Expected after the intentionally timed-out client closes.
        def log_message(self, *args): pass
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        assert peers.read_json(url + '/alive') == {'alive': True}
        monkeypatch.setattr(peers, 'READ_SECONDS', .04)
        started = time.monotonic()
        with pytest.raises(httpx.ReadTimeout):
            peers.read_json(url + '/slow')
        assert time.monotonic() - started < .12
        time.sleep(.16)
        assert peers.read_json(url + '/alive') == {'alive': True}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(1)


def test_trickle_deadline_stops_transport_before_fixed_size_buffer_fills(monkeypatch):
    clock = [10.0]
    reads = []
    class Trickle(httpx.SyncByteStream):
        def __iter__(self):
            for index in range(100):
                clock[0] += .25
                reads.append(index)
                yield b' '
    real_client = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=Trickle()))
    monkeypatch.setattr(peers.httpx, 'Client', lambda **kw: real_client(transport=transport, **kw))
    monkeypatch.setattr(peers.time, 'monotonic', lambda: clock[0])
    token = peers.peer_deadline.set(11.0)
    try:
        with pytest.raises(httpx.ReadTimeout):
            peers.read_json('https://fixture.invalid/')
    finally:
        peers.peer_deadline.reset(token)
    assert len(reads) <= 5, f'whole-response deadline consumed {len(reads)} chunks / {clock[0]-10}s before checking time'


def test_real_private_socket_trickle_stops_by_total_budget(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"independent":true}'
            self.send_response(200)
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            try:
                for byte in body:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(.025)
            except (BrokenPipeError,ConnectionResetError):
                pass
        def log_message(self,*args): pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    monkeypatch.setattr(peers,'READ_SECONDS',.2)
    token=peers.peer_deadline.set(time.monotonic()+.12)
    started=time.monotonic()
    try:
        with pytest.raises(httpx.ReadTimeout,match='time budget'):
            peers.read_json(f'http://127.0.0.1:{server.server_port}/')
        elapsed=time.monotonic()-started
        assert elapsed < .3, f'trickle consumed {elapsed:.3f}s with total budget .12s'
    finally:
        peers.peer_deadline.reset(token)
        server.shutdown()
        server.server_close()
        thread.join(1)

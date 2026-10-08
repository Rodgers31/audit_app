"""Disposable loopback CORS/PUT fixture, never a live acceptance runner.

Two private loopback servers live for at most 120 seconds. Grants are controlled
fixture tokens, not SigV4. The actual SDK/inspector/service acceptance controls
run in the media test lane. Nothing reads deployment configuration or credentials.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
import json
import threading
from urllib.parse import parse_qs, urlsplit

from social.media.cli import CLIInputError, PrivateArgumentParser, bounded_arguments

MAX_BODY = 512 * 1024
MAX_REQUESTS = 64


def image_bytes(kind):
    from PIL import Image
    output = BytesIO()
    Image.new('RGB', (64, 32), 'green').save(output, format=kind)
    return output.getvalue()


def fixture_page(object_origin, *, foreign=False):
    # Origins come only from sockets we bind, never from user/config input.
    return '''<!doctype html><meta charset="utf-8"><title>Local media acceptance fixture</title>
<h1>Local media acceptance fixture</h1><p>Loopback fake storage. No live acceptance or write settlement authority.</p>
<button id="run">Run local checks</button><pre id="result">Not run</pre>
<script>
const target = %s, foreign = %s;
document.getElementById('run').onclick = async () => {
  const checks = [];
  const record = (name, passed) => checks.push({name, passed});
  const put = (key, bytes, type, guard='*') => fetch(target + key + '?fixture_grant=controlled', {
    method:'PUT', credentials:'omit', redirect:'error', headers:{'Content-Type':type, 'If-None-Match':guard}, body:bytes});
  try {
    const png = await (await fetch('/png')).blob();
    if (foreign) {
      let denied = false;
      try { await put('/foreign', png, 'image/png'); } catch { denied = true; }
      record('foreign_origin_browser_denied', denied);
    } else {
      const jpeg = await (await fetch('/jpeg')).blob();
      record('png_create_visible', (await put('/png', new File([png], 'fixture.png', {type:'image/png'}), 'image/png')).status === 200);
      record('repeat_create_rejected', (await put('/png', png, 'image/png')).status === 412);
      record('changed_type_rejected', (await put('/type', png, 'image/jpeg')).status === 403);
      record('changed_length_rejected', (await put('/length', new Blob([png, 'x']), 'image/png')).status === 403);
      record('missing_create_guard_rejected', (await put('/guard', png, 'image/png', '')).status === 403);
      record('jpeg_create_visible', (await put('/jpeg', jpeg, 'image/jpeg')).status === 200);
      record('unsigned_access_denied', (await fetch(target + '/png', {credentials:'omit'})).status === 403);
      const read = await fetch(target + '/png?fixture_grant=controlled', {credentials:'omit'});
      record('private_get_visible_and_exact', read.status === 200 &&
        JSON.stringify(Array.from(new Uint8Array(await read.arrayBuffer()))) === JSON.stringify(Array.from(new Uint8Array(await png.arrayBuffer()))));
    }
  } catch { record('unexpected_fixture_error', false); }
  document.getElementById('result').textContent = JSON.stringify({evidence_scope:'local_browser_fixture_only', checks}, null, 2);
};
</script>''' % (json.dumps(object_origin), json.dumps(foreign))


@contextmanager
def browser_fixture():
    png, jpeg = image_bytes('PNG'), image_bytes('JPEG')
    objects, observations = {}, []
    origins = {}
    grants = {key: (len(jpeg), 'image/jpeg') if key == '/jpeg' else (len(png), 'image/png')
              for key in ('/png', '/jpeg', '/type', '/length', '/guard', '/foreign')}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *args): pass

        def reply(self, status, body=b'', mime='application/octet-stream', *, preflight=False):
            self.send_response(status)
            if self.headers.get_all('Origin') == [origins.get('app')]:
                self.send_header('Access-Control-Allow-Origin', origins['app'])
                self.send_header('Vary', 'Origin')
                if preflight:
                    self.send_header('Access-Control-Allow-Methods', 'GET, PUT')
                    self.send_header('Access-Control-Allow-Headers', 'content-type, if-none-match')
                    self.send_header('Access-Control-Max-Age', '0')
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def parse_request(self):
            if not super().parse_request():
                return False
            if len(observations) >= MAX_REQUESTS:
                self.reply(429)
                return False
            observations.append({'method': self.command, 'origin_allowed': self.headers.get_all('Origin') == [origins.get('app')]})
            return True

        def do_OPTIONS(self):
            header_fields = self.headers.get_all('Access-Control-Request-Headers', [])
            names = [name.strip().lower() for name in header_fields[0].split(',')] if len(header_fields) == 1 else []
            allowed = (self.headers.get_all('Origin') == [origins['app']]
                       and self.headers.get_all('Access-Control-Request-Method') in [['GET'], ['PUT']]
                       and len(header_fields) <= 1 and len(names) == len(set(names))
                       and set(names) <= {'content-type', 'if-none-match'})
            self.reply(204 if allowed else 403, preflight=allowed)

        def do_GET(self):
            parts = urlsplit(self.path)
            if self.server is app:
                if parts.path == '/png': self.reply(200, png, 'image/png')
                elif parts.path == '/jpeg': self.reply(200, jpeg, 'image/jpeg')
                elif parts.path == '/': self.reply(200, fixture_page(origins['objects']).encode(), 'text/html')
                elif parts.path == '/foreign': self.reply(200, fixture_page(origins['objects'], foreign=True).encode(), 'text/html')
                else: self.reply(404)
            elif parse_qs(parts.query) != {'fixture_grant': ['controlled']} or parts.path not in objects:
                self.reply(403)
            else: self.reply(200, objects[parts.path], grants[parts.path][1])

        def do_PUT(self):
            parts = urlsplit(self.path)
            expected = grants.get(parts.path)
            sizes = self.headers.get_all('Content-Length', [])
            if len(sizes) != 1 or not sizes[0].isdigit() or len(sizes[0]) > 8:
                self.reply(400)
                return
            size = int(sizes[0])
            if size > MAX_BODY:
                self.reply(413)
                return
            if (self.server is not storage or expected is None or parse_qs(parts.query) != {'fixture_grant': ['controlled']}
                    or self.headers.get_all('Origin', []) not in [[], [origins['app']]]
                    or self.headers.get_all('Content-Type') != [expected[1]]
                    or self.headers.get_all('If-None-Match') != ['*'] or size != expected[0]):
                self.reply(403)
                return
            body = self.rfile.read(size)
            if len(body) != size: self.reply(400)
            elif parts.path in objects: self.reply(412)
            else:
                objects[parts.path] = body
                self.reply(200)

    app = HTTPServer(('127.0.0.1', 0), Handler)
    storage = HTTPServer(('127.0.0.1', 0), Handler)
    origins.update(app='http://127.0.0.1:' + str(app.server_port), objects='http://127.0.0.1:' + str(storage.server_port))
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (app, storage)]
    for thread in threads: thread.start()
    try:
        yield origins, objects, observations
    finally:
        for server in (app, storage): server.shutdown(); server.server_close()
        for thread in threads: thread.join(timeout=4)


def main(argv=None):
    parser = PrivateArgumentParser(description='Disposable loopback browser fixtures only; no live storage/configuration is accepted.')
    parser.add_argument('--seconds', type=int, default=90, help='Lifetime from 1 to 120 seconds')
    try:
        args = parser.parse_args(bounded_arguments(argv))
    except CLIInputError:
        print(json.dumps({'error_code': 'MEDIA_FIXTURE_INPUT_REFUSED'}))
        return 2
    if not 1 <= args.seconds <= 120:
        print(json.dumps({'error_code': 'INVALID_FIXTURE_LIFETIME'}))
        return 2
    with browser_fixture() as (origins, objects, observations):
        foreign_origin = origins['app'].replace('127.0.0.1', 'localhost')
        print(json.dumps({'evidence_scope': 'local_browser_fixture_only', 'app_origin': origins['app'], 'foreign_fixture_origin': foreign_origin, 'foreign_fixture_path': '/foreign', 'expires_in_seconds': args.seconds}), flush=True)
        threading.Event().wait(args.seconds)
        print(json.dumps({'evidence_scope': 'local_browser_fixture_only', 'objects': len(objects), 'bytes': sum(map(len, objects.values())), 'requests': len(observations), 'probe_disposition': 'discarded_with_in_memory_fixture', 'live_acceptance': 'not_run', 'write_quiescence_proven': False}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

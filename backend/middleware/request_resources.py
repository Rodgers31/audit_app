"""ASGI ingress budgets before body decoding; no credentials or proxy trust."""
import asyncio
import codecs
import json
import math
from contextvars import ContextVar
from time import monotonic

from starlette.responses import JSONResponse

# PostDocument admits master + 25 overrides, each with 20k text, 35*2k
# media alt text and 50*100 hashtags. Worst escaped Unicode is about 31 MB.
# File bytes use direct private storage, not this API's JSON request body.
MAX_BODY_BYTES = 32 * 1024 * 1024
MAX_BUFFERED_BYTES = MAX_BODY_BYTES
MAX_QUERY_BYTES = 32 * 1024
MAX_HEADER_BYTES = 32 * 1024
MAX_INFLIGHT = 8
BODY_TIMEOUT = 10.0
REQUEST_TIMEOUT = 30.0
MAX_JSON_CONTAINERS = 2048
MAX_JSON_DEPTH = 64
MAX_JSON_SEPARATORS = 16384
HEALTH_PATHS = frozenset({'/health', '/health/live', '/health/ready'})
request_deadline = ContextVar('api_request_deadline', default=None)


def cheap_health(scope):
    return scope.get('method') in {'GET', 'HEAD'} and scope.get('path') in HEALTH_PATHS


def _non_utf8_json_lead(raw):
    """Recognize a decoded JSON opener after any allowed leading whitespace.

    Use the byte-encoding decision made by json.loads itself, then scan bounded
    decoded chunks. A fixed byte prefix cannot classify whitespace-padded
    UTF16/32. Non-JSON binary/multipart bodies retain their existing transport.
    """
    encoding = json.detect_encoding(raw)
    if encoding in {'utf-8','utf-8-sig'}:
        return False
    decoder = codecs.getincrementaldecoder(encoding)()
    try:
        for offset in range(0,len(raw),65536):
            for value in decoder.decode(memoryview(raw)[offset:offset+65536],final=False):
                if value not in ' \t\r\n':
                    return value in '{["'
        for value in decoder.decode(b'',final=True):
            if value not in ' \t\r\n':
                return value in '{["'
    except UnicodeError:
        # Invalidly encoded binary cannot be a valid JSON document for the
        # standard decoder. Its explicit non-JSON media path remains available.
        return False
    return False


class RequestRefused(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


class RequestResourceMiddleware:
    """Bound process admission and raw input while preserving signed bytes.

    These are process ceilings, not edge connection/DDoS controls. The server
    already parsed ASGI headers; its own header/connection/proxy budgets remain
    an operator boundary. Cancellation cannot terminate blocking Python work.
    """
    def __init__(self, app, *, max_body=MAX_BODY_BYTES, max_query=MAX_QUERY_BYTES,
                 max_headers=MAX_HEADER_BYTES, max_buffered=MAX_BUFFERED_BYTES,
                 max_inflight=MAX_INFLIGHT, body_timeout=BODY_TIMEOUT,
                 request_timeout=REQUEST_TIMEOUT, status=None,
                 max_json_containers=MAX_JSON_CONTAINERS, max_json_depth=MAX_JSON_DEPTH,
                 max_json_separators=MAX_JSON_SEPARATORS):
        if any(type(value) is not int or value < 1 for value in
               (max_body,max_query,max_headers,max_buffered,max_inflight,
                max_json_containers,max_json_depth,max_json_separators)):
            raise ValueError('Positive explicit request byte/admission limits required')
        if any(type(value) not in (int,float) or not math.isfinite(value) or value <= 0
               for value in (body_timeout,request_timeout)):
            raise ValueError('Positive finite request time budgets required')
        self.app = app
        self.max_body, self.max_query, self.max_headers = max_body, max_query, max_headers
        self.max_buffered, self.max_inflight = max_buffered, max_inflight
        self.body_timeout, self.request_timeout = body_timeout, request_timeout
        self.max_json_containers = max_json_containers
        self.max_json_depth = max_json_depth
        self.max_json_separators = max_json_separators
        self.inflight = self.buffered = 0
        self.status = status if status is not None else {}
        self.status.update(resource_guard=True, max_inflight=max_inflight,
                           max_body_bytes=max_body, max_buffered_bytes=max_buffered,
                           max_json_containers=max_json_containers, max_json_depth=max_json_depth,
                           max_json_separators=max_json_separators)

    def check_json_budget(self, raw, scope):
        # These signed ingress paths already retain their small 25k/64k raw
        # ceilings. Do not interpret/rewrite a provider's signed envelope here.
        if scope['path'].startswith('/api/v1/social/platform-events/') or scope['path'] in {
            '/api/v1/social/privacy/meta/data-deletion','/api/v1/social/privacy/meta/deauthorization'}:
            return
        mime = next((v.split(b';',1)[0].strip().lower() for k,v in scope.get('headers',[])
                     if k.lower()==b'content-type'), b'')
        start = 3 if raw[:3] == b'\xef\xbb\xbf' else 0
        while start < len(raw) and raw[start] in b' \t\r\n':
            start += 1
        encoded_json = _non_utf8_json_lead(raw)
        json_looking = start < len(raw) and raw[start] in b'{['
        if not (not mime or mime==b'application/json' or mime.endswith(b'+json') or json_looking or encoded_json):
            return
        # json.loads(bytes) auto-detects UTF16/32, including without BOM. Their
        # raw NULs must not bypass a UTF8 lexical scan. Escaped \\u0000 is valid.
        if 0 in raw:
            raise RequestRefused(415,'JSON_ENCODING_UNSUPPORTED')
        decoder = codecs.getincrementaldecoder('utf-8')()
        try:
            for offset in range(0,len(raw),65536):
                decoder.decode(memoryview(raw)[offset:offset+65536],final=False)
            decoder.decode(b'',final=True)
        except UnicodeError:
            raise RequestRefused(415,'JSON_ENCODING_UNSUPPORTED') from None
        containers = separators = depth = 0
        quoted = escaped = False
        for value in raw:
            if quoted:
                if escaped:
                    escaped = False
                elif value == 92:
                    escaped = True
                elif value == 34:
                    quoted = False
            elif value == 34:
                quoted = True
            elif value in (123,91):
                containers += 1
                depth += 1
                if containers > self.max_json_containers or depth > self.max_json_depth:
                    raise RequestRefused(413,'JSON_COMPLEXITY_EXCEEDED')
            elif value in (125,93):
                depth = max(0,depth-1)
            elif value in (44,58):
                separators += 1
                if separators > self.max_json_separators:
                    raise RequestRefused(413,'JSON_COMPLEXITY_EXCEEDED')

    def framing(self, scope):
        if len(scope.get('query_string', b'')) > self.max_query:
            raise RequestRefused(414, 'QUERY_TOO_LARGE')
        if len(scope.get('raw_path', scope['path'].encode())) > 8192:
            raise RequestRefused(414, 'PATH_TOO_LARGE')
        headers = scope.get('headers', [])
        if len(headers) > 100 or sum(len(k) + len(v) for k, v in headers) > self.max_headers:
            raise RequestRefused(431, 'HEADERS_TOO_LARGE')
        values = {}
        for name, value in headers:
            values.setdefault(name.lower(), []).append(value)
        lengths = values.get(b'content-length', [])
        transfers = values.get(b'transfer-encoding', [])
        encodings = values.get(b'content-encoding', [])
        if len(lengths) > 1 or len(transfers) > 1 or lengths and transfers:
            raise RequestRefused(400, 'AMBIGUOUS_BODY_FRAMING')
        if transfers and transfers[0].strip().lower() != b'chunked':
            raise RequestRefused(400, 'AMBIGUOUS_BODY_FRAMING')
        if len(encodings) > 1 or encodings and encodings[0].strip().lower() != b'identity':
            raise RequestRefused(415, 'CONTENT_ENCODING_UNSUPPORTED')
        length = None
        if lengths:
            raw = lengths[0]
            if not 1 <= len(raw) <= 10 or not raw.isdigit():
                raise RequestRefused(400, 'INVALID_CONTENT_LENGTH')
            length = int(raw)
            if length > self.max_body:
                raise RequestRefused(413, 'BODY_TOO_LARGE')
        return length

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        admitted = False
        held_bytes = 0
        started = False
        deadline_token = None
        async def tracked_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
            await send(message)
        try:
            declared = self.framing(scope)
            health = cheap_health(scope)
            if health and (declared not in (None, 0) or any(k.lower() == b'transfer-encoding' for k, _ in scope.get('headers', []))):
                raise RequestRefused(400, 'HEALTH_BODY_UNSUPPORTED')
            path = scope['path']
            body_limit = self.max_body
            if path.startswith(('/api/v1/admin/social/media/', '/api/v1/social/platform-events/')):
                body_limit = min(body_limit, 65536)
            if path in {'/api/v1/social/privacy/meta/data-deletion', '/api/v1/social/privacy/meta/deauthorization'}:
                body_limit = min(body_limit, 25000)
            if declared is not None and declared > body_limit:
                raise RequestRefused(413, 'BODY_TOO_LARGE')
            if not health:
                if self.inflight >= self.max_inflight:
                    raise RequestRefused(503, 'REQUEST_CAPACITY_EXCEEDED')
                self.inflight += 1
                admitted = True
            deadline = monotonic() + self.request_timeout
            deadline_token = request_deadline.set(deadline)
            # Read once before the application sees bytes. A false/absent
            # Content-Length cannot bypass either the byte or elapsed budget.
            buffered = bytearray()
            try:
                async with asyncio.timeout(self.body_timeout):
                    while True:
                        event = await receive()
                        if event['type'] == 'http.disconnect':
                            return
                        chunk = event.get('body', b'')
                        if health and chunk:
                            raise RequestRefused(400, 'HEALTH_BODY_UNSUPPORTED')
                        if len(buffered) + len(chunk) > body_limit:
                            raise RequestRefused(413, 'BODY_TOO_LARGE')
                        if self.buffered + len(chunk) > self.max_buffered:
                            raise RequestRefused(503, 'BODY_CAPACITY_EXCEEDED')
                        self.buffered += len(chunk)
                        held_bytes += len(chunk)
                        buffered.extend(chunk)
                        if not event.get('more_body', False):
                            break
            except TimeoutError:
                raise RequestRefused(408, 'BODY_READ_TIMEOUT') from None
            if declared is not None and declared != len(buffered):
                raise RequestRefused(400, 'BODY_LENGTH_MISMATCH')
            self.check_json_budget(buffered,scope)
            body = bytes(buffered)
            del buffered
            pending = True
            async def replay():
                nonlocal pending
                if pending:
                    pending = False
                    return {'type':'http.request', 'body':body, 'more_body':False}
                return await receive()
            try:
                async with asyncio.timeout(max(.001, deadline - monotonic())):
                    await self.app(scope, replay, tracked_send)
            except TimeoutError:
                if started:
                    # A partial response cannot be recertified as a successful
                    # complete body. Let the ASGI server close the transport.
                    raise
                raise RequestRefused(504, 'REQUEST_TIME_BUDGET_EXCEEDED') from None
        except RequestRefused as error:
            await JSONResponse({'detail':error.code}, status_code=error.status,
                headers={'Cache-Control':'no-store', **({'Retry-After':'1'} if error.status == 503 else {})})(scope, receive, send)
        finally:
            self.buffered -= held_bytes
            if admitted:
                self.inflight -= 1
            if deadline_token is not None:
                request_deadline.reset(deadline_token)

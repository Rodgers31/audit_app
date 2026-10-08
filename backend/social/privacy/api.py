"""Bounded data-deletion ingress only. Deauthorization has no verified wire contract."""
from urllib.parse import parse_qsl
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from ..http_boundary import SocialRoute
from ..service import SocialError
from .service import PrivacyService, invalid

DATA_PATH = '/api/v1/social/privacy/meta/data-deletion'
STATUS_PATH = DATA_PATH + '/status'
HEADERS = {'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer',
           'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'"}
MAX_BODY_BYTES = 25000  # Worst-case percent encoding of the 8192-byte verifier limit.


class PrivacyRoute(SocialRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            response = await original(request)
            response.headers.update(HEADERS)
            return response
        return handler


def create_privacy_router(service_dependency):
    if not callable(service_dependency):
        raise ValueError('Explicit privacy service dependency is required')
    router = APIRouter(route_class=PrivacyRoute, include_in_schema=False)

    async def get_service(svc=Depends(service_dependency)):
        if type(svc) is not PrivacyService:
            raise SocialError('PRIVACY_UNAVAILABLE', 'Privacy callbacks are unavailable.', 503)
        from urllib.parse import urlsplit
        if urlsplit(svc.config.status_url_base).path != STATUS_PATH:
            raise SocialError('PRIVACY_CONFIGURATION_INVALID', 'The exact status path is required.', 503)
        return svc

    @router.post(DATA_PATH)
    async def deletion(request: Request, svc=Depends(get_service)):
        if (request.scope.get('query_string', b'') or request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/x-www-form-urlencoded'
                or request.headers.get('content-encoding', 'identity').lower() != 'identity'):
            raise invalid()
        try:
            length = request.headers.get('content-length')
            if length is not None and (not length.isascii() or not length.isdecimal() or int(length) > MAX_BODY_BYTES):
                raise ValueError()
            content = bytearray()
            async for chunk in request.stream():
                if len(content) + len(chunk) > MAX_BODY_BYTES:
                    raise ValueError()
                content.extend(chunk)
            encoded = content.decode('ascii')
            # Reject malformed percent escapes before urllib's permissive decoder.
            import re
            if re.search(r'%(?![0-9a-fA-F]{2})', encoded):
                raise ValueError()
            fields = parse_qsl(encoded, keep_blank_values=True, strict_parsing=True, max_num_fields=2, encoding='ascii', errors='strict')
            if len(fields) != 1 or fields[0][0] != 'signed_request':
                raise ValueError()
        except (ValueError, UnicodeError):
            raise invalid() from None
        result = await run_in_threadpool(svc.receive, fields[0][1], kind='data_deletion')
        return JSONResponse(result, headers=HEADERS)

    @router.get(STATUS_PATH)
    async def status(request: Request, svc=Depends(get_service)):
        if len(request.scope.get('query_string', b'')) > 256:
            raise SocialError('NOT_FOUND', 'Request status was not found.', 404)
        fields = list(request.query_params.multi_items())
        if len(fields) != 1 or fields[0][0] != 'code':
            raise SocialError('NOT_FOUND', 'Request status was not found.', 404)
        result = await run_in_threadpool(svc.status, fields[0][1])
        return JSONResponse(result, headers=HEADERS)

    return router

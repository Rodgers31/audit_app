"""Unauthenticated provider ingress only stages ciphertext; exchange needs admin auth."""
import base64
import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from ..http_boundary import SocialRoute
from .api import Service
from .config import DIRECT_CALLBACK_PATH, DIRECT_LAUNCH_PATH, origin
from .direct_callback import DirectCallback, cookie_name, fields, refused

HEADERS = {'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
    'Content-Security-Policy': "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"}


def callback_html(flow_id, admin_origin):
    # Neither query data nor denial text is interpolated. The UUID is a hint,
    # never a bearer capability; completion revalidates the Supabase session.
    script = "history.replaceState(null,''," + json.dumps(DIRECT_CALLBACK_PATH) + ");"
    if flow_id is not None:
        message = json.dumps({'type': 'auditgava-meta-ready', 'flow_id': str(UUID(str(flow_id)))})
        script += "if(window.opener){window.opener.postMessage(" + message + ',' + json.dumps(admin_origin).replace('<', '\\u003c') + ");window.close();}"
    hashed = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    return HTMLResponse('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>AuditGava account connection</title><p role="status">Return to the Accounts window to finish this connection. If it is closed, use Recover account choices.</p><script>' + script + '</script></html>', headers=dict(HEADERS, **{'Content-Security-Policy': HEADERS['Content-Security-Policy'] + "; script-src 'sha256-" + hashed + "'"}))


class DirectRoute(SocialRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def private(request):
            response = await handler(request)
            for key, value in HEADERS.items():
                if key.lower() != 'content-security-policy' or key not in response.headers:
                    response.headers[key] = value
            # The global security middleware replaces response CSP. Keep only
            # this trusted route's policy for the outer private boundary.
            request.state.social_direct_callback_csp = response.headers['Content-Security-Policy']
            return response
        return private


router = APIRouter(prefix='/api/v1/social/oauth/meta', tags=['Meta OAuth callback'], route_class=DirectRoute)


def exact_target(request, expected):
    # No user-controlled forwarded header/origin becomes a redirect destination.
    if str(request.url).partition('?')[0] != expected:
        raise refused('REDIRECT_MISMATCH', 422)


@router.post('/launch', response_class=RedirectResponse)
async def launch(request: Request, svc: Service):
    callback = svc.config.require_direct()
    exact_target(request, origin(callback) + DIRECT_LAUNCH_PATH)
    if request.url.query or request.headers.get('content-type', '').lower() != 'application/x-www-form-urlencoded':
        raise refused()
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 1024:
            raise refused()
        raw.extend(chunk)
    value = fields(bytes(raw), {'flow_id', 'launch_token'}, 1024)
    if set(value) != {'flow_id', 'launch_token'}:
        raise refused()
    try:
        flow_id = UUID(value['flow_id'])
    except ValueError:
        raise refused() from None
    url, name, browser = await run_in_threadpool(DirectCallback(svc).launch, flow_id, value['launch_token'], request.headers.get('origin'))
    response = RedirectResponse(url, status_code=303, headers=HEADERS)
    response.set_cookie(name, browser, max_age=600, secure=True, httponly=True, samesite='lax', path='/')
    return response


@router.get('/callback', response_class=HTMLResponse)
def callback(request: Request, svc: Service):
    expected = svc.config.require_direct()
    exact_target(request, expected)
    flow_id = DirectCallback(svc).stage(request.scope['query_string'], request.cookies)
    response = callback_html(flow_id, svc.config.admin_origin)
    response.delete_cookie(cookie_name(flow_id), secure=True, httponly=True, samesite='lax', path='/')
    return response

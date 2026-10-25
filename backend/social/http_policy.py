"""Keep the entire social admin namespace out of intermediary/browser caches."""
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from uuid import uuid4

from .telemetry import log_event


def private_social_path(path):
    return (path == '/api/v1/admin/social' or path.startswith('/api/v1/admin/social/')
            or path == '/api/v1/social/oauth/meta' or path.startswith('/api/v1/social/oauth/meta/')
            or path == '/api/v1/social/privacy/meta' or path.startswith('/api/v1/social/privacy/meta/'))


def social_log_path(path):
    if not private_social_path(path):
        return path
    if path in {'/api/v1/social/privacy/meta/data-deletion',
                '/api/v1/social/privacy/meta/data-deletion/status'}:
        return path
    namespace = ('/api/v1/admin/social' if path.startswith('/api/v1/admin/social') else
                 '/api/v1/social/oauth/meta' if path.startswith('/api/v1/social/oauth/meta') else '/api/v1/social/privacy/meta')
    return namespace + '/[redacted]'


class SocialNoStoreMiddleware:
    """Also cover unmatched routes and outer security-middleware rejections."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        protected = private_social_path(path)
        if scope["type"] != "http" or not protected:
            await self.app(scope, receive, send)
            return

        response_started = False
        replaced_callback_error = False

        async def send_private(message):
            nonlocal response_started, replaced_callback_error
            if replaced_callback_error:
                return
            if message["type"] == "http.response.start":
                response_started = True
                if path.rstrip('/') == '/api/v1/social/oauth/meta/callback' and message['status'] != 200:
                    from .connections.direct_api import callback_html
                    fallback = callback_html(None, None)
                    # Slash normalization and outer middleware may otherwise
                    # redirect the original query before exact_target runs.
                    # A non-error status must still render the scrub document.
                    fallback.status_code = message['status'] if message['status'] >= 400 else 409
                    replaced_callback_error = True
                    await fallback(scope, receive, send)
                    return
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "private, no-store"
                if path.startswith('/api/v1/admin/social/connections/meta/direct/'):
                    headers['Referrer-Policy'] = 'no-referrer'
                if path == '/api/v1/social/oauth/meta' or path.startswith('/api/v1/social/oauth/meta/'):
                    from .connections.direct_api import HEADERS
                    for key, value in HEADERS.items():
                        headers[key] = (scope.get('state', {}).get('social_direct_callback_csp', value)
                                        if key == 'Content-Security-Policy' else value)
                if path == '/api/v1/social/privacy/meta' or path.startswith('/api/v1/social/privacy/meta/'):
                    from .privacy.api import HEADERS
                    # Apply after the global security middleware, including its
                    # early rejections and unmatched routes in this namespace.
                    headers.update(HEADERS)
            await send(message)

        try:
            await self.app(scope, receive, send_private)
        except Exception as error:
            # ServerErrorMiddleware is outside user middleware. Handle this
            # namespace before it emits an unprotected generic error response.
            request_id = scope.get("state", {}).get("social_request_id") or uuid4()
            log_event("social.request_failed", request_id=request_id,
                      error_code="SOCIAL_INTERNAL_ERROR", error_type=type(error).__name__)
            if response_started:
                raise  # Existing response headers are already private.
            response = JSONResponse(
                {"detail": {"code": "SOCIAL_INTERNAL_ERROR",
                            "message": "The social request failed. Use the request ID when contacting an administrator.",
                            "field_errors": [], "target_errors": [],
                            "retryable": False, "request_id": str(request_id)}},
                status_code=500,
                headers={"X-Request-ID": str(request_id)},
            )
            await response(scope, receive, send_private)

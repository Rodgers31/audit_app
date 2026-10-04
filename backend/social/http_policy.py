"""Keep the entire social admin namespace out of intermediary/browser caches."""
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from uuid import uuid4

from .telemetry import log_event


class SocialNoStoreMiddleware:
    """Also cover unmatched routes and outer security-middleware rejections."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        protected = path == "/api/v1/admin/social" or path.startswith(
            "/api/v1/admin/social/"
        )
        if scope["type"] != "http" or not protected:
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_private(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                MutableHeaders(scope=message)["Cache-Control"] = "private, no-store"
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

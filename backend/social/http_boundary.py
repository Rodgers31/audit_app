"""Shared admin identity, idempotency header and private social HTTP policy.

Feature routers import this boundary rather than importing one another.
"""
from typing import Annotated
from time import monotonic
from uuid import UUID, uuid4
from fastapi import Depends, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm.exc import StaleDataError
if __package__ == "backend.social":
    from ..database import get_db
    from ..supabase_auth import AdminUser, require_admin
else:
    from database import get_db
    from supabase_auth import AdminUser, require_admin
from .service import SocialError
from .telemetry import log_event

NO_STORE = {'Cache-Control': 'private, no-store'}

class SocialRoute(APIRoute):

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            started = monotonic()
            failure_code = None
            request_id = uuid4()
            request.state.social_request_id = request_id
            try:
                response = await original(request)
            except SocialError as error:
                failure_code = error.code
                response = JSONResponse(status_code=error.status, content={'detail': error.detail(request_id)})
            except (RequestValidationError, ValidationError) as invalid:
                fields = [{"code": "INVALID_FIELD", "field": ".".join(str(part) for part in error.get("loc", ())), "message": "This field is invalid or unsupported."} for error in invalid.errors()[:25]]
                error = SocialError('INVALID_REQUEST', 'Check the request fields, UUIDs and positive integer versions.', 422, field_errors=fields)
                failure_code = error.code
                response = JSONResponse(status_code=422, content={'detail': error.detail(request_id)})
            except HTTPException as error:
                code = 'AUTHENTICATION_REQUIRED' if error.status_code == 401 else 'PERMISSION_DENIED' if error.status_code == 403 else 'INVALID_REQUEST'
                safe = SocialError(code, 'Sign in with an administrator account.' if error.status_code in {401, 403} else 'The request could not be accepted.', error.status_code)
                failure_code = safe.code
                response = JSONResponse(status_code=error.status_code, content={'detail': safe.detail(request_id)}, headers=error.headers)
            except StaleDataError:
                error = SocialError('VERSION_CONFLICT', 'This record changed. Refresh before continuing.')
                failure_code = error.code
                response = JSONResponse(status_code=409, content={'detail': error.detail(request_id)})
            except IntegrityError:
                error = SocialError('VERSION_CONFLICT', 'A conflicting command already changed this record. Refresh before continuing.')
                failure_code = error.code
                response = JSONResponse(status_code=409, content={'detail': error.detail(request_id)})
            except DBAPIError as db_error:
                sqlstate = getattr(db_error.orig, 'pgcode', None) or getattr(db_error.orig, 'sqlstate', None)
                schema_missing = sqlstate in {'42P01', '42703'} or 'no such table: social_' in str(db_error.orig)
                error = SocialError('SOCIAL_SCHEMA_UNAVAILABLE' if schema_missing else 'SOCIAL_DATABASE_UNAVAILABLE', 'The social database schema is unavailable. Ask an administrator to verify the social migration.' if schema_missing else 'The social database is unavailable. Retry after service is restored.', 503, retryable=not schema_missing)
                failure_code = error.code
                log_event('social.request_failed', request_id=request_id, error_code=error.code, error_type=type(db_error).__name__)
                response = JSONResponse(status_code=503, content={'detail': error.detail(request_id)})
            except Exception as unexpected:
                failure_code = 'SOCIAL_INTERNAL_ERROR'
                log_event('social.request_failed', request_id=request_id, error_code='SOCIAL_INTERNAL_ERROR', error_type=type(unexpected).__name__)
                error = SocialError('SOCIAL_INTERNAL_ERROR', 'The social request failed. Use the request ID when contacting an administrator.', 500)
                response = JSONResponse(status_code=500, content={'detail': error.detail(request_id)})
            response.headers.update(NO_STORE)
            response.headers['X-Request-ID'] = str(request_id)
            # Use the static route template and validated identities. Never
            # serialize request URLs, query strings, bodies or exception text.
            identities = {}
            for name in ('post_id', 'target_id', 'account_id', 'asset_id', 'flow_id'):
                try:
                    identities[name] = UUID(str(request.path_params[name]))
                except (KeyError, ValueError, TypeError):
                    pass
            log_event('social.http_completed', request_id=request_id,
                      operation=request.method + ' ' + self.path,
                      duration_ms=max(0, int((monotonic() - started) * 1000)),
                      result=response.status_code, error_code=failure_code,
                      **identities)
            return response
        return handler
def social_admin(admin: AdminUser = Depends(require_admin)):
    try:
        UUID(admin.id)
    except (TypeError, ValueError, AttributeError):
        raise SocialError("PERMISSION_DENIED", "The administrator identity must be a valid UUID.", 403) from None
    return admin


IdempotencyKey = Annotated[UUID, Header(alias='Idempotency-Key')]

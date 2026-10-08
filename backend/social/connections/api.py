"""Authenticated server exchange: browser relays only a short-lived code/state.

The redirect lands on a same-origin frontend callback that removes the query
before rendering, then calls this API with its existing Supabase bearer token.
The verified session_id, rather than a rotating access token or client value,
binds both stages. No bearer-token cookie/CORS relaxation is required.
"""
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

if __package__ == 'backend.social.connections':
    from ...database import get_db
    from ...supabase_auth import AdminUser
else:
    from database import get_db
    from supabase_auth import AdminUser
from ..http_boundary import IdempotencyKey, NO_STORE, SocialRoute, social_admin
from ..service import SocialError
from .config import load_config
from .contracts import AccountCommand, AccountHealth, CompleteCommand, ConnectionStatus, DiscoveredFlow, SelectCommand, SelectedAccounts, StartCommand, StartedFlow
from .service import ConnectionService, session_binding


@dataclass(frozen=True)
class AdminSession:
    actor: UUID
    binding: str


def admin_session(admin: AdminUser = Depends(social_admin)):
    # get_current_user populates session_id only after Supabase signature/audience
    # verification. It is never read from a request body or unverified JWT.
    try:
        actor = UUID(admin.id)
        session_id = UUID(getattr(admin, 'session_id', None))
    except (ValueError, TypeError, AttributeError):
        raise SocialError('ADMIN_SESSION_REQUIRED', 'Sign in again with a current administrator session before connecting accounts.', 401) from None
    return AdminSession(actor, session_binding(actor, session_id))


def service(request: Request, db: Session = Depends(get_db)):
    from ..worker.native_runtime import registered_adapters
    from ..privacy.runtime import registered_ownership
    return ConnectionService(db, load_config(), available_adapters=registered_adapters(request), ownership_recorder=registered_ownership(request))


router = APIRouter(prefix='/api/v1/admin/social', tags=['Admin Social Connections'], route_class=SocialRoute, dependencies=[Depends(social_admin)])
Service = Annotated[ConnectionService, Depends(service)]
Identity = Annotated[AdminSession, Depends(admin_session)]


def command_response(request, value):
    dto = request.scope['route'].response_model.model_validate(value)
    return JSONResponse(content=dto.model_dump(mode='json'), headers=NO_STORE)


def args(request, identity, key, body):
    return identity.actor, identity.binding, request.method + ' ' + request.url.path, key, body, request.state.social_request_id


@router.get('/connections/meta/status', response_model=ConnectionStatus)
def status(svc: Service):
    return svc.status()


@router.post('/connections/meta/start', response_model=StartedFlow)
def start(request: Request, body: StartCommand, svc: Service, identity: Identity, key: IdempotencyKey):
    return command_response(request, svc.start(*args(request, identity, key, body)))


@router.post('/connections/meta/complete', response_model=DiscoveredFlow)
def complete(request: Request, body: CompleteCommand, svc: Service, identity: Identity, key: IdempotencyKey):
    return command_response(request, svc.complete(*args(request, identity, key, body)))


@router.get('/connections/meta/flows/{flow_id}', response_model=DiscoveredFlow)
def choices(flow_id: UUID, svc: Service, identity: Identity):
    return svc.discovery(flow_id, identity.actor, identity.binding)


@router.post('/connections/meta/flows/{flow_id}/select', response_model=SelectedAccounts)
def select(flow_id: UUID, request: Request, body: SelectCommand, svc: Service, identity: Identity, key: IdempotencyKey):
    return command_response(request, svc.select(flow_id, *args(request, identity, key, body)))


@router.get('/accounts/{account_id}/health', response_model=AccountHealth)
def health(account_id: UUID, svc: Service):
    return svc.health(account_id)


@router.post('/accounts/{account_id}/disconnect', response_model=AccountHealth)
def disconnect(account_id: UUID, request: Request, body: AccountCommand, svc: Service, identity: Identity, key: IdempotencyKey):
    return command_response(request, svc.account_command(account_id, *args(request, identity, key, body)))


@router.post('/accounts/{account_id}/rotate-key', response_model=AccountHealth)
def rotate(account_id: UUID, request: Request, body: AccountCommand, svc: Service, identity: Identity, key: IdempotencyKey):
    return command_response(request, svc.account_command(account_id, *args(request, identity, key, body), rotate=True))

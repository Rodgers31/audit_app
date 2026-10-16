"""Admin/session-bound API, explicit runtime composition, no secret responses."""
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

if __package__ == 'backend.social.platform_connections':
    from ...database import get_db
else:
    from database import get_db
from ..connections.api import AdminSession, admin_session, command_response, args
from ..connections.contracts import AccountCommand, CompleteCommand, StartCommand, StartedFlow
from ..http_boundary import IdempotencyKey, SocialRoute, social_admin
from ..service import SocialError
from .config import ConnectionConfig
from .contracts import ConfirmCommand, ConnectedAccount, ConnectionChoice, CredentialHealth, CreatorSettingsResponse, PlatformConnectionStatus
from .service import PlatformConnectionService

Provider = Literal['threads', 'x', 'tiktok']


def service(provider: Provider, request: Request, db: Session = Depends(get_db)):
    configurations = getattr(request.app.state, 'social_platform_connections_config', {})
    config = configurations.get(provider, ConnectionConfig(platform=provider))
    if not isinstance(config, ConnectionConfig) or config.platform != provider:
        raise SocialError('CONNECTIONS_UNAVAILABLE', 'The provider composition is invalid.', 503)
    from ..worker.native_runtime import registered_adapters
    return PlatformConnectionService(db, config, available_adapters=registered_adapters(request))


router = APIRouter(prefix='/api/v1/admin/social/platform-connections', tags=['Admin Social Platform Connections'], route_class=SocialRoute, dependencies=[Depends(social_admin)])
Service = Annotated[PlatformConnectionService, Depends(service)]
Identity = Annotated[AdminSession, Depends(admin_session)]


@router.get('/{provider}/status', response_model=PlatformConnectionStatus)
def status(provider: Provider, svc: Service):
    return svc.status()


@router.post('/{provider}/start', response_model=StartedFlow)
def start(provider: Provider, request: Request, body: StartCommand, svc: Service, identity: Identity, key: IdempotencyKey):
    return command_response(request, svc.start(*args(request, identity, key, body)))


@router.post('/{provider}/complete', response_model=ConnectionChoice)
def complete(provider: Provider, request: Request, body: CompleteCommand, svc: Service, identity: Identity, key: IdempotencyKey):
    return command_response(request, svc.complete(*args(request, identity, key, body)))


@router.get('/{provider}/flows/{flow_id}', response_model=ConnectionChoice)
def choice(provider: Provider, flow_id: UUID, svc: Service, identity: Identity):
    return svc.choice(flow_id, identity.actor, identity.binding)


@router.post('/{provider}/flows/{flow_id}/confirm', response_model=ConnectedAccount)
def confirm(provider: Provider, flow_id: UUID, request: Request, body: ConfirmCommand, svc: Service, identity: Identity, key: IdempotencyKey):
    return command_response(request, svc.confirm(flow_id, *args(request, identity, key, body)))


@router.get('/{provider}/accounts/{account_id}/health', response_model=CredentialHealth)
def health(provider: Provider, account_id: UUID, svc: Service):
    return svc.health(account_id)


@router.get('/{provider}/accounts/{account_id}/creator-settings', response_model=CreatorSettingsResponse)
def creator_settings(provider: Provider, account_id: UUID, svc: Service):
    return svc.creator_settings(account_id)


@router.post('/{provider}/accounts/{account_id}/refresh', response_model=CredentialHealth)
def refresh(provider: Provider, account_id: UUID, request: Request, body: AccountCommand, svc: Service, identity: Identity, key: IdempotencyKey):
    return command_response(request, svc.refresh(account_id, *args(request, identity, key, body)))


@router.post('/{provider}/accounts/{account_id}/disconnect', response_model=CredentialHealth)
def disconnect(provider: Provider, account_id: UUID, request: Request, body: AccountCommand, svc: Service, identity: Identity, key: IdempotencyKey):
    return command_response(request, svc.disconnect(account_id, *args(request, identity, key, body)))


@router.post('/{provider}/accounts/{account_id}/rotate-key', response_model=CredentialHealth)
def rotate_key(provider: Provider, account_id: UUID, request: Request, body: AccountCommand, svc: Service, identity: Identity, key: IdempotencyKey):
    return command_response(request, svc.rotate_key(account_id, *args(request, identity, key, body)))

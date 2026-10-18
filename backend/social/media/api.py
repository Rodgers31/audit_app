from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from ..http_boundary import AdminUser, get_db, social_admin
from .contracts import CompleteUpload, MediaAssetDTO, MediaCapabilities, MediaLibrary, MediaPreview, UploadAuthorization, UploadIntent
from .http import MediaRoute
from .runtime import request_media_runtime
from .service import MediaService
from .deletion import PrivacyMediaDeletionCommand, PrivacyMediaDeletionResult, execute_deletion, MediaDeletionInventory, inspect_deletion_scope
from .operator import OperatorReport, prepare_reconciliation
from .reconciliation import ReconcileOwnedUpload
from .owned_writes import reconcile_owned
from ..service import SocialError

router = APIRouter(prefix='/api/v1/admin/social/media', tags=['Admin Social Media'], dependencies=[Depends(social_admin)], route_class=MediaRoute)


def service(request: Request, db: Session = Depends(get_db)):
    runtime = request_media_runtime(request)
    from .privacy_adapter import PrivacyWorkflowMediaAdapter
    privacy_port = getattr(request.app.state, 'social_privacy_media_port', None)
    if isinstance(privacy_port, PrivacyWorkflowMediaAdapter) and privacy_port.runtime is runtime:
        runtime = privacy_port.authorized_runtime()
    return MediaService(db, runtime)

Service = Annotated[MediaService, Depends(service)]
Key = Annotated[UUID, Header(alias='Idempotency-Key')]
Admin = Annotated[AdminUser, Depends(social_admin)]


@router.get('/capabilities', response_model=MediaCapabilities)
def capabilities(svc: Service):
    return svc.capabilities()


@router.get('/maintenance', response_model=OperatorReport)
def maintenance(svc: Service, limit: int = Query(20, ge=1, le=20), after_asset_id: UUID | None = None):
    return prepare_reconciliation(svc, limit=limit, after_asset_id=after_asset_id)


@router.post('/assets/{asset_id}/retire', response_model=PrivacyMediaDeletionResult)
def retire(asset_id: UUID, body: PrivacyMediaDeletionCommand, svc: Service):
    if body.asset_id != asset_id:
        raise SocialError('INVALID_REQUEST', 'The deletion command must name this media asset.', 422)
    return execute_deletion(svc, body)


@router.get('/assets/{asset_id}/retirement-scope', response_model=MediaDeletionInventory)
def retirement_scope(asset_id: UUID, svc: Service):
    with svc.db.begin():
        return inspect_deletion_scope(svc, asset_id)


@router.post('/uploads', response_model=UploadAuthorization, status_code=201)
def initiate(body: UploadIntent, request: Request, svc: Service, admin: Admin, key: Key):
    return svc.initiate(UUID(admin.id), key, body, request.state.social_request_id)


@router.post('/uploads/{asset_id}/complete', response_model=MediaAssetDTO)
def complete(asset_id: UUID, body: CompleteUpload, request: Request, svc: Service, admin: Admin, key: Key):
    return svc.complete(UUID(admin.id), asset_id, key, body.expected_version, request.state.social_request_id)


@router.post('/uploads/{asset_id}/reconcile-owned', response_model=MediaAssetDTO)
def owned_reconciliation(asset_id: UUID, body: ReconcileOwnedUpload, request: Request, svc: Service, admin: Admin, key: Key):
    return reconcile_owned(svc, UUID(admin.id), asset_id, key, body, request.state.social_request_id)


@router.get('/assets', response_model=MediaLibrary)
def library(svc: Service, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50), q: str = Query('', max_length=100), kind: Literal['image', 'video'] | None = None):
    return svc.library(page, page_size, q, kind)


@router.get('/assets/{asset_id}/preview', response_model=MediaPreview)
def preview(asset_id: UUID, svc: Service):
    return svc.preview(asset_id)

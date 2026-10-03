from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from ..http_boundary import AdminUser, SocialRoute, get_db, social_admin
from .contracts import CompleteUpload, MediaAssetDTO, MediaCapabilities, MediaLibrary, MediaPreview, UploadAuthorization, UploadIntent
from .runtime import media_runtime
from .service import MediaService

router = APIRouter(prefix='/api/v1/admin/social/media', tags=['Admin Social Media'], dependencies=[Depends(social_admin)], route_class=SocialRoute)


def service(db: Session = Depends(get_db)):
    return MediaService(db, media_runtime())

Service = Annotated[MediaService, Depends(service)]
Key = Annotated[UUID, Header(alias='Idempotency-Key')]
Admin = Annotated[AdminUser, Depends(social_admin)]


@router.get('/capabilities', response_model=MediaCapabilities)
def capabilities(svc: Service):
    return svc.capabilities()


@router.post('/uploads', response_model=UploadAuthorization, status_code=201)
def initiate(body: UploadIntent, request: Request, svc: Service, admin: Admin, key: Key):
    return svc.initiate(UUID(admin.id), key, body, request.state.social_request_id)


@router.post('/uploads/{asset_id}/complete', response_model=MediaAssetDTO)
def complete(asset_id: UUID, body: CompleteUpload, request: Request, svc: Service, admin: Admin, key: Key):
    return svc.complete(UUID(admin.id), asset_id, key, body.expected_version, request.state.social_request_id)


@router.get('/assets', response_model=MediaLibrary)
def library(svc: Service, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=50), q: str = Query('', max_length=100), kind: Literal['image', 'video'] | None = None):
    return svc.library(page, page_size, q, kind)


@router.get('/assets/{asset_id}/preview', response_model=MediaPreview)
def preview(asset_id: UUID, svc: Service):
    return svc.preview(asset_id)

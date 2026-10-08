"""Admin-only social HTTP surface. All errors and successes are private/no-store."""
from typing import Union
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field, StrictBool
from sqlalchemy.orm import Session
if __package__ == "backend.social":
    from ..database import get_db
    from ..supabase_auth import AdminUser, require_admin
else:
    from database import get_db
    from supabase_auth import AdminUser, require_admin
from .contracts import ApproveCommand, CapabilitySet, ControlsCommand, CreatePost, EditorialState, PatchPost, Platform, PostDocument, PublishCommand, Reference, RejectCommand, ResumeCommand, RetryCommand, ScheduleCommand, ScheduleEditCommand, RescheduleCommand, StrictModel, TargetState, ValidateCommand, ValidationResult, VersionCommand
from .service import SocialError, SocialService
from .http_boundary import IdempotencyKey, NO_STORE, SocialRoute, social_admin

router = APIRouter(prefix='/api/v1/admin/social', tags=['Admin Social'], dependencies=[Depends(social_admin)], route_class=SocialRoute)

class TargetDTO(StrictModel):
    id: UUID
    account_id: UUID
    platform: Platform
    state: TargetState
    remote_url: Union[str, None]
    safe_error_message: Union[str, None]
    next_action_at: Union[datetime, None]
    published_at: Union[datetime, None]

class PublicationDTO(StrictModel):
    id: UUID
    revision_id: UUID
    scheduled_for: Union[datetime, None]
    version: int
    approved_at: datetime
    approved_by: UUID
    schedule_timezone: Union[str, None]
    requested_local_time: Union[str, None]
    cancel_requested_at: Union[datetime, None]

class PostSummary(StrictModel):
    id: UUID
    title: str
    content_type: str
    origin_type: Literal['manual', 'generated']
    editorial_state: EditorialState
    delivery_status: str
    version: int
    revision_id: UUID
    created_at: datetime
    created_by: Union[UUID, None]
    updated_at: datetime
    targets: tuple[TargetDTO, ...]
    publication: Union[PublicationDTO, None]

class CancellationDTO(StrictModel):
    in_flight_target_ids: tuple[UUID, ...]
    message: str

class PostDetail(PostSummary):
    document: PostDocument
    references: tuple[Reference, ...]
    cancellation: Union[CancellationDTO, None] = None

class PostList(StrictModel):
    posts: tuple[PostSummary, ...]
    total: int
    page: int
    page_size: int
    has_more: bool

class AcceptedTarget(StrictModel):
    id: UUID
    account_id: UUID
    platform: Platform
    status: TargetState

class PublicationAccepted(StrictModel):
    post_id: UUID
    publication_id: UUID
    status: Literal['queued']
    scheduled_for: Union[datetime, None]
    targets: tuple[AcceptedTarget, ...]
    status_url: str

class AccountDTO(StrictModel):
    id: UUID
    platform: Platform
    display_name: str
    handle: Union[str, None]
    profile_url: Union[str, None]
    connection_state: str
    publishing_enabled: bool
    capabilities: CapabilitySet

class AccountsDTO(StrictModel):
    accounts: tuple[AccountDTO, ...]

class PlatformDTO(StrictModel):
    platform: Platform
    capabilities: CapabilitySet

class PlatformsDTO(StrictModel):
    platforms: tuple[PlatformDTO, ...]

class ControlsDTO(StrictModel):
    version: int
    publishing_enabled: bool
    generation_enabled: Literal[False]
    auto_approve_enabled: Literal[False]
    auto_schedule_enabled: Literal[False]
    auto_publish_enabled: Literal[False]

class WorkerDTO(StrictModel):
    state: str
    heartbeat_at: Union[datetime, None]
    last_scan_at: Union[datetime, None]

class SystemDTO(StrictModel):
    publishing_enabled: bool
    controls_version: int
    worker: WorkerDTO
    queue_counts: dict[str, int]
    adapters_available: tuple[str, ...]
    media_upload_available: StrictBool
    generation_enabled: Literal[False]
    auto_approve_enabled: Literal[False]
    auto_schedule_enabled: Literal[False]
    auto_publish_enabled: Literal[False]

def service(db: Session=Depends(get_db)):
    return SocialService(db)

def command(request, svc, admin, key, body, action, status=200):
    try:
        actor = UUID(admin.id)
    except (TypeError, ValueError, AttributeError):
        raise SocialError('PERMISSION_DENIED', 'The authenticated administrator must have a valid UUID identity.', 403) from None
    status, result = svc.command(actor=actor, route=request.method + ' ' + request.url.path, key=key, body=body.model_dump(mode='json', exclude_unset=True), request_id=request.state.social_request_id, action=action, status=status)
    dto = request.scope['route'].response_model.model_validate(result)
    return JSONResponse(status_code=status, content=dto.model_dump(mode='json', exclude_unset=True), headers=NO_STORE)
Admin = Annotated[AdminUser, Depends(social_admin)]
Service = Annotated[SocialService, Depends(service)]

@router.get('/posts', response_model=PostList)
def list_posts(svc: Service, page: int=Query(1, ge=1), page_size: int=Query(20, ge=1, le=100), editorial_state: Union[EditorialState, None]=None, delivery_filter: Literal['all', 'scheduled', 'history', 'needs_attention']='all'):
    return svc.posts(page, page_size, editorial_state, delivery_filter)

@router.post('/posts', response_model=PostDetail, status_code=201)
def create_post(request: Request, body: CreatePost, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.create(body), 201)

@router.get('/posts/{post_id}', response_model=PostDetail, response_model_exclude_unset=True)
def get_post(post_id: UUID, svc: Service):
    return svc.detail(post_id)

@router.get("/posts/{post_id}/status", response_model=PostSummary)
def post_status(post_id: UUID, svc: Service):
    return svc.summary(post_id)

@router.patch('/posts/{post_id}', response_model=PostDetail)
def patch_post(post_id: UUID, request: Request, body: PatchPost, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.patch(post_id, body))

@router.post('/posts/{post_id}/validate', response_model=ValidationResult)
def validate_post(post_id: UUID, svc: Service, body: Union[ValidateCommand, None]=None):
    return svc.validate(post_id, body or ValidateCommand())

@router.post('/posts/{post_id}/submit', response_model=PostDetail)
def submit_post(post_id: UUID, request: Request, body: VersionCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.submit(post_id, body))

@router.post('/posts/{post_id}/approve', response_model=PostDetail)
def approve_post(post_id: UUID, request: Request, body: ApproveCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.approve(post_id, body))

@router.post('/posts/{post_id}/reject', response_model=PostDetail)
def reject_post(post_id: UUID, request: Request, body: RejectCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.reject(post_id, body))

@router.post('/posts/{post_id}/publish', response_model=PublicationAccepted, status_code=202)
def publish_post(post_id: UUID, request: Request, body: PublishCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.publish(post_id, body), 202)

@router.post('/posts/{post_id}/schedule', response_model=PublicationAccepted, status_code=202)
def schedule_post(post_id: UUID, request: Request, body: ScheduleCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.publish(post_id, body, scheduled=True), 202)

@router.post('/posts/{post_id}/reschedule', response_model=PostDetail)
def reschedule_post(post_id: UUID, request: Request, body: RescheduleCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.edit_schedule(post_id, body, scheduled=True))

@router.post('/posts/{post_id}/publish-now', response_model=PostDetail, status_code=202)
def publish_now_post(post_id: UUID, request: Request, body: ScheduleEditCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.edit_schedule(post_id, body), 202)

@router.post('/posts/{post_id}/cancel', response_model=PostDetail)
def cancel_post(post_id: UUID, request: Request, body: VersionCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.cancel(post_id, body))

@router.post('/posts/{post_id}/resume', response_model=PublicationAccepted, status_code=202)
def resume_post(post_id: UUID, request: Request, body: ResumeCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.resume(post_id, body), 202)

@router.post('/posts/{post_id}/duplicate', response_model=PostDetail, status_code=201)
def duplicate_post(post_id: UUID, request: Request, body: VersionCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.duplicate(post_id, body), 201)

@router.post('/targets/{target_id}/retry', response_model=PostDetail)
def retry_target(target_id: UUID, request: Request, body: RetryCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.retry(target_id, body))

@router.get('/accounts', response_model=AccountsDTO)
def get_accounts(svc: Service):
    return svc.accounts()

@router.get('/platforms', response_model=PlatformsDTO)
def get_platforms(svc: Service):
    return svc.platforms()

@router.get('/system/status', response_model=SystemDTO)
def get_status(svc: Service):
    return svc.status()

@router.patch('/controls', response_model=ControlsDTO)
def set_controls(request: Request, body: ControlsCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.controls(body))

# Feature routers already have their complete public prefix. Aggregate beside
# the editorial router rather than nesting under its prefix a second time.
from .connections.api import router as connection_router
from .media.api import router as media_router
_editorial_router = router
router = APIRouter()
router.include_router(_editorial_router)
router.include_router(connection_router)
router.include_router(media_router)

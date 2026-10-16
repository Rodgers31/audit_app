"""Private admin command ports; runtime activation defaults off and needs a ceiling."""
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from ..api import Service, Admin, command, PostDetail, PublicationAccepted
from ..http_boundary import SocialRoute, social_admin, IdempotencyKey
from ..contracts import StrictModel
from .contracts import OperatingEvidenceCommand, SnapshotCommand, PolicyControlsCommand, AuthorizePolicyCommand, SchedulePolicyCommand
from .service import AutomationService, controls_dto
from .models import PolicyDecision

router = APIRouter(prefix='/api/v1/admin/social', tags=['Admin Social Policy'], dependencies=[Depends(social_admin)], route_class=SocialRoute)

class EvidenceResult(StrictModel):
    id: UUID
    evidence_hash: str

class SnapshotResult(StrictModel):
    id: UUID
    snapshot_hash: str

class PolicyControlsDTO(StrictModel):
    version: int
    snapshot_id: UUID | None
    environment_enabled: bool
    auto_approve_enabled: bool
    auto_schedule_enabled: bool
    auto_publish_enabled: bool

class DecisionDTO(StrictModel):
    id: UUID
    snapshot_id: UUID
    post_id: UUID
    revision_id: UUID
    content_hash: str
    inputs: dict
    decision_hash: str
    created_at: datetime

class DecisionsDTO(StrictModel):
    decisions: list[DecisionDTO]
    total: int
    page: int
    page_size: int
    has_more: bool

@router.get('/automation/policy-controls', response_model=PolicyControlsDTO)
def get_controls(svc: Service):
    return controls_dto(svc.db)

@router.patch('/automation/policy-controls', response_model=PolicyControlsDTO)
def set_controls(request: Request, body: PolicyControlsCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: AutomationService(svc).set_controls(body))

@router.post('/automation/operating-evidence', response_model=EvidenceResult, status_code=201)
def evidence(request: Request, body: OperatingEvidenceCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: AutomationService(svc).accept_operating_evidence(body), 201)

@router.post('/automation/policy-snapshots', response_model=SnapshotResult, status_code=201)
def snapshot(request: Request, body: SnapshotCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: AutomationService(svc).authorize_snapshot(body), 201)

@router.post('/posts/{post_id}/policy-authorize', response_model=PostDetail)
def authorize(post_id: UUID, request: Request, body: AuthorizePolicyCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: AutomationService(svc).authorize(post_id, body))

@router.post('/posts/{post_id}/policy-schedule', response_model=PublicationAccepted, status_code=202)
def schedule(post_id: UUID, request: Request, body: SchedulePolicyCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: AutomationService(svc).schedule(post_id, body), 202)

@router.get('/automation/policy-decisions', response_model=DecisionsDTO)
def decisions(svc: Service, page: int=Query(1, ge=1, le=1000000)):
    total = svc.db.scalar(select(func.count()).select_from(PolicyDecision))
    rows = svc.db.scalars(select(PolicyDecision).order_by(PolicyDecision.created_at.desc(), PolicyDecision.id).offset((page-1)*20).limit(20))
    return dict(decisions=[dict(id=r.id, snapshot_id=r.snapshot_id, post_id=r.post_id, revision_id=r.revision_id, content_hash=r.content_hash, inputs=r.inputs, decision_hash=r.decision_hash, created_at=r.created_at) for r in rows], total=total, page=page, page_size=20, has_more=page*20 < total)

"""Authenticated privacy review surface; operator policy cannot be changed here."""
from typing import Any, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..http_boundary import IdempotencyKey, SocialRoute, social_admin, get_db
from ..contracts import StrictModel
from ..service import SocialError
from .models import SocialPrivacyReceipt
from .workflow import PrivacyWorkflow
from .workflow_contracts import PrivacyProposal, PrivacyApproval, PrivacyRun, PrivacyWorkflowConfig
from .workflow_models import PrivacyPlan

router = APIRouter(prefix='/api/v1/admin/social/privacy', tags=['Admin Social Privacy'], dependencies=[Depends(social_admin)], route_class=SocialRoute)

class ReceiptSummary(StrictModel):
    id: UUID
    kind: str
    state: str
    resolution: str
    affected_count: int

class PrivacyQueue(StrictModel):
    requests: list[ReceiptSummary]
    page: int
    page_size: int
    total: int
    has_more: bool
    workflow_enabled: bool
    execution_enabled: bool
    policies: dict[str, str]

class PlanView(StrictModel):
    id: UUID
    receipt_id: UUID
    proposed_by: UUID
    policy_key: str
    policy_hash: str
    plan_hash: str
    evidence: str
    scope: dict[str, list[dict[str, Any]]]
    decision: Literal['pending_review', 'approved', 'rejected'] = 'pending_review'
    approved_by: UUID | None = None
    execution: dict[str, Any] | None = None


def workflow(request: Request, db: Session = Depends(get_db)):
    config = getattr(request.app.state, 'social_privacy_workflow_config', PrivacyWorkflowConfig())
    registration = getattr(request.app.state, 'social_privacy_registration', None)
    media = getattr(request.app.state, 'social_privacy_media_port', None)
    runtime = getattr(request.app.state, 'social_media_runtime', None)
    if media is None and config.execution_enabled and registration is not None and runtime is not None and getattr(runtime.config, 'fenced_retirement_enabled', False) is True:
        # Optional additive media successor. Its policy remains independently off.
        from ..media.privacy_adapter import PrivacyWorkflowMediaAdapter
        media = PrivacyWorkflowMediaAdapter(registration.session_factory, runtime,
            getattr(request.app.state, 'social_privacy_deletion_ledger', None))
        request.app.state.social_privacy_media_port = media
    return PrivacyWorkflow(db, config, cipher=registration.cipher if registration else None,
        ledger=getattr(request.app.state, 'social_privacy_deletion_ledger', None),
        media=media)

@router.get('/requests', response_model=PrivacyQueue)
def requests(request: Request, page: int = Query(1, ge=1, le=10000), page_size: int = Query(20, ge=1, le=100), svc=Depends(workflow)):
    with svc.db.begin():
        count = svc.db.scalar(select(func.count()).select_from(SocialPrivacyReceipt))
        rows = svc.db.scalars(select(SocialPrivacyReceipt).order_by(SocialPrivacyReceipt.received_at.desc(), SocialPrivacyReceipt.id).offset((page-1)*page_size).limit(page_size)).all()
        return {'requests': [dict(id=r.id, kind=r.kind, state=r.state, resolution=r.resolution, affected_count=len(r.affected)) for r in rows],
            'page': page, 'page_size': page_size, 'total': count, 'has_more': page*page_size<count,
            'workflow_enabled': svc.config.enabled, 'execution_enabled': svc.config.execution_enabled, 'policies': dict(svc.config.policies)}

@router.get('/plans/{plan_id}', response_model=PlanView)
def plan(plan_id: UUID, svc=Depends(workflow)):
    return svc.get(plan_id)

@router.post('/plans', response_model=PlanView)
def propose(command: PrivacyProposal, key: IdempotencyKey, actor=Depends(social_admin), svc=Depends(workflow)):
    return svc.propose(UUID(actor.id), key, command)

@router.post('/plans/{plan_id}/decision', response_model=PlanView)
def decide(plan_id: UUID, command: PrivacyApproval, actor=Depends(social_admin), svc=Depends(workflow)):
    return svc.decide(UUID(actor.id), plan_id, command)

@router.post('/plans/{plan_id}/execute', response_model=PlanView)
def execute(plan_id: UUID, command: PrivacyRun, actor=Depends(social_admin), svc=Depends(workflow)):
    svc.execute(UUID(actor.id), plan_id, command.expected_version)
    return svc.get(plan_id)

@router.post('/plans/{plan_id}/reconcile', response_model=PlanView)
def reconcile(plan_id: UUID, command: PrivacyRun, actor=Depends(social_admin), svc=Depends(workflow)):
    svc.reconcile(UUID(actor.id), plan_id, command.expected_version)
    return svc.get(plan_id)

class RequestView(ReceiptSummary):
    credentials: list[UUID]
    flows: list[UUID]
    plans: list[PlanView]

@router.get('/requests/{receipt_id}', response_model=RequestView)
def request_detail(receipt_id: UUID, svc=Depends(workflow)):
    with svc.db.begin():
        row = svc.db.get(SocialPrivacyReceipt, receipt_id)
        if row is None:
            raise SocialError('NOT_FOUND', 'Privacy request was not found.', 404)
        plans = list(svc.db.scalars(select(PrivacyPlan.id).where(PrivacyPlan.receipt_id == receipt_id).order_by(PrivacyPlan.created_at.desc(), PrivacyPlan.id).limit(50)))
        result = dict(id=row.id, kind=row.kind, state=row.state, resolution=row.resolution, affected_count=len(row.affected),
            credentials=sorted({r['credential_id'] for r in row.affected if r['credential_id']}),
            flows=sorted({r['flow_id'] for r in row.affected}))
    result['plans'] = [svc.get(i) for i in plans]
    return result

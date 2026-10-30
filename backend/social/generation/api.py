"""Authenticated private draft/shadow APIs. No endpoint accepts invented facts."""
from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import func, select

from ..api import Admin, Service, command, PostDetail
from ..contracts import StrictModel, DocumentTarget
from ..http_boundary import IdempotencyKey, SocialRoute, social_admin
from fastapi import Depends
from ..service import SocialError
from ..models import SocialCommandReceipt
from .contracts import GenerationControlsCommand, RuleCommand, EvaluateCommand, SourceObservation, DetectCommand, PreviewCommand, PrepareDraftCommand
from .models import GenerationControls, AutomationRuleVersion, ShadowDecision, SourceEvent
from .service import GenerationService, controls_dto, rule_dto, decision_dto, consume_observation

router = APIRouter(prefix='/api/v1/admin/social', tags=['Admin Social Generation'], dependencies=[Depends(social_admin)], route_class=SocialRoute)


class ControlsDTO(StrictModel):
    version: int
    drafts_enabled: bool
    shadow_enabled: bool
    source_allowlist: list[str]
    targets: list[DocumentTarget]


class RuleDTO(StrictModel):
    id: UUID
    version: int
    definition: dict
    definition_hash: str
    created_at: datetime


class RulesDTO(StrictModel):
    rules: list[RuleDTO]
    total: int
    page: int
    page_size: int
    has_more: bool


class DecisionDTO(StrictModel):
    id: UUID
    post_id: UUID
    revision_id: UUID
    rule_version_id: UUID
    content_hash: str
    outcome: Literal['would_allow', 'human_review']
    reasons: list[str]
    account_ids: list[UUID]
    inputs: dict
    created_at: datetime


class DecisionsDTO(StrictModel):
    decisions: list[DecisionDTO]
    total: int
    page: int
    page_size: int
    has_more: bool


class EvidenceDTO(StrictModel):
    post_id: UUID
    revision_id: UUID
    source_event_id: Union[UUID, None]
    evidence: dict
    generator_metadata: Union[dict, None]


class DetectionResult(StrictModel):
    status: Literal['baseline', 'unchanged', 'draft_created']
    event_id: Union[UUID, None]
    post_id: Union[UUID, None]
    sequence: int


class DetectionDTO(StrictModel):
    results: list[DetectionResult]


@router.get('/generation/controls', response_model=ControlsDTO)
def get_controls(svc: Service):
    row = svc.db.get(GenerationControls, 1)
    return controls_dto(row) if row else dict(version=1, drafts_enabled=False, shadow_enabled=False, source_allowlist=[], targets=[])


@router.patch('/generation/controls', response_model=ControlsDTO)
def set_controls(request: Request, body: GenerationControlsCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: GenerationService(svc).set_controls(body))


@router.get('/posts/{post_id}/evidence', response_model=EvidenceDTO)
def evidence(post_id: UUID, svc: Service):
    post = svc._post(post_id)
    revision = svc._revision(post)
    return dict(post_id=post.id, revision_id=revision.id, source_event_id=post.source_event_id, evidence=revision.evidence_snapshot, generator_metadata=revision.generator_metadata)


@router.post('/posts/{post_id}/prepare', response_model=PostDetail)
def prepare_draft(post_id: UUID, request: Request, body: PrepareDraftCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: GenerationService(svc).prepare(post_id, body))


@router.get('/automation/rules', response_model=RulesDTO)
def rules(svc: Service, page: int=Query(1, ge=1, le=1000000)):
    total = svc.db.scalar(select(func.count()).select_from(AutomationRuleVersion))
    rows = svc.db.scalars(select(AutomationRuleVersion).order_by(AutomationRuleVersion.created_at.desc(), AutomationRuleVersion.id).offset((page-1)*20).limit(20))
    return dict(rules=[rule_dto(r) for r in rows], total=total, page=page, page_size=20, has_more=page*20 < total)


@router.post('/automation/rules/{rule_id}/versions', response_model=RuleDTO, status_code=201)
def save_rule(rule_id: UUID, request: Request, body: RuleCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: GenerationService(svc).save_rule(rule_id, body), 201)


@router.post('/posts/{post_id}/shadow', response_model=DecisionDTO)
def shadow(post_id: UUID, request: Request, body: EvaluateCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: GenerationService(svc).evaluate(post_id, body))


@router.get('/automation/decisions', response_model=DecisionsDTO)
def decisions(svc: Service, page: int=Query(1, ge=1, le=1000000), post_id: Union[UUID, None]=None):
    where = [ShadowDecision.post_id == post_id] if post_id else []
    total = svc.db.scalar(select(func.count()).select_from(ShadowDecision).where(*where))
    rows = svc.db.scalars(select(ShadowDecision).where(*where).order_by(ShadowDecision.created_at.desc(), ShadowDecision.id).offset((page-1)*20).limit(20))
    return dict(decisions=[decision_dto(r) for r in rows], total=total, page=page, page_size=20, has_more=page*20 < total)


@router.post('/generation/detect', response_model=DetectionDTO)
def detect(request: Request, body: DetectCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return _detect(request, body, svc, admin, key, reports=False)


@router.post('/generation/detect-reports', response_model=DetectionDTO)
def detect_reports(request: Request, body: DetectCommand, svc: Service, admin: Admin, key: IdempotencyKey):
    return _detect(request, body, svc, admin, key, reports=True)


def _detect(request, body, svc, admin, key, *, reports):
    # Release the read-only receipt lookup before opening a committed source
    # reader. Holding one pool connection while borrowing another can starve
    # every concurrent detector at the configured pool boundary.
    if svc.db.in_transaction():
        raise SocialError('REQUEST_SESSION_UNAVAILABLE', 'A fresh request session is required.', 503)
    route = request.method + ' ' + request.url.path
    replay = svc.db.scalar(select(SocialCommandReceipt.id).where(SocialCommandReceipt.actor_key == str(UUID(admin.id)), SocialCommandReceipt.route_key == route, SocialCommandReceipt.idempotency_key == key))
    svc.db.rollback()
    if replay:
        def receipt_only():
            raise SocialError('REPLAY_UNAVAILABLE', 'The original receipt is unavailable. Inspect the existing drafts before retrying.', 503)
        return command(request, svc, admin, key, body, receipt_only)
    from sqlalchemy.orm import sessionmaker
    from importlib import import_module
    try:
        adapter = import_module('backend.seeding.source_observations' if __package__.startswith('backend.') else 'seeding.source_observations')
    except ModuleNotFoundError as error:
        if error.name not in {'seeding.source_observations', 'backend.seeding.source_observations'}:
            raise
        raise SocialError('SOURCE_ADAPTER_UNAVAILABLE', 'The reviewed committed-evidence adapter is not installed.', 503) from None
    capability_module = import_module('backend.seeding.generation_capabilities' if __package__.startswith('backend.') else 'seeding.generation_capabilities')
    selected = capability_module.capability(body.domain)
    if not (selected.reports if reports else selected.financial):
        raise SocialError('SOURCE_NOT_ELIGIBLE', 'The selected native source has no eligible adapter.', 422)
    reader = getattr(adapter, selected.report_reader if reports else selected.financial_reader, None)
    if not callable(reader):
        raise SocialError('SOURCE_ADAPTER_UNAVAILABLE', 'The reviewed committed-evidence adapter is not installed.', 503)
    factory = sessionmaker(bind=svc.db.get_bind(), expire_on_commit=False)
    values = []
    for record_id in body.record_ids:
        try:
            value = reader(factory, record_id=record_id, ingestion_id=body.ingestion_id)
        except adapter.SourceObservationUnavailable:
            raise SocialError('SOURCE_NOT_ELIGIBLE', 'Committed evidence is incomplete or ineligible. Inspect the ETL source record.', 422) from None
        values.append(SourceObservation.model_validate(value))
    def action():
        results = [consume_observation(svc, value, backfill=body.backfill) for value in values]
        svc.audit('generation.reports_detected' if reports else 'generation.detected', reason=body.reason, details={'record_ids': list(body.record_ids), 'ingestion_id': body.ingestion_id, 'backfill': body.backfill})
        return {'results': results}
    return command(request, svc, admin, key, body, action)


class CapabilityDTO(StrictModel):
    domain: str
    financial: bool
    reports: bool
    reason: str


class PreviewResult(StrictModel):
    record_id: int
    status: Literal['baseline', 'unchanged', 'eligible_change', 'refused', 'unsupported_source']
    reason: str
    source_document_id: int | None


class PreviewDTO(StrictModel):
    drafts_enabled: bool
    results: list[PreviewResult]


@router.get('/generation/capabilities', response_model=list[CapabilityDTO])
def generation_capabilities():
    from .preview import capabilities_dto
    return capabilities_dto()


@router.post('/generation/preview', response_model=PreviewDTO)
def preview_generation(body: PreviewCommand, svc: Service):
    from sqlalchemy.orm import sessionmaker
    from .preview import preview
    if svc.db.in_transaction():
        raise SocialError('REQUEST_SESSION_UNAVAILABLE', 'A fresh request session is required.', 503)
    return preview(sessionmaker(bind=svc.db.get_bind(), expire_on_commit=False), body)

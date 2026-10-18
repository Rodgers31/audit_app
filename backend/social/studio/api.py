from datetime import datetime
import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select

from ..api import Admin, PostDetail, Service, command
from ..contracts import Hash, Platform, StrictModel, VersionCommand
from ..http_boundary import IdempotencyKey, SocialRoute, social_admin
from ..service import SocialError
from .analytics import observations
from .contracts import Approval, Composition, Metric, TEMPLATES, TEMPLATE_DEFINITIONS
from .integrity import bound_composition
from .models import RenderJob
from .runtime import request_runtime, verified_bytes
from .service import StudioService, calendar, job_dto

router = APIRouter(prefix='/api/v1/admin/social/studio', tags=['Admin Social Studio'], dependencies=[Depends(social_admin)], route_class=SocialRoute)


class JobDTO(StrictModel):
    id: UUID
    revision_id: UUID
    state: Literal['queued', 'running', 'ready', 'failed', 'cancelled']
    version: int
    composition: Composition
    input_hash: Hash
    sha256: Hash | None
    inspection: dict | None
    safe_error: str | None
    approved_sha256: Hash | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    runtime_hash: Hash | None
    cancel_requested: bool
    attempt: int
    retry_of_id: UUID | None


class JobsDTO(StrictModel):
    jobs: tuple[JobDTO, ...]
    page: int
    has_more: bool


class CapabilitiesDTO(StrictModel):
    rendering_available: bool
    unavailable_reason: str | None
    templates: tuple[str, ...]
    template_version: Literal[1]
    analytics_collection_available: bool
    analytics_reason: str
    uploads_enabled: Literal[False]
    template_definitions: dict[str, dict]


class Attach(VersionCommand):
    asset_id: UUID


class CalendarItem(StrictModel):
    publication_id: UUID
    post_id: UUID
    title: str
    revision_id: UUID
    scheduled_for: datetime
    timezone: str | None
    cancel_requested: bool
    revoked: bool


class CalendarDTO(StrictModel):
    items: tuple[CalendarItem, ...]
    page: int
    has_more: bool


class ObservationDTO(Metric):
    freshness: Literal['fresh', 'stale']


class CollectionDTO(StrictModel):
    id: UUID
    state: Literal['reserved', 'collected', 'unavailable', 'failed']
    reason: str | None
    remote_id: str
    created_at: datetime
    metrics: tuple[ObservationDTO, ...]


class AnalyticsDTO(StrictModel):
    target_id: UUID
    platform: Platform
    availability: Literal['observed', 'unavailable']
    reason: str | None
    collections: tuple[CollectionDTO, ...]
    page: int
    has_more: bool


def studio(request: Request, svc: Service):
    return StudioService(svc, request_runtime(request))


Studio = Annotated[StudioService, Depends(studio)]


@router.get('/capabilities', response_model=CapabilitiesDTO)
def capabilities(request: Request, svc: Service):
    runtime = request_runtime(request)
    from .native_metrics import request_analytics_runtime, capability_status
    analytics = request_analytics_runtime(request)
    analytics_available, analytics_reason = capability_status(svc.db, analytics)
    return {'rendering_available': runtime.enabled, 'unavailable_reason': None if runtime.enabled else 'Local rendering is disabled; operator configuration and verified capacity are required.', 'templates': TEMPLATES, 'template_definitions': TEMPLATE_DEFINITIONS, 'template_version': 1, 'analytics_collection_available': analytics_available, 'analytics_reason': analytics_reason, 'uploads_enabled': False}


@router.get('/jobs', response_model=JobsDTO)
def jobs(svc: Studio, page: int = Query(1, ge=1, le=100000)):
    rows = svc.db.scalars(select(RenderJob).order_by(RenderJob.created_at.desc(), RenderJob.id).offset((page - 1) * 10).limit(11)).all()
    return {'jobs': [job_dto(r) for r in rows[:10]], 'page': page, 'has_more': len(rows) > 10}


@router.get('/jobs/{job_id}', response_model=JobDTO)
def job(job_id: UUID, svc: Studio):
    return job_dto(svc.get(job_id))


@router.post('/jobs', response_model=JobDTO, status_code=201)
def create(body: Composition, request: Request, svc: Studio, admin: Admin, key: IdempotencyKey):
    return command(request, svc.social, admin, key, body, lambda: svc.create(body), 201)


@router.post('/jobs/{job_id}/cancel', response_model=JobDTO)
def cancel(job_id: UUID, body: VersionCommand, request: Request, svc: Studio, admin: Admin, key: IdempotencyKey):
    return command(request, svc.social, admin, key, body, lambda: svc.cancel(job_id, body.expected_version))


@router.post('/jobs/{job_id}/approve', response_model=JobDTO)
def approve(job_id: UUID, body: Approval, request: Request, svc: Studio, admin: Admin, key: IdempotencyKey):
    return command(request, svc.social, admin, key, body, lambda: svc.approve(job_id, body))


@router.post('/jobs/{job_id}/retry', response_model=JobDTO, status_code=201)
def retry(job_id: UUID, body: VersionCommand, request: Request, svc: Studio, admin: Admin, key: IdempotencyKey):
    return command(request, svc.social, admin, key, body, lambda: svc.retry(job_id, body.expected_version), 201)


@router.post('/jobs/{job_id}/attach', response_model=PostDetail)
def attach(job_id: UUID, body: Attach, request: Request, svc: Studio, admin: Admin, key: IdempotencyKey):
    return command(request, svc.social, admin, key, body, lambda: svc.attach(job_id, body.asset_id, body.expected_version))


@router.get('/jobs/{job_id}/preview', response_class=Response)
def preview(job_id: UUID, svc: Studio):
    row = svc.get(job_id)
    bound_composition(svc.db, row)
    if row.state != 'ready':
        raise SocialError('RENDER_NOT_READY', 'Only inspected derivatives can be previewed.')
    data = verified_bytes(svc.runtime, row)
    return Response(data, media_type=row.inspection['mime_type'], headers={'Content-Disposition': f'inline; filename="{row.id}.{"mp4" if row.composition["kind"] == "video" else "png"}"', 'X-Content-SHA256': row.sha256})


@router.get('/jobs/{job_id}/transcript', response_class=Response)
def transcript(job_id: UUID, svc: Studio, format: Literal['json', 'srt'] = 'json'):
    row = svc.get(job_id)
    bound_composition(svc.db, row)
    if row.state != 'ready':
        raise SocialError('RENDER_NOT_READY', 'Only inspected derivatives have an admitted transcript.')
    facts = {f['id']: f for f in row.composition['facts']}
    elapsed, entries, subtitles = 0, [], []
    for index, scene in enumerate(row.composition['scenes']):
        fact, end = facts[scene['fact_id']], elapsed + scene['seconds']
        entries.append({'fact_id': fact['id'], 'source_url': fact['source_url'], 'text': fact['text'], 'start_ms': elapsed * 1000, 'end_ms': end * 1000})
        subtitles.append(f'{index + 1}\n00:00:{elapsed:02d},000 --> 00:00:{end:02d},000\n{fact["text"]}\n')
        elapsed = end
    body = json.dumps({'sha256': row.sha256, 'input_hash': row.input_hash, 'entries': entries}) if format == 'json' else '\n'.join(subtitles)
    return Response(body, media_type='application/json' if format == 'json' else 'application/x-subrip', headers={'Content-Disposition': f'attachment; filename="{row.id}.{format}"', 'X-Content-SHA256': row.sha256})


@router.get('/calendar', response_model=CalendarDTO)
def get_calendar(svc: Service, start: datetime, end: datetime, page: int = Query(1, ge=1, le=100000)):
    return calendar(svc.db, start, end, page)


@router.get('/analytics/{target_id}', response_model=AnalyticsDTO)
def get_analytics(target_id: UUID, svc: Service, page: int = Query(1, ge=1, le=100000)):
    return observations(svc.db, target_id, page)

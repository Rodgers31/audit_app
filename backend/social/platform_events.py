"""Verified provider hints, never publication proof or a second publisher.

Pinned 2026-10-16: Threads webhooks (updated 2026-06-30) and TikTok
Accounts API v1.3. Callbacks persist minimal events before acknowledging;
the bounded consumer only expedites an existing status/reconciliation action.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .contracts import Reason, StrictModel
from .http_boundary import IdempotencyKey, NO_STORE, SocialRoute, get_db, social_admin
from .models import SocialAccount, SocialPostTarget
from .platform_event_models import SocialPlatformEvent
from .service import SocialError, SocialService, utc

SOURCES = (
    'https://developers.facebook.com/documentation/threads/webhooks',
    'https://developers.facebook.com/docs/graph-api/webhooks/getting-started',
    'https://business-api.tiktok.com/portal/docs/post-publishing-events/v1.3',
    'https://business-api.tiktok.com/portal/docs/webhook-verification/v1.3',
)
MAX_BODY_BYTES = 65536
MAX_EVENT_AGE_SECONDS = 172800  # Threads retries may arrive for 36 hours.
MAX_DELIVERY_AGE_SECONDS = 300  # Our TikTok signed-delivery freshness policy.
RETENTION_DAYS = 30  # Dedupe tombstones outlive provider redelivery windows.
Provider = Literal['threads', 'tiktok']


@dataclass(frozen=True)
class EventConfig:
    platform: str
    enabled: bool = False
    subscription_verified: bool = False
    product_access_verified: bool = False
    app_id: str = ''
    app_secret: str = field(default='', repr=False)
    verify_token: str = field(default='', repr=False)
    # Exact approved Threads subscription ID -> connected external account ID.
    subscriptions: tuple[tuple[str, str], ...] = ()
    # TikTok Accounts API user_openid values, never inferred from an advertiser.
    account_ids: tuple[str, ...] = ()

    def require_ready(self):
        ready = (self.platform in {'threads', 'tiktok'} and self.enabled is True
                 and self.subscription_verified is True and self.product_access_verified is True
                 and isinstance(self.app_secret, str) and bool(self.app_secret)
                 and _identifier(self.app_id))
        if self.platform == 'threads':
            ready = (ready and bool(self.verify_token) and isinstance(self.verify_token, str)
                     and type(self.subscriptions) is tuple and bool(self.subscriptions)
                     and all(type(item) is tuple and len(item) == 2 and all(_identifier(v) for v in item) for item in self.subscriptions)
                     and len({item[0] for item in self.subscriptions}) == len(self.subscriptions))
        else:
            ready = (ready and type(self.account_ids) is tuple and bool(self.account_ids)
                     and all(_identifier(item) for item in self.account_ids)
                     and len(set(self.account_ids)) == len(self.account_ids))
        if not ready:
            raise SocialError('EVENTS_UNAVAILABLE', 'Provider event subscription and product access must be explicitly verified.', 503)


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.~:-]{1,256}', value) is not None


def _invalid(code='INVALID_PROVIDER_EVENT', status=400):
    return SocialError(code, 'The provider event could not be verified.', status)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def _json(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda _: (_ for _ in ()).throw(_invalid()))
    except (ValueError, UnicodeError, RecursionError):
        raise _invalid() from None
    if not isinstance(value, dict):
        raise _invalid()
    return value


def _timestamp(value, now):
    if type(value) is not int:
        raise _invalid()
    if not int(now.timestamp()) - MAX_EVENT_AGE_SECONDS <= value <= int(now.timestamp()) + 300:
        raise _invalid('PROVIDER_EVENT_EXPIRED', 403)
    return datetime.fromtimestamp(value, timezone.utc)


@dataclass(frozen=True)
class VerifiedEvent:
    provider: str
    external_account_id: str
    event_type: str
    remote_id: str
    post_id: str | None
    event_at: datetime
    dedupe_hash: str


def verify_event(config: EventConfig, raw: bytes, signature: str | None, *, now=None):
    """Verify exact received bytes before parsing; no JSON reserialization fallback."""
    config.require_ready()
    now = utc(now or datetime.now(timezone.utc))
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BODY_BYTES:
        raise _invalid('PROVIDER_EVENT_TOO_LARGE', 413)
    if not isinstance(signature, str) or len(signature) > 256:
        raise _invalid('PROVIDER_SIGNATURE_INVALID', 403)
    if config.platform == 'threads':
        if re.fullmatch(r'sha256=[0-9a-f]{64}', signature) is None:
            raise _invalid('PROVIDER_SIGNATURE_INVALID', 403)
        expected = 'sha256=' + hmac.new(config.app_secret.encode(), raw, hashlib.sha256).hexdigest()
    else:
        if re.fullmatch(r't=[0-9]{1,12},s=[0-9a-f]{64}', signature) is None:
            raise _invalid('PROVIDER_SIGNATURE_INVALID', 403)
        timestamp = signature[2:].split(',s=')[0]
        if not 0 <= int(now.timestamp()) - int(timestamp) <= MAX_DELIVERY_AGE_SECONDS:
            raise _invalid('PROVIDER_EVENT_EXPIRED', 403)
        expected = 't=' + timestamp + ',s=' + hmac.new(config.app_secret.encode(), timestamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise _invalid('PROVIDER_SIGNATURE_INVALID', 403)
    body = _json(raw)
    if config.platform == 'threads':
        if body.get('app_id') != config.app_id:
            raise _invalid()
        subscription_id = body.get('subscription_id')
        if not _identifier(subscription_id):
            raise _invalid()
        external = dict(config.subscriptions).get(subscription_id)
        values = body.get('values')
        if not external or not isinstance(values, dict) or not isinstance(values.get('value'), dict):
            raise _invalid()
        kind, content = values.get('field'), values['value']
        if not isinstance(kind, str) or not isinstance(body.get('topic'), str) or (kind, body.get('topic')) not in {('publish', 'interaction'), ('delete', 'moderate')}:
            raise _invalid('PROVIDER_EVENT_UNSUPPORTED', 422)
        # target_id is not documented as account identity for every field;
        # account membership comes from the exact verified subscription binding.
        remote = content.get('id')
        post = remote
        event_at = _timestamp(body.get('time'), now)
        subscription = body.get('subscription_id')
    else:
        if body.get('client_key') != config.app_id or body.get('user_openid') not in config.account_ids:
            raise _invalid()
        external, kind = body['user_openid'], body.get('event')
        if not isinstance(kind, str) or kind not in {'post.publish.failed', 'post.publish.complete', 'post.publish.publicly_available', 'post.publish.no_longer_publicly_available'}:
            raise _invalid('PROVIDER_EVENT_UNSUPPORTED', 422)
        if not isinstance(body.get('content'), str):
            raise _invalid()
        content = _json(body['content'])
        if content.get('publish_type') != 'DIRECT_PUBLISH':
            raise _invalid('PROVIDER_EVENT_UNSUPPORTED', 422)
        remote, post = content.get('publish_id'), content.get('post_id')
        event_at = _timestamp(body.get('create_time'), now)
        subscription = config.app_id
        if kind in {'post.publish.publicly_available', 'post.publish.no_longer_publicly_available'} and not post:
            raise _invalid()
    if not _identifier(remote) or post is not None and (not isinstance(post, str) or re.fullmatch(r'[0-9]{1,64}', post) is None):
        raise _invalid()
    # No trustworthy provider event ID is documented. A semantic hash ignores
    # incidental text, URLs, signatures and redelivery JSON formatting changes.
    # A Threads media ID has one publish and one delete lifecycle; redelivery
    # time is not event identity. TikTok visibility can change repeatedly.
    key = [config.platform, config.app_id, subscription, external, kind, remote, post,
           None if config.platform == 'threads' else int(event_at.timestamp())]
    digest = hashlib.sha256(json.dumps(key, separators=(',', ':')).encode()).hexdigest()
    return VerifiedEvent(config.platform, external, kind, remote, post, event_at, digest)


def accept_event(db: Session, event: VerifiedEvent, *, now=None):
    """Durable commit is the acknowledgement boundary; failures propagate."""
    now = utc(now or datetime.now(timezone.utc))
    with db.begin():
        account = db.scalar(select(SocialAccount).where(SocialAccount.platform == event.provider,
            SocialAccount.api_product == ('threads' if event.provider == 'threads' else 'tiktok_accounts_api'),
            SocialAccount.external_account_id == event.external_account_id,
            SocialAccount.connection_state == 'connected').with_for_update())
        if account is None:
            raise _invalid('PROVIDER_EVENT_ACCOUNT_UNAVAILABLE', 403)
        dialect = db.get_bind().dialect.name
        if dialect not in {'postgresql', 'sqlite'}:
            raise SocialError('EVENTS_UNAVAILABLE', 'Provider events require supported durable persistence.', 503)
        # A single outer-transaction INSERT avoids SQLite's first-write SAVEPOINT
        # release committing a tombstone before the acknowledgement commit.
        insert = pg_insert if dialect == 'postgresql' else sqlite_insert
        statement = insert(SocialPlatformEvent).values(provider=event.provider, dedupe_hash=event.dedupe_hash,
            account_id=account.id, event_type=event.event_type, remote_id=event.remote_id,
            post_id=event.post_id, event_at=event.event_at, received_at=now)
        result = db.execute(statement.on_conflict_do_nothing(index_elements=['provider', 'dedupe_hash']))
    return result.rowcount == 1


def process_pending_events(db: Session, *, limit=25, now=None):
    """Atomic local consumer: SKIP LOCKED and CAS never disturb worker fencing.

    Published/unknown/dispatching targets cannot be moved by event hints. Even
    a publicly_available event only advances an existing status-check deadline.
    A missing response/checkpoint cannot be recovered by speculative matching.
    """
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Event batch limit must be an integer from 1 to 100')
    now = utc(now or datetime.now(timezone.utc))
    processed = 0
    with db.begin():
        # Read hints without locks, then follow common account -> target ->
        # event lock ordering. Account ordering also serializes competing batches.
        events = db.scalars(select(SocialPlatformEvent).where(SocialPlatformEvent.processing_state == 'pending')
            .order_by(SocialPlatformEvent.account_id, SocialPlatformEvent.id).limit(limit)).all()
        for event in events:
            account = db.scalar(select(SocialAccount).where(SocialAccount.id == event.account_id,
                SocialAccount.platform == event.provider).with_for_update(skip_locked=True))
            if account is None:
                continue
            remote_match = (or_(SocialPostTarget.primary_remote_id == event.remote_id,
                SocialPostTarget.remote_refs['post_id'].as_string() == event.remote_id,
                SocialPostTarget.checkpoint['post_id'].as_string() == event.remote_id)
                if event.provider == 'threads' else or_(
                SocialPostTarget.remote_refs['share_id'].as_string() == event.remote_id,
                SocialPostTarget.checkpoint['share_id'].as_string() == event.remote_id))
            # Only already-scheduled status/reconciliation operations; no publish
            # action, checkpoint, owner, token, epoch or visibility mutation.
            candidates = db.scalars(select(SocialPostTarget).where(SocialPostTarget.account_id == event.account_id,
                SocialPostTarget.state.in_(('processing', 'reconciling')),
                SocialPostTarget.next_action.in_(('poll', 'reconcile')),
                or_(SocialPostTarget.error_code.is_(None), SocialPostTarget.error_code != 'RATE_LIMITED'),
                SocialPostTarget.lease_token.is_(None), remote_match)
                .order_by(SocialPostTarget.id).limit(2).with_for_update(skip_locked=True)).all()
            locked_event = db.scalar(select(SocialPlatformEvent).where(SocialPlatformEvent.id == event.id,
                SocialPlatformEvent.processing_state == 'pending').with_for_update(skip_locked=True))
            if locked_event is None:
                continue
            matched = False
            for target in candidates if len(candidates) == 1 else ():
                result = db.execute(update(SocialPostTarget).where(SocialPostTarget.id == target.id,
                    SocialPostTarget.state == target.state, SocialPostTarget.next_action == target.next_action,
                    SocialPostTarget.lease_token.is_(None), SocialPostTarget.lease_epoch == target.lease_epoch,
                    SocialPostTarget.next_action_at > now).values(next_action_at=now).execution_options(synchronize_session=False))
                matched = matched or result.rowcount == 1
            event.processing_state = 'processed' if matched else 'unmatched'
            event.processed_at = now
            processed += 1
    return processed


def prune_processed_events(db: Session, *, limit=100, now=None, manage_transaction=True):
    """Separate bounded maintenance authority; never grants worker DELETE."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('Retention limit must be an integer from 1 to 1000')
    if type(manage_transaction) is not bool or not manage_transaction and not db.in_transaction():
        raise ValueError('Retention must own a transaction or explicitly join an existing command transaction')
    now = utc(now or datetime.now(timezone.utc))
    with db.begin() if manage_transaction else nullcontext():
        expired = select(SocialPlatformEvent.id).where(SocialPlatformEvent.received_at < now - timedelta(days=RETENTION_DAYS),
            SocialPlatformEvent.processing_state != 'pending').order_by(SocialPlatformEvent.received_at).limit(limit)
        result = db.execute(delete(SocialPlatformEvent).where(SocialPlatformEvent.id.in_(expired)).execution_options(synchronize_session=False))
    return result.rowcount


def event_config(provider: Provider, request: Request):
    config = getattr(request.app.state, 'social_platform_events_config', {}).get(provider, EventConfig(provider))
    if not isinstance(config, EventConfig) or config.platform != provider:
        raise SocialError('EVENTS_UNAVAILABLE', 'The provider event composition is invalid.', 503)
    config.require_ready()
    return config


class EventAcknowledgement(BaseModel):
    accepted: StrictBool


router = APIRouter(prefix='/api/v1/social/platform-events', tags=['Social Provider Events'], route_class=SocialRoute)
maintenance_router = APIRouter(prefix='/api/v1/admin/social/platform-events', tags=['Admin Social Provider Events'],
    route_class=SocialRoute, dependencies=[Depends(social_admin)])


class PruneEventsCommand(StrictModel):
    limit: int = Field(default=100, strict=True, ge=1, le=1000)
    reason: Reason


class PrunedEvents(StrictModel):
    pruned: int = Field(strict=True, ge=0, le=1000)
    retention_days: Literal[30]


@maintenance_router.post('/prune', response_model=PrunedEvents)
def prune_events(request: Request, body: PruneEventsCommand, key: IdempotencyKey,
                admin=Depends(social_admin), db: Session = Depends(get_db)):
    svc = SocialService(db)

    def prune():
        count = prune_processed_events(db, limit=body.limit, now=svc.now(), manage_transaction=False)
        svc.audit('provider_events.pruned', reason=body.reason,
            details={'pruned': count, 'limit': body.limit, 'retention_days': RETENTION_DAYS})
        return {'pruned': count, 'retention_days': RETENTION_DAYS}

    status, result = svc.command(actor=UUID(admin.id), route=request.method + ' ' + request.url.path,
        key=key, body=body.model_dump(mode='json'), request_id=request.state.social_request_id, action=prune)
    return JSONResponse(status_code=status, content=PrunedEvents.model_validate(result).model_dump(mode='json'), headers=NO_STORE)


@router.get('/threads', response_class=PlainTextResponse)
def challenge(request: Request):
    config = event_config('threads', request)
    params = request.query_params
    if (any(len(params.getlist(key)) != 1 for key in ('hub.mode', 'hub.verify_token', 'hub.challenge'))
            or params.get('hub.mode') != 'subscribe'
            or not hmac.compare_digest(params.get('hub.verify_token', '').encode(), config.verify_token.encode())
            or re.fullmatch(r'[0-9]{1,32}', params.get('hub.challenge', '')) is None):
        raise _invalid('PROVIDER_CHALLENGE_INVALID', 403)
    return params['hub.challenge']


@router.post('/{provider}', response_model=EventAcknowledgement)
async def callback(provider: Provider, request: Request, db: Session = Depends(get_db)):
    config = event_config(provider, request)
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise _invalid('PROVIDER_CONTENT_TYPE_INVALID', 415)
    header = 'x-hub-signature-256' if provider == 'threads' else 'tiktok-signature'
    signatures = request.headers.getlist(header)
    if len(signatures) != 1 or request.headers.get('content-encoding', 'identity') != 'identity':
        raise _invalid('PROVIDER_SIGNATURE_INVALID', 403)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise _invalid('PROVIDER_EVENT_TOO_LARGE', 413)
        body.extend(chunk)
    event = verify_event(config, bytes(body), signatures[0])
    await run_in_threadpool(accept_event, db, event)
    return {'accepted': True}

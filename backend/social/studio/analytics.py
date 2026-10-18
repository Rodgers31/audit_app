"""Explicit, bounded observation collection; no implicit paid/provider transport."""
from datetime import datetime, timedelta, timezone
import json
import multiprocessing
import os
import signal
from uuid import uuid4

from sqlalchemy import func, select, text

from ..contracts import canonical_json, canonical_hash
from ..models import SocialAccount, SocialAuditEvent, SocialPostTarget
from ..service import SocialError, iso, utc
from .contracts import Metric, MetricRequest
from .models import MetricCollection, MetricObservation
from .service import studio_lock


def _port_child(port, request, output):
    """An owned process/session is reaped on deadline, including nested tools."""
    os.setsid()
    signal.signal(signal.SIGALRM, lambda *_: os.killpg(os.getpgrp(), signal.SIGKILL))
    signal.alarm(10)
    try:
        values = port.collect(request)
        if type(values) is not tuple or not 1 <= len(values) <= request.max_records:
            raise ValueError('Invalid metric batch')
        raw = canonical_json([Metric.model_validate(v).model_dump(mode='json') for v in values]).encode()
        if len(raw) > request.max_response_bytes:
            raise ValueError('Oversize metric batch')
        output.send_bytes(raw)
    except Exception:
        # Provider exceptions may contain credentials; expose only a failed exit.
        raise SystemExit(2) from None
    finally:
        output.close()


def bounded_collect(port, request):
    # Spawn avoids inheriting database sockets/locks from the operator. Ports
    # must be importable/pickleable, with no platform import assumed here.
    context = multiprocessing.get_context('spawn')
    incoming, outgoing = context.Pipe(duplex=False)
    process = context.Process(target=_port_child, args=(port, request, outgoing))
    started = False
    try:
        process.start()
        started = True
        outgoing.close()
        if not incoming.poll(10):
            raise TimeoutError('Provider collection deadline exceeded')
        raw = incoming.recv_bytes(request.max_response_bytes)
        process.join(timeout=1)
        if process.exitcode != 0:
            raise ValueError('Provider collection process failed')
        # A child exiting successfully does not prove its descendants exited.
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise ValueError('Provider transport retained child processes')
        return tuple(Metric.model_validate(v) for v in json.loads(raw))
    finally:
        outgoing.close()
        if started:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                if process.is_alive():
                    process.kill()
            process.join(timeout=2)
        incoming.close()
        process.close()


def collect(factory, target_id, ports, *, enabled=False, authorization=None):
    if type(enabled) is not bool or not enabled:
        raise SocialError('ANALYTICS_DISABLED', 'Metrics collection has not been enabled.', 503)
    now = datetime.now(timezone.utc)
    with factory() as db, db.begin():
        studio_lock(db)
        target = db.get(SocialPostTarget, target_id)
        if target is None:
            raise SocialError('NOT_FOUND', 'Published target not found.', 404)
        account = db.scalar(select(SocialAccount).where(SocialAccount.id == target.account_id).with_for_update())
        if target.state != 'published' or target.visibility_state != 'public' or not target.primary_remote_id:
            raise SocialError('METRICS_NOT_PUBLIC', 'Only confirmed public targets can be collected.')
        from .native_metrics import AnalyticsRuntime
        native = type(ports) is AnalyticsRuntime
        request = MetricRequest(platform=account.platform, account_id=account.id, target_id=target.id, remote_id=target.primary_remote_id, deadline=now + timedelta(seconds=10))
        if account.platform == 'x':
            raise SocialError('METRICS_UNAVAILABLE', 'X metrics are unavailable at zero budget; no request is authorized.', 503)
        port = ports.prepare(db, target, authorization, request) if native else ports.get(account.platform)
        # No X reads under the zero-spend contract, even if a port is installed.
        if account.platform == 'x' or port is None or port.platform != account.platform or port.zero_cost is not True:
            raise SocialError('METRICS_UNAVAILABLE', 'An authorized zero-cost provider metrics port is unavailable.', 503)
        if account.connection_state != 'connected':
            raise SocialError('METRICS_UNAVAILABLE', 'Reconnect the provider account before collection.', 503)
        from .platform_metrics import check_read_hold
        latest = db.scalar(select(MetricCollection).where(MetricCollection.account_id == account.id).order_by(MetricCollection.created_at.desc(), MetricCollection.id.desc()).limit(1))
        if latest is not None:
            check_read_hold(latest.reason, now)
            if native and account.platform in {'threads', 'tiktok'} and latest.state == 'reserved':
                raise SocialError('METRICS_COLLECTION_HELD', 'An interrupted metrics read retains its reservation; inspect history before any new collection.', 409)
        quota = db.scalar(select(func.count()).select_from(MetricCollection).where(MetricCollection.account_id == account.id, MetricCollection.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0)))
        recent = db.scalar(select(MetricCollection.id).where(MetricCollection.account_id == account.id, MetricCollection.created_at > now - timedelta(hours=1)).limit(1))
        if quota >= 24 or recent:
            raise SocialError('METRICS_QUOTA', 'Collection is limited to one account read per hour and 24 per UTC day.', 429)
        request = MetricRequest(platform=account.platform, account_id=account.id, target_id=target.id, remote_id=target.primary_remote_id, deadline=now + timedelta(seconds=10))
        row = MetricCollection(id=uuid4(), account_id=account.id, target_id=target.id, platform=account.platform, remote_id=target.primary_remote_id, state='reserved', created_at=now)
        db.add(row)
        collection_id = row.id
        if native:
            audit = SocialAuditEvent(id=uuid4(), actor_kind='metrics', action='metrics.reserved', target_id=target_id,
                details={'collection_id': str(row.id), 'authorization': authorization.model_dump(mode='json'),
                         'request_hash': canonical_hash(request.model_dump(mode='json'))},
                request_id=str(collection_id))
            db.add(audit)
            _verify_writes(db, row, audit)
    # The reservation is durable before the provider read; failure consumes quota.
    # Platform transport owns deadline/byte enforcement; fixture ports are never
    # automatically registered as native adapters.
    try:
        values = bounded_collect(port, request)
        if type(values) is not tuple or not 1 <= len(values) <= request.max_records:
            raise ValueError('Invalid metric batch')
        metrics = tuple(Metric.model_validate(v) for v in values)
        completed = datetime.now(timezone.utc)
        if completed > request.deadline or len(canonical_json([m.model_dump(mode='json') for m in metrics]).encode()) > request.max_response_bytes:
            raise ValueError('Collection exceeded bounds')
        keys = [(m.name, m.period, m.window_start, m.window_end) for m in metrics]
        if len(set(keys)) != len(keys) or any(not now - timedelta(minutes=1) <= m.collected_at <= completed for m in metrics):
            raise ValueError('Duplicate or incoherent metric observations')
    except Exception:
        with factory() as db, db.begin():
            row = db.get(MetricCollection, collection_id)
            row.state, row.reason = 'failed', 'Provider collection failed or returned invalid/late observations.'
        raise SocialError('METRICS_COLLECTION_FAILED', 'Provider collection failed; its quota reservation is retained.', 502) from None
    with factory() as db, db.begin():
        studio_lock(db)
        if native:
            target = db.scalar(select(SocialPostTarget).where(SocialPostTarget.id == target_id).with_for_update().execution_options(populate_existing=True))
            try:
                ports.material(db, target, authorization)
            except Exception:
                row = db.get(MetricCollection, collection_id)
                row.state, row.reason = 'failed', 'Authorization changed during collection; observations were discarded.'
                # Commit failure evidence before raising below.
                failed_authorization = True
            else:
                failed_authorization = False
        else:
            failed_authorization = False
        row = db.scalar(select(MetricCollection).where(MetricCollection.id == collection_id).with_for_update())
        if failed_authorization:
            db.flush()
        else:
            _save_observations(db, row, metrics, target_id, collection_id)
    if failed_authorization:
        raise SocialError('METRICS_AUTHORIZATION_CHANGED', 'Authorization changed; observations were discarded and quota retained.')
    return collection_id


def _save_observations(db, row, metrics, target_id, collection_id):
    if row.state != 'reserved':
        raise SocialError('METRICS_COLLECTION_CONFLICT', 'The collection reservation changed.')
    from .platform_metrics import RATE_HOLD, RATE_PREFIX
    limited = {m.reason for m in metrics if m.reason == RATE_HOLD or isinstance(m.reason, str) and m.reason.startswith(RATE_PREFIX)}
    if len(limited) > 1:
        raise SocialError('METRICS_COLLECTION_FAILED', 'Inconsistent provider throttle observations.')
    row.state = 'unavailable' if row.platform in {'threads', 'tiktok'} and all(m.status == 'unavailable' for m in metrics) else 'collected'
    row.reason = next(iter(limited)) if limited else None
    written = [MetricObservation(id=uuid4(), collection_id=row.id, metric=metric.model_dump(mode='json')) for metric in metrics]
    db.add_all(written)
    audit = SocialAuditEvent(id=uuid4(), actor_kind='metrics', action='metrics.collected', target_id=target_id, details={'collection_id': str(row.id), 'observations': len(metrics)}, request_id=str(collection_id))
    db.add(audit)
    _verify_writes(db, row, audit, written)


def _verify_writes(db, row, audit, written=()):
    """Database readback, including deferred triggers, precedes success/dispatch."""
    expected = (row.account_id, row.target_id, row.platform, row.remote_id, row.state, row.reason, utc(row.created_at))
    audit_expected = (audit.action, audit.actor_kind, audit.target_id, audit.request_id, canonical_json(audit.details))
    observations_expected = {m.id: canonical_json(m.metric) for m in written}
    db.flush()
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
    actual = db.execute(select(MetricCollection.account_id, MetricCollection.target_id, MetricCollection.platform,
        MetricCollection.remote_id, MetricCollection.state, MetricCollection.reason, MetricCollection.created_at).where(MetricCollection.id == row.id)).one_or_none()
    stored = db.execute(select(SocialAuditEvent.action, SocialAuditEvent.actor_kind, SocialAuditEvent.target_id,
        SocialAuditEvent.request_id, SocialAuditEvent.details).where(SocialAuditEvent.id == audit.id)).one_or_none()
    if actual is None or (*actual[:6], utc(actual[6])) != expected or stored is None or (*stored[:4], canonical_json(stored[4])) != audit_expected:
        raise SocialError('METRICS_PERSISTENCE_FAILED', 'Stored collection or audit differs; dispatch/success refused.', 503)
    if written:
        actual_metrics = db.execute(select(MetricObservation.id, MetricObservation.metric).where(MetricObservation.collection_id == row.id)).all()
        if {key: canonical_json(value) for key, value in actual_metrics} != observations_expected:
            raise SocialError('METRICS_PERSISTENCE_FAILED', 'Stored observations differ; success refused.', 503)


def observations(db, target_id, page=1, now=None):
    if type(page) is not int or page < 1:
        raise SocialError('INVALID_REQUEST', 'Use a positive observation page.', 422)
    now = now or datetime.now(timezone.utc)
    target = db.get(SocialPostTarget, target_id)
    if not target:
        raise SocialError('NOT_FOUND', 'Target not found.', 404)
    account = db.get(SocialAccount, target.account_id)
    rows = db.scalars(select(MetricCollection).where(MetricCollection.target_id == target_id).order_by(MetricCollection.created_at.desc(), MetricCollection.id).offset((page - 1) * 10).limit(11)).all()
    values = db.execute(select(MetricObservation.collection_id, MetricObservation.metric).where(MetricObservation.collection_id.in_([r.id for r in rows[:10]]))).all() if rows else []
    by_collection = {}
    for collection_id, raw in values:
        metric = Metric.model_validate(raw)
        by_collection.setdefault(collection_id, []).append({**metric.model_dump(mode='json'), 'freshness': 'stale' if now >= metric.available_until else 'fresh'})
    return {'target_id': str(target_id), 'platform': account.platform, 'availability': 'observed' if by_collection else 'unavailable', 'reason': None if by_collection else 'No provider observations have been collected on this page.', 'collections': [{'id': str(r.id), 'state': r.state, 'reason': r.reason, 'remote_id': r.remote_id, 'created_at': iso(r.created_at), 'metrics': by_collection.get(r.id, [])} for r in rows[:10]], 'page': page, 'has_more': len(rows) > 10}

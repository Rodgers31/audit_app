"""Sanitized signed fixtures. Never contact provider, credentials or live APIs."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event as sql_event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from social.http_boundary import get_db
from social.models import Base, SocialAccount, SocialPost, SocialPostRevision, SocialPublication, SocialPostTarget
from social.platform_events import (EventConfig, MAX_BODY_BYTES, SocialPlatformEvent,
    accept_event, process_pending_events, prune_processed_events, router, verify_event)
from social.service import SocialError

NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
THREADS = EventConfig('threads', True, True, True, '123', 'fixture-secret', 'fixture-verify', (('234', '789'),))
TIKTOK = EventConfig('tiktok', True, True, True, 'fixture-app', 'fixture-secret', account_ids=('owned-openid',))


def payload(provider='threads', **updates):
    body = ({'app_id': '123', 'topic': 'interaction', 'target_id': '789', 'time': int(NOW.timestamp()),
             'subscription_id': '234', 'values': {'field': 'publish', 'value': {'id': '890', 'text': 'Do not retain this text', 'permalink': 'https://example.test/never-store'}}}
            if provider == 'threads' else {'client_key': 'fixture-app', 'event': 'post.publish.publicly_available',
                'create_time': int(NOW.timestamp()), 'user_openid': 'owned-openid',
                'content': json.dumps({'publish_id': 'v_pub_url~v1.42', 'post_id': '890', 'publish_type': 'DIRECT_PUBLISH'})})
    body.update(updates)
    return json.dumps(body, separators=(',', ':')).encode()


def signature(config, raw, *, timestamp=None):
    if config.platform == 'threads':
        return 'sha256=' + hmac.new(config.app_secret.encode(), raw, hashlib.sha256).hexdigest()
    stamp = str(timestamp if timestamp is not None else int(NOW.timestamp()))
    return 't=' + stamp + ',s=' + hmac.new(config.app_secret.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()


@pytest.fixture
def db():
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    @sql_event.listens_for(engine, 'connect')
    def fk(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name.startswith('social_')])
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def target(db, *, provider='threads', external=None, state='processing', action='poll', remote='890', lease=False):
    with db.begin():
        account = SocialAccount(platform=provider, api_product='threads' if provider == 'threads' else 'tiktok_accounts_api',
            connection_method='oauth', external_account_id=external or ('789' if provider == 'threads' else 'owned-openid'),
            display_name='Sanitized owned account', connection_state='connected')
        db.add(account)
        db.flush()
        post = SocialPost(title='fixture', content_type='text')
        db.add(post)
        db.flush()
        revision = SocialPostRevision(post_id=post.id, revision_no=1, document={}, content_hash='a' * 64)
        db.add(revision)
        db.flush()
        publication = SocialPublication(post_id=post.id, revision_id=revision.id, approved_by=uuid4(), approved_at=NOW, approved_hash='a' * 64)
        db.add(publication)
        db.flush()
        row = SocialPostTarget(publication_id=publication.id, account_id=account.id, resolved_payload={}, payload_hash='a' * 64,
            capability_version='fixture', state=state, next_action=action, next_action_at=NOW + timedelta(hours=1),
            lease_token=uuid4() if lease else None, lease_epoch=3, lease_owner='owner' if lease else None,
            checkpoint={'post_id': remote} if provider == 'threads' else {'share_id': remote},
            remote_refs={'post_id': remote} if provider == 'threads' else {'share_id': remote})
        if state == 'published':
            row.primary_remote_id, row.confirmation_kind, row.published_at, row.visibility_state = remote, 'fixture_proof', NOW, 'public'
        db.add(row)
        db.flush()
    return row


@pytest.mark.parametrize('config', [THREADS, TIKTOK], ids=['threads', 'tiktok'])
def test_raw_signature_and_semantic_dedup(config):
    raw = payload(config.platform)
    result = verify_event(config, raw, signature(config, raw), now=NOW)
    assert result.remote_id == ('890' if config.platform == 'threads' else 'v_pub_url~v1.42')
    changed_format = json.dumps(json.loads(raw), indent=2).encode()
    with pytest.raises(SocialError, match='PROVIDER_SIGNATURE_INVALID'):
        verify_event(config, changed_format, signature(config, raw), now=NOW)
    assert verify_event(config, changed_format, signature(config, changed_format), now=NOW).dedupe_hash == result.dedupe_hash


@pytest.mark.parametrize('config', [THREADS, TIKTOK], ids=['threads', 'tiktok'])
@pytest.mark.parametrize('field,value', [('enabled', False), ('enabled', 1), ('subscription_verified', False), ('product_access_verified', False), ('app_secret', '')])
def test_every_entry_point_fails_closed(config, field, value):
    raw = payload(config.platform)
    with pytest.raises(SocialError, match='EVENTS_UNAVAILABLE'):
        verify_event(replace(config, **{field: value}), raw, signature(config, raw), now=NOW)


@pytest.mark.parametrize('delay', [-1, 301, 86400])
def test_tiktok_signed_delivery_timestamp_rejects_future_and_replay(delay):
    raw = payload('tiktok')
    with pytest.raises(SocialError, match='PROVIDER_EVENT_EXPIRED'):
        verify_event(TIKTOK, raw, signature(TIKTOK, raw, timestamp=int(NOW.timestamp()) - delay), now=NOW)


@pytest.mark.parametrize('config', [THREADS, TIKTOK], ids=['threads', 'tiktok'])
def test_unknown_app_or_subscription_or_account_rejected(config):
    mutations = ({'app_id': 'other'}, {'subscription_id': 'other'}) if config.platform == 'threads' else ({'client_key': 'other'}, {'user_openid': 'other'})
    for update in mutations:
        raw = payload(config.platform, **update)
        with pytest.raises(SocialError):
            verify_event(config, raw, signature(config, raw), now=NOW)


@pytest.mark.parametrize('config', [THREADS, TIKTOK], ids=['threads', 'tiktok'])
def test_signed_duplicate_json_keys_and_oversize_refused(config):
    raw = b'{"app_id":"123","app_id":"456"}'
    with pytest.raises(SocialError):
        verify_event(config, raw, signature(config, raw), now=NOW)
    with pytest.raises(SocialError, match='PROVIDER_EVENT_TOO_LARGE'):
        verify_event(config, b' ' * (MAX_BODY_BYTES + 1), None, now=NOW)


@pytest.mark.parametrize('config', [THREADS, TIKTOK], ids=['threads', 'tiktok'])
def test_persist_dedup_restart_and_target_only_status_nudge(db, config):
    expected = '890' if config.platform == 'threads' else 'v_pub_url~v1.42'
    row = target(db, provider=config.platform, remote=expected)
    sibling = target(db, provider=config.platform, external='different-owned-account', remote=expected)
    raw = payload(config.platform)
    verified = verify_event(config, raw, signature(config, raw), now=NOW)
    assert accept_event(db, verified, now=NOW) is True
    assert accept_event(db, verified, now=NOW) is False
    assert process_pending_events(db, now=NOW) == 1
    db.expire_all()
    assert db.get(SocialPostTarget, row.id).next_action_at.replace(tzinfo=timezone.utc) == NOW
    assert db.get(SocialPostTarget, sibling.id).next_action_at.replace(tzinfo=timezone.utc) == NOW + timedelta(hours=1)
    assert row.state == 'processing' and row.next_action == 'poll' and row.visibility_state == 'unknown' and row.lease_epoch == 3
    db.rollback()
    # A new session is the durable restart boundary, not an in-memory seen set.
    with Session(db.bind) as restarted:
        assert accept_event(restarted, verified, now=NOW) is False
        assert process_pending_events(restarted, now=NOW) == 0
        stored = restarted.scalar(select(SocialPlatformEvent))
        assert stored.processing_state == 'processed'
        assert not hasattr(stored, 'payload')


@pytest.mark.parametrize('state,action,lease', [('published', None, False), ('processing', 'publish', False), ('processing', 'poll', True), ('outcome_unknown', 'reconcile', False), ('dispatching', 'poll', False)])
def test_events_never_rewrite_published_uncertain_dispatching_or_leased_targets(db, state, action, lease):
    row = target(db, state=state, action=action, lease=lease)
    before = (row.state, row.next_action, row.next_action_at, row.lease_token, row.lease_epoch, row.visibility_state)
    raw = payload()
    accept_event(db, verify_event(THREADS, raw, signature(THREADS, raw), now=NOW), now=NOW)
    process_pending_events(db, now=NOW)
    db.expire_all()
    assert (row.state, row.next_action, row.next_action_at.replace(tzinfo=timezone.utc), row.lease_token, row.lease_epoch, row.visibility_state) == before


def test_callback_routes_default_unavailable_and_challenge_only_configured(db):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    path = '/api/v1/social/platform-events/threads'
    query = {'hub.mode': 'subscribe', 'hub.verify_token': 'fixture-verify', 'hub.challenge': '42'}
    assert client.get(path, params=query).status_code == 503
    app.state.social_platform_events_config = {'threads': THREADS}
    response = client.get(path, params=query)
    assert response.status_code == 200 and response.text == '42'
    assert 'no-store' in response.headers['cache-control']
    assert client.get(path, params={**query, 'hub.verify_token': 'wrong'}).status_code == 403
    assert client.get(path, params=list(query.items()) + [('hub.challenge', '43')]).status_code == 403


def test_http_callback_commits_before_ack_and_does_no_status_transition(db):
    row = target(db)
    app = FastAPI()
    app.state.social_platform_events_config = {'threads': THREADS}
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    body = json.loads(payload())
    body['time'] = int(datetime.now(timezone.utc).timestamp())
    raw = json.dumps(body).encode()
    headers = {'content-type': 'application/json', 'x-hub-signature-256': signature(THREADS, raw)}
    path = '/api/v1/social/platform-events/threads'
    assert client.post(path, content=raw, headers=headers).status_code == 200
    assert not db.in_transaction()
    with Session(db.bind) as separate:
        assert separate.scalar(select(func.count()).select_from(SocialPlatformEvent)) == 1
        assert separate.get(SocialPostTarget, row.id).next_action_at.replace(tzinfo=timezone.utc) == NOW + timedelta(hours=1)
    assert client.post(path, content=b' ' * (MAX_BODY_BYTES + 1), headers=headers).status_code == 413
    assert client.post(path, content=raw, headers={**headers, 'x-hub-signature-256': 'sha256=' + '0' * 64}).status_code == 403


def test_failed_commit_cannot_ack_or_leave_dedup_tombstone(db):
    target(db)
    raw = payload()
    verified = verify_event(THREADS, raw, signature(THREADS, raw), now=NOW)
    def fail_commit(session):
        if not session.in_nested_transaction():
            raise RuntimeError('fixture commit unavailable')
    sql_event.listen(db, 'before_commit', fail_commit)
    try:
        with pytest.raises(RuntimeError, match='fixture commit unavailable'):
            accept_event(db, verified, now=NOW)
    finally:
        sql_event.remove(db, 'before_commit', fail_commit)
    with Session(db.bind) as restarted:
        assert restarted.scalar(select(func.count()).select_from(SocialPlatformEvent)) == 0
    assert accept_event(db, verified, now=NOW) is True


@pytest.mark.parametrize('provider,update', [
    ('threads', {'subscription_id': []}),
    ('threads', {'values': {'field': [], 'value': {'id': '890'}}}),
    ('threads', {'values': {'field': 'publish', 'value': {'id': 'bad/id'}}}),
    ('tiktok', {'event': []}),
    ('tiktok', {'content': '{"publish_id":"42","publish_type":"UPLOAD"}'}),
    ('tiktok', {'content': '{"publish_id":"42","publish_type":"DIRECT_PUBLISH"}'}),
], ids=['subscription-type', 'threads-event-type', 'threads-id', 'tiktok-event-type', 'draft-event', 'missing-public-post'])
def test_malformed_signed_contract_refused_without_internal_error(provider, update):
    config = THREADS if provider == 'threads' else TIKTOK
    raw = payload(provider, **update)
    with pytest.raises(SocialError):
        verify_event(config, raw, signature(config, raw), now=NOW)


def test_retention_bounded_and_does_not_delete_recent_or_pending_events(db):
    target(db)
    raw = payload()
    verified = verify_event(THREADS, raw, signature(THREADS, raw), now=NOW)
    accept_event(db, verified, now=NOW)
    assert prune_processed_events(db, now=NOW + timedelta(days=31)) == 0
    process_pending_events(db, now=NOW)
    assert prune_processed_events(db, now=NOW + timedelta(days=29)) == 0
    assert prune_processed_events(db, limit=1, now=NOW + timedelta(days=31)) == 1
    assert prune_processed_events(db, limit=1, now=NOW + timedelta(days=31)) == 0


@pytest.mark.parametrize('limit', [True, 0, 101, 1.5, '25'])
def test_consumer_rejects_invalid_batch_limits(db, limit):
    with pytest.raises(ValueError):
        process_pending_events(db, limit=limit, now=NOW)


@pytest.mark.parametrize('provider', ['threads', 'tiktok'])
@pytest.mark.parametrize('stamp', [True, '1792152000', -1, 10**20])
def test_event_time_is_strict_bounded_integer(provider, stamp):
    config = THREADS if provider == 'threads' else TIKTOK
    raw = payload(provider, **{('time' if provider == 'threads' else 'create_time'): stamp})
    with pytest.raises(SocialError):
        verify_event(config, raw, signature(config, raw), now=NOW)


def test_threads_redelivery_time_is_not_a_second_event():
    first, redelivery = payload(), payload(time=int(NOW.timestamp()) + 120)
    expected = verify_event(THREADS, first, signature(THREADS, first), now=NOW)
    actual = verify_event(THREADS, redelivery, signature(THREADS, redelivery), now=NOW + timedelta(seconds=120))
    assert expected.dedupe_hash == actual.dedupe_hash


def test_callback_commit_failure_returns_safe_error_and_retries(db):
    target(db)
    app = FastAPI()
    app.include_router(router)
    app.state.social_platform_events_config = {'threads': THREADS}
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    raw = payload(time=int(datetime.now(timezone.utc).timestamp()))
    def fail_commit(session):
        raise RuntimeError('fixture-secret-do-not-expose')
    headers = {'content-type': 'application/json', 'x-hub-signature-256': signature(THREADS, raw)}
    sql_event.listen(db, 'before_commit', fail_commit)
    try:
        response = client.post('/api/v1/social/platform-events/threads', content=raw, headers=headers)
        assert response.status_code == 500
        assert 'fixture-secret' not in response.text
    finally:
        sql_event.remove(db, 'before_commit', fail_commit)
    assert client.post('/api/v1/social/platform-events/threads', content=raw, headers=headers).status_code == 200


def test_tiktok_http_callback_and_duplicate_header_refusal(db):
    target(db, provider='tiktok', remote='v_pub_url~v1.42')
    app = FastAPI()
    app.include_router(router)
    app.state.social_platform_events_config = {'tiktok': TIKTOK}
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    timestamp = int(datetime.now(timezone.utc).timestamp())
    raw = payload('tiktok', create_time=timestamp)
    headers = [('content-type', 'application/json'), ('tiktok-signature', signature(TIKTOK, raw, timestamp=timestamp))]
    assert client.post('/api/v1/social/platform-events/tiktok', content=raw, headers=headers).status_code == 200
    assert client.post('/api/v1/social/platform-events/tiktok', content=raw, headers=headers + [headers[1]]).status_code == 403


def retention_client(db, *, authenticated=True, aggregate=False):
    from social import platform_events
    from social.http_boundary import require_admin
    from supabase_auth import AdminUser
    app = FastAPI()
    if aggregate:
        from social.api import router as aggregate_router
        app.include_router(aggregate_router)
    else:
        app.include_router(platform_events.maintenance_router)
    def isolated():
        with Session(db.bind, expire_on_commit=False) as request_db:
            yield request_db
    app.dependency_overrides[get_db] = isolated
    if authenticated:
        app.dependency_overrides[require_admin] = lambda: AdminUser(id='00000000-0000-4000-8000-000000000042', email=None, roles=['admin'])
    return TestClient(app)


def expired_event(db, *, processed=True):
    from dataclasses import replace as event_replace
    raw = payload()
    verified = verify_event(THREADS, raw, signature(THREADS, raw), now=NOW)
    verified = event_replace(verified, dedupe_hash=uuid4().hex * 2)
    accept_event(db, verified, now=datetime.now(timezone.utc) - timedelta(days=31))
    if processed:
        with db.begin():
            row = db.scalar(select(SocialPlatformEvent).where(SocialPlatformEvent.dedupe_hash == verified.dedupe_hash))
            row.processing_state, row.processed_at = 'processed', datetime.now(timezone.utc)
    return verified.dedupe_hash


def test_admin_retention_auth_idempotency_audit_and_batch_bound(db):
    from social.models import SocialAuditEvent, SocialCommandReceipt
    target(db)
    expired_event(db)
    expired_event(db)
    pending_hash = expired_event(db, processed=False)
    path = '/api/v1/admin/social/platform-events/prune'
    body = {'limit': 1, 'reason': 'Expire processed provider event hints'}
    headers = {'Idempotency-Key': str(uuid4())}
    assert retention_client(db, authenticated=False).post(path, json=body, headers=headers).status_code in {401, 403}
    client = retention_client(db)
    first = client.post(path, json=body, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json() == {'pruned': 1, 'retention_days': 30}
    assert first.headers['cache-control'] == 'private, no-store'
    assert client.post(path, json=body, headers=headers).json() == first.json()
    assert client.post(path, json={**body, 'limit': 2}, headers=headers).status_code == 409
    with Session(db.bind) as check:
        assert check.scalar(select(func.count()).select_from(SocialPlatformEvent)) == 2
        assert check.scalar(select(SocialPlatformEvent).where(SocialPlatformEvent.dedupe_hash == pending_hash)).processing_state == 'pending'
        audit = check.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action == 'provider_events.pruned')).all()
        assert len(audit) == 1 and audit[0].reason == body['reason']
        assert audit[0].details == {'pruned': 1, 'limit': 1, 'retention_days': 30}
        assert check.scalar(select(func.count()).select_from(SocialCommandReceipt)) == 1


@pytest.mark.parametrize('body', [
    {'limit': True, 'reason': 'test'}, {'limit': 0, 'reason': 'test'}, {'limit': 1001, 'reason': 'test'},
    {'limit': 1, 'reason': ''}, {'limit': 1, 'reason': 'test', 'cutoff': '2099-01-01'},
], ids=['bool-limit', 'zero-limit', 'excess-limit', 'empty-reason', 'caller-cutoff'])
def test_admin_retention_rejects_bad_commands(db, body):
    response = retention_client(db).post('/api/v1/admin/social/platform-events/prune', json=body,
        headers={'Idempotency-Key': str(uuid4())})
    assert response.status_code == 422


def test_admin_retention_commit_failure_restores_events_audit_and_receipt(db):
    from social.models import SocialAuditEvent, SocialCommandReceipt
    target(db)
    expired_event(db)
    def refuse_commit(session):
        raise RuntimeError('fixture retention commit unavailable')
    sql_event.listen(Session, 'before_commit', refuse_commit)
    try:
        response = retention_client(db).post('/api/v1/admin/social/platform-events/prune',
            json={'limit': 1, 'reason': 'Expire processed provider event hints'}, headers={'Idempotency-Key': str(uuid4())})
        assert response.status_code == 500
    finally:
        sql_event.remove(Session, 'before_commit', refuse_commit)
    with Session(db.bind) as check:
        assert check.scalar(select(func.count()).select_from(SocialPlatformEvent)) == 1
        assert check.scalar(select(func.count()).select_from(SocialAuditEvent)) == 0
        assert check.scalar(select(func.count()).select_from(SocialCommandReceipt)) == 0


def test_actual_worker_event_wrapper_commits_outer_connection_transaction(db, monkeypatch):
    """Real repository/consumer; only global PG authority SQL is a local double."""
    from social.worker.config import WorkerConfig
    from social.worker.repository import QueueRepository
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    row = target(db)
    with db.begin():
        row.next_action_at = future
    raw = payload()
    accept_event(db, verify_event(THREADS, raw, signature(THREADS, raw), now=NOW), now=NOW)
    repo = QueueRepository(db.bind, WorkerConfig('postgresql://fixture@localhost/social_worker_test'), uuid4())
    authority_connections = []
    def local_authority(connection):
        assert connection.in_transaction()
        authority_connections.append(connection)
    monkeypatch.setattr(repo, '_authority', local_authority)
    assert repo.process_provider_events() == 1
    assert len(authority_connections) == 1
    with Session(db.bind) as check:
        assert check.scalar(select(SocialPlatformEvent)).processing_state == 'processed'
        result = check.get(SocialPostTarget, row.id)
        assert result.next_action_at.replace(tzinfo=timezone.utc) < future
        assert result.state == 'processing' and result.next_action == 'poll' and result.lease_epoch == 3


def test_worker_event_wrapper_refuses_authority_before_consumption(db, monkeypatch):
    from social.worker.config import WorkerConfig
    from social.worker.ownership import AuthorityLost
    from social.worker.repository import QueueRepository
    target(db)
    raw = payload()
    accept_event(db, verify_event(THREADS, raw, signature(THREADS, raw), now=NOW), now=NOW)
    repo = QueueRepository(db.bind, WorkerConfig('postgresql://fixture@localhost/social_worker_test'), uuid4())
    def absent_authority(connection):
        raise AuthorityLost('fixture refused authority')
    monkeypatch.setattr(repo, '_authority', absent_authority)
    with pytest.raises(AuthorityLost):
        repo.process_provider_events()
    with Session(db.bind) as check:
        assert check.scalar(select(SocialPlatformEvent)).processing_state == 'pending'


def test_worker_event_wrapper_outer_commit_failure_rolls_back_consumer(db, monkeypatch):
    from social.worker.config import WorkerConfig
    from social.worker.repository import QueueRepository
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    row = target(db)
    with db.begin():
        row.next_action_at = future
    raw = payload()
    accept_event(db, verify_event(THREADS, raw, signature(THREADS, raw), now=NOW), now=NOW)
    repo = QueueRepository(db.bind, WorkerConfig('postgresql://fixture@localhost/social_worker_test'), uuid4())
    monkeypatch.setattr(repo, '_authority', lambda connection: None)
    def refuse_commit(connection):
        raise RuntimeError('fixture outer connection commit unavailable')
    sql_event.listen(db.bind, 'commit', refuse_commit)
    try:
        with pytest.raises(RuntimeError, match='fixture outer connection commit unavailable'):
            repo.process_provider_events()
    finally:
        sql_event.remove(db.bind, 'commit', refuse_commit)
    with Session(db.bind) as check:
        assert check.scalar(select(SocialPlatformEvent)).processing_state == 'pending'
        assert check.get(SocialPostTarget, row.id).next_action_at.replace(tzinfo=timezone.utc) == future


def test_retention_requires_idempotency_header_and_explicit_transaction_join(db):
    client = retention_client(db)
    assert client.post('/api/v1/admin/social/platform-events/prune', json={'reason': 'Expire processed hints'}).status_code == 422
    with pytest.raises(ValueError, match='own a transaction'):
        prune_processed_events(db, manage_transaction=False)
    with pytest.raises(ValueError, match='own a transaction'):
        prune_processed_events(db, manage_transaction=1)


def test_aggregate_retention_dispatch_is_authenticated_and_single_prefix(db):
    path = '/api/v1/admin/social/platform-events/prune'
    body = {'reason': 'Expire processed provider event hints'}
    headers = {'Idempotency-Key': str(uuid4())}
    assert retention_client(db, authenticated=False, aggregate=True).post(path, json=body, headers=headers).status_code in {401, 403}
    response = retention_client(db, aggregate=True).post(path, json=body, headers=headers)
    assert response.status_code == 200
    assert response.json() == {'pruned': 0, 'retention_days': 30}


@pytest.mark.parametrize('provider',['threads','tiktok'])
def test_verified_event_cannot_shorten_a_durable_provider_rate_hold(db,provider):
    config=THREADS if provider=='threads' else TIKTOK
    remote='890' if provider=='threads' else 'v_pub_url~v1.42'
    row=target(db,provider=provider,remote=remote)
    with db.begin():
        row.error_code='RATE_LIMITED'
        row.next_action_at=NOW+timedelta(hours=6)
    raw=payload(provider)
    verified=verify_event(config,raw,signature(config,raw),now=NOW)
    accept_event(db,verified,now=NOW)
    process_pending_events(db,now=NOW)
    db.expire_all()
    observed=db.get(SocialPostTarget,row.id)
    assert observed.next_action_at.replace(tzinfo=timezone.utc)==NOW+timedelta(hours=6)
    assert observed.error_code=='RATE_LIMITED' and observed.state=='processing'
    assert observed.next_action=='poll' and observed.visibility_state=='unknown'

"""Platforms lane's real PostgreSQL migration + durable worker integration.

Only explicit assigned loopback55398/b15_platforms_test is accepted. Each test
owns a fresh schema. No historical port62124 helper is repointed or modified.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet
import httpx
from PIL import Image
import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from social.adapters.threads import ThreadsAdapterConfig
from social.adapters.tiktok import TikTokAdapterConfig, TikTokCreatorSettings
from social.adapters.x import XAdapterConfig
from social.platform_budget import SocialPlatformBudget
from social.connections.crypto import CredentialCipher
from social.contracts import ApproveCommand, PublishCommand, TikTokPostOptions
from social.media.config import MediaConfig
from social.media.inspection import LocalInspector
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.models import SocialAccount, SocialControls, SocialMediaAsset, SocialPostTarget, SocialPublishAttempt
from social.platform_connections.models import PlatformCredential
from social.worker.native_runtime import create_platform_registration
from social.worker.runner import SocialWorker
from test_connections_migration_postgres import _migration, upgrade
from test_domain_postgres import migration
from test_domain_support import ACTOR, call, draft_body
from test_media_support import ENDPOINT, FakeStorage
from test_queue_postgres import repository
import test_threads_adapter as threads_fixture
import test_tiktok_adapter as tiktok_fixture
import test_x_adapter as x_fixture


def assigned_url(raw):
    if not isinstance(raw, str) or '?' in raw:
        raise ValueError('Only assigned loopback55398/b15_platforms_test without options is allowed')
    url = make_url(raw)
    if (url.drivername not in {'postgresql', 'postgresql+psycopg2'} or url.host != '127.0.0.1'
            or url.port != 55398 or url.database != 'b15_platforms_test' or url.query):
        raise ValueError('Only assigned loopback55398/b15_platforms_test without options is allowed')
    return url.set(drivername='postgresql+psycopg2', query={'hostaddr': '127.0.0.1'})


@pytest.fixture
def platform_pg():
    raw = os.getenv('B15_PLATFORMS_TEST_DATABASE_URL')
    if not raw:
        pytest.skip('Set B15_PLATFORMS_TEST_DATABASE_URL to the owned assigned fixture')
    url = assigned_url(raw)
    schema = 'b15_platforms_' + uuid4().hex
    admin = create_engine(url, pool_size=1, max_overflow=0, hide_parameters=True)
    engine = create_engine(url, pool_size=3, max_overflow=0, hide_parameters=True,
        connect_args={'options': '-csearch_path=' + schema})
    with admin.begin() as connection:
        connection.execute(text('CREATE SCHEMA ' + schema))
    try:
        with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
            migration().upgrade()
        upgrade(engine, current=True)
        with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
            _migration('a703b15a0001_platform_connections.py').upgrade()
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
        with admin.connect() as connection:
            if connection.execute(text('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:name)'), {'name': schema}).scalar_one():
                raise RuntimeError('Owned platforms fixture schema cleanup failed')
        admin.dispose()


class PlatformStorage(FakeStorage):
    def provider_fetch(self, key, snapshot, ttl):
        if type(ttl) is not int or not 1 <= ttl <= 1860:
            raise ValueError('Bounded provider URL lifetime required')
        self.operations.append('provider_fetch')
        return self.preview(key, snapshot, ttl)


class Providers:
    def __init__(self):
        self.threads = threads_fixture.Graph()
        self.tiktok = tiktok_fixture.Provider()
        self.x = x_fixture.Provider()
    async def __call__(self, request):
        if request.url.host == 'graph.threads.com':
            return await self.threads(request)
        if request.url.host == 'business-api.tiktok.com':
            return await self.tiktok(request)
        if request.url.host == 'api.x.com':
            return await self.x(request)
        raise AssertionError('Unexpected non-fixture provider')


def construction(engine, storage, providers, cipher):
    return create_platform_registration(engine,
        {'threads': ThreadsAdapterConfig(enabled=True, operational_gates_verified=True, media_uploads_enabled=True),
         'tiktok': TikTokAdapterConfig(enabled=True, operational_gates_verified=True, product_access_verified=True),
         'x': XAdapterConfig(enabled=True, operational_gates_verified=True)},
        cipher=cipher, storage=storage, storage_origin='a'*32+'.r2.cloudflarestorage.com',
        transport_factory=lambda: httpx.MockTransport(providers),
        connection_configurations={'tiktok': SimpleNamespace(access_verified=True)},
        tiktok_verified_origins=(ENDPOINT + '/media-test/',))


def prepare(engine, *, platforms=('threads',), mode='direct'):
    providers, storage = Providers(), PlatformStorage()
    cipher = CredentialCipher('v1', {'v1': Fernet.generate_key().decode()})
    registered = construction(engine, storage, providers, cipher)
    now = datetime.now(timezone.utc)
    with Session(engine, expire_on_commit=False) as db:
        db.add(SocialControls(id=1, publishing_enabled=True, budget_controls={'x_budget_microusd': 1000000} if 'x' in platforms else {}))
        accounts = []
        for index, platform in enumerate(platforms):
            kind = {'threads': 'threads', 'tiktok': 'tiktok_accounts_api', 'x': 'x_api_v2'}[platform]
            external = {'threads': '101', 'x': '901', 'tiktok': 'owned-account-fixture' + (str(index) if index else '')}[platform]
            provider = registered.adapters[(platform, kind)]
            scopes = ['video.publish', 'video.upload'] if platform == 'tiktok' else list(provider.scopes)
            context = dict(platform=platform, api_product=kind, connection_state='connected', granted_scopes=scopes,
                capability_snapshot={'eligible': True}, tiktok_product_approved=True, x_access_verified=True, x_budget_remaining_microusd=1000000)
            account = SocialAccount(id=uuid4(), platform=platform, api_product=kind, connection_method='fixture_owned_grant',
                external_account_id=external, display_name='Sanitized owned ' + platform, connection_state='connected',
                publishing_enabled=True, capability_snapshot=provider.capabilities(context).model_dump(mode='json'), granted_scopes=scopes)
            db.add(account)
            db.flush()
            credential_id = uuid4()
            token = {'threads': 'fixture-threads-token', 'tiktok': tiktok_fixture.TOKEN, 'x': 'sanitized-fixture-user-token'}[platform]
            key, encrypted = cipher.encrypt(credential_id, 'platform:' + platform + ':credential',
                {'access_token': token, 'subject': external, 'scopes': scopes})
            db.add(PlatformCredential(id=credential_id, account_id=account.id, platform=platform, encrypted_bundle=encrypted,
                key_version=key, version=1, access_expires_at=now + timedelta(hours=1), issued_at=now))
            if platform == 'x':
                db.add(SocialPlatformBudget(account_id=account.id, enabled=True, access_verified=True, limit_microusd=1000000))
            accounts.append(account)
        db.commit()
        asset = None
        if 'tiktok' in platforms:
            buffer = BytesIO()
            Image.new('RGB', (320, 320), 'green').save(buffer, format='JPEG')
            content = buffer.getvalue()
            runtime = MediaRuntime(MediaConfig(enabled=True, endpoint=ENDPOINT, bucket='media-test', access_key='fixture', secret_key='fixture'),
                storage, LocalInspector(MediaConfig()))
            media = MediaService(db, runtime)
            granted = media.initiate(ACTOR, uuid4(), {'filename': 'fixture.jpg', 'declared_mime_type': 'image/jpeg', 'declared_size': len(content)}, uuid4())
            storage.objects[storage.last_key] = (content, 'image/jpeg', None)
            ready = media.complete(ACTOR, granted.asset.id, uuid4(), granted.asset.version, uuid4())
            asset = db.get(SocialMediaAsset, ready.id)
        targets = []
        for account in accounts:
            target = {'account_id': str(account.id), 'format': 'image' if account.platform == 'tiktok' else 'text',
                'overrides': {'media': {'mode': 'replace', 'value': []}} if account.platform == 'threads' and asset else {}}
            if account.platform == 'tiktok':
                target['tiktok_options'] = TikTokPostOptions(mode=mode, privacy_level='PUBLIC_TO_EVERYONE',
                    upload_consent=True, music_usage_confirmed=True, creator_settings_checked_at=now,
                    creator_settings_hash=TikTokCreatorSettings(**providers.tiktok.settings).bound_hash(account.external_account_id)).model_dump(mode='json')
            targets.append(target)
        body = draft_body(document={'schema_version': 1, 'master': {'text': 'Verified announcement',
            'media': [{'asset_id': str(asset.id)}] if asset else []}, 'targets': targets})
        _, created = call(db, body, lambda service: service.create(body), adapters=registered.adapters, route='platform-create')
        approve = ApproveCommand(expected_version=created['version'], revision_id=created['revision_id'])
        _, approved = call(db, approve, lambda service: service.approve(UUID(created['id']), approve), adapters=registered.adapters, route='platform-approve')
        publish = PublishCommand(expected_version=approved['version'], revision_id=approved['revision_id'], acknowledged_warning_codes=('ALT_TEXT_MISSING',) if asset else ())
        _, accepted = call(db, publish, lambda service: service.publish(UUID(created['id']), publish), adapters=registered.adapters, route='platform-publish')
        target_ids = [UUID(target['id']) for target in accepted['targets']]
    asyncio.run(registered.close())
    return SimpleNamespace(storage=storage, providers=providers, cipher=cipher, targets=target_ids)


def due(engine, target_ids):
    with engine.begin() as connection:
        for target in target_ids:
            connection.execute(text("UPDATE social_post_targets SET next_action_at=clock_timestamp()-interval '1 second' WHERE id=:id"), {'id': target})


def step(engine, fixture, *, drop_receipt=False):
    repo = repository(engine)
    registered = construction(engine, fixture.storage, fixture.providers, fixture.cipher)
    if drop_receipt:
        def lose(*args, **kwargs):
            raise RuntimeError('Controlled lost receipt persistence')
        repo.finish = lose
    async def exercise():
        worker = SocialWorker(repo, adapters=registered.adapters, credential_loader=registered.credential_loader, media_access=registered.media_access)
        try:
            claims = await worker.db(repo.claim_due, 2)
            for claim in claims:
                await worker.process(claim)
            return len(claims)
        finally:
            await worker.close()
            await registered.close()
    return asyncio.run(exercise())


def rows(engine, fixture):
    with Session(engine) as db:
        return {row.id: (row.state, row.visibility_state, row.primary_remote_id, row.submit_count, row.checkpoint)
            for row in db.scalars(select(SocialPostTarget).where(SocialPostTarget.id.in_(fixture.targets)))}


def test_platform_migration_full_social_chain_from_accepted_base(platform_pg):
    module = _migration('a703b15a0001_platform_connections.py')
    assert module.down_revision == 'a545b14a0001'
    with platform_pg.begin() as connection:
        tables = {name for name in inspect(connection).get_table_names()}
        assert set(module.TABLES) <= tables
        for table in module.TABLES:
            rls = connection.execute(text('SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:name AS regclass)'), {'name': table}).scalar_one()
            assert rls is True
            assert not connection.execute(text("SELECT EXISTS(SELECT 1 FROM pg_class c,LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid=CAST(:name AS regclass) AND a.grantee=0)"), {'name': table}).scalar_one()
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()
        assert not set(module.TABLES) & set(inspect(connection).get_table_names())


@pytest.mark.parametrize('platform,mode', [('threads', 'direct'), ('tiktok', 'direct'), ('tiktok', 'draft')])
def test_real_worker_full_chain_uses_encrypted_material_and_inspected_media(platform_pg, platform, mode):
    fixture = prepare(platform_pg, platforms=(platform,), mode=mode)
    if mode == 'draft':
        fixture.providers.tiktok.status, fixture.providers.tiktok.post_ids = 'SEND_TO_USER_INBOX', None
    with Session(platform_pg) as db:
        frozen = db.get(SocialPostTarget, fixture.targets[0]).resolved_payload
    for _ in range(9):
        due(platform_pg, fixture.targets)
        step(platform_pg, fixture)
        result = rows(platform_pg, fixture)[fixture.targets[0]]
        if result[0] in {'published', 'blocked', 'failed', 'outcome_unknown'}:
            break
    if platform == 'threads':
        assert result[0:2] == ('processing', 'unknown'), result
        assert result[2] == '999' and result[3] == 1
    elif mode == 'draft':
        assert result[0:2] == ('blocked', 'manual_action'), result
        assert result[2] is None and result[3] == 0
    else:
        assert result[0:2] == ('published', 'public'), result
        assert result[2] and result[3] == 1
    with Session(platform_pg) as db:
        assert db.get(SocialPostTarget, fixture.targets[0]).resolved_payload == frozen
        attempts = list(db.scalars(select(SocialPublishAttempt)))
        receipts = str([row.receipt for row in attempts])
        assert 'fixture-threads-token' not in receipts and tiktok_fixture.TOKEN not in receipts and 'preview-secret' not in receipts
        assert all(row.completed_at is not None for row in attempts)
    if platform == 'threads':
        assert sum(method == 'POST' for method, _ in fixture.providers.threads.calls) == 2
    else:
        assert sum(method == 'POST' for method, _, _ in fixture.providers.tiktok.calls) == 1
        assert 'download' in fixture.storage.operations


def test_target_only_retry_never_resends_published_sibling(platform_pg):
    fixture = prepare(platform_pg, platforms=('tiktok', 'tiktok'))
    first = True
    async def limited_once(request):
        nonlocal first
        if first and request.method == 'POST':
            first = False
            return httpx.Response(429, headers={'retry-after': '1'}, json={'code': 42900, 'data': {}})
        return None
    # Restrict one TikTok mutation only; settings and later status remain normal.
    original = fixture.providers.tiktok.__call__
    async def controlled(request):
        special = await limited_once(request)
        if special:
            fixture.providers.tiktok.calls.append((request.method, request.url.path, {}))
            return special
        return await original(request)
    async def route(request):
        if request.url.host == 'graph.threads.com':
            return await fixture.providers.threads(request)
        return await controlled(request)
    # Special-method lookup requires an explicit callable wrapper.
    class Router:
        threads, tiktok = fixture.providers.threads, fixture.providers.tiktok
        async def __call__(self, request):
            return await route(request)
    fixture.providers = Router()
    for _ in range(10):
        due(platform_pg, fixture.targets)
        step(platform_pg, fixture)
        current = rows(platform_pg, fixture)
        if all(item[0] == 'published' for item in current.values()):
            break
    assert all(item[0] == 'published' for item in current.values()), current
    assert fixture.providers.threads.calls == []
    assert sum(method == 'POST' for method, _, _ in fixture.providers.tiktok.calls) == 3
    assert sorted(item[3] for item in current.values()) == [1, 2]


@pytest.mark.parametrize('raw', ['postgresql://fixture@remote.example:55398/b15_platforms_test',
    'postgresql://fixture@127.0.0.1:62124/b15_platforms_test', 'postgresql://fixture@127.0.0.1:55398/production',
    'postgresql://fixture@127.0.0.1:55398/b15_platforms_test?host=remote.example'])
def test_owned_database_guard_cannot_be_redirected(raw):
    with pytest.raises(ValueError):
        assigned_url(raw)


def prior_submissions(engine, target_id, *, count, age_seconds):
    """Synthetic historical committed intents, never raw target-state shortcuts."""
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO social_publish_attempts
                (id,target_id,sequence,operation_id,operation,request_fingerprint,lease_epoch,outcome,receipt,
                 estimated_cost_microusd,cost_reservation_state,completed_at,created_at)
            SELECT gen_random_uuid(),CAST(:id AS uuid),start.sequence+n,gen_random_uuid(),
                   CASE WHEN n%2=0 THEN 'upload' ELSE 'publish' END,repeat('a',64),0,'definite_failure',
                   jsonb_build_object('intent',jsonb_build_object('publication_capable',true,
                       'mutating',true,'safe_replay_class','requires_reconciliation')),
                   0,'not_required',clock_timestamp(),clock_timestamp()-make_interval(secs => :age)
            FROM generate_series(1,:count) AS n
            CROSS JOIN (SELECT COALESCE(MAX(sequence),0) AS sequence
                        FROM social_publish_attempts WHERE target_id=CAST(:id AS uuid)) AS start
        """), {'id': target_id, 'count': count, 'age': age_seconds})


@pytest.mark.parametrize('mode,count,age', [('direct', 6, 10), ('draft', 6, 10), ('direct', 15, 120), ('draft', 15, 120)])
def test_tiktok_combined_direct_draft_account_quota_refuses_new_dispatch(platform_pg, mode, count, age):
    fixture = prepare(platform_pg, platforms=('tiktok',), mode=mode)
    due(platform_pg, fixture.targets)
    step(platform_pg, fixture)  # Only current settings read is allowed so far.
    with Session(platform_pg) as db:
        before = db.get(SocialPostTarget, fixture.targets[0]).checkpoint
    prior_submissions(platform_pg, fixture.targets[0], count=count, age_seconds=age)
    due(platform_pg, fixture.targets)
    step(platform_pg, fixture)
    with Session(platform_pg) as db:
        target = db.get(SocialPostTarget, fixture.targets[0])
        assert target.state == 'blocked' and target.error_code == 'RATE_LIMITED'
        assert target.checkpoint == before and target.submit_count == 0
        attempts = list(db.scalars(select(SocialPublishAttempt)))
        assert len(attempts) == count + 1  # No new intent is created on refusal.
    assert not any(method == 'POST' for method, _, _ in fixture.providers.tiktok.calls)


@pytest.mark.parametrize('restriction', ['zero', 'access', 'disabled'])
@pytest.mark.parametrize('phase', ['initial', 'processing', 'reconciling'])
def test_x_every_worker_read_and_write_requires_current_access_and_budget(platform_pg, restriction, phase):
    fixture = prepare(platform_pg, platforms=('x',))
    if phase != 'initial':
        due(platform_pg, fixture.targets)
        step(platform_pg, fixture)
        with Session(platform_pg) as db:
            target = db.get(SocialPostTarget, fixture.targets[0])
            assert target.state == 'processing' and target.checkpoint
        if phase == 'reconciling':
            with platform_pg.begin() as connection:
                connection.execute(text("UPDATE social_post_targets SET state='reconciling',next_action='reconcile' WHERE id=:id"), {'id': fixture.targets[0]})
    with Session(platform_pg) as db:
        target = db.get(SocialPostTarget, fixture.targets[0])
        budget = db.get(SocialPlatformBudget, target.account_id)
        if restriction == 'zero':
            # Retained reservations are not erased to manufacture a zero gate.
            budget.limit_microusd = budget.reserved_microusd + budget.spent_microusd
        elif restriction == 'access':
            budget.access_verified = False
        else:
            budget.enabled = False
        db.commit()
    before_calls = len(fixture.providers.x.calls)
    with Session(platform_pg) as db:
        attempts_before = len(list(db.scalars(select(SocialPublishAttempt))))
    due(platform_pg, fixture.targets)
    step(platform_pg, fixture)
    assert len(fixture.providers.x.calls) == before_calls
    with Session(platform_pg) as db:
        target = db.get(SocialPostTarget, fixture.targets[0])
        assert target.state in {'blocked', 'failed'}
        assert len(list(db.scalars(select(SocialPublishAttempt)))) == attempts_before


@pytest.mark.parametrize('failure', ['timeout_after_dispatch', 'receipt_persistence_loss'])
def test_tiktok_uncertain_dispatch_retains_owner_history_and_never_resubmits(platform_pg, failure):
    fixture = prepare(platform_pg, platforms=('tiktok',))
    due(platform_pg, fixture.targets)
    step(platform_pg, fixture)  # Settings checkpoint is durable first.
    if failure == 'timeout_after_dispatch':
        fixture.providers.tiktok.timeout_mutation = True
    due(platform_pg, fixture.targets)
    step(platform_pg, fixture, drop_receipt=failure == 'receipt_persistence_loss')
    if failure == 'receipt_persistence_loss':
        with platform_pg.begin() as connection:
            connection.execute(text("UPDATE social_post_targets SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"), {'id': fixture.targets[0]})
            connection.execute(text("UPDATE social_accounts SET publish_lease_expires_at=clock_timestamp()-interval '1 second' WHERE publish_lease_target_id=:id"), {'id': fixture.targets[0]})
        repository(platform_pg).recover_expired()
    due(platform_pg, fixture.targets)
    step(platform_pg, fixture)
    with Session(platform_pg) as db:
        target = db.get(SocialPostTarget, fixture.targets[0])
        account = db.get(SocialAccount, target.account_id)
        assert target.state == 'outcome_unknown' and target.submit_count == 1 and target.primary_remote_id is None
        assert account.hold_reason and str(target.id) in account.hold_reason
        assert account.hold_reason == "RECONCILIATION_REQUIRED:" + str(target.id)
        assert len(list(db.scalars(select(SocialPublishAttempt)))) >= 2
    assert sum(method == 'POST' for method, _, _ in fixture.providers.tiktok.calls) == 1


def test_tiktok_account_quota_includes_other_publication_targets(platform_pg):
    fixture = prepare(platform_pg, platforms=('tiktok',))
    due(platform_pg, fixture.targets)
    step(platform_pg, fixture)
    # Construct another genuine approved publication through the same service,
    # then seed historical provider intents against that sibling target only.
    with Session(platform_pg, expire_on_commit=False) as db:
        first = db.get(SocialPostTarget, fixture.targets[0])
        from social.models import SocialPostRevision, SocialPublication
        publication = db.get(SocialPublication, first.publication_id)
        revision = db.get(SocialPostRevision, publication.revision_id)
        registered = construction(platform_pg, fixture.storage, fixture.providers, fixture.cipher)
        body = draft_body(title='Other authorization', document=revision.document)
        _, created = call(db, body, lambda service: service.create(body), adapters=registered.adapters, route='quota-peer-create')
        approve = ApproveCommand(expected_version=created['version'], revision_id=created['revision_id'])
        _, approved = call(db, approve, lambda service: service.approve(UUID(created['id']), approve), adapters=registered.adapters, route='quota-peer-approve')
        sibling = UUID(approved['targets'][0]['id'])
        asyncio.run(registered.close())
    prior_submissions(platform_pg, sibling, count=6, age_seconds=10)
    due(platform_pg, fixture.targets)
    step(platform_pg, fixture)
    with Session(platform_pg) as db:
        target = db.get(SocialPostTarget, fixture.targets[0])
        assert target.state == 'blocked' and target.error_code == 'RATE_LIMITED'
        assert db.get(SocialPostTarget, sibling).state == 'ready'
    assert not any(method == 'POST' for method, _, _ in fixture.providers.tiktok.calls)


def test_x_positive_worker_publish_and_public_author_read_reserve_each_cost(platform_pg):
    fixture = prepare(platform_pg, platforms=('x',))
    for _ in range(2):
        due(platform_pg, fixture.targets)
        step(platform_pg, fixture)
    with Session(platform_pg) as db:
        target = db.get(SocialPostTarget, fixture.targets[0])
        budget = db.get(SocialPlatformBudget, target.account_id)
        assert (target.state, target.visibility_state, target.primary_remote_id, target.submit_count) == ('published', 'public', '777', 1)
        attempts = list(db.scalars(select(SocialPublishAttempt).order_by(SocialPublishAttempt.sequence)))
        assert [row.operation for row in attempts] == ['publish', 'poll']
        assert [row.estimated_cost_microusd for row in attempts] == [15000, 15000]
        assert all(row.cost_reservation_state == 'reserved' and row.completed_at is not None for row in attempts)
        assert budget.reserved_microusd == 30000 and budget.spent_microusd == 0
        assert len({row.operation_id for row in attempts}) == 2
    assert [(method, path) for method, path, _, _ in fixture.providers.x.calls] == [('POST', '/2/tweets'), ('GET', '/2/tweets/777')]
    query = fixture.providers.x.calls[-1][2].decode()
    assert 'author_id' in query and 'protected' in query


def test_x_budget_exactly_exhausted_after_send_retains_unknown_and_does_not_read_or_resend(platform_pg):
    fixture = prepare(platform_pg, platforms=('x',))
    with Session(platform_pg) as db:
        target = db.get(SocialPostTarget, fixture.targets[0])
        db.get(SocialPlatformBudget, target.account_id).limit_microusd = 15000
        db.commit()
    due(platform_pg, fixture.targets)
    step(platform_pg, fixture)
    with Session(platform_pg) as db:
        target = db.get(SocialPostTarget, fixture.targets[0])
        checkpoint = target.checkpoint
        assert target.state == 'processing' and checkpoint['post_id'] == '777'
    due(platform_pg, fixture.targets)
    step(platform_pg, fixture)
    due(platform_pg, fixture.targets)
    assert step(platform_pg, fixture) == 0
    with Session(platform_pg) as db:
        target = db.get(SocialPostTarget, fixture.targets[0])
        assert target.state == 'blocked' and target.visibility_state == 'unknown'
        assert target.checkpoint == checkpoint and target.submit_count == 1
        assert len(list(db.scalars(select(SocialPublishAttempt)))) == 1
        budget = db.get(SocialPlatformBudget, target.account_id)
        assert budget.reserved_microusd == budget.limit_microusd == 15000
    assert [(method, path) for method, path, _, _ in fixture.providers.x.calls] == [('POST', '/2/tweets')]


def test_x_two_locked_reservations_cannot_exceed_the_same_account_budget(platform_pg):
    from concurrent.futures import ThreadPoolExecutor
    from social.platform_budget import reserve_x_operation
    fixture = prepare(platform_pg, platforms=('x',))
    with Session(platform_pg) as db:
        account_id = db.get(SocialPostTarget, fixture.targets[0]).account_id
        db.get(SocialPlatformBudget, account_id).limit_microusd = 20000
        db.commit()
    def reserve(_):
        with platform_pg.begin() as connection:
            connection.execute(text('SELECT id FROM social_accounts WHERE id=:id FOR UPDATE'), {'id': account_id})
            return reserve_x_operation(connection, account_id, 15000)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(reserve, range(2)))
    assert sorted(results) == [False, True]
    with Session(platform_pg) as db:
        budget = db.get(SocialPlatformBudget, account_id)
        assert budget.reserved_microusd == 15000 and budget.reserved_microusd <= budget.limit_microusd
    assert fixture.providers.x.calls == []


@pytest.mark.parametrize('case', ['suppress','alter_before','alter_after','alter_deferred'])
def test_x_reservation_requires_exact_persisted_increment_even_with_prior_credit(platform_pg,case):
    from social.platform_budget import reserve_x_operation
    fixture=prepare(platform_pg,platforms=('x',))
    with Session(platform_pg) as db:
        target=db.get(SocialPostTarget,fixture.targets[0])
        account_id=target.account_id
        budget=db.get(SocialPlatformBudget,account_id)
        budget.reserved_microusd=20000
        budget.version=1
        db.commit()
    with platform_pg.begin() as connection:
        if case in ('suppress','alter_before'):
            body='RETURN NULL;' if case=='suppress' else 'NEW.reserved_microusd:=OLD.reserved_microusd+1; RETURN NEW;'
            connection.execute(text('CREATE FUNCTION fixture_budget_change() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN '+body+' END $$'))
            connection.execute(text('CREATE TRIGGER fixture_budget_change BEFORE UPDATE ON social_platform_budgets FOR EACH ROW EXECUTE FUNCTION fixture_budget_change()'))
        else:
            connection.execute(text('''CREATE FUNCTION fixture_budget_change() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
                IF pg_trigger_depth()=1 AND NEW.reserved_microusd>OLD.reserved_microusd+1 THEN
                    UPDATE social_platform_budgets SET reserved_microusd=OLD.reserved_microusd+1 WHERE account_id=NEW.account_id;
                END IF; RETURN NEW; END $$'''))
            trigger='CREATE CONSTRAINT TRIGGER fixture_budget_change AFTER UPDATE ON social_platform_budgets DEFERRABLE INITIALLY DEFERRED' if case=='alter_deferred' else 'CREATE TRIGGER fixture_budget_change AFTER UPDATE ON social_platform_budgets'
            connection.execute(text(trigger+' FOR EACH ROW EXECUTE FUNCTION fixture_budget_change()'))
    with pytest.raises(RuntimeError,match='X_BUDGET_RESERVATION_'):
        with platform_pg.begin() as connection:
            reserve_x_operation(connection,account_id,15000)
    with platform_pg.connect() as connection:
        actual=connection.execute(text('SELECT reserved_microusd,version FROM social_platform_budgets WHERE account_id=:id'),{'id':account_id}).one()
        assert tuple(actual)==(20000,1)


def test_full_alembic_revision_chain_from_empty_assigned_database(monkeypatch):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.runtime.environment import EnvironmentContext
    raw=os.getenv('B15_PLATFORMS_TEST_DATABASE_URL')
    if not raw:
        pytest.skip('Set the explicit assigned fixture DSN')
    url=assigned_url(raw)
    name='b15_platforms_fullchain_'+uuid4().hex
    admin=create_engine(url,pool_size=1,max_overflow=0,hide_parameters=True,isolation_level='AUTOCOMMIT')
    owned_url=url.set(database=name)
    engine=create_engine(owned_url,pool_size=1,max_overflow=0,hide_parameters=True)
    with admin.connect() as connection:
        connection.execute(text('CREATE DATABASE '+name))
    try:
        # Historical migrations explicitly inspect public. A new owned database
        # exercises their real chain without changing any existing schema.
        monkeypatch.setenv('DATABASE_URL',owned_url.render_as_string(hide_password=False))
        config=Config()
        config.set_main_option('script_location',str(Path(__file__).resolve().parents[2]/'alembic'))
        script=ScriptDirectory.from_config(config)
        assert script.get_heads()==['a703b15a0001']
        with engine.begin() as connection:
            with EnvironmentContext(config,script,fn=lambda rev,ctx:script._upgrade_revs('head',rev)) as context:
                context.configure(connection=connection)
                context.run_migrations()
            assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='a703b15a0001'
            assert set(_migration('a703b15a0001_platform_connections.py').TABLES)<=set(inspect(connection).get_table_names())
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text('DROP DATABASE '+name))
            assert not connection.execute(text('SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=:name)'),{'name':name}).scalar_one()
        admin.dispose()


@pytest.mark.parametrize('command',['schedule','reschedule','resume','retry','worker'])
def test_tiktok_future_workflow_requires_separate_permission_at_every_entry(platform_pg,command):
    from social.contracts import ScheduleCommand,RescheduleCommand,ResumeCommand,RetryCommand,ScheduleTime
    from social.models import SocialPostRevision,SocialPublication
    from social.service import SocialService,SocialError
    fixture=prepare(platform_pg,platforms=('tiktok',))
    registered=construction(platform_pg,fixture.storage,fixture.providers,fixture.cipher)
    try:
        with Session(platform_pg,expire_on_commit=False) as db:
            target=db.get(SocialPostTarget,fixture.targets[0])
            publication=db.get(SocialPublication,target.publication_id)
            revision=db.get(SocialPostRevision,publication.revision_id)
            post_id=publication.post_id
            future=datetime.now(timezone.utc)+timedelta(minutes=30)
            schedule=ScheduleTime(local_time=future.replace(tzinfo=None).isoformat(timespec='seconds'),timezone='UTC',utc_offset='+00:00')
            if command=='schedule':
                body=draft_body(title='Future request',document=revision.document)
                _,created=call(db,body,lambda svc:svc.create(body),adapters=registered.adapters,route='future-create')
                post_id=UUID(created['id'])
                body=ScheduleCommand(expected_version=created['version'],revision_id=created['revision_id'],schedule=schedule,acknowledged_warning_codes=('ALT_TEXT_MISSING',))
                action=lambda svc:svc.publish(post_id,body,scheduled=True)
            elif command=='reschedule':
                detail=SocialService(db).detail(post_id)
                body=RescheduleCommand(expected_version=detail['version'],publication_id=publication.id,expected_publication_version=publication.version,reason='Fixture future request',schedule=schedule,acknowledged_warning_codes=('ALT_TEXT_MISSING',))
                action=lambda svc:svc.edit_schedule(post_id,body,scheduled=True)
            else:
                # A retained authorization from an earlier configuration must
                # not outlive withdrawal of unattended workflow permission.
                publication.scheduled_for=future
                if command=='resume':
                    publication.cancel_requested_at=datetime.now(timezone.utc)
                    target.state,target.next_action,target.next_action_at='cancelled',None,None
                elif command=='retry':
                    target.state,target.next_action,target.next_action_at='failed',None,None
                    db.add(SocialPublishAttempt(id=uuid4(),target_id=target.id,sequence=1,operation_id=uuid4(),operation='publish',request_fingerprint='a'*64,lease_epoch=1,outcome='definite_failure',receipt={'retry_safe':True},estimated_cost_microusd=0,cost_reservation_state='not_applicable',completed_at=datetime.now(timezone.utc)))
                db.commit()
                if command=='resume':
                    detail=SocialService(db).detail(post_id)
                    body=ResumeCommand(expected_version=detail['version'],revision_id=revision.id,reason='Fixture resume',acknowledged_warning_codes=('ALT_TEXT_MISSING',))
                    action=lambda svc:svc.resume(post_id,body)
                elif command=='retry':
                    body=RetryCommand(reason='Fixture retry')
                    action=lambda svc:svc.retry(target.id,body)
            if command!='worker':
                with pytest.raises(SocialError,match='UNATTENDED_WORKFLOW_UNVERIFIED'):
                    call(db,body,action,adapters=registered.adapters,route='future-'+command)
                assert fixture.providers.tiktok.calls==[]
            else:
                due(platform_pg,fixture.targets)
                step(platform_pg,fixture)  # A creator-settings read is allowed.
                due(platform_pg,fixture.targets)
                step(platform_pg,fixture)  # The actual mutation remains refused.
                assert not any(method=='POST' for method,_,_ in fixture.providers.tiktok.calls)
                with Session(platform_pg) as observed:
                    actual=observed.get(SocialPostTarget,fixture.targets[0])
                    assert actual.state=='blocked'
                    assert all(row.operation=='poll' for row in observed.scalars(select(SocialPublishAttempt)))
    finally:
        asyncio.run(registered.close())


def test_x_lost_receipt_waits_then_confirms_unique_post_without_resend(platform_pg):
    from social.contracts import ResolvedPostPayload
    fixture=prepare(platform_pg,platforms=('x',))
    due(platform_pg,fixture.targets)
    step(platform_pg,fixture,drop_receipt=True)
    with platform_pg.begin() as connection:
        connection.execute(text("UPDATE social_post_targets SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"),{'id':fixture.targets[0]})
        connection.execute(text("UPDATE social_accounts SET publish_lease_expires_at=clock_timestamp()-interval '1 second' WHERE publish_lease_target_id=:id"),{'id':fixture.targets[0]})
    repository(platform_pg).recover_expired()
    due(platform_pg,fixture.targets)
    step(platform_pg,fixture)
    with Session(platform_pg) as db:
        target=db.get(SocialPostTarget,fixture.targets[0])
        assert (target.state,target.next_action,target.submit_count)==('reconciling','reconcile',1)
        payload=ResolvedPostPayload.model_validate(target.resolved_payload)
    assert len(fixture.providers.x.calls)==1
    # Move only this sanitized fixture's original dispatch clock so the lookup
    # covers its full window; retain original fingerprint and frozen payload.
    dispatched=datetime.now(timezone.utc)-timedelta(minutes=10)
    with platform_pg.begin() as connection:
        connection.execute(text("UPDATE social_publish_attempts SET dispatch_started_at=:when WHERE target_id=:id AND operation='publish'"),{'id':fixture.targets[0],'when':dispatched})
    fixture.providers.x.overrides[('GET','/2/users/901/tweets')]=x_fixture.own_posts(payload,posts=[{'id':'777','author_id':'901','text':payload.text,'created_at':(dispatched+timedelta(seconds=1)).isoformat()}])
    due(platform_pg,fixture.targets)
    step(platform_pg,fixture)
    with Session(platform_pg) as db:
        target=db.get(SocialPostTarget,fixture.targets[0])
        budget=db.get(SocialPlatformBudget,target.account_id)
        assert (target.state,target.visibility_state,target.primary_remote_id,target.submit_count)==('published','public','777',1)
        assert budget.reserved_microusd==85000
        attempts=list(db.scalars(select(SocialPublishAttempt).order_by(SocialPublishAttempt.sequence)))
        assert [row.estimated_cost_microusd for row in attempts]==[15000,35000,35000]
        assert all(row.cost_reservation_state=='reserved' for row in attempts)
    assert [(method,path) for method,path,*_ in fixture.providers.x.calls]==[('POST','/2/tweets'),('GET','/2/users/901/tweets')]


def test_real_postgres_event_consumer_commits_only_a_status_nudge(platform_pg):
    from social.platform_event_models import SocialPlatformEvent
    fixture=prepare(platform_pg,platforms=('tiktok',))
    for _ in range(2):
        due(platform_pg,fixture.targets)
        step(platform_pg,fixture)
    now=datetime.now(timezone.utc)
    with Session(platform_pg) as db:
        target=db.get(SocialPostTarget,fixture.targets[0])
        assert target.state=='processing' and target.checkpoint['share_id']
        checkpoint=target.checkpoint.copy()
        target.next_action_at=now+timedelta(hours=1)
        event=SocialPlatformEvent(id=uuid4(),provider='tiktok',account_id=target.account_id,event_type='post.publish.publicly_available',remote_id=checkpoint['share_id'],post_id='777',event_at=now,received_at=now,dedupe_hash='a'*64)
        db.add(event)
        event_id=event.id
        db.commit()
    assert repository(platform_pg).process_provider_events()==1
    with Session(platform_pg) as db:
        target=db.get(SocialPostTarget,fixture.targets[0])
        event=db.get(SocialPlatformEvent,event_id)
        assert event.processing_state=='processed' and event.processed_at is not None
        assert target.next_action_at<=datetime.now(timezone.utc)
        assert (target.state,target.next_action,target.visibility_state)==('processing','poll','unknown')
        assert target.checkpoint==checkpoint and target.lease_token is None and target.submit_count==1
    assert sum(method=='POST' for method,_,_ in fixture.providers.tiktok.calls)==1

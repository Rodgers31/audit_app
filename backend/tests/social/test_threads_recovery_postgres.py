"""Owned PostgreSQL17 operator/worker and transaction/concurrency controls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from uuid import UUID, uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session

from social.models import SocialAccount, SocialAuditEvent, SocialControls, SocialPostTarget, SocialPublishAttempt
from social.threads_recovery import ThreadsRecoveryService
from test_api_admin import make_client, key
from test_connections_migration_postgres import _migration, upgrade
from test_domain_postgres import migration
from test_platforms_postgres import prepare, due, step, rows
from test_threads_recovery import pending, proposal, observation, REVIEWER


def assigned_url(raw):
    if not isinstance(raw, str) or '?' in raw:
        raise ValueError('Use owned loopback55424/b16_threads_test without options')
    try:
        url = make_url(raw)
    except ArgumentError:
        raise ValueError('Use owned loopback55424/b16_threads_test without options') from None
    if (url.drivername not in {'postgresql', 'postgresql+psycopg2'} or url.host != '127.0.0.1'
            or url.port != 55424 or url.database != 'b16_threads_test' or url.query):
        raise ValueError('Use owned loopback55424/b16_threads_test without options')
    return url.set(drivername='postgresql+psycopg2', query={'hostaddr':'127.0.0.1'})


@pytest.fixture
def recovery_pg():
    raw = os.getenv('B16_THREADS_TEST_DATABASE_URL')
    if not raw:
        pytest.skip('Set B16_THREADS_TEST_DATABASE_URL to the owned PostgreSQL17 fixture')
    url = assigned_url(raw)
    schema = 'b16_threads_' + uuid4().hex
    admin = create_engine(url, pool_size=1, max_overflow=0)
    engine = create_engine(url, pool_size=3, max_overflow=0, connect_args={'options':'-csearch_path='+schema})
    with admin.begin() as conn:
        assert str(conn.scalar(text('SHOW server_version_num'))).startswith('17')
        conn.execute(text('CREATE SCHEMA '+schema))
    try:
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            migration().upgrade()
        upgrade(engine, current=True)
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            _migration('a704b15a0001_social_generation_shadow.py').upgrade()
            _migration('a706b15a0001_social_policy_authority.py').upgrade()
            _migration('a703b15a0001_platform_connections.py').upgrade()
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text('DROP SCHEMA '+schema+' CASCADE'))
            assert not conn.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:s)'), {'s':schema})
        admin.dispose()


def proposed(engine):
    with Session(engine, expire_on_commit=False) as db:
        return proposal(db)


def test_actual_worker_unknown_to_operator_public_and_restart_no_resend(recovery_pg):
    fixture = prepare(recovery_pg, platforms=('threads',))
    for _ in range(9):
        due(recovery_pg, fixture.targets)
        step(recovery_pg, fixture)
    assert rows(recovery_pg, fixture)[fixture.targets[0]][:2] == ('processing', 'unknown')
    with Session(recovery_pg) as db:
        target = db.get(SocialPostTarget, fixture.targets[0])
        assert all(a.completed_at for a in db.scalars(select(SocialPublishAttempt)))
        checkpoint, refs = target.checkpoint, target.remote_refs
        before = list(db.scalars(select(SocialPublishAttempt.id)))
        db.get(SocialControls, 1).publishing_enabled = False
        db.commit()
    url = f'/api/v1/admin/social/targets/{fixture.targets[0]}'
    client = make_client(recovery_pg)
    context = client.get(url+'/public-proof').json()
    first = observation(context)
    first.update(remote_id='999', remote_url='https://www.threads.com/@fixture/post/abc')
    # Exact provider fixture permalink is retained by the actual worker.
    with Session(recovery_pg) as db:
        first['remote_url'] = db.get(SocialPostTarget, fixture.targets[0]).remote_url
    response = client.post(url+'/public-proof', json=dict(expected_publication_version=context['publication_version'],
        binding_hash=context['binding_hash'], observation=first, reason='Retained exact anonymous fixture public observation.'), headers=key())
    assert response.status_code == 201, response.text
    second = {**first, 'capture_sha256':'b'*64, 'custody_reference':str(uuid4())}
    body = dict(expected_publication_version=context['publication_version'], proof_id=response.json()['proof_id'],
        observation=second, reason='Independent anonymous fixture verification after operator restart.')
    headers = key()
    response = make_client(recovery_pg, actor=REVIEWER).post(url+'/record-existing', json=body, headers=headers)
    assert response.status_code == 200, response.text
    # New HTTP client/session models restart after an ambiguous transport response.
    assert make_client(recovery_pg, actor=REVIEWER).post(url+'/record-existing', json=body, headers=headers).json() == response.json()
    calls_before = list(fixture.providers.threads.calls)
    due(recovery_pg, fixture.targets)
    assert step(recovery_pg, fixture) == 0
    assert fixture.providers.threads.calls == calls_before
    with Session(recovery_pg) as db:
        target = db.get(SocialPostTarget, fixture.targets[0])
        assert target.state == 'published' and target.checkpoint == checkpoint and target.remote_refs == refs
        assert list(db.scalars(select(SocialPublishAttempt.id))) == before
        assert target.submit_count == 1


def test_same_key_and_competing_reviewers_are_atomic(recovery_pg):
    target_id, url, context, first, body = proposed(recovery_pg)
    headers = key()
    def admit(_):
        return make_client(recovery_pg, actor=REVIEWER).post(url+'/record-existing', json=body, headers=headers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(admit, range(2)))
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json() == results[1].json()
    with Session(recovery_pg) as db:
        admitted = list(db.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action=='threads.public_proof_admitted')))
        assert len(admitted) == 1


@pytest.mark.parametrize('table,operation', [('social_audit_events','suppress'), ('social_command_receipts','suppress'),
    ('social_post_targets','alter'), ('social_accounts','suppress'), ('social_publications','suppress')])
def test_required_write_suppression_or_alteration_rolls_back(recovery_pg, table, operation):
    target_id, url, context, first, body = proposed(recovery_pg)
    with recovery_pg.begin() as conn:
        effect = 'NEW.remote_url := \'https://www.threads.com/@wrong/post/nope\'; RETURN NEW;' if operation=='alter' else 'RETURN NULL;'
        conn.execute(text('CREATE FUNCTION b16_hostile_write() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN '+effect+' END $$'))
        conn.execute(text(f'CREATE TRIGGER b16_hostile BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION b16_hostile_write()'))
    response = make_client(recovery_pg, actor=REVIEWER).post(url+'/record-existing', json=body, headers=key())
    expected_status = 409 if table in {'social_accounts', 'social_publications'} else 503
    expected_code = 'VERSION_CONFLICT' if expected_status == 409 else 'RECOVERY_PERSISTENCE_FAILED'
    assert response.status_code == expected_status, response.text
    assert response.json()['detail']['code'] == expected_code
    with Session(recovery_pg) as db:
        target = db.get(SocialPostTarget, target_id)
        assert target.state == 'outcome_unknown' and target.remote_url is None
        assert db.get(SocialAccount, target.account_id).hold_reason.endswith(str(target_id))
        assert not list(db.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action=='threads.public_proof_admitted')))


def test_competing_distinct_keys_only_one_admission(recovery_pg):
    target_id, url, context, first, body = proposed(recovery_pg)
    def admit(actor):
        candidate = {**body, 'observation':{**body['observation'], 'capture_sha256': ('b' if actor==REVIEWER else 'c')*64,
            'custody_reference':str(uuid4())}}
        return make_client(recovery_pg, actor=actor).post(url+'/record-existing', json=candidate, headers=key())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(admit, [REVIEWER, uuid4()]))
    assert sorted(r.status_code for r in results) == [200, 409]
    with Session(recovery_pg) as db:
        assert len(list(db.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action=='threads.public_proof_admitted')))) == 1


def test_duplicate_remote_across_account_products_and_exact_sibling_preservation(recovery_pg):
    owner = '10101010'
    with Session(recovery_pg, expire_on_commit=False) as db:
        targets = [pending(db, owner_id=owner, product=p) for p in ('fixture', 'alias')]
        for target_id in targets:
            target = db.get(SocialPostTarget, target_id)
            target.primary_remote_id = None
            target.remote_refs = {'container_id':'8001'}
        db.commit()
    admissions = []
    for target_id, capture in zip(targets, ['c','d']):
        url = f'/api/v1/admin/social/targets/{target_id}'
        client = make_client(recovery_pg)
        context = client.get(url+'/public-proof').json()
        response = client.post(url+'/public-proof', json=dict(expected_publication_version=context['publication_version'],
            binding_hash=context['binding_hash'], observation=observation(context, capture),
            reason='Observe exact unknown-identity publication in anonymous fixture.'), headers=key())
        assert response.status_code == 201, response.text
        admissions.append((url, dict(expected_publication_version=context['publication_version'], proof_id=response.json()['proof_id'],
            observation=observation(context, 'e' if capture=='c' else 'f'), reason='Independent exact public observation with separately retained packet.')))
    client = make_client(recovery_pg, actor=REVIEWER)
    assert client.post(admissions[0][0]+'/record-existing', json=admissions[0][1], headers=key()).status_code == 200
    refused = client.post(admissions[1][0]+'/record-existing', json=admissions[1][1], headers=key())
    assert refused.json()['detail']['code'] == 'PROOF_REPLAY'
    with Session(recovery_pg) as db:
        sibling = db.get(SocialPostTarget, targets[1])
        assert sibling.state == 'outcome_unknown' and sibling.primary_remote_id is None and sibling.submit_count == 1
        assert db.get(SocialAccount, sibling.account_id).hold_reason.endswith(str(sibling.id))
        assert sibling.remote_refs == {'container_id':'8001'}


@pytest.mark.parametrize('malformed', [None, '', 'postgresql://x@remote:55424/b16_threads_test',
    'postgresql://x@127.0.0.1:55424/production', 'postgresql://x@127.0.0.1:55424/b16_threads_test?host=remote'])
def test_fixture_refuses_unowned_targets(malformed):
    with pytest.raises(ValueError):
        assigned_url(malformed)


def attempt_settlement(engine, target_id):
    """Return the first explicit refusal, or execute all the way to admission."""
    url = f'/api/v1/admin/social/targets/{target_id}'
    client = make_client(engine)
    response = client.get(url+'/public-proof')
    if response.status_code != 200:
        return response
    context = response.json()
    response = client.post(url+'/public-proof', json=dict(expected_publication_version=context['publication_version'],
        binding_hash=context['binding_hash'], observation=observation(context),
        reason='Executable hostile-input regression at the actual operator boundary.'), headers=key())
    if response.status_code != 201:
        return response
    return make_client(engine, actor=REVIEWER).post(url+'/record-existing', json=dict(
        expected_publication_version=context['publication_version'], proof_id=response.json()['proof_id'],
        observation=observation(context, 'b'), reason='Independent regression admission must refuse contradictory evidence.'), headers=key())


@pytest.mark.parametrize('field', ['remote_refs', 'checkpoint'])
def test_retained_sibling_identity_without_primary_refuses(recovery_pg, field):
    with Session(recovery_pg, expire_on_commit=False) as db:
        first = pending(db, owner_id='7241234')
        sibling = db.get(SocialPostTarget, first)
        sibling.primary_remote_id = None
        sibling.remote_refs = {} if field=='checkpoint' else {'post_id':'9001'}
        if field=='checkpoint':
            # A retained identity is sufficient to require investigation even
            # where the sibling's other checkpoint fields are unavailable.
            sibling.checkpoint = {'post_id':'9001'}
        db.commit()
        second = pending(db, owner_id='7241234', product='another-product')
    response = attempt_settlement(recovery_pg, second)
    assert response.status_code == 409, response.text
    assert response.json()['detail']['code'] == 'PROOF_REPLAY'
    with Session(recovery_pg) as db:
        assert db.get(SocialPostTarget, second).state == 'outcome_unknown'


@pytest.mark.parametrize('checkpoint', [[], '', False, 0, None])
def test_malformed_falsey_checkpoint_never_becomes_public(recovery_pg, checkpoint):
    with Session(recovery_pg, expire_on_commit=False) as db:
        target_id = pending(db)
        # NOT NULL protects SQL NULL; JSON null remains externally shaped JSON.
        db.get(SocialPostTarget, target_id).checkpoint = checkpoint
        db.commit()
    response = attempt_settlement(recovery_pg, target_id)
    assert response.status_code == 409, response.text
    assert response.json()['detail']['code'] == 'PROOF_BINDING_INVALID'


@pytest.mark.parametrize('intent', [None, {}, {'publication_capable':False}, {'publication_capable':1},
    {'publication_capable':True, 'mutating':False, 'safe_replay_class':'read_only'},
    {'publication_capable':True, 'mutating':True, 'safe_replay_class':'safe'}])
def test_contradictory_or_absent_public_intent_never_becomes_public(recovery_pg, intent):
    with Session(recovery_pg, expire_on_commit=False) as db:
        target_id = pending(db)
        attempt = db.scalar(select(SocialPublishAttempt).where(SocialPublishAttempt.target_id==target_id))
        attempt.receipt = {'intent':intent}
        db.commit()
    response = attempt_settlement(recovery_pg, target_id)
    assert response.status_code == 409, response.text
    assert response.json()['detail']['code'] == 'RECONCILIATION_REQUIRED'


def test_deferred_target_alteration_is_checked_before_commit(recovery_pg):
    target_id, url, context, first, body = proposed(recovery_pg)
    with recovery_pg.begin() as conn:
        conn.execute(text("""CREATE FUNCTION b16_deferred_alter() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            UPDATE social_post_targets SET remote_url='https://www.threads.com/@wrong/post/nope' WHERE id=NEW.id;
            RETURN NULL; END $$"""))
        conn.execute(text("""CREATE CONSTRAINT TRIGGER b16_deferred AFTER UPDATE ON social_post_targets
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            WHEN (NEW.state='published' AND NEW.remote_url <> 'https://www.threads.com/@wrong/post/nope')
            EXECUTE FUNCTION b16_deferred_alter()"""))
    response = make_client(recovery_pg, actor=REVIEWER).post(url+'/record-existing', json=body, headers=key())
    assert response.status_code == 503, response.text
    assert response.json()['detail']['code'] == 'RECOVERY_PERSISTENCE_FAILED'
    with Session(recovery_pg) as db:
        assert db.get(SocialPostTarget, target_id).state == 'outcome_unknown'
        assert not list(db.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action=='threads.public_proof_admitted')))


def test_operator_target_lock_fences_actual_worker_claim(recovery_pg, monkeypatch):
    import threading
    from test_queue_postgres import repository
    with Session(recovery_pg, expire_on_commit=False) as db:
        target_id = pending(db)
        target = db.get(SocialPostTarget, target_id)
        target.state, target.next_action = 'processing', 'poll'
        target.next_action_at = ThreadsRecoveryService(db).now()-timedelta(seconds=1)
        db.commit()
    client = make_client(recovery_pg)
    url = f'/api/v1/admin/social/targets/{target_id}'
    context = client.get(url+'/public-proof').json()
    first = client.post(url+'/public-proof', json=dict(expected_publication_version=context['publication_version'],
        binding_hash=context['binding_hash'], observation=observation(context), reason='Owned worker-operator interleaving proof control.'), headers=key())
    assert first.status_code == 201, first.text
    body = dict(expected_publication_version=context['publication_version'], proof_id=first.json()['proof_id'],
        observation=observation(context, 'b'), reason='Independent owned worker-operator interleaving control.')
    repo = repository(recovery_pg)
    locked, release = threading.Event(), threading.Event()
    original = ThreadsRecoveryService._observation
    def pause_after_observation(self, *args):
        original(self, *args)
        if self.actor == REVIEWER:
            locked.set()
            assert release.wait(5), 'Operator interleaving fixture was not released'
    monkeypatch.setattr(ThreadsRecoveryService, '_observation', pause_after_observation)
    with ThreadPoolExecutor(max_workers=1) as pool:
        admission = pool.submit(lambda: make_client(recovery_pg, actor=REVIEWER).post(url+'/record-existing', json=body, headers=key()))
        try:
            assert locked.wait(5), 'Admission did not reach the locked proof check'
            assert repo.claim_due(1) == []  # actual SKIP LOCKED target admission
        finally:
            release.set()
        assert admission.result(timeout=5).status_code == 200
    assert repo.claim_due(1) == []


def test_actual_worker_claim_first_refuses_operator_and_keeps_ownership(recovery_pg):
    from test_queue_postgres import repository
    with Session(recovery_pg, expire_on_commit=False) as db:
        target_id = pending(db)
        target = db.get(SocialPostTarget, target_id)
        target.state, target.next_action = 'processing', 'poll'
        target.next_action_at = ThreadsRecoveryService(db).now()-timedelta(seconds=1)
        db.commit()
    client = make_client(recovery_pg)
    url = f'/api/v1/admin/social/targets/{target_id}'
    context = client.get(url+'/public-proof').json()
    first = client.post(url+'/public-proof', json=dict(expected_publication_version=context['publication_version'],
        binding_hash=context['binding_hash'], observation=observation(context), reason='Durable proof preceding actual repository claim.'), headers=key())
    assert first.status_code == 201, first.text
    repo = repository(recovery_pg)
    claim, = repo.claim_due(1)
    body = dict(expected_publication_version=context['publication_version'], proof_id=first.json()['proof_id'],
        observation=observation(context, 'b'), reason='Independent review must respect current worker ownership.')
    response = make_client(recovery_pg, actor=REVIEWER).post(url+'/record-existing', json=body, headers=key())
    assert response.status_code == 409 and response.json()['detail']['code'] == 'RECOVERY_BUSY'
    with Session(recovery_pg) as db:
        target = db.get(SocialPostTarget, target_id)
        assert str(target.lease_token) == claim.token and target.lease_epoch == claim.epoch and target.state == 'processing'
    repo.abandon(claim, state='outcome_unknown', code='FIXTURE_RECOVERY_COMPLETE')

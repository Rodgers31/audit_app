"""Real sticky global-owner races and restricted direct-bypass controls."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import text

from social.worker.config import WorkerConfig
from social.worker.ownership import AuthorityLost, RuntimeAuthority, acquire_authority, check_authority, release_authority
from social.worker.repository import QueueRepository
from test_connections_migration_postgres import _migration
from worker_ownership_support import role_database
from social.worker.role_contract import install_worker_role, verify_worker_role


def receipt(authority):
    return dict(version=1, owner_id=str(authority.owner_id), generation=authority.generation,
                process_joined=True, worker_exit_code=0, providers_closed=True,
                executor_closed=True, claims_drained=True)


def repo(engine, authority=None):
    return QueueRepository(engine, WorkerConfig(engine.url.render_as_string(hide_password=False)),
                           authority.owner_id if authority else uuid4(), authority=authority)


def test_one_whole_budget_owner_under_contenders_and_old_heartbeat(role_database):
    owner, _, _, _ = role_database
    def contend(i):
        try: return acquire_authority(owner, uuid4(), 'overlap-' + str(i))
        except AuthorityLost as error: return str(error)
    with ThreadPoolExecutor(max_workers=6) as threads:
        outcomes = list(threads.map(contend, range(6)))
    winners = [x for x in outcomes if isinstance(x, RuntimeAuthority)]
    assert len(winners) == 1
    assert outcomes.count('GLOBAL_WORKER_OWNED') == 5
    with owner.begin() as conn:
        conn.execute(text("UPDATE social_worker_heartbeats SET heartbeat_at='2000-01-01'"))
    with pytest.raises(AuthorityLost, match='GLOBAL_WORKER_OWNED'):
        acquire_authority(owner, uuid4(), 'rollback')
    with owner.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM social_worker_runtime_history')).scalar_one() == 1


@pytest.mark.parametrize('entry', ['check_authority','validate_schema','claim_due','recover_expired','next_due_delay'])
def test_direct_queue_paths_refuse_without_authority(role_database, entry):
    owner, _, _, _ = role_database
    repository = repo(owner)
    with pytest.raises(AuthorityLost):
        getattr(repository, entry)(60) if entry == 'next_due_delay' else getattr(repository, entry)()


def test_release_requires_positive_typed_proof_and_never_reuses_generation(role_database):
    owner, _, _, _ = role_database
    old = acquire_authority(owner, uuid4(), 'old')
    for key in receipt(old):
        bad = receipt(old); bad.pop(key)
        with pytest.raises(AuthorityLost): release_authority(owner, old, bad)
    for key in ('process_joined','providers_closed','executor_closed','claims_drained'):
        for value in (False, 1, 'true', None):
            bad = receipt(old); bad[key] = value
            with pytest.raises(AuthorityLost): release_authority(owner, old, bad)
    for key in ('generation','version','worker_exit_code'):
        bad = receipt(old); bad[key] = True
        with pytest.raises(AuthorityLost): release_authority(owner, old, bad)
    release_authority(owner, old, receipt(old))
    new = acquire_authority(owner, uuid4(), 'new')
    assert new.generation == old.generation + 1
    for forged in (old, RuntimeAuthority(uuid4(), new.generation), RuntimeAuthority(new.owner_id, new.generation + 1)):
        with pytest.raises(AuthorityLost): repo(owner, forged).claim_due()
    with pytest.raises(AuthorityLost): release_authority(owner, old, receipt(old))
    with owner.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM social_worker_runtime_history')).scalar_one() == 3
    with pytest.raises(RuntimeError, match='history'):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        with owner.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            _migration('a545b14a0001_social_worker_global_owner.py').downgrade()


def test_restricted_role_can_acquire_but_cannot_release_or_forge_history(role_database):
    owner, worker, schema, role = role_database
    install_worker_role(owner, role, schema)
    verify_worker_role(worker, role, schema)
    authority = acquire_authority(worker, uuid4(), 'restricted')
    repo(worker, authority).validate_schema()
    repo(worker, authority).claim_due()
    for sql in [
        'DELETE FROM social_worker_runtime_ownership',
        'UPDATE social_worker_runtime_ownership SET generation=generation+1',
        'TRUNCATE social_worker_runtime_ownership',
        'DELETE FROM social_worker_runtime_history',
        "INSERT INTO social_worker_runtime_history SELECT generation,'released',owner_id,deployment_version,'{}'::jsonb,clock_timestamp() FROM social_worker_runtime_ownership",
    ]:
        with pytest.raises(Exception):
            with worker.begin() as conn: conn.execute(text(sql))
    with pytest.raises(Exception): release_authority(worker, authority, receipt(authority))
    with owner.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM social_worker_runtime_history')).scalar_one() == 1


def test_missing_singleton_constraint_refuses_before_admission(role_database):
    owner, _, _, _ = role_database
    with owner.begin() as conn:
        conn.execute(text('ALTER TABLE social_worker_runtime_ownership DROP CONSTRAINT social_worker_runtime_ownership_pkey'))
    with pytest.raises(AuthorityLost, match='SCHEMA_UNAVAILABLE'):
        acquire_authority(owner, uuid4(), 'invalid-schema')
    with owner.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM social_worker_runtime_history')).scalar_one() == 0


def seeded(role_database):
    from test_queue_postgres import seed
    owner, _, _, _ = role_database
    with owner.begin() as conn: conn.execute(text('DELETE FROM social_controls'))
    ids = seed(owner)
    authority = acquire_authority(owner, uuid4(), 'intent-fixture')
    return owner, repo(owner, authority), authority, ids


def test_copied_global_reference_cannot_start_or_settle_provider_intent(role_database):
    from test_queue_postgres import intent
    owner, repository, authority, ids = seeded(role_database)
    claim = repository.claim_due()[0]
    # A copied value has not acquired authority in this process.
    copied = repo(owner, RuntimeAuthority(authority.owner_id, authority.generation))
    with pytest.raises(AuthorityLost): copied.begin_operation(claim, operation_id=uuid4(), operation='publish',
        publication_capable=True, mutating=True, safe_replay_class='requires_reconciliation',
        request_fingerprint='a'*64, checkpoint_input={})
    admitted = intent(repository, claim)
    with pytest.raises(AuthorityLost):
        copied.finish(claim, admitted, state='published', outcome='confirmed_success', checkpoint={},remote_refs={},
            remote_id='observed-id', visibility_state='public', confirmation_kind='fake-confirmed',
            receipt={'primary_remote_id':'observed-id'})
    with owner.connect() as conn:
        row = conn.execute(text('SELECT completed_at,receipt FROM social_publish_attempts')).one()
        assert row.completed_at is None and 'primary_remote_id' not in row.receipt
        assert conn.execute(text('SELECT state FROM social_post_targets')).scalar_one() == 'dispatching'


def test_one_bound_runtime_and_copied_or_forked_reference_cannot_bypass_acquire(role_database):
    import asyncio, os
    from social.worker.runner import SocialWorker
    owner, _, _, _ = role_database
    authority = acquire_authority(owner, uuid4(), 'one-runtime')
    first = SocialWorker(repo(owner, authority))
    try:
        with pytest.raises(AuthorityLost): SocialWorker(repo(owner, authority))
        copied = RuntimeAuthority(authority.owner_id, authority.generation)
        with pytest.raises(AuthorityLost): repo(owner, copied).claim_due()
        pid = os.fork()
        if pid == 0:
            # Do not touch inherited DB sockets: local receipt must reject first.
            from social.worker.ownership import bind_runtime
            try: bind_runtime(authority, object())
            except AuthorityLost: os._exit(0)
            os._exit(2)
        _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
    finally:
        asyncio.run(first.close())


def test_settled_ambiguity_allows_positive_release_but_unfinished_intent_refuses(role_database):
    from test_queue_postgres import intent
    owner, repository, authority, ids = seeded(role_database)
    claim = repository.claim_due()[0]
    admitted = intent(repository, claim)
    with pytest.raises(AuthorityLost, match='UNRESOLVED'):
        release_authority(owner, authority, receipt(authority))
    repository.finish(claim, admitted, state='reconciling',outcome='ambiguous',checkpoint={},remote_refs={})
    with owner.begin() as conn:
        conn.execute(text("UPDATE social_post_targets SET next_action_at=now()-interval '1 second'"))
    recovery = repository.claim_due()[0]
    read = intent(repository, recovery, public=False, operation='reconcile',replay='read_only')
    repository.finish(recovery, read, state='published',outcome='confirmed_success',checkpoint={},remote_refs={},
        remote_id='settled',visibility_state='public',confirmation_kind='fake-confirmed')
    release_authority(owner, authority, receipt(authority))
    assert acquire_authority(owner, uuid4(), 'next').generation == authority.generation + 1


def test_empty_upgrade_downgrade_and_browser_denial(role_database):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    owner, _, schema, _ = role_database
    with owner.begin() as conn:
        rows=conn.execute(text("SELECT relname,relrowsecurity FROM pg_class WHERE relnamespace=CAST(:schema AS regnamespace) AND relkind='r' AND relname LIKE :pattern"),
                          {'schema':schema,'pattern':'social_worker_runtime_%'}).all()
        assert len(rows)==2 and all(row.relrowsecurity for row in rows)
        for table,_ in rows:
            assert not conn.execute(text("SELECT EXISTS(SELECT 1 FROM pg_class c,LATERAL aclexplode(c.relacl) a WHERE c.oid=CAST(:table AS regclass) AND a.grantee=0)"),{'table':table}).scalar_one()
        with Operations.context(MigrationContext.configure(conn)):
            _migration('a545b14a0001_social_worker_global_owner.py').downgrade()
            _migration('a545b14a0001_social_worker_global_owner.py').upgrade()
    assert acquire_authority(owner,uuid4(),'after-empty-downgrade').generation==1


@pytest.mark.parametrize('kind', ['missing', 'copied', 'wrong_repository_owner'])
def test_unissued_repository_cannot_settle_pending_provider_intent(role_database, kind):
    from test_queue_postgres import intent
    owner, repository, authority, _ = seeded(role_database)
    claim = repository.claim_due()[0]
    admitted = intent(repository, claim)
    candidate = None if kind == 'missing' else RuntimeAuthority(authority.owner_id, authority.generation) if kind == 'copied' else authority
    unissued = QueueRepository(owner, repository.config,
                              uuid4() if kind == 'wrong_repository_owner' else authority.owner_id,
                              authority=candidate)
    with pytest.raises(AuthorityLost, match='AUTHORITY_REQUIRED'):
        unissued.finish(claim, admitted, state='published', outcome='confirmed_success',
                        checkpoint={}, remote_refs={}, remote_id='forged-observation',
                        visibility_state='public', confirmation_kind='synthetic')
    with owner.connect() as conn:
        attempt = conn.execute(text('SELECT completed_at,outcome,receipt FROM social_publish_attempts')).one()
        assert attempt.completed_at is None and attempt.outcome == 'intent'
        assert 'forged-observation' not in str(attempt.receipt)
        assert conn.execute(text('SELECT state FROM social_post_targets')).scalar_one() == 'dispatching'


def test_successor_authority_cannot_settle_predecessor_provider_intent(role_database):
    import json
    from test_queue_postgres import intent
    owner, predecessor, authority, _ = seeded(role_database)
    claim = predecessor.claim_due()[0]
    admitted = intent(predecessor, claim)
    # Simulate an external administrative generation replacement. The supported
    # release API separately refuses this unresolved intent; no real provider ran.
    with owner.begin() as conn:
        conn.execute(text('''INSERT INTO social_worker_runtime_history
            (generation,event,owner_id,deployment_version,proof)
            SELECT generation,'released',owner_id,deployment_version,CAST(:proof AS jsonb)
            FROM social_worker_runtime_ownership'''), {'proof': json.dumps(receipt(authority))})
        conn.execute(text('DELETE FROM social_worker_runtime_ownership'))
    successor = repo(owner, acquire_authority(owner, uuid4(), 'successor'))
    assert successor.finish(claim, admitted, state='published', outcome='confirmed_success',
                            checkpoint={}, remote_refs={}, remote_id='wrong-runtime',
                            visibility_state='public', confirmation_kind='synthetic') is False
    with owner.connect() as conn:
        assert conn.execute(text('SELECT completed_at FROM social_publish_attempts')).scalar_one() is None
        assert conn.execute(text('SELECT state FROM social_post_targets')).scalar_one() == 'dispatching'
    # The original process-bound issuance still retains its own late observation.
    assert predecessor.finish(claim, admitted, state='published', outcome='confirmed_success',
                              checkpoint={}, remote_refs={}, remote_id='old-observation',
                              visibility_state='public', confirmation_kind='synthetic',
                              receipt={'primary_remote_id': 'old-observation'}) is False
    with owner.connect() as conn:
        completed = conn.execute(text('SELECT completed_at,receipt FROM social_publish_attempts')).one()
        assert completed.completed_at is not None and completed.receipt['primary_remote_id'] == 'old-observation'
        assert conn.execute(text('SELECT state FROM social_post_targets')).scalar_one() == 'dispatching'

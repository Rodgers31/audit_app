"""Real material freshness after durable intent; isolated domain schema only.

The imported native helpers accept this test's random-schema engine directly.
The shared worker engine fixture and its TRUNCATE lane are never requested.
"""
import asyncio
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from social.models import SocialPostTarget, SocialPublishAttempt
from social.worker.runner import SocialWorker
from test_connections_support import config
from test_connections_migration_postgres import upgrade
from test_domain_postgres import pg_engine
from test_native_meta_adapters import Graph
from test_native_worker_postgres import prepare, registration
from test_queue_postgres import repository


def test_pg_post_intent_rotation_blocks_send_then_recovery_loads_fresh_material(pg_engine, config, monkeypatch):
    upgrade(pg_engine, current=True)

    graph = Graph()
    storage, target_id = prepare(pg_engine, config, graph, monkeypatch)
    repo = repository(pg_engine)
    reg = registration(pg_engine, config, storage, graph)
    original_begin = repo.begin_operation
    observed = []

    async def load(request):
        observed.append(request)
        return await reg.credential_loader(request)

    def commit_then_rotate(claim, **kwargs):
        intent = original_begin(claim, **kwargs)
        assert intent is not None
        # This separate transaction runs strictly after dispatch permission and
        # the durable intent have committed, before the real loader sees them.
        with pg_engine.begin() as conn:
            conn.execute(text('UPDATE social_credentials SET version=version+1 '
                'WHERE id=(SELECT credential_id FROM social_accounts WHERE id=CAST(:id AS uuid))'),
                {'id': claim.account_id})
        return intent

    async def process_once():
        worker = SocialWorker(repo, adapters=reg.adapters, credential_loader=load, media_access=reg.media_access)
        try:
            claims = await worker.db(repo.claim_due, 1)
            assert len(claims) == 1
            await worker.process(claims[0])
        finally:
            await worker.close()

    try:
        repo.begin_operation = commit_then_rotate
        asyncio.run(process_once())
        with Session(pg_engine) as db:
            target = db.get(SocialPostTarget, target_id)
            attempt = db.scalar(select(SocialPublishAttempt))
            assert target.state == 'dispatching' and target.submit_count == 1
            assert attempt.outcome == 'intent' and attempt.completed_at is None
            original_operation_id = attempt.operation_id
        assert len(observed) == 1 and observed[0].credential_version == 1
        assert observed[0].mutating is True
        assert not graph.calls

        repo.begin_operation = original_begin
        with pg_engine.begin() as conn:
            conn.execute(text("UPDATE social_post_targets SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"),
                {'id': target_id})
            conn.execute(text("UPDATE social_accounts SET publish_lease_expires_at=clock_timestamp()-interval '1 second' WHERE publish_lease_target_id=:id"),
                {'id': target_id})
        repo.recover_expired()
        with pg_engine.begin() as conn:
            conn.execute(text("UPDATE social_post_targets SET next_action_at=clock_timestamp()-interval '1 second' WHERE id=:id"),
                {'id': target_id})

        adapter = reg.adapters[('facebook', 'facebook_pages')]
        original_reconcile = adapter.reconcile
        received = []

        async def reconcile(payload, checkpoint, attempt, credential, media_access):
            assert credential.credential_version == 2
            received.append(credential)
            return await original_reconcile(payload, checkpoint, attempt, credential, media_access)

        adapter.reconcile = reconcile
        asyncio.run(process_once())
        assert len(observed) == 2 and observed[1].mutating is False and observed[1].credential_version == 2
        assert observed[1].operation_id != original_operation_id
        assert len(received) == 1 and not graph.calls
        with Session(pg_engine) as db:
            target = db.get(SocialPostTarget, target_id)
            assert target.state == 'outcome_unknown' and target.submit_count == 1
            attempts = list(db.scalars(select(SocialPublishAttempt).order_by(SocialPublishAttempt.sequence)))
            assert len(attempts) == 2
            assert attempts[0].operation_id == original_operation_id
            assert attempts[0].outcome == 'intent' and attempts[0].completed_at is None
            assert attempts[1].operation == 'reconcile'
    finally:
        asyncio.run(reg.close())

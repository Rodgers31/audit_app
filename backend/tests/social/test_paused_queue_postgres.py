"""Paused normal queue items perform no claim writes; recovery reads continue."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from test_queue_postgres import engine, repository, seed, row, intent


def pause(engine, scope):
    with engine.begin() as conn:
        if scope == 'global':
            conn.execute(text('UPDATE social_controls SET publishing_enabled=false'))
        else:
            conn.execute(
                text('UPDATE social_controls SET platform_controls=CAST(:control AS jsonb)'),
                {'control': '{"facebook":{"publishing_enabled":false}}'},
            )


def snapshot(engine):
    with engine.connect() as conn:
        return (
            conn.execute(text('SELECT to_jsonb(t) FROM social_post_targets t ORDER BY id')).scalars().all(),
            conn.execute(text('SELECT count(*) FROM social_audit_events')).scalar(),
            conn.execute(text('SELECT count(*) FROM social_publish_attempts')).scalar(),
        )


@pytest.mark.parametrize('scope', ['global', 'platform'])
@pytest.mark.parametrize('state', ['queued', 'retry_wait'])
def test_paused_normal_targets_are_not_claimed_or_rewritten(engine, scope, state):
    ids = seed(engine, state=state)
    pause(engine, scope)
    repo = repository(engine)
    before = snapshot(engine)
    for _ in range(3):
        assert repo.claim_due() == []
    assert snapshot(engine) == before
    assert row(engine, ids['targets'][0])['lease_epoch'] == 0
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_post_targets SET next_action_at=now()+interval '2 seconds'"))
    assert repo.next_due_delay(60) == 60


@pytest.mark.parametrize('scope', ['global', 'platform'])
@pytest.mark.parametrize('state,operation', [('processing', 'poll'), ('reconciling', 'reconcile')])
def test_paused_recovery_states_remain_claimable_for_read_intents(engine, scope, state, operation):
    ids = seed(engine, state=state)
    pause(engine, scope)
    repo = repository(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_post_targets SET next_action_at=now()+interval '2 seconds'"))
    assert 0 < repo.next_due_delay(60) <= 2
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_post_targets SET next_action_at=now()-interval '1 second'"))
    claim = repo.claim_due()[0]
    admitted = repo.begin_operation(
        claim, operation_id=uuid4(), operation=operation,
        publication_capable=False, mutating=False, safe_replay_class='read_only',
        request_fingerprint='a' * 64, checkpoint_input={},
    )
    assert admitted is not None
    assert row(engine, ids['targets'][0])['submit_count'] == 0


def test_paused_queue_does_not_hide_or_wake_before_recovery_work(engine):
    ids = seed(engine, count=2)
    pause(engine, 'global')
    repo = repository(engine)
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE social_post_targets SET next_action_at=now()+interval '0.2 seconds' WHERE id=:id
        """), {'id': ids['targets'][0]})
        conn.execute(text("""
            UPDATE social_post_targets SET state='reconciling',next_action_at=now()+interval '5 seconds'
            WHERE id=:id
        """), {'id': ids['targets'][1]})
    assert 4 < repo.next_due_delay(60) <= 5
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_post_targets SET next_action_at=now()-interval '1 second'"))
    claims = repo.claim_due(2)
    assert [c.target_id for c in claims] == [str(ids['targets'][1])]
    assert row(engine, ids['targets'][0])['lease_epoch'] == 0


def test_platform_pause_leaves_other_platform_claims_and_wakeups_eligible(engine):
    ids = seed(engine, count=2)
    pause(engine, 'platform')
    repo = repository(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_accounts SET platform='instagram' WHERE id=:id"),
                     {'id': ids['accounts'][1]})
        conn.execute(text("""
            UPDATE social_post_targets SET next_action_at=now()+interval '0.2 seconds' WHERE id=:id
        """), {'id': ids['targets'][0]})
        conn.execute(text("""
            UPDATE social_post_targets SET next_action_at=now()+interval '5 seconds' WHERE id=:id
        """), {'id': ids['targets'][1]})
    assert 4 < repo.next_due_delay(60) <= 5
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_post_targets SET next_action_at=now()-interval '1 second'"))
    assert [claim.target_id for claim in repo.claim_due(2)] == [str(ids['targets'][1])]
    assert row(engine, ids['targets'][0])['lease_epoch'] == 0


@pytest.mark.parametrize('scope', ['global', 'platform'])
def test_resume_reconsiders_unchanged_queued_authorization(engine, scope):
    ids = seed(engine)
    pause(engine, scope)
    repo = repository(engine)
    before = snapshot(engine)
    assert repo.claim_due() == []
    assert snapshot(engine) == before
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_controls SET publishing_enabled=true,platform_controls='{}'::jsonb"))
    claim = repo.claim_due()[0]
    assert claim.target_id == str(ids['targets'][0])
    assert intent(repo, claim) is not None


@pytest.mark.parametrize('scope', ['global', 'platform'])
def test_pause_after_claim_still_refuses_mutation(engine, scope):
    ids = seed(engine)
    repo = repository(engine)
    claim = repo.claim_due()[0]
    pause(engine, scope)
    assert intent(repo, claim) is None
    assert row(engine, ids['targets'][0])['submit_count'] == 0
    with engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM social_publish_attempts')).scalar() == 0


def test_missing_controls_are_not_misreported_as_paused_empty_queue(engine):
    seed(engine)
    repo = repository(engine)
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM social_controls'))
    claim = repo.claim_due()[0]
    assert intent(repo, claim) is None
    assert row(engine, claim.target_id)['error_code'] == 'SOCIAL_SCHEMA_UNAVAILABLE'


@pytest.mark.parametrize('control', [
    '{"other":{"publishing_enabled":false}}',
    '{"facebook":{"publishing_enabled":"false"}}',
])
def test_only_explicit_boolean_platform_pause_suppresses_claims(engine, control):
    seed(engine)
    repo = repository(engine)
    with engine.begin() as conn:
        conn.execute(text('UPDATE social_controls SET platform_controls=CAST(:control AS jsonb)'), {'control': control})
    assert len(repo.claim_due()) == 1

"""Post-commit hook fails visibly, remains off and never borrows writer state."""
import sys
from types import ModuleType

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker

from social.models import SocialPost, SocialAuditEvent, SocialPublication
from social.generation.integration import maybe_generate_committed
from test_domain_support import db
from test_generation import configure, observation


def source(monkeypatch):
    module = ModuleType('seeding.source_observations')
    class Unavailable(Exception):
        pass
    module.SourceObservationUnavailable = Unavailable
    def read(factory, *, record_id, ingestion_id):
        if record_id == 2:
            raise Unavailable('Missing reviewed evidence')
        return observation(ingestion_id, source_key=f'county:{record_id}').model_dump(mode='json')
    module.read_county_budget_observation = read
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module


def test_hook_default_off_without_database_or_import(monkeypatch):
    monkeypatch.delenv('SOCIAL_GENERATION_HOOK_ENABLED', raising=False)
    def forbidden():
        pytest.fail('Default-off hook opened a database session')
    result = maybe_generate_committed(forbidden, record_ids=[1], ingestion_id=1)
    assert result['state'] == 'disabled' and result['processed'] == 0


@pytest.mark.parametrize('values,job', [([],1), ([True],1), ([0],1), ([1,1],1), ([1],True), (list(range(1,1002)),1), (None,1)])
def test_hook_rejects_invalid_cohorts_before_factory(values, job):
    def forbidden():
        pytest.fail('Malformed cohort opened a session')
    assert maybe_generate_committed(forbidden, record_ids=values, ingestion_id=job)['reason'] == 'INVALID_RECORD_COHORT'


def test_hook_pipeline_audit_baseline_change_replay_and_partial_refusal(db, monkeypatch):
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'true')
    module = source(monkeypatch)
    configure(db)
    factory = sessionmaker(bind=db.bind, expire_on_commit=False)
    first = maybe_generate_committed(factory, record_ids=[1], ingestion_id=1)
    assert first['state'] == 'completed' and first['baselines'] == 1
    module.read_county_budget_observation = lambda factory, **kwargs: observation(2, '456', source_key='county:1').model_dump(mode='json')
    result = maybe_generate_committed(factory, record_ids=[1], ingestion_id=2)
    assert result['state'] == 'completed' and result['drafts_created'] == 1
    assert maybe_generate_committed(factory, record_ids=[1], ingestion_id=2)['unchanged'] == 1
    with factory() as check:
        assert check.scalar(select(func.count()).select_from(SocialPost)) == 1
        assert check.scalar(select(func.count()).select_from(SocialPublication)) == 0
        audit = check.scalar(select(SocialAuditEvent).where(SocialAuditEvent.action == 'generation.draft_created'))
        assert audit.actor_kind == 'pipeline' and audit.actor_id is None
    source(monkeypatch)
    partial = maybe_generate_committed(factory, record_ids=[2,3], ingestion_id=3)
    assert partial['state'] == 'unavailable' and partial['refused'] == 1 and partial['baselines'] == 1


def test_hook_refuses_existing_writer_without_rolling_it_back(db, monkeypatch):
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'true')
    pending = SocialPost(title='Caller-owned pending work', content_type='announcement', editorial_state='draft')
    db.add(pending)
    result = maybe_generate_committed(lambda: db, record_ids=[1], ingestion_id=1)
    assert result['reason'] == 'FRESH_SESSION_REQUIRED'
    assert pending in db.new and db.in_transaction()


def test_malformed_flag_and_missing_schema_are_visible(db, monkeypatch):
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'TRUE')
    assert maybe_generate_committed(lambda: None, record_ids=[1], ingestion_id=1)['state'] == 'unavailable'
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'true')
    factory = sessionmaker(bind=db.bind)
    assert maybe_generate_committed(factory, record_ids=[1], ingestion_id=1)['reason'] == 'RUNTIME_SOURCE_DISABLED'


def test_hook_deadline_stops_after_confirmed_partial_progress(db, monkeypatch):
    import social.generation.integration as integration
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'true')
    module = source(monkeypatch)
    configure(db)
    factory = sessionmaker(bind=db.bind, expire_on_commit=False)
    clock = [0.0]
    monkeypatch.setattr(integration.time, 'monotonic', lambda: clock[0])
    read = module.read_county_budget_observation
    def advancing(factory, **kwargs):
        result = read(factory, **kwargs)
        clock[0] += 16
        return result
    monkeypatch.setattr(module, 'read_county_budget_observation', advancing)
    result = maybe_generate_committed(factory, record_ids=[1,3], ingestion_id=1)
    assert result['state'] == 'failed' and result['reason'] == 'GENERATION_DEADLINE_EXCEEDED', result
    assert result['processed'] == 1 and result['baselines'] == 1
    with factory() as check:
        from social.generation.models import SourceCursor
        assert check.scalar(select(func.count()).select_from(SourceCursor)) == 1


def test_hook_deadline_before_commit_rolls_back_current_event(db, monkeypatch):
    import social.generation.integration as integration
    from social.generation.models import SourceCursor
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'true')
    source(monkeypatch)
    configure(db)
    factory = sessionmaker(bind=db.bind, expire_on_commit=False)
    clock = [0.0]
    monkeypatch.setattr(integration.time, 'monotonic', lambda: clock[0])
    consume = integration.consume_observation
    def expires(svc, value):
        result = consume(svc, value)
        clock[0] = 31.0
        return result
    monkeypatch.setattr(integration, 'consume_observation', expires)
    result = maybe_generate_committed(factory, record_ids=[1], ingestion_id=1)
    assert result['state'] == 'failed' and result['reason'] == 'GENERATION_DEADLINE_EXCEEDED'
    assert result['processed'] == 0
    with factory() as check:
        assert check.scalar(select(func.count()).select_from(SourceCursor)) == 0

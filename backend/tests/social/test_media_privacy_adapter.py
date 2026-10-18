"""Executable media bridge contract using durable SQL policy fixtures.

The predecessor's real signed-ledger integration is a separate combined replay;
these fixtures isolate this lane's authority/read-only and HTTP composition.
"""
from dataclasses import dataclass, replace
from types import ModuleType
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, JSON, Text, Uuid, event
from sqlalchemy.orm import declarative_base, sessionmaker

from social.contracts import canonical_hash
from social.media.deletion import MediaDeletionExecutor
from social.media.privacy_adapter import PrivacyWorkflowMediaAdapter
from test_media_payload_retirement import configured, granted
from test_media_support import media, media_db


@pytest.fixture
def bridge(media, monkeypatch):
    service, storage = configured(media[0])
    service.config = replace(service.config, retirement_policy_hashes=('b' * 64,))
    runtime = replace(service.runtime, config=service.config)
    factory = sessionmaker(service.db.bind, expire_on_commit=False)
    base = declarative_base()
    class Plan(base):
        __tablename__ = 'fixture_privacy_plan'
        id = Column(Uuid, primary_key=True)
        receipt_id = Column(Uuid)
        proposed_by = Column(Uuid)
        policy_key = Column(Text)
        policy_hash = Column(Text)
        evidence = Column(Text)
        scope = Column(JSON)
        plan_hash = Column(Text)
    class Decision(base):
        __tablename__ = 'fixture_privacy_decision'
        id = Column(Uuid, primary_key=True, default=uuid4)
        plan_id = Column(Uuid)
        approved_by = Column(Uuid)
        plan_hash = Column(Text)
        decision = Column(Text)
    class Execution(base):
        __tablename__ = 'fixture_privacy_execution'
        id = Column(Uuid, primary_key=True)
        plan_id = Column(Uuid)
        state = Column(Text)
    base.metadata.create_all(service.db.bind)
    models = ModuleType('social.privacy.workflow_models')
    models.PrivacyPlan, models.PrivacyDecision, models.PrivacyExecution = Plan, Decision, Execution
    monkeypatch.setitem(__import__('sys').modules, models.__name__, models)
    port = ModuleType('social.privacy.media_port')
    @dataclass(frozen=True)
    class Command:
        operation_id: UUID
        authority_id: UUID
        asset_id: UUID
        plan_hash: str
        policy_hash: str
    @dataclass(frozen=True)
    class Result:
        operation_id: UUID
        asset_id: UUID
        state: str
        verified_deleted: bool
    port.PrivacyMediaDeletionCommand, port.PrivacyMediaDeletionResult = Command, Result
    monkeypatch.setitem(__import__('sys').modules, port.__name__, port)
    validator = ModuleType('social.privacy.deletion_ledger')
    def validate(value):
        if type(value) is not dict or value.get('schema_version') != 1:
            raise ValueError('fixture malformed ledger')
    validator.validate_intent = validate
    monkeypatch.setitem(__import__('sys').modules, validator.__name__, validator)
    class Ledger:
        intent = None
        def read(self, operation):
            if self.intent is None or self.intent['operation_id'] != str(operation):
                raise ValueError('fixture missing signed ledger')
            return self.intent
    ledger = Ledger()
    adapter = PrivacyWorkflowMediaAdapter(factory, runtime, ledger)
    identity = granted(service, storage)
    scope = {'credentials': [], 'flows': [], 'media_assets': [
        {'id': str(identity), 'scope_hash': adapter.inspect_scope(identity)['scope_hash']}]}
    plan_id, receipt_id, parent = uuid4(), uuid4(), uuid4()
    plan_value = {'receipt_id': str(receipt_id), 'policy_key': 'reviewed-storage-policy',
        'policy_hash': 'b' * 64, 'evidence': 'Explicit synthetic fixture', 'scope': scope}
    digest = canonical_hash(plan_value)
    with factory() as db, db.begin():
        db.add(Plan(id=plan_id, receipt_id=receipt_id, proposed_by=uuid4(), **{k:v for k,v in plan_value.items() if k!='receipt_id'}, plan_hash=digest))
        db.add(Decision(plan_id=plan_id, approved_by=uuid4(), plan_hash=digest, decision='approved'))
        db.add(Execution(id=parent, plan_id=plan_id, state='executing'))
    ledger.intent = {'schema_version': 1, 'operation_id': str(parent), 'plan_id': str(plan_id),
        'plan_hash': digest, 'policy_hash': 'b' * 64, 'scope': scope}
    command = Command(parent, plan_id, identity, digest, 'b' * 64)
    return adapter, command, storage, factory, Plan, Decision, Execution, ledger


def test_exact_approved_scope_executes_and_reconciles_without_writes(bridge):
    adapter, command, storage, factory, *rest = bridge
    result = adapter.execute(command)
    assert result.verified_deleted and result.operation_id == command.operation_id
    before = list(storage.sdk.puts)
    statements = []
    def trace(conn, cursor, statement, *args): statements.append(statement)
    event.listen(factory.kw['bind'], 'before_cursor_execute', trace)
    try:
        assert adapter.reconcile(command).verified_deleted
    finally:
        event.remove(factory.kw['bind'], 'before_cursor_execute', trace)
    assert statements and all(statement.startswith('SELECT') for statement in statements)
    assert storage.sdk.puts == before


@pytest.mark.parametrize('field', ['policy_hash', 'plan_hash', 'asset_id', 'authority_id', 'operation_id'])
def test_wrong_policy_plan_asset_or_execution_has_no_effect(bridge, field):
    adapter, command, storage, *_ = bridge
    wrong = 'c' * 64 if field.endswith('hash') else uuid4()
    assert adapter.execute(replace(command, **{field: wrong})).state == 'blocked'
    assert storage.sdk.puts == []


def test_changed_asset_binding_after_approval_blocks_before_storage(bridge):
    from social.media.models import SocialMediaUpload
    adapter, command, storage, factory, *_ = bridge
    with factory() as db, db.begin():
        db.get(SocialMediaUpload, command.asset_id).grant_epoch += 1
    assert adapter.execute(command).state == 'blocked' and storage.sdk.puts == []


def test_missing_or_mismatched_external_intent_has_no_effect(bridge):
    adapter, command, storage, factory, Plan, Decision, Execution, ledger = bridge
    ledger.intent = {**ledger.intent, 'policy_hash': 'c' * 64}
    assert adapter.execute(command).state == 'blocked' and storage.sdk.puts == []


def test_lost_response_needs_explicit_media_retry_privacy_reconcile_reads_only(bridge):
    adapter, command, storage, factory, Plan, Decision, Execution, ledger = bridge
    storage.sdk.lose_response = True
    assert adapter.execute(command).state == 'outcome_unknown'
    with factory() as db, db.begin():
        db.get(Execution, command.operation_id).state = 'outcome_unknown'
    before = list(storage.sdk.puts)
    assert adapter.reconcile(command).state == 'outcome_unknown'
    assert storage.sdk.puts == before
    internal = adapter._command(command, read_only=True)
    assert MediaDeletionExecutor(factory, adapter.authorized_runtime()).execute_privacy_deletion(internal).verified_deleted
    assert adapter.reconcile(command).verified_deleted


def test_actual_http_dependency_borrows_app_owned_privacy_authority(bridge):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from social.http_boundary import AdminUser, get_db, require_admin
    from social.media.api import router
    from test_media_support import ACTOR
    adapter, command, storage, factory, *_ = bridge
    app = FastAPI()
    app.state.social_media_runtime = adapter.runtime
    app.state.social_privacy_media_port = adapter
    app.include_router(router)
    def database():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[require_admin] = lambda: AdminUser(id=str(ACTOR), email=None, roles=['admin'])
    internal = adapter._command(command)
    with TestClient(app) as client:
        response = client.post(f'/api/v1/admin/social/media/assets/{command.asset_id}/retire', json=internal.model_dump(mode='json'))
    assert response.status_code == 200 and response.json()['verified_deleted'] is True


@pytest.mark.parametrize('field', ['asset_id', 'authority_id', 'receipt_id', 'mode', 'result_hash', 'scope_hash', 'policy_hash'])
def test_readonly_reconcile_refuses_malformed_historical_identity_and_completion(bridge, field):
    from datetime import datetime, timezone
    from social.media.models import SocialMediaDeletion
    adapter, command, storage, factory, *_ = bridge
    internal = adapter._command(command)
    values = dict(operation_id=internal.operation_id, asset_id=internal.asset_id,
        authority_id=internal.authority_id, receipt_id=internal.receipt_id,
        command_hash=canonical_hash(internal.model_dump(mode='json')), scope_hash=canonical_hash({
            'binding': internal.expected_scope_hash, 'command': internal.model_dump(mode='json')}),
        policy_hash=internal.policy_hash, binding_hash='e' * 64, mode='all', state='complete',
        quarantine_fenced=1, original_fenced=1, result_hash='f' * 64, completed_at=datetime.now(timezone.utc))
    if field == 'asset_id':
        from social.media.service import MediaService
        with factory() as db:
            values[field] = granted(MediaService(db, adapter.runtime), storage)
    elif field in {'authority_id', 'receipt_id'}:
        values[field] = uuid4()
    elif field == 'mode':
        values[field] = 'quarantine'
    elif field == 'result_hash':
        values[field] = 'malformed'
    else:
        values[field] = 'a' * 64
    with factory() as db, db.begin():
        db.add(SocialMediaDeletion(**values))
    assert adapter.reconcile(command).state == 'outcome_unknown'
    assert storage.sdk.puts == []


def test_documented_exact_media_retry_works_after_parent_unknown(bridge):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from social.media.api import router
    from social.http_boundary import AdminUser,get_db,require_admin
    adapter,command,storage,factory,Plan,Decision,Execution,ledger=bridge
    storage.sdk.lose_response=True
    first=adapter.execute(command)
    assert first.state=='outcome_unknown'
    with factory() as session,session.begin(): session.get(Execution,command.operation_id).state='outcome_unknown'
    before=list(storage.sdk.puts)
    assert adapter.reconcile(command).state=='outcome_unknown' and storage.sdk.puts==before
    internal=adapter._command(command,read_only=True)
    assert internal is not None
    app=FastAPI();app.state.social_media_runtime=adapter.runtime;app.state.social_privacy_media_port=adapter;app.include_router(router)
    def database():
        with factory() as session: yield session
    app.dependency_overrides[get_db]=database
    app.dependency_overrides[require_admin]=lambda:AdminUser(id=str(UUID(int=1)),email=None,roles=['admin'])
    with TestClient(app) as client:
        response=client.post(f'/api/v1/admin/social/media/assets/{command.asset_id}/retire',json=internal.model_dump(mode='json'))
    reconciled=adapter.reconcile(command)
    assert response.status_code==200 and response.json()['verified_deleted'] is True and reconciled.verified_deleted

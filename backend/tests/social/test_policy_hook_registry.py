"""Actual post-commit caller uses shared native rules without creating clients."""
import asyncio
import builtins
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
from types import ModuleType, SimpleNamespace
import sys

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from social.models import SocialPublication, SocialPostTarget, SocialAuditEvent, SocialPost
from social.generation.integration import maybe_generate_committed
from social.automation.service import worker_gate
from test_domain_support import db, account
from test_automation import accepted_snapshot
from test_generation import observation


def validation_environment(monkeypatch):
    from cryptography.fernet import Fernet
    values = dict(SOCIAL_NATIVE_ENABLED='true', SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED='true',
        META_CONNECTIONS_ENABLED='true', META_APP_CONFIGURATION_VALIDATED='true', META_APP_ID='123',
        META_APP_SECRET='inert-fixture-secret', META_GRAPH_VERSION='v26.0', META_ACCESS_MODE='owned_standard',
        META_REDIRECT_URIS=json.dumps(['https://example.test/admin/social/accounts/callback']),
        SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION='v1', SOCIAL_CREDENTIAL_KEYS=json.dumps({'v1':Fernet.generate_key().decode()}),
        SOCIAL_MEDIA_ENABLED='false', SOCIAL_MEDIA_RETAINED_WRITES_ENABLED='false')
    for name, value in values.items(): monkeypatch.setenv(name, value)
    return values


def policy_source_fixture(db, monkeypatch):
    from social.adapters.validation_registry import load_native_validation_registry
    a = account(db)
    accepted_snapshot(db, a, monkeypatch)
    validation_environment(monkeypatch)
    registry = load_native_validation_registry()
    adapter = registry.adapters[('facebook', 'facebook_pages')]
    a.api_product, a.external_account_id = adapter.product, '123456'
    a.granted_scopes = list(adapter.scopes)
    # Synthetic fixture starts from the actual shared native rules, rather than
    # inventing a publishing capability. No live account verification is claimed.
    a.capability_snapshot = adapter.capabilities(dict(platform=a.platform, api_product=a.api_product,
        external_account_id=a.external_account_id, connection_state=a.connection_state,
        granted_scopes=a.granted_scopes, capability_snapshot=a.capability_snapshot)).model_dump(mode='json')
    a.capabilities_checked_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    db.commit()
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED','true')
    source = ModuleType('seeding.source_observations')
    source.SourceObservationUnavailable = type('Unavailable',(Exception,),{})
    from unit_source_authority_fixture import unit_observation_payload
    source.read_county_budget_observation = lambda factory, **kwargs: unit_observation_payload(db, observation(2,'250'))
    monkeypatch.setitem(sys.modules, source.__name__, source)
    db.rollback()
    return a, sessionmaker(bind=db.bind, expire_on_commit=False), registry


def deny_clients(monkeypatch):
    import social.adapters.meta_http as meta_http
    import social.media.runtime as media_runtime
    import social.worker.startup as startup
    def denied(*args, **kwargs): pytest.fail('Post-commit validation constructed delivery clients/material')
    monkeypatch.setattr(meta_http.MetaHTTP, '__init__', denied)
    monkeypatch.setattr(media_runtime, 'build_media_runtime', denied)
    monkeypatch.setattr(startup, 'native_runtime', denied)
    monkeypatch.setattr(httpx, 'AsyncClient', denied)
    monkeypatch.setattr(httpx, 'AsyncHTTPTransport', denied)


def policy_publication(factory):
    with factory() as check:
        return check.scalar(select(SocialPublication).where(SocialPublication.authorization_kind=='policy'))


def test_actual_hook_native_rules_reach_shared_queue_and_worker_gate_without_clients(db, monkeypatch):
    a, factory, _ = policy_source_fixture(db, monkeypatch)
    deny_clients(monkeypatch)
    async def existing_loop():
        return maybe_generate_committed(factory, record_ids=[1], ingestion_id=2)
    result = asyncio.run(existing_loop())
    with factory() as check:
        publication = check.scalar(select(SocialPublication).where(SocialPublication.authorization_kind=='policy'))
        refusals = [r.details for r in check.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action=='automation.human_review_required'))]
        assert publication is not None and publication.dispatch_requested_at is not None, (result, refusals)
        assert result['state']=='completed' and result['drafts_created']==1
        target = check.scalar(select(SocialPostTarget).where(SocialPostTarget.publication_id==publication.id))
        assert target.state=='queued' and target.next_action=='publish'
        from social.service import SocialService
        assert worker_gate(check.connection(), publication.id, a.id, 'facebook', SocialService(check).now(), public=True) is None


@pytest.mark.parametrize('control', ['ceiling', 'approval'])
def test_draft_only_never_imports_native_registry(db, monkeypatch, control):
    from social.models import SocialControls
    _, factory, _ = policy_source_fixture(db, monkeypatch)
    if control == 'ceiling': monkeypatch.setenv('SOCIAL_POLICY_AUTOMATION_ENABLED','false')
    else:
        cfg = db.get(SocialControls, 1)
        cfg.auto_approve_enabled = cfg.auto_schedule_enabled = cfg.auto_publish_enabled = False
        db.commit()
    original = builtins.__import__
    def denied(name, *args, **kwargs):
        if 'validation_registry' in name or 'native_runtime' in name or name.endswith('worker.startup'):
            pytest.fail('Draft-only path imported native composition/rules')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', denied)
    result = maybe_generate_committed(factory, record_ids=[1], ingestion_id=2)
    assert result['state']=='completed' and result['drafts_created']==1
    assert policy_publication(factory) is None


@pytest.mark.parametrize('bad', [object(), [], {}, True, 1, 'facebook'])
def test_invalid_borrowed_registry_preserves_human_draft(db, monkeypatch, bad):
    _, factory, _ = policy_source_fixture(db, monkeypatch)
    result = maybe_generate_committed(factory, record_ids=[1], ingestion_id=2, native_registration=bad)
    assert result['state']=='unavailable' and result['reason']=='NATIVE_REGISTRY_INVALID'
    assert result['drafts_created']==1 and result['processed']==1
    assert policy_publication(factory) is None
    with factory() as check:
        assert check.scalar(select(SocialPost).where(SocialPost.editorial_state=='pending_review')) is not None


@pytest.mark.parametrize('shape', [None, [], {}, 'facebook', True, 1, frozenset({'facebook'})])
def test_malformed_typed_registry_never_uses_platform_set_fallback(db, monkeypatch, shape):
    from social.worker.native_runtime import NativeRegistration
    _, factory, _ = policy_source_fixture(db, monkeypatch)
    result = maybe_generate_committed(factory, record_ids=[1], ingestion_id=2,
        native_registration=NativeRegistration(shape, None, None))
    assert result['state']=='unavailable' and result['reason']=='NATIVE_REGISTRY_INVALID'
    assert result['drafts_created']==1 and policy_publication(factory) is None


@pytest.mark.parametrize('mode', ['disabled', 'invalid', 'empty', 'wrong_key', 'untyped_value'])
def test_unavailable_validation_preserves_cursor_and_cancels_prior_policy(db, monkeypatch, mode):
    import social.adapters.validation_registry as module
    from social.generation.models import SourceCursor
    _, factory, registry = policy_source_fixture(db, monkeypatch)
    assert maybe_generate_committed(factory, record_ids=[1], ingestion_id=2)['state']=='completed'
    prior_id = policy_publication(factory).id
    from unit_source_authority_fixture import unit_observation_payload
    sys.modules['seeding.source_observations'].read_county_budget_observation = lambda factory, **kwargs: unit_observation_payload(db, observation(3,'350'))
    if mode=='disabled': monkeypatch.setenv('SOCIAL_NATIVE_ENABLED','false')
    elif mode=='invalid': monkeypatch.setenv('META_GRAPH_VERSION','v27.0')
    else:
        shapes = {'empty': {}, 'wrong_key': {('facebook','wrong'):next(iter(registry.adapters.values()))},
            'untyped_value': {('facebook','facebook_pages'):object()}}
        monkeypatch.setattr(module, 'load_native_validation_registry', lambda: module.NativeValidationRegistry(shapes[mode]))
    result = maybe_generate_committed(factory, record_ids=[1], ingestion_id=3)
    assert result['state']=='unavailable' and result['drafts_created']==1 and result['processed']==1
    with factory() as check:
        assert check.scalar(select(SourceCursor)).sequence==3
        prior = check.get(SocialPublication, prior_id)
        assert prior.revoked_at is not None or prior.cancel_requested_at is not None
        assert check.scalar(select(SocialPostTarget).where(SocialPostTarget.publication_id==prior_id)).state=='cancelled'
        assert len(list(check.scalars(select(SocialPublication).where(SocialPublication.authorization_kind=='policy'))))==1


def test_validation_loading_obeys_original_deadline(db, monkeypatch):
    import social.generation.integration as integration
    import social.adapters.validation_registry as module
    _, factory, _ = policy_source_fixture(db, monkeypatch)
    clock=[0.0]
    monkeypatch.setattr(integration.time,'monotonic',lambda:clock[0])
    actual = module.load_native_validation_registry
    def expired():
        registry = actual(); clock[0]=31.0; return registry
    monkeypatch.setattr(module,'load_native_validation_registry',expired)
    result = maybe_generate_committed(factory, record_ids=[1], ingestion_id=2)
    assert result['state']=='failed' and result['reason']=='GENERATION_DEADLINE_EXCEEDED'
    assert result['processed']==0 and policy_publication(factory) is None


def native_source_fixture(db, monkeypatch):
    """Actual owned registry fixture for the explicit borrowed port only."""
    import social.worker.startup as startup
    from test_native_startup import ready
    a, factory, _ = policy_source_fixture(db, monkeypatch)
    real_runtime = startup.native_runtime
    ready(monkeypatch)
    transports, entered = [], []
    class DeniedTransport(httpx.AsyncBaseTransport):
        def __init__(self): self.closes=0
        async def handle_async_request(self, request): pytest.fail('Unexpected HTTP')
        async def aclose(self): self.closes+=1
    def transport():
        value=DeniedTransport(); transports.append(value); return value
    @asynccontextmanager
    async def runtime(engine):
        async with real_runtime(engine, environ={'SOCIAL_NATIVE_ENABLED':'true','SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED':'true'}, transport_factory=transport) as registration:
            entered.append(registration); yield registration
    monkeypatch.setattr(startup,'native_runtime',runtime)
    return a, factory, entered, transports


def test_async_caller_borrows_installed_registry_without_closing_it(db, monkeypatch):
    import social.worker.startup as startup
    _, factory, entered, transports = native_source_fixture(db, monkeypatch)
    async def invoke():
        async with startup.native_runtime(db.bind) as registry:
            result = maybe_generate_committed(factory, record_ids=[1], ingestion_id=2, native_registration=registry)
            assert all(t.closes==0 for t in transports)
            return result
    result=asyncio.run(invoke())
    assert result['state']=='completed' and policy_publication(factory) is not None
    assert len(entered)==1 and all(t.closes==1 for t in transports)


def test_legacy_capabilities_cannot_be_upgraded_by_validation_registry(db, monkeypatch):
    a, factory, _ = policy_source_fixture(db, monkeypatch)
    a.capability_snapshot={**a.capability_snapshot, 'provider_api_version':'unverified'}
    db.commit()
    result=maybe_generate_committed(factory, record_ids=[1], ingestion_id=2)
    assert result['drafts_created']==1 and policy_publication(factory) is None
    with factory() as check:
        assert any(row.details.get('code')=='TARGET_VALIDATION_FAILED' for row in check.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action=='automation.human_review_required')))


def test_unattended_product_guard_uses_canonical_publication_feature():
    from social.automation.service import require_unattended_product
    from social.service import SocialError
    account = SimpleNamespace(api_product='tiktok_accounts_api')
    evidence = SimpleNamespace(evidence={'tiktok_unattended_product':'tiktok_accounts_api'})
    require_unattended_product(account, SimpleNamespace(feature_states={'unattended_publication':'supported'}), evidence)
    for features in ({}, {'unattended_publication':'requires_review'}, {'unattended_publishing':'supported'}):
        with pytest.raises(SocialError, match='TIKTOK_UNATTENDED_UNACCEPTED'):
            require_unattended_product(account, SimpleNamespace(feature_states=features), evidence)
    with pytest.raises(SocialError, match='TIKTOK_UNATTENDED_UNACCEPTED'):
        require_unattended_product(account, SimpleNamespace(feature_states={'unattended_publication':'supported'}), SimpleNamespace(evidence={'tiktok_unattended_product':'different-product'}))


@pytest.mark.parametrize('config', [None, SimpleNamespace(ready=True,graph_version='v26.0')])
def test_forged_pure_configuration_retains_human_draft(db, monkeypatch, config):
    import social.adapters.validation_registry as module
    from social.adapters.meta_validation import FacebookPageValidation
    _, factory, _ = policy_source_fixture(db, monkeypatch)
    registry = module.NativeValidationRegistry({('facebook','facebook_pages'):FacebookPageValidation(config)})
    monkeypatch.setattr(module,'load_native_validation_registry',lambda:registry)
    result = maybe_generate_committed(factory, record_ids=[1], ingestion_id=2)
    assert result['state']=='unavailable' and result['reason']=='NATIVE_REGISTRY_INVALID'
    assert result['processed']==1 and result['drafts_created']==1 and policy_publication(factory) is None


def test_pure_registry_cannot_impersonate_borrowed_installed_runtime(db, monkeypatch):
    _, factory, registry = policy_source_fixture(db, monkeypatch)
    result = maybe_generate_committed(factory, record_ids=[1], ingestion_id=2, native_registration=registry)
    assert result['state']=='unavailable' and result['reason']=='NATIVE_REGISTRY_INVALID'
    assert result['drafts_created']==1 and policy_publication(factory) is None

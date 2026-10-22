"""Inert callback admission tests; no real OAuth, provider transport or production DB."""
from dataclasses import replace
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from social.connections.config import MetaConfig
from social.connections.contracts import StartCommand, CompleteCommand
from social.connections.service import ConnectionService
from social.platform_connections.config import ConnectionConfig
from social.platform_connections.service import PlatformConnectionService
from social.service import SocialError

CALLBACK = 'https://admin.example.test/admin/social/accounts/callback'


def ready_config(provider):
    common = dict(redirect_uris=(CALLBACK,), active_key_version='v1',
                  encryption_keys={'v1': Fernet.generate_key().decode()})
    if provider == 'meta':
        return MetaConfig(enabled=True, app_configuration_validated=True, app_id='123',
                          app_secret='inert-secret', access_mode='owned_standard', **common)
    return ConnectionConfig(provider, enabled=True, access_verified=True, client_id='123',
                            client_secret='inert-secret', connection_budget_microusd=1000, **common)


class NoDatabase:
    def __getattr__(self, name):
        raise AssertionError('Unqualified callback reached database: ' + name)


@pytest.mark.parametrize('provider', ['meta', 'threads', 'x'])
def test_configured_callback_is_not_automatically_safe(provider):
    cfg = ready_config(provider)
    cfg.require_ready()  # Account maintenance still has its old readiness contract.
    with pytest.raises(SocialError) as failure:
        cfg.require_redirect(CALLBACK)
    assert failure.value.code == 'CALLBACK_INGRESS_UNVERIFIED'
    assert failure.value.status == 503


@pytest.mark.parametrize('provider', ['meta', 'threads', 'x'])
@pytest.mark.parametrize('command', ['start', 'complete'])
def test_hold_precedes_database_receipts_state_and_provider(provider, command):
    cfg = ready_config(provider)
    def no_provider(_):
        raise AssertionError('Unqualified callback constructed provider')
    cls = ConnectionService if provider == 'meta' else PlatformConnectionService
    service = cls(NoDatabase(), cfg, provider_factory=no_provider)
    body = StartCommand(redirect_uri=CALLBACK, reason='Inert test') if command == 'start' else CompleteCommand(
        redirect_uri=CALLBACK, code='inert-code', state='x' * 43)
    with pytest.raises(SocialError) as failure:
        getattr(service, command)(uuid4(), 'inert-binding', command, uuid4(), body, uuid4())
    assert failure.value.code == 'CALLBACK_INGRESS_UNVERIFIED'


@pytest.mark.parametrize('provider', ['meta', 'threads', 'x'])
@pytest.mark.parametrize('verified', [None, [], True, (True,), ({},), ('https://other.example.test/admin/social/accounts/callback',), (CALLBACK, CALLBACK), (CALLBACK, 'https://other.example.test/admin/social/accounts/callback')])
def test_invalid_or_stale_attestation_never_opens_ingress(provider, verified):
    cfg = replace(ready_config(provider), verified_callback_ingress_uris=verified)
    assert 'CALLBACK_INGRESS_UNVERIFIED' in cfg.oauth_blockers()
    with pytest.raises(SocialError, match='CALLBACK_INGRESS_UNVERIFIED'):
        cfg.require_redirect(CALLBACK)


@pytest.mark.parametrize('provider', ['meta', 'threads', 'x'])
def test_exact_synthetic_qualification_retains_redirect_validation(provider):
    cfg = replace(ready_config(provider), verified_callback_ingress_uris=(CALLBACK,))
    assert cfg.oauth_blockers() == []
    cfg.require_redirect(CALLBACK)
    for changed in (CALLBACK + '/', CALLBACK + '?code=inert', CALLBACK + '#inert', CALLBACK.replace('https:', 'http:'), CALLBACK.replace('admin.example.test', 'other.example.test')):
        with pytest.raises(SocialError, match='REDIRECT_MISMATCH'):
            cfg.require_redirect(changed)
    changed_cfg = replace(cfg, redirect_uris=(CALLBACK.replace('admin.example.test', 'other.example.test'),))
    with pytest.raises(SocialError, match='CALLBACK_INGRESS_UNVERIFIED'):
        changed_cfg.require_redirect(changed_cfg.redirect_uris[0])


@pytest.mark.parametrize('raw', ['', '{}', 'null', 'true', '[1]', '["duplicate", "duplicate"]', 'not json'])
def test_malformed_environment_attestation_fails_closed(raw):
    from social.connections.callback_ingress import verified_callbacks
    assert verified_callbacks(raw) == ()


def test_explicit_loaders_do_not_inherit_an_attestation(monkeypatch):
    import json
    from social.connections.config import load_config
    from social.platform_runtime import load_platform_settings
    from test_platform_runtime import environment
    monkeypatch.setenv('META_VERIFIED_CALLBACK_INGRESS_URIS', json.dumps([CALLBACK]))
    assert load_config({}).verified_callback_ingress_uris == ()
    assert load_config({'META_VERIFIED_CALLBACK_INGRESS_URIS': json.dumps([CALLBACK])}).verified_callback_ingress_uris == (CALLBACK,)
    for platform in ('threads', 'x', 'tiktok'):
        values = environment(platform)
        cfg = load_platform_settings(values).connections[platform]
        cfg.require_ready()  # Hold cannot prevent server startup or maintenance.
        assert 'CALLBACK_INGRESS_UNVERIFIED' in cfg.oauth_blockers()
        values[platform.upper() + '_VERIFIED_CALLBACK_INGRESS_URIS'] = json.dumps(cfg.redirect_uris)
        admitted = load_platform_settings(values).connections[platform]
        admitted.require_redirect(admitted.redirect_uris[0])


@pytest.mark.parametrize('provider', ['meta', 'threads', 'x'])
def test_direct_provider_entrypoints_hold_before_transport_and_budget(provider):
    import httpx
    from social.connections.provider import MetaProvider
    from social.platform_connections.provider import OAuthProvider
    calls, admission = [], []
    cfg = ready_config(provider)
    def budget(cost):
        admission.append(cost)
        return True
    transport = httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(200, json={}))
    client = MetaProvider(cfg, transport=transport) if provider == 'meta' else OAuthProvider(cfg, transport=transport, admission=budget)
    admission.clear()  # Constructor may perform the existing zero-cost readiness check.
    try:
        commands = (lambda: client.authorize_url('inert-state', CALLBACK), lambda: client.discover('inert-code', CALLBACK)) if provider == 'meta' else (lambda: client.authorize_url('inert-state', CALLBACK, 'v' * 64), lambda: client.exchange('inert-code', CALLBACK, 'v' * 64))
        for command in commands:
            with pytest.raises(SocialError, match='CALLBACK_INGRESS_UNVERIFIED'):
                command()
        assert calls == admission == []
    finally:
        client.close()


# Actual durable receipts and accounts are synthetic local SQLite fixtures.
from test_platform_connections import db, build, start as platform_start, complete as platform_complete, build_tiktok
from test_connections_support import graph, svc, start as meta_start, complete as meta_complete, select_asset
from social.connections.models import SocialOAuthFlow
from social.platform_connections.models import PlatformOAuthFlow
from sqlalchemy import select


@pytest.mark.parametrize('provider', ['meta', 'threads', 'x', 'tiktok'])
def test_hold_blocks_pending_and_replayed_flow_without_changing_accounts(db, graph, provider):
    if provider == 'meta':
        service = svc(db, replace(ready_config(provider), verified_callback_ingress_uris=(CALLBACK,)), graph)
        start, complete, model = meta_start, meta_complete, SocialOAuthFlow
    else:
        service, _ = build_tiktok(db) if provider == 'tiktok' else build(db, provider)
        start, model = platform_start, PlatformOAuthFlow
        complete = lambda service, state, **kwargs: platform_complete(service, state, redirect=service.config.redirect_uris[0], **kwargs)
    flow, state = start(service)
    # The flow was issued before the operator revoked its ingress attestation.
    service.config = replace(service.config, verified_callback_ingress_uris=())
    with pytest.raises(SocialError, match='CALLBACK_INGRESS_UNVERIFIED'):
        complete(service, state)
    assert db.scalar(select(model.status)) == 'initiated'
    db.rollback()
    service.config = replace(service.config, verified_callback_ingress_uris=service.config.redirect_uris)
    key = uuid4()
    completed = complete(service, state, key=key)
    service.config = replace(service.config, verified_callback_ingress_uris=())
    with pytest.raises(SocialError, match='CALLBACK_INGRESS_UNVERIFIED'):
        complete(service, state, key=key)  # Even a successful receipt cannot bypass the hold.
    assert db.scalar(select(model.status)) == ('awaiting_selection' if provider == 'meta' else 'awaiting_confirmation')
    db.rollback()
    service.config.require_ready()
    status = service.status()
    assert status['available'] is False and status['blockers'] == ['CALLBACK_INGRESS_UNVERIFIED']
    db.rollback()
    # No further provider exchange is needed to finish an already discovered identity.
    if provider == 'meta':
        from uuid import UUID
        accounts = select_asset(service, UUID(flow['flow_id']))['accounts']
        account_id = UUID(accounts[0]['id'])
        health = service.health(account_id)
        assert health['connection_state'] == 'connected'
    else:
        from test_platform_connections import ACTOR, BINDING
        from social.platform_connections.contracts import ConfirmCommand
        selected = service.confirm(__import__('uuid').UUID(completed['flow_id']), ACTOR, BINDING, 'POST confirm', uuid4(), ConfirmCommand(external_account_id=completed['external_account_id'], reason='Inert confirmation'), uuid4())
        assert selected['account']['publishing_enabled'] is False

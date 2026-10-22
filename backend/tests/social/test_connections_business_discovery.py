"""Business-owned Page discovery uses an explicit, separately approved scope."""
import json
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
import pytest

from social.connections.config import load_config
from social.service import SocialError
from test_connections_support import *


def configured(monkeypatch, config, flag='true'):
    values = {
        'META_CONNECTIONS_ENABLED': 'true',
        'META_APP_CONFIGURATION_VALIDATED': 'true',
        'META_APP_ID': config.app_id,
        'META_APP_SECRET': config.app_secret,
        'META_REDIRECT_URIS': json.dumps(config.redirect_uris),
        'META_VERIFIED_CALLBACK_INGRESS_URIS': json.dumps(config.verified_callback_ingress_uris),
        'META_ACCESS_MODE': config.access_mode,
        'SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION': config.active_key_version,
        'SOCIAL_CREDENTIAL_KEYS': json.dumps(config.encryption_keys),
        'META_BUSINESS_DISCOVERY_ENABLED': flag,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return load_config()


def test_business_owned_page_survives_normal_start_discover_and_selection(db, config, graph, monkeypatch):
    business_config = configured(monkeypatch, config)
    original = graph.__call__

    def business_owned(request):
        # Reproduces the live contrast: the same Page is absent without the
        # business grant and visible with it, including real content-task proof.
        if request.url.path == '/v26.0/me/accounts' and 'business_management' not in graph.scopes:
            return httpx.Response(200, json={'data': []})
        return original(request)

    service = svc(db, business_config, business_owned)
    started, state = start(service)
    requested = parse_qs(urlsplit(started['authorize_url']).query)['scope'][0].split(',')
    graph.scopes = requested  # Provider consent grants exactly what login asks.
    result = complete(service, state)
    assert len(result['choices']) == 1, 'Business-owned Page disappeared from normal OAuth discovery'
    assert result['choices'][0]['page_eligible'] is True
    assert result['choices'][0]['instagram_eligible'] is True
    assert 'business_management' in result['granted_scopes']
    selected = select_asset(service, UUID(started['flow_id']))
    assert len(selected['accounts']) == 2
    assert all(a['publishing_enabled'] is False for a in selected['accounts'])


def test_business_scope_matches_both_authorization_builders_and_status(db, config, graph, monkeypatch):
    business_config = configured(monkeypatch, config)
    service = svc(db, business_config, graph)
    status = service.status()
    db.rollback()
    started, _ = start(service)
    provider = MetaProvider(business_config, transport=httpx.MockTransport(graph))
    try:
        provider_url = provider.authorize_url('fake-state', REDIRECT)
    finally:
        provider.close()
    expected = list(SCOPES) + ['business_management']
    for url in (started['authorize_url'], provider_url):
        assert parse_qs(urlsplit(url).query)['scope'][0].split(',') == expected
    assert status['scopes'] == expected


def test_denied_business_permission_fails_before_page_discovery(config, graph, monkeypatch):
    business_config = configured(monkeypatch, config)
    provider = MetaProvider(business_config, transport=httpx.MockTransport(graph))
    try:
        with pytest.raises(SocialError, match='PERMISSIONS_REQUIRED'):
            provider.discover('fake-code', REDIRECT)
    finally:
        provider.close()
    assert not any(r.url.path == '/v26.0/me/accounts' for r in graph.calls)


@pytest.mark.parametrize('flag', ['', 'false', 'TRUE', '1'])
def test_business_access_is_never_requested_without_exact_opt_in(db, config, graph, monkeypatch, flag):
    regular = configured(monkeypatch, config, flag)
    started, state = start(svc(db, regular, graph))
    assert parse_qs(urlsplit(started['authorize_url']).query)['scope'][0].split(',') == list(SCOPES)
    assert complete(svc(db, regular, graph), state)['choices'][0]['page_eligible'] is True


def test_business_access_defaults_off_when_setting_absent(config, monkeypatch):
    configured(monkeypatch, config)
    monkeypatch.delenv('META_BUSINESS_DISCOVERY_ENABLED')
    assert load_config().requested_scopes == SCOPES


@pytest.mark.parametrize('flag', [None, '', 'true', 1, [], {}])
def test_programmatic_business_setting_rejects_non_boolean(config, flag):
    invalid = replace(config, business_discovery_enabled=flag)
    assert 'BUSINESS_DISCOVERY_CONFIGURATION_INVALID' in invalid.blockers()
    with pytest.raises(SocialError, match='CONNECTIONS_UNAVAILABLE'):
        MetaProvider(invalid)


def test_debug_scope_cannot_substitute_for_actual_business_permission(config, graph, monkeypatch):
    business_config = configured(monkeypatch, config)
    graph.scopes.append('business_management')
    original = graph.__call__

    def denied(request):
        if request.url.path == '/v26.0/me/permissions':
            return httpx.Response(200, json={'data': [
                {'permission': scope, 'status': 'declined' if scope == 'business_management' else 'granted'}
                for scope in graph.scopes
            ]})
        return original(request)

    provider = MetaProvider(business_config, transport=httpx.MockTransport(denied))
    try:
        with pytest.raises(SocialError, match='PERMISSIONS_REQUIRED'):
            provider.discover('fake-code', REDIRECT)
    finally:
        provider.close()
    assert not any(r.url.path == '/v26.0/me/accounts' for r in graph.calls)


def test_business_grant_does_not_replace_provider_content_tasks(config, graph, monkeypatch):
    business_config = configured(monkeypatch, config)
    graph.scopes.append('business_management')
    graph.tasks[:] = ['ANALYZE']
    provider = MetaProvider(business_config, transport=httpx.MockTransport(graph))
    try:
        result = provider.discover('fake-code', REDIRECT)
    finally:
        provider.close()
    assert not result['choices'][0]['page_eligible']
    assert not result['choices'][0]['instagram_eligible']

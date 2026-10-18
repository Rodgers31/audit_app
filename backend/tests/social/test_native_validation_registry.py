"""Native delivery and client-free validation share exact rules and config gates."""
import asyncio

import httpx
import pytest

from social.adapters import FacebookPageAdapter, InstagramFacebookLoginAdapter
from social.adapters.meta_validation import FacebookPageValidation, InstagramFacebookLoginValidation
from social.adapters.validation_registry import load_native_validation_registry
from social.service import SocialError
from test_policy_hook_registry import validation_environment, deny_clients


@pytest.mark.parametrize('kind,pure,platform,format', [
    (FacebookPageAdapter, FacebookPageValidation, 'facebook', 'text'),
    (FacebookPageAdapter, FacebookPageValidation, 'facebook', 'image'),
    (InstagramFacebookLoginAdapter, InstagramFacebookLoginValidation, 'instagram', 'image'),
])
def test_local_and_delivery_rules_have_identical_validation(kind, pure, platform, format, monkeypatch):
    from test_native_meta_adapters import payload, rehash
    validation_environment(monkeypatch)
    local = load_native_validation_registry().adapters[(kind.platform,kind.product)]
    assert isinstance(local, pure)
    assert not any(hasattr(local,name) for name in ('http','execute','close','credential_loader','media_access'))
    assert kind.capabilities is pure.capabilities and kind.validate is pure.validate
    assert kind._content_errors is pure._content_errors
    account = dict(platform=kind.platform, api_product=kind.product, connection_state='connected',
        external_account_id='123', granted_scopes=kind.scopes, capability_snapshot={'eligible':True})
    async def compare():
        adapter = kind(local.config, transport=httpx.MockTransport(lambda request: pytest.fail('Unexpected HTTP')))
        try:
            for change in ({}, {'granted_scopes':[]}, {'connection_state':'revoked'}, {'capability_snapshot':{}}, {'api_product':'wrong'}):
                assert local.capabilities({**account,**change}) == adapter.capabilities({**account,**change})
            cap = local.capabilities(account)
            value = payload(platform,format)
            variants = [value, value.model_copy(update={'content_hash':'f'*64}),
                rehash(value.model_copy(update={'api_product':'wrong'})),
                rehash(value.model_copy(update={'text':'x'*20001})),
                rehash(value.model_copy(update={'format':'reel'}))]
            for item in variants:
                assert local.validate(item, cap) == adapter.validate(item, cap)
        finally:
            await adapter.close()
    asyncio.run(compare())


@pytest.mark.parametrize('changes', [
    {'SOCIAL_NATIVE_ENABLED':'yes'}, {'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED':'yes'},
    {'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED':'false'}, {'META_CONNECTIONS_ENABLED':'false'},
    {'META_APP_CONFIGURATION_VALIDATED':'false'}, {'META_APP_ID':''}, {'META_APP_SECRET':''},
    {'META_APP_SECRET':'inert fixture'}, {'META_APP_SECRET':'inerté'}, {'META_ACCESS_MODE':'unverified'},
    {'META_GRAPH_VERSION':'v27.0'}, {'META_REDIRECT_URIS':'[]'},
    {'SOCIAL_CREDENTIAL_KEYS':'{}'}, {'SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION':'missing'},
])
def test_local_registry_refuses_incomplete_or_malformed_native_configuration(monkeypatch, changes):
    values = validation_environment(monkeypatch)
    deny_clients(monkeypatch)
    with pytest.raises(SocialError, match='NATIVE_CONFIGURATION_INVALID') as raised:
        load_native_validation_registry({**values,**changes})
    assert raised.value.__context__ is None


def test_disabled_registry_reads_no_meta_or_media_configuration(monkeypatch):
    import social.connections.config as config
    def forbidden(*args): pytest.fail('Disabled native registry read connection material')
    monkeypatch.setattr(config,'load_config',forbidden)
    assert load_native_validation_registry({}) is None


@pytest.mark.parametrize('platform,format,operations', [
    ('facebook','text',['publish','poll']),
    ('facebook','image',['upload','publish','poll']),
    ('instagram','image',['poll','create_container','poll','poll','publish','poll']),
])
def test_existing_native_delivery_baseline_after_pure_rule_extraction(platform, format, operations):
    # Execute the existing async baseline through asyncio.run in this sync test;
    # no optional pytest-asyncio plugin or live provider is required.
    from test_native_meta_adapters import test_positive_baseline_survives_restart_after_every_durable_step
    asyncio.run(test_positive_baseline_survives_restart_after_every_durable_step(platform,format,operations))

"""Actual composed provider registration remains borrowable by the ETL hook."""
import asyncio
import os

import httpx
import pytest
from sqlalchemy import select
from test_domain_support import db
from test_policy_hook_registry import policy_source_fixture, deny_clients
from social.models import SocialPublication, SocialPostTarget
from social.generation.integration import maybe_generate_committed


def queued(factory):
    with factory() as session:
        publication = session.scalar(select(SocialPublication).where(SocialPublication.authorization_kind == 'policy'))
        assert publication is not None and publication.dispatch_requested_at is not None
        target = session.scalar(select(SocialPostTarget).where(SocialPostTarget.publication_id == publication.id))
        assert target.state == 'queued' and target.next_action == 'publish'


@pytest.mark.parametrize('combined',[False,True])
def test_caller_owned_actual_registration_borrowed_without_startup(db,monkeypatch,combined):
    from social.worker.native_runtime import create_native_registration,create_platform_registration,combine_native_registrations
    from social.adapters.config import MetaAdapterConfig
    from social.adapters.threads import ThreadsAdapterConfig
    from social.connections.crypto import CredentialCipher
    from social.media.storage import R2Storage
    import json
    _,factory,_=policy_source_fixture(db,monkeypatch)
    cipher=CredentialCipher('v1',json.loads(os.environ['SOCIAL_CREDENTIAL_KEYS']))
    origin='a'*32+'.r2.cloudflarestorage.com'
    storage=R2Storage(object(),'independent-test','https://'+origin)
    transports=[]
    class DeniedHTTP(httpx.AsyncBaseTransport):
        def __init__(self): self.closes=0;transports.append(self)
        async def handle_async_request(self,request): raise AssertionError('Unexpected HTTP')
        async def aclose(self): self.closes+=1
    registration=create_native_registration(db.bind,MetaAdapterConfig('v26.0',True,True,'inert-fixture-secret'),cipher=cipher,storage=storage,storage_origin=origin,transport_factory=DeniedHTTP)
    if combined:
        platform=create_platform_registration(db.bind,{'threads':ThreadsAdapterConfig(enabled=True,operational_gates_verified=True)},cipher=cipher,storage=storage,storage_origin=origin,transport_factory=DeniedHTTP)
        registration=combine_native_registrations(registration,platform)
    deny_clients(monkeypatch)
    async def invoke():
        try:
            result=maybe_generate_committed(factory,record_ids=[1],ingestion_id=2,native_registration=registration)
            assert all(t.closes==0 for t in transports)
            assert result['state']=='completed', result
            queued(factory)
        finally:
            await registration.close()
    asyncio.run(invoke())
    assert all(t.closes==1 for t in transports)



@pytest.mark.parametrize('case', ['platform', 'combined', 'foreign_meta', 'foreign_platform', 'callable', 'nested', 'cycle', 'empty', 'swapped'])
def test_borrowed_material_binding_uses_known_same_database_leaves(db, case):
    from types import SimpleNamespace
    from social.adapters.validation_registry import _loader_bound_to_engine
    from social.worker.materials import CredentialMaterialLoader
    from social.platform_materials import PlatformCredentialMaterialLoader, CombinedCredentialLoader
    engine = db.bind
    meta = CredentialMaterialLoader(engine, None)
    platforms = PlatformCredentialMaterialLoader(engine, None, {})
    combined = CombinedCredentialLoader(meta, platforms)
    choices = {'platform': platforms, 'combined': combined,
        'foreign_meta': CombinedCredentialLoader(CredentialMaterialLoader(object(), None), platforms),
        'foreign_platform': CombinedCredentialLoader(meta, PlatformCredentialMaterialLoader(object(), None, {})),
        'callable': SimpleNamespace(engine=engine), 'nested': CombinedCredentialLoader(combined, platforms),
        'cycle': CombinedCredentialLoader(meta, platforms), 'empty': CombinedCredentialLoader(None, None),
        'swapped': CombinedCredentialLoader(platforms, meta)}
    choices['cycle'].meta = choices['cycle']
    assert _loader_bound_to_engine(choices[case], engine) is (case in {'platform', 'combined'})

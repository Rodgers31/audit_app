"""Native HTTP, real encrypted material and durable PostgreSQL restart boundaries."""
import asyncio
from datetime import datetime, timezone
from io import BytesIO
import json
from uuid import UUID, uuid4

import httpx
from PIL import Image
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from social.adapters import MetaAdapterConfig
from social.connections.crypto import CredentialCipher
from social.connections.provider import MetaProvider
from social.connections.service import ConnectionService
from social.contracts import ApproveCommand, PublishCommand
from social.media.config import MediaConfig
from social.media.inspection import LocalInspector
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.models import SocialAccount, SocialControls, SocialMediaAsset, SocialPostTarget, SocialPublishAttempt
from social.worker.native_runtime import create_native_registration
from social.worker.runner import SocialWorker
from test_connections_support import config, FakeGraph, start, complete, select_asset, PAGE
from test_domain_support import ACTOR, call, draft_body
from test_media_support import FakeStorage, ENDPOINT
from test_queue_postgres import engine, repository
import test_native_meta_adapters as native_fixture


def registration(engine, config, storage, graph):
    return create_native_registration(engine, MetaAdapterConfig('v26.0',True,True,'fake-native-app-secret'),
        cipher=CredentialCipher(config.active_key_version,config.encryption_keys),storage=storage,
        storage_origin='a'*32+'.r2.cloudflarestorage.com',transport_factory=lambda:httpx.MockTransport(graph))


def prepare(engine, config, graph, monkeypatch, *, platform='facebook', image=False):
    storage=FakeStorage(); reg=registration(engine,config,storage,graph)
    monkeypatch.setattr(native_fixture,'TOKEN',PAGE)
    with Session(engine,expire_on_commit=False) as db:
        connection=ConnectionService(db,config,provider_factory=lambda settings:MetaProvider(settings,transport=httpx.MockTransport(FakeGraph())),available_adapters=reg.adapters)
        _,state=start(connection); discovered=complete(connection,state)
        select_asset(connection,UUID(discovered['flow_id']))
        account=db.scalar(select(SocialAccount).where(SocialAccount.platform==platform))
        db.get(SocialControls,1).publishing_enabled=True; account.publishing_enabled=True; db.commit()
        asset=None
        if image:
            buffer=BytesIO(); Image.new('RGB',(320,320),'green').save(buffer,format='JPEG'); content=buffer.getvalue()
            runtime=MediaRuntime(MediaConfig(enabled=True,endpoint=ENDPOINT,bucket='media-test',access_key='fake',secret_key='fake'),storage,LocalInspector(MediaConfig()))
            media=MediaService(db,runtime)
            grant=media.initiate(ACTOR,uuid4(),{'filename':'fixture.jpg','declared_mime_type':'image/jpeg','declared_size':len(content)},uuid4())
            storage.objects[storage.last_key]=(content,'image/jpeg',None)
            ready=media.complete(ACTOR,grant.asset.id,uuid4(),grant.asset.version,uuid4())
            asset=db.get(SocialMediaAsset,ready.id)
            monkeypatch.setattr(native_fixture,'IMAGE',content)
            monkeypatch.setattr(native_fixture,'FETCH_URL',ENDPOINT+'/media-test/'+asset.storage_key+'?fixture=preview-secret')
        body=draft_body((account,))
        if asset:
            body=draft_body(document={'master':{'text':'Verified announcement','media':[{'asset_id':str(asset.id),'alt_text':'A green inspection fixture'}]},
                'targets':[{'account_id':str(account.id),'format':'image','overrides':{}}]})
        _,created=call(db,body,lambda service:service.create(body),adapters=reg.adapters,route='native-create')
        approve=ApproveCommand(expected_version=created['version'],revision_id=created['revision_id'])
        _,approved=call(db,approve,lambda service:service.approve(UUID(created['id']),approve),adapters=reg.adapters,route='native-approve')
        publish=PublishCommand(expected_version=approved['version'],revision_id=approved['revision_id'])
        _,accepted=call(db,publish,lambda service:service.publish(UUID(created['id']),publish),adapters=reg.adapters,route='native-publish')
        target=UUID(accepted['targets'][0]['id'])
    asyncio.run(reg.close())
    return storage,target


def step(engine, config, storage, graph, *, drop_receipt=False):
    repo=repository(engine); reg=registration(engine,config,storage,graph)
    if drop_receipt:
        def lost(*args,**kwargs): raise RuntimeError('Simulated process lost its receipt persistence')
        repo.finish=lost
    async def run():
        worker=SocialWorker(repo,adapters=reg.adapters,credential_loader=reg.credential_loader,media_access=reg.media_access)
        try:
            claims=await worker.db(repo.claim_due,1)
            if claims: await worker.process(claims[0])
        finally:
            await worker.close(); await reg.close()
    asyncio.run(run())


def due(engine,target):
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_post_targets SET next_action_at=clock_timestamp()-interval '1 second' WHERE id=:id"),{'id':target})


@pytest.mark.parametrize('platform,image,expected_posts',[('facebook',False,1),('facebook',True,2),('instagram',True,2)])
def test_native_pipeline_survives_restart_at_every_checkpoint(engine,config,monkeypatch,platform,image,expected_posts):
    graph=native_fixture.Graph(); storage,target_id=prepare(engine,config,graph,monkeypatch,platform=platform,image=image)
    with Session(engine) as db: frozen=db.get(SocialPostTarget,target_id).resolved_payload
    for _ in range(8):
        due(engine,target_id); step(engine,config,storage,graph)
        with Session(engine) as db:
            target=db.get(SocialPostTarget,target_id)
            assert target.resolved_payload==frozen
            if target.state=='published': break
    assert target.state=='published' and target.visibility_state=='public' and target.remote_url
    assert sum(method=='POST' for method,_,_ in graph.calls)==expected_posts
    with Session(engine) as db:
        receipts=json.dumps([row.receipt for row in db.scalars(select(SocialPublishAttempt))])
        assert PAGE not in receipts and 'preview-secret' not in receipts
    assert sum(path.endswith('/content_publishing_limit') for _,path,_ in graph.calls)==(2 if platform=='instagram' else 0)


@pytest.mark.parametrize('failure',['timeout_after_acceptance','receipt_persistence_loss'])
def test_native_accepted_send_without_saved_id_is_never_resent(engine,config,monkeypatch,caplog,failure):
    graph=native_fixture.Graph(); storage,target_id=prepare(engine,config,graph,monkeypatch)
    if failure=='timeout_after_acceptance': graph.timeout_path='/v26.0/901/feed'
    step(engine,config,storage,graph,drop_receipt=failure=='receipt_persistence_loss')
    if failure=='receipt_persistence_loss':
        with engine.begin() as conn:
            conn.execute(text("UPDATE social_post_targets SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"),{'id':target_id})
            conn.execute(text("UPDATE social_accounts SET publish_lease_expires_at=clock_timestamp()-interval '1 second' WHERE publish_lease_target_id=:id"),{'id':target_id})
        repository(engine).recover_expired()
    due(engine,target_id); step(engine,config,storage,graph)
    due(engine,target_id); step(engine,config,storage,graph)
    with Session(engine) as db:
        target=db.get(SocialPostTarget,target_id)
        assert target.state=='outcome_unknown' and target.primary_remote_id is None and target.submit_count==1
    assert sum(method=='POST' for method,_,_ in graph.calls)==1
    assert PAGE not in caplog.text and 'preview-secret' not in caplog.text

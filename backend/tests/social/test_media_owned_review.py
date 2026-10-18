"""Recommended regression file; imports the original owned SQLite fixtures."""
from dataclasses import replace
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select
from social.media import owned_writes
from social.media.models import SocialMediaWriteAttempt,SocialMediaWriteOwner,SocialMediaUpload
from social.service import SocialError
from test_media_support import media_db,media,ACTOR,intent,png
from test_media_owned_writes import owned,concrete_runtime,failed_intent,scope,totals

def disable(svc):
    svc.config=replace(svc.config,owned_quiescence_enabled=False)
    svc.runtime=replace(svc.runtime,config=svc.config)

def admitted(svc,io,monkeypatch,kind='grant'):
    # A lost local acknowledgement leaves a real durable admitted grant.
    def lost(*args,**kw):raise KeyboardInterrupt('owned regression interrupts before acknowledgement')
    monkeypatch.setattr(io.sdk,'generate_presigned_url',lost)
    with pytest.raises(KeyboardInterrupt):svc.initiate(ACTOR,uuid4(),intent(),uuid4())
    with svc.db.begin():
        identity=svc.db.scalar(select(SocialMediaUpload.asset_id))
        asset,upload=svc._rows(identity)
        grant=svc.db.scalar(select(SocialMediaWriteAttempt))
        if kind=='finalize':
            operation=owned_writes.admit(svc,asset,upload,'finalize',1)
        else:operation=grant.operation_id
    return identity,operation

@pytest.mark.parametrize('kind,state',[('grant','not_issued'),('grant','issued'),('finalize','completed')])
@pytest.mark.parametrize('closed',[False,True])
def test_exact_admitted_attempt_can_acknowledge_after_disable(owned,monkeypatch,kind,state,closed):
    svc,io=owned
    identity,operation=admitted(svc,io,monkeypatch,kind)
    before=totals(svc,identity)
    if closed:
        with svc.db.begin():svc.db.get(SocialMediaWriteOwner,identity).state='closed'
    disable(svc)
    with svc.db.begin():
        asset,upload=svc._rows(identity)
        owned_writes.finish(svc,asset,upload,kind,1,operation,state)
    with svc.db.begin():
        assert svc.db.get(SocialMediaWriteAttempt,(identity,kind,1)).state==state
        assert svc.db.get(SocialMediaWriteOwner,identity).state==('closed' if closed else 'open')
    assert totals(svc,identity)==before
    assert io.calls==[]
    with svc.db.begin():
        asset,upload=svc._rows(identity)
        with pytest.raises(SocialError):owned_writes.admit(svc,asset,upload,'grant',2)
    with pytest.raises(SocialError):
        owned_writes.reconcile_owned(svc,ACTOR,identity,uuid4(),scope(svc,identity),uuid4())
    assert totals(svc,identity)==before

@pytest.mark.parametrize('damage',['operation','none','zero_uuid','epoch_bool','epoch_zero','epoch_wrong','kind','state','credential','already_terminal'])
def test_disable_does_not_weaken_exact_acknowledgement_binding(owned,monkeypatch,damage):
    svc,io=owned
    identity,operation=admitted(svc,io,monkeypatch)
    before=totals(svc,identity)
    kind,epoch,state='grant',1,'not_issued'
    if damage=='operation':operation=uuid4()
    if damage=='none':operation=None
    if damage=='zero_uuid':operation=UUID(int=0)
    if damage=='epoch_bool':epoch=True
    if damage=='epoch_zero':epoch=0
    if damage=='epoch_wrong':epoch=2
    if damage=='kind':kind='unknown'
    if damage=='state':state='completed'
    if damage=='already_terminal':
        with svc.db.begin():
            asset,upload=svc._rows(identity)
            owned_writes.finish(svc,asset,upload,'grant',1,operation,'not_issued')
    disable(svc)
    if damage=='credential':
        svc.config=replace(svc.config,secret_key='rotated-inert-fixture')
        svc.runtime=replace(svc.runtime,config=svc.config)
    with svc.db.begin():
        asset,upload=svc._rows(identity)
        with pytest.raises(SocialError):owned_writes.finish(svc,asset,upload,kind,epoch,operation,state)
    with svc.db.begin():
        assert svc.db.get(SocialMediaWriteAttempt,(identity,'grant',1)).state==('not_issued' if damage=='already_terminal' else 'admitted')
    assert totals(svc,identity)==before
    assert io.calls==[]

def test_real_finalizer_acknowledges_after_disable_without_releasing_capacity(owned,monkeypatch):
    svc,io=owned
    grant=svc.initiate(ACTOR,uuid4(),intent(),uuid4())
    with svc.db.begin():
        upload=svc.db.get(SocialMediaUpload,grant.asset.id)
        io.objects[upload.quarantine_key]=(png(),'image/png',{})
    original=io.sdk.put_object
    def finish(**kw):
        disable(svc)
        return original(**kw)
    monkeypatch.setattr(io.sdk,'put_object',finish)
    assert svc.complete(ACTOR,grant.asset.id,uuid4(),1,uuid4()).state=='ready'
    with svc.db.begin():
        row=svc.db.get(SocialMediaWriteAttempt,(grant.asset.id,'finalize',1))
        assert row.state=='completed'
        upload=svc.db.get(SocialMediaUpload,grant.asset.id)
        assert upload.finalization_settled==1 and upload.reservation_released==0
    assert len([c for c in io.calls if c[0]=='put'])==1

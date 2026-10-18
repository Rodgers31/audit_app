"""Real service/API with the concrete R2 port and inert local SDK I/O."""
from dataclasses import replace
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
import hashlib

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import pytest
from sqlalchemy import event, select

from social.media.models import SocialMediaUpload, SocialMediaBudget, SocialMediaWriteOwner, SocialMediaWriteAttempt
from social.media.reconciliation import ReconcileOwnedUpload
from social.media.owned_writes import reconcile_owned
from social.media.service import MediaService
from social.media.storage import R2Storage, StorageFailure
from social.models import SocialAuditEvent
from social.service import SocialError
from test_media_api import client, header, BASE
from test_media_support import ACTOR, ENDPOINT, media, media_db, intent, png


def concrete_runtime(svc, monkeypatch):
    # Match the controlled database clock; these cases exercise writer
    # acknowledgements, while dedicated signing tests exercise clock skew.
    with svc.db.begin():
        signing_time = svc.now().replace(microsecond=0, tzinfo=None)
    monkeypatch.setattr('botocore.auth.get_current_datetime', lambda: signing_time)
    sdk = boto3.client('s3', endpoint_url=ENDPOINT, region_name='auto',
        aws_access_key_id='fixture', aws_secret_access_key='fixture',
        config=Config(signature_version='s3v4', s3={'addressing_style': 'path'},
            retries={'total_max_attempts': 1}, connect_timeout=1, read_timeout=1))
    objects, calls = {}, []
    def head(**kw):
        calls.append(('head', kw['Key']))
        if kw['Key'] not in objects:
            raise ClientError({'ResponseMetadata': {'HTTPStatusCode': 404, 'RetryAttempts': 0}, 'Error': {'Code': 'NoSuchKey'}}, 'HeadObject')
        data, mime, metadata = objects[kw['Key']]
        return {'ContentLength': len(data), 'ContentType': mime, 'Metadata': metadata,
            'ETag': '"'+hashlib.md5(data).hexdigest()+'"', 'ResponseMetadata': {'HTTPStatusCode': 200, 'RetryAttempts': 0}}
    def get(**kw):
        value = head(**kw)
        value['Body'] = BytesIO(objects[kw['Key']][0])
        return value
    def put(**kw):
        calls.append(('put', kw['Key']))
        body = kw['Body'].read() if hasattr(kw['Body'], 'read') else kw['Body']
        objects[kw['Key']] = body, kw['ContentType'], kw.get('Metadata', {})
        return {'ResponseMetadata': {'HTTPStatusCode': 200, 'RetryAttempts': 0}}
    def delete(**kw):
        calls.append(('delete', kw['Key']))
        objects.pop(kw['Key'], None)
        return {'ResponseMetadata': {'HTTPStatusCode': 204, 'RetryAttempts': 0}}
    for name, method in [('head_object', head), ('get_object', get), ('put_object', put), ('delete_object', delete)]:
        monkeypatch.setattr(sdk, name, method)
    cfg = replace(svc.config, owned_quiescence_enabled=True, access_key='fixture', secret_key='fixture')
    svc.config = cfg
    svc.runtime = replace(svc.runtime, config=cfg, storage=R2Storage(sdk, cfg.bucket, cfg.endpoint))
    return SimpleNamespace(sdk=sdk, objects=objects, calls=calls, runtime=svc.runtime)


@pytest.fixture
def owned(media, monkeypatch):
    svc, _ = media
    io = concrete_runtime(svc, monkeypatch)
    yield svc, io
    io.sdk.close()


def fail_signer(io, monkeypatch):
    def fail(*args, **kw):
        raise RuntimeError('inert local signer failure')
    monkeypatch.setattr(io.sdk, 'generate_presigned_url', fail)


def failed_intent(svc, io, monkeypatch, key=None):
    fail_signer(io, monkeypatch)
    with pytest.raises(SocialError, match='MEDIA_STORAGE_UNAVAILABLE'):
        svc.initiate(ACTOR, key or uuid4(), intent(), uuid4())
    with svc.db.begin():
        return svc.db.scalar(select(SocialMediaUpload.asset_id))


def scope(svc, identity):
    with svc.db.begin():
        u = svc.db.get(SocialMediaUpload, identity)
        return ReconcileOwnedUpload(expected_version=u.version,
            expected_grant_epoch=u.grant_epoch, expected_finalization_epoch=u.finalization_epoch)


def totals(svc, identity):
    with svc.db.begin():
        u = svc.db.get(SocialMediaUpload, identity, populate_existing=True)
        b = svc.db.get(SocialMediaBudget, 'global', populate_existing=True)
        return u.grant_settled_epoch, u.reservation_released, b.bytes_used, b.pending_count


def test_unissued_bearer_recovery_api_replay_and_explicit_cleanup(owned, monkeypatch):
    svc, io = owned
    fail_signer(io, monkeypatch)
    api = client((svc, io))
    assert api.post(BASE+'/uploads', json=intent(), headers=header()).status_code == 503
    with svc.db.begin():
        identity = svc.db.scalar(select(SocialMediaUpload.asset_id))
    body = scope(svc, identity).model_dump(mode='json')
    key = header()
    response = api.post(BASE+f'/uploads/{identity}/reconcile-owned', json=body, headers=key)
    assert response.status_code == 200, response.text
    assert response.json()['state'] == 'archived'
    assert api.post(BASE+f'/uploads/{identity}/reconcile-owned', json=body, headers=key).json() == response.json()
    assert totals(svc, identity) == (1, 0, 2*len(png()), 1)
    assert io.calls == []
    with svc.db.begin():
        audit = svc.db.scalar(select(SocialAuditEvent).where(SocialAuditEvent.action=='media.writes_reconciled'))
        assert audit.details['receipt_id'] == key['Idempotency-Key']
        assert len(audit.details['evidence_hash']) == 64
        svc.db.get(SocialMediaUpload, identity).expires_at = svc.now()-timedelta(seconds=1)
    assert svc.cleanup() == 1
    assert totals(svc, identity) == (1, 1, 0, 0)
    assert all(c[0]=='delete' for c in io.calls)


def test_issued_bearer_head_and_age_never_quiescent(owned):
    svc, io = owned
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    with svc.db.begin():
        u=svc.db.get(SocialMediaUpload, grant.asset.id)
        io.objects[u.quarantine_key]=(png(), 'image/png', {})
        u.expires_at=svc.now()-timedelta(days=365)
        u.grant_expires_at=svc.now()-timedelta(days=365)
    with pytest.raises(SocialError, match='MEDIA_WRITE_QUIESCENCE_UNCONFIRMED'):
        reconcile_owned(svc, ACTOR, grant.asset.id, uuid4(), scope(svc, grant.asset.id), uuid4())
    assert totals(svc, grant.asset.id) == (0, 0, 2*len(png()), 1)
    assert svc.cleanup() == 0
    assert io.calls == []


@pytest.mark.parametrize('damage', ['missing_attempt', 'admitted', 'wrong_credential', 'flag_off', 'missing_owner', 'wrong_generation'])
def test_incomplete_or_rebound_history_stays_held(owned, monkeypatch, damage):
    svc, io=owned
    identity=failed_intent(svc, io, monkeypatch)
    with svc.db.begin():
        owner=svc.db.get(SocialMediaWriteOwner, identity)
        attempt=svc.db.scalar(select(SocialMediaWriteAttempt))
        if damage=='missing_attempt': svc.db.delete(attempt)
        if damage=='admitted': attempt.state='admitted'
        if damage=='missing_owner':
            svc.db.delete(attempt); svc.db.flush(); svc.db.delete(owner)
        if damage=='wrong_generation': owner.binding_hash='f'*64
    if damage in ('wrong_credential','flag_off'):
        svc.config=replace(svc.config, secret_key='rotated' if damage=='wrong_credential' else 'fixture',
            owned_quiescence_enabled=damage!='flag_off')
        svc.runtime=replace(svc.runtime, config=svc.config)
    with pytest.raises(SocialError):
        reconcile_owned(svc, ACTOR, identity, uuid4(), scope(svc, identity), uuid4())
    assert totals(svc, identity)[1:] == (0, 2*len(png()), 1)
    assert io.calls==[]


def test_historical_upload_is_never_enrolled(media, monkeypatch):
    svc, store=media
    grant=svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    io=concrete_runtime(svc, monkeypatch)
    try:
        with pytest.raises(SocialError):
            reconcile_owned(svc, ACTOR, grant.asset.id, uuid4(), scope(svc, grant.asset.id), uuid4())
        assert totals(svc, grant.asset.id)==(0,0,2*len(png()),1)
        with svc.db.begin(): assert svc.db.get(SocialMediaWriteOwner, grant.asset.id) is None
    finally: io.sdk.close()


def test_server_finalizer_ack_is_recorded_but_issued_browser_still_blocks(owned):
    svc, io=owned
    grant=svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    with svc.db.begin():
        u=svc.db.get(SocialMediaUpload, grant.asset.id)
        io.objects[u.quarantine_key]=(png(), 'image/png', {})
    result=svc.complete(ACTOR, grant.asset.id, uuid4(),1,uuid4())
    assert result.state=='ready'
    with svc.db.begin():
        assert svc.db.scalar(select(SocialMediaWriteAttempt.state).where(SocialMediaWriteAttempt.kind=='finalize'))=='completed'
    with pytest.raises(SocialError):
        reconcile_owned(svc, ACTOR, grant.asset.id, uuid4(), scope(svc, grant.asset.id),uuid4())
    assert totals(svc, grant.asset.id)[2:]==(2*len(png()),1)
    assert not any(c[0]=='delete' for c in io.calls)


def test_lost_put_reply_and_positive_head_do_not_complete_attempt(owned, monkeypatch):
    svc, io=owned
    grant=svc.initiate(ACTOR,uuid4(),intent(),uuid4())
    with svc.db.begin():
        io.objects[svc.db.get(SocialMediaUpload,grant.asset.id).quarantine_key]=(png(),'image/png',{})
    original=io.sdk.put_object
    def lost(**kw):
        original(**kw)
        raise TimeoutError('actual owned fake stores bytes before losing response')
    monkeypatch.setattr(io.sdk,'put_object',lost)
    with pytest.raises(SocialError,match='MEDIA_FINALIZATION_UNKNOWN'):
        svc.complete(ACTOR,grant.asset.id,uuid4(),1,uuid4())
    with svc.db.begin():
        attempt=svc.db.scalar(select(SocialMediaWriteAttempt).where(SocialMediaWriteAttempt.kind=='finalize'))
        assert attempt.state=='admitted'
        asset,u=svc._rows(grant.asset.id)
        assert svc.runtime.storage.head(asset.storage_key).size==len(png())
        asset.lease_expires_at=svc.now()-timedelta(seconds=1)
    with pytest.raises(SocialError):
        reconcile_owned(svc,ACTOR,grant.asset.id,uuid4(),scope(svc,grant.asset.id),uuid4())
    assert totals(svc,grant.asset.id)==(0,0,2*len(png()),1)


@pytest.mark.parametrize('value',[True,False,0,-1,1.0,'1',None,float('nan'),float('inf')])
def test_direct_command_epoch_guards_survive_constructed_models(owned, monkeypatch,value):
    svc,io=owned
    identity=failed_intent(svc,io,monkeypatch)
    body=ReconcileOwnedUpload.model_construct(expected_version=value,expected_grant_epoch=1,expected_finalization_epoch=None)
    with pytest.raises((ValueError,SocialError)):
        reconcile_owned(svc,ACTOR,identity,uuid4(),body,uuid4())
    assert totals(svc,identity)==(0,0,2*len(png()),1)


@pytest.mark.parametrize('field',['actor','request_id'])
@pytest.mark.parametrize('value',[None,True,'invalid'])
def test_settled_replay_still_validates_caller_identity(owned,monkeypatch,field,value):
    svc,io=owned
    identity=failed_intent(svc,io,monkeypatch)
    body=scope(svc,identity); key=uuid4()
    reconcile_owned(svc,ACTOR,identity,key,body,uuid4())
    args=dict(service=svc,actor=ACTOR,asset_id=identity,key=key,body=body,request_id=uuid4())
    args[field]=value
    with pytest.raises(SocialError): reconcile_owned(**args)


@pytest.mark.parametrize('field,value',[
    ('grant_epoch',2),('grant_settled_epoch',0),('finalization_epoch',777),
    ('write_quiescence_receipt_hash','f'*64),
])
def test_settled_replay_refuses_changed_write_scope(owned,monkeypatch,field,value):
    svc,io=owned
    identity=failed_intent(svc,io,monkeypatch)
    body=scope(svc,identity); key=uuid4()
    reconcile_owned(svc,ACTOR,identity,key,body,uuid4())
    with svc.db.begin(): setattr(svc.db.get(SocialMediaUpload,identity),field,value)
    with pytest.raises(SocialError): reconcile_owned(svc,ACTOR,identity,key,body,uuid4())


def test_owned_history_lifetime_limit_survives_cleanup_refund(owned,monkeypatch):
    svc,io=owned
    svc.config=replace(svc.config,max_actor_assets=1,max_total_assets=1)
    svc.runtime=replace(svc.runtime,config=svc.config)
    identity=failed_intent(svc,io,monkeypatch)
    reconcile_owned(svc,ACTOR,identity,uuid4(),scope(svc,identity),uuid4())
    with svc.db.begin(): svc.db.get(SocialMediaUpload,identity).expires_at=svc.now()-timedelta(seconds=1)
    assert svc.cleanup()==1
    with pytest.raises(SocialError,match='MEDIA_QUOTA_EXCEEDED'):
        svc.initiate(ACTOR,uuid4(),intent(),uuid4())


def test_mutable_flush_hook_cannot_change_expected_audit_by_alias(owned,monkeypatch):
    svc,io=owned
    identity=failed_intent(svc,io,monkeypatch)
    def alter(session,context,instances):
        for row in session.new:
            if isinstance(row,SocialAuditEvent) and row.action=='media.writes_reconciled':
                row.details['grant_epoch']=True
    event.listen(svc.db,'before_flush',alter)
    try:
        with pytest.raises(SocialError):
            reconcile_owned(svc,ACTOR,identity,uuid4(),scope(svc,identity),uuid4())
    finally: event.remove(svc.db,'before_flush',alter)
    assert totals(svc,identity)==(0,0,2*len(png()),1)

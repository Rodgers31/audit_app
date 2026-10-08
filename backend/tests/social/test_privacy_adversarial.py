"""Independent executed hostile HTTP and forced PostgreSQL interleavings."""
import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Event
import time
from urllib.parse import quote
from uuid import UUID, uuid4
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session
from social.models import SocialAccount, SocialAuditEvent
from social.connections.models import SocialCredential, SocialOAuthFlow
from social.connections.provider import MetaProvider, InspectedDiscovery
from social.connections.service import ConnectionService
from social.privacy.api import DATA_PATH, STATUS_PATH, create_privacy_router
from social.privacy.models import SocialPrivacyOwnership, SocialPrivacyReceipt, SocialPrivacyRequestVariant
from social.privacy.ownership import OwnershipRecorder
from social.service import SocialError
from test_privacy_support import *
from test_privacy_postgres import privacy_pg


def http_client(engine, config):
    app=FastAPI()
    def dependency():
        with Session(engine) as session:
            yield privacy(session, config)
    app.include_router(create_privacy_router(dependency))
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize('body', [
    b'', b'signed_request', b'=a', b'signed_request=',
    b'signed_request=x&signed_request=y', b'signed_request=x&extra=',
    b'%73igned_request=%GG', b'signed_request=abc%',
    b'signed_request=abc%FF', b'signed_request=x&&',
    b'signed_request=x\xff', b'signed_request=x'*3000,
])
def test_hostile_form_never_acknowledges(db, config, body):
    response=http_client(db.bind,config).post(DATA_PATH, content=body, headers={'Content-Type':'application/x-www-form-urlencoded'})
    assert response.status_code==400
    assert response.headers['cache-control']=='private, no-store'
    assert 'confirmation_code' not in response.text
    assert db.scalar(select(func.count()).select_from(SocialPrivacyReceipt))==0


@pytest.mark.parametrize('query', ['', '?code=', '?code=true', '?code=null', '?code='+'a'*63,
    '?code='+'a'*65, '?code='+'A'*64, '?code='+'a'*64+'&code='+'a'*64,
    '?code='+'a'*64+'&subject=701', '?receipt_id='+str(uuid4()), '?code=%00', '?code=%FF'])
def test_status_lookup_hostile_and_unknown_are_indistinguishable(db, config, query):
    response=http_client(db.bind,config).get(STATUS_PATH+query)
    assert response.status_code==404
    result=response.json()['detail']
    assert result['code']=='NOT_FOUND' and result['message']=='Request status was not found.'
    assert set(result)== {'code','message','request_id','retryable','field_errors','target_errors'}
    assert result['field_errors']==[] and result['target_errors']==[]
    # A random request UUID may contain the short fixture subject's digits.
    # Exact allowlisted field/value assertions above prove absence of exposure.
    assert UUID(result['request_id']).version == 4 and result['retryable'] is False
    assert 'receipt_id' not in response.text
    assert response.headers['cache-control']=='private, no-store'


def test_status_and_callback_real_http_positive_control(db,config,graph):
    connected(db,config,graph)
    client=http_client(db.bind,config)
    accepted=client.post(DATA_PATH,content='signed_request='+quote(signed(config),safe=''),headers={'Content-Type':'application/x-www-form-urlencoded'})
    assert accepted.status_code==200
    out=accepted.json()
    assert set(out)=={'url','confirmation_code'} and len(out['confirmation_code'])==64
    status=client.get(STATUS_PATH,params={'code':out['confirmation_code']})
    assert status.status_code==200 and status.json()['deletion_completed'] is False
    assert '701' not in status.text and 'ownership' not in status.json()
    assert client.post(DATA_PATH, data={'signed_request':signed(config,padded=True)}).json()==out
    assert client.post(DATA_PATH.replace('data-deletion','deauthorization'), data={'signed_request':signed(config)}).status_code==404


@pytest.mark.parametrize('mutation', ['app','subject','duplicate','partial','unknown','wrong_page_subject'])
def test_actual_provider_port_result_mismatch_rolls_back(db,config,graph,mutation):
    class Provider(MetaProvider):
        def discover_with_ownership(self,*args):
            actual=super().discover_with_ownership(*args)
            if mutation=='app': return replace(actual,app_id='456')
            if mutation=='subject': return replace(actual,subject='702')
            if mutation=='duplicate': return replace(actual,page_ids=actual.page_ids*2)
            if mutation=='partial': return replace(actual,page_ids=())
            if mutation=='unknown': return {'app_id':'123','subject':'701','grant':actual.grant}
            actual.grant['choices'][0]['metadata']['external_user_id']='702'
            return actual
    service=ConnectionService(db,config,provider_factory=lambda c:Provider(c,transport=httpx.MockTransport(graph)),ownership_recorder=OwnershipRecorder(config.app_id,digester()))
    flow,state=start(service)
    with pytest.raises(SocialError) as caught:
        complete(service,state)
    assert caught.value.code == 'PRIVACY_OWNERSHIP_UNRESOLVED'
    assert db.scalar(select(func.count()).select_from(SocialPrivacyOwnership))==0
    assert db.scalar(select(func.count()).select_from(SocialCredential))==0
    assert db.get(SocialOAuthFlow,UUID(flow['flow_id'])).status=='failed'
    assert all(a.action!='connection.discovered' for a in db.scalars(select(SocialAuditEvent)))
    assert len(graph.calls)>3  # Real HTTP port actually inspected before hostile transformation.


def wait_until_blocked(engine, expected='social_controls'):
    started=time.monotonic()
    while time.monotonic()-started<3:
        with engine.connect() as observer:
            value=observer.execute(text("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE :pattern AND pid<>pg_backend_pid() AND datname=current_database()"), {'pattern':'%'+expected+'%'}).scalar()
        if value: return
        time.sleep(.01)
    raise AssertionError('Forced competing operation never blocked on real PostgreSQL lock')


def test_pg_first_receipt_rollback_releases_waiter_and_restart_has_single_ack(privacy_pg,config,graph):
    with Session(privacy_pg) as db: connected(db,config,graph)
    inserted,release,started=Event(),Event(),Event()
    failures=[]
    first=True
    def sabotage(conn,cursor,statement,params,context,many):
        nonlocal first
        if first and statement.startswith('INSERT INTO social_privacy_receipts'):
            first=False; inserted.set(); assert release.wait(5)
            raise RuntimeError('owned hostile post-insert fault')
    event.listen(privacy_pg,'after_cursor_execute',sabotage)
    def receive(two=False):
        if two: started.set()
        with Session(privacy_pg) as db:
            return privacy(db,config).receive(signed(config),kind='deauthorization')
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            one=pool.submit(receive); assert inserted.wait(5)
            two=pool.submit(receive,True); assert started.wait(5)
            wait_until_blocked(privacy_pg)
            assert not two.done(); release.set()
            with pytest.raises(RuntimeError,match='post-insert fault'): one.result(5)
            result=two.result(5)
    finally:
        release.set(); event.remove(privacy_pg,'after_cursor_execute',sabotage)
    with Session(privacy_pg) as fresh:
        rows=list(fresh.scalars(select(SocialPrivacyReceipt)))
        assert len(rows)==1 and str(rows[0].id)==result['receipt_id']
        assert all(a.connection_state=='revoked' for a in fresh.scalars(select(SocialAccount)))
        assert len(list(fresh.scalars(select(SocialPrivacyRequestVariant))))==1
        assert fresh.scalar(select(func.count()).select_from(SocialAuditEvent).where(SocialAuditEvent.action=='privacy.received'))==1
        fresh.rollback()
        assert privacy(fresh,config).receive(signed(config),kind='deauthorization')==result


def test_pg_callback_wins_select_lock_and_prevents_credentials(privacy_pg,config,graph):
    with Session(privacy_pg) as db:
        service=connection(db,config,graph); flow,state=start(service); complete(service,state)
        flow_id=UUID(flow['flow_id'])
    inserted,release,started=Event(),Event(),Event()
    first=True
    def pause(conn,cursor,statement,params,context,many):
        nonlocal first
        if first and statement.startswith('INSERT INTO social_privacy_receipts'):
            first=False; inserted.set(); assert release.wait(5)
    event.listen(privacy_pg,'after_cursor_execute',pause)
    def callback():
        with Session(privacy_pg) as db: return privacy(db,config).receive(signed(config),kind='deauthorization')
    def selecting():
        started.set()
        with Session(privacy_pg) as db: return select_asset(connection(db,config,graph),flow_id)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            one=pool.submit(callback); assert inserted.wait(5)
            two=pool.submit(selecting); assert started.wait(5)
            wait_until_blocked(privacy_pg); assert not two.done(); release.set()
            assert one.result(5)['state']=='blocked_future_mutations'
            with pytest.raises(SocialError) as exc: two.result(5)
            assert exc.value.code=='PRIVACY_FLOW_BLOCKED'
    finally:
        release.set(); event.remove(privacy_pg,'after_cursor_execute',pause)
    with Session(privacy_pg) as db:
        assert db.scalar(select(func.count()).select_from(SocialCredential))==0
        row=db.get(SocialOAuthFlow,flow_id)
        assert row.status=='awaiting_selection' and row.encrypted_pending_grant is not None


def test_pg_reconnect_commit_wins_exact_replay_and_new_event_blocks_only_current(privacy_pg,config,graph):
    with Session(privacy_pg) as db:
        service,_,selected=connected(db,config,graph)
        first=privacy(db,config).receive(signed(config),kind='deauthorization')
        flow,state=start(service,reconnect=UUID(selected['accounts'][0]['id'])); complete(service,state)
        flow_id=UUID(flow['flow_id'])
    saved,release,started=Event(),Event(),Event()
    first_save=True
    def pause(conn,cursor,statement,params,context,many):
        nonlocal first_save
        if first_save and statement.startswith('INSERT INTO social_privacy_ownership') and 'credential:' in str(params):
            first_save=False; saved.set(); assert release.wait(5)
    event.listen(privacy_pg,'after_cursor_execute',pause)
    def selecting():
        with Session(privacy_pg) as db: return select_asset(connection(db,config,graph),flow_id)
    def replaying():
        started.set()
        with Session(privacy_pg) as db: return privacy(db,config).receive(signed(config,padded=True),kind='deauthorization')
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            one=pool.submit(selecting); assert saved.wait(5)
            two=pool.submit(replaying); assert started.wait(5)
            wait_until_blocked(privacy_pg); assert not two.done(); release.set()
            selected=one.result(5); assert two.result(5)==first
    finally:
        release.set(); event.remove(privacy_pg,'after_cursor_execute',pause)
    with Session(privacy_pg) as db:
        current={a.credential_id for a in db.scalars(select(SocialAccount))}
        assert all(db.get(SocialCredential,c).revoked_at is None for c in current)
        assert all(a.connection_state=='connected' for a in db.scalars(select(SocialAccount)))
        old_refs=db.get(SocialPrivacyReceipt,UUID(first['receipt_id'])).affected
        assert not current.intersection(UUID(r['credential_id']) for r in old_refs if r['credential_id'])
        db.rollback()
        # Positive new event uses an unambiguously later provider second.
        event_time=int(datetime.now(timezone.utc).timestamp())+1
        fresh=privacy(db,config).receive(signed(config,payload={'algorithm':'HMAC-SHA256','user_id':'701','issued_at':event_time}),kind='deauthorization')
        assert fresh['receipt_id']!=first['receipt_id']
        assert all(a.connection_state=='revoked' for a in db.scalars(select(SocialAccount)))


def test_pg_variant_rotation_dedup_concurrent_shared_frozen_capability(privacy_pg,config,graph):
    with Session(privacy_pg) as db: connected(db,config,graph)
    inserted,release,started=Event(),Event(),Event(); first=True
    def pause(conn,cursor,statement,params,context,many):
        nonlocal first
        if first and statement.startswith('INSERT INTO social_privacy_receipts'):
            first=False; inserted.set(); assert release.wait(5)
    event.listen(privacy_pg,'after_cursor_execute',pause)
    def receive(rotated=False):
        if rotated: started.set()
        with Session(privacy_pg) as db:
            keys=digester('d2',{'d1':b'x'*32,'d2':b'y'*32}) if rotated else digester()
            value=signed(config,raw='{ "app_id":"123", "user_id":"701", "algorithm":"HMAC-SHA256" }',padded=True) if rotated else signed(config)
            return privacy(db,config,keys).receive(value,kind='data_deletion')
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            one=pool.submit(receive); assert inserted.wait(5)
            two=pool.submit(receive,True); assert started.wait(5)
            wait_until_blocked(privacy_pg); release.set()
            result=one.result(5); assert two.result(5)==result
    finally:
        release.set(); event.remove(privacy_pg,'after_cursor_execute',pause)
    with Session(privacy_pg) as db:
        assert db.scalar(select(func.count()).select_from(SocialPrivacyReceipt))==1
        assert db.scalar(select(func.count()).select_from(SocialPrivacyRequestVariant))==2
        db.rollback()
        assert privacy(db,config).status(result['confirmation_code'])['deletion_completed'] is False


def test_delayed_expiry_only_event_cannot_revoke_generation_after_expiry(privacy_pg,config,graph):
    with Session(privacy_pg) as db:
        _,flow_id,_=connected(db,config,graph)
        generation=db.get(SocialOAuthFlow,flow_id).created_at
        old_expiry=int(generation.timestamp())-1
        db.rollback()
        out=privacy(db,config).receive(signed(config,payload={'algorithm':'HMAC-SHA256','user_id':'701','expires':old_expiry}),kind='deauthorization')
        assert out['state']=='ownership_unresolved'
        assert all(a.connection_state=='connected' for a in db.scalars(select(SocialAccount)))
        assert all(c.revoked_at is None for c in db.scalars(select(SocialCredential)))


def test_pg_active_admission_rechecked_after_callback_without_discarding_intent(privacy_pg,config,graph,monkeypatch):
    import test_worker_materials
    from social.worker.materials import MaterialUnavailable
    from social.models import SocialPostTarget, SocialPublishAttempt
    monkeypatch.setattr(test_worker_materials,'svc',connection)
    with Session(privacy_pg,expire_on_commit=False) as db:
        loader,request,account_id,credential_id=test_worker_materials.admitted.__wrapped__(db,config,graph)
        material=asyncio.run(loader(request))
        assert material.credential_id==credential_id  # Meaningful admitted positive control.
        original_attempt=db.scalar(select(SocialPublishAttempt))
        original_receipt=copy.deepcopy(original_attempt.receipt)
        original_operation=original_attempt.operation_id
        original_checkpoint=copy.deepcopy(db.get(SocialPostTarget,UUID(request.claim.target_id)).checkpoint)
        db.rollback()
        privacy(db,config).receive(signed(config),kind='deauthorization')
        with pytest.raises(MaterialUnavailable,match='CREDENTIAL_ACCOUNT_CHANGED'):
            asyncio.run(loader(request))
    with Session(privacy_pg) as restarted:
        target=restarted.get(SocialPostTarget,UUID(request.claim.target_id))
        attempt=restarted.scalar(select(SocialPublishAttempt))
        account=restarted.get(SocialAccount,account_id)
        assert account.connection_state=='revoked' and not account.publishing_enabled
        assert str(account.publish_lease_token)==request.claim.token
        assert target.state=='dispatching' and target.checkpoint==original_checkpoint
        assert attempt.receipt==original_receipt and attempt.operation_id==original_operation
        assert attempt.outcome=='intent' and attempt.completed_at is None


def test_accepted_variants_survive_key_loss_and_ceiling_never_acknowledges(db,config,graph):
    connected(db,config,graph)
    original=privacy(db,config).receive(signed(config),kind='data_deletion')
    raw='{"algorithm":"HMAC-SHA256","user_id":"701"}'
    for n in range(1,64):
        accepted_variant=signed(config,raw=' '*n+raw)
        assert privacy(db,config).receive(accepted_variant,kind='data_deletion')==original
    with pytest.raises(SocialError) as overflow:
        privacy(db,config).receive(signed(config,raw=' '*64+raw),kind='data_deletion')
    assert overflow.value.code=='PRIVACY_VARIANT_LIMIT' and overflow.value.status==503
    assert db.scalar(select(func.count()).select_from(SocialPrivacyRequestVariant))==64
    assert db.scalar(select(func.count()).select_from(SocialPrivacyReceipt))==1
    db.rollback()
    with Session(db.bind) as restarted:
        missing_prior_key=digester('d2',{'d2':b'y'*32})
        retried=privacy(restarted,config,missing_prior_key).receive(accepted_variant,kind='data_deletion')
        assert retried==original
        assert restarted.scalar(select(func.count()).select_from(SocialPrivacyReceipt))==1


def test_pg_stale_credential_versions_leave_current_grants_and_report_unresolved(privacy_pg,config,graph):
    with Session(privacy_pg) as db:
        connected(db,config,graph)
        for credential in db.scalars(select(SocialCredential)):
            credential.version+=1
        db.commit()
        out=privacy(db,config).receive(signed(config),kind='deauthorization')
        assert out['state']=='ownership_unresolved'
        assert out['resolution']=='indexed_partial_version_changed'
        assert all(a.connection_state=='connected' for a in db.scalars(select(SocialAccount)))
        assert all(c.revoked_at is None for c in db.scalars(select(SocialCredential)))
        assert len(db.get(SocialPrivacyReceipt,UUID(out['receipt_id'])).affected)==4
    with Session(privacy_pg) as restarted:
        assert privacy(restarted,config).receive(signed(config),kind='deauthorization')==out
        assert all(c.revoked_at is None for c in restarted.scalars(select(SocialCredential)))

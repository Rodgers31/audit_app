"""Retained privacy history remains authoritative at explicit local consent."""
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from social.account_publishing import AccountPublishingCommand, account_publishing, set_account_publishing
from social.connections.models import SocialCredential, SocialOAuthFlow
from social.models import SocialAuditEvent, SocialCommandReceipt
from social.privacy.models import SocialPrivacyOwnership, SocialPrivacyReceipt
from social.service import SocialError, SocialService
from test_account_publishing import connected, REGISTRY
from test_media_support import media_db
from test_existing_grant_verification import saved, db, config, graph, verify

ACTOR=uuid4()


def retained(db, *, app='123', subject='a'*64, version='v1', received=None):
    audit=SocialAuditEvent(id=uuid4(),actor_kind='system',action='privacy.received',request_id=str(uuid4()))
    db.add(audit);db.flush()
    values=dict(app_id=app,kind='deauthorization',digest_version=version,subject_digest=subject,
        event_key=uuid4().hex*2,request_fingerprint=uuid4().hex*2,affected={},resolution='fixture_pending',state='ownership_unresolved',audit_id=audit.id)
    if received is not None:values['received_at']=received
    db.add(SocialPrivacyReceipt(**values));db.commit()


def index_grant(db,row):
    page=db.get(SocialCredential,row.credential_id);parent=db.get(SocialCredential,page.parent_credential_id)
    now=SocialService(db).now()
    flow=SocialOAuthFlow(id=uuid4(),actor_id=ACTOR,state_hash=uuid4().hex*2,binding_hash=uuid4().hex*2,key_version='fixture',redirect_uri='https://admin.example.test/callback',status='completed',expires_at=now+timedelta(days=1),consumed_at=now)
    db.add(flow);db.flush()
    for credential in (page,parent):
        db.add(SocialPrivacyOwnership(app_id='123',digest_version='v1',subject_digest='a'*64,reference_key=str(uuid4()),flow_id=flow.id,
            credential_id=credential.id,credential_version=credential.version,account_id=row.id if credential is page else None,
            page_id='fixture-page' if credential is page else None,generation_at=parent.created_at))
    db.commit()


def consent(svc,identifier,enabled=True,body=None):
    status=account_publishing(svc,identifier)
    body=body or AccountPublishingCommand(expected_controls_version=status['controls_version'],expected_state=status['state_token'],publishing_enabled=enabled,reason='Synthetic explicit consent')
    svc.db.rollback()
    return svc.command(actor=ACTOR,route='PATCH consent/'+str(identifier),key=uuid4(),body=body.model_dump(mode='json'),request_id=uuid4(),action=lambda:set_account_publishing(svc,identifier,body))[1]


@pytest.mark.parametrize('indexed,configured,app,subject,version,expected',[
    (False,'123','999','a'*64,'v1',None),
    (False,None,'999','a'*64,'v1','PRIVACY_STATE_UNAVAILABLE'),
    (False,'123','123','a'*64,'v1','PRIVACY_STATE_UNAVAILABLE'),
    (True,'123','123','a'*64,'v1','PRIVACY_GRANT_BLOCKED'),
    (True,'123','123','b'*64,'v1',None),
    (True,'123','999','a'*64,'v1',None),
    (True,'123','123','b'*64,'v2','PRIVACY_STATE_UNAVAILABLE'),
])
def test_privacy_namespace_and_subject_scope(media_db,indexed,configured,app,subject,version,expected):
    row=connected(media_db);identifier=row.id
    if indexed:index_grant(media_db,row)
    retained(media_db,app=app,subject=subject,version=version)
    svc=SocialService(media_db,available_adapters=REGISTRY,privacy_app_id=configured)
    status=account_publishing(svc,identifier)
    assert status['enable_available'] is (expected is None)
    if expected:
        assert expected in status['enable_blockers'] and expected in status['delivery_holds']
        with pytest.raises(SocialError,match=expected):consent(svc,identifier)
        assert consent(svc,identifier,False)['publishing_enabled'] is False
    else:
        assert consent(svc,identifier)['publishing_enabled'] is True


def test_old_retained_history_does_not_override_new_grant_generation(media_db):
    row=connected(media_db);identifier=row.id;index_grant(media_db,row)
    retained(media_db,received=SocialService(media_db).now()-timedelta(days=1))
    svc=SocialService(media_db,available_adapters=REGISTRY,privacy_app_id='123')
    assert consent(svc,identifier)['publishing_enabled'] is True


def test_receipt_after_readiness_invalidates_cached_consent(media_db):
    row=connected(media_db);identifier=row.id;svc=SocialService(media_db,available_adapters=REGISTRY,privacy_app_id='123')
    status=account_publishing(svc,identifier)
    body=AccountPublishingCommand(expected_controls_version=status['controls_version'],expected_state=status['state_token'],publishing_enabled=True,reason='Synthetic cached consent')
    retained(media_db)
    with pytest.raises(SocialError,match='VERSION_CONFLICT'):consent(svc,identifier,body=body)


def test_real_provider_verification_cannot_bypass_later_retained_receipt(saved):
    service,row,_=saved;identifier=row.id
    result=verify(service,SimpleNamespace(id=identifier))
    assert result['enable_available'] is True
    retained(service.db,subject='a'*64)
    with pytest.raises(SocialError,match='PRIVACY_STATE_UNAVAILABLE'):consent(service.base,identifier)
    assert not any(r.route_key.startswith('PATCH consent/') for r in service.db.scalars(select(SocialCommandReceipt)))


def test_owner_inventory_bound_cannot_certify_an_omitted_namespace(media_db):
    from uuid import UUID
    from sqlalchemy import insert
    row=connected(media_db);identifier=row.id;index_grant(media_db,row)
    page=media_db.get(SocialCredential,row.credential_id);parent=media_db.get(SocialCredential,page.parent_credential_id)
    flow_id=media_db.scalar(select(SocialOAuthFlow.id).limit(1))
    rows=[]
    for number in range(1,1003):
        credential=page if number==1 else parent
        rows.append(dict(id=UUID(int=number),app_id='456' if number==1002 else '123',digest_version='v1',subject_digest='a'*64,
            reference_key='bounded-fixture:'+str(number),flow_id=flow_id,credential_id=credential.id,credential_version=credential.version,
            account_id=identifier if number==1 else None,page_id='fixture-page' if number==1 else None,generation_at=parent.created_at))
    media_db.execute(insert(SocialPrivacyOwnership),rows);media_db.commit()
    retained(media_db,app='456')
    svc=SocialService(media_db,available_adapters=REGISTRY,privacy_app_id='123')
    status=account_publishing(svc,identifier)
    assert status['enable_available'] is False
    assert 'PRIVACY_STATE_UNAVAILABLE' in status['enable_blockers']
    assert consent(svc,identifier,False)['publishing_enabled'] is False

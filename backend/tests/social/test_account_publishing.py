"""Synthetic local account controls; no credentials are decrypted or sent."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from social.account_publishing import AccountPublishingCommand, account_publishing, set_account_publishing
from social.connections.models import SocialCredential
from social.models import SocialAccount, SocialControls, SocialAuditEvent, SocialPost, SocialPostRevision, SocialPublication, SocialPostTarget
from social.service import SocialService, SocialError
from social.contracts import CapabilitySet, ValidationResult
from test_media_support import media_db, media

ACTOR = uuid4()
CAPS = CapabilitySet(eligible=True, adapter_available=True, supported_formats=('text','image'), provider_api_version='fixture', feature_states={'publishing':'supported'}, price_class='free')
class Adapter:
    def capabilities(self, account): return CAPS
    def validate(self, payload, capabilities): return ValidationResult(valid=True)
REGISTRY = {('facebook','facebook_pages'): Adapter()}


def connected(db):
    now = SocialService(db).now()
    parent = SocialCredential(id=uuid4(), provider='meta', credential_kind='facebook_user', encrypted_bundle=b'synthetic', key_version='fixture', version=1, access_expires_at=now-timedelta(days=1))
    page = SocialCredential(id=uuid4(), provider='meta', credential_kind='facebook_page', parent_credential_id=parent.id, encrypted_bundle=b'synthetic', key_version='fixture', version=1)
    db.add(parent); db.flush(); db.add(page); db.flush()
    row = SocialAccount(id=uuid4(), platform='facebook', api_product='facebook_pages', external_account_id='fixture-page', display_name='Synthetic Page', connection_method='facebook_login', connection_state='connected', credential_id=page.id, publishing_enabled=False, granted_scopes=[], capability_snapshot=CAPS.model_dump(mode='json'))
    db.add(row); db.commit(); return row


def execute(db, row, body, *, key=None, registry=REGISTRY):
    account_id = row.id
    db.rollback(); svc = SocialService(db, available_adapters=registry)
    return svc.command(actor=ACTOR, route='account/'+str(account_id), key=key or uuid4(), body=body.model_dump(mode='json'), request_id=uuid4(), action=lambda: set_account_publishing(svc,account_id,body))[1]


def intent(db, row, enabled=True, registry=REGISTRY):
    status = account_publishing(SocialService(db, available_adapters=registry),row.id)
    db.rollback()
    return AccountPublishingCommand(expected_controls_version=status['controls_version'], expected_state=status['state_token'], publishing_enabled=enabled, reason='Local fixture account decision')


def test_enable_replay_pause_and_stale_aba_leave_global_off(media_db):
    db=media_db; row=connected(db); body=intent(db,row); key=uuid4()
    result=execute(db,row,body,key=key)
    assert result['publishing_enabled'] is True
    assert result['global_publishing_enabled'] is False
    assert execute(db,row,body,key=key)==result
    execute(db,row,intent(db,row,False))
    with pytest.raises(SocialError, match='VERSION_CONFLICT'): execute(db,row,body)
    assert db.get(SocialAccount,row.id).publishing_enabled is False
    assert db.scalar(select(SocialControls)).publishing_enabled is False
    assert len(list(db.scalars(select(SocialAuditEvent))))==2


@pytest.mark.parametrize('change,code', [
    ('disconnected','ACCOUNT_DISCONNECTED'), ('unsupported','NATIVE_ADMISSION_UNAVAILABLE'),
    ('revoked','CREDENTIAL_UNAVAILABLE'), ('expired','CREDENTIAL_UNAVAILABLE'),
    ('refresh','CREDENTIAL_UNAVAILABLE'), ('hold','ACCOUNT_HELD'), ('lease','DELIVERY_UNRESOLVED')])
def test_enable_refuses_but_pause_preserves_uncertainty(media_db,change,code):
    db=media_db; row=connected(db)
    if change=='disconnected': row.connection_state='disconnected'
    if change=='unsupported': row.capability_snapshot={}
    if change=='hold': row.hold_reason='outcome_unknown'
    if change=='lease': retain_delivery(db,row)
    cred=db.get(SocialCredential,row.credential_id)
    if change=='revoked': cred.revoked_at=SocialService(db).now()
    if change=='expired': cred.access_expires_at=SocialService(db).now()-timedelta(seconds=1)
    if change=='refresh': cred.refresh_lease_token=uuid4(); cred.refresh_lease_expires_at=SocialService(db).now()-timedelta(seconds=1)
    db.commit(); before=row.publish_lease_token
    body=intent(db,row)
    with pytest.raises(SocialError, match=code): execute(db,row,body)
    result=execute(db,row,intent(db,row,False))
    assert result['publishing_enabled'] is False
    assert db.get(SocialAccount,row.id).publish_lease_token==before


def test_snapshot_fences_credential_rotation_and_typed_registry(media_db):
    db=media_db; row=connected(db); body=intent(db,row)
    db.get(SocialCredential,row.credential_id).version+=1; db.commit()
    with pytest.raises(SocialError, match='VERSION_CONFLICT'): execute(db,row,body)
    body=intent(db,row,registry=('facebook',))
    with pytest.raises(SocialError, match='NATIVE_ADMISSION_UNAVAILABLE'): execute(db,row,body,registry=('facebook',))


def retain_delivery(db,row):
    now=SocialService(db).now()
    post=SocialPost(id=uuid4(),title='Retained fixture',content_type='announcement',editorial_state='approved')
    db.add(post); db.flush()
    revision=SocialPostRevision(id=uuid4(),post_id=post.id,revision_no=1,document={},evidence_snapshot={},content_hash='a'*64)
    db.add(revision); db.flush()
    publication=SocialPublication(id=uuid4(),post_id=post.id,revision_id=revision.id,approved_by=ACTOR,approved_at=now,approved_hash='a'*64)
    db.add(publication); db.flush()
    target=SocialPostTarget(id=uuid4(),publication_id=publication.id,account_id=row.id,resolved_payload={},payload_hash='a'*64,capability_version='fixture',state='outcome_unknown')
    db.add(target); db.flush()
    row.publish_lease_token=uuid4(); row.publish_lease_target_id=target.id; row.publish_lease_expires_at=now-timedelta(seconds=1)


def test_suppressed_account_write_cannot_create_success_receipt(media_db):
    from sqlalchemy import text
    from social.models import SocialCommandReceipt
    db=media_db; row=connected(db); body=intent(db,row)
    db.execute(text("CREATE TRIGGER suppress_account_toggle AFTER UPDATE ON social_accounts BEGIN UPDATE social_accounts SET publishing_enabled=OLD.publishing_enabled WHERE id=NEW.id; END")); db.commit()
    with pytest.raises(SocialError, match='ACCOUNT_CONTROL_FAILED'): execute(db,row,body)
    assert db.get(SocialAccount,row.id).publishing_enabled is False
    assert list(db.scalars(select(SocialCommandReceipt)))==[]


@pytest.mark.parametrize('change', ['parent_data_expired','parent_revoked','parent_refresh','page_data_expired','missing_credential'])
def test_credential_safety_boundaries(media_db,change):
    db=media_db; row=connected(db); cred=db.get(SocialCredential,row.credential_id); parent=db.get(SocialCredential,cred.parent_credential_id); now=SocialService(db).now()
    if change=='parent_data_expired': parent.data_access_expires_at=now-timedelta(seconds=1)
    if change=='parent_revoked': parent.revoked_at=now
    if change=='parent_refresh': parent.refresh_lease_token=uuid4(); parent.refresh_lease_expires_at=now-timedelta(seconds=1)
    if change=='page_data_expired': cred.data_access_expires_at=now-timedelta(seconds=1)
    if change=='missing_credential': row.credential_id=None
    db.commit()
    with pytest.raises(SocialError, match='CREDENTIAL_UNAVAILABLE'): execute(db,row,intent(db,row))


def test_account_api_strict_auth_fences_and_replay(media):
    from fastapi import HTTPException
    from test_manual_media_workflow import mounted_client, BASE, headers
    from social.http_boundary import require_admin
    db,_=media; row=connected(db.db); client=mounted_client(media); path=BASE+'/accounts/'+str(row.id)+'/publishing'
    observed=client.get(path)
    assert observed.status_code==200 and observed.headers['cache-control']=='private, no-store'
    state=observed.json(); body={'expected_controls_version':state['controls_version'],'expected_state':state['state_token'],'publishing_enabled':True,'reason':'Synthetic explicit account consent'}
    for patch in ({'publishing_enabled':'true'},{'expected_controls_version':True},{'expected_controls_version':0},{'expected_state':'bad'},{'extra':True}):
        assert client.patch(path,json={**body,**patch},headers=headers()).status_code==422
    assert client.patch(path,json=body).status_code==422
    key=headers(); accepted=client.patch(path,json=body,headers=key)
    assert accepted.status_code==200, accepted.text
    assert accepted.json()['global_publishing_enabled'] is False
    assert client.patch(path,json=body,headers=key).json()==accepted.json()
    assert client.patch(path,json={**body,'publishing_enabled':False},headers=key).json()['detail']['code']=='IDEMPOTENCY_CONFLICT'
    assert client.patch(path,json=body,headers=headers()).json()['detail']['code']=='VERSION_CONFLICT'
    def denied(): raise HTTPException(403)
    client.app.dependency_overrides[require_admin]=denied
    assert client.get(path).status_code==403
    assert client.patch(path,json=body,headers=headers()).status_code==403


def test_genuinely_connected_other_platform_uses_its_own_credential_namespace(media_db):
    from social.platform_connections.models import PlatformCredential
    db=media_db; row=connected(db)
    row.platform='threads'; row.api_product='threads'; row.credential_id=None
    credential=PlatformCredential(id=uuid4(),account_id=row.id,platform='threads',encrypted_bundle=b'synthetic',key_version='fixture',version=1,access_expires_at=SocialService(db).now()+timedelta(days=1),issued_at=SocialService(db).now())
    db.add(credential); db.commit(); registry={('threads','threads'):Adapter()}
    result=execute(db,row,intent(db,row,registry=registry),registry=registry)
    assert result['publishing_enabled'] is True and result['global_publishing_enabled'] is False
    credential.refresh_claim=uuid4(); db.commit()
    with pytest.raises(SocialError,match='CREDENTIAL_UNAVAILABLE'): execute(db,row,intent(db,row,registry=registry),registry=registry)


def test_numeric_native_proof_must_not_authorize_enable(media_db):
    db=media_db; row=connected(db)
    from sqlalchemy.orm.attributes import flag_modified
    row.capability_snapshot={**row.capability_snapshot,'eligible':1}; flag_modified(row,'capability_snapshot'); db.commit()
    db.refresh(row)
    assert type(row.capability_snapshot['eligible']) is int
    body=intent(db,row)
    with pytest.raises(SocialError,match='NATIVE_ADMISSION_UNAVAILABLE'): execute(db,row,body)
    assert db.get(SocialAccount,row.id).publishing_enabled is False


def test_account_setter_requires_command_and_clears_pending_checks(media_db):
    db=media_db; row=connected(db); body=intent(db,row); svc=SocialService(db,available_adapters=REGISTRY)
    with pytest.raises(SocialError,match='COMMAND_REQUIRED'): set_account_publishing(svc,row.id,body)
    db.rollback()
    assert svc._command_postconditions is None
    execute(db,row,body)


def test_suppressed_audit_cannot_create_success_receipt(media_db):
    from sqlalchemy import text
    from social.models import SocialCommandReceipt
    db=media_db; row=connected(db); body=intent(db,row)
    db.execute(text("CREATE TRIGGER suppress_account_audit BEFORE INSERT ON social_audit_events WHEN NEW.action='account.publishing_updated' BEGIN SELECT RAISE(IGNORE); END")); db.commit()
    with pytest.raises(SocialError,match='ACCOUNT_CONTROL_FAILED'): execute(db,row,body)
    assert db.get(SocialAccount,row.id).publishing_enabled is False
    assert list(db.scalars(select(SocialCommandReceipt)))==[]


@pytest.mark.parametrize('snapshot',[None,[],True,1,'invalid'])
def test_malformed_tiktok_admission_cannot_prevent_safety_pause(media_db,snapshot):
    from sqlalchemy.orm.attributes import flag_modified
    db=media_db; row=connected(db); row.platform='tiktok'; row.api_product='tiktok_accounts_api'; row.credential_id=None
    row.publishing_enabled=True; row.capability_snapshot=snapshot; flag_modified(row,'capability_snapshot'); db.commit(); db.refresh(row)
    registry={('tiktok','tiktok_accounts_api'):Adapter()}
    body=intent(db,row,False,registry=registry)
    result=execute(db,row,body,registry=registry)
    assert result['publishing_enabled'] is False
    assert 'NATIVE_ADMISSION_UNAVAILABLE' in result['enable_blockers']


@pytest.mark.parametrize('policy',[None,[],True,1,'invalid',{'facebook':None},{'facebook':[]},{'facebook':True},{'facebook':1},{'facebook':'invalid'},{'facebook':{'publishing_enabled':None}},{'facebook':{'publishing_enabled':1}},{'facebook':{'publishing_enabled':'false'}}])
def test_malformed_platform_controls_refuse_enable_and_preserve_pause(media_db,policy):
    from sqlalchemy.orm.attributes import flag_modified
    db=media_db; row=connected(db); row.publishing_enabled=True
    controls=SocialControls(id=1,version=1,platform_controls=policy); db.add(controls); db.flush()
    controls.platform_controls=policy; flag_modified(controls,'platform_controls'); db.commit(); db.refresh(controls)
    assert type(controls.platform_controls) is type(policy)
    observed=account_publishing(SocialService(db,available_adapters=REGISTRY),row.id)
    assert observed['enable_available'] is False
    assert 'PLATFORM_CONTROLS_UNAVAILABLE' in observed['enable_blockers']
    assert 'PLATFORM_CONTROLS_UNAVAILABLE' in observed['delivery_holds']
    assert execute(db,row,intent(db,row,False))['publishing_enabled'] is False
    with pytest.raises(SocialError,match='PLATFORM_CONTROLS_UNAVAILABLE'): execute(db,row,intent(db,row,True))


@pytest.mark.parametrize('policy',[{}, {'instagram':None}, {'facebook':{}}, {'facebook':{'publishing_enabled':True}}, {'facebook':{'publishing_enabled':False}}])
def test_valid_platform_controls_keep_inheritance_and_separate_ceiling(media_db,policy):
    db=media_db; row=connected(db); db.add(SocialControls(id=1,version=1,platform_controls=policy)); db.commit()
    observed=account_publishing(SocialService(db,available_adapters=REGISTRY),row.id)
    assert observed['enable_available'] is True
    assert ('PLATFORM_PUBLISHING_DISABLED' in observed['delivery_holds']) is (policy.get('facebook',{}).get('publishing_enabled') is False)
    assert execute(db,row,intent(db,row))['global_publishing_enabled'] is False


def test_legacy_proof_mismatch_is_distinct_from_absent_native_runtime(media_db):
    db=media_db; row=connected(db)
    row.capability_snapshot={**row.capability_snapshot,'adapter_available':False,'supported_formats':[],'feature_states':{'publishing':'unsupported'}}; db.commit()
    observed=account_publishing(SocialService(db,available_adapters=REGISTRY),row.id)
    assert 'NATIVE_ADMISSION_UNAVAILABLE' in observed['enable_blockers']
    assert 'NATIVE_RUNTIME_UNAVAILABLE' not in observed['delivery_holds']
    absent=account_publishing(SocialService(db,available_adapters={}),row.id)
    assert 'NATIVE_ADMISSION_UNAVAILABLE' in absent['enable_blockers']
    assert 'NATIVE_RUNTIME_UNAVAILABLE' in absent['delivery_holds']


def test_same_clock_repeated_consent_has_distinct_durable_state_witness(media_db,monkeypatch):
    db=media_db; row=connected(db); fixed=SocialService(db).now(); db.rollback()
    monkeypatch.setattr(SocialService,'now',lambda self:fixed)
    first=execute(db,row,intent(db,row,False))
    second=execute(db,row,intent(db,row,False))
    assert second['controls_version']==first['controls_version']+1
    assert second['state_token']!=first['state_token']

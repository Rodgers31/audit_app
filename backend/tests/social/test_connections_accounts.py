from datetime import timedelta
from dataclasses import replace
from uuid import UUID,uuid4
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from social.connections.crypto import CredentialCipher
from social.connections.contracts import AccountCommand
from social.connections.models import SocialCredential,SocialOAuthFlow
from social.models import SocialAccount, SocialAuditEvent
from social.service import SocialError
from test_connections_support import *

def connected(service):
    started,state=start(service)
    complete(service,state)
    result=select_asset(service,UUID(started['flow_id']))
    return [UUID(a['id']) for a in result['accounts']]

def account_command(service,account_id,version=1,rotate=False,key=None):
    current=service.health(account_id)
    service.db.rollback()
    return service.account_command(account_id,ACTOR,BINDING,('rotate' if rotate else 'disconnect')+'/'+str(account_id),key or uuid4(),AccountCommand(expected_credential_id=UUID(current['credential_id']),expected_credential_version=version,reason='Audited fixture action'),uuid4(),rotate=rotate)

def test_health_disconnect_shared_grant_and_audit(db,config,graph):
    service=svc(db,config,graph)
    page,ig=connected(service)
    health=service.health(page)
    assert health['connection_state']=='connected' and not health['reconnect_required']
    assert health['access_expires_at'] is None and health['parent_access_expires_at'] is not None and health['renewal_strategy']=='facebook_login_reconnect'
    db.rollback()
    count=len(graph.calls)
    key=uuid4()
    result=account_command(service,page,key=key)
    assert result['connection_state']=='disconnected' and not result['publishing_enabled'] and not result['provider_revocation_confirmed']
    assert account_command(service,page,key=key)==result
    assert service.health(ig)['connection_state']=='disconnected'
    assert len(graph.calls)==count  # Local disconnect cannot silently call provider revocation.
    assert len(list(db.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action=='connection.disconnected'))))==2

def test_rotation_version_ciphertext_and_active_key(db,config,graph):
    service=svc(db,config,graph)
    page,ig=connected(service)
    credential=db.get(SocialCredential,db.get(SocialAccount,page).credential_id)
    old=credential.encrypted_bundle
    db.rollback()
    new=replace(config,active_key_version='v2',encryption_keys={**config.encryption_keys,'v2':Fernet.generate_key().decode()})
    service=svc(db,new,graph)
    result=account_command(service,page,rotate=True)
    assert result['key_version']=='v2' and result['credential_version']==2
    credential=db.get(SocialCredential,db.get(SocialAccount,page).credential_id)
    assert credential.encrypted_bundle!=old
    assert service.cipher.decrypt(credential.id,'facebook_page','v2',credential.encrypted_bundle)['access_token']==PAGE
    db.rollback()
    with pytest.raises(SocialError,match='VERSION_CONFLICT'): account_command(service,page,rotate=True)

def test_account_lease_and_credential_refresh_lease_block_mutations(db,config,graph):
    service=svc(db,config,graph)
    page,ig=connected(service)
    with db.begin(): db.get(SocialAccount,ig).publish_lease_token=uuid4()
    with pytest.raises(SocialError,match='ACCOUNT_BUSY'): account_command(service,page)
    with db.begin():
        db.get(SocialAccount,ig).publish_lease_token=None
        credential=db.get(SocialCredential,db.get(SocialAccount,page).credential_id)
        credential.refresh_lease_token=uuid4()
        credential.refresh_lease_expires_at=datetime.now(timezone.utc)+timedelta(minutes=2)
    with pytest.raises(SocialError,match='CREDENTIAL_BUSY'): account_command(service,page,rotate=True)

def test_parent_revocation_and_expiry_are_truthful(db,config,graph):
    service=svc(db,config,graph)
    page,_=connected(service)
    with db.begin():
        credential=db.get(SocialCredential,db.get(SocialAccount,page).credential_id)
        parent=db.get(SocialCredential,credential.parent_credential_id)
        parent.access_expires_at=datetime.now(timezone.utc)-timedelta(seconds=60)
    assert service.health(page)['connection_state']=='connected'
    assert service.health(page)['parent_grant_reconnect_required'] is True
    db.rollback()
    with db.begin(): db.get(SocialCredential,parent.id).revoked_at=datetime.now(timezone.utc)
    assert service.health(page)['connection_state']=='revoked'

def test_reconnect_same_identity_preserves_account_and_rejects_wrong_identity(db,config,graph):
    service=svc(db,config,graph)
    page,ig=connected(service)
    old=db.get(SocialAccount,page).credential_id
    db.rollback()
    graph.pages.append({'id':'902','name':'Other','access_token':PAGE2,'tasks':['CREATE_CONTENT']})
    started,state=start(service,reconnect=page)
    complete(service,state)
    with pytest.raises(SocialError,match='RECONNECT_IDENTITY_MISMATCH'): select_asset(service,UUID(started['flow_id']),page='902',ig=None)
    result=select_asset(service,UUID(started['flow_id']))
    assert [UUID(a['id']) for a in result['accounts']]==[page,ig]
    assert db.get(SocialCredential,old).revoked_at is not None
    assert db.get(SocialAccount,page).credential_id!=old

def test_pending_grants_are_purged_by_bounded_expiry_maintenance(db,config,graph):
    service=svc(db,config,graph)
    started,state=start(service)
    complete(service,state)
    with db.begin(): db.get(SocialOAuthFlow,UUID(started['flow_id'])).expires_at=datetime.now(timezone.utc)-timedelta(minutes=1)
    assert service.expire_flows()==1
    flow=db.get(SocialOAuthFlow,UUID(started['flow_id']))
    assert flow.status=='expired' and flow.encrypted_pending_grant is None and flow.encrypted_verifier is None

def test_health_selects_only_safe_metadata_never_ciphertext(db,config,graph):
    from sqlalchemy import event
    service=svc(db,config,graph)
    page,_=connected(service)
    sql=[]
    def capture(conn,cursor,statement,params,context,executemany):sql.append(statement)
    event.listen(db.bind,'before_cursor_execute',capture)
    try:
        service.health(page)
    finally:event.remove(db.bind,'before_cursor_execute',capture)
    credentials=[statement for statement in sql if 'FROM social_credentials' in statement]
    assert credentials and all('encrypted_bundle' not in statement for statement in credentials)

def test_stale_disconnect_must_not_revoke_reconnected_grant(db,config,graph):
    service=svc(db,config,graph)
    page,_=connected(service)
    old=service.health(page)
    db.rollback()
    stale=AccountCommand(expected_credential_id=UUID(old['credential_id']),expected_credential_version=old['credential_version'],reason='Stale screen from original grant')
    started,state=start(service,reconnect=page)
    complete(service,state)
    select_asset(service,UUID(started['flow_id']))
    with pytest.raises(SocialError,match='VERSION_CONFLICT'):
        service.account_command(page,ACTOR,BINDING,'POST disconnect/'+str(page),uuid4(),stale,uuid4())

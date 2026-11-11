"""Frozen-v1 regression: preserve known pre-I/O refusal codes/statuses."""
import json
from datetime import datetime,timezone
from uuid import uuid4
import pytest
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from social.connections.models import SocialCredential
from social.connections.service import ConnectionService
from social.connections.verification import SavedGrantVerificationAuthority
from social.models import SocialAccount,SocialAuditEvent
from social.privacy.models import SocialPrivacyReceipt
from social.service import SocialError
from test_connections_support import ACTOR,BINDING
from test_meta_default_process import harness,status,call,saved,graph

@pytest.mark.parametrize('mutant,expected,status_code',[
    ('unpaused','ACCOUNT_MUST_BE_PAUSED',409),
    ('revoked_credential','CREDENTIAL_UNAVAILABLE',409),
    ('legacy_privacy','PRIVACY_STATE_UNAVAILABLE',503),
])
def test_known_pre_io_refusal_retains_original_code_and_status(harness,mutant,expected,status_code):
    h=harness;body=status(h,'facebook');key=uuid4();account=h.ids['facebook']
    with Session(h.engine)as db:
        row=db.get(SocialAccount,account)
        if mutant=='unpaused':row.publishing_enabled=True
        elif mutant=='revoked_credential':
            page=db.get(SocialCredential,row.credential_id)
            db.get(SocialCredential,page.parent_credential_id).revoked_at=datetime.now(timezone.utc)
        else:
            db.execute(text('DELETE FROM social_privacy_ownership'))
            audit=db.scalar(select(SocialAuditEvent.id).limit(1))
            db.add(SocialPrivacyReceipt(app_id='123',kind='deauthorization',digest_version='v1',subject_digest=h.digester.digest('123','701','v1'),event_key='c'*64,request_fingerprint='d'*64,affected={},resolution='fixture_pending',state='ownership_unresolved',audit_id=audit))
        db.commit()
    before=saved(h)
    with Session(h.engine)as db:
        semantic=ConnectionService(db,h.config,verification_authority=SavedGrantVerificationAuthority(h.config))
        with pytest.raises(SocialError)as caught:
            semantic._verify_existing_grant(account,ACTOR,BINDING,f'POST /api/v1/admin/social/accounts/{account}/verify-publishing-access',key,body,uuid4())
    assert (caught.value.code,caught.value.status)==(expected,status_code)
    response=call(h,'facebook',body,key)
    print('REFUSAL_PROJECTION '+json.dumps({'mutant':mutant,'private_code':caught.value.code,'private_status':caught.value.status,'public_status':response.status_code,'public_code':response.json()['detail']['code']}),flush=True)
    assert not graph(h)and saved(h)==before
    assert (response.status_code,response.json()['detail']['code'])==(status_code,expected)

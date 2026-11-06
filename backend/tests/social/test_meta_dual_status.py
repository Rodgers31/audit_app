"""Reachable matching-privacy readiness refusal has original HTTP503."""
import json
from uuid import uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from social.connections.service import ConnectionService
from social.connections.verification import SavedGrantVerificationAuthority
from social.privacy.ownership import OwnershipRecorder
from social.privacy.models import SocialPrivacyReceipt
from social.models import SocialAuditEvent
from social.service import SocialError
from test_connections_support import ACTOR,BINDING
from test_meta_default_process import harness,status,call,saved,graph


def test_matching_privacy_readiness_retains_original_503(harness):
    h=harness;body=status(h,'facebook');key=uuid4();account=h.ids['facebook']
    with Session(h.engine)as db:
        audit=db.scalar(select(SocialAuditEvent.id).limit(1))
        db.add(SocialPrivacyReceipt(app_id='123',kind='deauthorization',digest_version='v1',subject_digest=h.digester.digest('123','701','v1'),event_key='c'*64,request_fingerprint='d'*64,affected={},resolution='fixture_pending',state='ownership_unresolved',audit_id=audit));db.commit()
    before=saved(h)
    with Session(h.engine)as db:
        semantic=ConnectionService(db,h.config,ownership_recorder=OwnershipRecorder(h.config.app_id,h.digester),verification_authority=SavedGrantVerificationAuthority(h.config))
        with pytest.raises(SocialError)as caught:
            semantic._verify_existing_grant(account,ACTOR,BINDING,f'POST /api/v1/admin/social/accounts/{account}/verify-publishing-access',key,body,uuid4())
    assert caught.value.code=='PRIVACY_GRANT_BLOCKED'and caught.value.status==503
    response=call(h,'facebook',body,key)
    print('DUAL_STATUS '+json.dumps({'private':caught.value.code,'private_status':caught.value.status,'public':response.json()['detail']['code'],'public_status':response.status_code}),flush=True)
    assert not graph(h)and saved(h)==before
    assert response.status_code==503 and response.json()['detail']['code']=='PRIVACY_GRANT_BLOCKED',response.text

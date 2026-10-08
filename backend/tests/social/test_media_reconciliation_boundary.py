from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from pydantic import ValidationError
from social.media.reconciliation import ReconcileUpload, WriteQuiescenceReceipt, WriteQuiescenceEvidence
from social.media.models import SocialMediaUpload, SocialMediaBudget
from social.service import SocialError
from test_media_support import ACTOR, media, media_db, intent, png

class ReflectingVerifier:
    def verify(self, scope, receipt):
        return WriteQuiescenceEvidence(scope=scope, receipt=receipt, verified_at=datetime.now(timezone.utc))

@pytest.mark.parametrize('field,value', [('evidence_hash', 'malformed'), ('evidence_hash', True), ('evidence_hash', None), ('receipt_id', 'not-a-uuid'), ('receipt_id', None)])
def test_constructed_invalid_receipt_does_not_settle_writes(media, field, value):
    svc, store = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, grant.asset.id)
        upload.expires_at = svc.now() - timedelta(seconds=1)
    svc.runtime = replace(svc.runtime, write_quiescence_verifier=ReflectingVerifier())
    values = {'receipt_id': uuid4(), 'evidence_hash': 'a' * 64, field: value}
    receipt = WriteQuiescenceReceipt.model_construct(**values)
    body = ReconcileUpload.model_construct(expected_version=1, expected_grant_epoch=1, expected_finalization_epoch=None, receipt=receipt)
    with pytest.raises((ValidationError, SocialError)):
        svc.reconcile(ACTOR, grant.asset.id, body, uuid4())
    with svc.db.begin():
        upload = svc.db.get(SocialMediaUpload, grant.asset.id)
        assert upload.grant_settled_epoch == 0
        assert upload.write_quiescence_receipt_hash is None
        assert svc.db.get(SocialMediaBudget, 'global').bytes_used == 2 * len(png())

@pytest.mark.parametrize('field,value', [('expected_version', True), ('expected_version', 1.0), ('expected_grant_epoch', True), ('expected_grant_epoch', 1.0)])
def test_constructed_wrong_epoch_types_do_not_settle(media, field, value):
    svc, _ = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    svc.runtime = replace(svc.runtime, write_quiescence_verifier=ReflectingVerifier())
    values = {'expected_version': 1, 'expected_grant_epoch': 1, 'expected_finalization_epoch': None, 'receipt': WriteQuiescenceReceipt(receipt_id=uuid4(), evidence_hash='a'*64), field: value}
    body = ReconcileUpload.model_construct(**values)
    with pytest.raises((ValidationError, SocialError)):
        svc.reconcile(ACTOR, grant.asset.id, body, uuid4())
@pytest.mark.parametrize('field', ['upload_version', 'grant_epoch', 'finalization_epoch'])
def test_constructed_invalid_scope_is_refused_even_if_python_equality_matches(media, field):
    svc, store = media
    grant = svc.initiate(ACTOR, uuid4(), intent(), uuid4())
    with svc.db.begin():
        upload=svc.db.get(SocialMediaUpload, grant.asset.id)
        upload.finalization_epoch=1
        upload.finalization_settled=0
        upload.expires_at=svc.now()-timedelta(seconds=1)
    class HostileVerifier:
        def verify(self, scope, receipt):
            forged_scope=scope.model_copy(update={field: float(getattr(scope,field))})
            assert forged_scope == scope
            return WriteQuiescenceEvidence.model_construct(scope=forged_scope, receipt=receipt, verified_at=datetime.now(timezone.utc))
    svc.runtime=replace(svc.runtime,write_quiescence_verifier=HostileVerifier())
    body=ReconcileUpload(expected_version=1,expected_grant_epoch=1,expected_finalization_epoch=1,receipt=WriteQuiescenceReceipt(receipt_id=uuid4(),evidence_hash='a'*64))
    with pytest.raises(SocialError,match='MEDIA_WRITE_QUIESCENCE_UNCONFIRMED'):
        svc.reconcile(ACTOR,grant.asset.id,body,uuid4())

"""Canonical Threads identity boundaries across operator schemas and helpers."""
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from social.adapters.meta_http import remote_id
from social.models import SocialPostTarget, SocialAuditEvent
from social.service import SocialError
from social.threads_recovery import (PublicObservation, PublicProofContext, SettlementDTO,
    ProposePublicProof, RecordExisting, ThreadsRecoveryService)
from test_api_admin import make_client, key
from test_domain_support import ACTOR, db
from test_threads_recovery import pending, observation, REVIEWER


def unresolved(db, owner_size=64):
    target_id = pending(db, owner_id='1'*owner_size)
    target = db.get(SocialPostTarget, target_id)
    target.primary_remote_id, target.remote_refs = None, {}
    db.commit()
    return target_id


def observed(context, size=64, capture='a'):
    return {**observation(context, capture), 'remote_id':'2'*size}


@pytest.mark.parametrize('field', ['external_account_id', 'remote_id'])
@pytest.mark.parametrize('size', [64, 65])
def test_observation_uses_canonical_account_and_post_identity(field, size):
    value = observed({'external_account_id':'1'*64,'caption':'Approved','asset_sha256':[]})
    value[field] = '3'*size
    if size == 64:
        parsed = PublicObservation.model_validate(value)
        assert getattr(parsed, field) == remote_id(value[field])
    else:
        with pytest.raises(ValueError):
            remote_id(value[field])
        with pytest.raises(ValidationError):
            PublicObservation.model_validate(value)


@pytest.mark.parametrize('size', [64, 65])
def test_http_without_retained_id_only_accepts_canonical_publication(db, size):
    target_id = unresolved(db)
    client = make_client(db.bind)
    url = f'/api/v1/admin/social/targets/{target_id}'
    context_response = client.get(url+'/public-proof')
    assert context_response.status_code == 200, context_response.text
    context = context_response.json()
    first = dict(expected_publication_version=context['publication_version'], binding_hash=context['binding_hash'],
        observation=observed(context,size), reason='Compare exact operator identities with the canonical adapter boundary.')
    proof = client.post(url+'/public-proof', json=first, headers=key())
    if size == 65:
        if proof.status_code == 201:
            second = dict(expected_publication_version=context['publication_version'], proof_id=proof.json()['proof_id'],
                observation=observed(context,size,'b'), reason='Independent observation must refuse a noncanonical public identity.')
            result = make_client(db.bind,actor=REVIEWER).post(url+'/record-existing',json=second,headers=key())
            assert result.status_code == 422, result.text
        assert proof.status_code == 422, proof.text
        db.expire_all()
        assert db.get(SocialPostTarget,target_id).state == 'outcome_unknown'
        assert not list(db.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action=='threads.public_proof_proposed')))
        return
    assert proof.status_code == 201, proof.text
    second = dict(expected_publication_version=context['publication_version'], proof_id=proof.json()['proof_id'],
        observation=observed(context,size,'b'), reason='Independent second observation of the exact canonical public identity.')
    result = make_client(db.bind,actor=REVIEWER).post(url+'/record-existing',json=second,headers=key())
    assert result.status_code == 200, result.text
    assert result.json()['remote_id'] == remote_id('2'*64)


@pytest.mark.parametrize('size', [64,65])
def test_context_service_rejects_noncanonical_account_without_checkpoint(db,size):
    target_id = unresolved(db,size)
    if size == 64:
        context = ThreadsRecoveryService(db).context(target_id)
        assert context['external_account_id'] == remote_id('1'*64)
    else:
        with pytest.raises(SocialError,match='PROOF_BINDING_INVALID'):
            ThreadsRecoveryService(db).context(target_id)


@pytest.mark.parametrize('source', ['primary','refs'])
@pytest.mark.parametrize('size', [64,65])
def test_context_service_rejects_noncanonical_retained_post_identity(db,source,size):
    target_id = unresolved(db)
    target = db.get(SocialPostTarget,target_id)
    if source == 'primary':
        target.primary_remote_id='2'*size
    else:
        target.remote_refs={'post_id':'2'*size}
    db.commit()
    if size == 64:
        context=ThreadsRecoveryService(db).context(target_id)
        assert context['known_remote_id'] == (remote_id('2'*64) if source=='primary' else None)
    else:
        with pytest.raises(SocialError,match='PROOF_BINDING_INVALID'):
            ThreadsRecoveryService(db).context(target_id)


@pytest.mark.parametrize('schema,field', [(PublicProofContext,'external_account_id'),(PublicProofContext,'known_remote_id'),(SettlementDTO,'remote_id')])
@pytest.mark.parametrize('size', [64,65])
def test_response_schemas_preserve_canonical_identity(db,schema,field,size):
    target_id=unresolved(db)
    context=ThreadsRecoveryService(db).context(target_id)
    value=context if schema is PublicProofContext else dict(target_id=str(target_id),proof_id=str(uuid4()),
        state='published',remote_id='2'*64,remote_url='https://www.threads.com/@fixture/post/AbCd1',publication_version=2)
    value={**value,field:'3'*size}
    if size == 64:
        assert getattr(schema.model_validate(value),field)==remote_id('3'*64)
    else:
        with pytest.raises(ValidationError):
            schema.model_validate(value)


@pytest.mark.parametrize('operation', ['propose','record_existing','observation'])
@pytest.mark.parametrize('field', ['external_account_id','remote_id'])
def test_constructed_observation_cannot_bypass_command_helpers(db,operation,field):
    target_id=unresolved(db)
    context=ThreadsRecoveryService(db).context(target_id)
    valid=PublicObservation.model_validate(observed(context)).model_dump(mode='python')
    invalid=PublicObservation.model_construct(**{**valid,field:'3'*65})
    svc=ThreadsRecoveryService(db)
    if operation=='observation':
        account,pub,target,payload,snapshot=svc._load(target_id)
        with pytest.raises(ValidationError):
            svc._observation(invalid,account,target,payload)
        return
    if operation=='propose':
        body=ProposePublicProof.model_construct(expected_publication_version=context['publication_version'],
            binding_hash=context['binding_hash'],observation=invalid,reason='Direct constructed-model regression must not admit bad identity.')
    else:
        body=RecordExisting.model_construct(expected_publication_version=context['publication_version'],
            proof_id=uuid4(),observation=invalid,reason='Direct constructed-model regression must not admit bad identity.')
    db.rollback()
    with pytest.raises(ValidationError):
        svc.command(actor=ACTOR,route='identity-'+operation,key=uuid4(),body={},request_id=uuid4(),
            action=lambda:getattr(svc,operation)(target_id,body))
    assert db.get(SocialPostTarget,target_id).state=='outcome_unknown'


def test_constructed_64_digit_models_remain_usable_through_real_helpers(db):
    target_id=unresolved(db)
    svc=ThreadsRecoveryService(db)
    context=svc.context(target_id)
    first=PublicObservation.model_construct(**PublicObservation.model_validate(observed(context)).model_dump(mode='python'))
    account,pub,target,payload,snapshot=svc._load(target_id)
    svc._observation(first,account,target,payload)
    body=ProposePublicProof.model_construct(expected_publication_version=context['publication_version'],
        binding_hash=context['binding_hash'],observation=first,reason='Constructed exact64 identities still satisfy canonical operator admission.')
    db.rollback()
    _,proof=svc.command(actor=ACTOR,route='constructed-propose',key=uuid4(),body={},request_id=uuid4(),
        action=lambda:svc.propose(target_id,body))
    second=PublicObservation.model_construct(**PublicObservation.model_validate(observed(context,64,'b')).model_dump(mode='python'))
    body=RecordExisting.model_construct(expected_publication_version=context['publication_version'],
        proof_id=UUID(proof['proof_id']),observation=second,reason='Independent constructed exact64 public observation remains admissible.')
    _,settled=svc.command(actor=REVIEWER,route='constructed-admit',key=uuid4(),body={},request_id=uuid4(),
        action=lambda:svc.record_existing(target_id,body))
    assert settled['state']=='published' and settled['remote_id']==remote_id('2'*64)

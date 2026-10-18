"""Raw permalink bytes must be canonical before urlsplit can normalize them."""
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from social.models import SocialAuditEvent, SocialPostTarget
from social.threads_recovery import PublicObservation, ProposePublicProof, RecordExisting, ThreadsRecoveryService
from test_api_admin import make_client, key
from test_domain_support import ACTOR, db
from test_threads_recovery import pending, observation, REVIEWER

CANONICAL = 'https://www.threads.com/@fixture/post/abc'
CHARACTERS = ['\x00', '\t', '\n', '\r', '\x1f', ' ', '\x7f', '\x85', '\xa0']


def with_character(character, position):
    if position == 'leading':
        return character+CANONICAL
    if position == 'embedded':
        return CANONICAL.replace('threads', 'thre'+character+'ads')
    return CANONICAL+character


@pytest.mark.parametrize('character', CHARACTERS)
@pytest.mark.parametrize('position', ['leading', 'embedded', 'trailing'])
def test_raw_helper_refuses_whitespace_and_controls(character, position):
    with pytest.raises(ValueError):
        PublicObservation.permalink(with_character(character,position))


@pytest.mark.parametrize('character', CHARACTERS)
@pytest.mark.parametrize('position', ['leading', 'embedded', 'trailing'])
def test_observation_schema_refuses_whitespace_and_controls(character,position):
    value=observation({'external_account_id':'101','caption':'Verified','asset_sha256':[]})
    value['remote_url']=with_character(character,position)
    with pytest.raises(ValidationError):
        PublicObservation.model_validate(value)


@pytest.mark.parametrize('host', ['threads.com','www.threads.com','threads.net','www.threads.net'])
def test_exact_canonical_urls_remain_byte_identical(host):
    url='https://'+host+'/@fixture/post/abc'
    assert PublicObservation.permalink(url)==url
    value=observation({'external_account_id':'101','caption':'Verified','asset_sha256':[]})
    assert PublicObservation.model_validate({**value,'remote_url':url}).remote_url==url


@pytest.mark.parametrize('character,position', [('\n','embedded'), ('\x00','leading'), ('\r','trailing'),
    ('\t','embedded'), (' ','leading'), ('\x7f','trailing')])
def test_operator_api_never_records_normalized_malformed_permalink(db,character,position):
    target_id=pending(db)
    client=make_client(db.bind)
    url=f'/api/v1/admin/social/targets/{target_id}'
    context=client.get(url+'/public-proof').json()
    malformed=with_character(character,position)
    first={**observation(context),'remote_url':malformed}
    body=dict(expected_publication_version=context['publication_version'],binding_hash=context['binding_hash'],
        observation=first,reason='A malformed raw permalink must not become public proof through normalization.')
    proof=client.post(url+'/public-proof',json=body,headers=key())
    if proof.status_code==201:
        second={**observation(context,'b'),'remote_url':malformed}
        body=dict(expected_publication_version=context['publication_version'],proof_id=proof.json()['proof_id'],
            observation=second,reason='Independent observation must still reject the malformed raw permalink.')
        result=make_client(db.bind,actor=REVIEWER).post(url+'/record-existing',json=body,headers=key())
        assert result.status_code==422, result.text
    assert proof.status_code==422,proof.text
    db.expire_all()
    target=db.get(SocialPostTarget,target_id)
    assert target.state=='outcome_unknown' and target.remote_url is None
    assert not list(db.scalars(select(SocialAuditEvent).where(SocialAuditEvent.action.in_(
        ('threads.public_proof_proposed','threads.public_proof_admitted')))))


@pytest.mark.parametrize('operation', ['propose','record_existing','observation'])
@pytest.mark.parametrize('malformed', ['https://www.thre\nads.com/@fixture/post/abc', '\x00'+CANONICAL])
def test_constructed_observations_cannot_bypass_raw_url_guard(db,operation,malformed):
    target_id=pending(db)
    svc=ThreadsRecoveryService(db)
    context=svc.context(target_id)
    valid=PublicObservation.model_validate(observation(context)).model_dump(mode='python')
    invalid=PublicObservation.model_construct(**{**valid,'remote_url':malformed})
    if operation=='observation':
        account,pub,target,payload,snapshot=svc._load(target_id)
        with pytest.raises(ValidationError):
            svc._observation(invalid,account,target,payload)
        return
    if operation=='propose':
        body=ProposePublicProof.model_construct(expected_publication_version=context['publication_version'],
            binding_hash=context['binding_hash'],observation=invalid,reason='Constructed raw URL still requires canonical validation.')
    else:
        body=RecordExisting.model_construct(expected_publication_version=context['publication_version'],proof_id=uuid4(),
            observation=invalid,reason='Constructed raw URL still requires canonical validation.')
    db.rollback()
    with pytest.raises(ValidationError):
        svc.command(actor=ACTOR,route='raw-url-'+operation,key=uuid4(),body={},request_id=uuid4(),
            action=lambda:getattr(svc,operation)(target_id,body))
    assert db.get(SocialPostTarget,target_id).state=='outcome_unknown'


def test_raw_rejection_happens_before_url_parsing(monkeypatch):
    def parsing_must_not_run(value):
        raise AssertionError('urlsplit ran before the raw canonical guard')
    monkeypatch.setattr('social.threads_recovery.urlsplit',parsing_must_not_run)
    with pytest.raises(ValueError):
        PublicObservation.permalink('\x00'+CANONICAL)

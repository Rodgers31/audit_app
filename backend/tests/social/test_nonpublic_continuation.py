"""Binding controls: a nonpublic receipt can never clear a public ambiguity."""
from copy import deepcopy
from uuid import uuid4

import pytest
from social.contracts import canonical_hash
from social.worker.continuation import nonpublic_continuation_matches


def example():
    account, operation = uuid4(), uuid4()
    checkpoint = {'adapter':'facebook_reels-v1','video_id':'701','phase':'publish_ready'}
    original = {'operation_id':operation,'operation':'upload','dispatch_started_at':None,
        'request_fingerprint':'a'*64,'receipt':{'intent':{'publication_capable':False,'mutating':True,
            'safe_replay_class':'requires_reconciliation'}}}
    proof = {'kind':'provider_nonpublic_checkpoint','account_id':str(account),'operation_id':str(operation),
        'content_hash':'b'*64,'request_fingerprint':'a'*64,'checkpoint_hash':canonical_hash(checkpoint)}
    arguments = dict(account_id=account,payload_hash='b'*64,checkpoint=checkpoint,outcome='confirmed_success')
    return proof,original,arguments


def test_exact_nonpublic_receipt_can_continue():
    proof,original,arguments = example()
    assert nonpublic_continuation_matches(proof,original,**arguments)


@pytest.mark.parametrize('change', ['public','dispatched','delete','wrong_operation','wrong_account','wrong_payload',
    'wrong_fingerprint','wrong_checkpoint','processing','malformed','no_intent','false_boolean','integer_boolean'])
def test_untrusted_or_public_continuation_cannot_release_hold(change):
    proof,original,arguments = example()
    if change=='public': original['receipt']['intent']['publication_capable']=True
    elif change=='dispatched': original['dispatch_started_at']='some-time'
    elif change=='delete': original['operation']='delete'
    elif change=='wrong_operation': proof['operation_id']=str(uuid4())
    elif change=='wrong_account': proof['account_id']=str(uuid4())
    elif change=='wrong_payload': proof['content_hash']='c'*64
    elif change=='wrong_fingerprint': proof['request_fingerprint']='c'*64
    elif change=='wrong_checkpoint': arguments['checkpoint']={'video_id':'999'}
    elif change=='processing': arguments['outcome']='processing'
    elif change=='malformed': proof=[]
    elif change=='no_intent': original['receipt']={}
    elif change=='false_boolean': original['receipt']['intent']['mutating']=False
    elif change=='integer_boolean': original['receipt']['intent']['publication_capable']=0
    assert not nonpublic_continuation_matches(proof,original,**arguments)

"""Actual PostgreSQL17 worker -> independent operator -> retained outcome."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, text, func, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import FlushError
from social.contracts import ResolvedPostPayload, canonical_hash
from social.adapters.common import caption
from social.meta_reels_recovery import MetaReelsRecoveryService, RecordExistingReel, ProposeReelProof, ADMITTED, CONTRACT
from social.models import SocialAccount, SocialAuditEvent, SocialCommandReceipt, SocialControls, SocialMediaAsset, SocialPostTarget, SocialPublication, SocialPublishAttempt
from social.service import SocialError
from test_meta_reels_postgres import engine, config, inspected_video, prepare_reel, due, step
from test_meta_reels_delivery import ReelGraph
from test_meta_reels_recovery import FIRST, SECOND, observation, invoke, proposed, seed
import test_native_meta_adapters as native


def held(engine,config,monkeypatch,rendered,platform='facebook'):
    graph=ReelGraph() if platform=='facebook' else native.Graph()
    if platform=='instagram':graph.overrides[('POST','/v26.0/801/media')]={'id':'501'}
    storage,target_id,_=prepare_reel(engine,config,graph,monkeypatch,rendered,platform=platform)
    if platform=='instagram':
        with Session(engine) as db:value=ResolvedPostPayload.model_validate(db.get(SocialPostTarget,target_id).resolved_payload)
        graph.overrides[('GET','/v26.0/601')]={'id':'601','owner':{'id':'801'},'media_type':'VIDEO','media_product_type':'REELS','permalink':'https://www.instagram.com/reel/fixture/','shortcode':'fixture','caption':caption(value)}
    for _ in range(14):
        due(engine,target_id);step(engine,config,storage,graph)
        with Session(engine) as db:
            target=db.get(SocialPostTarget,target_id)
            if target.state=='outcome_unknown':break
    assert target.state=='outcome_unknown'
    return storage,target_id,graph


@pytest.mark.parametrize('platform',['facebook','instagram'])
def test_real_worker_exact_render_then_two_admin_public_recovery_and_replay(engine,config,monkeypatch,inspected_video,platform):
    storage,target_id,graph=held(engine,config,monkeypatch,inspected_video,platform)
    wire_before=len(graph.calls)
    with Session(engine) as db:
        target=db.get(SocialPostTarget,target_id)
        retained=(target.checkpoint,target.remote_refs,target.submit_count,target.resolved_payload)
        attempts=[(str(a.operation_id),a.receipt) for a in db.scalars(select(SocialPublishAttempt).order_by(SocialPublishAttempt.sequence))]
        # Past public outcome can be recorded with all new publishing paused.
        db.get(SocialControls,1).publishing_enabled=False
        db.get(SocialAccount,target.account_id).publishing_enabled=False;db.commit()
        context,first,proposal=proposed(db,target_id)
        body=RecordExistingReel(expected_publication_version=context['publication_version'],proof_id=UUID(proposal['proof_id']),observation=observation(context),reason='Independent inert full Reel/public/owner packet review')
        key=uuid4();result=invoke(db,SECOND,body,lambda svc:svc.record_existing(target_id,body),route='record',key=key)
    # New session models restart/readback after an ambiguous HTTP response.
    with Session(engine) as db:
        replay=invoke(db,SECOND,body,lambda svc:svc.record_existing(target_id,body),route='record',key=key)
        target=db.get(SocialPostTarget,target_id);account=db.get(SocialAccount,target.account_id)
        assert replay==result and target.state=='published' and target.visibility_state=='public' and target.confirmation_kind==CONTRACT
        assert (target.checkpoint,target.remote_refs,target.submit_count,target.resolved_payload)==retained
        assert [(str(a.operation_id),a.receipt) for a in db.scalars(select(SocialPublishAttempt).order_by(SocialPublishAttempt.sequence))]==attempts
        assert account.hold_reason is None and not account.publishing_enabled
        assert db.scalar(select(func.count()).select_from(SocialAuditEvent).where(SocialAuditEvent.action==ADMITTED))==1
    due(engine,target_id);step(engine,config,storage,graph)
    assert len(graph.calls)==wire_before


@pytest.mark.parametrize('fault',['suppress_admission_audit','alter_target'])
def test_actual_trigger_write_failure_rolls_back_receipt_outcome_and_hold(engine,fault):
    with Session(engine) as db:
        target_id=seed(db);context,first,proposal=proposed(db,target_id)
    body=RecordExistingReel(expected_publication_version=1,proof_id=UUID(proposal['proof_id']),observation=observation(context),reason='Synthetic persistence failure control')
    if fault=='suppress_admission_audit':
        table='social_audit_events';timing='INSERT';function="BEGIN IF NEW.action='meta.reels_public_proof_admitted' THEN RETURN NULL; END IF; RETURN NEW; END"
    else:
        table='social_post_targets';timing='UPDATE';function="BEGIN IF NEW.state='published' THEN NEW.primary_remote_id='999'; END IF; RETURN NEW; END"
    with engine.begin() as conn:
        conn.execute(text('CREATE FUNCTION meta723_fault() RETURNS trigger LANGUAGE plpgsql AS $$'+function+'$$'))
        conn.execute(text('CREATE TRIGGER meta723_fault BEFORE '+timing+' ON '+table+' FOR EACH ROW EXECUTE FUNCTION meta723_fault()'))
    try:
        with Session(engine) as db,pytest.raises((SocialError,FlushError)) as caught:
            invoke(db,SECOND,body,lambda svc:svc.record_existing(target_id,body),route='record')
        if isinstance(caught.value,SocialError):assert caught.value.code=='RECOVERY_PERSISTENCE_FAILED'
        with Session(engine) as db:
            target=db.get(SocialPostTarget,target_id)
            assert target.state=='outcome_unknown' and db.get(SocialAccount,target.account_id).hold_reason=='RECONCILIATION_REQUIRED:'+str(target.id)
            assert db.scalar(select(func.count()).select_from(SocialAuditEvent).where(SocialAuditEvent.action==ADMITTED))==0
            assert db.scalar(select(func.count()).select_from(SocialCommandReceipt).where(SocialCommandReceipt.route_key=='record'))==0
    finally:
        with engine.begin() as conn:
            conn.execute(text('DROP TRIGGER meta723_fault ON '+table));conn.execute(text('DROP FUNCTION meta723_fault()'))


def test_concurrent_independent_admissions_have_one_durable_outcome(engine):
    with Session(engine) as db:target_id=seed(db);context,first,proposal=proposed(db,target_id)
    body=RecordExistingReel(expected_publication_version=1,proof_id=UUID(proposal['proof_id']),observation=observation(context),reason='Concurrent inert proof admission')
    key=uuid4()
    def execute(_):
        with Session(engine) as db:return invoke(db,SECOND,body,lambda svc:svc.record_existing(target_id,body),route='record',key=key)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(execute,range(2)))
    assert results[0]==results[1]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(SocialCommandReceipt).where(SocialCommandReceipt.route_key=='record'))==1
        assert db.scalar(select(func.count()).select_from(SocialAuditEvent).where(SocialAuditEvent.action==ADMITTED))==1


@pytest.mark.parametrize('problem',['wrong_product','coherent_payload_tamper','no_public_permit','unfinished','lease','duplicate_remote','stale_version'])
def test_actual_repository_rejects_authority_and_identity_mismatch(engine,problem):
    with Session(engine) as db:
        target_id=seed(db);context,first,proposal=proposed(db,target_id);target=db.get(SocialPostTarget,target_id)
        if problem=='wrong_product':db.execute(update(SocialAccount).where(SocialAccount.id==target.account_id).values(api_product='unsupported_legacy'))
        elif problem=='coherent_payload_tamper':
            payload={**target.resolved_payload,'text':'Coherently hashed but never approved copy'};payload['content_hash']=canonical_hash({k:v for k,v in payload.items() if k!='content_hash'})
            db.execute(update(SocialPostTarget).where(SocialPostTarget.id==target.id).values(resolved_payload=payload,payload_hash=payload['content_hash'],checkpoint={**target.checkpoint,'content_hash':payload['content_hash']}))
        elif problem=='no_public_permit':
            db.execute(update(SocialPublishAttempt).where(SocialPublishAttempt.target_id==target.id).values(dispatch_started_at=None))
        elif problem=='unfinished':db.scalar(select(SocialPublishAttempt)).completed_at=None
        elif problem=='lease':target.lease_owner='retained-worker';target.lease_token=uuid4();target.lease_expires_at=datetime.now(timezone.utc)-timedelta(hours=1)
        elif problem=='duplicate_remote':seed(db,account_product='legacy_reels_fixture')
        elif problem=='stale_version':db.get(SocialPublication,target.publication_id).version+=1
        db.commit()
        body=RecordExistingReel(expected_publication_version=1,proof_id=UUID(proposal['proof_id']),observation=observation(context),reason='Rejected inert authority mismatch')
        with pytest.raises(SocialError):invoke(db,SECOND,body,lambda svc:svc.record_existing(target_id,body),route='record')
        assert db.get(SocialPostTarget,target_id).state=='outcome_unknown'
        assert db.scalar(select(func.count()).select_from(SocialAuditEvent).where(SocialAuditEvent.action==ADMITTED))==0

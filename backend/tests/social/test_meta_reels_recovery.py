"""Meta human authority fixtures: no live provider/public-custody claim."""
from datetime import datetime, timedelta, timezone
import hashlib
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func
from social.adapters.facebook_reels import FacebookReels
from social.contracts import InspectedAsset, canonical_hash
from social.meta_reels_recovery import MetaReelsRecoveryService, ReelObservation, ProposeReelProof, RecordExistingReel, ADMITTED, CONTRACT
from social.models import SocialAccount, SocialAuditEvent, SocialControls, SocialMediaAsset, SocialPost, SocialPostRevision, SocialPostTarget, SocialPublication, SocialPublishAttempt
from social.service import SocialError
from test_domain_support import db
import test_native_meta_adapters as native
FIRST,SECOND=uuid4(),uuid4()


def seed(db,platform='facebook',*,account_product=None):
    now=datetime.now(timezone.utc)
    if db.get(SocialControls,1) is None:db.add(SocialControls(id=1,publishing_enabled=False))
    owner,asset_id,post_id,revision_id,publication_id,target_id=[uuid4() for _ in range(6)]
    data=b'owned-original-fixture-not-live-media';digest=hashlib.sha256(data).hexdigest()
    asset=SocialMediaAsset(id=asset_id,storage_provider='fixture',bucket='private',storage_key=str(asset_id),original_filename='approved.mp4',state='ready',mime_type='video/mp4',sha256=digest,byte_size=len(data),width=720,height=1280,duration_ms=15000,frame_rate=24,codec_metadata={},created_by=FIRST)
    value=native.payload(platform,'reel',account_id=owner,assets=(InspectedAsset(asset_id=asset_id,sha256=digest,mime_type='video/mp4',byte_size=len(data),width=720,height=1280,duration_ms=15000,frame_rate_milli_fps=24000),),evidence_hash=canonical_hash({'references':[]}))
    account=SocialAccount(id=owner,platform=platform,api_product=account_product or value.api_product,external_account_id=value.external_account_id,connection_method='facebook_login',connection_state='connected',display_name='Owned fixture',publishing_enabled=False,granted_scopes=list(native.SCOPES),capability_snapshot={},hold_reason='RECONCILIATION_REQUIRED:'+str(target_id))
    document={'schema_version':1,'master':{'text':value.text,'link':None,'hashtags':list(value.hashtags),'media':[{'asset_id':str(asset_id),'alt_text':None,'caption_asset_id':None}]},'targets':[{'account_id':str(owner),'format':'reel','overrides':{}}]}
    evidence={'references':[]};revision_hash=canonical_hash({'document':document,'evidence_snapshot':evidence})
    post=SocialPost(id=post_id,title='Owned recovery fixture',content_type='announcement',editorial_state='approved');db.add_all([asset,account,post]);db.flush()
    revision=SocialPostRevision(id=revision_id,post_id=post_id,revision_no=1,document=document,evidence_snapshot=evidence,content_hash=revision_hash)
    db.add(revision);db.flush();post.current_revision_id=revision_id
    publication=SocialPublication(id=publication_id,post_id=post_id,revision_id=revision_id,approved_by=FIRST,approved_at=now,approved_hash=revision_hash,dispatch_requested_at=now,start_deadline=now+timedelta(hours=1),retry_deadline=now+timedelta(hours=24))
    if platform=='facebook':
        from types import SimpleNamespace
        checkpoint=FacebookReels(SimpleNamespace()).state(value,'publication_accepted',video_id='701',offset=len(data),upload_count=1);refs={'video_id':'701'}
    else:
        checkpoint={'schema_version':1,'adapter':'instagram_facebook_login-v1','account_id':str(owner),'external_account_id':value.external_account_id,'content_hash':value.content_hash,'phase':'media_created','container_id':'501','media_id':'601','poll_count':1};refs={'container_id':'501','media_id':'601'}
    target=SocialPostTarget(id=target_id,publication_id=publication_id,account_id=owner,resolved_payload=value.model_dump(mode='json'),payload_hash=value.content_hash,capability_version='social-v1',state='outcome_unknown',submit_count=1,checkpoint=checkpoint,remote_refs=refs,visibility_state='unknown')
    db.add(publication);db.flush();db.add(target);db.flush()
    db.add(SocialPublishAttempt(id=uuid4(),target_id=target_id,sequence=1,operation_id=uuid4(),operation='publish',request_fingerprint='f'*64,lease_epoch=1,dispatch_started_at=now,outcome='ambiguous',completed_at=now,receipt={'intent':{'publication_capable':True,'mutating':True,'safe_replay_class':'requires_reconciliation'}}));db.commit()
    return target_id


def observation(context,**changes):
    value=dict(platform=context['platform'],api_product=context['api_product'],method='anonymous_browser',visibility='public',observed_at=datetime.now(timezone.utc)-timedelta(seconds=2),capture_sha256=hashlib.sha256(uuid4().bytes).hexdigest(),custody_reference=uuid4(),identity_capture_sha256=hashlib.sha256(uuid4().bytes).hexdigest(),identity_custody_reference=uuid4(),external_account_id=context['external_account_id'],remote_id=context['known_remote_id'] or '601',remote_url='https://www.facebook.com/reel/701' if context['platform']=='facebook' else 'https://www.instagram.com/reel/fixture/',text=context['caption'],asset_sha256=context['asset_sha256'],identity_basis='Inert independently retained owner identity packet, not actual provider evidence.',media_comparison='Inert complete scene and audio comparison packet, not live public evidence.')
    value.update(changes);return ReelObservation.model_validate(value)


def invoke(db,actor,body,action,*,route='proof',key=None):
    if db.in_transaction():db.rollback()
    svc=MetaReelsRecoveryService(db)
    return svc.command(actor=actor,route=route,key=key or uuid4(),body=body.model_dump(mode='json'),request_id=uuid4(),action=lambda:action(svc))[1]


def proposed(db,target_id):
    context=MetaReelsRecoveryService(db).context(target_id)
    body=ProposeReelProof(expected_publication_version=context['publication_version'],binding_hash=context['binding_hash'],observation=observation(context),reason='Synthetic independent public capture proposal')
    proof=invoke(db,FIRST,body,lambda svc:svc.propose(target_id,body));return context,body,proof


@pytest.mark.parametrize('platform',['facebook','instagram'])
def test_exact_two_admin_settlement_is_audited_idempotent_and_never_sends(db,platform):
    target_id=seed(db,platform);context,first,proof=proposed(db,target_id)
    body=RecordExistingReel(expected_publication_version=context['publication_version'],proof_id=UUID(proof['proof_id']),observation=observation(context),reason='Separate synthetic complete public and owner inspection')
    key=uuid4();result=invoke(db,SECOND,body,lambda svc:svc.record_existing(target_id,body),route='record',key=key)
    replay=invoke(db,SECOND,body,lambda svc:svc.record_existing(target_id,body),route='record',key=key)
    assert replay==result and result['state']=='published'
    target=db.get(SocialPostTarget,target_id);account=db.get(SocialAccount,target.account_id)
    assert target.confirmation_kind==CONTRACT and target.visibility_state=='public' and target.submit_count==1
    assert target.checkpoint['phase'] in {'publication_accepted','media_created'} and target.remote_refs
    assert account.hold_reason is None and account.publishing_enabled is False
    assert db.scalar(select(func.count()).select_from(SocialPublishAttempt))==1
    assert db.scalar(select(func.count()).select_from(SocialAuditEvent).where(SocialAuditEvent.action==ADMITTED))==1


def test_self_admission_and_reused_packets_are_refused(db):
    target_id=seed(db);context,first,proof=proposed(db,target_id)
    body=RecordExistingReel(expected_publication_version=1,proof_id=UUID(proof['proof_id']),observation=observation(context),reason='Synthetic separate inspection')
    with pytest.raises(SocialError,match='INDEPENDENT_REVIEW_REQUIRED'):invoke(db,FIRST,body,lambda svc:svc.record_existing(target_id,body))
    for change in ({'capture_sha256':first.observation.capture_sha256},{'identity_capture_sha256':first.observation.capture_sha256},{'custody_reference':first.observation.identity_custody_reference}):
        bad=body.model_copy(update={'observation':observation(context,**change)})
        with pytest.raises(SocialError,match='PROOF_REPLAY'):invoke(db,SECOND,bad,lambda svc:svc.record_existing(target_id,bad))
    assert db.get(SocialPostTarget,target_id).state=='outcome_unknown'


@pytest.mark.parametrize('change',[{'remote_id':'999','remote_url':'https://www.facebook.com/reel/999'},{'external_account_id':'999'},{'asset_sha256':'0'*64},{'text':'Wrong copy'},{'platform':'instagram','api_product':'instagram_graph_facebook_login','remote_url':'https://www.instagram.com/reel/fixture/'},{'observed_at':datetime.now(timezone.utc)+timedelta(days=1)},{'observed_at':datetime.now(timezone.utc)-timedelta(hours=1)}])
def test_wrong_owner_content_product_source_or_freshness_cannot_propose(db,change):
    target_id=seed(db);context=MetaReelsRecoveryService(db).context(target_id)
    body=ProposeReelProof(expected_publication_version=1,binding_hash=context['binding_hash'],observation=observation(context,**change),reason='Synthetic rejected observation')
    with pytest.raises(SocialError):invoke(db,FIRST,body,lambda svc:svc.propose(target_id,body))
    assert db.get(SocialPostTarget,target_id).state=='outcome_unknown'


@pytest.mark.parametrize('change',[{'visibility':'private'},{'visibility':'unknown'},{'method':'authenticated_browser'},{'remote_url':'https://attacker.example/reel/701'},{'remote_url':'https://www.facebook.com/reel/701?secret=bad'},{'remote_url':'https://www.facebook.com/reel/999'},{'remote_url':'https://www.facebook.com/posts/701'},{'observed_at':datetime.now()},{'asset_sha256':True}])
def test_bad_observation_shapes_are_not_public_proof(db,change):
    target_id=seed(db);context=MetaReelsRecoveryService(db).context(target_id)
    with pytest.raises(ValueError):observation(context,**change)


def test_changed_binding_requires_fresh_proposal(db):
    target_id=seed(db);context,first,proof=proposed(db,target_id)
    target=db.get(SocialPostTarget,target_id);target.lease_epoch+=1;db.commit()
    body=RecordExistingReel(expected_publication_version=1,proof_id=UUID(proof['proof_id']),observation=observation(context),reason='Stale target capture')
    with pytest.raises(SocialError,match='PROOF_EXPIRED'):invoke(db,SECOND,body,lambda svc:svc.record_existing(target_id,body))
    assert db.get(SocialPostTarget,target_id).state=='outcome_unknown'


@pytest.mark.parametrize('ownership',['target_expired','account_expired','unfinished'])
def test_retained_worker_ownership_refuses_takeover(db,ownership):
    target_id=seed(db);target=db.get(SocialPostTarget,target_id);account=db.get(SocialAccount,target.account_id);past=datetime.now(timezone.utc)-timedelta(hours=1)
    if ownership=='target_expired':target.lease_token=uuid4();target.lease_owner='old-worker';target.lease_expires_at=past
    elif ownership=='account_expired':account.publish_lease_target_id=target.id;account.publish_lease_token=uuid4();account.publish_lease_expires_at=past
    else:db.scalar(select(SocialPublishAttempt)).completed_at=None
    db.commit()
    with pytest.raises(SocialError,match='RECOVERY_BUSY'):MetaReelsRecoveryService(db).context(target_id)


def test_direct_bypass_and_boolean_version_are_rejected(db):
    target_id=seed(db);context=MetaReelsRecoveryService(db).context(target_id)
    body=ProposeReelProof(expected_publication_version=1,binding_hash=context['binding_hash'],observation=observation(context),reason='Synthetic proposal')
    with pytest.raises(SocialError,match='OPERATOR_COMMAND_REQUIRED'):MetaReelsRecoveryService(db).propose(target_id,body)
    bad=body.model_copy(update={'expected_publication_version':True})
    with pytest.raises(ValueError):invoke(db,FIRST,bad,lambda svc:svc.propose(target_id,bad))


@pytest.mark.parametrize('corruption',['missing_ig_container','changed_frame_rate'])
def test_corrupt_retained_product_custody_cannot_form_operator_context(db,corruption):
    from sqlalchemy import update
    target_id=seed(db,'instagram');target=db.get(SocialPostTarget,target_id)
    if corruption=='missing_ig_container':
        db.execute(update(SocialPostTarget).where(SocialPostTarget.id==target_id).values(checkpoint={**target.checkpoint,'container_id':None}))
    else:
        asset_id=UUID(target.resolved_payload['assets'][0]['asset_id'])
        db.execute(update(SocialMediaAsset).where(SocialMediaAsset.id==asset_id).values(frame_rate=30))
    db.commit()
    with pytest.raises(SocialError,match='PROOF_BINDING_INVALID'):MetaReelsRecoveryService(db).context(target_id)


@pytest.mark.parametrize('corruption',['first_expired','first_wrong_source'])
def test_stored_first_observation_is_revalidated_at_admission(db,corruption):
    from sqlalchemy import update
    target_id=seed(db);context,first,proof=proposed(db,target_id)
    event=db.get(SocialAuditEvent,UUID(proof['proof_id']));details={**event.details,'observation':{**event.details['observation']}}
    if corruption=='first_expired':details['observation']['observed_at']=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    else:details['observation']['asset_sha256']='0'*64
    db.execute(update(SocialAuditEvent).where(SocialAuditEvent.id==event.id).values(details=details));db.commit()
    body=RecordExistingReel(expected_publication_version=1,proof_id=event.id,observation=observation(context),reason='Rejected corrupted retained first capture')
    with pytest.raises(SocialError):invoke(db,SECOND,body,lambda svc:svc.record_existing(target_id,body))


@pytest.mark.parametrize('platform',['facebook','instagram'])
def test_completed_operator_contract_exposes_bounded_reels_with_manual_confirmation(platform):
    from test_meta_reels_delivery import reel
    value=reel(platform);provider=native.adapter(value,native.Graph());caps=native.capabilities(provider,value)
    assert 'reel' in caps.supported_formats
    assert caps.feature_states['reel_operator_confirmation']=='supported'
    assert caps.feature_states['reel_automatic_confirmation']=='unsupported'
    assert provider.validate(value,caps).valid

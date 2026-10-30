"""Executed regressions for older PR731 review-body findings, no provider access."""
from datetime import timedelta
import httpx
import pytest
from social.adapters.meta_http import MetaHTTPFailure
import test_native_meta_adapters as native
from test_meta_reels_delivery import reel, adapter, credential, video_media
from test_meta_reels_postgres import inspected_video
from test_domain_support import db


@pytest.mark.parametrize('platform',['facebook','instagram'])
@pytest.mark.parametrize('alt_text',['A supplied video description',''])
def test_reels_refuse_unsupported_alt_text_instead_of_dropping_approved_content(platform,alt_text):
    value=reel(platform)
    value=native.rehash(value.model_copy(update={'assets':(value.assets[0].model_copy(update={'alt_text':alt_text}),)}))
    provider=adapter(value,native.Graph())
    result=provider.validate(value,native.capabilities(provider,value))
    assert not result.valid
    assert 'UNSUPPORTED_REEL_ALT_TEXT' in {error.code for error in result.errors}


@pytest.mark.asyncio
@pytest.mark.parametrize('method',['GET','POST'])
@pytest.mark.parametrize('content',[b'',b'upstream throttle',b'[]',b'{}',b'x'*65537],ids=['empty','nonjson','array','missingerror','oversized'])
async def test_429_deadline_survives_uninterpretable_or_oversized_body_without_proving_mutation_rejected(method,content):
    calls=[]
    async def handler(request):
        calls.append(request)
        return httpx.Response(429,headers={'retry-after':'3600'},content=content)
    provider=adapter(reel(),handler)
    try:
        with pytest.raises(MetaHTTPFailure) as caught:
            await provider.http.request(method,'901',token=native.TOKEN,edge='video_reels' if method=='POST' else None)
        error=caught.value
        assert error.ambiguous is True and error.retry_safe is False
        assert error.http_status==429 and error.next_action_at==native.NOW+timedelta(hours=1)
        assert len(calls)==1
    finally:await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('format',['reel','image'])
@pytest.mark.parametrize('phase',[None,'container_ready'])
async def test_instagram_quota_throttle_stays_processing_and_honors_deadline(format,phase):
    value=reel('instagram') if format=='reel' else native.payload('instagram','image')
    graph=native.Graph()
    graph.overrides[('GET','/v26.0/801/content_publishing_limit')]=lambda request:httpx.Response(429,headers={'retry-after':'3600'},json={'error':{'code':4}})
    provider=adapter(value,graph)
    checkpoint={} if phase is None else provider._state(value,phase,container_id='501')
    try:
        result=await provider.execute(value,provider.next_operation(value,checkpoint),credential(value),video_media())
        assert result.outcome=='processing' and result.next_action_at==native.NOW+timedelta(hours=1)
        assert result.http_status==429 and result.error_code=='QUOTA_LOOKUP_UNAVAILABLE'
        assert result.checkpoint==checkpoint and len(graph.calls)==1 and graph.calls[0][0]=='GET'
    finally:await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('publication_capable',[False,True],ids=['create-session','publish-finish'])
async def test_ambiguous_reel_429_retains_deadline_through_actual_worker_result(publication_capable):
    from social.adapters.facebook_reels import FacebookReels
    from social.worker.runner import SocialWorker
    value=reel()
    calls=[]
    async def handler(request):
        calls.append(request)
        return httpx.Response(429,headers={'retry-after':'3600'},content=b'')
    provider=adapter(value,handler)
    checkpoint=FacebookReels(provider).state(value,'publish_ready',video_id='701',offset=value.assets[0].byte_size,upload_count=1) if publication_capable else {}
    plan=provider.next_operation(value,checkpoint)
    class CaptureSave:
        _delay=staticmethod(SocialWorker._delay)
        async def _save(self,*args,**kwargs):self.saved=kwargs
    capture=CaptureSave()
    try:
        assert plan.publication_capable is publication_capable
        result=await provider.execute(value,plan,credential(value),video_media())
        assert result.outcome=='ambiguous' and not result.retry_safe
        await SocialWorker._result(capture,None,None,{'database_now':native.NOW},plan,result,0)
        assert capture.saved['state']=='reconciling' and capture.saved['next_action']=='reconcile'
        assert capture.saved['delay']==3600 and len(calls)==1
    finally:await provider.close()


@pytest.mark.parametrize('platform',['facebook','instagram'])
def test_actual_studio_mp4_attachment_enters_reels_validation_without_generated_image_alt(inspected_video,platform):
    from uuid import UUID
    from social.contracts import InspectedAsset
    media=inspected_video.document['master']['media'][0]
    info=inspected_video.inspection
    asset=InspectedAsset(asset_id=UUID(media['asset_id']),sha256=info.sha256,mime_type=info.mime_type,byte_size=info.byte_size,
        width=info.width,height=info.height,duration_ms=info.duration_ms,frame_rate_milli_fps=int(info.frame_rate*1000),alt_text=media['alt_text'])
    value=native.payload(platform,'reel',assets=(asset,),text=inspected_video.document['master']['text'])
    provider=adapter(value,native.Graph())
    result=provider.validate(value,native.capabilities(provider,value))
    assert result.valid,result.errors
    assert media['alt_text'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('result_delay,policy_delay,expected',[(3600,1200,3600),(1200,3600,3600),(None,None,30)])
async def test_policy_reconciliation_honors_both_future_deadlines_without_resend(result_delay,policy_delay,expected):
    from types import SimpleNamespace
    from uuid import uuid4
    from social.contracts import OperationPlan,OperationResult
    from social.worker.runner import SocialWorker
    worker=object.__new__(SocialWorker);saved=[]
    async def save(*args,**kwargs):saved.append(kwargs)
    async def db(fn,*args):return SimpleNamespace(action='reconcile',reason='RECONCILIATION_REQUIRED',next_action_at=native.NOW+timedelta(seconds=policy_delay) if policy_delay else None)
    worker._save=save;worker.db=db;worker.repository=SimpleNamespace(retry_policy=object())
    result=OperationResult(outcome='definite_failure',next_action_at=native.NOW+timedelta(seconds=result_delay) if result_delay else None)
    plan=OperationPlan(operation_id=uuid4(),operation='poll',publication_capable=False,safe_replay_class='read_only',checkpoint={})
    await worker._result(None,None,{'database_now':native.NOW},plan,result,0)
    assert len(saved)==1 and saved[0]['state']=='reconciling' and saved[0]['next_action']=='reconcile'
    assert saved[0]['delay']==expected


@pytest.mark.parametrize('platform',['facebook','instagram'])
def test_explicitly_removed_meta_reel_alt_does_not_restore_library_default(db,platform):
    from uuid import UUID
    from social.models import SocialPostTarget,SocialAccount,SocialMediaAsset,SocialPublication,SocialPostRevision
    from social.contracts import PostDocument
    from social.validation import validate_document
    from test_meta_reels_recovery import seed
    target_id=seed(db,platform);target=db.get(SocialPostTarget,target_id);account=db.get(SocialAccount,target.account_id)
    pub=db.get(SocialPublication,target.publication_id);revision=db.get(SocialPostRevision,pub.revision_id)
    asset=db.get(SocialMediaAsset,UUID(target.resolved_payload['assets'][0]['asset_id']))
    asset.default_alt_text='Library default video description'
    value=reel(platform,account_id=account.id);provider=adapter(value,native.Graph())
    account.publishing_enabled=True;account.hold_reason=None;account.capability_snapshot=native.capabilities(provider,value).model_dump(mode='json');db.commit()
    # A newly prepared candidate supplies its required on-site destination;
    # the retained legacy revision remains unchanged as recovery history.
    document=PostDocument.model_validate(revision.document)
    document=document.model_copy(update={'master':document.master.model_copy(update={'link':'https://www.auditgava.com/audits'})})
    assert document.master.media[0].alt_text is None
    result=validate_document(db,document,revision.evidence_snapshot,{(account.platform,account.api_product):provider})
    assert result.valid,result


@pytest.mark.parametrize('platform',['facebook','instagram'])
@pytest.mark.parametrize('reference_alt,expected',[(None,'Library image description'),('','')])
def test_image_library_default_and_intentional_empty_alt_are_preserved(db,platform,reference_alt,expected):
    from uuid import uuid4
    from social.models import SocialPostTarget,SocialAccount,SocialMediaAsset
    from social.contracts import PostDocument
    from social.validation import validate_document
    from test_meta_reels_recovery import seed,FIRST
    target_id=seed(db,platform);target=db.get(SocialPostTarget,target_id);account=db.get(SocialAccount,target.account_id)
    value=native.payload(platform,'image',account_id=account.id);item=value.assets[0]
    asset=SocialMediaAsset(id=item.asset_id,storage_provider='fixture',bucket='private',storage_key=str(uuid4()),original_filename='image.jpg',state='ready',mime_type=item.mime_type,sha256=item.sha256,byte_size=item.byte_size,width=item.width,height=item.height,default_alt_text='Library image description',codec_metadata={},created_by=FIRST)
    db.add(asset)
    provider=adapter(value,native.Graph());account.publishing_enabled=True;account.hold_reason=None;account.capability_snapshot=native.capabilities(provider,value).model_dump(mode='json');db.commit()
    document=PostDocument.model_validate({'master':{'text':'Image caption','link':'https://www.auditgava.com/audits','media':[{'asset_id':str(asset.id),'alt_text':reference_alt}]},'targets':[{'account_id':str(account.id),'format':'image'}]})
    result=validate_document(db,document,{'references':[]},{(account.platform,account.api_product):provider})
    assert result.valid,result
    assert result.targets[0].resolved_preview.assets[0].alt_text==expected

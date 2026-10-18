"""Bounded native Reels transport regressions; no real provider requests."""
import hashlib
from urllib.parse import parse_qs

import pytest

from social.contracts import InspectedAsset
from social.adapters import FacebookPageAdapter, InstagramFacebookLoginAdapter, MetaAdapterConfig
import test_native_meta_adapters as native

VIDEO = b'owned-inspected-mp4-fixture'


def adapter(value,graph):
    return native.adapter(value,graph)


def credential(value):
    return native.credential(value)


def reel(platform='facebook', **changes):
    asset = InspectedAsset(asset_id=native.uuid4(), sha256=hashlib.sha256(VIDEO).hexdigest(),
        mime_type='video/mp4', byte_size=len(VIDEO), width=720, height=1280,
        duration_ms=15000, frame_rate_milli_fps=24000)
    return native.payload(platform, 'reel', assets=(asset,), **changes)


@pytest.mark.parametrize('platform', ['facebook', 'instagram'])
def test_inspected_reel_is_a_distinct_supported_format(platform):
    value = reel(platform); provider = adapter(value, native.Graph())
    result = provider.validate(value, native.capabilities(provider, value))
    assert result.valid, result.errors
    assert 'video' not in provider.formats


@pytest.mark.asyncio
async def test_facebook_starts_nonpublic_session_instead_of_feed_publication():
    value = reel(); graph = native.Graph(); provider = adapter(value, graph)
    plan = provider.next_operation(value, {})
    assert plan.operation == 'create_container' and not plan.publication_capable
    await provider.close()


@pytest.mark.asyncio
async def test_instagram_uses_approved_video_url_and_reels_product():
    value = reel('instagram'); graph = native.Graph(); media = native.Media()
    graph.overrides[('POST', '/v26.0/801/media')] = {'id': '501'}
    provider = adapter(value, graph)
    plan = await native.until_operation(provider, value, graph, media, 'create_container')
    result = await provider.execute(value, plan, credential(value), media)
    assert result.outcome == 'confirmed_success'
    form = parse_qs(graph.calls[-1][2].decode())
    assert form['video_url'] == [native.FETCH_URL] and form['media_type'] == ['REELS']
    assert 'image_url' not in form and 'alt_text' not in form
    await provider.close()

from dataclasses import replace
import json

import httpx
from social.adapters.common import caption


class ReelGraph:
    def __init__(self):
        self.calls = []
        self.offset = 0
        self.published = False
        self.overrides = {}
        self.timeout = None
        self.partial = None

    async def __call__(self, request):
        body = await request.aread()
        key = (request.method, request.url.host, request.url.path)
        self.calls.append((key, dict(request.headers), body))
        if key in self.overrides:
            value = self.overrides[key]
            return value(request) if callable(value) else httpx.Response(200, json=value)
        if request.url.host == 'rupload.facebook.com':
            assert key == ('POST', 'rupload.facebook.com', '/video-upload/v26.0/701')
            assert request.headers['authorization'] == 'OAuth ' + native.TOKEN
            assert request.headers['file_size'] == str(len(VIDEO))
            assert int(request.headers['offset']) == self.offset
            assert body == VIDEO[self.offset:]
            self.offset = self.partial if self.partial is not None else len(VIDEO)
            self.partial = None
            value = {'success': True}
        else:
            assert request.headers['authorization'] == 'Bearer ' + native.TOKEN
            assert request.url.host == 'graph.facebook.com'
            form = parse_qs(body.decode())
            if key == ('POST', 'graph.facebook.com', '/v26.0/901/video_reels'):
                if form['upload_phase'] == ['start']:
                    value = {'video_id': '701', 'upload_url': 'https://rupload.facebook.com/video-upload/v26.0/701'}
                else:
                    assert self.offset == len(VIDEO)
                    assert form['video_id'] == ['701'] and form['video_state'] == ['PUBLISHED']
                    self.published = True
                    value = {'success': True}
            elif key == ('GET', 'graph.facebook.com', '/v26.0/701'):
                value = self.status()
            else:
                raise AssertionError(key)
        if self.timeout == key:
            self.timeout = None
            raise httpx.ReadTimeout('inert partial upload fixture', request=request)
        return httpx.Response(200, json=value)

    def status(self):
        return {'id': '701', 'status': {'video_status': 'ready' if self.published else 'processing',
            'uploading_phase': {'status': 'complete' if self.offset == len(VIDEO) else 'in_progress', 'bytes_transfered': self.offset},
            'processing_phase': {'status': 'complete' if self.published else 'not_started'},
            'publishing_phase': {'status': 'complete' if self.published else 'not_started'}}}


async def advance(value, graph, checkpoint=None, count=1, *, media=None):
    saved = checkpoint or {}
    for _ in range(count):
        provider = adapter(value, graph)
        plan = provider.next_operation(value, saved)
        result = await provider.execute(value, plan, credential(value), media or video_media())
        saved = json.loads(json.dumps(result.checkpoint))
        await provider.close()
    return result


def video_media():
    media = native.Media(); media.body = VIDEO
    return media


@pytest.mark.asyncio
async def test_facebook_bytes_uploaded_and_publication_accepted_are_not_public_proof():
    value = reel(); graph = ReelGraph(); checkpoint = {}
    phases = ['session_created', 'uploaded', 'publish_ready', 'publication_accepted', 'publication_accepted']
    for phase in phases:
        result = await advance(value, graph, checkpoint)
        assert result.checkpoint['phase'] == phase
        assert result.primary_remote_id is None and result.visibility_state == 'unknown'
        checkpoint = result.checkpoint
    assert result.outcome == 'processing' and result.error_code == 'PUBLIC_VISIBILITY_UNCONFIRMED'
    assert graph.published
    assert [key[0] for key, _, _ in graph.calls] == ['POST','POST','GET','POST','GET']
    assert native.TOKEN not in json.dumps(checkpoint) and 'https://' not in json.dumps(checkpoint)


@pytest.mark.asyncio
async def test_partial_upload_restarts_from_authoritative_offset_with_exact_original_bytes():
    value = reel(); graph = ReelGraph()
    started = await advance(value, graph)
    graph.partial = 7
    graph.timeout = ('POST', 'rupload.facebook.com', '/video-upload/v26.0/701')
    failed = await advance(value, graph, started.checkpoint)
    assert failed.outcome == 'ambiguous'
    provider = adapter(value, graph)
    recovered = await provider.reconcile(value, failed.checkpoint, {'operation': 'upload'}, credential(value), video_media())
    assert recovered.outcome == 'still_processing'
    assert recovered.result.checkpoint['offset'] == 7
    resumed = await advance(value, graph, recovered.result.checkpoint)
    assert resumed.checkpoint['phase'] == 'uploaded'
    uploads = [call for call in graph.calls if call[0][1] == 'rupload.facebook.com']
    assert uploads[0][2] == VIDEO and uploads[1][2] == VIDEO[7:]
    assert uploads[1][1]['offset'] == '7'
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('lost_operation,steps', [('create_container',0),('upload',1),('publish',3)])
async def test_receipt_loss_reconciliation_never_blindly_replays_mutation(lost_operation, steps):
    value = reel(); graph = ReelGraph(); saved = {}
    if steps:
        saved = (await advance(value, graph, count=steps)).checkpoint
    accepted = await advance(value, graph, saved)
    provider = adapter(value, graph)
    recovered = await provider.reconcile(value, saved, {'operation': lost_operation}, credential(value), video_media())
    mutations = len([c for c in graph.calls if c[0][0] == 'POST'])
    if lost_operation == 'create_container':
        assert recovered.outcome == 'unknown'
    elif lost_operation == 'upload':
        assert recovered.result.checkpoint['phase'] == 'publish_ready'
        assert recovered.result.checkpoint['offset'] == len(VIDEO)
    else:
        assert accepted.checkpoint['phase'] == 'publication_accepted'
        assert recovered.result.checkpoint['phase'] == 'publication_uncertain'
        assert provider.next_operation(value, recovered.result.checkpoint).operation == 'poll'
    assert len([c for c in graph.calls if c[0][0] == 'POST']) == mutations
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [b'wrong', VIDEO[:-1]])
async def test_facebook_changed_bytes_refuse_before_rupload(body):
    value = reel(); graph = ReelGraph(); media = video_media(); media.body = body
    saved = (await advance(value, graph)).checkpoint
    result = await advance(value, graph, saved, media=media)
    assert result.outcome == 'definite_failure' and result.error_code == 'INSPECTED_MEDIA_CHANGED'
    assert len(graph.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('url', ['https://attacker.example/701', 'http://rupload.facebook.com/video-upload/701',
    'https://rupload.facebook.com/video-upload/v26.0/999', 'https://rupload.facebook.com/video-upload/v26.0/701?token=bad'])
async def test_untrusted_provider_upload_url_never_receives_bytes_or_credentials(url):
    value = reel(); graph = ReelGraph()
    graph.overrides[('POST','graph.facebook.com','/v26.0/901/video_reels')] = {'video_id':'701','upload_url':url}
    result = await advance(value, graph)
    assert result.outcome == 'ambiguous' and result.checkpoint['phase'] == 'creation_uncertain'
    assert len(graph.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [None, {}, [], 'bad', {'id':'999'}, {'id':'701','status':[]},
    {'id':'701','status':{'uploading_phase':{'status':'complete'}}}])
async def test_malformed_or_changed_remote_status_never_authorizes_finish(bad):
    value = reel(); graph = ReelGraph(); saved = (await advance(value, graph, count=2)).checkpoint
    graph.overrides[('GET','graph.facebook.com','/v26.0/701')] = bad
    result = await advance(value, graph, saved)
    assert result.outcome in {'ambiguous','processing'}
    assert result.error_code in {'REEL_STATUS_PROOF_INVALID','REEL_STATUS_UNAVAILABLE'}
    assert not graph.published


@pytest.mark.asyncio
@pytest.mark.parametrize('offset', [True, -1, 999999999, 0.5, '7'])
async def test_hostile_resume_offsets_are_held(offset):
    value = reel(); graph = ReelGraph(); saved = (await advance(value, graph)).checkpoint
    graph.partial = 7; graph.timeout = ('POST','rupload.facebook.com','/video-upload/v26.0/701')
    failed = await advance(value, graph, saved)
    bad = graph.status(); bad['status']['uploading_phase']['bytes_transfered'] = offset
    graph.overrides[('GET','graph.facebook.com','/v26.0/701')] = bad
    result = await advance(value, graph, failed.checkpoint)
    assert result.outcome == 'ambiguous' and not graph.published


@pytest.mark.parametrize('changes', [{'mime_type':'image/jpeg'}, {'byte_size':50_000_001}, {'duration_ms':14999},
    {'duration_ms':45001}, {'width':320}, {'height':720}, {'frame_rate_milli_fps':23999},
    {'frame_rate_milli_fps':60001}, {'duration_ms':None}, {'frame_rate_milli_fps':None}])
@pytest.mark.parametrize('platform', ['facebook','instagram'])
def test_reel_bounds_fail_closed(platform, changes):
    value = reel(platform)
    value = native.rehash(value.model_copy(update={'assets':(value.assets[0].model_copy(update=changes),)}))
    provider = adapter(value, native.Graph())
    assert not provider.validate(value, native.capabilities(provider,value)).valid


@pytest.mark.asyncio
@pytest.mark.parametrize('status,code,expected', [(429,4,'RATE_LIMITED'), (403,200,'PERMISSION_DENIED'),
    (401,190,'TOKEN_REVOKED'), (503,2,'PROVIDER_OUTCOME_UNCERTAIN')])
async def test_reel_http_errors_preserve_classification_and_no_wire_retry(status,code,expected):
    value = reel(); graph = ReelGraph()
    graph.overrides[('POST','graph.facebook.com','/v26.0/901/video_reels')] = lambda request: httpx.Response(status,
        headers={'retry-after':'120'}, json={'error':{'code':code}})
    result = await advance(value, graph)
    assert result.error_code == expected and len(graph.calls) == 1
    assert result.outcome == ('ambiguous' if status == 503 else 'definite_failure')


@pytest.mark.asyncio
async def test_instagram_reel_readback_is_identity_proof_without_public_visibility_claim():
    value = reel('instagram'); graph = native.Graph(); media = video_media(); provider = adapter(value,graph)
    graph.overrides[('POST','/v26.0/801/media')] = {'id':'501'}
    graph.overrides[('GET','/v26.0/601')] = {'id':'601','owner':{'id':'801'},'media_type':'VIDEO',
        'media_product_type':'REELS','permalink':'https://www.instagram.com/reel/fixture/',
        'shortcode':'fixture','caption':caption(value)}
    saved = {}
    for _ in range(6):
        plan = provider.next_operation(value,saved)
        result = await provider.execute(value,plan,credential(value),media)
        saved = json.loads(json.dumps(result.checkpoint))
    assert result.outcome == 'processing' and result.error_code == 'PUBLIC_VISIBILITY_UNCONFIRMED'
    assert result.visibility_state == 'unknown' and result.primary_remote_id is None
    for _ in range(5):
        result = await provider.execute(value,provider.next_operation(value,saved),credential(value),media)
        saved = result.checkpoint
    assert result.outcome == 'ambiguous' and result.error_code == 'PUBLICATION_VERIFICATION_REQUIRED'
    assert sum(method=='POST' for method,_,_ in graph.calls) == 2
    await provider.close()

@pytest.mark.parametrize('platform',['facebook','instagram'])
@pytest.mark.parametrize('size',[True,0,-1,float('nan'),float('inf')])
def test_reel_direct_validation_rejects_untrusted_numeric_shapes(platform,size):
    value = reel(platform)
    value = value.model_copy(update={'assets':(value.assets[0].model_copy(update={'byte_size':size}),)})
    if type(size) is not float:
        value = native.rehash(value)
    # Keep bad values executable even though canonical hashes rightly refuse NaN.
    provider = adapter(value,native.Graph())
    try:
        result = provider.validate(value,native.capabilities(provider,value))
    except (ValueError,TypeError):
        return
    assert not result.valid


@pytest.mark.asyncio
async def test_repeated_lost_upload_receipts_cannot_reset_the_durable_upload_budget():
    value = reel(); graph = ReelGraph(); saved = (await advance(value,graph)).checkpoint
    for index in range(6):
        provider = adapter(value,graph)
        plan = provider.next_operation(value,saved)
        if plan.operation != 'upload':
            await provider.close()
            break
        graph.partial = index+1
        result = await provider.execute(value,plan,credential(value),video_media())
        assert result.outcome == 'confirmed_success'
        # Deliberately lose the response checkpoint and retain only the intent.
        recovered = await provider.reconcile(value,saved,{'operation':'upload',
            'operation_id':str(plan.operation_id),'request_fingerprint':'a'*64},credential(value),video_media())
        if recovered.result: saved = recovered.result.checkpoint
        await provider.close()
    assert sum(key[1]=='rupload.facebook.com' for key,_,_ in graph.calls) <= 5
    assert saved['upload_count'] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize('platform',['facebook','instagram'])
async def test_reels_status_rate_limit_preserves_authoritative_retry_after(platform):
    value = reel(platform)
    if platform=='facebook':
        graph = ReelGraph(); saved = (await advance(value,graph,count=2)).checkpoint
        key = ('GET','graph.facebook.com','/v26.0/701')
    else:
        graph = native.Graph(); graph.overrides[('POST','/v26.0/801/media')] = {'id':'501'}
        provider = adapter(value,graph); saved = {}
        for _ in range(2):
            result = await provider.execute(value,provider.next_operation(value,saved),credential(value),video_media())
            saved = result.checkpoint
        await provider.close(); key = ('GET','/v26.0/501')
    graph.overrides[key] = lambda request: httpx.Response(429,headers={'retry-after':'3600'},json={'error':{'code':4}})
    provider = adapter(value,graph)
    result = await provider.execute(value,provider.next_operation(value,saved),credential(value),video_media())
    assert result.outcome=='processing' and result.next_action_at >= native.NOW + native.timedelta(seconds=3600)
    assert result.http_status==429
    await provider.close()


@pytest.mark.parametrize('platform',['facebook','instagram'])
def test_default_native_gates_still_refuse_reels_before_activation(platform):
    value = reel(platform)
    kind = FacebookPageAdapter if platform=='facebook' else InstagramFacebookLoginAdapter
    provider = kind(MetaAdapterConfig('v26.0'),transport=httpx.MockTransport(native.Graph()))
    caps = native.capabilities(provider,value)
    assert not caps.adapter_available and caps.feature_states['publishing']=='restricted'
    assert not provider.validate(value,caps).valid
    account = dict(platform=value.platform,api_product=value.api_product,connection_state='connected',
        granted_scopes=native.SCOPES,capability_snapshot=caps.model_dump(mode='json'))
    assert not provider.validate_mutation_admission(value,account).valid

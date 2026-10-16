"""Sanitized Threads provider contracts; transport state survives adapter restart."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import pytest

from social.adapters.threads import ThreadsAdapter, ThreadsAdapterConfig
from social.contracts import InspectedAsset, ResolvedPostPayload, canonical_hash
from social.native_admission import NativeCapabilityAdmission
from social.worker.materials import ProviderFetchURL, WorkerCredentialMaterial

NOW = datetime(2026,10,16,12,tzinfo=timezone.utc)


def payload(format='text', text='Reviewed public source', **changes):
    count=2 if format=='carousel' else 0 if format=='text' else 1
    values=dict(account_id=uuid4(),platform='threads',api_product='threads',external_account_id='101',
        format=format,text=text,evidence_hash='1'*64,content_hash='0'*64,
        assets=tuple(InspectedAsset(asset_id=uuid4(),sha256=hashlib.sha256(b'fixture').hexdigest(),
            mime_type='video/mp4' if format=='video' else 'image/jpeg',byte_size=7,width=1080,height=1080,
            duration_ms=5000 if format=='video' else None,frame_rate_milli_fps=30000 if format=='video' else None,
            alt_text='An inspected chart') for _ in range(count)))
    values.update(changes)
    result=ResolvedPostPayload(**values)
    return result.model_copy(update={'content_hash':canonical_hash(result.model_dump(mode='json',exclude={'content_hash'}))})


def adapter(graph,**changes):
    return ThreadsAdapter(ThreadsAdapterConfig(enabled=True,operational_gates_verified=True,
        media_uploads_enabled=True,**changes),transport=httpx.MockTransport(graph),now=lambda:NOW)


def caps(provider,p):
    return provider.capabilities(dict(platform='threads',api_product='threads',connection_state='connected',
        granted_scopes=provider.scopes,capability_snapshot={'eligible':True}))


def material(provider,p):
    return WorkerCredentialMaterial(p.account_id,uuid4(),1,'threads','threads',p.external_account_id,
        p.external_account_id,'fixture-threads-token',provider.scopes,NOW+timedelta(days=1),None,
        NativeCapabilityAdmission.from_snapshot(caps(provider,p)))


class Media:
    async def provider_fetch_url(self,asset,minimum_ttl_seconds):
        return ProviderFetchURL('https://media.example/final.jpg?fixture=redacted',NOW+timedelta(seconds=300),asset.asset_id,asset.sha256)


class Graph:
    def __init__(self):
        self.calls=[]; self.text=''; self.kind='TEXT_POST'; self.ids=200; self.status='FINISHED'; self.override=None
    async def __call__(self,request):
        self.calls.append((request.method,request.url.path))
        assert request.url.host=='graph.threads.com'
        assert request.headers['authorization']=='Bearer fixture-threads-token'
        if self.override:
            return self.override(request)
        path=request.url.path
        if path.endswith('/threads_publishing_limit'):
            return httpx.Response(200,json={'data':[{'quota_usage':0,'config':{'quota_total':250,'quota_duration':86400}}]})
        if path.endswith('/threads'):
            data=parse_qs((await request.aread()).decode())
            assert data.get('auto_publish_text') != ['true']
            self.text=data.get('text',[self.text])[0]
            self.kind={'TEXT':'TEXT_POST','IMAGE':'IMAGE','VIDEO':'VIDEO','CAROUSEL':'CAROUSEL_ALBUM'}[data['media_type'][0]]
            self.ids+=1
            return httpx.Response(200,json={'id':str(self.ids)})
        if path.endswith('/threads_publish'):
            self.status='PUBLISHED'
            return httpx.Response(200,json={'id':'999'})
        if path.endswith('/999'):
            return httpx.Response(200,json={'id':'999','owner':{'id':'101'},'username':'audit_fixture','shortcode':'fixture',
                'permalink':'https://www.threads.com/@audit_fixture/post/fixture','text':self.text,
                'media_type':self.kind,'media_product_type':'THREADS','is_quote_post':False})
        return httpx.Response(200,json={'id':path.rsplit('/',1)[1],'status':self.status})


def run(awaitable):
    return asyncio.run(awaitable)


@pytest.mark.parametrize('format',['text','image','carousel','video'])
def test_frozen_steps_survive_every_adapter_restart(format):
    async def scenario():
        graph,p,checkpoint=Graph(),payload(format),{}
        for _ in range(12):
            provider=adapter(graph)
            assert provider.validate(p,caps(provider,p)).valid
            result=await provider.execute(p,provider.next_operation(p,checkpoint),material(provider,p),Media())
            await provider.close()
            assert result.outcome in {'confirmed_success','processing'},result
            checkpoint=json.loads(json.dumps(result.checkpoint))
            if result.confirmation_kind=='threads_owned_post_read':
                assert result.primary_remote_id=='999'
                break
        else:
            pytest.fail('Provider never confirmed the retained owned post')
        assert len([c for c in graph.calls if c[1].endswith('/threads_publish')])==1
        provider=adapter(graph)
        recovery=await provider.reconcile(p,checkpoint,{'operation':'publish'},material(provider,p),Media())
        assert recovery.outcome=='still_processing'
        assert recovery.result.visibility_state=='unknown'
        await provider.close()
    run(scenario())


def test_emoji_bytes_are_counted_before_provider_call():
    p,graph=payload(text='😀'*126),Graph()
    provider=adapter(graph)
    assert not provider.validate(p,caps(provider,p)).valid
    run(provider.close())
    assert graph.calls==[]


@pytest.mark.parametrize('status',['FINISHED','PUBLISHED','ERROR','EXPIRED'])
def test_lost_publish_response_never_authorizes_republication(status):
    async def scenario():
        graph,p=Graph(),payload()
        provider=adapter(graph)
        checkpoint={}
        while True:
            plan=provider.next_operation(p,checkpoint)
            if plan.operation=='publish': break
            checkpoint=(await provider.execute(p,plan,material(provider,p),Media())).checkpoint
        graph.status=status
        recovery=await provider.reconcile(p,checkpoint,{'operation':'publish'},material(provider,p),Media())
        assert recovery.outcome=='unknown'
        assert recovery.absence_proof is None
        assert all(not path.endswith('/threads_publish') for _,path in graph.calls)
        await provider.close()
    run(scenario())


@pytest.mark.parametrize('quota',[None,True,-1,'0',{},[],250])
def test_quota_missing_malformed_or_exhausted_never_creates_container(quota):
    async def scenario():
        graph,p=Graph(),payload()
        graph.override=lambda req:httpx.Response(200,json={'data':[{'quota_usage':quota,'config':{'quota_total':250,'quota_duration':86400}}]})
        provider=adapter(graph)
        result=await provider.execute(p,provider.next_operation(p,{}),material(provider,p),Media())
        assert result.outcome in {'ambiguous','definite_failure'}
        assert len(graph.calls)==1
        await provider.close()
    run(scenario())


def test_cross_target_checkpoint_and_expired_credentials_never_send():
    async def scenario():
        graph,p=Graph(),payload()
        provider=adapter(graph)
        result=await provider.execute(p,provider.next_operation(p,{}),replace(material(provider,p),access_expires_at=NOW),Media())
        assert result.error_code=='TOKEN_EXPIRED'
        assert graph.calls==[]
        checkpoint=provider._state(payload(),'quota_checked')
        with pytest.raises(ValueError): provider.next_operation(p,checkpoint)
        await provider.close()
    run(scenario())


def test_authenticated_permalink_never_certifies_private_profile_as_public():
    async def scenario():
        p,graph=payload(),Graph()
        provider=adapter(graph)
        state=provider._checkpoint(p,provider._state(p,'post_created',container_id='201',post_id='999'))
        graph.text=p.text
        result=await provider._post(p,state,material(provider,p))
        assert result.visibility_state=='unknown'
        assert result.error_code=='PUBLIC_VISIBILITY_UNVERIFIED'
        assert result.outcome=='processing'
        await provider.close()
    run(scenario())


@pytest.mark.parametrize('phase',['quota_checked','publish_ready'])
def test_expired_data_access_blocks_every_threads_mutation(phase):
    async def scenario():
        graph,p=Graph(),payload()
        provider=adapter(graph)
        checkpoint=provider._state(p,phase,container_id='201') if phase=='publish_ready' else provider._state(p,phase)
        plan=provider.next_operation(p,checkpoint)
        result=await provider.execute(p,plan,replace(material(provider,p),data_access_expires_at=NOW-timedelta(seconds=1)),Media())
        assert result.error_code=='TOKEN_EXPIRED'
        assert graph.calls==[]
        await provider.close()
    run(scenario())


@pytest.mark.parametrize('header,seconds,safe', [('1000000',1000000,True),
    ('Wed, 21 Oct 2026 12:00:00 GMT',432000,True),('invalid',None,False),('0',None,False),(None,None,False)])
def test_rate_limit_never_retries_before_exact_provider_delay(header,seconds,safe):
    async def exercise():
        p,graph=payload(),Graph()
        headers={'Retry-After':header} if header is not None else {}
        graph.override=lambda request:httpx.Response(429,headers=headers,json={'error':{'code':4}})
        provider=adapter(graph)
        try:
            result=await provider.execute(p,provider.next_operation(p,{}),material(provider,p),Media())
            assert result.error_code=='RATE_LIMITED'
            assert result.retry_safe is safe
            assert result.next_action_at==(NOW+timedelta(seconds=seconds) if seconds is not None else None)
            assert len(graph.calls)==1
        finally:
            await provider.close()
    run(exercise())

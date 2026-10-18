"""Owned PostgreSQL17: exact inspected render -> approval -> durable worker.

Requires META_REELS_TEST_DATABASE_URL for the named disposable loopback fixture.
No production DB URL, existing fixture server or credentials are accepted.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from social.contracts import ApproveCommand, PublishCommand
from social.media.config import MediaConfig
from social.media.inspection import LocalInspector
from social.models import SOCIAL_TABLES, SocialPost, SocialAccount, SocialControls, SocialMediaAsset, SocialPostTarget, SocialPublishAttempt
from social.studio.contracts import Composition
from social.studio.runner import run_job
from test_connections_support import config, FakeGraph, start, complete, select_asset, PAGE
from social.connections.service import ConnectionService
from social.connections.provider import MetaProvider
from test_domain_support import ACTOR, call, draft_body
from test_media_support import FakeStorage
from test_native_worker_postgres import registration as real_registration, step as real_step, due
from test_queue_postgres import repository
from test_meta_reels_delivery import ReelGraph
import test_meta_reels_delivery as reels_fixture
import test_native_meta_adapters as native


registration = real_registration
step = real_step


@pytest.fixture
def engine():
    raw = os.environ.get('META_REELS_TEST_DATABASE_URL')
    if not raw:
        pytest.skip('Set an owned Meta Reels loopback fixture DSN')
    url = make_url(raw)
    if ('?' in raw or url.drivername!='postgresql+psycopg2' or url.host!='127.0.0.1' or url.port!=62323
            or url.database!='social_worker_test' or url.username!='reels723' or url.query):
        raise ValueError('Use only the exact owned Meta Reels loopback fixture')
    engine = create_engine(url.set(query={'hostaddr':'127.0.0.1'}), pool_size=2, max_overflow=0)
    with engine.connect() as conn:
        if conn.execute(text('select current_user')).scalar()!='reels723' or not conn.execute(text('show server_version_num')).scalar().startswith('17'):
            raise ValueError('Owned PostgreSQL17 identity is required')
    SocialPost.metadata.create_all(engine, tables=SOCIAL_TABLES)
    names = ','.join('"'+table.name+'"' for table in SOCIAL_TABLES)
    with engine.begin() as conn:
        conn.execute(text('TRUNCATE '+names+' RESTART IDENTITY CASCADE'))
        # The ownership helper creates its own baseline guard/history once.
        if conn.execute(text("select to_regclass('social_worker_runtime_ownership')")).scalar():
            conn.execute(text('TRUNCATE social_worker_runtime_ownership,social_worker_runtime_history'))
    yield engine
    with engine.begin() as conn:
        conn.execute(text('TRUNCATE '+names+' RESTART IDENTITY CASCADE'))
    engine.dispose()


@pytest.fixture(scope='module')
def inspected_video(tmp_path_factory):
    # Execute the actual Studio render, review, and attachment bridge once.
    import shutil
    from types import SimpleNamespace
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from test_studio import source, enqueue
    from social.studio.models import RenderJob
    from social.studio.runtime import StudioRuntime, verified_bytes
    from social.studio.contracts import Approval
    from social.studio.service import StudioService
    from social.contracts import PatchPost
    root = tmp_path_factory.mktemp('meta-reels-render')
    root.chmod(0o700)
    runtime = StudioRuntime(True, root.resolve(), shutil.which('ffmpeg'), shutil.which('ffprobe')).validate()
    isolated = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread':False})
    SocialPost.metadata.create_all(isolated, tables=[t for t in SocialPost.metadata.sorted_tables if t.name.startswith('social_')])
    with Session(isolated,expire_on_commit=False) as db:
        post = source(db); queued = enqueue(db,runtime,post,'video')
        job_id = UUID(queued['id'])
        assert run_job(sessionmaker(bind=isolated),runtime,job_id) == 'ready'
        db.expire_all(); job = db.get(RenderJob,job_id)
        approval = Approval(expected_version=job.version,sha256=job.sha256,
            review_attestation={'facts_checked':True,'sources_checked':True})
        reviewed = call(db,approval,lambda svc:StudioService(svc,runtime).approve(job_id,approval))[1]
        data = verified_bytes(runtime,job)
        asset = SocialMediaAsset(id=uuid4(),storage_provider='fixture',bucket='private',storage_key=str(uuid4()),
            original_filename='reviewed.mp4',state='ready',created_by=ACTOR,**job.inspection)
        db.add(asset); db.commit()
        body = PatchPost(expected_version=post['version'])
        attached = call(db,body,lambda svc:StudioService(svc,runtime).attach(job_id,asset.id,body.expected_version))[1]
        assert attached['document']['master']['media'][0]['asset_id'] == str(asset.id)
        assert reviewed['approved_sha256'] == hashlib.sha256(data).hexdigest()
        result = SimpleNamespace(media_path=runtime.directory(job_id)/'output.mp4',
            inspection=SimpleNamespace(**job.inspection),document=attached['document'])
    isolated.dispose()
    return result


def prepare_reel(engine, config, graph, monkeypatch, rendered, platform='facebook'):
    storage = FakeStorage(); reg = registration(engine,config,storage,graph)
    monkeypatch.setattr(native,'TOKEN',PAGE)
    monkeypatch.setattr(reels_fixture,'VIDEO',rendered.media_path.read_bytes())
    with Session(engine,expire_on_commit=False) as db:
        connections = ConnectionService(db,config,provider_factory=lambda settings:MetaProvider(settings,transport=httpx.MockTransport(FakeGraph())),available_adapters=reg.adapters)
        _,state = start(connections); discovered = complete(connections,state)
        select_asset(connections,UUID(discovered['flow_id']))
        account = db.scalar(select(SocialAccount).where(SocialAccount.platform==platform))
        db.get(SocialControls,1).publishing_enabled = True; account.publishing_enabled = True
        data = rendered.media_path.read_bytes(); inspection = rendered.inspection
        key = 'final/owned-reels723/'+str(uuid4())+'/approved.mp4'
        storage.objects[key] = (data,'video/mp4',inspection.sha256)
        snapshot = storage.head(key)
        asset = SocialMediaAsset(id=uuid4(),storage_provider=storage.provider,bucket=storage.bucket,storage_key=key,
            original_filename='approved.mp4',mime_type=inspection.mime_type,byte_size=inspection.byte_size,
            sha256=inspection.sha256,width=inspection.width,height=inspection.height,duration_ms=inspection.duration_ms,
            frame_rate=inspection.frame_rate,state='ready',created_by=ACTOR,
            codec_metadata={**inspection.codec_metadata,'storage_etag':snapshot.etag,'storage_version':snapshot.version})
        db.add(asset); db.commit()
        monkeypatch.setattr(native,'FETCH_URL', 'https://'+'a'*32+'.r2.cloudflarestorage.com/media-test/'+key+'?fixture=preview-secret')
        body = draft_body(document={'master':{**rendered.document['master'],'media':[{**rendered.document['master']['media'][0],'asset_id':str(asset.id)}]},
            'targets':[{'account_id':str(account.id),'format':'reel','overrides':{}}]})
        _,created = call(db,body,lambda service:service.create(body),adapters=reg.adapters,route='reels-create')
        approve = ApproveCommand(expected_version=created['version'],revision_id=created['revision_id'])
        _,approved = call(db,approve,lambda service:service.approve(UUID(created['id']),approve),adapters=reg.adapters,route='reels-approve')
        publish = PublishCommand(expected_version=approved['version'],revision_id=approved['revision_id'])
        _,accepted = call(db,publish,lambda service:service.publish(UUID(created['id']),publish),adapters=reg.adapters,route='reels-publish')
        target = UUID(accepted['targets'][0]['id'])
    asyncio.run(reg.close())
    return storage,target,asset.id


def test_real_approved_render_survives_worker_restart_and_remains_visibility_held(engine,config,monkeypatch,inspected_video):
    graph = ReelGraph(); storage,target_id,asset_id = prepare_reel(engine,config,graph,monkeypatch,inspected_video)
    with Session(engine) as db:
        frozen = db.get(SocialPostTarget,target_id).resolved_payload
        assert frozen['assets'][0]['sha256'] == hashlib.sha256(inspected_video.media_path.read_bytes()).hexdigest()
        assert frozen['assets'][0]['duration_ms'] == inspected_video.inspection.duration_ms
    for _ in range(12):
        due(engine,target_id); step(engine,config,storage,graph)
        with Session(engine) as db:
            target = db.get(SocialPostTarget,target_id)
            assert target.resolved_payload == frozen
            if target.state == 'outcome_unknown':
                break
    assert target.state == 'outcome_unknown' and target.visibility_state == 'unknown', (target.state,target.error_code,target.checkpoint)
    assert target.submit_count == 1 and graph.published
    assert sum(c[0][0]=='POST' for c in graph.calls) == 3
    with Session(engine) as db:
        assert db.get(SocialMediaAsset,asset_id).sha256 == inspected_video.inspection.sha256
        attempts = list(db.scalars(select(SocialPublishAttempt)))
        assert len(attempts) >= 5
        assert all(row.completed_at for row in attempts)
        receipts = str([row.receipt for row in attempts])
        assert PAGE not in receipts and 'preview-secret' not in receipts


@pytest.mark.parametrize('change', ['sha256','duration_ms','frame_rate','width','token','capability'])
def test_stale_approved_media_or_material_blocks_final_publication(engine,config,monkeypatch,inspected_video,change):
    graph = ReelGraph(); storage,target_id,asset_id = prepare_reel(engine,config,graph,monkeypatch,inspected_video)
    for _ in range(3):
        due(engine,target_id); step(engine,config,storage,graph)
    with Session(engine) as db:
        target = db.get(SocialPostTarget,target_id)
        assert target.checkpoint['phase'] == 'publish_ready'
        account = db.get(SocialAccount,target.account_id)
        if change == 'token':
            account.connection_state = 'revoked'
        elif change == 'capability':
            account.capability_snapshot = {**account.capability_snapshot,'supported_formats':['text','image']}
        else:
            # Deliberate corruption via owned fixture SQL bypasses the ORM's
            # existing ready-asset immutability guard to test final admission.
            assert change in {'sha256','duration_ms','frame_rate','width'}
            db.execute(text('UPDATE social_media_assets SET '+change+'=:value WHERE id=:id'),
                {'value':'0'*64 if change=='sha256' else 30000 if change=='duration_ms' else 30 if change=='frame_rate' else 1080,'id':asset_id})
        db.commit()
    due(engine,target_id); step(engine,config,storage,graph)
    with Session(engine) as db:
        target = db.get(SocialPostTarget,target_id)
        assert target.state == 'blocked'
    assert not graph.published
    assert sum(c[0][0]=='POST' for c in graph.calls) == 2


def test_instagram_real_render_uses_retained_exact_fetch_custody_and_never_claims_public(engine,config,monkeypatch,inspected_video):
    from social.adapters.common import caption
    from social.contracts import ResolvedPostPayload
    graph = native.Graph()
    graph.overrides[('POST','/v26.0/801/media')] = {'id':'501'}
    storage,target_id,_ = prepare_reel(engine,config,graph,monkeypatch,inspected_video,platform='instagram')
    with Session(engine) as db:
        value = ResolvedPostPayload.model_validate(db.get(SocialPostTarget,target_id).resolved_payload)
    graph.overrides[('GET','/v26.0/601')] = {'id':'601','owner':{'id':'801'},'media_type':'VIDEO',
        'media_product_type':'REELS','permalink':'https://www.instagram.com/reel/fixture/',
        'shortcode':'fixture','caption':caption(value)}
    for _ in range(13):
        due(engine,target_id); step(engine,config,storage,graph)
        with Session(engine) as db:
            target = db.get(SocialPostTarget,target_id)
            if target.state=='outcome_unknown': break
    assert target.state=='outcome_unknown' and target.visibility_state=='unknown'
    assert target.checkpoint['media_id']=='601' and target.submit_count==1
    assert 'download' in storage.operations and 'preview' in storage.operations
    mutations = [body for method,path,body in graph.calls if method=='POST']
    assert len(mutations)==2 and b'video_url=' in mutations[0] and b'media_type=REELS' in mutations[0]


@pytest.mark.parametrize('operation,steps', [('upload',1),('publish',3)])
def test_repository_restart_with_lost_receipt_never_repeats_accepted_mutation(engine,config,monkeypatch,inspected_video,operation,steps):
    graph = ReelGraph(); storage,target_id,_ = prepare_reel(engine,config,graph,monkeypatch,inspected_video)
    for _ in range(steps):
        due(engine,target_id); step(engine,config,storage,graph)
    due(engine,target_id); step(engine,config,storage,graph,drop_receipt=True)
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_post_targets SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:id"),{'id':target_id})
        conn.execute(text("UPDATE social_accounts SET publish_lease_expires_at=clock_timestamp()-interval '1 second' WHERE publish_lease_target_id=:id"),{'id':target_id})
    repository(engine).recover_expired()
    for _ in range(12):
        due(engine,target_id); step(engine,config,storage,graph)
        with Session(engine) as db:
            target = db.get(SocialPostTarget,target_id)
            if target.state=='outcome_unknown': break
    assert target.state=='outcome_unknown' and graph.published
    uploads = [c for c in graph.calls if c[0][1]=='rupload.facebook.com']
    finishes = [c for c in graph.calls if c[0][0]=='POST' and b'upload_phase=finish' in c[2]]
    assert len(uploads)==1 and len(finishes)==1 and target.submit_count==1


def test_real_registration_admits_only_delivery_and_retains_operator_confirmation(engine,config,monkeypatch,inspected_video):
    graph = ReelGraph(); storage,target_id,asset_id = prepare_reel(engine,config,graph,monkeypatch,inspected_video)
    # Real native admission authorizes bounded delivery, never automatic public confirmation.
    due(engine,target_id); real_step(engine,config,storage,graph)
    with Session(engine) as db:
        target = db.get(SocialPostTarget,target_id)
        assert target.state == 'queued' and target.checkpoint['phase']=='session_created'
    assert len(graph.calls)==1 and graph.published is False

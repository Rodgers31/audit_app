"""Cleanup races execute against the dedicated loopback PostgreSQL fixture."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from local_postgres import local_postgres_url

from social.media.models import SocialMediaBudget, SocialMediaUpload
from social.media.service import MediaService
from social.media.storage import StorageFailure
from social.models import Base, SocialMediaAsset
from social.service import SocialError
from test_media_support import ACTOR, intent, media, media_db, png, upload_ready, settle_writes


@pytest.fixture
def media_pg(media):
    # Explicit dedicated local test database; no dotenv/default app DSN.
    dsn = os.getenv('SOCIAL_WORKER_TEST_DATABASE_URL') or os.getenv('SOCIAL_TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('Set SOCIAL_WORKER_TEST_DATABASE_URL for the isolated media PostgreSQL lane')
    database = 'social_worker_test' if os.getenv('SOCIAL_WORKER_TEST_DATABASE_URL') else 'social_domain_test'
    url = local_postgres_url(dsn, database)
    schema='media_race_'+uuid4().hex
    admin=create_engine(url,pool_size=1,max_overflow=0,hide_parameters=True)
    with admin.begin() as conn: conn.execute(text('CREATE SCHEMA '+schema))
    engine=create_engine(url,pool_size=4,max_overflow=0,hide_parameters=True,connect_args={'options':'-csearch_path='+schema})
    Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name.startswith('social_')])
    try: yield engine,media[0].runtime
    finally:
        engine.dispose()
        with admin.begin() as conn: conn.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        admin.dispose()


def test_late_finalize_remains_reserved_until_settled_then_cleanup_deletes(media):
    svc,store=media; grant=svc.initiate(ACTOR,uuid4(),intent(),uuid4())
    store.objects[store.last_key]=(png(),'image/png',None)
    key='ready/'+str(grant.asset.id)+'/original'
    def late(operation):
        if operation == 'finalize':
            store.hook=None
            with svc.db.begin():
                svc.db.get(SocialMediaAsset,grant.asset.id).lease_expires_at=svc.now()-timedelta(seconds=1)
                svc.db.get(SocialMediaUpload,grant.asset.id).expires_at=svc.now()-timedelta(seconds=1)
            assert svc.cleanup()==0
            with svc.db.begin():
                assert svc.db.get(SocialMediaBudget,'global').bytes_used==2*len(png())
    store.hook=late
    with pytest.raises(SocialError,match='MEDIA_LEASE_LOST'): svc.complete(ACTOR,grant.asset.id,uuid4(),1,uuid4())
    assert key in store.objects
    settle_writes(svc, grant.asset.id)
    assert svc.cleanup()==1
    assert key not in store.objects
    with svc.db.begin(): assert svc.db.get(SocialMediaBudget,'global').bytes_used==0


@pytest.mark.parametrize('crash',[RuntimeError,StorageFailure])
def test_unknown_remote_creation_is_retained_and_reported(media,crash):
    svc,store=media; grant=svc.initiate(ACTOR,uuid4(),intent(),uuid4()); key=uuid4()
    store.objects[store.last_key]=(png(),'image/png',None)
    original=store.finalize
    def ambiguous(*args):
        original(*args)
        raise crash('private remote error')
    store.finalize=ambiguous
    with pytest.raises(SocialError if crash is StorageFailure else RuntimeError): svc.complete(ACTOR,grant.asset.id,key,1,uuid4())
    with svc.db.begin():
        svc.db.get(SocialMediaAsset,grant.asset.id).lease_expires_at=svc.now()-timedelta(seconds=1)
        svc.db.get(SocialMediaUpload,grant.asset.id).expires_at=svc.now()-timedelta(seconds=1)
        assert svc.db.get(SocialMediaBudget,'global').bytes_used==2*len(png())
    assert svc.cleanup()==0
    with pytest.raises(SocialError,match='MEDIA_FINALIZATION_UNKNOWN') as error: svc.complete(ACTOR,grant.asset.id,key,1,uuid4())
    assert not error.value.retryable


def test_cleanup_failure_keeps_budget_and_can_retry_after_lease(media):
    svc,store=media; grant=svc.initiate(ACTOR,uuid4(),intent(),uuid4())
    with svc.db.begin(): svc.db.get(SocialMediaUpload,grant.asset.id).expires_at=svc.now()-timedelta(seconds=1)
    settle_writes(svc, grant.asset.id)
    store.fail='delete'; assert svc.cleanup()==0
    with svc.db.begin():
        assert svc.db.get(SocialMediaBudget,'global').bytes_used==2*len(png())
        svc.db.get(SocialMediaAsset,grant.asset.id).lease_expires_at=svc.now()-timedelta(seconds=1)
    store.fail=None; assert svc.cleanup()==1
    assert svc.cleanup()==0


def test_physical_two_copy_budget_ready_quarantine_release_once(media):
    svc,store=media; ready=upload_ready(media)
    with svc.db.begin():
        assert svc.db.get(SocialMediaBudget,'global').bytes_used==2*len(png())
        svc.db.get(SocialMediaUpload,ready.id).expires_at=svc.now()-timedelta(seconds=1)
    settle_writes(svc, ready.id)
    assert svc.cleanup()==1 and svc.cleanup()==0
    with svc.db.begin():
        assert svc.db.get(SocialMediaBudget,'global').bytes_used==len(png())
        assert svc.db.get(SocialMediaUpload,ready.id).reserved_bytes==len(png())
    assert svc.preview(ready.id).asset.state=='ready'


def test_pg_stale_cleanup_candidate_cannot_release_other_pending_quota(media_pg):
    engine,runtime=media_pg
    with Session(engine,expire_on_commit=False) as db:
        svc=MediaService(db,runtime); expired=svc.initiate(ACTOR,uuid4(),intent(),uuid4()).asset
        svc.initiate(ACTOR,uuid4(),intent(),uuid4())
        with db.begin(): db.get(SocialMediaUpload,expired.id).expires_at=svc.now()-timedelta(seconds=1)
        settle_writes(svc, expired.id)
    selected,release=threading.Event(),threading.Event()
    class Paused(MediaService):
        def _budgets(self,actor):
            selected.set(); assert release.wait(5); return super()._budgets(actor)
    def delayed():
        with Session(engine,expire_on_commit=False) as db: return Paused(db,runtime).cleanup()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(delayed); assert selected.wait(5)
        try:
            with Session(engine,expire_on_commit=False) as db: assert MediaService(db,runtime).cleanup()==1
        finally: release.set()
        assert future.result(timeout=5)==0
    with Session(engine) as db:
        budget=db.get(SocialMediaBudget,'global')
        assert budget.bytes_used==2*len(png()) and budget.pending_count==1


def test_pg_same_intent_replay_and_quota_races(media_pg):
    engine,runtime=media_pg; key=uuid4()
    def initiate(k):
        with Session(engine,expire_on_commit=False) as db: return MediaService(db,runtime).initiate(ACTOR,k,intent(),uuid4()).asset.id
    with ThreadPoolExecutor(max_workers=2) as pool: ids=list(pool.map(initiate,[key,key]))
    assert ids[0]==ids[1]
    def consume(_):
        try: return initiate(uuid4())
        except SocialError as error: return error.code
    with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(consume,range(3)))
    assert results.count('MEDIA_QUOTA_EXCEEDED')==1
    with Session(engine) as db:
        assert db.get(SocialMediaBudget,'global').bytes_used==6*len(png())
        assert db.get(SocialMediaBudget,'global').pending_count==3


def test_unknown_finalization_does_not_starve_later_cleanup_batches(media):
    svc,store=media
    first=svc.initiate(ACTOR,uuid4(),intent(),uuid4()).asset
    second=svc.initiate(ACTOR,uuid4(),intent(),uuid4()).asset
    with svc.db.begin():
        original=svc.db.get(SocialMediaUpload,first.id)
        original.expires_at=svc.now()-timedelta(seconds=10)
        original.finalization_epoch=1; original.finalization_settled=0
        svc.db.get(SocialMediaUpload,second.id).expires_at=svc.now()-timedelta(seconds=1)
    settle_writes(svc, second.id)
    assert svc.cleanup(limit=1)==1
    with svc.db.begin():
        assert svc.db.get(SocialMediaUpload,first.id).reservation_released==0
        assert svc.db.get(SocialMediaUpload,second.id).reservation_released==1
        assert svc.db.get(SocialMediaBudget,'global').bytes_used==2*len(png())


def test_referenced_nonready_asset_is_retained_without_starving_orphans(media):
    from social.contracts import CreatePost
    from social.service import SocialService
    svc,_=media
    retained=svc.initiate(ACTOR,uuid4(),intent(),uuid4()).asset
    removable=svc.initiate(ACTOR,uuid4(),intent(),uuid4()).asset
    body=CreatePost.model_validate({'title':'Retained evidence','content_type':'announcement','document':{'schema_version':1,'master':{'text':'Evidence','link':None,'hashtags':[],'media':[]},'targets':[]},'references':[]})
    domain=SocialService(svc.db)
    _, created = domain.command(actor=ACTOR,route='fixture.create',key=uuid4(),body=body.model_dump(mode='json'),request_id=uuid4(),action=lambda:domain.create(body))
    # Historical references predate the new ready-only reference contract.
    from social.models import SocialPost, SocialRevisionAsset
    from uuid import UUID
    with svc.db.begin():
        post = svc.db.get(SocialPost, UUID(created['id']))
        svc.db.add(SocialRevisionAsset(revision_id=post.current_revision_id, asset_id=retained.id))
        svc.db.get(SocialMediaUpload,retained.id).expires_at=svc.now()-timedelta(seconds=10)
        svc.db.get(SocialMediaUpload,removable.id).expires_at=svc.now()-timedelta(seconds=1)
    settle_writes(svc, removable.id)
    assert svc.cleanup(limit=1)==1
    with svc.db.begin():
        assert svc.db.get(SocialMediaUpload,retained.id).reservation_released==0
        assert svc.db.get(SocialMediaAsset,retained.id).deleted_at is None
        assert svc.db.get(SocialMediaUpload,removable.id).reservation_released==1


def test_pg_concurrent_completion_is_busy_during_active_remote_finalize(media_pg):
    engine,runtime=media_pg; store=runtime.storage
    with Session(engine,expire_on_commit=False) as db:
        grant=MediaService(db,runtime).initiate(ACTOR,uuid4(),intent(),uuid4())
    store.objects[store.last_key]=(png(),'image/png',None)
    started,release=threading.Event(),threading.Event(); key=uuid4()
    def pause(operation):
        if operation=='finalize': started.set(); assert release.wait(5)
    store.hook=pause
    def first():
        with Session(engine,expire_on_commit=False) as db: return MediaService(db,runtime).complete(ACTOR,grant.asset.id,key,1,uuid4())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(first); assert started.wait(5)
        try:
            with Session(engine,expire_on_commit=False) as db:
                with pytest.raises(SocialError,match='MEDIA_INSPECTION_BUSY') as error: MediaService(db,runtime).complete(ACTOR,grant.asset.id,key,1,uuid4())
                assert error.value.retryable
        finally: release.set(); store.hook=None
        ready=future.result(timeout=5)
    with Session(engine,expire_on_commit=False) as db:
        svc=MediaService(db,runtime)
        assert ready.state=='ready' and svc.complete(ACTOR,grant.asset.id,key,1,uuid4())==ready


def test_live_cleanup_lease_does_not_consume_the_bounded_candidate_batch(media):
    svc,_=media
    first=svc.initiate(ACTOR,uuid4(),intent(),uuid4()).asset
    second=svc.initiate(ACTOR,uuid4(),intent(),uuid4()).asset
    with svc.db.begin():
        svc.db.get(SocialMediaUpload,first.id).expires_at=svc.now()-timedelta(seconds=10)
        svc.db.get(SocialMediaUpload,second.id).expires_at=svc.now()-timedelta(seconds=1)
        asset=svc.db.get(SocialMediaAsset,first.id)
        asset.state='archived'; asset.lease_token=uuid4(); asset.lease_epoch=1
        asset.lease_expires_at=svc.now()+timedelta(seconds=60)
    settle_writes(svc, second.id)
    assert svc.cleanup(limit=1)==1
    with svc.db.begin():
        assert svc.db.get(SocialMediaUpload,first.id).reservation_released==0
        assert svc.db.get(SocialMediaUpload,second.id).reservation_released==1


def test_r2_put_timeout_with_matching_remote_bytes_retains_finalization_quota(media):
    from social.media.storage import R2Storage
    from test_media_support import ENDPOINT
    svc,store=media; grant=svc.initiate(ACTOR,uuid4(),intent(),uuid4()); command=uuid4()
    store.objects[store.last_key]=(png(),'image/png',None)
    class AmbiguousSDK:
        from types import SimpleNamespace
        meta = SimpleNamespace(config=SimpleNamespace(retries={'total_max_attempts': 1}))
        def put_object(self,**params):
            data=params['Body'].read()
            store.objects[params['Key']]=(data,params['ContentType'],params['Metadata']['sha256'])
            raise TimeoutError('another remote attempt may still finish')
        def head_object(self,**params): raise AssertionError('A matching HEAD must not settle the write')
    store.finalize=R2Storage(AmbiguousSDK(),store.bucket,ENDPOINT).finalize
    with pytest.raises(SocialError,match='MEDIA_FINALIZATION_UNKNOWN'): svc.complete(ACTOR,grant.asset.id,command,1,uuid4())
    with svc.db.begin():
        upload=svc.db.get(SocialMediaUpload,grant.asset.id)
        assert upload.finalization_epoch==1 and upload.finalization_settled==0
        upload.expires_at=svc.now()-timedelta(seconds=1)
        svc.db.get(SocialMediaAsset,grant.asset.id).lease_expires_at=svc.now()-timedelta(seconds=1)
    assert svc.cleanup()==0
    with svc.db.begin(): assert svc.db.get(SocialMediaBudget,'global').bytes_used==2*len(png())

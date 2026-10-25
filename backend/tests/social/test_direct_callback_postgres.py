"""Owned B86 PostgreSQL lifecycle/concurrency; ORM schema, no migration claim."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from urllib.parse import parse_qs,urlsplit
from uuid import UUID,uuid4

import pytest
from sqlalchemy import create_engine,select,text,event
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url

from social.connections.direct_callback import DirectCallback,cookie_name
from social.connections.contracts import DirectStartCommand,DirectCompleteCommand
from social.connections.models import SocialOAuthFlow
from social.models import Base,SOCIAL_TABLES
from social.service import SocialError
from test_connections_support import config,graph,svc,ACTOR,BINDING
from test_direct_callback import direct_config,ORIGIN

@pytest.fixture
def direct_pg():
    raw=os.environ.get('B86_767_TEST_DATABASE_URL')
    if not raw: pytest.skip('Requires explicitly owned B86_767_TEST_DATABASE_URL')
    u=make_url(raw)
    if '?' in raw or u.host!='127.0.0.1' or u.port not in {5432,55867} or u.database!='b86_767' or u.username!='b86_767' or u.drivername!='postgresql+psycopg2': raise ValueError('Use only the owned B86 callback fixture')
    admin=create_engine(u,pool_size=1,max_overflow=0); schema='b86_767_'+uuid4().hex
    with admin.begin() as c:c.execute(text('CREATE SCHEMA '+schema))
    engine=create_engine(u,pool_size=3,max_overflow=0,connect_args={'hostaddr':'127.0.0.1','options':'-csearch_path='+schema+' -cstatement_timeout=5000 -clock_timeout=5000'})
    try:
        Base.metadata.create_all(engine,tables=SOCIAL_TABLES)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as c:c.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        admin.dispose()


def prepared(engine,cfg,graph):
    with Session(engine,expire_on_commit=False) as db:
        d=DirectCallback(svc(db,cfg,graph))
        flow=d.start(ACTOR,BINDING,'direct start',uuid4(),DirectStartCommand(admin_origin=ORIGIN,reason='Inert fixture'),uuid4())
        flow_id=UUID(flow['flow_id']); url,name,browser=d.launch(flow_id,flow['launch_token'],ORIGIN)
        state=parse_qs(urlsplit(url).query)['state'][0]
        d.stage(('state='+state+'&code=INERT-concurrent-code').encode(),{name:browser})
        return flow_id


def test_pg_simultaneous_claim_has_one_provider_effect_and_no_open_db_transaction(direct_pg,config,graph):
    cfg=direct_config(config); flow_id=prepared(direct_pg,cfg,graph)
    entered,release=threading.Event(),threading.Event()
    def finish(wait):
        with Session(direct_pg,expire_on_commit=False) as db:
            def provider(request):
                assert not db.in_transaction()
                if wait and not entered.is_set():
                    entered.set(); assert release.wait(5)
                return graph(request)
            try:
                return DirectCallback(svc(db,cfg,provider)).complete(ACTOR,BINDING,'direct complete',uuid4(),DirectCompleteCommand(flow_id=flow_id),uuid4())
            except SocialError as e:return e.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(finish,True); assert entered.wait(5)
        with Session(direct_pg) as db:
            f=db.get(SocialOAuthFlow,flow_id);assert f.status=='exchanging' and f.encrypted_verifier is None
        second=pool.submit(finish,False);assert second.result(timeout=5)=='OAUTH_STATE_USED'
        release.set();assert first.result(timeout=5)['flow_id']==str(flow_id)
    # Existing provider makes two different token exchange calls per discovery.
    short=[r for r in graph.calls if b'INERT-concurrent-code' in r.content]
    assert len(short)==1


def test_pg_stage_commit_failure_leaves_original_attempt_retryable(direct_pg,config,graph):
    cfg=direct_config(config)
    with Session(direct_pg,expire_on_commit=False) as db:
        d=DirectCallback(svc(db,cfg,graph)); f=d.start(ACTOR,BINDING,'start',uuid4(),DirectStartCommand(admin_origin=ORIGIN,reason='Inert fixture'),uuid4()); url,name,browser=d.launch(UUID(f['flow_id']),f['launch_token'],ORIGIN)
        state=parse_qs(urlsplit(url).query)['state'][0]
        def fail(_): raise RuntimeError('INERT-commit-failure')
        event.listen(db,'before_commit',fail)
        with pytest.raises(RuntimeError):d.stage(('state='+state+'&code=INERT').encode(),{name:browser})
        db.rollback();event.remove(db,'before_commit',fail)
        assert d.stage(('state='+state+'&code=INERT').encode(),{name:browser})==UUID(f['flow_id'])
        assert graph.calls==[]


def test_pg_claim_commit_failure_never_calls_provider(direct_pg,config,graph):
    cfg=direct_config(config); flow_id=prepared(direct_pg,cfg,graph)
    with Session(direct_pg,expire_on_commit=False) as db:
        d=DirectCallback(svc(db,cfg,graph))
        def fail(_):raise RuntimeError('INERT-commit-failure')
        event.listen(db,'before_commit',fail)
        with pytest.raises(RuntimeError):d.complete(ACTOR,BINDING,'complete',uuid4(),DirectCompleteCommand(flow_id=flow_id),uuid4())
        db.rollback();event.remove(db,'before_commit',fail)
        assert graph.calls==[]
        assert db.get(SocialOAuthFlow,flow_id).status=='initiated'

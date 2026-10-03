"""Connection concurrency proof in random schemas on the explicit local fixture.

The integrator separately tests the real additive migration/RLS. This lane
executes service locking; it never imports main, dotenv or production settings.
"""
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID,uuid4
import pytest
from sqlalchemy import create_engine,select,text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from social.models import Base,SOCIAL_TABLES,SocialAccount,SocialControls
from social.connections.models import CONNECTION_TABLES,SocialOAuthFlow,SocialCredential
from social.connections.contracts import AccountCommand
from social.connections.service import ConnectionService
from social.service import SocialError
from test_connections_support import *

@pytest.fixture
def connection_pg_engine():
    dsn=os.getenv('SOCIAL_CONNECTIONS_TEST_DATABASE_URL')
    if not dsn:pytest.skip('Set the explicit isolated local connection test DSN')
    url=make_url(dsn)
    if url.host not in {'127.0.0.1','localhost','::1'} or url.port!=62124 or url.database!='social_worker_test':
        pytest.fail('Connection tests require local social_worker_test on port 62124')
    schema='social_connections_'+uuid4().hex
    admin=create_engine(url,pool_size=1,max_overflow=0)
    with admin.begin() as connection:connection.execute(text('CREATE SCHEMA '+schema))
    engine=create_engine(url,pool_size=3,max_overflow=0,connect_args={'options':'-csearch_path='+schema+' -cstatement_timeout=5000 -clock_timeout=5000'})
    try:
        Base.metadata.create_all(engine,tables=SOCIAL_TABLES+CONNECTION_TABLES)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:connection.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        admin.dispose()

def test_pg_state_consumption_is_single_use_and_does_not_hold_transaction(connection_pg_engine,config,graph):
    with Session(connection_pg_engine,expire_on_commit=False) as db:
        _,state=start(svc(db,config,graph))
    entered,release=threading.Event(),threading.Event()
    def gated(request):
        if request.url.path=='/v26.0/oauth/access_token' and not entered.is_set():
            entered.set()
            assert release.wait(5)
        return graph(request)
    def finish(fake):
        with Session(connection_pg_engine,expire_on_commit=False) as db:
            try:complete(svc(db,config,fake),state);return 'completed'
            except SocialError as e:return e.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(finish,gated)
        assert entered.wait(5)
        with Session(connection_pg_engine) as db:
            flow=db.scalar(select(SocialOAuthFlow))
            assert flow.status=='exchanging' and flow.encrypted_verifier is None
        second=pool.submit(finish,graph)
        assert second.result(timeout=5)=='OAUTH_STATE_USED'
        release.set()
        assert first.result(timeout=5)=='completed'
    assert len([r for r in graph.calls if r.url.path=='/v26.0/oauth/access_token'])==2


def test_pg_reconnect_fences_stale_disconnect_after_account_pointer_changes(connection_pg_engine,config,graph):
    with Session(connection_pg_engine,expire_on_commit=False) as db:
        service=svc(db,config,graph)
        first,state=start(service);complete(service,state)
        accounts=select_asset(service,UUID(first['flow_id']))['accounts']
        page=UUID(accounts[0]['id'])
        old=service.health(page);db.rollback()
        next_flow,next_state=start(service,reconnect=page);complete(service,next_state)
    locked,release,disconnect_started=threading.Event(),threading.Event(),threading.Event()
    class PausedReconnect(ConnectionService):
        def _lock_accounts(self,ids):
            rows=super()._lock_accounts(ids)
            locked.set()
            assert release.wait(5)
            return rows
    def reconnect():
        with Session(connection_pg_engine,expire_on_commit=False) as db:
            return select_asset(PausedReconnect(db,config),UUID(next_flow['flow_id']))
    def stale_disconnect():
        with Session(connection_pg_engine,expire_on_commit=False) as db:
            # Cache the obsolete pointer before waiting for reconnect's control lock.
            db.get(SocialAccount,page);db.rollback()
            disconnect_started.set()
            try:
                return svc(db,config,graph).account_command(page,ACTOR,BINDING,'POST disconnect/'+str(page),uuid4(),AccountCommand(expected_credential_id=UUID(old['credential_id']),expected_credential_version=old['credential_version'],reason='Stale fixture'),uuid4())
            except SocialError as e:return e.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(reconnect)
        assert locked.wait(5)
        second=pool.submit(stale_disconnect)
        assert disconnect_started.wait(5)
        assert not second.done()
        release.set()
        first.result(timeout=5)
        assert second.result(timeout=5)=='VERSION_CONFLICT'
    with Session(connection_pg_engine) as db:
        row=db.get(SocialAccount,page)
        credential=db.get(SocialCredential,row.credential_id)
        assert str(credential.id)!=old['credential_id'] and credential.revoked_at is None
        assert row.connection_state=='connected' and row.publishing_enabled is False

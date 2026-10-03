"""Only fake grants, isolated SQLite and explicit HTTPX MockTransport."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from urllib.parse import parse_qs, urlsplit
import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from social.models import Base, SOCIAL_TABLES
from social.connections.models import CONNECTION_TABLES
from social.connections.config import MetaConfig, SCOPES
from social.connections.provider import MetaProvider
from social.connections.service import ConnectionService, session_binding
from social.connections.contracts import StartCommand, CompleteCommand, SelectCommand

ACTOR, SESSION = uuid4(), uuid4()
BINDING = session_binding(ACTOR, SESSION)
REDIRECT = 'https://admin.example.test/admin/social/accounts/callback'
USER, PAGE, PAGE2 = 'fake-user-grant-not-a-real-token', 'fake-page-grant-not-a-real-token', 'fake-second-page-grant-not-a-real-token'

@pytest.fixture
def config():
    return MetaConfig(enabled=True, app_configuration_validated=True, app_id='123', app_secret='fake-app-secret', redirect_uris=(REDIRECT,), access_mode='owned_standard', active_key_version='v1', encryption_keys={'v1': Fernet.generate_key().decode()})

@pytest.fixture
def db():
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def fk(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine, tables=SOCIAL_TABLES + CONNECTION_TABLES)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()

class FakeGraph:
    def __init__(self):
        self.calls = []
        self.scopes = list(SCOPES)
        self.tasks = ['CREATE_CONTENT']
        self.pages = [{'id':'901','name':'AuditGava','access_token':PAGE,'tasks':self.tasks,'instagram_business_account':{'id':'801'}}]
        self.paging = False
        self.revoke = False
        self.expired = False
        self.error = None
    def __call__(self, request):
        self.calls.append(request)
        path = request.url.path.removeprefix('/v26.0/')
        if self.error:
            return httpx.Response(400, json=self.error)
        if path == 'oauth/access_token':
            assert request.method == 'POST'
            return httpx.Response(200,json={'access_token': USER, 'token_type':'bearer','expires_in':5184000})
        if path == 'debug_token':
            token = request.url.params['input_token']
            return httpx.Response(200,json={'data': {'app_id':'123','type':'USER' if token == USER else 'PAGE','is_valid':not self.revoke,'user_id':'701','scopes':self.scopes,'expires_at':int((datetime.now(timezone.utc)+timedelta(days=-1 if self.expired else 60)).timestamp()) if token == USER else 0, 'data_access_expires_at':int((datetime.now(timezone.utc)+timedelta(days=90)).timestamp())}})
        if path == 'me':
            token=request.headers['Authorization'].removeprefix('Bearer ')
            return httpx.Response(200,json={'id': '901' if token == PAGE else '902'})
        if path == 'me/permissions':
            return httpx.Response(200,json={'data':[{'permission':s,'status':'granted'} for s in self.scopes]})
        if path == 'me/accounts':
            if self.paging and not request.url.params.get('after'):
                return httpx.Response(200,json={'data':self.pages[:1], 'paging': {'next':'https://attacker.example/steal?access_token='+USER,'cursors':{'after':'next-page'}}})
            return httpx.Response(200,json={'data':self.pages[1:] if self.paging else self.pages})
        if path == '801':
            return httpx.Response(200,json={'id':'801','username':'auditgava','name':'AuditGava IG'})
        raise AssertionError('Unexpected provider endpoint: ' + path)

@pytest.fixture
def graph():
    return FakeGraph()

def svc(db, config, graph):
    return ConnectionService(db, config, provider_factory=lambda c: MetaProvider(c, client=httpx.Client(transport=httpx.MockTransport(graph), trust_env=False)))

def start(service, *, actor=ACTOR, binding=BINDING, key=None, reconnect=None):
    result = service.start(actor, binding, 'POST start', key or uuid4(), StartCommand(redirect_uri=REDIRECT, reconnect_account_id=reconnect, reason='Connect owned assets'), uuid4())
    return result, parse_qs(urlsplit(result['authorize_url']).query)['state'][0]

def complete(service, state, *, actor=ACTOR, binding=BINDING, key=None, redirect=REDIRECT):
    return service.complete(actor, binding, 'POST complete', key or uuid4(), CompleteCommand(code='fake-short-lived-code', state=state, redirect_uri=redirect), uuid4())

def select_asset(service, flow_id, *, page='901', ig='801', key=None):
    return service.select(flow_id, ACTOR, BINDING, 'POST select/'+str(flow_id), key or uuid4(), SelectCommand(page_id=page, instagram_id=ig, reason='Explicit owned asset selection'), uuid4())

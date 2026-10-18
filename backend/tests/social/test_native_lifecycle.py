"""Executable regressions from independent lifecycle review; no external I/O."""
from types import SimpleNamespace
from contextlib import asynccontextmanager
import pytest
import httpx
from sqlalchemy import create_engine
from test_native_startup import ready
from social.worker.startup import native_runtime, installed_native_runtime
from social.service import SocialError
ENABLED = {'SOCIAL_NATIVE_ENABLED':'true', 'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED':'true'}
SECRET = 'FIXTURE_ONLY_SECRET_ERROR_MARKER'


class Transport(httpx.AsyncBaseTransport):
    def __init__(self,events,name,broken=False):self.events=events;self.name=name;self.broken=broken
    async def handle_async_request(self,request):pytest.fail('unexpected network')
    async def aclose(self):
        self.events.append(self.name)
        if self.broken:raise RuntimeError(SECRET)

@pytest.mark.asyncio
async def test_partial_setup_close_failure_cannot_escape_sanitized_error(monkeypatch):
    module=ready(monkeypatch);events=[];engine=create_engine('sqlite://')
    transport=Transport(events,'transport',True);calls=[]
    def factory():
        calls.append(1)
        if len(calls)==2:raise ValueError(SECRET)
        return transport
    try:
        with pytest.raises(SocialError,match='NATIVE_CONFIGURATION_INVALID') as error:
            async with native_runtime(engine,environ=ENABLED,transport_factory=factory):pytest.fail('admitted')
        assert error.value.__context__ is None
    finally:engine.dispose()

@pytest.mark.asyncio
async def test_normal_shutdown_close_failure_still_closes_all_transports(monkeypatch):
    ready(monkeypatch);events=[];engine=create_engine('sqlite://');calls=[]
    def factory():
        calls.append(1);return Transport(events,str(len(calls)),len(calls)==1)
    try:
        with pytest.raises(Exception):
            async with native_runtime(engine,environ=ENABLED,transport_factory=factory):pass
        assert events==['1','2'],'first failing close prevented second transport cleanup'
    finally:engine.dispose()

@pytest.mark.asyncio
async def test_r2_close_cannot_leak_sdk_exception(monkeypatch):
    module=ready(monkeypatch);base=module.load_media_runtime({});engine=create_engine('sqlite://')
    def fail():raise RuntimeError(SECRET)
    base.storage.client.close.side_effect=fail
    try:
        with pytest.raises(SocialError) as error:
            async with native_runtime(engine,environ=ENABLED,transport_factory=lambda:httpx.MockTransport(lambda r:pytest.fail('network'))):pass
        assert SECRET not in str(error.value)
        assert error.value.__context__ is None
    finally:engine.dispose()

@pytest.mark.asyncio
async def test_happy_installed_shutdown_detaches_before_transport_and_storage_close(monkeypatch):
    module=ready(monkeypatch);base=module.load_media_runtime({});events=[];engine=create_engine('sqlite://');app=SimpleNamespace(state=SimpleNamespace())
    class Check(Transport):
        async def aclose(self):
            assert not hasattr(app.state,'social_native_registration');await super().aclose()
    base.storage.client.close.side_effect=lambda:events.append('storage')
    try:
        async with installed_native_runtime(app,engine,environ=ENABLED,transport_factory=lambda:Check(events,'transport')) as reg:
            assert app.state.social_native_registration is reg
        assert events==['transport','transport','storage']
        assert not hasattr(app.state,'social_native_registration')
    finally:engine.dispose()

def test_cli_dispose_failure_is_sanitized_and_returns_nonzero(monkeypatch,caplog):
    import social.worker.__main__ as cli
    class Engine:
        def dispose(self):raise RuntimeError(SECRET)
    class Worker:
        def __init__(self,*a,**k):pass
        async def run(self,**k):pass
        async def close(self):pass
        def stop(self):pass
    monkeypatch.setattr(cli,'create_worker_engine',lambda cfg:Engine())
    monkeypatch.setattr(cli,'QueueRepository',lambda *a,**k:object())
    monkeypatch.setattr(cli,'SocialWorker',Worker)
    assert cli.main(['--database-url','postgresql://fixture@invalid/fixture','--once'])==1
    assert SECRET not in caplog.text

def test_explicit_mapping_never_borrows_credentials_from_process(monkeypatch):
    from social.connections.config import load_config
    monkeypatch.setenv('META_APP_SECRET',SECRET)
    monkeypatch.setenv('META_APP_ID','123')
    actual=load_config({})
    assert actual.app_secret=='' and actual.app_id==''
    assert actual.enabled is False

def test_cli_real_worker_bounded_scan_closes_native_then_engine(monkeypatch):
    import os
    import threading
    from social.worker import ownership
    import social.worker.__main__ as cli
    module=ready(monkeypatch);base=module.load_media_runtime({});events=[]
    monkeypatch.setenv('SOCIAL_NATIVE_ENABLED','true');monkeypatch.setenv('SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED','true')
    monkeypatch.setattr(cli,'verify_worker_role',lambda *args:None)
    monkeypatch.setattr(cli,'validate_worker_native_environment',lambda values:None)
    def acquire(engine, worker_id, version):
        authority=ownership.RuntimeAuthority(worker_id,1)
        monkeypatch.setitem(ownership._issued,(os.getpid(),id(authority)),authority)
        return authority
    monkeypatch.setattr(cli,'acquire_authority',acquire)
    engine=create_engine('sqlite://')
    original=engine.dispose
    def dispose():events.append('engine');original()
    monkeypatch.setattr(engine,'dispose',dispose)
    monkeypatch.setattr(cli,'create_worker_engine',lambda cfg:engine)
    class Repo:
        def __init__(self,eng,config,worker_id,*,authority):
            self.config=config;self.authority=authority;self.admission_stopped=threading.Event()
        def check_authority(self):events.append('authority')
        def drained(self):events.append('drained');return True
        def validate_schema(self):events.append('schema')
        def recover_expired(self):events.append('recover')
        def claim_due(self,n):events.append('scan');return []
        def heartbeat(self,**kwargs):events.append('heartbeat')
    monkeypatch.setattr(cli,'QueueRepository',Repo)
    base.storage.client.close.side_effect=lambda:events.append('storage')
    @asynccontextmanager
    async def composition(engine):
        async with native_runtime(engine,environ=ENABLED,transport_factory=lambda:Transport(events,'transport')) as reg:yield reg
    monkeypatch.setattr(cli,'native_runtime',composition)
    assert cli.main(['--database-url','postgresql://fixture@invalid/fixture','--once','--native-meta','--worker-role','inert_worker'])==0
    assert events==['authority','schema','recover','scan','heartbeat','heartbeat','transport','transport','storage','drained','engine']

@pytest.mark.asyncio
async def test_real_app_lifespan_stops_work_before_native_close(monkeypatch):
    import main
    import database
    import importlib
    seeder=importlib.import_module('services.auto_seeder')
    import social.worker.startup as startup_module
    events=[];app=SimpleNamespace(state=SimpleNamespace())
    monkeypatch.setattr(main,'DATABASE_AVAILABLE',True)
    monkeypatch.setattr(database,'engine',object())
    async def sequence():
        events.append('startup')
        try:await __import__('asyncio').Event().wait()
        finally:events.append('cancel-startup')
    async def stop():events.append('stop-seeder')
    @asynccontextmanager
    async def installed(app_,engine):
        events.append('native-open')
        try:yield
        finally:events.append('native-close')
    monkeypatch.setattr(main,'_startup_sequence',sequence)
    monkeypatch.setattr(seeder,'stop_auto_seeder',stop)
    monkeypatch.setattr(startup_module,'installed_native_runtime',installed)
    async with main._app_lifespan(app):
        await __import__('asyncio').sleep(0)
        events.append('serve')
    assert events==['native-open','startup','serve','cancel-startup','stop-seeder','native-close']

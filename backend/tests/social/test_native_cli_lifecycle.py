"""Independent CLI signal, cancellation and bounded-run regressions."""
import asyncio,logging
from contextlib import asynccontextmanager
from types import SimpleNamespace
import pytest
from social.worker import __main__ as cli

@pytest.fixture
def f(monkeypatch):
 events=[];config=[];instances=[]
 engine=SimpleNamespace(dispose=lambda:events.append('dispose'))
 monkeypatch.setattr(cli,'create_worker_engine',lambda c:engine)
 monkeypatch.setattr(cli,'verify_worker_role',lambda *args:events.append('role_verified'))
 def repo(e,c,id):config.append(c);return SimpleNamespace(config=c)
 monkeypatch.setattr(cli,'QueueRepository',repo)
 registration=SimpleNamespace(adapters={('fake','fake'):object()},credential_loader=object(),media_access=object())
 @asynccontextmanager
 async def runtime(e):
  events.append('native_enter')
  try:yield registration
  finally:events.append('native_exit')
 monkeypatch.setattr(cli,'native_runtime',runtime)
 class Worker:
  def __init__(self,repository,**kwargs):self.kwargs=kwargs;instances.append(self);events.append('construct')
  def stop(self):events.append('stop')
  async def run(self,*,once):events.append(('run',once))
  async def close(self):events.append('worker_close')
 monkeypatch.setattr(cli,'SocialWorker',Worker)
 loop=SimpleNamespace(add_signal_handler=lambda sig,fn:events.append(('add_signal',sig)),remove_signal_handler=lambda sig:events.append(('remove_signal',sig)))
 monkeypatch.setattr(cli.asyncio,'get_running_loop',lambda:loop)
 return SimpleNamespace(events=events,config=config,instances=instances,engine=engine,registration=registration,loop=loop)

@pytest.mark.parametrize('native,once',[(False,False),(False,True),(True,False),(True,True)])
def test_cli_opt_in_and_once_semantics(f,native,once):
 args=['--database-url','postgresql://inert:inert@127.0.0.1/inert']
 if native:args+=['--native-meta','--worker-role','inert_worker']
 if once:args+=['--once']
 assert cli.main(args)==0
 assert ('run',once) in f.events
 assert ('native_enter' in f.events) is native
 assert f.instances[0].kwargs['adapters']==(f.registration.adapters if native else None)
 assert f.events[-1]=='dispose'
 assert f.events.index('worker_close') < f.events.index('dispose')
 if native:assert f.events.index('worker_close')<f.events.index('native_exit')<f.events.index('dispose')

def test_native_flag_cannot_succeed_when_registration_is_disabled(f,monkeypatch,caplog):
 @asynccontextmanager
 async def disabled(e):yield None
 monkeypatch.setattr(cli,'native_runtime',disabled)
 with caplog.at_level(logging.ERROR):assert cli.main(['--database-url','postgresql://inert@127.0.0.1/inert','--native-meta','--worker-role','inert_worker','--once'])==1
 assert not f.instances and f.events==['role_verified','dispose']
 assert 'WORKER_UNAVAILABLE' in caplog.text

def test_partial_signal_installation_removes_first_and_closes_all(f):
 count=0
 def add(sig,fn):
  nonlocal count
  count+=1
  if count==2:raise RuntimeError('PRIVATE_SIGNAL_MARKER')
  f.events.append(('add_signal',sig))
 f.loop.add_signal_handler=add
 assert cli.main(['--database-url','postgresql://inert@127.0.0.1/inert','--native-meta','--worker-role','inert_worker','--once'])==1
 assert len([x for x in f.events if isinstance(x,tuple) and x[0]=='remove_signal'])==1
 assert f.events[-3:]==['worker_close','native_exit','dispose']

def test_worker_failure_is_logged_sanitized_and_cleanup_runs(f,caplog):
 original=cli.SocialWorker
 class Bad(original):
  async def run(self,*,once):raise RuntimeError('PRIVATE_WORKER_MARKER')
 cli.SocialWorker=Bad
 try:
  with caplog.at_level(logging.ERROR):assert cli.main(['--database-url','postgresql://inert@127.0.0.1/inert','--native-meta','--worker-role','inert_worker','--once'])==1
 finally:cli.SocialWorker=original
 assert 'PRIVATE_WORKER_MARKER' not in caplog.text
 assert f.events[-3:]==['worker_close','native_exit','dispose']

def test_worker_cancellation_propagates_after_cleanup(f,monkeypatch):
 original=cli.SocialWorker
 class Cancel(original):
  async def run(self,*,once):raise asyncio.CancelledError()
 monkeypatch.setattr(cli,'SocialWorker',Cancel)
 with pytest.raises(asyncio.CancelledError):cli.main(['--database-url','postgresql://inert@127.0.0.1/inert','--native-meta','--worker-role','inert_worker','--once'])
 assert f.events[-3:]==['worker_close','native_exit','dispose']

def test_signal_removal_failure_still_closes_worker_and_native_resources(f):
 def fail(sig):
  f.events.append(('remove_signal',sig))
  raise RuntimeError('PRIVATE_SIGNAL_REMOVAL_MARKER')
 f.loop.remove_signal_handler=fail
 assert cli.main(['--database-url','postgresql://inert@127.0.0.1/inert','--native-meta','--worker-role','inert_worker','--once'])==1
 assert 'worker_close' in f.events
 assert f.events[-1]=='dispose'
 assert len([x for x in f.events if isinstance(x,tuple) and x[0]=='remove_signal'])==2

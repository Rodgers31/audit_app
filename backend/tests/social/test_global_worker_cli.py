"""CLI acquires before native construction; closure failures never attest drain."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from social.worker import __main__ as cli
from social.worker.ownership import AuthorityLost, acquire_authority
from social.worker.role_contract import install_worker_role
from worker_ownership_support import role_database
from uuid import uuid4


@pytest.mark.parametrize('failure',[None,'startup','close','worker','dispose','cancel'])
def test_cli_native_once_acquires_and_retains_owner_without_unsafe_closure_receipt(role_database,monkeypatch,caplog,failure):
    owner,worker,schema,role=role_database
    install_worker_role(owner,role,schema)
    monkeypatch.setenv('INERT_WORKER_DSN',worker.url.render_as_string(hide_password=False))
    monkeypatch.setattr(cli,'create_worker_engine',lambda config:worker)
    monkeypatch.setattr(cli,'validate_worker_native_environment',lambda values:None)
    events=[]
    @asynccontextmanager
    async def native(engine):
        # This is the actual database owner, before any fake provider client.
        with owner.connect() as conn:
            assert conn.execute(text('SELECT count(*) FROM social_worker_runtime_ownership')).scalar_one()==1
        events.append('provider_construct')
        if failure=='startup':raise RuntimeError('PRIVATE_SDK_SECRET')
        try:
            yield SimpleNamespace(adapters={},credential_loader=None,media_access=None)
        finally:
            events.append('provider_close')
            if failure=='close':raise RuntimeError('PRIVATE_SDK_CLOSE')
    monkeypatch.setattr(cli,'native_runtime',native)
    if failure in ('worker','cancel'):
        async def fail(self,**kwargs):
            if failure=='cancel':raise asyncio.CancelledError('PRIVATE_CANCEL_SECRET')
            raise RuntimeError('PRIVATE_RUN_SECRET')
        monkeypatch.setattr(cli.SocialWorker,'run',fail)
    if failure=='dispose':
        monkeypatch.setattr(worker,'dispose',lambda:(_ for _ in ()).throw(RuntimeError('PRIVATE_DISPOSE_SECRET')))
    read_fd,write_fd=os.pipe();os.set_blocking(read_fd,False)
    try:
        result=cli.main(['--database-url-env','INERT_WORKER_DSN','--worker-role',role,'--database-schema',schema,
                         '--native-meta','--once','--supervisor-receipt-fd',str(write_fd)])
        os.close(write_fd);write_fd=None
        raw=os.read(read_fd,4096)
        if failure is None:
            assert result==0 and json.loads(raw)['claims_drained'] is True
        else:
            assert result==1 and raw==b''
        assert 'PRIVATE_' not in caplog.text
        with pytest.raises(AuthorityLost):acquire_authority(owner,uuid4(),'successor-after-exit')
        assert events[0]=='provider_construct'
    finally:
        os.close(read_fd)
        if write_fd is not None:os.close(write_fd)
        if failure=='dispose':monkeypatch.undo();worker.dispose()


def test_plain_diagnostic_is_once_zero_target_only_and_never_acquires(role_database,monkeypatch):
    owner,_,_,_=role_database
    monkeypatch.setattr(cli,'create_worker_engine',lambda config:owner)
    monkeypatch.setattr(cli,'native_runtime',lambda *a:pytest.fail('Diagnostic constructed provider'))
    monkeypatch.setattr(cli,'acquire_authority',lambda *a:pytest.fail('Diagnostic acquired authority'))
    args=['--database-url-env','INERT_DIAGNOSTIC_DSN']
    monkeypatch.setenv('INERT_DIAGNOSTIC_DSN',owner.url.render_as_string(hide_password=False))
    assert cli.main(args)==1
    assert cli.main(args+['--once'])==0
    from test_queue_postgres import seed
    with owner.begin() as conn:conn.execute(text('DELETE FROM social_controls'))
    seed(owner)
    assert cli.main(args+['--once'])==1


def test_real_signal_wakes_the_sixty_second_idle_selector(role_database,tmp_path):
    import select,subprocess,sys
    from pathlib import Path
    owner,worker,schema,role=role_database
    install_worker_role(owner,role,schema)
    gate_read,gate_write=os.pipe()
    script=r'''
import asyncio,os,sys
from contextlib import asynccontextmanager
from types import SimpleNamespace
from social.worker import __main__ as cli
class Policy(asyncio.DefaultEventLoopPolicy):
 def new_event_loop(self):
  loop=super().new_event_loop();original=loop._selector.select;armed=True
  def select(timeout=None):
   nonlocal armed
   if armed and timeout is not None and timeout>10:
    armed=False;print('IDLE_SELECTOR_BARRIER',flush=True)
    os.read(int(os.environ['TEST_GATE_FD']),1)
   return original(timeout)
  loop._selector.select=select
  return loop
asyncio.set_event_loop_policy(Policy())
@asynccontextmanager
async def native(engine):yield SimpleNamespace(adapters={},credential_loader=None,media_access=None)
cli.native_runtime=native
cli.validate_worker_native_environment=lambda values:None
if os.environ.get('TEST_DISABLE_WAKEUP')=='true':
 cli.os.write=lambda fd,data:len(data)
raise SystemExit(cli.main(['--database-url-env','TEST_DSN','--worker-role',os.environ['TEST_ROLE'],
 '--database-schema',os.environ['TEST_SCHEMA'],'--native-meta']))
'''
    env={**os.environ,'TEST_DSN':worker.url.render_as_string(hide_password=False),'TEST_SCHEMA':schema,
         'TEST_ROLE':role,'TEST_GATE_FD':str(gate_read),
         'PYTHONPATH':str(Path(cli.__file__).resolve().parents[2])+(os.pathsep+os.environ['PYTHONPATH'] if os.environ.get('PYTHONPATH') else '')}
    child=subprocess.Popen([sys.executable,'-c',script],env=env,pass_fds=(gate_read,),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        ready,_,_=select.select([child.stdout],[],[],8)
        assert ready and child.stdout.readline().strip()=='IDLE_SELECTOR_BARRIER'
        child.terminate()
        os.write(gate_write,b'continue')
        out,err=child.communicate(timeout=4)
        assert child.returncode==0,out+err
    finally:
        os.close(gate_read);os.close(gate_write)
        if child.poll() is None:child.kill();child.wait()


@pytest.mark.parametrize('failure',['pipe_setup','dispose_cancel'])
def test_pipe_setup_and_dispose_cancellation_restore_handlers_and_close_fds(monkeypatch,caplog,failure):
    import signal
    original_pipe=os.pipe;original_set_blocking=os.set_blocking;created=[]
    handlers={sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT)}
    def tracked_pipe():
        pair=original_pipe();created.extend(pair);return pair
    monkeypatch.setattr(cli.os,'pipe',tracked_pipe)
    if failure=='pipe_setup':
        monkeypatch.setattr(cli.os,'set_blocking',lambda *args:(_ for _ in ()).throw(OSError('PRIVATE_PIPE_SECRET')))
    else:
        def cancel():raise asyncio.CancelledError('PRIVATE_DISPOSE_CANCEL')
        monkeypatch.setattr(cli,'create_worker_engine',lambda config:SimpleNamespace(dispose=cancel))
    assert cli.main(['--database-url','postgresql://inert@localhost/inert','--once'])==1
    assert len(created)==2
    for fd in created:
        with pytest.raises(OSError):os.fstat(fd)
    assert {sig:signal.getsignal(sig) for sig in handlers}==handlers
    assert 'PRIVATE_' not in caplog.text

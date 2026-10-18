"""Observed review regressions; no credentials, remote services or application effects."""
import json
import os
import signal
import sys
import hashlib
import subprocess
import time
from uuid import UUID

import pytest
from sqlalchemy import create_engine,select
from social.recovery_operator import main
from social.recovery_database import _dump_snapshot,DatabaseRecoveryError
from social.connections.models import SocialCredential
from social.service import SocialError
from test_privacy_workflow import setup,approve,APPROVER
from test_privacy_support import db,config,graph

CANARY='INERT_RECOVERY_REVIEW_CANARY'


def test_unknown_operator_argument_never_echoes_private_input(capsys):
    escaped=None
    try:result=main(['rotate','--database-url-env','INERT_TARGET','--unexpected='+CANARY])
    except BaseException as error:escaped=error;result=None
    output=capsys.readouterr()
    assert escaped is None and result==1
    assert CANARY not in output.out+output.err
    assert json.loads(output.out)['code']=='RECOVERY_OPERATOR_REFUSED'


def test_operator_cleanup_failure_cannot_escape_or_print_success(monkeypatch,capsys):
    import social.recovery_operator as operator
    class Engine:
        def dispose(self):raise RuntimeError(CANARY)
    monkeypatch.setenv('INERT_TARGET','postgresql://inert@127.0.0.1:55420/inert')
    monkeypatch.setattr(operator,'create_engine',lambda *a,**kw:Engine())
    monkeypatch.setattr(operator,'read_private',lambda *a:b'x'*32)
    monkeypatch.setattr(operator,'verify_database_restore',lambda *a,**kw:{'status':'VERIFIED_BY_EXECUTION'})
    escaped=None
    try:result=main(['verify','--database-url-env','INERT_TARGET','--backup','/inert/backup','--manifest','/inert/manifest','--trusted-public-key','/inert/public'])
    except BaseException as error:escaped=error;result=None
    output=capsys.readouterr()
    assert escaped is None and result==1
    assert CANARY not in output.out+output.err
    assert json.loads(output.out)['code']=='RECOVERY_OPERATOR_REFUSED'


def test_export_refuses_detached_owned_descendant_and_reaps_it(tmp_path):
    program=tmp_path/'pg_dump';pidfile=tmp_path/'detached.pid';destination=tmp_path/'backup'
    program.write_text('#!'+sys.executable+'\nimport os,pathlib,subprocess,sys\np=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)\npathlib.Path('+repr(str(pidfile))+').write_text(str(p.pid))\nos.write(1,b"PGDMP")\n')
    program.chmod(0o700)
    engine=create_engine('postgresql://inert@127.0.0.1:55420/inert')
    escaped=None
    try:
        try:_dump_snapshot(engine,'00000001-00000001-1','public',destination,program)
        except BaseException as error:escaped=error
        assert isinstance(escaped,DatabaseRecoveryError)
        assert not destination.exists()
        if pidfile.exists():
            pid=int(pidfile.read_text())
            with pytest.raises(ProcessLookupError):os.kill(pid,0)
        else:assert sys.platform!='linux'
    finally:
        if pidfile.exists():
            try:os.kill(int(pidfile.read_text()),signal.SIGKILL)
            except ProcessLookupError:pass
        engine.dispose()


def test_dump_success_requires_owned_tree_closed_and_supported_host(tmp_path):
    program=tmp_path/'pg_dump';destination=tmp_path/'backup'
    program.write_text('#!'+sys.executable+'\nimport os\nos.write(1,b"PGDMP")\n');program.chmod(0o700)
    engine=create_engine('postgresql://inert@127.0.0.1:55420/inert')
    try:
        if sys.platform!='linux':
            with pytest.raises(DatabaseRecoveryError):_dump_snapshot(engine,'00000001-00000001-1','public',destination,program)
            assert not destination.exists()
        else:
            digest=_dump_snapshot(engine,'00000001-00000001-1','public',destination,program)
            assert digest==hashlib.sha256(b'PGDMP').hexdigest() and destination.read_bytes()==b'PGDMP'
    finally:engine.dispose()


@pytest.mark.parametrize('mode',['deadline','interrupt'])
def test_guardian_deadline_and_interrupt_reap_owned_child(tmp_path,mode):
    if sys.platform!='linux':
        from social.recovery_process import supervise
        assert supervise([sys.executable,'-c','raise SystemExit(0)'])==1
        return
    import social.recovery_process as guardian
    pidfile=tmp_path/'owned.pid'
    child='import os,pathlib,time;pathlib.Path('+repr(str(pidfile))+').write_text(str(os.getpid()));time.sleep(30)'
    code='import runpy,sys;g=runpy.run_path('+repr(guardian.__file__)+');sys.exit(g["supervise"]([sys.executable,"-c",'+repr(child)+'],lifetime=1))'
    process=subprocess.Popen([sys.executable,'-I','-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        end=time.monotonic()+3
        while not pidfile.exists() and time.monotonic()<end:time.sleep(.01)
        assert pidfile.exists()
        if mode=='interrupt':process.terminate()
        stdout,stderr=process.communicate(timeout=5)
        assert process.returncode==1 and not stdout and not stderr
        with pytest.raises(ProcessLookupError):os.kill(int(pidfile.read_text()),0)
    finally:
        if process.poll() is None:process.kill();process.wait()


def test_reconcile_refuses_signed_wrong_policy_before_erasing(setup):
    svc,command,ledger=setup
    approved=approve(svc,command);plan=UUID(approved['id'])
    intent={'schema_version':1,'operation_id':approved['execution']['id'],'plan_id':approved['id'],'plan_hash':approved['plan_hash'],'policy_hash':'b'*64,'scope':approved['scope']}
    ledger.persist(intent)
    with pytest.raises(SocialError):svc.execute(APPROVER,plan,1)
    unknown=svc.get(plan)
    with pytest.raises(SocialError):svc.reconcile(APPROVER,plan,unknown['execution']['version'])
    with svc.db.begin():
        assert all(svc.cipher.decrypt(c.id,c.credential_kind,c.key_version,c.encrypted_bundle).get('privacy_erased') is not True for c in svc.db.scalars(select(SocialCredential)))

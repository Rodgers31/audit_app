"""Executable fail-closed operator and process custody guards."""
import os
from pathlib import Path
import signal
import subprocess
import time
import pytest
from sqlalchemy import create_engine
from social.recovery_database import _dump_snapshot,DatabaseRecoveryError
from social.recovery_operator import main
from social.privacy.private_io import read_private,write_private


def test_operator_without_explicit_target_cannot_discover_credentials(monkeypatch,capsys):
    monkeypatch.delenv('B15_NO_DATABASE',raising=False)
    assert main(['rotate','--database-url-env','B15_NO_DATABASE','--apply'])==1
    assert 'RECOVERY_OPERATOR_REFUSED' in capsys.readouterr().out


def test_exported_parent_cannot_leave_descendants_and_report_success(tmp_path):
    script=tmp_path/'pg_dump';pidfile=tmp_path/'child.pid';backup=tmp_path/'backup.dump'
    script.write_text('#!/bin/sh\nsleep 30 >/dev/null 2>&1 &\nprintf "%s" "$!" > '+str(pidfile)+'\nprintf PGDMP\n')
    script.chmod(0o700)
    engine=create_engine('postgresql+psycopg2://fixture@127.0.0.1:55392/fixture')
    try:
        with pytest.raises(DatabaseRecoveryError):_dump_snapshot(engine,'00000001-00000001-1','public',backup,script)
        assert not backup.exists()
        pid=int(pidfile.read_text())
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            result=subprocess.run(['ps','-o','stat=','-p',str(pid)],capture_output=True,text=True)
            if result.returncode!=0 or result.stdout.strip().startswith('Z'):break
            time.sleep(0.01)
        else:pytest.fail('Owned exporter descendant remains running')
    finally:
        if pidfile.exists():
            try:os.kill(int(pidfile.read_text()),signal.SIGKILL)
            except ProcessLookupError:pass
        engine.dispose()

@pytest.mark.parametrize('bad', ['symlink','shared','empty','oversize'])
def test_private_files_refuse_unknown_custody(tmp_path,bad):
    path=tmp_path/'private'
    write_private(path,b'private-inert')
    if bad=='symlink':
        other=tmp_path/'other';other.symlink_to(path);path=other
    if bad=='shared':path.chmod(0o644)
    if bad=='empty':path.write_bytes(b'')
    if bad=='oversize':path.write_bytes(b'x'*33)
    with pytest.raises((ValueError,OSError)):read_private(path,32)

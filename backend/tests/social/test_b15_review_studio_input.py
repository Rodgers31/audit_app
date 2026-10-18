"""Accept refusal or exact approved derivative, never mutable unapproved bytes."""
import json
import hashlib
import sys
import pytest
from pathlib import Path
import subprocess
from uuid import UUID

from sqlalchemy.orm import sessionmaker

from social.studio.models import RenderJob
from social.studio.runner import run_job
from social.studio.runtime import verified_bytes
from test_domain_support import db
from test_studio import enqueue, runtime, source


def test_changed_local_input_never_changes_admitted_approved_bytes(db, runtime, monkeypatch):
    factory = sessionmaker(bind=db.bind)
    legitimate = enqueue(db, runtime, source(db))
    legitimate_id = UUID(legitimate['id'])
    assert run_job(factory, runtime, legitimate_id) == 'ready'
    db.expire_all()
    approved_bytes = verified_bytes(runtime, db.get(RenderJob, legitimate_id))
    queued = enqueue(db, runtime, source(db))
    job_id = UUID(queued['id'])
    original_popen = subprocess.Popen
    launches = []
    def launch(args, *a, **kw):
        if any(str(arg).endswith('render_child.py') for arg in args):
            # A fixed runner may use an inherited immutable/pipe input instead.
            # Keep attacking the old mutable path; it must not alter ready bytes.
            directory_arg = next((str(arg) for arg in args if str(arg).endswith(str(job_id))), None)
            assert directory_arg is not None
            input_file = Path(directory_arg) / 'input.json'
            if input_file.exists():
                original = json.loads(input_file.read_text())
                input_file.write_text(json.dumps({**original, 'title': 'UNAPPROVED LOCAL TITLE'}))
            else:
                input_file.write_text(json.dumps({**queued['composition'], 'title': 'UNAPPROVED LOCAL TITLE'}))
            launches.append(True)
        return original_popen(args, *a, **kw)
    monkeypatch.setattr(subprocess, 'Popen', launch)
    state = run_job(factory, runtime, job_id)
    db.expire_all()
    row = db.get(RenderJob, job_id)
    assert launches == [True], 'hostile fixture must reach actual child launch'
    assert row.composition['title'] == 'Reviewed report'
    if state == 'ready':
        assert verified_bytes(runtime, row) == approved_bytes, 'Unapproved local input changed admitted derivative'
    else:
        assert state == 'failed' and row.sha256 is None


@pytest.mark.parametrize('attack', ['changed', 'empty', 'oversized', 'wrong_hash'])
def test_authenticated_pipe_failure_never_admits_derivative(db, runtime, monkeypatch, attack):
    queued = enqueue(db, runtime, source(db))
    job_id = UUID(queued['id'])
    original_popen = subprocess.Popen
    observed = []
    def launch(args, *a, **kw):
        if not any(str(arg).endswith('render_child.py') for arg in args):
            return original_popen(args, *a, **kw)
        if attack == 'wrong_hash':
            args = [*args[:-1], '0' * 64]
        process = original_popen(args, *a, **kw)
        stdin = process.stdin
        class AttackInput:
            def write(self, payload):
                observed.append(True)
                if attack == 'changed':
                    value = json.loads(payload)
                    value['composition']['title'] = 'UNAPPROVED PIPE TITLE'
                    payload = json.dumps(value).encode()
                    # Original diagnostic bytes stay in place: change-and-restore
                    # of that path cannot launder the child-consumed payload.
                elif attack == 'empty': payload = b''
                elif attack == 'oversized': payload = b'X' * 32769
                return stdin.write(payload)
            def close(self): stdin.close()
        process.stdin = AttackInput()
        return process
    monkeypatch.setattr(subprocess, 'Popen', launch)
    assert run_job(sessionmaker(bind=db.bind), runtime, job_id) == 'failed'
    db.expire_all()
    row = db.get(RenderJob, job_id)
    assert observed == [True]
    assert row.sha256 is None and row.inspection is None and row.approved_sha256 is None
    directory = runtime.directory(job_id)
    assert not (directory/'card-0.png').exists() and not (directory/'output.mp4').exists()
    assert json.loads((directory/'input.json').read_text())['title'] == 'Reviewed report'


@pytest.mark.parametrize('attack', ['empty','oversized','mismatch','malformed_authenticated'])
def test_real_child_refuses_invalid_bytes_before_output(tmp_path, runtime, attack):
    import social.studio.render_child as child
    raw = b'' if attack == 'empty' else b'X' * 32769 if attack == 'oversized' else b'{' if attack == 'malformed_authenticated' else b'{}'
    expected = hashlib.sha256(raw).hexdigest() if attack != 'mismatch' else '0'*64
    work = tmp_path / attack; work.mkdir(mode=0o700)
    result = subprocess.run([sys.executable, '-I', '-B', child.__file__,str(work),runtime.ffmpeg,expected],input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,timeout=5)
    assert result.returncode != 0
    assert not list(work.iterdir())

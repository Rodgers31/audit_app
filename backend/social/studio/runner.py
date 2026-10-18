"""One-shot local renderer; never imported or run by the delivery worker."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import UUID, uuid4

from sqlalchemy import select

from ..media.config import MediaConfig
from ..media.inspection import LocalInspector
from ..models import SocialAuditEvent, SocialPostRevision
from ..contracts import canonical_json
from ..service import SocialError, utc
from .contracts import Composition
from .models import RenderJob
from .integrity import bound_composition
from .runtime import MAX_BYTES, TIMEOUT, verified_bytes
from .service import studio_lock


def run_job(factory, runtime, job_id):
    """A committed claim precedes CPU work; cancellation wins the final CAS.

    Interrupted claims remain visible until the explicit recover command. They
    are never automatically retried and output directories are never reused.
    """
    runtime.require()
    token = uuid4()
    with factory() as db, db.begin():
        studio_lock(db)
        row = db.scalar(select(RenderJob).where(RenderJob.id == job_id).with_for_update())
        if row is None or row.state != 'queued' or row.cancel_requested:
            raise SocialError('RENDER_NOT_QUEUED', 'The render job is not queued.')
        if db.scalar(select(RenderJob.id).where(RenderJob.state == 'running').limit(1)):
            raise SocialError('RENDER_BUSY', 'Another local render retains execution ownership.')
        spec = bound_composition(db, row)
        revision = db.get(SocialPostRevision, row.revision_id)
        payload = canonical_json({'composition': spec.model_dump(mode='json'),
            'revision_hash': revision.content_hash}).encode('utf-8')
        input_hash = row.input_hash
        if len(payload) > 32768 or hashlib.sha256(payload).hexdigest() != input_hash:
            raise SocialError('RENDER_INTEGRITY', 'The child input differs from its approved source.')
        row.state, row.token, row.started_at = 'running', token, datetime.now(timezone.utc)
        row.version += 1
    process, error, inspection, runtime_hash = None, None, None, None
    cancelled = False
    try:
        directory = runtime.directory(job_id)
        directory.mkdir(mode=0o700, exist_ok=False)
        (directory / 'input.json').write_text(spec.model_dump_json())
        runtime_hash = runtime.fingerprint()
        with (directory / 'tool.log').open('xb') as errors:
            process = subprocess.Popen([sys.executable, '-I', '-B', str(Path(__file__).with_name('render_child.py')), str(directory), runtime.ffmpeg, input_hash], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors, start_new_session=True, env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
            # The child consumes these authenticated bytes once. The retained
            # input.json is diagnostic only and is never rendered.
            try:
                process.stdin.write(payload)
            finally:
                process.stdin.close()
            deadline = time.monotonic() + TIMEOUT
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Bounded render elapsed')
                with factory() as db:
                    current = db.get(RenderJob, job_id)
                    if current is None or current.token != token or current.state != 'running':
                        raise RuntimeError('Render execution ownership changed')
                    cancelled = bool(current.cancel_requested)
                if cancelled:
                    raise InterruptedError('Render cancelled')
                time.sleep(0.25)
            if process.returncode != 0:
                raise RuntimeError('Local rendering tool failed')
        path = directory / ('output.mp4' if spec.kind == 'video' else 'card-0.png')
        size = path.stat().st_size
        inspector = LocalInspector(MediaConfig(ffprobe_path=runtime.ffprobe))
        result = inspector.inspect(path, 'video/mp4' if spec.kind == 'video' else 'image/png', size)
        inspection = asdict(result)
        if (result.width, result.height) != (720, 1280) or size > MAX_BYTES:
            raise RuntimeError('Unexpected derivative dimensions/size')
        if spec.kind == 'video' and abs(result.duration_ms - sum(s.seconds for s in spec.scenes) * 1000) > 100:
            raise RuntimeError('Unexpected derivative duration')
        if runtime.fingerprint() != runtime_hash:
            raise RuntimeError('Renderer source or runtime changed during execution')
    except InterruptedError:
        error = 'Render cancelled; no derivative was admitted.'
    except Exception as exc:
        # Fixed public error; tool stderr remains local/private and bounded.
        error = 'Local render or inspection failed (' + type(exc).__name__ + '). No derivative was admitted.'
    finally:
        if process is not None:
            # Kill the entire owned session, including a tool surviving its parent.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    with factory() as db, db.begin():
        studio_lock(db)
        row = db.scalar(select(RenderJob).where(RenderJob.id == job_id).with_for_update())
        if row is None or row.token != token or row.state != 'running':
            raise SocialError('RENDER_OWNERSHIP_LOST', 'Execution result retained locally; job ownership changed.')
        bound_composition(db, row)
        cancelled = cancelled or bool(row.cancel_requested)
        row.state = 'cancelled' if cancelled else 'failed' if error else 'ready'
        row.safe_error = error
        row.finished_at = datetime.now(timezone.utc)
        row.version += 1
        if row.state == 'ready':
            row.inspection, row.sha256, row.runtime_hash = inspection, inspection['sha256'], runtime_hash
        db.add(SocialAuditEvent(actor_kind='renderer', action='render.' + row.state, details={'job_id': str(row.id), 'input_hash': row.input_hash, 'sha256': row.sha256}, request_id=str(token)))
        return row.state


def recover_interrupted(factory, job_id, now=None):
    """Terminal failure only after OS CPU/wall limits; never requeue or clear history."""
    now = now or datetime.now(timezone.utc)
    with factory() as db, db.begin():
        studio_lock(db)
        row = db.scalar(select(RenderJob).where(RenderJob.id == job_id).with_for_update())
        if not row or row.state != 'running' or not row.started_at or now < utc(row.started_at) + timedelta(seconds=TIMEOUT + 60):
            raise SocialError('RENDER_RECOVERY_REFUSED', 'A running render must exceed its bounded execution and reap window.')
        row.state, row.finished_at = 'failed', now
        row.safe_error = 'Interrupted render retained; create a changed composition after inspection. No automatic retry.'
        row.version += 1
        db.add(SocialAuditEvent(actor_kind='operator', action='render.interrupted', details={'job_id': str(row.id), 'token': str(row.token)}, request_id=str(uuid4())))

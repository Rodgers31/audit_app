"""Run the original workflow phases against real owned v2 routes and PostgreSQL."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from acceptance_backend_config import OFF as DISABLED_CONTROLS
from acceptance_refresh import PATHS, ROOT
from acceptance_refresh_v2 import PREFIX, PROTOCOL
from common import Refusal, canonical
from operational import observe_local
from record import reap
from test_acceptance_refresh_v2 import private
from tests.test_refresh_current_run_postgres import fixture_db  # noqa: F401


TOOL = Path(__file__).resolve().parent
WORKFLOW = ROOT / 'scripts/verification/nightly_workflow/refresh.py'
OFF = {'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1', 'ENVIRONMENT': 'test',
       'REDIS_URL': '', 'DATABASE_URL': 'sqlite://', 'SECRET_BACKEND': 'env',
       'SECRET_KEY': 'inert-loopback-application-fixture', 'WEB_CONCURRENCY': '2',
       **dict.fromkeys(DISABLED_CONTROLS, 'false')}


def proc_identity(pid):
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()
    return f'{pid}:{fields[19]}'


def kernel_snapshot(supervisor, port):
    proc = Path(f'/proc/{supervisor}')
    children = (proc / f'task/{supervisor}/children').read_text().split()
    if len(children) != 2:
        raise ValueError('waiting for exact fixture children')
    master = proc_identity(supervisor)
    workers = sorted(proc_identity(int(pid)) for pid in children)
    listeners = {}
    for source in ('tcp', 'tcp6'):
        for row in Path('/proc/net', source).read_text().splitlines()[1:]:
            fields = row.split()
            if fields[3] == '0A' and int(fields[1].split(':')[1], 16) == port:
                listeners[int(fields[9])] = set()
    for path in Path('/proc').iterdir():
        if not path.name.isascii() or not path.name.isdigit():
            continue
        try:
            for descriptor in (path / 'fd').iterdir():
                try:
                    link = os.readlink(descriptor)
                except FileNotFoundError:
                    continue
                matched = re.fullmatch(r'socket:\[([0-9]+)\]', link)
                if matched and int(matched[1]) in listeners:
                    listeners[int(matched[1])].add(proc_identity(int(path.name)))
        except FileNotFoundError:
            continue
    if set().union(*listeners.values()) != {master, *workers}:
        raise ValueError('waiting for exact fixture listener holders')
    return {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'pid_namespace_inode': (proc / 'ns/pid').stat().st_ino,
            'supervisor': master, 'workers': workers,
            'listeners': [dict(port=port, inode=inode, holders=sorted(holders))
                          for inode, holders in sorted(listeners.items())]}


def ready(process, observe):
    deadline = time.monotonic() + 20
    while process.poll() is None and time.monotonic() < deadline:
        try:
            result = observe()
        except (OSError, ValueError):
            result = None
        if result:
            return result
        time.sleep(.1)
    raise RuntimeError('owned loopback server readiness failed')


def absent(port):
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', port))


def genuine_bundle(root, context, key_file, cached_frontend):
    cert, tls_key = root/'cert.pem', root/'tls-key.pem'
    env = {'PATH': os.environ['PATH'], 'HOME': str(root), 'TMPDIR': str(root), **OFF}
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1',
                    '-keyout', str(tls_key), '-out', str(cert)], check=True, capture_output=True, env=env, timeout=10)
    env.update(REVALIDATE_SECRET=key_file.read_text(encoding='utf-8'), SSL_CERT_FILE=str(cert))
    (root/'v2_fixture_app.py').write_text(
        'from fastapi import FastAPI\nfrom routers.cache_invalidation import router\n'
        'from cache.invalidation import register_local_cache\n'
        'app = FastAPI(); app.include_router(router)\nregister_local_cache("owned-probe", lambda: 0)\n')
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    backend_port = listener.getsockname()[1]
    backend = f'https://127.0.0.1:{backend_port}'
    generation = root/'generation'
    processes = []
    next_log = root/'next.log'
    try:
        with (root/'backend.log').open('xb') as backend_log, next_log.open('xb') as frontend_log:
            web = subprocess.Popen([sys.executable, '-m', 'gunicorn', 'v2_fixture_app:app',
                '--worker-class', 'uvicorn.workers.UvicornWorker', '--workers', '2', '--bind',
                f'fd://{listener.fileno()}', '--certfile', str(cert), '--keyfile', str(tls_key)],
                cwd=root, env=dict(env, PYTHONPATH=f'{root}:{ROOT / "backend"}', CACHE_GENERATION_FILE=str(generation),
                                   RENDER_GIT_COMMIT=context['source_sha']), start_new_session=True,
                stdout=backend_log, stderr=backend_log, pass_fds=(listener.fileno(),))
            processes.append(web)
            listener.close()
            before = ready(web, lambda: kernel_snapshot(web.pid, backend_port))
            next_route = subprocess.Popen(['node', str(TOOL/'refresh_v2_frontend_fixture.cjs'),
                str(ROOT/'frontend'), cached_frontend, str(cert), str(tls_key)], cwd=root,
                env=dict(env, VERCEL_GIT_COMMIT_SHA=context['source_sha']), start_new_session=True,
                stdout=frontend_log, stderr=frontend_log)
            processes.append(next_route)

            def read_ready():
                return next((json.loads(line[6:]) for line in next_log.read_text().splitlines()
                             if line.startswith('READY ')), None)

            frontend = ready(next_route, read_ready)
            assert frontend.pop('pid') == next_route.pid
            state, originals = root/'state.json', root/'private-wire.jsonl'
            producer_env = dict(env, RUNNER_TEMP=str(root), API_BASE_URL=backend, REVALIDATE_URL=frontend['url'],
                GITHUB_SHA=context['source_sha'], GITHUB_RUN_ID=context['run_id'], GITHUB_RUN_ATTEMPT=context['run_attempt'],
                REFRESH_NEEDS=json.dumps({'source_plan': {'outputs': {'plan_sha256': context['plan_sha256']}},
                                         'migrate': {'outputs': {'schema_head': context['schema_head']}}}))
            phase_files, ciphertext, exits = {}, [], {}
            started_at = int(time.time())
            for phase in ('backend', 'pages'):
                dest = root/f'{phase}.out'
                result = subprocess.run([sys.executable, '-B', str(WORKFLOW), phase, '--state', str(state),
                                         '--evidence', str(originals)], cwd=ROOT, capture_output=True,
                                        env=dict(producer_env, GITHUB_OUTPUT=str(dest)), timeout=45, umask=0o077)
                exits[phase] = result.returncode
                if result.returncode != 0:
                    messages = [line for line in result.stdout.decode().splitlines() if line.startswith('Refresh refused:')]
                    pytest.fail(f'original {phase} workflow child failed with status {result.returncode}: {messages}')
                ciphertext.extend(line for line in result.stdout.splitlines(keepends=True) if line.startswith(PREFIX))
                phase_files[phase] = private(root/f'{phase}-private.out', dest.read_bytes())
            finished_at = int(time.time())
            after = kernel_snapshot(web.pid, backend_port)
            assert before == after
            stat = generation.stat()
            assert originals.stat().st_mode & 0o077 == 0
            expected_tags = ['_N_T_' + p + ('/page' if '[' in p else '') for p in json.loads(PATHS.read_bytes())['paths']]

            def cache_effect():
                return next((json.loads(line[6:]) for line in next_log.read_text().splitlines()
                             if line.startswith('CACHE ')), None)

            observed_tags = ready(next_route, cache_effect)
            assert observed_tags == dict(tags=expected_tags, pathWasRevalidated=True)
            assert phase_files['pages']['sha256'] != phase_files['backend']['sha256']
            witness = dict(schema='nightly-refresh-local-witness-v2', context=context,
                           started_at=started_at, finished_at=finished_at, backend_origin=backend,
                           frontend=frontend, backend_before=before, backend_after=after,
                           generation=generation.read_text(), marker_identity=[stat.st_ino, stat.st_mtime_ns, stat.st_size],
                           backend_exit=exits['backend'], pages_exit=exits['pages'])
            bundle = dict(schema='nightly-refresh-v2-bundle-v1',
                          sealed=private(root/'sealed.log', b''.join(ciphertext)),
                          state=private(root/'private-state.json', state.read_bytes()),
                          backend_output=phase_files['backend'], pages_output=phase_files['pages'])
            # Keep only sealed evidence and the original transcript hash for import.
            transcript_hash = hashlib.sha256(originals.read_bytes()).hexdigest()
            originals.unlink()
            return bundle, witness, transcript_hash
    finally:
        listener.close()
        cleanup_errors = []
        for process in reversed(processes):
            try:
                if not reap(process)['group_absent']:
                    cleanup_errors.append('owned process group survived')
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                cleanup_errors.append(type(exc).__name__)
        try:
            absent(backend_port)
            if 'frontend' in locals():
                absent(urlsplit(frontend['url']).port)
        finally:
            tls_key.unlink(missing_ok=True)
            (root/'private-wire.jsonl').unlink(missing_ok=True)
        assert not cleanup_errors, cleanup_errors


@pytest.mark.parametrize('source_hold', [False, True], ids=['complete', 'required-source-hold'])
def test_actual_v2_workflow_and_semantic_entry_points(fixture_db, tmp_path, source_hold):
    from models import IngestionJob, IngestionStatus
    from seeding.current_run import PRIOR_STEPS, classify, plan_identity
    from seeding.source_plan import build_plan
    from tests.test_refresh_eligibility import audit_fixture

    cached_frontend = os.environ.get('REFRESH_V2_CACHED_FRONTEND')
    if cached_frontend is None:
        pytest.skip('exact cached Next runtime and owned Linux fixture explicitly required')
    engine, _ = fixture_db
    revision = 'a756b20a0001'
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE alembic_version(version_num varchar(32) PRIMARY KEY)'))
        connection.execute(text('INSERT INTO alembic_version VALUES (:revision)'), {'revision': revision})
    plan = build_plan(event='workflow_dispatch', schedule='', domain='', dry_run='false', cra='false',
                      opendata='false', discovery='false')
    commit = os.environ['REFRESH_V2_FIXTURE_COMMIT']
    now = datetime.now(timezone.utc)
    context = dict(floor=0, source_sha=commit, admitted_sha=commit, planned_sha=commit,
        schema_head=revision, planned_identity=plan_identity(plan), prior_success='true', cli_outcome='success',
        cli_executed='true', cli_exit='0', run_id='101', run_attempt='1', cli_run_id='101', cli_run_attempt='1',
        cli_floor='0', cli_started=(now-timedelta(minutes=45)).strftime('%Y-%m-%dT%H:%M:%SZ'),
        cli_finished=now.strftime('%Y-%m-%dT%H:%M:%SZ'), prior_job_status='success',
        prior_steps={name: {'outcome': 'success', 'conclusion': 'success', 'outputs': {}} for name in PRIOR_STEPS})
    with Session(engine) as db:
        if source_hold:
            job = db.scalar(select(IngestionJob).where(IngestionJob.domain == 'audits'))
            native, _, _ = audit_fixture()
            meta = dict(native[0].meta, execution_plan=job.meta['execution_plan'])
            job.meta, job.status, job.errors = meta, IngestionStatus(native[0].status), native[0].errors
            job.items_processed = job.items_updated = 4
            db.commit()
        jobs = list(db.scalars(select(IngestionJob).where(IngestionJob.id > context['floor'])
                               .order_by(IngestionJob.id.desc())))
        report = classify(jobs, plan, context)
    assert report['classification'] == ('required_source_incomplete' if source_hold else 'complete')
    wire = {key: report[key] for key in ('source_sha', 'plan_sha256', 'run_id', 'run_attempt', 'schema_head')}
    root = tmp_path.resolve()/'refresh-v2'
    root.mkdir(mode=0o700)
    key = root/'inert-signing-key'
    private(key, os.urandom(32).hex().encode())
    try:
        bundle, witness, transcript_hash = genuine_bundle(root, wire, key, cached_frontend)

        def put(name, value):
            return private(root/name, canonical(value))

        input_ref = put('semantic.json', dict(schema='nightly-semantic-local-input-v2', kind='full15',
            binding=dict(commit=commit, run_id=101, attempt=1), plan=put('plan.json', asdict(plan)),
            context=put('context.json', context), current_report=put('report.json', report),
            pg_schema=engine.info_acceptance['schema'], refresh=put('bundle.json', bundle),
            census=put('witness.json', witness), oag=[], fiscal=None))
        put('backend-config.json', dict(schema='nightly-backend-config-v1', plugins=['pytest_asyncio.plugin','acceptance_backend'],
            pg_url=os.environ['REFRESH_FIXTURE_PG_URL'], fixture_token=os.environ['REFRESH_FIXTURE_TOKEN'], original_family='none'))
        options = dict(backend_config=root/'backend-config.json', signing_key_file=key, expected_refresh_protocol=PROTOCOL)
        result = observe_local(root/input_ref['path'], **options)
        assert result['schema'] == 'nightly-semantic-local-observation-v2'
        assert result['production_accepted'] is False and result['current_run']['source_complete'] is (not source_hold)
        assert result['current_run']['cli_execution_proven'] is False
        assert result['refresh']['original_http_evidence_sha256'] == transcript_hash
        assert result['refresh']['worker_count'] == 2 and result['refresh']['cache_acknowledged'] is True
        assert result['fiscal'] is None and 'frozen-fiscal-debt-authority-schema' in result['holds']
        packet = json.loads((root/input_ref['path']).read_bytes())
        for field in ('admitted_sha', 'planned_sha'):
            packet['context'] = put(f'{field}-context.json', dict(context, **{field: '0'*40}))
            wrong = put(f'{field}-semantic.json', packet)
            with pytest.raises(Refusal, match='differs from actual PostgreSQL'):
                observe_local(root/wrong['path'], **options)
        for entry, flags in [('operational.py', ['--semantic-local']), ('ledger.py', ['check-semantic-local'])]:
            env = {'PATH': os.environ['PATH'], 'HOME': str(root), 'TMPDIR': str(root),
                   'PYTHONPATH': f'{TOOL}:{ROOT / "backend"}', **OFF}
            ambient_db = root/'unused-cli.sqlite'
            env['DATABASE_URL'] = f'sqlite:///{ambient_db}'
            cmd = [sys.executable, '-B', *(['-O'] if not __debug__ else []), str(TOOL/entry), *flags,
                   str(root/input_ref['path']), '--backend-config', str(options['backend_config']),
                   '--signing-key-file', str(key), '--require-refresh-v2']
            child = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=20)
            assert child.returncode == 0, child.stderr
            assert child.stdout.splitlines() == ['LOCAL_SEMANTIC_OBSERVATIONS_ONLY_OPERATIONAL_GATES_PENDING',
                                                 'OFFLINE_V2_HTTP_HMAC_AND_ACK_SEMANTICS_VERIFIED']
            assert not ambient_db.exists()
    finally:
        key.unlink(missing_ok=True)

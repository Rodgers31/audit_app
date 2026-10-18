"""Owned Linux rehearsal of the real shared API/native worker lifecycle.

Requires a locally built b15-worker-runtime image and cached postgres:17. Uses
only a Docker internal network, inert credentials, dedicated resource names,
loopback55390/33501, and fresh output outside the checkout. No cloud operations.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CASES = ('startup', 'idle', 'processing', 'closure', 'hardkill', 'containerkill', 'deadline', 'capacity')
THRESHOLDS = dict(memory_peak_bytes=460 * 1024 ** 2, abort_memory_bytes=480 * 1024 ** 2,
    hard_memory_bytes=512 * 1024 ** 2, cpu_limit=0.5, steady_mean_cpu=0.40,
    api_p95_seconds=1.0, api_max_seconds=3.0, worker_connections=2,
    duration_seconds=180, minimum_api_requests=100, minimum_published=3,
    local_drain_seconds=60, host_window_seconds=90, minimum_idle_seconds=65,
    busy_server_bytes=2_000_000, busy_client_bytes=4_000_000, idle_monthly_server_bytes=200_000_000,
    maximum_stop_seconds=75, minimum_busy_span_seconds=120)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    serialized = json.dumps(value, indent=2, allow_nan=False)
    with path.open('x') as stream:
        stream.write(serialized)
    require(path.read_text() == serialized, 'Receipt readback mismatch')


def inventory():
    files = subprocess.check_output(['git', 'ls-files', '-z', 'backend'], cwd=ROOT).decode().split('\0')
    paths = {ROOT / p for p in files if p}
    paths.update(HERE.glob('*.py'))
    paths.add(HERE / 'Dockerfile')
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)}


class Rehearsal:
    def __init__(self, out, duration, cases, *, optimized=False):
        require(type(optimized) is bool, 'Explicit interpreter mode required')
        require(type(duration) is int and 180 <= duration <= 900, 'Duration must be 180..900 seconds')
        require(type(cases) is list and cases and len(set(cases)) == len(cases)
                and all(case in CASES for case in cases), 'Explicit unique known cases required')
        require(type(out) is Path or isinstance(out, Path), 'Output path required')
        require('..' not in out.parts and out == out.resolve(), 'Canonical output path required')
        require(out.is_absolute() and not out.exists() and not out.is_relative_to(ROOT),
                'Fresh absolute output outside source required')
        require(not any(p.is_symlink() for p in [out, *out.parents]), 'Symlink output refused')
        require('.git' not in out.parts and not any((p / '.git').exists() for p in out.parents),
                'Output in a checkout or Git metadata refused')
        require(not (ROOT / '.env').exists() and not (ROOT / 'backend/.env').exists(),
                'Rehearsal source must contain no dotenv credentials')
        out.mkdir(parents=True)
        self.out, self.duration, self.cases = out, duration, cases
        self.source = inventory()
        self.provenance = dict(generated_by=str(Path(__file__).relative_to(ROOT)),
            generator_sha256=digest(Path(__file__)), source_inventory_sha256=hashlib.sha256(
                json.dumps(self.source, sort_keys=True).encode()).hexdigest())
        self.run_id = uuid4().hex[:12]
        self.network = 'b15-worker-' + self.run_id
        self.resources = []
        self.service = None
        self.results = []
        self.command_sequence = 0
        self.fixture = dict(SOCIAL_NATIVE_ENABLED='true', SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED='true',
            PYTHONOPTIMIZE='1' if optimized else '0',
            META_CONNECTIONS_ENABLED='true', META_APP_CONFIGURATION_VALIDATED='true',
            META_APP_ID='123', META_APP_SECRET='inert-rehearsal-app', META_ACCESS_MODE='owned_standard',
            META_REDIRECT_URIS='["https://admin.example.test/admin/social/accounts/callback"]',
            SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION='v1',
            SOCIAL_CREDENTIAL_KEYS=json.dumps({'v1': base64.urlsafe_b64encode(b'0' * 32).decode()}),
            META_PRIVACY_ENABLED='true', META_DEAUTHORIZATION_ENABLED='true',
            META_PRIVACY_STATUS_URL='https://admin.example.test/api/v1/social/privacy/meta/data-deletion/status',
            META_PRIVACY_SUBJECT_ACTIVE_KEY_VERSION='v1',
            META_PRIVACY_SUBJECT_KEYS=json.dumps({'v1': base64.urlsafe_b64encode(b'1' * 32).decode()}),
            SOCIAL_MEDIA_ENABLED='false', SOCIAL_WORKER_MEDIA_READS_ENABLED='true',
            SOCIAL_MEDIA_RETAINED_WRITES_ENABLED='false',
            SOCIAL_MEDIA_R2_ENDPOINT='https://' + 'a' * 32 + '.r2.cloudflarestorage.com',
            SOCIAL_MEDIA_BUCKET='media-test', SOCIAL_MEDIA_ACCESS_KEY='inert-rehearsal-access',
            SOCIAL_MEDIA_SECRET_KEY='inert-rehearsal-secret', AWS_EC2_METADATA_DISABLED='true')
        self.image = 'b15-worker-runtime:local'
        self.publish(out / 'predeclared.json', dict(generated_by=str(Path(__file__).relative_to(ROOT)),
            generator_sha256=digest(Path(__file__)), generated_at=datetime.now(timezone.utc).isoformat(),
            target_commit=self.cmd(['git', 'rev-parse', 'HEAD'], docker=False).strip(),
            run_id=self.run_id, source=self.source, thresholds=THRESHOLDS, duration=duration, cases=cases, optimized=optimized,
            fixture_environment=self.fixture,
            parity_limits=['Linux arm64 fixture; production architecture must be read back',
                'Owned direct PostgreSQL17 without TLS/pooler; protocol bytes are not billed egress',
                'Inert Graph/S3 over real TLS; no actual provider acceptance or closed-day cost',
                'No production data; local API route/data distribution is a declared fixture']))

    def publish(self, path, value):
        write_json(path, dict(value, provenance=dict(self.provenance,
            generated_at=datetime.now(timezone.utc).isoformat())))

    def cmd(self, args, *, docker=True, check=True, timeout=60):
        self.command_sequence += 1
        name = self.out / f'command-{self.command_sequence:04}.json'
        if docker and args[:2] == ['run', '--rm']:
            require(not any(a in ('--name', '--label', '-l') or a.startswith(('--name=', '--label='))
                            for a in args[2:]), 'Transient ownership overrides refused')
            args = [*args[:2], '--name', f'b15-worker-probe-{self.run_id}-{self.command_sequence}',
                    '--label', 'b15-worker-run=' + self.run_id, *args[2:]]
        command = (['docker'] if docker else []) + args
        # Containers receive only explicit -e arguments, never host env forwarding.
        host_env = {k: os.environ[k] for k in ('PATH', 'HOME', 'USER', 'TMPDIR') if k in os.environ}
        started = time.monotonic()
        try:
            process = subprocess.run(command, cwd=ROOT, env=host_env, capture_output=True,
                                     text=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            def decoded(value):
                return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
            self.publish(name, dict(argv=command, exit_code=None, state='TIMED_OUT',
                elapsed=time.monotonic() - started, stdout=decoded(error.stdout), stderr=decoded(error.stderr)))
            raise
        self.publish(name, dict(argv=command, exit_code=process.returncode, state='COMPLETED',
            elapsed=time.monotonic() - started, stdout=process.stdout, stderr=process.stderr))
        if check:
            require(process.returncode == 0, f'Command failed; retained {name}')
        return process.stdout

    def env(self, values):
        result = []
        for key, value in values.items():
            result += ['-e', key + '=' + value]
        return result

    def mounts(self):
        return ['-v', str(ROOT / 'backend') + ':/app:ro',
                '-v', str(HERE) + ':/harness:ro', '-v', str(self.out) + ':/evidence']

    def start(self, name, image, args, *, environment=None, extra=None):
        name = 'b15-worker-' + name + '-' + self.run_id
        output = self.cmd(['run', '-d', '--pull=never', '--name', name,
            '--label', 'b15-worker-run=' + self.run_id, '--network', self.network,
            *(extra or []), *self.env(environment or {}), image, *args])
        container_id = output.strip()
        require(re.fullmatch('[a-f0-9]{64}', container_id), 'Container identity unavailable')
        self.resources.append(container_id)
        return container_id

    def setup(self):
        for image in (self.image, 'postgres:17'):
            self.cmd(['image', 'inspect', image])
        self.cmd(['network', 'create', '--internal', '--label', 'b15-worker-run=' + self.run_id, self.network])
        self.db = self.start('db', 'postgres:17', ['-c', 'shared_preload_libraries=pg_stat_statements',
            '-c', 'pg_stat_statements.track=all', '-c', 'max_connections=30'],
            environment={'POSTGRES_HOST_AUTH_METHOD': 'trust'},
            extra=['--network-alias', 'b15-worker-db', '-p', '127.0.0.1:55390:5432'])
        for _ in range(60):
            if 'accepting connections' in self.cmd(['exec', self.db, 'pg_isready', '-U', 'postgres'], check=False):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError('Owned PostgreSQL did not become ready')
        self.cmd(['exec', self.db, 'psql', '-U', 'postgres', '-c',
            'CREATE ROLE b15_worker LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2'])
        (self.out / 'endpoint-delay').write_text('0')
        (self.out / 'endpoint-case').write_text('setup')
        self.endpoint = self.start('endpoint', self.image, ['python', '/harness/endpoints.py'],
                                  environment={'B15_ENDPOINT_RUN_ID': self.run_id}, extra=[*self.mounts(), '--network-alias', 'graph.facebook.com',
                                         '--network-alias', 'auth.fixture.test',
                                         '--network-alias', 'a' * 32 + '.r2.cloudflarestorage.com'])
        self.proxy = self.start('wire', self.image, ['python', '/harness/wire.py'],
                               extra=[*self.mounts(), '--network-alias', 'b15-worker-wire'])
        self.until(lambda: 'INERT_ENDPOINT_READY' in self.logs(self.endpoint), 15, 'TLS endpoint startup')

    def control(self, mode, database, *extra):
        raw = self.cmd(['run', '--rm', '--pull=never', '--network', self.network,
            *self.mounts(), *self.env(dict(self.fixture, PYTHONPATH='/app:/app/tests/social')),
            self.image, 'python', '/harness/control.py', mode, database, *extra])
        lines = [line.removeprefix('CONTROL_JSON:') for line in raw.splitlines() if line.startswith('CONTROL_JSON:')]
        require(len(lines) == 1, 'Exactly one control result required')
        return json.loads(lines[0])

    def launch(self, database, *, start_delay=0, close_delay=0, deadline=60, native=True, run_gate=False):
        values = dict(self.fixture, DATABASE_URL=f'postgresql+psycopg2://postgres@b15-worker-db:5432/{database}',
            SOCIAL_WORKER_DATABASE_URL=f'postgresql+psycopg2://b15_worker@b15-worker-wire:5432/{database}',
            SOCIAL_WORKER_ROLE='b15_worker', SOCIAL_WORKER_SUPERVISOR_ENABLED='true' if native else 'false',
            SOCIAL_WORKER_SHUTDOWN_SECONDS=str(deadline), RENDER_GIT_COMMIT=self.run_id,
            ENVIRONMENT='test', SECRET_KEY='inert-rehearsal-signing-key', AUTO_SEEDER_ENABLED='false',
            SUPABASE_URL='https://auth.fixture.test', SUPABASE_SERVICE_ROLE_KEY='inert-profile-service',
            SUPABASE_JWT_SECRET='inert-rehearsal-admin-jwt',
            REDIS_URL='', WEB_CONCURRENCY='1', PORT='33501',
            SSL_CERT_FILE='/evidence/ca.pem', AWS_CA_BUNDLE='/evidence/ca.pem',
            B15_REHEARSAL='isolated', B15_START_DELAY='0', B15_CLOSE_DELAY='0',
            B15_START_GATE='true' if start_delay else 'false',
            B15_CLOSE_GATE='true' if close_delay else 'false',
            B15_RUN_GATE='true' if run_gate else 'false',
            PYTHONPATH='/harness:/app:/app/tests/social')
        if not native:
            values['SOCIAL_NATIVE_ENABLED'] = 'false'
            values['SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED'] = 'false'
            values['SOCIAL_MEDIA_ENABLED'] = 'false'
        self.service = self.start(database, self.image, ['python', '-m', 'social_worker_supervisor'],
            environment=values, extra=[*self.mounts(), '--memory=512m', '--memory-swap=512m', '--cpus=0.5',
                                      '--network-alias', 'b15-worker-api',
                                      '-p', '127.0.0.1:33501:33501'])
        self.cmd(['inspect', self.service])  # resolved runtime config, resource limits and process identity

    def logs(self, container):
        return self.cmd(['logs', container])

    def events(self):
        values = []
        for line in self.logs(self.service).splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue  # Gunicorn/API prose is archived, never treated as a receipt.
            if type(row) is dict:
                values.append(row)
        return values

    def until(self, predicate, seconds, label):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.25)
        raise RuntimeError('Timed out: ' + label)

    def worker_pid(self):
        events = [e for e in self.events() if e.get('event') == 'social_supervisor_started']
        require(len(events) == 1 and type(events[0]['worker_pid']) is int, 'Exact owned child required')
        return events[0]['worker_pid']

    def worker_stage(self, stage):
        pid = self.worker_pid()
        return any(e.get('rehearsal_stage') == stage and e.get('pid') == pid for e in self.events())

    def api(self, route='/health/live', *, timings=False):
        script = '''import json,time,urllib.request
wall_start=time.time()
start=time.monotonic()
with urllib.request.urlopen('http://b15-worker-api:33501'+%r, timeout=3) as response:
 content=response.read(2*1024*1024)
 if response.status!=200 or not content: raise RuntimeError('Nonempty 200 required')
end=time.monotonic()
print(json.dumps(dict(started=start,completed=end,wall_started=wall_start,latency=end-start)))
''' % route
        raw = self.cmd(['run', '--rm', '--pull=never', '--network', self.network,
                        self.image, 'python', '-S', '-c', script], check=False)
        require(raw.strip(), 'API request failed')
        value = json.loads(raw.strip())
        return value if timings else value['latency']

    def ready(self):
        def check():
            try:
                self.api('/health/ready')
                return True
            except RuntimeError:
                return False  # Startup readiness is bounded; steady failures abort below.
        self.until(check, 90, 'actual API readiness')

    def uploads_off(self):
        script = '''import json,time,urllib.request,urllib.error
from uuid import uuid4
from jose import jwt
token=jwt.encode(dict(sub='11111111-1111-4111-8111-111111111111',aud='authenticated',exp=int(time.time())+60),
 'inert-rehearsal-admin-jwt',algorithm='HS256')
headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Idempotency-Key':str(uuid4())}
base='http://b15-worker-api:33501/api/v1/admin/social/media'
with urllib.request.urlopen(urllib.request.Request(base+'/capabilities',headers=headers),timeout=3) as response:
 value=json.load(response)
 if value['upload_available'] is not False: raise RuntimeError('HTTP upload available')
try:
 urllib.request.urlopen(urllib.request.Request(base+'/uploads',headers=headers,method='POST',
  data=json.dumps(dict(filename='inert.jpg',declared_mime_type='image/jpeg',declared_size=1)).encode()),timeout=3)
except urllib.error.HTTPError as error:
 value=json.load(error)
 if error.code!=503 or value['detail']['code']!='MEDIA_UNAVAILABLE': raise RuntimeError('Wrong upload refusal')
else: raise RuntimeError('HTTP upload was admitted')
print(json.dumps(dict(upload_available=False,upload_status=503)))
'''
        return json.loads(self.cmd(['run', '--rm', '--pull=never', '--network', self.network,
            *self.mounts(), '-e', 'SSL_CERT_FILE=/evidence/ca.pem', self.image, 'python', '-c', script]))

    def metrics(self):
        script = """import json,pathlib,psutil
p=pathlib.Path('/sys/fs/cgroup')
print(json.dumps(dict(memory=int((p/'memory.current').read_text()),peak=int((p/'memory.peak').read_text()),
 cpu=dict(line.split() for line in (p/'cpu.stat').read_text().splitlines()),
 oom=dict(line.split() for line in (p/'memory.events').read_text().splitlines()),
 processes=[dict(pid=x.pid,ppid=x.ppid(),argv=x.cmdline(),rss=x.memory_info().rss,threads=x.num_threads()) for x in psutil.process_iter()])))"""
        return json.loads(self.cmd(['exec', '-e', 'B15_REHEARSAL=', self.service, 'python', '-c', script]))

    def stop(self, *, repeated=False, startup=False, processing=False):
        start = time.monotonic()
        self.cmd(['kill', '--signal=TERM', self.service])
        if startup:
            require(not self.worker_stage('native_constructed'), 'Startup phase ended before TERM')
            (self.out / 'start-release').touch()
        if processing:
            (self.out / 'provider-release').touch()
        if repeated:
            self.until(lambda: self.worker_stage('native_closing'), 10, 'native closure')
            for sig in ('INT', 'TERM', 'INT'):
                self.cmd(['kill', '--signal=' + sig, self.service])
                self.signal_worker(sig)
            (self.out / 'close-release').touch()
        output = self.cmd(['wait', self.service], timeout=80)
        duration = time.monotonic() - start
        events = self.events()
        report = [e for e in events if e.get('event') == 'social_worker_unavailable']
        require(len(report) == 1, 'Exactly one launcher custody report required')
        inspection = json.loads(self.cmd(['inspect', self.service]))[0]
        require(inspection['State']['Running'] is False and inspection['State']['OOMKilled'] is False,
                'Container stop/OOM state unresolved')
        stops = [e for e in events if e.get('event') == 'social_supervisor_stopped']
        require(len(stops) == 1 and stops[0]['web_joined'] is True
                and 0 <= stops[0]['web_stop_seconds'] < 10
                and 0 < stops[0]['total_stop_seconds'] <= THRESHOLDS['maximum_stop_seconds'],
                'Measured web/reap headroom unavailable')
        # Docker wait confirms PID1 exit; process groups are attested only by the
        # real launcher after waitpid/subreaping. Preserve both independent layers.
        require(duration <= THRESHOLDS['maximum_stop_seconds'], 'Measured stop exceeds reserved host headroom')
        return dict(stop_seconds=duration, container_exit=int(output.strip()), report=report[0],
                    events=events, state=inspection['State'])

    def snapshot(self, case, stage, database, **context):
        result = self.control('census', database)
        if case == 'capacity':
            result['cohort'] = self.capacity_binding
        result.update(context)
        self.publish(self.out / f'{case}-{stage}.json', result)
        return result

    def run_case(self, case):
        database = 'b15_worker_' + case
        (self.out / 'endpoint-case').write_text(case)
        self.control('init', database)
        if case in ('processing', 'hardkill', 'containerkill', 'capacity'):
            seeded = self.control('seed', database, *(['image'] if case == 'capacity' else []))
            if case == 'capacity':
                self.capacity_binding = dict(run_id=self.run_id, case=case, target_id=seeded['target_id'],
                    media_paths=seeded['media_paths'], provider_paths=seeded['provider_paths'])
        (self.out / 'endpoint-delay').write_text('3' if case in ('processing', 'hardkill') else '0')
        if case in ('processing', 'hardkill', 'containerkill'):
            (self.out / 'provider-gated').touch()
        self.endpoint_offset = len(self.logs(self.endpoint).splitlines())
        self.launch(database, start_delay=3 if case == 'startup' else 0,
                    close_delay=3 if case == 'closure' else 10 if case == 'deadline' else 0,
                    deadline=60, run_gate=case in ('processing', 'hardkill', 'containerkill', 'capacity'))
        self.until(lambda: any(e.get('event') == 'social_supervisor_started' for e in self.events()), 10, 'supervisor')
        self.until(lambda: self.worker_stage('native_constructing' if case == 'startup' else 'native_constructed'),
                   30, 'real native worker startup')
        data = dict(case=case)
        if case != 'startup':
            self.ready()
            data['http_uploads'] = self.uploads_off()
            budgets = [e for e in self.events() if e.get('rehearsal_stage') == 'worker_budgets'
                       and e.get('pid') == self.worker_pid()]
            require(len(budgets) == 1 and all(type(budgets[0].get(key)) is int
                and budgets[0][key] == expected for key, expected in
                [('external_slots', 1), ('executor_threads', 2), ('pool_size', 2), ('max_overflow', 0)]),
                'Actual configured native worker budgets differ')
        if case == 'idle':
            before = self.snapshot(case, 'before', database)
            require(before['social_worker_heartbeats'][0]['state'] == 'idle', 'Actual idle heartbeat absent')
            wire_before = self.wire()
            time.sleep(THRESHOLDS['minimum_idle_seconds'])
            after = self.snapshot(case, 'steady', database)
            wire_after = self.wire()
            bytes_out = wire_after['server_bytes'] - wire_before['server_bytes']
            require(type(bytes_out) is int and 0 < bytes_out * (30 * 86400 / 65)
                    <= THRESHOLDS['idle_monthly_server_bytes'], 'Idle protocol egress budget failed')
            require(wire_after['peak_active'] <= 2, 'Observed worker connections exceeded two')
            data['idle'] = dict(seconds=65, before=before['statements'], after=after['statements'],
                                wire_before=wire_before, wire_after=wire_after)
        if case in ('processing', 'hardkill', 'containerkill'):
            (self.out / 'run-release').touch()
            def pending_provider():
                pending = self.snapshot_poll(database)['social_publish_attempts']
                requests = [json.loads(line) for line in self.logs(self.endpoint).splitlines()[self.endpoint_offset:]
                            if line.startswith('{')]
                started = {row['request_id'] for row in requests if row.get('method') == 'POST' and 'started' in row}
                completed = {row['request_id'] for row in requests if row.get('method') == 'POST' and 'completed' in row}
                return (any(row['completed_at'] is None for row in pending)
                        and bool(started - completed))
            self.until(pending_provider, 65, 'actual native provider request pending')
            if case == 'containerkill':
                self.cmd(['kill', '--signal=KILL', self.service])
                require(self.cmd(['wait', self.service]).strip() == '137', 'Actual container hard kill absent')
                require(not any(e.get('event') == 'social_worker_unavailable' for e in self.events()),
                        'Container hard kill fabricated launcher custody')
                after = self.snapshot(case, 'after', database)
                require(len(after['social_worker_runtime_ownership']) == 1
                        and any(r['completed_at'] is None for r in after['social_publish_attempts']),
                        'Hard-killed container lost sticky owner/unfinished intent')
                data.update(container_exit=137, release_proof=None,
                            contender=self.control('contender', database))
                self.results.append(data)
                (self.out / 'provider-release').touch()
                self.cmd(['rm', '-v', self.service])
                self.resources.remove(self.service)
                self.service = None
                for name in ('provider-gated', 'provider-release', 'run-release'):
                    (self.out / name).unlink(missing_ok=True)
                return
            if case == 'hardkill':
                self.signal_worker('KILL')
                self.until(lambda: any(e.get('event') == 'social_worker_unavailable' for e in self.events()), 10, 'hard-kill report')
                self.api()  # Actual Gunicorn remains responsive after native failure.
                (self.out / 'provider-release').touch()
        if case == 'capacity':
            data['capacity'] = self.capacity(database)
        data.update(self.stop(repeated=case == 'closure', startup=case == 'startup', processing=case == 'processing'))
        after = self.snapshot(case, 'after', database)
        require(len(after['social_worker_runtime_ownership']) == 1, 'Exit must retain exact authority')
        report = data['report']
        if case in ('hardkill', 'deadline'):
            require(report['release_proof'] is None, 'Killed worker fabricated positive closure')
            require(report['deadline_kill'] is (case == 'deadline') and report['group_joined'] is True,
                    'Expected forced/joined outcome absent')
        else:
            require(report['release_proof'] is not None and data['container_exit'] == 0,
                    'Real native resources did not close cleanly')
            proof = report['release_proof']
            held = after['social_worker_runtime_ownership'][0]
            require(proof['owner_id'] == held['owner_id'] and proof['generation'] == held['generation'],
                    'Pipe proof does not identify the actual retained authority')
        self.publish(self.out / (case + '-custody.json'), report)
        data['contender'] = self.control('contender', database)
        self.cmd(['rm', '-v', self.service])
        self.resources.remove(self.service)
        self.service = None
        if case == 'idle':
            # Roll back operationally to web-only while retaining the exact
            # owner/history. No schema downgrade, deletion or expiry is allowed.
            self.launch(database, native=False)
            self.ready()
            data['rollback_http_uploads'] = self.uploads_off()
            rollback = self.snapshot(case, 'web_only_rollback', database)
            require(rollback['social_worker_runtime_ownership'] == after['social_worker_runtime_ownership']
                and rollback['social_worker_runtime_history'] == after['social_worker_runtime_history'],
                'Web-only rollback changed ownership/history')
            self.cmd(['kill', '--signal=TERM', self.service])
            require(self.cmd(['wait', self.service], timeout=40).strip() == '0', 'Web-only rollback failed stop')
            require(not any(e.get('event') == 'social_supervisor_started' for e in self.events()),
                    'Default-off rollback started a native child')
            self.cmd(['rm', '-v', self.service])
            self.resources.remove(self.service)
            self.service = None
            data['release'] = self.control('release', database, '/evidence/idle-custody.json')
            self.launch(database)
            self.until(lambda: self.worker_stage('native_constructed'), 30, 'successor native construction')
            self.ready()
            data['successor'] = self.stop()
            successor = self.snapshot(case, 'successor_after', database)
            require(successor['social_worker_runtime_ownership'][0]['generation'] == 2
                and len(successor['social_worker_runtime_history']) == 3,
                'Successor did not preserve monotonic history')
            self.cmd(['rm', '-v', self.service])
            self.resources.remove(self.service)
            self.service = None
        self.results.append(data)
        for name in ('provider-gated', 'provider-release', 'close-release', 'start-release', 'run-release'):
            (self.out / name).unlink(missing_ok=True)

    def snapshot_poll(self, database):
        return self.control('census', database)

    def signal_worker(self, name):
        require(name in ('TERM', 'INT', 'KILL'), 'Known signal required')
        pid = self.worker_pid()
        self.cmd(['exec', self.service, 'python', '-S', '-c',
                  'import os,signal;os.kill(' + str(pid) + ',signal.SIG' + name + ')'])

    def wire(self):
        values = [json.loads(line) for line in self.logs(self.proxy).splitlines() if line.startswith('{')]
        require(values, 'No actual wire samples')
        return values[-1]

    def capacity(self, database):
        # Image first and two text publications share one Page's real permit.
        self.control('seed', database)
        self.control('seed', database)
        samples, latencies = [], []
        census_before = self.snapshot('capacity', 'baseline', database)
        require(not any(row['state'] == 'published' for row in census_before['social_post_targets']),
                'Capacity publication occurred before gated baseline')
        wire_before = self.wire()
        start = time.monotonic()
        # First county response and CPU sample precede admission. Linux monotonic
        # timestamps share the endpoint's kernel clock, unlike the host clock.
        first = self.api('/api/v1/counties', timings=True)
        latencies.append(first['latency'])
        require(first['latency'] <= THRESHOLDS['api_max_seconds'], 'API latency abort')
        wire_before['measurement_started'] = first['started']
        wire_before['wall_started'] = first['wall_started']
        baseline = self.metrics()
        baseline['elapsed'] = time.monotonic() - start
        samples.append(baseline)
        require(baseline['memory'] < THRESHOLDS['abort_memory_bytes']
                and int(baseline['oom']['oom_kill']) == 0, 'Initial memory/OOM abort')
        self.endpoint_offset = len(self.logs(self.endpoint).splitlines())
        (self.out / 'run-release').touch()
        next_seed = 25
        while time.monotonic() - start < self.duration:
            latency = self.api('/api/v1/counties')
            latencies.append(latency)
            require(latency <= THRESHOLDS['api_max_seconds'], 'API latency abort')
            if len(latencies) % 5 == 0:
                sample = self.metrics()
                sample['elapsed'] = time.monotonic() - start
                samples.append(sample)
                require(sample['memory'] < THRESHOLDS['abort_memory_bytes'], 'Memory abort')
                require(int(sample['oom']['oom_kill']) == 0, 'OOM abort')
            if time.monotonic() - start >= next_seed and next_seed <= 150:
                self.control('seed', database)
                next_seed += 25
            time.sleep(0.5)
        require(len(latencies) >= THRESHOLDS['minimum_api_requests'] and len(samples) >= 2,
                'Insufficient sustained workload')
        last = self.snapshot('capacity', 'steady', database, statements_before=census_before['statements'])
        from qualification import assess
        wire_after = self.wire()
        clock = json.loads(self.cmd(['exec', self.endpoint, 'python', '-S', '-c',
            'import json,time;print(json.dumps(dict(monotonic=time.monotonic(),wall=time.time())))']))
        wire_after['measurement_completed'] = clock['monotonic']
        wire_after['wall_completed'] = clock['wall']
        requests = [json.loads(line) for line in self.logs(self.endpoint).splitlines()[self.endpoint_offset:]
                    if line.startswith('{')]
        assessed = assess(samples, latencies, last, wire_before, wire_after, requests,
                          time.monotonic() - start, THRESHOLDS)
        return dict(seconds=time.monotonic() - start, samples=samples, api_latencies=latencies,
                    wire_before=wire_before, wire_after=wire_after, requests=requests, **assessed)

    def cleanup(self):
        errors = []
        volumes_removed = []
        owned = self.cmd(['ps', '-aq', '--no-trunc', '--filter', 'label=b15-worker-run=' + self.run_id]).split()
        escaped = [container for container in owned if container not in self.resources]
        if escaped:
            errors.append('Transient containers survived execution: ' + ', '.join(escaped))
        for container in reversed(list(dict.fromkeys([*self.resources, *escaped]))):
            try:
                meta = json.loads(self.cmd(['inspect', container]))[0]
                require(meta['Config']['Labels']['b15-worker-run'] == self.run_id, 'Cleanup ownership mismatch')
                volumes = [m['Name'] for m in meta['Mounts'] if m['Type'] == 'volume']
                self.cmd(['logs', container], check=False)
                self.cmd(['rm', '-f', '-v', container])
                require(not self.cmd(['ps', '-aq', '--filter', 'id=' + container]).strip(), 'Container survived cleanup')
                for volume in volumes:
                    require(not self.cmd(['volume', 'ls', '-q', '--filter', 'name=^' + volume + '$']).strip(),
                            'Owned data volume survived cleanup')
                    volumes_removed.append(volume)
            except Exception as error:
                errors.append(str(error))
        remaining = self.cmd(['ps', '-aq', '--filter', 'label=b15-worker-run=' + self.run_id])
        require(not remaining.strip(), 'Owned process cleanup unresolved')
        network = self.cmd(['network', 'inspect', self.network], check=False)
        if network.strip() != '[]':
            meta = json.loads(network)[0]
            require(meta['Labels']['b15-worker-run'] == self.run_id, 'Network ownership mismatch')
            self.cmd(['network', 'rm', self.network])
        return dict(errors=errors, owned_containers_absent=not remaining.strip(), volumes_removed=volumes_removed)

    def run(self):
        error = None
        try:
            self.setup()
            for case in self.cases:
                print('RUNNING ' + case, flush=True)
                self.run_case(case)
        except Exception as failure:
            error = str(failure)
        finally:
            cleanup = self.cleanup()
        unchanged = self.source == inventory()
        if [row['case'] for row in self.results] != self.cases:
            error = error or 'Required case inventory incomplete'
        artifacts = {str(p.relative_to(self.out)): digest(p) for p in sorted(self.out.rglob('*')) if p.is_file()}
        value = dict(generated_by=str(Path(__file__).relative_to(ROOT)), generator_sha256=digest(Path(__file__)),
            generated_at=datetime.now(timezone.utc).isoformat(), source=self.source, results=self.results,
            cleanup=cleanup, source_unchanged=unchanged, error=error,
            artifacts=artifacts,
            verdict='PASS' if not error and unchanged and not cleanup['errors'] else 'FAIL',
            scope='ISOLATED_LINUX_ONLY', production_accepted=False)
        self.publish(self.out / 'receipt.json', value)
        require(value['verdict'] == 'PASS', 'Rehearsal failed: ' + str(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--duration', type=int, default=180)
    parser.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES))
    parser.add_argument('--optimized', action='store_true', help='Execute native/control interpreters with PYTHONOPTIMIZE=1')
    args = parser.parse_args()
    Rehearsal(args.out, args.duration, args.cases, optimized=args.optimized).run()


if __name__ == '__main__':
    main()

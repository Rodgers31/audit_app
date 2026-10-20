"""Run the qualified capacity workload inside the copied root and SAME budget.

No shutdown signal is sent on success: Render must terminate the actual outer
supervisor when the operator restores the accepted deployment. Failures abort
only this deliberately selected maintenance fixture and produce no PASS.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from run import Rehearsal, THRESHOLDS, require
from bounded_profile import inert_environment
from custody import export
from qualification import assess, counter, integer, number
from isolation import post_exec


class HostRehearsal(Rehearsal):
    def __init__(self):
        self.out = Path('/evidence')
        self.duration = 180
        identity = json.loads((self.out / 'identity.json').read_text())
        self.run_id = identity['run_id']
        require(self.run_id == os.environ['B15_ENDPOINT_RUN_ID']
                and identity['manifest_sha256'] == hashlib.sha256(Path('/manifest.json').read_bytes()).hexdigest(),
                'Run/build identity differs')
        self.provenance = dict(generated_by='tools/worker_host_fixture/driver.py',
            generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), **identity)
        self.fixture = dict(os.environ)
        inert_environment(self.fixture)
        self.endpoint, self.proxy, self.service = 'endpoint', 'wire', 'supervisor'
        self.image, self.network = 'inert-fixed', 'private-loopback'
        seed = json.loads((self.out / 'image-seed.json').read_text())
        self.capacity_binding = dict(run_id=self.run_id, case='capacity', target_id=seed['target_id'],
            media_paths=seed['media_paths'], provider_paths=seed['provider_paths'])
        self.last_sequence = 0
        self.observer_sha256 = hashlib.sha256(Path('/host/observer.py').read_bytes()).hexdigest()
        self.plan = json.loads((self.out / 'capacity-plan.json').read_text())
        validate_plan(self.plan)

    def publish(self, path, value):
        require(path.parent == self.out and not path.exists() and not path.is_symlink(),
                'Fresh owned artifact required')
        data = json.dumps(dict(self.provenance, **value), default=str, allow_nan=False, indent=2)
        with path.open('x') as stream:
            stream.write(data)
        require(path.read_text() == data, 'Receipt readback mismatch')

    def mounts(self):
        return []

    def cmd(self, args, *, check=True, **_):
        # Inherited workload uses only Python payloads. There is no Docker,
        # shell, remote host, environment forwarding or user-supplied command.
        if args[:3] == ['exec', self.endpoint, 'python']:
            argv = args[2:]
        else:
            require(args[:5] == ['run', '--rm', '--pull=never', '--network', self.network]
                    and args.count(self.image) == 1, 'Private Python operation required')
            position = args.index(self.image)
            prefix = args[5:position]
            require(len(prefix) % 2 == 0 and all(prefix[i] == '-e' for i in range(0, len(prefix), 2)),
                    'Unknown controller option')
            override = dict(self.fixture)
            for index in range(0, len(prefix), 2):
                key, value = prefix[index+1].split('=', 1)
                override[key] = value
            inert_environment(override, controller=True)
            argv = args[position+1:]
        require(argv[:1] == ['python'] and (argv[1:3] == ['-S', '-c'] or argv[1:2] == ['-c'])
                and len(argv) in (3, 4) and len(argv[-1]) <= 16384, 'Fixed Python payload required')
        values = dict(self.fixture)
        values['B15_REHEARSAL'] = ''
        inert_environment(values, controller=True)
        result = subprocess.run([sys.executable, *argv[1:]], env=values, capture_output=True,
            text=True, timeout=10, close_fds=True, stdin=subprocess.DEVNULL)
        if check:
            require(result.returncode == 0, 'Private request failed')
        return result.stdout

    def control(self, mode, database, *extra):
        require(mode == 'census' and database == 'b15_worker_capacity' and not extra,
                'Fixed read-only census required; all writes are predeclared')
        tables = ('social_worker_runtime_ownership', 'social_worker_runtime_history',
                  'social_worker_heartbeats', 'social_post_targets', 'social_publish_attempts')
        pairs = ["'%s',(SELECT coalesce(json_agg(row_to_json(t)), '[]'::json) FROM %s t)" % (table, table)
                 for table in tables]
        pairs.append("'connections',(SELECT count(*) FROM pg_stat_activity "
                     "WHERE datname=current_database() AND usename='b15_worker')")
        pairs.append("'statements',(SELECT coalesce(json_agg(row_to_json(q)), '[]'::json) FROM "
            "(SELECT query,sum(calls)::bigint AS calls,sum(rows)::bigint AS rows,"
            "sum(total_exec_time) AS total_exec_time FROM stats.pg_stat_statements "
            "WHERE userid=(SELECT oid FROM pg_roles WHERE rolname='b15_worker') "
            "AND dbid=(SELECT oid FROM pg_database WHERE datname=current_database()) "
            "GROUP BY query ORDER BY query) q)")
        return self.sql('SELECT json_build_object(' + ','.join(pairs) + ')')

    def sql(self, query):
        require(type(query) is str and 0 < len(query) <= 16384, 'Bounded owned SQL required')
        raw = subprocess.check_output(['/usr/lib/postgresql/17/bin/psql', '-X', '-h', '127.0.0.2',
            '-U', 'postgres', '-d', 'b15_worker_capacity', '-v', 'ON_ERROR_STOP=1', '-At', '-c', query],
            env={'PATH':'/usr/bin:/bin', 'LANG':'C.UTF-8'}, stdin=subprocess.DEVNULL,
            text=True, timeout=10, close_fds=True)
        require(raw.strip() and len(raw) <= 4 * 1024 ** 2, 'Bounded nonempty SQL result required')
        return json.loads(raw)

    def capacity(self, database):
        require(database == 'b15_worker_capacity', 'Owned capacity database required')
        before = self.snapshot('capacity', 'baseline', database)
        require({row['id'] for row in before['social_post_targets']} == {row['target_id'] for row in self.plan}
                and all(row['state'] == 'queued' for row in before['social_post_targets']),
                'Exact preseeded unpublished cohort required')
        wire_before = self.wire()
        start = time.monotonic()
        first = self.api('/api/v1/counties', timings=True)
        latencies, samples = [first['latency']], []
        require(first['latency'] <= THRESHOLDS['api_max_seconds'], 'API latency abort')
        wire_before.update(measurement_started=first['started'], wall_started=first['wall_started'])
        sample = self.metrics()
        sample['elapsed'] = time.monotonic() - start
        samples.append(sample)
        require(sample['memory'] < THRESHOLDS['abort_memory_bytes'], 'Initial memory abort')
        scheduled = self.sql(schedule_sql(self.plan))
        validate_scheduled(self.plan, scheduled, wire_before['wall_started'], time.time())
        self.endpoint_offset = len(self.logs(self.endpoint).splitlines())
        (self.out / 'run-release').touch()
        while time.monotonic() - start < self.duration:
            latency = self.api('/api/v1/counties')
            latencies.append(latency)
            require(latency <= THRESHOLDS['api_max_seconds'], 'API latency abort')
            if len(latencies) % 5 == 0:
                sample = self.metrics()
                sample['elapsed'] = time.monotonic() - start
                samples.append(sample)
                require(sample['memory'] < THRESHOLDS['abort_memory_bytes'], 'Memory abort')
            time.sleep(.5)
        last = self.snapshot('capacity', 'steady', database, statements_before=before['statements'])
        wire_after = self.wire()
        wire_after.update(measurement_completed=time.monotonic(), wall_completed=time.time())
        requests = [json.loads(line) for line in self.logs(self.endpoint).splitlines()[self.endpoint_offset:]
                    if line.startswith('{')]
        duration = time.monotonic() - start
        self.publish(self.out / 'capacity-observations.json', dict(seconds=duration,
            samples=samples, api_latencies=latencies, census=last, wire_before=wire_before,
            wire_after=wire_after, requests=requests, eligibility_plan=self.plan,
            database_schedule=scheduled, verdict='UNASSESSED'))
        assessed = assess(samples, latencies, last, wire_before, wire_after, requests, duration, THRESHOLDS)
        return dict(seconds=duration, samples=samples, api_latencies=latencies, wire_before=wire_before,
            wire_after=wire_after, requests=requests, eligibility_plan=self.plan,
            database_schedule=scheduled, **assessed)

    def logs(self, name):
        require(name in ('endpoint', 'wire', 'supervisor'), 'Fixed owned log required')
        path = self.out / (name + '.log')
        require(path.stat().st_size <= 4 * 1024 ** 2, 'Log bound')
        return path.read_text()

    def metrics(self):
        value = json.loads((self.out / 'metrics.json').read_text())
        require(type(value) is dict and value['generator_sha256'] == self.observer_sha256
                and value['manifest_sha256'] == self.provenance['manifest_sha256']
                and value['run_id'] == self.run_id and type(value['sequence']) is int
                and value['sequence'] > self.last_sequence
                and 0 <= time.monotonic() - number(value['observed_at'], positive=True) <= 3,
                'Fresh source-bound external kernel sample required')
        require(0 < integer(value['memory']) <= integer(value['peak']) <= 512 * 1024 ** 2,
                'Measured memory invalid')
        require(type(value['cpu']) is dict and counter(value['cpu']['usage_usec']) >= 0
                and type(value['oom']) is dict and counter(value['oom']['oom_kill']) == 0,
                'Actual CPU/OOM counters required')
        require(type(value['processes']) is list and value['processes'], 'Actual process census required')
        pids = set()
        for process in value['processes']:
            require(type(process) is dict and integer(process['pid'], positive=True) not in pids
                    and integer(process['ppid']) >= 0 and integer(process['rss'], positive=True) > 0
                    and integer(process['threads'], positive=True) > 0
                    and type(process['argv']) is list and process['argv']
                    and all(type(arg) is str for arg in process['argv']), 'Invalid actual process observation')
            pids.add(process['pid'])
        self.last_sequence = value['sequence']
        return value


def qualified_capacity(result, uploads, *, run_id, manifest_sha256, observer_sha256, cohort, driver_sha256):
    import re
    require(type(run_id) is str and re.fullmatch('[0-9a-f]{12}', run_id)
            and all(type(s) is str and re.fullmatch('[0-9a-f]{64}', s)
                    for s in (manifest_sha256, observer_sha256, driver_sha256))
            and type(cohort) is dict and cohort.get('run_id') == run_id
            and cohort.get('case') == 'capacity', 'Expected current run/build/cohort required')
    require(type(result) is dict and type(uploads) is dict
            and uploads == {'upload_available': False, 'upload_status': 503}
            and uploads.get('upload_available') is False and type(uploads.get('upload_status')) is int,
            'Actual upload refusal required')
    require(type(result.get('samples')) is list and result['samples']
            and all(type(row) is dict and row.get('run_id') == run_id
                    and row.get('generator_sha256') == observer_sha256
                    and row.get('manifest_sha256') == manifest_sha256 for row in result['samples']),
            'Current kernel-observer scope required')
    census = result.get('census')
    require(type(census) is dict and census.get('run_id') == run_id
            and census.get('manifest_sha256') == manifest_sha256
            and census.get('generator_sha256') == driver_sha256
            and census.get('cohort') == cohort, 'Current census/cohort source binding required')
    validate_plan(result.get('eligibility_plan'))
    validate_target_cohort(result['eligibility_plan'], census['social_post_targets'],
        cohort['target_id'], result.get('database_schedule'))
    validate_scheduled(result['eligibility_plan'], result.get('database_schedule'),
        result['wire_before']['wall_started'], result['wire_after']['wall_completed'])
    # Re-evaluate the retained raw observations at publication; a missing or
    # truthy failed return from any producer is never a success artifact.
    assessed = assess(result['samples'], result['api_latencies'], result['census'],
        result['wire_before'], result['wire_after'], result['requests'], result['seconds'], THRESHOLDS)
    require(all(result.get(key) == value for key, value in assessed.items()), 'Capacity summary differs')
    return True


def validate_target_cohort(plan, targets, image_target, scheduled):
    from datetime import datetime
    validate_plan(plan)
    expected = {row['target_id'] for row in plan}
    require(plan[0]['target_id'] == image_target and type(targets) is list
            and len(targets) == len(plan)
            and all(type(row) is dict and type(row.get('id')) is str for row in targets)
            and {row['id'] for row in targets} == expected,
            'Exact unique actual plan/target cohort required')
    require(type(scheduled) is dict and type(scheduled.get('rows')) is list,
            'Actual schedule required')
    due = {row['id']: datetime.fromisoformat(row['next_action_at']) for row in scheduled['rows']}
    for row in targets:
        if row['state'] == 'published':
            require(type(row.get('published_at')) is str
                    and datetime.fromisoformat(row['published_at']) >= due[row['id']],
                    'Publication precedes actual target eligibility')


def validate_plan(plan):
    from uuid import UUID
    delays = (0, 0, 0, 25, 50, 75, 100, 125, 150)
    require(type(plan) is list and len(plan) == len(delays), 'Nine predeclared targets required')
    identities = []
    for row, delay in zip(plan, delays):
        require(type(row) is dict and set(row) == {'target_id', 'delay'}
                and type(row['delay']) is int and row['delay'] == delay
                and type(row['target_id']) is str and str(UUID(row['target_id'])) == row['target_id'],
                'Canonical actual target and exact due delay required')
        identities.append(row['target_id'])
    require(len(set(identities)) == len(delays), 'Unique actual targets required')


def schedule_sql(plan):
    validate_plan(plan)
    values = ','.join("('%s'::uuid,%d)" % (row['target_id'], row['delay']) for row in plan)
    return ("WITH moment AS MATERIALIZED (SELECT clock_timestamp() AS ts), "
        "input(id,delay) AS (VALUES " + values + "), changed AS ("
        "UPDATE social_post_targets t SET next_action_at=moment.ts+input.delay*interval '1 second' "
        "FROM input,moment WHERE t.id=input.id AND t.state='queued' RETURNING t.id,t.next_action_at) "
        "SELECT json_build_object('count',(SELECT count(*) FROM changed),'anchor',(SELECT ts FROM moment),"
        "'rows',(SELECT json_agg(row_to_json(changed)) FROM changed))")


def validate_scheduled(plan, result, window_start, window_end):
    from datetime import datetime, timedelta
    validate_plan(plan)
    require(type(result) is dict and set(result) == {'count', 'anchor', 'rows'}
            and type(result['count']) is int and result['count'] == len(plan)
            and type(result['anchor']) is str and type(result['rows']) is list
            and len(result['rows']) == len(plan), 'Actual complete schedule readback required')
    anchor = datetime.fromisoformat(result['anchor'])
    require(anchor.tzinfo is not None and number(window_start, positive=True) <= anchor.timestamp()
            <= number(window_end, positive=True), 'Schedule anchor outside actual measurement')
    expected = {row['target_id']: anchor + timedelta(seconds=row['delay']) for row in plan}
    seen = set()
    for row in result['rows']:
        require(type(row) is dict and set(row) == {'id', 'next_action_at'}
                and type(row['id']) is str and row['id'] in expected and row['id'] not in seen
                and type(row['next_action_at']) is str
                and datetime.fromisoformat(row['next_action_at']) == expected[row['id']],
                'Actual target eligibility readback differs')
        seen.add(row['id'])


def main():
    # No failure path may signal PID1 unless this process first proves it is
    # inside the immutable, nonroot, no-proc private fixture boundary.
    post_exec()
    try:
        rehearsal = HostRehearsal()
        rehearsal.until(lambda: (rehearsal.out / 'supervisor.log').exists()
            and any(e.get('event') == 'social_supervisor_started' for e in rehearsal.events()),
            15, 'actual supervisor')
        rehearsal.until(lambda: rehearsal.worker_stage('native_constructed'), 45, 'native construction')
        rehearsal.ready()
        uploads = rehearsal.uploads_off()
        result = rehearsal.capacity('b15_worker_capacity')
        # The shared capacity method persists its complete final census in the
        # steady snapshot, rather than duplicating it in the return value.
        result['census'] = json.loads((rehearsal.out / 'capacity-steady.json').read_text())
        require(qualified_capacity(result, uploads, run_id=rehearsal.run_id,
            manifest_sha256=rehearsal.provenance['manifest_sha256'],
            observer_sha256=rehearsal.observer_sha256, cohort=rehearsal.capacity_binding,
            driver_sha256=rehearsal.provenance['generator_sha256']) is True,
            'Positive capacity qualification required')
        rehearsal.publish(rehearsal.out / 'host-capacity.json', dict(capacity=result,
            uploads=uploads, verdict='PASS', scope='INERT_TARGET_HOST_CAPACITY', production_accepted=False))
        export('capacity', (rehearsal.out / 'host-capacity.json').read_bytes())
        print('HOST_FIXTURE_READY_FOR_RENDER_STOP ' + rehearsal.run_id, flush=True)
        # Exit the driver before Render stop; it is outside the worker group.
        return 0
    except BaseException as error:
        print('HOST_FIXTURE_FAILED ' + type(error).__name__, flush=True)
        # No real process or production owner can be targeted: PID1 is the
        # dedicated maintenance fixture itself, in its original PID namespace.
        os.kill(1, 15)
        raise


if __name__ == '__main__':
    raise SystemExit(main())

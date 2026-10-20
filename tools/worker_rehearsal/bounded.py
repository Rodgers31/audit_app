"""Run every real worker rehearsal component inside ONE hard resource budget.

Local Docker only. No hosted activation or production acceptance is implied.
The image is explicit, locally inspected and never implicitly downloaded.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from run import CASES, HERE, ROOT, THRESHOLDS, Rehearsal, digest, inventory, require
from bounded_profile import inert_environment


def image_id(value):
    require(type(value) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', value),
            'An exact locally inspected image ID is required')
    return value


def resolved_boundary(meta, expected_image, run_id, expected_binds, volume):
    """Verify the daemon's resolved limits, rather than the requested flags."""
    require(type(meta) is dict and meta['Image'] == image_id(expected_image), 'Image identity differs')
    require(meta['Config']['Labels'] == {'b15-worker-run': run_id}, 'Exact owned label required')
    host = meta['HostConfig']
    require(type(host['Memory']) is int and host['Memory'] == 512 * 1024 ** 2
            and type(host['MemorySwap']) is int and host['MemorySwap'] == host['Memory']
            and type(host['NanoCpus']) is int and host['NanoCpus'] == 500_000_000
            and type(host['PidsLimit']) is int and host['PidsLimit'] == 128,
            'Aggregate memory/swap/CPU/PID bounds differ')
    require(host['NetworkMode'] == 'none' and host['ReadonlyRootfs'] is True
            and host['Privileged'] is False and host['CapDrop'] == ['ALL']
            and not host['CapAdd'] and host['SecurityOpt'] == ['no-new-privileges'],
            'Isolation boundary differs')
    require(meta['Config']['User'] == '10001:10001'
            and not host['PortBindings'] and not host['Devices'], 'Host access refused')
    require(host['PidMode'] == '' and host['IpcMode'] == 'private'
            and host['UTSMode'] == '' and host['UsernsMode'] == ''
            and host['CgroupnsMode'] == 'private', 'Host namespace refused')
    require(host['Ulimits'] == [{'Name': 'nofile', 'Hard': 512, 'Soft': 512}]
            and host['Tmpfs'] == {'/tmp': 'rw,noexec,nosuid,size=16m,mode=1777',
                                   '/dev/shm': 'rw,noexec,nosuid,size=16m'},
            'File descriptor/tmpfs bounds differ')
    mounts = meta['Mounts']
    require(type(mounts) is list and len(mounts) == len(expected_binds) + 1,
            'Unexpected fixture mount')
    seen = set()
    for mount in mounts:
        dest = mount['Destination']
        require(dest not in seen, 'Duplicate fixture mount')
        seen.add(dest)
        if dest == '/state':
            require(mount['Type'] == 'volume' and mount['Name'] == volume and mount['RW'] is True,
                    'Owned state mount required')
        else:
            require(dest in expected_binds and mount['Type'] == 'bind'
                    and mount['Source'] in (expected_binds[dest][0], '/host_mnt' + expected_binds[dest][0])
                    and mount['RW'] is expected_binds[dest][1]
                    and mount['Propagation'] == 'rprivate', 'Host mount refused')
    require(seen == {*expected_binds, '/state'}, 'Missing fixture mount')


class BoundedRehearsal(Rehearsal):
    def __init__(self, out, duration, cases, *, image, optimized=False):
        image_id(image)
        super().__init__(out, duration, cases, optimized=optimized)
        self.image = image
        self.provenance.update(generated_by='tools/worker_rehearsal/bounded.py',
                               generator_sha256=digest(Path(__file__)))
        self.source['tools/worker_rehearsal/Dockerfile.bounded'] = digest(HERE / 'Dockerfile.bounded')
        self.provenance['source_inventory_sha256'] = hashlib.sha256(
            json.dumps(self.source, sort_keys=True).encode()).hexdigest()
        self.active = None
        self.active_env = None
        self.volume = 'b27-worker-state-' + self.run_id
        self.volume_owned = False
        self.volume_attempted = False
        self.counter = 0
        self.endpoint, self.proxy = 'bounded-endpoint', 'bounded-wire'
        self.public = self.out / 'public'
        self.public.mkdir()
        self.harness = self.out / 'harness'
        self.harness.mkdir()
        # This fresh directory contains only inert public fixture artifacts.
        # The fixed non-root container UID must be able to append its receipts.
        self.out.chmod(0o1777)
        self.stage_source()
        self.publish(self.out / 'aggregate-predeclared.json', dict(image=image, thresholds=THRESHOLDS,
            cases=cases, duration=duration, all_components_in_one_cgroup=True,
            components=['PostgreSQL17', 'TLS image/Graph/auth fixture', 'protocol proxy',
                        'real PID1 supervisor', 'Gunicorn API', 'real native worker',
                        'all controller/probe processes'], network='none',
            production_accepted=False, scope='LOCAL_AGGREGATE_FIXTURE',
            parity_limits=['Host architecture read back from the image; not inferred',
                'Direct local PostgreSQL17; no production TLS/pooler or billed-egress proof',
                'Linux container stop is separate from Render whole-service stop',
                'Inert fixture publishing only; production publishing/uploads remain off']))

    def stage_source(self):
        paths = [p for p in self.source if p.startswith('backend/') and
                 (Path(p).suffix in ('.py', '.sql', '.ini', '.json')
                  or p.startswith('backend/social/adapters/x_vendor/'))]
        require(paths and sum((ROOT / p).stat().st_size for p in paths) <= 32 * 1024 ** 2,
                'Bounded nonempty public source required')
        for relative in paths:
            require('..' not in Path(relative).parts and not Path(relative).is_absolute(),
                    'Source traversal refused')
            source = ROOT / relative
            require(source.is_file() and not source.is_symlink()
                    and not any(p.is_symlink() for p in source.parents), 'Source link refused')
            require(digest(source) == self.source[relative], 'Source changed before staging')
            target = self.public / Path(relative).relative_to('backend')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            require(digest(target) == self.source[relative], 'Staged bytes differ')
            target.chmod(0o444)
        for path in sorted(self.public.rglob('*'), reverse=True):
            if path.is_dir():
                path.chmod(0o555)
        self.public.chmod(0o555)
        for relative, expected in self.source.items():
            if relative.startswith('tools/worker_rehearsal/'):
                require(Path(relative).parent == Path('tools/worker_rehearsal'), 'Helper traversal refused')
                target = self.harness / Path(relative).name
                source = ROOT / relative
                require(source.is_file() and not source.is_symlink() and digest(source) == expected,
                        'Fixture helper source changed')
                shutil.copyfile(source, target)
                require(digest(target) == expected, 'Fixture helper snapshot differs')
                target.chmod(0o444)
        self.harness.chmod(0o555)

    def mounts(self):
        return ['-v', str(self.public) + ':/app:ro', '-v', str(self.harness) + ':/harness:ro',
                '-v', str(self.out) + ':/evidence', '-v', self.volume + ':/state']

    def verify_staged(self):
        """The executed copies, including their complete shape, must still match."""
        expected_public = {str(Path(p).relative_to('backend')): sha for p, sha in self.source.items()
            if p.startswith('backend/') and (Path(p).suffix in ('.py', '.sql', '.ini', '.json')
                                             or p.startswith('backend/social/adapters/x_vendor/'))}
        expected_harness = {Path(p).name: sha for p, sha in self.source.items()
                            if Path(p).parent == Path('tools/worker_rehearsal')}
        require(expected_public and expected_harness, 'Staged source inventory absent')
        for root, expected in ((self.public, expected_public), (self.harness, expected_harness)):
            require(root.is_dir() and not root.is_symlink(), 'Staged root replaced')
            actual = {}
            actual_dirs = set()
            expected_dirs = {str(parent) for name in expected for parent in Path(name).parents
                             if str(parent) != '.'}
            for path in root.rglob('*'):
                require(not path.is_symlink(), 'Staged link refused')
                relative = str(path.relative_to(root))
                if path.is_file():
                    actual[relative] = digest(path)
                else:
                    require(path.is_dir(), 'Staged special file refused')
                    actual_dirs.add(relative)
            require(actual == expected and actual_dirs == expected_dirs, 'Executed staged source differs')
        return True

    def clean_env(self, values):
        result = dict(PATH='/usr/local/bin:/usr/bin:/bin', LANG='C.UTF-8', HOME='/tmp',
                    PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1',
                    **values)
        inert_environment(result)
        return result

    def cmd(self, args, *, docker=True, check=True, timeout=60):
        # Reuse the original case logic, but run its controllers/probes within
        # the SAME bounded container, never as unbudgeted transient sidecars.
        if docker and args[:2] == ['run', '--rm']:
            self.ensure_active()
            require(args.count(self.image) == 1, 'Exact fixture image required')
            position = args.index(self.image)
            values = dict(self.active_env)
            i = 2
            while i < position:
                flag = args[i]
                if flag == '--pull=never':
                    i += 1
                elif flag in ('--network', '-v'):
                    require(i + 1 < position, 'Incomplete internal fixture option')
                    i += 2
                elif flag == '-e':
                    key, value = args[i + 1].split('=', 1)
                    require(key in values or key == 'SSL_CERT_FILE', 'Unexpected controller environment')
                    values[key] = value
                    i += 2
                else:
                    raise RuntimeError('Unknown transient fixture option')
            child = args[position + 1:]
            require(child and child[0] == 'python', 'Fixed Python fixture command required')
            inert_environment(values, controller=True)
            args = ['exec', self.active, '/usr/bin/env', '-i',
                    *[key + '=' + value for key, value in values.items()], *child]
        elif docker and args and args[0] == 'exec':
            # metrics, signals and clocks are also charged to the same cgroup.
            if args[1:3] == ['-e', 'B15_REHEARSAL=']:
                args = ['exec', *args[3:]]
                values = dict(self.active_env, B15_REHEARSAL='')
            else:
                values = dict(self.active_env)
            if args[1] == self.endpoint:
                args[1] = self.active
            require(args[1] == self.active and args[2] == 'python', 'Owned observation required')
            inert_environment(values, controller=True)
            args = ['exec', args[1], '/usr/bin/env', '-i',
                    *[key + '=' + value for key, value in values.items()], *args[2:]]
        result = super().cmd(args, docker=docker, check=check, timeout=timeout)
        if docker and args and args[0] == 'rm' and getattr(self, 'active', None) in args[1:]:
            self.active = None
            self.active_env = None
        return result

    def running(self, container):
        return json.loads(super().cmd(['inspect', container]))[0]['State']['Running'] is True

    def launch_container(self, mode, values):
        require(mode in ('auxiliary', 'service'), 'Fixed mode required')
        require(self.verify_staged() is True, 'Positive staged source verification required')
        if self.active is not None and self.running(self.active):
            require(self.active != self.service, 'Refusing overlap with a running worker service')
            super().cmd(['stop', '--time=10', self.active], timeout=15)
        self.counter += 1
        values = self.clean_env(dict(values, B27_FIXTURE='isolated', B27_MODE=mode,
            B15_ENDPOINT_RUN_ID=self.run_id, PYTHONPATH='/harness:/app:/app/tests/social'))
        aliases = [('b15-worker-db', '127.0.0.2'), ('b15-worker-wire', '127.0.0.3'),
                   ('b15-worker-api', '127.0.0.1'), ('graph.facebook.com', '127.0.0.4'),
                   ('auth.fixture.test', '127.0.0.4'),
                   ('a' * 32 + '.r2.cloudflarestorage.com', '127.0.0.4')]
        raw = super().cmd(['run', '-d', '--pull=never', '--name', f'b27-worker-{self.run_id}-{self.counter}',
            '--label', 'b15-worker-run=' + self.run_id, '--network=none', '--read-only',
            '--user=10001:10001', '--cap-drop=ALL', '--security-opt=no-new-privileges',
            '--memory=512m', '--memory-swap=512m', '--cpus=0.5', '--pids-limit=128',
            '--ulimit=nofile=512:512', '--tmpfs=/tmp:rw,noexec,nosuid,size=16m,mode=1777',
            '--tmpfs=/dev/shm:rw,noexec,nosuid,size=16m', *self.mounts(),
            *[item for host, ip in aliases for item in ('--add-host', host + ':' + ip)],
            '--entrypoint=/usr/bin/env', self.image, '-i',
            *[key + '=' + value for key, value in values.items()],
            'python', '-B', '/harness/bounded_boot.py'])
        container = raw.strip()
        require(re.fullmatch('[a-f0-9]{64}', container), 'Container identity unavailable')
        self.resources.append(container)
        self.active, self.active_env = container, values
        meta = json.loads(super().cmd(['inspect', container]))[0]
        resolved_boundary(meta, self.image, self.run_id,
            {'/app': (str(self.public), False), '/harness': (str(self.harness), False),
             '/evidence': (str(self.out), True)}, self.volume)
        def ready():
            require(self.running(container), 'Bounded bootstrap exited; retained logs in cleanup')
            return 'BOUNDED_FIXTURE_READY' in super(BoundedRehearsal, self).logs(container)
        self.until(ready, 60, 'bounded fixture bootstrap')
        return container

    def ensure_active(self):
        if self.active is None or not self.running(self.active):
            self.launch_container('auxiliary', self.fixture)

    def setup(self):
        meta = json.loads(super().cmd(['image', 'inspect', self.image]))[0]
        require(meta['Id'] == self.image and meta['Os'] == 'linux', 'Local Linux image required')
        self.publish(self.out / 'image.json', dict(identity=meta['Id'], architecture=meta['Architecture'],
                                                  os=meta['Os']))
        require(not super().cmd(['volume', 'ls', '-q', '--filter', 'name=^' + self.volume + '$']).strip(),
                'Pre-existing fixture volume refused')
        self.volume_attempted = True
        super().cmd(['volume', 'create', '--label', 'b15-worker-run=' + self.run_id, self.volume])
        meta = json.loads(super().cmd(['volume', 'inspect', self.volume]))[0]
        require(meta['Name'] == self.volume and meta['Labels'] == {'b15-worker-run': self.run_id},
                'Volume ownership unavailable')
        self.volume_owned = True
        for name, value in [('endpoint-delay', '0'), ('endpoint-case', 'setup')]:
            (self.out / name).write_text(value)
        self.ensure_active()

    def start(self, name, image, args, *, environment=None, extra=None):
        require(image == self.image and args == ['python', '-m', 'social_worker_supervisor'],
                'Only real supervisor commands admitted')
        return self.launch_container('service', environment)

    def logs(self, container):
        if container in (self.endpoint, self.proxy):
            path = self.out / ('endpoint.log' if container == self.endpoint else 'wire.log')
            require(path.is_file() and not path.is_symlink(), 'Inert recorder unavailable')
            return path.read_text()
        return super().logs(container)

    def cleanup(self):
        errors = []
        owned = super().cmd(['ps', '-aq', '--no-trunc', '--filter', 'label=b15-worker-run=' + self.run_id]).split()
        unknown = set(owned) - set(self.resources)
        if unknown:
            errors.append('Untracked owned container survived')
        for container in reversed(list(dict.fromkeys([*self.resources, *owned]))):
            # Some cases already removed their exact service IDs.
            if container not in owned:
                continue
            try:
                meta = json.loads(super().cmd(['inspect', container]))[0]
                require(meta['Config']['Labels'] == {'b15-worker-run': self.run_id}, 'Foreign cleanup refused')
                super().cmd(['logs', container], check=False)
                super().cmd(['rm', '-f', '-v', container])
            except Exception as exc:
                errors.append(str(exc))
        remaining = super().cmd(['ps', '-aq', '--filter', 'label=b15-worker-run=' + self.run_id]).strip()
        if remaining:
            errors.append('Owned process cleanup unresolved')
        removed = False
        if self.volume_attempted and not remaining:
            try:
                meta = json.loads(super().cmd(['volume', 'inspect', self.volume]))[0]
                require(meta['Labels'] == {'b15-worker-run': self.run_id}, 'Foreign volume cleanup refused')
                super().cmd(['volume', 'rm', self.volume])
                removed = not super().cmd(['volume', 'ls', '-q', '--filter', 'name=^' + self.volume + '$']).strip()
                require(removed, 'Owned fixture data survived')
            except Exception as exc:
                errors.append(str(exc))
        return dict(errors=errors, owned_containers_absent=not remaining,
                    fixture_volume_removed=removed, temporary_database_retained=False if removed else None)

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
        current = inventory()
        current['tools/worker_rehearsal/Dockerfile.bounded'] = digest(HERE / 'Dockerfile.bounded')
        unchanged = self.source == current
        try:
            staged_unchanged = self.verify_staged()
        except Exception as failure:
            staged_unchanged = False
            error = error or str(failure)
        if [row['case'] for row in self.results] != self.cases:
            error = error or 'Required case inventory incomplete'
        artifacts = {str(p.relative_to(self.out)): digest(p) for p in sorted(self.out.rglob('*')) if p.is_file()}
        cleanup_ok = (cleanup.get('owned_containers_absent') is True
                      and cleanup.get('fixture_volume_removed') is True
                      and cleanup.get('errors') == [])
        value = dict(generated_by=self.provenance['generated_by'],
            generator_sha256=self.provenance['generator_sha256'],
            generated_at=datetime.now(timezone.utc).isoformat(), source=self.source,
            results=self.results, cleanup=cleanup, source_unchanged=unchanged,
            staged_source_unchanged=staged_unchanged, error=error,
            artifacts=artifacts, verdict='PASS' if not error and unchanged and staged_unchanged is True and cleanup_ok else 'FAIL',
            scope='LOCAL_AGGREGATE_FIXTURE', production_accepted=False)
        self.publish(self.out / 'aggregate-receipt.json', value)
        require(value['verdict'] == 'PASS', 'Bounded rehearsal failed: ' + str(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--duration', type=int, default=180)
    parser.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES))
    parser.add_argument('--optimized', action='store_true')
    args = parser.parse_args()
    BoundedRehearsal(args.out, args.duration, args.cases, image=args.image, optimized=args.optimized).run()


if __name__ == '__main__':
    main()

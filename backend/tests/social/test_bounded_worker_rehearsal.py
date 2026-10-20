"""Execute aggregate-fixture refusal and cleanup paths without Docker/cloud IO."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[3] / 'tools/worker_rehearsal'
with patch.object(sys, 'path', [str(HERE), *sys.path]):
    bounded = importlib.import_module('bounded')
    profile = importlib.import_module('bounded_profile')


class BoundedGuards(unittest.TestCase):
    def fixture(self):
        # The real constructor supplies precisely the inherited inert profile.
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder).resolve() / 'fresh'
            with patch.object(bounded.Rehearsal, 'cmd', return_value='inert-head'):
                runner = bounded.BoundedRehearsal(output, 180, ['startup'],
                                                   image='sha256:' + 'a' * 64)
            return runner.fixture

    def test_noninert_values_and_duplicate_keyrings_refused(self):
        good = self.fixture()
        profile.inert_environment(good)
        for key in ('META_APP_SECRET', 'SOCIAL_MEDIA_ACCESS_KEY', 'SOCIAL_MEDIA_SECRET_KEY'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                profile.inert_environment(dict(good, **{key: 'SYNTHETIC_NOT_INERT'}))
        for key in ('SOCIAL_CREDENTIAL_KEYS', 'META_PRIVACY_SUBJECT_KEYS'):
            duplicate = '{"v1":"SYNTHETIC_NOT_INERT",' + good[key][1:]
            # json.loads equality used to discard the first value silently.
            self.assertEqual(json.loads(duplicate), json.loads(good[key]))
            with self.subTest(key=key), self.assertRaises(ValueError):
                profile.inert_environment(dict(good, **{key: duplicate}))
        with self.assertRaises(ValueError):
            profile.inert_environment(dict(good, DATABASE_URL='postgresql://synthetic@foreign/db'))

    def test_controller_override_validated_before_exec(self):
        runner = object.__new__(bounded.BoundedRehearsal)
        runner.image = 'sha256:' + 'a' * 64
        runner.active, runner.endpoint = 'owned', 'endpoint'
        runner.active_env = dict(self.fixture(), PYTHONPATH='/harness:/app:/app/tests/social')
        runner.ensure_active = lambda: None
        with patch.object(bounded.Rehearsal, 'cmd') as execute:
            with self.assertRaises(ValueError):
                runner.cmd(['run', '--rm', '-e', 'META_APP_SECRET=SYNTHETIC_NOT_INERT',
                            runner.image, 'python', '-c', 'print(1)'])
            execute.assert_not_called()
            runner.cmd(['run', '--rm', '-e', 'PYTHONPATH=/app:/app/tests/social',
                        runner.image, 'python', '-c', 'print(1)'])
            self.assertEqual(execute.call_args.args[0][:4], ['exec', 'owned', '/usr/bin/env', '-i'])

    def test_unknown_images_and_unsafe_source_paths_refused(self):
        for value in (None, True, '', 'latest', 'sha256:' + 'a' * 63, 'sha256:' + 'A' * 64):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                bounded.image_id(value)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / 'source/backend').mkdir(parents=True)
            escape = root / 'source/escape.py'
            escape.write_text('SYNTHETIC_SOURCE')
            runner = object.__new__(bounded.BoundedRehearsal)
            runner.source = {'backend/../escape.py': bounded.digest(escape)}
            runner.public = root / 'public'
            runner.public.mkdir()
            with patch.object(bounded, 'ROOT', root / 'source'), self.assertRaises(RuntimeError):
                runner.stage_source()
            self.assertEqual(list(runner.public.iterdir()), [])

    def test_resolved_daemon_boundary_rejects_missing_or_unsafe_limits(self):
        image, run_id = 'sha256:' + 'a' * 64, '0123456789ab'
        binds = {'/app': ('/owned/public', False), '/harness': ('/owned/harness', False),
                 '/evidence': ('/owned', True)}
        meta = dict(Image=image, Config=dict(Labels={'b15-worker-run': run_id}, User='10001:10001'),
            HostConfig=dict(Memory=512 * 1024 ** 2, MemorySwap=512 * 1024 ** 2,
                NanoCpus=500_000_000, PidsLimit=128, NetworkMode='none', ReadonlyRootfs=True,
                Privileged=False, CapDrop=['ALL'], CapAdd=None, SecurityOpt=['no-new-privileges'],
                PortBindings={}, Devices=[], PidMode='', IpcMode='private', UTSMode='', UsernsMode='',
                CgroupnsMode='private', Ulimits=[{'Name':'nofile','Hard':512,'Soft':512}],
                Tmpfs={'/tmp':'rw,noexec,nosuid,size=16m,mode=1777','/dev/shm':'rw,noexec,nosuid,size=16m'}),
            Mounts=[dict(Destination=dest, Source=source, RW=writable, Type='bind', Propagation='rprivate')
                    for dest, (source, writable) in binds.items()] +
                   [dict(Destination='/state', Type='volume', Name='owned-volume', RW=True)])
        bounded.resolved_boundary(meta, image, run_id, binds, 'owned-volume')
        for key, bad in [('Memory', True), ('Memory', 0), ('MemorySwap', -1), ('NanoCpus', float('nan')),
                         ('PidsLimit', None), ('PidMode', 'host'), ('IpcMode', 'host'), ('UTSMode', 'host'),
                         ('UsernsMode', 'host'), ('CgroupnsMode', 'host'), ('Ulimits', []), ('Tmpfs', {})]:
            altered = deepcopy(meta)
            altered['HostConfig'][key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises((RuntimeError, ValueError, TypeError)):
                bounded.resolved_boundary(altered, image, run_id, binds, 'owned-volume')
        for altered in (dict(meta, Mounts=[]), dict(meta, Mounts=meta['Mounts'] + [dict(Type='bind',
                Source='/var/run/docker.sock', Destination='/var/run/docker.sock', RW=True)])):
            with self.assertRaises(RuntimeError):
                bounded.resolved_boundary(altered, image, run_id, binds, 'owned-volume')

    def test_removed_active_container_is_not_reinspected(self):
        runner = object.__new__(bounded.BoundedRehearsal)
        runner.active, runner.active_env = 'owned', {'inert': 'value'}
        with patch.object(bounded.Rehearsal, 'cmd', return_value='owned'):
            runner.cmd(['rm', '-v', 'owned'])
        self.assertIsNone(runner.active)
        self.assertIsNone(runner.active_env)
        runner.fixture = {'inert': 'value'}
        with patch.object(runner, 'launch_container') as launch, patch.object(runner, 'running') as inspect:
            runner.ensure_active()
            inspect.assert_not_called()
            launch.assert_called_once_with('auxiliary', runner.fixture)

    def test_no_pass_when_cleanup_did_not_prove_absence(self):
        for cleanup in [dict(errors=[], owned_containers_absent=False, fixture_volume_removed=True),
                        dict(errors=[], owned_containers_absent=True, fixture_volume_removed=False),
                        dict(errors=[], owned_containers_absent=1, fixture_volume_removed=True),
                        dict(errors=[])]:
            with tempfile.TemporaryDirectory() as folder:
                runner = object.__new__(bounded.BoundedRehearsal)
                runner.out = Path(folder).resolve()
                runner.source = bounded.inventory()
                runner.source['tools/worker_rehearsal/Dockerfile.bounded'] = bounded.digest(HERE/'Dockerfile.bounded')
                runner.provenance = dict(generated_by='test', generator_sha256='synthetic')
                runner.results, runner.cases = [{'case': 'startup'}], ['startup']
                runner.setup = lambda: None
                runner.run_case = lambda case: None
                runner.cleanup = lambda: cleanup
                runner.verify_staged = lambda: True
                with self.subTest(cleanup=cleanup), self.assertRaises(RuntimeError):
                    runner.run()
                receipt = json.loads((runner.out/'aggregate-receipt.json').read_text())
                self.assertEqual(receipt['verdict'], 'FAIL')
                self.assertIs(receipt['production_accepted'], False)

    def test_staged_bytes_and_shape_are_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bounded.Rehearsal, 'cmd', return_value='inert-head'):
                runner = bounded.BoundedRehearsal(Path(folder).resolve()/'fresh', 180,
                    ['startup'], image='sha256:' + 'a' * 64)
            self.assertIs(runner.verify_staged(), True)
            target = runner.harness/'bounded_boot.py'
            original = target.read_bytes()
            target.chmod(0o644)
            target.write_bytes(original + b'\n# SYNTHETIC_CHANGE\n')
            with self.assertRaises(RuntimeError):
                runner.verify_staged()
            target.write_bytes(original)
            target.chmod(0o444)
            self.assertIs(runner.verify_staged(), True)
            runner.public.chmod(0o755)
            extra = runner.public/'unknown'
            extra.mkdir()
            with self.assertRaises(RuntimeError):
                runner.verify_staged()
            extra.rmdir()
            extra.symlink_to(target)
            with self.assertRaises(RuntimeError):
                runner.verify_staged()
            extra.unlink()
            self.assertIs(runner.verify_staged(), True)

    def test_staged_corruption_cannot_receive_a_pass_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(bounded.Rehearsal, 'cmd', return_value='inert-head'):
                runner = bounded.BoundedRehearsal(Path(folder).resolve()/'fresh', 180,
                    ['startup'], image='sha256:' + 'a' * 64)
            target = runner.harness/'bounded_boot.py'
            target.chmod(0o644)
            target.write_text('SYNTHETIC_CHANGE')
            runner.setup = lambda: None
            runner.run_case = lambda case: runner.results.append({'case': case})
            runner.cleanup = lambda: dict(errors=[], owned_containers_absent=True, fixture_volume_removed=True)
            with self.assertRaises(RuntimeError):
                runner.run()
            receipt = json.loads((runner.out/'aggregate-receipt.json').read_text())
            self.assertEqual(receipt['verdict'], 'FAIL')
            self.assertIs(receipt['source_unchanged'], True)
            self.assertIs(receipt['staged_source_unchanged'], False)

    def test_staged_dependency_requires_exact_positive_boolean(self):
        for value in (False, None, 1, 'true', {'ok': False}):
            with tempfile.TemporaryDirectory() as folder:
                runner = object.__new__(bounded.BoundedRehearsal)
                runner.out = Path(folder).resolve()
                runner.verify_staged = lambda: value
                with patch.object(bounded.Rehearsal, 'cmd') as execute, self.assertRaises(RuntimeError):
                    runner.launch_container('service', {})
                execute.assert_not_called()
                runner.source = bounded.inventory()
                runner.source['tools/worker_rehearsal/Dockerfile.bounded'] = bounded.digest(HERE/'Dockerfile.bounded')
                runner.provenance = dict(generated_by='test', generator_sha256='synthetic')
                runner.results, runner.cases = [{'case': 'startup'}], ['startup']
                runner.setup = lambda: None
                runner.run_case = lambda case: None
                runner.cleanup = lambda: dict(errors=[], owned_containers_absent=True, fixture_volume_removed=True)
                with self.subTest(value=value), self.assertRaises(RuntimeError):
                    runner.run()
                self.assertEqual(json.loads((runner.out/'aggregate-receipt.json').read_text())['verdict'], 'FAIL')


if __name__ == '__main__':
    unittest.main()

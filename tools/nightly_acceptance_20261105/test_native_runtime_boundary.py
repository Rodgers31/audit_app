"""Regression controls for the ingestion native execution boundary."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from contextlib import ExitStack
import json
import os
import sys

import runtime
import native_image
import native_environment
import native_artifacts


class NativeRuntimeBoundary(unittest.TestCase):
    def test_expected_runtime_is_consumed_from_the_authenticated_bytes(self):
        import copy
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            def write(name, value):
                path = root / name
                path.write_text(json.dumps(value, sort_keys=True) + '\n')
                return path
            tools = {name: {'path': '/usr/bin/' + name, 'sha256': 'a' * 64, 'version': 'fixture 1'}
                     for name in ('tesseract', 'pdftoppm', 'pdftotext', 'pdfinfo', 'java')}
            native = {**tools, 'dpkg': ['owned\t1'], 'dpkg_sha256': runtime.identity(['owned\t1']),
                      'os_release_sha256': 'b' * 64, 'languages': ['eng'],
                      'traineddata': {'/usr/share/eng.traineddata': 'c' * 64},
                      'linked_libraries': {'/usr/lib/owned.so': 'd' * 64}}
            profile = write('profile.json', {'schema': 'reviewed-ingestion-native-v1', 'native': native})
            observations, entries = {}, {}
            for role, lock in (('production', runtime.LOCK), ('qualification',
                               runtime.ROOT / 'backend/ingestion-qualification.lock.json')):
                observation = {'qualification': 'PYTHON_AND_REVIEWED_NATIVE',
                    'native_profile_sha256': runtime.sha256(profile), 'lock_sha256': runtime.sha256(lock),
                    'python': '3.12.16', 'executable_sha256': 'e' * 64, 'stdlib_sha256': 'f' * 64,
                    'soabi': 'cpython-312-x86_64-linux-gnu', 'system': 'Linux', 'machine': 'x86_64',
                    'native': native, 'packages': {r['name']: {'version': r['version'],
                        'files_sha256': '1' * 64} for r in runtime.load_lock(lock)['packages']}}
                observations[role] = observation
                path = write(role + '.json', observation)
                entries[role] = {'path': path.name, 'sha256': runtime.sha256(path),
                                 'prefix': '/opt/ingestion' if role == 'production' else '/opt/qualification'}
            environment = write('environment.json', {'schema': 'controlled-ingestion-environment-v1',
                'base_image': 'docker.io/library/python@sha256:' + '2' * 64, 'image_id': 'sha256:' + '3' * 64,
                'image_archive_sha256': '4' * 64, 'native_lock_sha256': '5' * 64, 'corpus_sha256': '6' * 64,
                'profiles': {job: {'path': profile.name, 'sha256': runtime.sha256(profile)}
                             for job in native_environment.JOBS}, 'runtimes': entries})
            changed = copy.deepcopy(observations['production'])
            changed['executable_sha256'] = '9' * 64
            original_hash = native_environment.sha256
            def replace_after_digest(path):
                result = original_hash(path)
                if Path(path) == root / 'production.json':
                    write('production.json', changed)
                return result
            with patch.object(native_environment, 'sha256', replace_after_digest), \
                    patch.object(runtime, 'verify', lambda *args: changed), \
                    patch.object(sys, 'prefix', '/opt/ingestion'):
                with self.assertRaisesRegex(runtime.Refusal, 'differs'):
                    native_environment.verify_environment(environment, 'seed')

    def test_native_build_snapshot_remains_exact_after_source_mutation(self):
        import hashlib
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / 'source'
            source.mkdir()
            artifact = source / 'owned.deb'
            artifact.write_bytes(b'owned')
            lock = {'packages': [{'filename': 'owned.deb', 'size': 5,
                                  'sha256': hashlib.sha256(b'owned').hexdigest()}]}
            captured = native_artifacts.snapshot_native_assets(lock, source, root / 'captured')
            artifact.write_bytes(b'other')
            self.assertEqual((captured / 'owned.deb').read_bytes(), b'owned')
            captured.chmod(0o700)
            (captured / 'owned.deb').chmod(0o600)

    def _assert_override_refuses(self, name):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / 'environment.json'
            path.write_text('{}')
            value = {'runtimes': {'production': {'prefix': '/opt/ingestion', 'path': 'runtime.json'}},
                     'profiles': {'seed': {'path': 'seed.json'}}, 'image_id': 'sha256:' + 'a' * 64}
            with patch.dict(os.environ, {name: '/inert/owned-fixture'}), \
                    patch.object(native_environment, 'load_environment', lambda path: value), \
                    patch.object(native_environment, 'member', lambda *args: path), \
                    patch.object(native_environment, 'read_json', lambda path: {}), \
                    patch.object(runtime, 'verify', lambda *args: {}), patch.object(sys, 'prefix', '/opt/ingestion'):
                with self.assertRaisesRegex(runtime.Refusal, 'override'):
                    native_environment.verify_environment(path, 'seed')

    def test_ld_audit_override_refuses(self):
        self._assert_override_refuses('LD_AUDIT')

    def test_bytecode_cache_prefix_override_refuses(self):
        self._assert_override_refuses('PYTHONPYCACHEPREFIX')

    def test_openssl_configuration_override_refuses(self):
        self._assert_override_refuses('OPENSSL_CONF')

    def test_openssl_modules_override_refuses(self):
        self._assert_override_refuses('OPENSSL_MODULES')

    def test_fontconfig_file_override_refuses(self):
        self._assert_override_refuses('FONTCONFIG_FILE')

    def test_fontconfig_path_override_refuses(self):
        self._assert_override_refuses('FONTCONFIG_PATH')

    def test_gconv_override_refuses(self):
        self._assert_override_refuses('GCONV_PATH')

    def test_native_artifact_change_during_digest_refuses(self):
        import hashlib
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            assets = root / 'debs'
            assets.mkdir()
            artifact = assets / 'owned_1_amd64.deb'
            artifact.write_bytes(b'owned')
            lock = root / 'lock.json'
            lock.write_text(json.dumps({'schema': 'ingestion-native-artifacts-v1',
                'base_image': 'docker.io/library/python@sha256:' + 'a' * 64,
                'repository_metadata': {'InRelease': 'b' * 64},
                'packages': [{'name': 'owned', 'version': '1', 'architecture': 'amd64',
                    'filename': artifact.name, 'url': 'https://deb.debian.org/debian/pool/main/o/owned/' + artifact.name,
                    'sha256': hashlib.sha256(b'owned').hexdigest(), 'size': 5}]}))
            original_hash = native_artifacts.sha256
            def changing_hash(path):
                result = original_hash(path)
                if Path(path) == artifact:
                    artifact.write_bytes(b'other')
                return result
            with patch.object(native_artifacts, 'sha256', changing_hash):
                with self.assertRaisesRegex(runtime.Refusal, 'changed|differ'):
                    native_artifacts.verify_native_assets(lock, assets)
            artifact.write_bytes(b'owned')
            parsed_lock_sha256 = runtime.sha256(lock)
            read_bytes = Path.read_bytes
            def replace_lock_after_read(path):
                raw = read_bytes(path)
                if path == lock:
                    lock.write_text('{"schema":"unvalidated-replacement"}')
                return raw
            with patch.object(Path, 'read_bytes', replace_lock_after_read):
                result = native_artifacts.verify_native_assets(lock, assets)
            self.assertEqual(result['lock_sha256'], parsed_lock_sha256)
            self.assertNotEqual(runtime.sha256(lock), parsed_lock_sha256)

    def fake_build(self, scratch, *, cleanup_timeout=False, bad_stdout=False):
        root = Path(scratch)
        lock = root / 'lock.json'
        lock.write_text(json.dumps({'base_image': 'docker.io/library/python@sha256:' + 'a' * 64}))
        output = root / 'output'
        calls = []

        def engine(argv, **kwargs):
            calls.append((argv, kwargs))
            if 'rm' in argv and cleanup_timeout:
                raise subprocess.TimeoutExpired(argv, kwargs.get('timeout', 1))
            stdout = b''
            if 'run' in argv and bad_stdout:
                stdout = b'\xff'
            if 'commit' in argv or 'inspect' in argv:
                stdout = ('sha256:' + 'b' * 64).encode()
            if 'save' in argv:
                Path(argv[argv.index('-o') + 1]).write_bytes(b'owned image archive')
            if argv[0].endswith('git'):
                stdout = b'owned-source-identity\n'
            return subprocess.CompletedProcess(argv, 0, stdout, b'')

        with ExitStack() as patches:
            patches.enter_context(patch.object(native_image, 'HEAVY_LOCK', str(root / 'heavy.lock')))
            patches.enter_context(patch.object(native_image, 'verify_native_assets',
                                  lambda *args: {'lock_sha256': runtime.sha256(lock)}))
            patches.enter_context(patch.object(native_image, 'snapshot_native_assets',
                                  lambda *args: root))
            patches.enter_context(patch('subprocess.run', engine))
            patches.enter_context(patch.object(Path, 'is_socket', lambda path: True))
            patches.enter_context(patch.dict(os.environ, {'DOCKER_HOST': 'tcp://192.0.2.10:2376',
                                                         'DOCKER_CONTEXT': 'inert-remote'}))
            if cleanup_timeout or bad_stdout:
                with self.assertRaises((runtime.Refusal, UnicodeError)):
                    native_image.build(lock, root, output)
            else:
                native_image.build(lock, root, output)
        return json.loads((output / 'build.json').read_bytes()), calls

    def test_native_build_pins_local_engine_and_drops_ambient_context(self):
        with tempfile.TemporaryDirectory() as scratch:
            _, calls = self.fake_build(scratch)
        docker = [(argv, options) for argv, options in calls if 'git' not in Path(argv[0]).name]
        self.assertTrue(docker)
        for argv, options in docker:
            self.assertIn('--host', argv)
            self.assertTrue(argv[argv.index('--host') + 1].startswith('unix://'))
            self.assertNotIn('DOCKER_HOST', options.get('env', os.environ))
            self.assertNotIn('DOCKER_CONTEXT', options.get('env', os.environ))

    def test_native_build_cleanup_timeout_retains_failed_receipt(self):
        with tempfile.TemporaryDirectory() as scratch:
            receipt, _ = self.fake_build(scratch, cleanup_timeout=True)
        self.assertEqual(receipt['verdict'], 'FAILED')
        self.assertTrue(receipt['failures'])

    def test_unexpected_build_exception_cannot_stamp_success(self):
        with tempfile.TemporaryDirectory() as scratch:
            receipt, _ = self.fake_build(scratch, bad_stdout=True)
        self.assertEqual(receipt['verdict'], 'FAILED')
        self.assertTrue(receipt['failures'])

    def test_native_build_receipt_binds_source_and_all_helpers(self):
        with tempfile.TemporaryDirectory() as scratch:
            receipt, _ = self.fake_build(scratch)
        self.assertIn('source', receipt)
        self.assertEqual(set(receipt['source']), {'commit', 'tree', 'status'})
        self.assertTrue({'native_artifacts.py', 'native_environment.py', 'runtime.py', 'common.py'}
                        <= {Path(p).name for p in receipt['inputs']})

    def _assert_interpreter_refuses(self, implementation, version, machine):
        with patch('platform.python_version', lambda: version), \
                patch('platform.system', lambda: 'Linux'), \
                patch('platform.machine', lambda: machine), \
                patch('platform.python_implementation', lambda: implementation):
            with self.assertRaisesRegex(runtime.Refusal, 'interpreter/platform'):
                runtime.target_verified(runtime.load_lock())

    def test_non_cpython_with_matching_version_and_platform_refuses(self):
        self._assert_interpreter_refuses('PyPy', '3.12.16', 'x86_64')

    def test_wrong_python_version_refuses(self):
        self._assert_interpreter_refuses('CPython', '3.12.15', 'x86_64')

    def test_wrong_python_architecture_refuses(self):
        self._assert_interpreter_refuses('CPython', '3.12.16', 'aarch64')

    def test_java_dynamic_runtime_and_configuration_are_bound(self):
        """The Java launcher ldd list alone omits the dynamically loaded VM."""
        with tempfile.TemporaryDirectory() as scratch:
            home = Path(scratch) / 'jvm'
            java = home / 'bin/java'
            vm = home / 'lib/server/libjvm.so'
            external_config = Path(scratch) / 'jvm-config'
            external_config.mkdir()
            home.mkdir()
            (home / 'conf').symlink_to(external_config, target_is_directory=True)
            config = home / 'conf/security/java.security'
            for path, data in ((java, b'launcher'), (vm, b'owned JVM payload'),
                               (config, b'owned security policy')):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)

            def probe(argv, **kwargs):
                if argv[0] == 'dpkg-query':
                    return subprocess.CompletedProcess(argv, 0, b'owned-jvm\t1.0\n', b'')
                if argv[0] == 'ldd':
                    return subprocess.CompletedProcess(argv, 0, b'', b'')
                return subprocess.CompletedProcess(argv, 0, b'', b'openjdk fixture version')

            original_hash = runtime.sha256
            def checksum(path):
                return 'a' * 64 if str(path) == '/etc/os-release' else original_hash(path)

            with patch('shutil.which', lambda name: str(java) if name == 'java' else None), \
                    patch('subprocess.run', probe), patch.object(runtime, 'sha256', checksum):
                observed = runtime.native_inventory()
                self.assertEqual(observed['linked_libraries'].get(str(vm)), original_hash(vm))
                self.assertEqual(observed['linked_libraries'].get(str(config)), original_hash(config))
                before = runtime.identity(observed)
                vm.write_bytes(b'changed dynamic JVM payload')
                self.assertNotEqual(runtime.identity(runtime.native_inventory()), before)


if __name__ == '__main__':
    unittest.main()

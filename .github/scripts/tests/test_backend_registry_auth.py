"""Two-image acquisition controls use only inert Docker and private OS temporary files."""
import base64
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


def load():
    path = ROOT / '.github/scripts/prepare_backend_registry_auth.py'
    module = types.ModuleType('backend_auth_control')
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


class BackendRegistryAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.subject = load()

    def exercise(self, fault=None, arch='amd64'):
        m = self.subject
        calls = []
        preparation_error = None
        cleanup_error = None
        with tempfile.TemporaryDirectory(prefix='backend-registry-control-') as temporary:
            root = Path(temporary).resolve()
            state = root / m.STATE_NAME
            environment = {'RUNNER_TEMP': str(root), 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                           'DOCKERHUB_USERNAME': 'inert-user', 'DOCKERHUB_TOKEN': 'INERT-TOKEN-ONLY'}
            if fault == 'missing-credentials':
                environment.pop('DOCKERHUB_TOKEN')
            if fault == 'wrong-event':
                environment['GITHUB_EVENT_NAME'] = 'pull_request'
            if fault == 'nul-token':
                environment['DOCKERHUB_TOKEN'] = 'inert\0token'

            def inert(argv, **kwargs):
                self.assertEqual(argv[:2], ['docker', '--config'])
                config = Path(argv[2])
                args = argv[3:]
                command = args[0]
                calls.append(args)
                self.assertNotIn('DOCKERHUB_TOKEN', kwargs['env'])
                self.assertNotIn('DOCKERHUB_USERNAME', kwargs['env'])
                if command == 'version':
                    server = {'Os': 'linux', 'Arch': 'other' if fault == 'wrong-daemon' else arch}
                    return subprocess.CompletedProcess(argv, 0, json.dumps(server).encode(), b'')
                if command == 'login':
                    self.assertEqual(kwargs['input'], (environment['DOCKERHUB_TOKEN'] + '\n').encode())
                    placeholder = json.loads((config / 'config.json').read_bytes())
                    self.assertEqual(placeholder, {'auths': {'https://index.docker.io/v1/': {'auth': ''}}})
                    self.assertEqual((config / 'config.json').stat().st_mode & 0o777, 0o600)
                    auth = base64.b64encode((environment['DOCKERHUB_USERNAME'] + ':' + environment['DOCKERHUB_TOKEN']).encode()).decode()
                    value = {'auths': {'https://index.docker.io/v1/': {'auth': auth}}}
                    if fault == 'wrong-config':
                        value = {'auths': {'peer': {'auth': 'wrong'}}}
                    if fault == 'null-config':
                        value = None
                    path = config / 'config.json'
                    path.write_text(json.dumps(value))
                    path.chmod(0o644 if fault == 'nonprivate-config' else 0o600)
                    code = 1 if fault == 'login-nonzero' else False if fault == 'login-bool' else 0
                    return subprocess.CompletedProcess(argv, code, b'INERT-TOKEN-ONLY', b'')
                if command == 'pull':
                    self.assertEqual(args[1:3], ['--platform', 'linux/' + arch])
                    self.assertIn(args[3], m.IMAGES)
                    if fault == 'pull-timeout':
                        raise subprocess.TimeoutExpired(argv, 1, output=b'INERT-TOKEN-ONLY')
                    return subprocess.CompletedProcess(argv, 1 if fault == 'pull-nonzero' else False if fault == 'pull-bool' else 0, b'INERT-TOKEN-ONLY', b'')
                if command == 'image':
                    self.assertEqual(args[:2], ['image', 'inspect'])
                    self.assertEqual(len(args), 3)  # Docker 28.0.4 compatibility: no inspect --platform.
                    reference = args[2]
                    image = {'Id': sorted(m.IMAGES[reference][arch])[0], 'Os': 'linux',
                             'Architecture': arch, 'RepoDigests': [reference]}
                    if fault == 'wrong-id':
                        image['Id'] = 'sha256:' + '0' * 64
                    if fault == 'wrong-arch':
                        image['Architecture'] = 'other'
                    if fault == 'wrong-repository':
                        image['RepoDigests'] = [reference.replace('postgres', 'foreign', 1)]
                    raw = b'' if fault == 'empty-inspection' else b'{' if fault == 'malformed-inspection' else json.dumps([image]).encode()
                    return subprocess.CompletedProcess(argv, 1 if fault == 'inspect-nonzero' else False if fault == 'inspect-bool' else 0, raw, b'INERT-TOKEN-ONLY')
                if command == 'logout':
                    if fault == 'logout-timeout':
                        raise subprocess.TimeoutExpired(argv, 1, stderr=b'INERT-TOKEN-ONLY')
                    return subprocess.CompletedProcess(argv, 1 if fault == 'logout-nonzero' else False if fault == 'logout-bool' else 0, b'INERT-TOKEN-ONLY', b'')
                self.fail('Unplanned Docker command')

            with patch.object(os, 'environ', environment), patch.object(m.subprocess, 'run', inert), redirect_stdout(io.StringIO()):
                try:
                    m.prepare(state, False if fault == 'bool-platform' else 'linux/' + arch)
                except (RuntimeError, ValueError, subprocess.TimeoutExpired) as caught:
                    preparation_error = caught
                if state.exists():
                    for path in (state, root / 'browser-registry-state.json'):
                        text = path.read_text()
                        self.assertNotIn('INERT-TOKEN-ONLY', text)
                        self.assertNotIn(base64.b64encode(b'inert-user:INERT-TOKEN-ONLY').decode(), text)
                    try:
                        m.cleanup(state)
                    except RuntimeError as caught:
                        cleanup_error = caught
                    final = json.loads(state.read_bytes())
                    self.assertFalse(Path(final['credential_owner']['config']).exists())
                    self.assertTrue(final['physical_config_removed'])
                    if preparation_error is not None:
                        self.assertNotIn('logout', [args[0] for args in calls])
                    elif not fault:
                        self.assertEqual(final['status'], 'OWNED_CONFIG_REMOVED')
                        self.assertIs(type(final['logout_exit_code']), int)
                        self.assertEqual(final['logout_exit_code'], 0)
                        self.assertEqual([row['image'] for row in final['images']], list(m.IMAGES))
            if fault is None:
                self.assertIsNone(preparation_error)
                self.assertIsNone(cleanup_error)
                self.assertEqual([args[0] for args in calls], ['version', 'login', 'pull', 'image', 'pull', 'image', 'logout'])
            elif fault.startswith('logout-'):
                self.assertIsNone(preparation_error)
                self.assertIsNotNone(cleanup_error)
            else:
                self.assertIsNotNone(preparation_error)
                self.assertIsNone(cleanup_error)

    def test_both_native_platform_profiles_acquire_only_exact_images(self):
        for arch in ('amd64', 'arm64'):
            with self.subTest(arch=arch):
                self.exercise(arch=arch)

    def test_credentials_event_and_native_platform_refusals(self):
        for fault in ('missing-credentials', 'wrong-event', 'nul-token', 'bool-platform', 'wrong-daemon'):
            with self.subTest(fault=fault):
                self.exercise(fault)

    def test_login_configuration_and_primitive_exit_refusals(self):
        for fault in ('login-nonzero', 'login-bool', 'wrong-config', 'null-config', 'nonprivate-config'):
            with self.subTest(fault=fault):
                self.exercise(fault)

    def test_pull_failures_never_logout_a_failed_configuration(self):
        for fault in ('pull-timeout', 'pull-nonzero', 'pull-bool'):
            with self.subTest(fault=fault):
                self.exercise(fault)

    def test_wrong_image_platform_repository_and_inspection_refuse(self):
        for fault in ('wrong-id', 'wrong-arch', 'wrong-repository', 'empty-inspection',
                      'malformed-inspection', 'inspect-nonzero', 'inspect-bool'):
            with self.subTest(fault=fault):
                self.exercise(fault)

    def test_logout_failure_still_physically_removes_owned_credentials(self):
        for fault in ('logout-timeout', 'logout-nonzero', 'logout-bool'):
            with self.subTest(fault=fault):
                self.exercise(fault)

    def test_browser_creator_peer_custody_is_refused_without_mutation(self):
        m = self.subject
        with tempfile.TemporaryDirectory(prefix='backend-browser-peer-control-') as temporary:
            root = Path(temporary).resolve()
            with patch.dict(os.environ, {'RUNNER_TEMP': str(root)}, clear=True):
                base = m.helper(m.time.monotonic() + 60)
                config = root / ('browser-registry-' + 'a' * 32)
                config.mkdir(mode=0o700)
                owner = {'nonce': 'a' * 32, 'uid': os.getuid(), 'generator_sha256': m.HELPER_SHA,
                         'registry': 'docker.io', 'config': str(config), 'config_identity': base.identity(config.stat())}
                base.write_state(config / 'owner.json', owner, exclusive=True)
                library = {**owner, 'status': 'AUTHENTICATED_CONFIG_VERIFIED'}
                base.write_state(root / base.STATE_NAME, library, exclusive=True)
                base.write_state(config / 'config.json', {'auths': {'https://index.docker.io/v1/': {'auth': 'inert'}}}, exclusive=True)
                state = root / m.STATE_NAME
                value = {'generator_sha256': m.source_hash(), 'helper_sha256': m.HELPER_SHA, 'uid': os.getuid(),
                         'status': 'ALLOCATED', 'platform': 'linux/amd64', 'images': [],
                         'helper_state': str(root / base.STATE_NAME), 'credential_owner': owner}
                m.write_state(base, state, value, exclusive=True)
                before = {path.name: path.read_bytes() for path in config.iterdir()}
                with patch.object(m.subprocess, 'run') as child, self.assertRaises(RuntimeError):
                    m.cleanup(state)
                child.assert_not_called()
                self.assertTrue(config.is_dir())
                self.assertEqual({path.name: path.read_bytes() for path in config.iterdir()}, before)

    def test_custom_signal_interrupt_and_original_handlers_are_restored(self):
        m = self.subject
        prior = {kind: signal.getsignal(kind) for kind in (signal.SIGTERM, signal.SIGINT)}
        def inert_main():
            with self.assertRaises(m.BackendRegistryInterrupted):
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        with patch.object(m, 'main', inert_main):
            m.run()
        self.assertEqual({kind: signal.getsignal(kind) for kind in prior}, prior)


if __name__ == '__main__':
    unittest.main()

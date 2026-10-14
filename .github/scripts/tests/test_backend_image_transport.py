"""Manual CI image selection with inert Docker and genuine isolated Python calls."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


def load(relative):
    path = ROOT / relative
    module = types.ModuleType('transport_control_' + path.stem)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


class BackendImageTransportTests(unittest.TestCase):
    def setUp(self):
        self.selector = load('tools/ci_postgres_image_transport.py')
        self.active = {self.selector.MODE_KEY: self.selector.MODE, 'CI': 'true',
                       'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch'}

    def test_default_ecr_and_service_bytes_are_preserved(self):
        s = self.selector
        for ref in s.SELECTED:
            self.assertEqual(s.select_image(ref, {}), ref)
        self.assertEqual(s.select_image(s.SERVICE_ECR, self.active), s.SERVICE_ECR)
        argv = ['docker', 'run', s.POSTGRES_ECR]
        self.assertIs(s.docker_run_arguments(argv, {}), argv)
        self.assertEqual(s.transport_environment({}), {})

    def test_opt_in_selects_only_two_exact_hub_references(self):
        s = self.selector
        self.assertEqual(s.select_image(s.POSTGRES_ECR, self.active), 'postgres@' + s.POSTGRES_ECR.split('@')[1])
        self.assertEqual(s.select_image(s.SUPABASE_ECR, self.active), 'supabase/postgres@' + s.SUPABASE_ECR.split('@')[1])
        supplied = {**self.active, 'DOCKERHUB_TOKEN': 'opaque', 'DOCKER_CONFIG': '/peer', 'PGPASSWORD': 'opaque'}
        self.assertEqual(s.transport_environment(supplied), self.active)

    def test_unknown_mode_event_types_and_mutable_references_refuse(self):
        s = self.selector
        for value in ('', 'docker-hub', None, False, 1):
            with self.subTest(mode=value), self.assertRaises(RuntimeError):
                s.select_image(s.POSTGRES_ECR, {**self.active, s.MODE_KEY: value})
        for key, value in [('CI', False), ('GITHUB_ACTIONS', 'false'), ('GITHUB_EVENT_NAME', 'pull_request')]:
            with self.subTest(context=key), self.assertRaises(RuntimeError):
                s.select_image(s.POSTGRES_ECR, {**self.active, key: value})
        for ref in ('postgres:17', s.SELECTED[s.POSTGRES_ECR], '', None, False):
            with self.subTest(reference=ref), self.assertRaises(RuntimeError):
                s.select_image(ref, self.active)

    def test_selected_docker_runs_never_pull_and_conflicts_refuse(self):
        s = self.selector
        for ref in (s.SELECTED[s.POSTGRES_ECR], s.SELECTED[s.SUPABASE_ECR]):
            argv = ['docker', 'run', '--rm', ref]
            self.assertEqual(s.docker_run_arguments(argv, self.active), ['docker', 'run', '--pull=never', '--rm', ref])
            for pull in (['--pull=never'], ['--pull', 'never']):
                existing = ['docker', 'run', *pull, ref]
                self.assertIs(s.docker_run_arguments(existing, self.active), existing)
            for pull in (['--pull=always'], ['--pull', 'always'], ['--pull']):
                with self.subTest(pull=pull), self.assertRaises(RuntimeError):
                    s.docker_run_arguments(['docker', 'run', ref, *pull], self.active)
        for argv in (['docker', 'image', 'inspect', s.SELECTED[s.POSTGRES_ECR]], ['docker', 'run', s.SERVICE_ECR]):
            self.assertIs(s.docker_run_arguments(argv, self.active), argv)

    def test_selected_cache_miss_refuses_without_anonymous_pull(self):
        with patch.dict(os.environ, self.active, clear=True):
            preparation = load('.github/scripts/prepare_postgres_test_images.py')
            ref = preparation.required_images()[0]
            results = [subprocess.CompletedProcess([], 0, b'{"Os":"linux","Arch":"amd64"}', b''),
                       subprocess.CompletedProcess([], 1, b'', ('Error response from daemon: No such image: ' + ref).encode())]
            with patch.object(preparation.subprocess, 'run', side_effect=results) as run:
                with self.assertRaises(preparation.Refusal) as failure:
                    preparation.prepare()
            self.assertEqual(str(failure.exception), 'selected_ci_image_missing_from_cache')
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args_list[1].args[0], ['docker', 'image', 'inspect', ref])

    def test_default_cache_miss_still_uses_original_explicit_pull(self):
        with patch.dict(os.environ, {}, clear=True):
            preparation = load('.github/scripts/prepare_postgres_test_images.py')
            refs = preparation.required_images()
            def inert(argv, **kwargs):
                if argv[1] == 'version':
                    return subprocess.CompletedProcess(argv, 0, b'{"Os":"linux","Arch":"amd64"}', b'')
                if argv[1] == 'pull':
                    self.assertEqual(argv[1:3], ['pull', '--platform'])
                    self.assertEqual(argv[3], 'linux/amd64')
                    return subprocess.CompletedProcess(argv, 0, b'', b'')
                ref = argv[-1]
                if ref == refs[0] and inert.first:
                    inert.first = False
                    return subprocess.CompletedProcess(argv, 1, b'', ('Error response from daemon: No such image: ' + ref).encode())
                return subprocess.CompletedProcess(argv, 0, json.dumps([{'Id': 'sha256:' + 'a' * 64,
                    'Os': 'linux', 'Architecture': 'amd64', 'RepoDigests': [ref]}]).encode(), b'')
            inert.first = True
            with patch.object(preparation.subprocess, 'run', side_effect=inert) as run, redirect_stdout(io.StringIO()):
                preparation.prepare()
            pulls = [call.args[0] for call in run.call_args_list if call.args[0][1] == 'pull']
            self.assertEqual(pulls, [['docker', 'pull', '--platform', 'linux/amd64', refs[0]]])

    def test_backup_and_reconciliation_run_forward_pull_never(self):
        with patch.dict(os.environ, self.active, clear=True):
            backup = load('tools/bounded_pg_backup.py')
            reconciliation = load('.github/scripts/prepare_reconciliation_test_fixture.py')
            with patch.object(backup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'bounded', b'')) as child:
                self.assertEqual(backup.run(['docker', 'run', backup.IMAGE]), b'bounded')
                self.assertEqual(child.call_args.args[0], ['docker', 'run', '--pull=never', backup.IMAGE])
                self.assertEqual({k: child.call_args.kwargs['env'][k] for k in self.active}, self.active)
            with patch.object(reconciliation.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'owned', b'')) as child:
                reconciliation.run(['docker', 'run', reconciliation.IMAGE], time.monotonic() + 10)
                self.assertEqual(child.call_args.args[0], ['docker', 'run', '--pull=never', reconciliation.IMAGE])

    def test_real_isolated_python_preserves_selected_and_default_environment(self):
        # -I ignores PYTHONPATH; the actual tool still compiles its pinned sibling
        # selector and scrubs credentials before invoking its own Python children.
        code = "import json,types;from pathlib import Path;p=Path(__import__('sys').argv[1]);m=types.ModuleType('b');m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);print(json.dumps([m.IMAGE,m.SUPABASE_IMAGE,m.ENV]))"
        base = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'PYTHONDONTWRITEBYTECODE': '1',
                'DOCKERHUB_TOKEN': 'opaque', 'PGPASSWORD': 'opaque', 'PYTHONPATH': '/untrusted'}
        for mode in ({}, self.active):
            result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(ROOT / 'tools/bounded_pg_backup.py')],
                                    env={**base, **mode}, capture_output=True, timeout=10, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            postgres, supabase, forwarded = json.loads(result.stdout)
            self.assertEqual(postgres, self.selector.select_image(self.selector.POSTGRES_ECR, mode))
            self.assertEqual(supabase, self.selector.select_image(self.selector.SUPABASE_ECR, mode))
            self.assertEqual({k: v for k, v in forwarded.items() if k not in ('PATH', 'PYTHONDONTWRITEBYTECODE')}, mode)
            self.assertNotIn('DOCKERHUB_TOKEN', forwarded)
            self.assertNotIn('PGPASSWORD', forwarded)


if __name__ == '__main__':
    unittest.main()

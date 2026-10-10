"""Execute portable replay boundaries with toy secrets and real relocated Git fixtures."""
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

ENTRY = Path(__file__).resolve().with_name('replay_v2.py')
NODE = os.environ.get('REPLAY_NODE') or shutil.which('node')
TOY = 'TOY_SECRET_BATCH11_NOT_A_CREDENTIAL'


class ReplayControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'relocated'; self.root.mkdir()
        self.env = {'PATH': '/usr/bin:/bin', 'HOME': str(self.base), 'LANG': 'C.UTF-8',
                    'PROVIDER_TOKEN': TOY, 'DATABASE_URL': 'postgresql://toy.invalid/toy',
                    'HTTP_PROXY': 'http://toy.invalid:9', 'NODE_OPTIONS': '--no-warnings',
                    'PYTHONDONTWRITEBYTECODE': '1'}
        self.git('init', '-q')
        (self.root / 'source.txt').write_text('source sentinel')
        self.git('add', 'source.txt')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@invalid', 'commit', '-qm', 'fixture')

    def git(self, *args):
        return subprocess.check_output(['/usr/bin/git', *args], cwd=self.root, env=self.env)

    def cli(self, operation, output, *args, checkout=None):
        command = [sys.executable, *(['-O'] if sys.flags.optimize else []), str(ENTRY),
                   operation, str(checkout or self.root), str(output), *args]
        return subprocess.run(command, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)

    def refused(self, result, diagnostic, output):
        self.assertEqual(result.returncode, 1, result.stderr.decode())
        self.assertIn(diagnostic.encode(), result.stderr)
        self.assertFalse((output / 'receipt.json').exists())
        self.assertFalse((output / 'source.tar').exists())
        self.assertFalse((output / 'replay.zip').exists())

    def test_run_relocated_with_toy_secrets_excluded(self):
        out = self.base / 'run'
        child = 'import json,os;print(json.dumps(dict(os.environ),sort_keys=True))'
        result = self.cli('run', out, '--', sys.executable, '-c', child)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        record = json.loads((out / 'receipt.json').read_text())
        self.assertEqual(record['schema'], 2)
        self.assertIs(record['source_stable'], True)
        self.assertIs(record['cleanup']['survivors_detected'], False)
        self.assertIs(record['cleanup']['group_absent'], True)
        self.assertIs(record['current_checkout_acceptance'], False)
        self.assertEqual(record['generator_sha256'], hashlib.sha256(ENTRY.read_bytes()).hexdigest())
        actual = json.loads((out / 'stdout.log').read_text())
        # CPython coerces locales; Apple's framework runtime also adds its encoding flag.
        # These are runtime additions after Popen, not values forwarded by this producer.
        actual.pop('LC_CTYPE', None)
        actual.pop('__CF_USER_TEXT_ENCODING', None)
        self.assertEqual(actual, record['environment'])
        for name in ('PROVIDER_TOKEN', 'DATABASE_URL', 'HTTP_PROXY', 'NODE_OPTIONS'):
            self.assertNotIn(name, actual)
        self.assertNotIn(TOY, (out / 'receipt.json').read_text() + (out / 'stdout.log').read_text())
        self.assertEqual(self.git('status', '--porcelain'), b'')

    def test_export_regular_bytes_and_source_manifest(self):
        out = self.base / 'export'
        result = self.cli('export', out)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        manifest = json.loads((out / 'source-manifest.json').read_text())
        self.assertEqual(manifest['source']['files'], {'source.txt': hashlib.sha256(b'source sentinel').hexdigest()})
        with tarfile.open(out / 'source.tar') as archive:
            self.assertEqual(archive.getnames(), ['source.txt'])
            self.assertTrue(archive.getmember('source.txt').isfile())
            self.assertEqual(archive.extractfile('source.txt').read(), b'source sentinel')
        self.assertEqual(manifest['archive_sha256'], hashlib.sha256((out / 'source.tar').read_bytes()).hexdigest())

    def test_pack_external_corpus_without_invented_acceptance(self):
        corpus = self.base / 'corpus'; corpus.mkdir(); (corpus / 'retained.txt').write_text('retained')
        out = self.base / 'pack'; result = self.cli('pack', out, '--corpus', str(corpus))
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        manifest = json.loads((out / 'replay-manifest.json').read_text())
        self.assertEqual(manifest['classification'], 'REPLAY_BYTE_ARCHIVE')
        self.assertIs(manifest['current_checkout_acceptance'], False)
        self.assertEqual(manifest['members'], {'retained.txt': hashlib.sha256(b'retained').hexdigest()})

    def test_all_operations_refuse_internal_output(self):
        for operation in ('run', 'export', 'pack'):
            with self.subTest(operation=operation):
                out = self.root / (operation + '-output')
                self.refused(self.cli(operation, out), 'external output required', out)
                self.assertFalse(out.exists())

    def test_all_operations_refuse_hidden_git_output(self):
        for operation in ('run', 'export', 'pack'):
            with self.subTest(operation=operation):
                out = self.root / '.git' / (operation + '-output')
                self.refused(self.cli(operation, out), 'external output required', out)
                self.assertFalse(out.exists())

    def test_all_operations_refuse_output_symlink_ancestor(self):
        alias = self.base / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        for operation in ('run', 'export', 'pack'):
            with self.subTest(operation=operation):
                out = alias / (operation + '-output')
                self.refused(self.cli(operation, out), 'symlink ancestor refused', out)
                self.assertFalse(out.exists())

    def test_all_operations_refuse_output_above_checkout(self):
        for operation in ('run', 'export', 'pack'):
            with self.subTest(operation=operation):
                self.refused(self.cli(operation, self.base), 'external output required', self.base)

    def test_all_operations_refuse_source_file_symlink(self):
        outside = self.base / 'outside'; outside.write_text(TOY)
        (self.root / 'source.txt').unlink(); (self.root / 'source.txt').symlink_to(outside)
        for operation in ('run', 'export', 'pack'):
            with self.subTest(operation=operation):
                out = self.base / (operation + '-output')
                self.refused(self.cli(operation, out), 'symlink ancestor refused', out)
                self.assertFalse(out.exists())

    def test_refuse_selected_source_parent_symlink(self):
        outside = self.base / 'outside'; outside.mkdir(); (outside / 'nested.txt').write_text(TOY)
        alias = self.root / 'source-link'; alias.symlink_to(outside, target_is_directory=True)
        out = self.base / 'run'
        self.refused(self.cli('run', out), 'symlink ancestor refused', out)
        self.assertFalse(out.exists())

    def test_dangling_selected_source_symlink(self):
        (self.root / 'dangling').symlink_to(self.base / 'missing')
        out = self.base / 'export'
        self.refused(self.cli('export', out), 'symlink ancestor refused', out)

    def test_inherited_output_preserved(self):
        out = self.base / 'run'; out.mkdir(); inherited = out / 'receipt.json'; inherited.write_text('old receipt')
        result = self.cli('run', out)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b'fresh output required', result.stderr)
        self.assertEqual(inherited.read_text(), 'old receipt')

    def test_child_source_mutation_cannot_claim_success(self):
        out = self.base / 'run'
        result = self.cli('run', out, '--', sys.executable, '-c', 'from pathlib import Path;Path("source.txt").write_text("changed")')
        self.assertEqual(result.returncode, 1, result.stderr.decode())
        record = json.loads((out / 'receipt.json').read_text())
        self.assertEqual(record['exit'], 0)
        self.assertIs(record['source_stable'], False)
        self.assertIs(record['current_checkout_acceptance'], False)

    def test_missing_child_has_no_success_receipt(self):
        out = self.base / 'run'
        result = self.cli('run', out, '--', str(self.base / 'missing-child'))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((out / 'receipt.json').exists())

    def test_runtime_dotenv_refused_without_reading_value(self):
        (self.root / '.env').write_text(TOY)
        out = self.base / 'run'
        self.refused(self.cli('run', out, '--', '/usr/bin/true'), 'runtime dotenv refused', out)
        self.assertNotIn(TOY.encode(), self.cli('run', self.base / 'second', '--', '/usr/bin/true').stderr)

    def test_runtime_dotenv_refused_by_all_source_operations(self):
        (self.root / '.env').write_text(TOY)
        for operation in ('run', 'export', 'pack'):
            with self.subTest(operation=operation):
                out = self.base / (operation + '-dotenv')
                self.refused(self.cli(operation, out), 'runtime dotenv refused', out)
                self.assertFalse(out.exists())

    def test_corpus_runtime_dotenv_refused_before_archive(self):
        corpus = self.base / 'corpus'; corpus.mkdir(); (corpus / '.env').write_text(TOY)
        out = self.base / 'pack'
        self.refused(self.cli('pack', out, '--corpus', str(corpus)), 'runtime dotenv refused', out)

    def test_immediate_parent_exit_cleans_owned_group_and_fails_capture(self):
        out = self.base / 'run'
        child = 'import json,os,subprocess,sys;p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]);print(json.dumps({"child_pid":p.pid,"group":os.getpgrp()}),flush=True)'
        result = self.cli('run', out, '--', sys.executable, '-c', child)
        self.assertEqual(result.returncode, 1, result.stderr.decode())
        record = json.loads((out / 'receipt.json').read_text())
        observed = json.loads((out / 'stdout.log').read_text())
        self.assertEqual(observed['group'], record['pid'])
        self.assertEqual(record['exit'], 0)
        self.assertIn('survived parent exit', record['error'])
        self.assertIs(record['cleanup']['survivors_detected'], True)
        self.assertIs(record['cleanup']['group_absent'], True)
        with self.assertRaises(ProcessLookupError):
            os.killpg(record['pid'], 0)

    def test_pack_corpus_symlink_refused(self):
        corpus = self.base / 'corpus'; corpus.mkdir(); (corpus / 'escaped').symlink_to(self.root / 'source.txt')
        out = self.base / 'pack'
        self.refused(self.cli('pack', out, '--corpus', str(corpus)), 'symlink ancestor refused', out)

    def test_pack_internal_corpus_refused(self):
        out = self.base / 'pack'
        self.refused(self.cli('pack', out, '--corpus', str(self.root)), 'external corpus required', out)

    def test_pack_output_cannot_change_measured_corpus(self):
        corpus = self.base / 'corpus'; corpus.mkdir(); (corpus / 'retained.txt').write_text('retained')
        out = corpus / 'output'
        self.refused(self.cli('pack', out, '--corpus', str(corpus)), 'output must be separate from corpus', out)
        self.assertEqual((corpus / 'retained.txt').read_text(), 'retained')

    def test_output_traversal_refused(self):
        out = self.base / 'unused' / '..' / 'escaped'
        self.refused(self.cli('export', out), 'absolute non-traversing path required', out)

    def test_baseline_versioned_child_excludes_toy_environment(self):
        entry = ENTRY.parent / 'replay-v2' / 'baseline-child.cjs'
        scratch = self.base / 'baseline-scratch'
        command = [NODE, str(entry), str(self.root), str(scratch), NODE, '-e', 'console.log(JSON.stringify(process.env))']
        result = subprocess.run(command, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertNotIn(TOY.encode(), result.stdout)
        self.assertNotIn(b'PROVIDER_TOKEN', result.stdout)
        self.assertIn(b'actual-baseline-readback', result.stdout)

    def test_baseline_and_linux_detect_detached_owned_group_survivors(self):
        frontend = self.root / 'frontend'; frontend.mkdir(); (frontend / 'input.txt').write_text('input')
        manifest = self.base / 'manifest.json'
        manifest.write_text(json.dumps({'files': {'frontend/input.txt': hashlib.sha256(b'input').hexdigest()}}))
        child = 'const p=require("child_process").spawn(process.execPath,["-e","setTimeout(()=>{},60000)"],{stdio:"ignore"});p.unref();console.log(JSON.stringify({child_pid:p.pid,group:process.pid}));process.exit(0)'
        for name, args in [('baseline-child.cjs', [str(frontend), str(self.base / 'baseline')]),
                           ('linux-run.cjs', [str(self.root), str(manifest), str(self.base / 'linux'), 'plain'])]:
            with self.subTest(entry=name):
                result = subprocess.run([NODE, str(ENTRY.parent / 'replay-v2' / name), *args, NODE, '-e', child],
                                        env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                records = [json.loads(line) for line in result.stdout.decode().splitlines() if line.startswith('{')]
                final = records[-1]
                observed = next(record for record in records if 'child_pid' in record)
                try:
                    self.assertEqual(result.returncode, 1, result.stderr.decode())
                    self.assertEqual(final['exit'], 0)
                    self.assertIs(final['cleanup']['survivorsDetected'], True)
                    self.assertIs(final['cleanup']['groupAbsent'], True)
                    with self.assertRaises(ProcessLookupError):
                        os.killpg(final['cleanup']['group'], 0)
                finally:
                    # This same fixture is also run against the old producer; clean only its observed owned group.
                    try:
                        group = os.getpgid(observed['child_pid'])
                    except ProcessLookupError:
                        group = None
                    if group is not None:
                        self.assertEqual(group, observed['group'])
                        os.killpg(group, signal.SIGTERM)
                        for _ in range(100):
                            try:
                                os.killpg(group, 0)
                            except ProcessLookupError:
                                break
                            time.sleep(.05)
                        else:
                            self.fail('owned fixture group survived cleanup')

    def test_native_and_preview_refuse_output_ancestor_before_fixture_creation(self):
        (self.root / 'frontend').mkdir()
        alias = self.base / 'alias'; alias.symlink_to(self.root, target_is_directory=True)
        cache = self.base / 'cache'; cache.mkdir()
        for name, args in [('native-builder.cjs', [str(self.root), str(alias / 'native'), str(cache)]),
                           ('preview.cjs', [str(self.root / 'frontend'), '13048', str(alias / 'preview'), str(cache), str(cache)])]:
            with self.subTest(entry=name):
                result = subprocess.run([NODE, str(ENTRY.parent / 'replay-v2' / name), *args], env=self.env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                self.assertEqual(result.returncode, 1)
                self.assertIn(b'symlink ancestor refused', result.stderr)
                self.assertFalse((self.root / ('native' if name.startswith('native') else 'preview')).exists())


class CacheAuthorityControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = Path(self.temp.name).resolve() / 'fixture'
        self.fixture.mkdir()
        spec = importlib.util.spec_from_file_location('owned_cache_control', ENTRY.with_name('npm_cache_control_v2.py'))
        self.cache = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cache)

    def test_regular_cached_package_bytes_remain_measured(self):
        member = self.fixture / 'node_modules' / 'sprintf-js' / 'package.json'
        member.parent.mkdir(parents=True)
        member.write_text('{"name":"sprintf-js"}')
        self.assertEqual(self.cache.files(self.fixture), {
            'node_modules/sprintf-js/package.json': hashlib.sha256(member.read_bytes()).hexdigest()})

    def test_npm_configuration_and_alternate_lock_refuse_before_read(self):
        original_read = Path.read_bytes
        for name in ('.npmrc', '.NPMRC', '.NpMrC', 'npm-shrinkwrap.json',
                     'NPM-SHRINKWRAP.JSON', 'Npm-Shrinkwrap.Json'):
            for parent in (self.fixture, self.fixture / 'node_modules' / 'sprintf-js'):
                with self.subTest(name=name, parent=str(parent.relative_to(self.fixture))):
                    parent.mkdir(parents=True, exist_ok=True)
                    member = parent / name
                    member.write_text(TOY)
                    def checked_read(path):
                        self.assertNotEqual(path, member, 'Supplemental npm authority bytes were read')
                        return original_read(path)
                    try:
                        with patch.object(Path, 'read_bytes', checked_read):
                            with self.assertRaisesRegex(ValueError, 'Supplemental npm authority refused'):
                                self.cache.files(self.fixture)
                    finally:
                        member.unlink()


if __name__ == '__main__':
    unittest.main(verbosity=2)

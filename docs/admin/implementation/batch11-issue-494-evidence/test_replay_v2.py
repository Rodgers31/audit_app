"""Execute portable replay boundaries with toy secrets and real relocated Git fixtures."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
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


if __name__ == '__main__':
    unittest.main(verbosity=2)

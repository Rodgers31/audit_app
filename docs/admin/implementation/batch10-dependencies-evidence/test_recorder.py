"""Execute recorder failure controls in disposable Git fixtures only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class RecorderControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='batch10-dependencies-recorder-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.runner = self.root / 'docs/admin/implementation/batch10-dependencies-evidence/run.py'
        self.runner.parent.mkdir(parents=True)
        self.runner.write_bytes(Path(__file__).with_name('run.py').read_bytes())
        self.start_hash = hashlib.sha256(self.runner.read_bytes()).hexdigest()
        self.out = Path(self.temp.name) / 'raw'
        self.out.mkdir()
        for command in (['git', 'init', '-q'], ['git', 'add', '.'],
                        ['git', '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture']):
            subprocess.run(command, cwd=self.root, check=True, capture_output=True)

    def execute(self, code, name='control'):
        return subprocess.run([sys.executable, str(self.runner), name, str(self.root), sys.executable, '-c', code],
                              env=dict(os.environ, BATCH10_DEPENDENCIES_OUTPUT=str(self.out)),
                              capture_output=True, timeout=30)

    def receipt(self):
        return json.loads((self.out / 'control.json').read_bytes())

    def test_positive(self):
        self.assertEqual(self.execute('print("actual child")').returncode, 0)
        self.assertEqual(self.receipt()['generator_sha256'], self.start_hash)
        self.assertTrue(self.receipt()['source_stable'])

    def test_failed_child(self):
        self.assertEqual(self.execute('raise SystemExit(7)').returncode, 1)
        self.assertEqual(self.receipt()['exit'], 7)
        self.assertEqual(self.receipt()['verification_exit'], 1)

    def test_generator_mutation_records_starting_bytes(self):
        self.assertEqual(self.execute('from pathlib import Path;p=Path("docs/admin/implementation/batch10-dependencies-evidence/run.py");p.write_text(p.read_text()+"\\n# changed\\n")').returncode, 1)
        self.assertEqual(self.receipt()['generator_sha256'], self.start_hash)
        self.assertFalse(self.receipt()['source_stable'])

    def test_added_source_fails(self):
        self.assertEqual(self.execute('from pathlib import Path;Path("new.py").write_text("changed")').returncode, 1)
        self.assertFalse(self.receipt()['source_stable'])

    def test_added_candidate_input_fails(self):
        candidate = Path(self.temp.name) / 'candidate'
        candidate.mkdir()
        result = subprocess.run([sys.executable, str(self.runner), 'control', str(candidate), sys.executable,
                                 '-c', 'from pathlib import Path;Path("package-lock.json").write_text("new input")'],
                                env=dict(os.environ, BATCH10_DEPENDENCIES_OUTPUT=str(self.out)),
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.receipt()['source_stable'])

    def test_deleted_source_fails(self):
        self.assertEqual(self.execute('from pathlib import Path;Path("docs/admin/implementation/batch10-dependencies-evidence/run.py").unlink()').returncode, 1)
        self.assertIsNone(self.receipt()['source_after']['files']['docs/admin/implementation/batch10-dependencies-evidence/run.py'])
        self.assertEqual(self.receipt()['generator_sha256'], self.start_hash)

    def test_output_collision_prevents_execution(self):
        (self.out / 'control.stdout').write_text('retained')
        self.assertNotEqual(self.execute('from pathlib import Path;Path("executed").touch()').returncode, 0)
        self.assertFalse((self.root / 'executed').exists())
        self.assertEqual((self.out / 'control.stdout').read_text(), 'retained')

    def test_missing_output_prevents_execution(self):
        self.out.rmdir()
        self.assertNotEqual(self.execute('from pathlib import Path;Path("executed").touch()').returncode, 0)
        self.assertFalse((self.root / 'executed').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)

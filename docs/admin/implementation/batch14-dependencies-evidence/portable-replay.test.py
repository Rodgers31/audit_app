"""Executable portability regression; requires the real prepared fixture."""
import json
import contextlib
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest

PACKET = Path(__file__).resolve().parent


class PortableReplay(unittest.TestCase):
    def test_all_three_entrypoints_replay_from_unrelated_cwd(self):
        baseline = os.environ['BATCH14_REPLAY_BASELINE']
        candidate = os.environ['BATCH14_REPLAY_CANDIDATE']
        entries = [('node', 'spec-review/blocker.cjs', 'blocker'),
                   ('node', 'spec-review/review.cjs', 'spec'),
                   ('python3', 'standards-review/run.py', 'standards')]
        retained = os.environ.get('BATCH14_REPLAY_TEST_OUTPUT')
        if retained:
            Path(retained).mkdir(parents=True, exist_ok=False)
        context = contextlib.nullcontext(retained) if retained else tempfile.TemporaryDirectory(prefix='batch14-portability-test-')
        with context as directory:
            relocated = Path(directory) / "packet"
            shutil.copytree(PACKET, relocated)
            for runtime, entry, mode in entries:
                with self.subTest(mode=mode):
                    output = Path(directory) / mode
                    child = subprocess.run([runtime, str(relocated / entry), '--baseline', baseline,
                                            '--candidate', candidate, '--output', str(output)],
                                           cwd=directory, capture_output=True, text=True, timeout=420)
                    self.assertEqual(child.returncode, 0, child.stdout + child.stderr)
                    result = json.loads((output / 'result.json').read_text())
                    self.assertTrue(result['replay_completed'])
                    self.assertFalse(result['candidate_compatible'])
                    self.assertTrue(json.loads((output / 'cleanup.json').read_text())['absent'])
                    self.assertTrue(list(output.glob('*.receipt.json')))
                    for receipt in output.glob('*.receipt.json'):
                        value = json.loads(receipt.read_text())
                        self.assertTrue(value['verified'])
                        self.assertTrue(Path(value['cwd']).is_absolute())


if __name__ == '__main__':
    unittest.main()

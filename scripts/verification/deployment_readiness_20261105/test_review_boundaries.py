"""Persistent independent-review symptoms, using only owned inert fixtures."""
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('reviewed_packet', Path(__file__).with_name('packet.py'))
packet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packet)


def pending_matrix():
    return {'schema': 'deployment-readiness-matrix-v1', 'scope': 'PREPARATION_ONLY',
            'release_authorized': False,
            'controls': {k: False for k in packet.OFF_CONTROLS},
            'gates': [{'id': n, 'state': 'pending_engineering', 'evidence': [],
                       'next': 'specific held observation', 'authority': 'engineering'}
                      for n in packet.GATE_IDS]}


class ReviewBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_scientific_notation_overflow_cannot_enter_json_proof(self):
        p = self.base / 'overflow.json'
        p.write_text('{"x":1e999}')
        with self.assertRaises(packet.Refusal):
            packet.load_object(p)

    def test_large_integer_is_a_controlled_refusal(self):
        p = self.base / 'large-integer.json'
        p.write_text('{"x":' + '9' * 5000 + '}')
        try:
            packet.load_object(p)
            outcome = 'ACCEPTED'
        except packet.Refusal:
            outcome = 'REFUSED'
        except Exception as error:
            outcome = type(error).__name__
        self.assertEqual(outcome, 'REFUSED')

    def test_deep_json_is_a_controlled_refusal(self):
        p = self.base / 'deep.json'
        p.write_text('{"x":' + '[' * 2000 + '0' + ']' * 2000 + '}')
        try:
            packet.load_object(p)
            outcome = 'ACCEPTED'
        except packet.Refusal:
            outcome = 'REFUSED'
        except Exception as error:
            outcome = type(error).__name__
        self.assertEqual(outcome, 'REFUSED')

    def test_json_inventory_depth_and_node_bounds(self):
        at_depth = '0'
        for _ in range(32):
            at_depth = '{"x":' + at_depth + '}'
        self.assertIsInstance(packet.parse_object(at_depth), dict)
        with self.assertRaises(packet.Refusal):
            packet.parse_object('{"x":' + at_depth + '}')
        at_nodes = '{"x":[' + ','.join(['0'] * 19_998) + ']}'
        self.assertEqual(len(packet.parse_object(at_nodes)['x']), 19_998)
        with self.assertRaises(packet.Refusal):
            packet.parse_object('{"x":[' + ','.join(['0'] * 19_999) + ']}')

    def test_text_json_uses_encoded_byte_ceiling(self):
        count = (4 * 1024 * 1024 - 8) // 2
        exact = '{"x":"' + '\u00e9' * count + '"}'
        self.assertEqual(len(exact.encode('utf-8')), 4 * 1024 * 1024)
        self.assertEqual(len(packet.parse_object(exact)['x']), count)
        above = '{"x":"' + '\u00e9' * (count + 1) + '"}'
        with self.assertRaises(packet.Refusal):
            packet.parse_object(above)
        with self.assertRaises(packet.Refusal):
            packet.parse_object('{"x":"\ud800"}')

    def test_historical_leaf_requires_actual_catalog_resolved_evidence(self):
        matrix = pending_matrix()
        matrix['gates'][0]['state'] = 'historical_scoped'
        with self.assertRaises(packet.Refusal):
            packet.check_matrix(matrix)

    def test_direct_matrix_helper_validates_record_values(self):
        matrix = pending_matrix()
        matrix['gates'][0]['state'] = 'historical_scoped'
        matrix['gates'][0]['evidence'] = ['original']
        valid = {'id': 'original', 'sha256': 'a' * 64, 'bytes': 1, 'scope': 'DATED_LEAF_ONLY'}
        self.assertEqual(packet.check_matrix(matrix, {'original': valid})['release'], 'HELD')
        with self.assertRaises(packet.Refusal):
            packet.check_matrix(matrix, {'original': {}})
        matrix['gates'][0]['evidence'] = ['invented_original']
        with self.assertRaises(packet.Refusal):
            packet.check_matrix(matrix)

    def test_census_name_allocation_stops_at_budget_plus_one(self):
        root = self.base / 'root'
        root.mkdir()
        for i in range(20):
            (root / ('candidate-' + str(i))).touch()
        count = [0]
        original_listdir, original_scandir = os.listdir, os.scandir
        def listdir(fd):
            names = original_listdir(fd)
            count[0] += len(names)
            return names
        class CountingScanner:
            def __init__(self, fd): self.inner = original_scandir(fd)
            def __enter__(self): self.inner.__enter__(); return self
            def __exit__(self, *args): return self.inner.__exit__(*args)
            def __iter__(self): return self
            def __next__(self):
                item = next(self.inner)
                count[0] += 1
                return item
        with mock.patch.object(packet.os, 'listdir', listdir), mock.patch.object(packet.os, 'scandir', CountingScanner):
            with self.assertRaises(packet.Refusal):
                packet.metadata([root], max_entries=3, max_depth=1)
        self.assertGreater(count[0], 0)
        self.assertLessEqual(count[0], 3)

    def test_root_substitution_refuses_mixed_generation_metadata(self):
        root, old = self.base / 'root', self.base / 'old'
        root.mkdir()
        (root / 'same-name.dump').write_bytes(b'a')
        triggered = [False]
        original_listdir, original_scandir = os.listdir, os.scandir
        def replace_root():
            if not triggered[0]:
                triggered[0] = True
                root.rename(old)
                root.mkdir()
                (root / 'same-name.dump').write_bytes(b'changed')
        def listdir(fd):
            names = original_listdir(fd)
            replace_root()
            return names
        class GatedScanner:
            def __init__(self, fd): self.inner = original_scandir(fd)
            def __enter__(self):
                inner = self.inner.__enter__()
                replace_root()
                return inner
            def __exit__(self, *args): return self.inner.__exit__(*args)
        with mock.patch.object(packet.os, 'listdir', listdir), mock.patch.object(packet.os, 'scandir', GatedScanner):
            with self.assertRaises(packet.Refusal):
                packet.metadata([root], max_entries=10, max_depth=2)
        self.assertTrue(triggered[0], 'the competing substitution must actually occur')

    def test_matrix_only_manifest_cannot_certify_packet_source_integrity(self):
        root = self.base / 'source'
        directory = root / 'docs/releases/deployment-readiness-20261105'
        directory.mkdir(parents=True)
        (directory / 'gate-matrix.json').write_text(json.dumps(pending_matrix()))
        matrix_name = 'docs/releases/deployment-readiness-20261105/gate-matrix.json'
        manifest = {'schema': 'deployment-readiness-source-v1', 'baseline_commit': 'a' * 40,
                    'baseline_tree': 'b' * 40, 'matrix': matrix_name,
                    'files': packet.inventory(root, [matrix_name])}
        path = directory / 'source-manifest.json'
        path.write_text(json.dumps(manifest))
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = packet.main(['--root', str(root), 'integrity', '--manifest', str(path)])
        self.assertEqual(result, 2)


if __name__ == '__main__':
    unittest.main()

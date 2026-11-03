"""Pure telemetry controls; no worker, Docker, database or provider is started."""
from copy import deepcopy
import hashlib
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parents[3] / 'tools/worker_rehearsal'
assess = runpy.run_path(str(HERE / 'capacity_v2.py'))['assess']
fixture = runpy.run_path(str(Path(__file__).with_name('test_worker_rehearsal_guards.py')))['evidence']


class CapacityV2(unittest.TestCase):
    def test_complete_control_has_only_unauthenticated_offline_scope(self):
        result = assess(*fixture())
        self.assertEqual(result['assessment_version'], 2)
        self.assertEqual(result['published'], 6)
        self.assertIs(result['production_accepted'], False)
        self.assertIs(result['evidence_authenticated'], False)
        self.assertAlmostEqual(result['maximum_sample_gap_seconds'], 8.9)

    def test_long_internal_gap_refuses_even_with_count_and_endpoints(self):
        value = fixture()
        for i, sample in enumerate(value[0]):
            sample['elapsed'] = 179 if i == 20 else 1 + i * .01
        self.assertEqual(len(value[0]), 21)
        with self.assertRaisesRegex(ValueError, 'gap'):
            assess(*value)

    def test_fifteen_second_gap_is_inclusive(self):
        for gap, accepted in ((15, True), (15.0001, False)):
            value = fixture()
            times = [1, 1 + gap] + [1 + gap + (178 - gap) * i / 19 for i in range(1, 20)]
            for sample, elapsed in zip(value[0], times):
                sample['elapsed'] = elapsed
            if accepted:
                self.assertEqual(assess(*value)['maximum_sample_gap_seconds'], 15)
            else:
                with self.assertRaisesRegex(ValueError, 'gap'):
                    assess(*value)

    def test_thresholds_cannot_weaken_the_fixed_profile(self):
        for key, bad in (
            ('memory_peak_bytes', 10**30), ('steady_mean_cpu', float('inf')),
            ('steady_mean_cpu', float('nan')), ('duration_seconds', 0),
            ('minimum_published', 0), ('worker_connections', True),
            ('api_max_seconds', '3'), ('api_p95_seconds', True),
        ):
            value = deepcopy(fixture())
            value[7][key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                assess(*value)

    def test_threshold_shape_and_exact_scalar_types(self):
        value = fixture()
        value[7] = dict(value[7], extra=15)
        with self.assertRaises(ValueError):
            assess(*value)
        value = fixture()
        value[7] = dict(value[7])
        value[7].pop('host_window_seconds')
        with self.assertRaises(ValueError):
            assess(*value)
        for bad in (None, [], True):
            value = fixture()
            value[7] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                assess(*value)

    def test_duration_is_finite_and_bounded_at_the_direct_api(self):
        for bad in (True, False, 0, -1, 179, 901, float('nan'), float('inf'), None, '180'):
            value = fixture()
            value[6] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                assess(*value)

    def test_absent_empty_or_nonmonotonic_samples_refuse(self):
        for bad in (None, [], {}, True):
            value = fixture()
            value[0] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                assess(*value)
        for bad in (0, -1, True, float('nan'), float('inf'), None, '2'):
            value = fixture()
            value[0][1]['elapsed'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                assess(*value)

    def test_absent_activity_and_bad_telemetry_still_refuse(self):
        for index, key in ((0, 'processes'), (2, 'social_post_targets'), (2, 'statements')):
            value = fixture()
            if index == 0:
                value[0][0][key] = []
            else:
                value[index][key] = []
            with self.subTest(key=key), self.assertRaises(ValueError):
                assess(*value)
        for index in (1, 5):
            value = fixture()
            value[index] = []
            with self.subTest(index=index), self.assertRaises(ValueError):
                assess(*value)

    def test_inputs_are_not_mutated(self):
        value = fixture()
        before = deepcopy(value)
        assess(*value)
        self.assertEqual(value, before)

    def test_duplicate_identities_cannot_inflate_measured_work(self):
        value = fixture()
        for row in value[2]['social_post_targets']:
            row['id'] = 'image-target'
        with self.assertRaisesRegex(ValueError, 'Duplicate target'):
            assess(*value)
        value = fixture()
        for sample in value[0]:
            sample['processes'].append(dict(sample['processes'][1]))
        with self.assertRaisesRegex(ValueError, 'Duplicate process'):
            assess(*value)

    def test_loaded_source_drift_cannot_relabel_executed_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('capacity_v2.py', 'qualification.py', 'run.py'):
                (root / name).write_bytes((HERE / name).read_bytes())
            helper = root / 'capacity_v2.py'
            loaded = runpy.run_path(str(helper))['assess']
            loaded_hash = hashlib.sha256(helper.read_bytes()).hexdigest()
            self.assertEqual(loaded(*fixture())['assessor_sha256'], loaded_hash)
            helper.write_bytes(helper.read_bytes() + b'\n# owned source drift after load\n')
            with self.assertRaisesRegex(ValueError, 'Loaded assessor source changed'):
                loaded(*fixture())

    def test_archive_execution_uses_the_exact_verified_bytes(self):
        for dependency in ('qualification.py', 'run.py'):
            with self.subTest(dependency=dependency), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                for name in ('capacity_v2.py', 'qualification.py', 'run.py'):
                    (root / name).write_bytes((HERE / name).read_bytes())
                target = root / dependency
                original = target.read_bytes()
                marker = root / 'unverified-execution'
                altered = original + (
                    '\nfrom pathlib import Path\nPath(' + repr(str(marker))
                    + ').write_text("owned-interleaving")\n'
                ).encode()
                original_read, triggered = Path.read_bytes, []

                def interleaved_read(path):
                    content = original_read(path)
                    if path == target and not triggered:
                        triggered.append(True)
                        target.write_bytes(altered)
                    return content

                try:
                    with patch.object(Path, 'read_bytes', interleaved_read):
                        loaded = runpy.run_path(str(root / 'capacity_v2.py'))
                finally:
                    target.write_bytes(original)
                self.assertEqual(triggered, [True])
                self.assertFalse(marker.exists(), 'Archive executed bytes outside its verified hash')
                result = loaded['assess'](*fixture())
                self.assertEqual(result['archived_dependency_sha256'][dependency],
                                 hashlib.sha256(original).hexdigest())


if __name__ == '__main__':
    unittest.main(verbosity=2)

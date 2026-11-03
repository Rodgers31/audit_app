"""Pure telemetry controls; no worker, Docker, database or provider is started."""
from copy import deepcopy
import builtins
import importlib.util
import hashlib
import os
from pathlib import Path
import py_compile
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parents[3] / 'tools/worker_rehearsal'
assess = runpy.run_path(str(HERE / 'capacity_v2.py'))['assess']
fixture = runpy.run_path(str(Path(__file__).with_name('test_worker_rehearsal_guards.py')))['evidence']


class CapacityV2(unittest.TestCase):
    def test_source_replaced_between_compile_and_exec_cannot_relabel_assessor(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for source in HERE.glob('*.py'):
                (root / source.name).write_bytes(source.read_bytes())
            implementation = root / 'capacity_v2_assessor.py'
            if not implementation.exists():
                implementation = root / 'capacity_v2.py'
            original = implementation.read_bytes()
            replacement = original.replace(b'_MAXIMUM_GAP_SECONDS = 15\n',
                                           b'_MAXIMUM_GAP_SECONDS = 1500\n')
            self.assertNotEqual(original, replacement, 'Owned boundary fixture did not change')
            original_compile, swaps = builtins.compile, []

            def compile_then_replace(source, filename, *args, **kwargs):
                compiled = original_compile(source, filename, *args, **kwargs)
                if str(filename) == str(implementation) and not swaps:
                    swaps.append(True)
                    implementation.write_bytes(replacement)
                return compiled

            with patch.object(builtins, 'compile', compile_then_replace):
                loaded = runpy.run_path(str(root / 'capacity_v2.py'))
            self.assertEqual(swaps, [True], 'Compile/execute interleaving did not run')
            try:
                result = loaded['assess'](*fixture())
            except ValueError as exc:
                self.assertIn('Loaded assessor source changed', str(exc))
            else:
                self.assertEqual(result['assessor_sha256'], hashlib.sha256(original).hexdigest(),
                                 'Reported replacement bytes while executing the original assessor')

    def test_complete_control_has_only_unauthenticated_offline_scope(self):
        result = assess(*fixture())
        self.assertEqual(result['assessment_version'], 2)
        self.assertEqual(result['published'], 6)
        self.assertIs(result['production_accepted'], False)
        self.assertIs(result['evidence_authenticated'], False)
        self.assertAlmostEqual(result['maximum_sample_gap_seconds'], 8.9)
        self.assertEqual(result['assessor_sha256'],
                         hashlib.sha256((HERE / 'capacity_v2_assessor.py').read_bytes()).hexdigest())
        self.assertEqual(result['assessor_entrypoint'], 'capacity_v2_assessor.py')
        self.assertEqual(result['source_identity_scope'],
                         'implementation bytes compiled by externally trusted capacity_v2.py')

    def test_public_import_uses_the_same_implementation_identity(self):
        spec = importlib.util.spec_from_file_location('owned_capacity_loader', HERE / 'capacity_v2.py')
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        self.assertEqual(loaded.assess(*fixture()), assess(*fixture()))

    def test_implementation_refuses_unsupported_direct_entry_points(self):
        implementation = HERE / 'capacity_v2_assessor.py'
        with self.assertRaisesRegex(RuntimeError, 'through tools.worker_rehearsal.capacity_v2'):
            runpy.run_path(str(implementation))
        spec = importlib.util.spec_from_file_location('unsupported_capacity_implementation', implementation)
        with self.assertRaisesRegex(RuntimeError, 'through tools.worker_rehearsal.capacity_v2'):
            spec.loader.exec_module(importlib.util.module_from_spec(spec))
        compiled = compile(implementation.read_bytes(), str(implementation), 'exec', dont_inherit=True)
        for bad in (None, True, '', bytearray()):
            with self.subTest(bad=bad), self.assertRaisesRegex(RuntimeError, 'through tools.worker_rehearsal.capacity_v2'):
                exec(compiled, {'__file__': str(implementation), '_ASSESSOR_SOURCE_BYTES': bad})

    def test_cli_has_no_implicit_assessment_and_implementation_refuses(self):
        flags = ['-O'] if sys.flags.optimize else []
        for name, accepted in (('capacity_v2.py', True), ('capacity_v2_assessor.py', False)):
            child = subprocess.run([sys.executable, *flags, str(HERE / name)],
                                   capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(child.stdout, '', 'A CLI load must not publish an assessment')
            if accepted:
                self.assertEqual(child.returncode, 0, child.stderr)
                self.assertEqual(child.stderr, '')
            else:
                self.assertNotEqual(child.returncode, 0)
                self.assertIn('through tools.worker_rehearsal.capacity_v2', child.stderr)

    def test_missing_empty_or_malformed_implementation_cannot_return_an_assessor(self):
        for bad, error in ((None, FileNotFoundError), (b'', KeyError), (b'broken (', SyntaxError)):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                (root / 'capacity_v2.py').write_bytes((HERE / 'capacity_v2.py').read_bytes())
                if bad is not None:
                    (root / 'capacity_v2_assessor.py').write_bytes(bad)
                with self.assertRaises(error):
                    runpy.run_path(str(root / 'capacity_v2.py'))

    def test_stale_implementation_bytecode_is_not_executed_or_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('capacity_v2.py', 'capacity_v2_assessor.py', 'qualification.py', 'run.py'):
                (root / name).write_bytes((HERE / name).read_bytes())
            implementation = root / 'capacity_v2_assessor.py'
            original = implementation.read_bytes()
            marker = root / 'unverified-bytecode-executed'
            replacement = ('from pathlib import Path\nPath(' + repr(str(marker)) + ').touch()\n').encode()
            replacement += b'#' + b' ' * (len(original) - len(replacement) - 1)
            self.assertEqual(len(replacement), len(original), 'Cache must match source size')
            implementation.write_bytes(replacement)
            stat = implementation.stat()
            py_compile.compile(str(implementation), doraise=True)
            implementation.write_bytes(original)
            os.utime(implementation, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            loaded = runpy.run_path(str(root / 'capacity_v2.py'))['assess']
            self.assertEqual(loaded(*fixture())['assessor_sha256'], hashlib.sha256(original).hexdigest())
            self.assertFalse(marker.exists())

    def test_source_drift_during_assessment_cannot_publish_a_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('capacity_v2.py', 'capacity_v2_assessor.py', 'qualification.py', 'run.py'):
                (root / name).write_bytes((HERE / name).read_bytes())
            loaded = runpy.run_path(str(root / 'capacity_v2.py'))['assess']
            original_assess = loaded.__globals__['_LEGACY']['assess']
            implementation = root / 'capacity_v2_assessor.py'

            def drift_after_validation(*args):
                result = original_assess(*args)
                implementation.write_bytes(implementation.read_bytes() + b'\n# owned drift\n')
                return result

            with patch.dict(loaded.__globals__['_LEGACY'], assess=drift_after_validation):
                with self.assertRaisesRegex(ValueError, 'Loaded assessor source changed'):
                    loaded(*fixture())

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
            for name in ('capacity_v2.py', 'capacity_v2_assessor.py', 'qualification.py', 'run.py'):
                (root / name).write_bytes((HERE / name).read_bytes())
            helper = root / 'capacity_v2_assessor.py'
            loaded = runpy.run_path(str(root / 'capacity_v2.py'))['assess']
            loaded_hash = hashlib.sha256(helper.read_bytes()).hexdigest()
            self.assertEqual(loaded(*fixture())['assessor_sha256'], loaded_hash)
            helper.write_bytes(helper.read_bytes() + b'\n# owned source drift after load\n')
            with self.assertRaisesRegex(ValueError, 'Loaded assessor source changed'):
                loaded(*fixture())

    def test_archive_execution_uses_the_exact_verified_bytes(self):
        for dependency in ('qualification.py', 'run.py'):
            with self.subTest(dependency=dependency), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                for name in ('capacity_v2.py', 'capacity_v2_assessor.py', 'qualification.py', 'run.py'):
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

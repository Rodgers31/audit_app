"""Executable regressions for false-green capacity and unsafe output paths."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


def module(name):
    path = Path(__file__).resolve().parents[3] / 'tools/worker_rehearsal' / (name + '.py')
    spec = importlib.util.spec_from_file_location('rehearsal_' + name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


qualification = module('qualification')
runner = module('run')


def evidence():
    processes = [dict(pid=1, rss=1024, threads=1, argv=['python', '-m', 'social_worker_supervisor']),
        dict(pid=7, rss=1024, threads=1, argv=['gunicorn', 'main:app']),
        dict(pid=8, rss=1024, threads=3, argv=['python', '-m', 'social.worker'])]
    samples = [dict(memory=200 * 1024 ** 2, peak=250 * 1024 ** 2, elapsed=1 + i * 8.9,
        cpu={'usage_usec': str(1000000 + i * 100000)}, oom={'oom_kill': '0'},
        processes=deepcopy(processes)) for i in range(21)]
    before = dict(wall_started=1, measurement_started=1, server_bytes=100, client_bytes=100, active=1, connections=1, peak_active=1, upstream_failures=0)
    after = dict(before, wall_completed=181, measurement_completed=181, server_bytes=1000, client_bytes=1000)
    census = dict(connections=1, statements=[dict(query='SELECT fixture', calls=2)],
        statements_before=[dict(query='SELECT fixture',calls=1)],
        cohort=dict(run_id='owned-run',case='capacity',target_id='image-target',
                    media_paths=['/media-test/owned'],provider_paths=['/feed']),
        social_post_targets=[dict(id='image-target' if i==0 else 'text-'+str(i),
            state='published',published_at='1970-01-01T00:00:03+00:00') for i in range(6)])
    requests = [dict(request_id='post-'+str(i), method='POST', path='/feed', started=1 + i * 25) for i in range(6)]
    requests += [dict(request_id='post-'+str(i), method='POST', path='/feed', completed=2 + i * 25) for i in range(6)]
    requests += [dict(request_id='media', method='GET', path='/media-test/owned', started=2),
                 dict(request_id='media', method='GET', path='/media-test/owned', completed=3, output_bytes=1024)]
    for row in requests: row.update(run_id='owned-run',case='capacity')
    return [samples, [.01] * 100, census, before, after, requests, 180, runner.THRESHOLDS]


class CapacityGuards(unittest.TestCase):
    def test_live_baseline_is_accepted(self):
        self.assertEqual(qualification.assess(*evidence())['published'], 6)

    def test_empty_sql_baseline_refuses(self):
        value = evidence()
        value[2]['statements_before'] = []
        with self.assertRaises(ValueError):
            qualification.assess(*value)

    def test_wrong_run_target_and_cumulative_sql_refuse(self):
        for mutation in ('run', 'target', 'sql', 'publication'):
            value = evidence()
            if mutation == 'run':
                for event in value[5]: event['run_id'] = 'other-run'
            elif mutation == 'target':
                for event in value[5]:
                    if event['method'] == 'GET': event['path'] = '/media-test/foreign'
            elif mutation == 'sql':
                value[2]['statements_before'] = value[2]['statements']
            else:
                for target in value[2]['social_post_targets']:
                    target['published_at'] = '1970-01-01T00:00:00+00:00'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                qualification.assess(*value)

    def test_dead_worker_zero_work_and_unbounded_transfer_cannot_pass(self):
        for key in ('processes', 'memory', 'peak'):
            value = evidence()
            for sample in value[0]:
                sample[key] = [] if key == 'processes' else 0
            with self.subTest(key=key), self.assertRaises(ValueError):
                qualification.assess(*value)
        for key, bad in [('server_bytes', 10 ** 30), ('peak_active', 10000), ('server_bytes', 100)]:
            value = evidence()
            value[4][key] = bad
            with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                qualification.assess(*value)
        for index, key in [(2, 'statements'), (2, 'social_post_targets')]:
            value = evidence()
            value[index][key] = []
            with self.assertRaises(ValueError):
                qualification.assess(*value)
        value = evidence()
        value[5] = []
        with self.assertRaises(ValueError):
            qualification.assess(*value)

    def test_hostile_telemetry_is_not_a_measurement(self):
        for bad in (True, False, -1, 0, float('nan'), float('inf'), None, '1'):
            for key in ('memory', 'peak', 'elapsed'):
                value = evidence()
                value[0][0][key] = bad
                with self.subTest(bad=bad, key=key), self.assertRaises(ValueError):
                    qualification.assess(*value)
            value = evidence()
            value[1][0] = bad
            with self.subTest(bad=bad, key='latency'), self.assertRaises(ValueError):
                qualification.assess(*value)

    def test_early_burst_does_not_certify_sustained_processing(self):
        value = evidence()
        for item in value[5]:
            if 'started' in item:
                item['started'] = 1
        with self.assertRaises(ValueError):
            qualification.assess(*value)

    def test_single_pid_and_short_samples_cannot_certify_shared_capacity(self):
        value = evidence()
        for sample in value[0]:
            sample['processes'] = [dict(pid=1, rss=1024, threads=1,
                argv=['python', '-m', 'social_worker_supervisor', 'social.worker', 'gunicorn', 'main:app'])]
        with self.assertRaises(ValueError):
            qualification.assess(*value)
        value = evidence()
        for index, sample in enumerate(value[0]):
            sample['elapsed'] = 1 + index / 20
        with self.assertRaises(ValueError):
            qualification.assess(*value)

    def test_post_completion_before_start_or_wrong_identity_refuses(self):
        for mutation in ('time', 'identity', 'duplicate', 'path'):
            value = evidence()
            if mutation == 'time':
                value[5][7]['completed'] = 1
            elif mutation == 'identity':
                value[5][7]['request_id'] = 'other'
            elif mutation == 'duplicate':
                value[5][7]['request_id'] = value[5][6]['request_id']
            else:
                value[5][7]['path'] = '/different'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                qualification.assess(*value)

    def test_media_outside_measured_api_window_refuses(self):
        value = evidence()
        value[5][-2]['started'] = 0.1
        value[5][-1]['completed'] = 0.2
        with self.assertRaises(ValueError):
            qualification.assess(*value)

    def test_extra_native_executor_thread_refuses(self):
        value = evidence()
        for sample in value[0]:
            sample['processes'][2]['threads'] = 4
        with self.assertRaises(ValueError):
            qualification.assess(*value)

    def test_wire_counters_are_bounded_and_consistent(self):
        for key, bad in [('client_bytes', 10 ** 30), ('active', 10000), ('connections', 0)]:
            value = evidence()
            value[4][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError):
                qualification.assess(*value)


class OutputGuards(unittest.TestCase):
    def test_boolean_readback_cannot_be_replaced_by_an_integer(self):
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            with patch.object(Path, 'read_text', return_value='{"passed":1}'):
                with self.assertRaises(RuntimeError):
                    runner.write_json(Path(raw) / 'receipt.json', {'passed': True})

    def test_transient_container_commands_have_owned_names_and_labels(self):
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as raw:
            tool = runner.Rehearsal.__new__(runner.Rehearsal)
            tool.out = Path(raw)
            tool.run_id = 'owned_probe'
            tool.command_sequence = 0
            tool.provenance = {'scope': 'unit-transport-double'}
            with patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=0, stdout='owned output', stderr='')) as child:
                tool.cmd(['run', '--rm', '--network=none', 'inert-image', 'inert-command'])
            argv = child.call_args.args[0]
            self.assertIn('--name', argv)
            self.assertTrue(argv[argv.index('--name') + 1].startswith('b15-worker-'))
            self.assertIn('b15-worker-run=owned_probe', argv)

    def test_existing_checkout_git_and_traversal_outputs_refuse_before_writing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            repo = root / 'other-repo'
            repo.mkdir()
            (repo / '.git').mkdir()
            for path in (repo / 'new-evidence', repo / '.git/new-evidence',
                         root / 'alias/../other-repo/new-evidence'):
                with self.subTest(path=path), self.assertRaises(RuntimeError):
                    runner.Rehearsal(path, 180, ['startup'])
                self.assertFalse((repo / 'new-evidence').exists())


if __name__ == '__main__':
    unittest.main()

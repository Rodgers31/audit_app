"""Executable report-bound regressions for the packet reader's verdict seams."""
import copy
from pathlib import Path
import sys
import unittest
sys.dont_write_bytecode = True
from verify_packet import cases, load

PACKET = Path(__file__).resolve().parents[1]


class ReportControls(unittest.TestCase):
    def setUp(self):
        self.good = load(PACKET / 'archives/focused-green-report.json.gz')

    def reject(self, mutate):
        report = copy.deepcopy(self.good)
        mutate(report)
        with self.assertRaises((ValueError, TypeError, KeyError)):
            cases(report)

    def first(self, report):
        def walk(s):
            if s['specs']:
                return s['specs'][0]
            for child in s.get('suites', []):
                found = walk(child)
                if found:
                    return found
        for suite in report['suites']:
            found = walk(suite)
            if found:
                return found

    def test_actual_positive_and_red_reports(self):
        for name, count, failures in [('focused-green', 6, 0), ('baseline-original-100', 100, 0), ('pending-original-red', 3, 3)]:
            with self.subTest(name=name):
                found, stats = cases(load(PACKET / ('archives/' + name + '-report.json.gz')))
                self.assertEqual(len(found), count)
                self.assertEqual(stats['unexpected'], failures)

    def test_invalid_result_durations(self):
        for value in [True, -1, float('nan'), float('inf'), None, '0']:
            with self.subTest(value=value):
                self.reject(lambda r: self.first(r)['tests'][0]['results'][0].update(duration=value))

    def test_invalid_report_durations(self):
        for value in [True, -1, float('nan'), float('inf'), None, '0']:
            with self.subTest(value=value):
                self.reject(lambda r: r['stats'].update(duration=value))

    def test_counter_schema_and_contradiction(self):
        for value in [True, -1, 5, None, '6']:
            with self.subTest(value=value):
                self.reject(lambda r: r['stats'].update(expected=value))

    def test_retry_and_project(self):
        self.reject(lambda r: self.first(r)['tests'][0]['results'][0].update(retry=1))
        self.reject(lambda r: self.first(r)['tests'][0].update(projectName='firefox'))

    def test_hidden_error_and_missing_result(self):
        self.reject(lambda r: self.first(r)['tests'][0]['results'][0].update(error={'message': 'failed'}))
        self.reject(lambda r: self.first(r)['tests'][0].update(results=[]))

    def test_empty_inventory_and_top_level_errors(self):
        self.reject(lambda r: r.update(suites=[]))
        self.reject(lambda r: r.update(errors=[{'message': 'setup failure'}]))

    def test_failure_requires_a_real_diagnostic(self):
        report = load(PACKET / 'archives/pending-original-red-report.json.gz')
        item = self.first(report)['tests'][0]['results'][0]
        item.pop('error', None)
        item['errors'] = []
        with self.assertRaises(ValueError):
            cases(report)


if __name__ == '__main__':
    unittest.main()

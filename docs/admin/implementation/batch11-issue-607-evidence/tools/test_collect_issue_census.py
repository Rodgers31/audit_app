"""Offline pagination/refusal controls; these do not replace the fresh API census."""
import copy
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from collect_issue_census import PAGE_SIZE, external_output, rest_pages, search_pages


def row(number, pr=False):
    value = {'number': number, 'id': number, 'title': 'owned fixture', 'body': '',
             'state': 'open' if number % 2 else 'closed', 'comments': 0}
    if pr:
        value['pull_request'] = {'url': 'https://api.github.com/repos/owned/fixture/pulls/' + str(number)}
    return value


class CensusControls(unittest.TestCase):
    def test_retained_collector_stops_after_first_search_page(self):
        """Reproduce the historical producer gap using its unchanged bytes."""
        old = Path(__file__).resolve().parents[1] / 'archive-generators/collect-county-initial-dedupe.py'
        with tempfile.TemporaryDirectory(prefix='census-old-') as scratch:
            script = Path(scratch) / old.name
            shutil.copyfile(old, script)
            commands = []
            def answer(command, **kwargs):
                commands.append(command)
                if command[1] == 'api':
                    return json.dumps({'total_count': 134, 'incomplete_results': False,
                                       'items': [row(n) for n in range(1, 101)]}).encode()
                return json.dumps(row(int(command[3]))).encode()
            with patch.object(subprocess, 'check_output', answer):
                runpy.run_path(str(script), run_name='__main__')
            found = json.loads((Path(scratch) / 'budget-refresh-search.json').read_text())
            self.assertEqual((found['total_count'], len(found['items'])), (134, 100))
            self.assertFalse(any('page=2' in command for command in commands))

    def test_rest_census_collects_second_page_and_excludes_pr_rows(self):
        requested = []
        def answer(endpoint, fields):
            requested.append(int(fields['page']))
            return ([row(n, pr=n % 3 == 0) for n in range(1, 101)] if fields['page'] == '1'
                    else [row(n, pr=n % 3 == 0) for n in range(101, 135)])
        found, pages = rest_pages(answer, 'owned', nonempty=True)
        self.assertEqual(requested, [1, 2])
        self.assertEqual(pages, [100, 34])
        self.assertEqual(len([r for r in found if 'pull_request' not in r]), 90)

    def test_exact_full_rest_page_requires_empty_terminal_page(self):
        requested = []
        def answer(endpoint, fields):
            requested.append(int(fields['page']))
            return [row(n) for n in range(1, 101)] if fields['page'] == '1' else []
        found, pages = rest_pages(answer, 'owned', nonempty=True)
        self.assertEqual((len(found), pages, requested), (100, [100, 0], [1, 2]))

    def test_complete_search_collects_second_page(self):
        def answer(endpoint, fields):
            numbers = range(1, 101) if fields['page'] == '1' else range(101, 135)
            return {'total_count': 134, 'incomplete_results': False, 'items': [row(n, True) for n in numbers]}
        found, pages, total = search_pages(answer, 'is:pr counties')
        self.assertEqual((len(found), pages, total), (134, [100, 34], 134))

    def test_empty_issue_census_refuses_but_zero_match_search_is_explicit(self):
        with self.assertRaisesRegex(ValueError, 'Empty issue census'):
            rest_pages(lambda *args: [], 'owned', nonempty=True)
        self.assertEqual(search_pages(lambda *args: {'total_count': 0, 'incomplete_results': False, 'items': []}, 'owned'), ([], [0], 0))

    def test_rest_duplicate_pages_refuse(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate REST'):
            rest_pages(lambda *args: [row(n) for n in range(1, 101)], 'owned', nonempty=True)

    def test_malformed_rest_pages_and_primitive_ids_refuse(self):
        for value in [None, {}, [True], [dict(row(1), number=True)], [dict(row(1), comments=True)],
                      [dict(row(1), state='unknown')]]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                rest_pages(lambda *args: value, 'owned', nonempty=True)

    def test_incomplete_truncated_and_wrong_type_search_refuse(self):
        good = {'total_count': 1, 'incomplete_results': False, 'items': [row(1, True)]}
        for change in [{'total_count': True}, {'total_count': 1001}, {'incomplete_results': True},
                       {'items': []}, {'items': {}}, {'items': [row(1)]}]:
            value = {**good, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                search_pages(lambda *args: value, 'is:pr counties')

    def test_search_changed_total_and_duplicate_second_page_refuse(self):
        for mode in ['changed-total', 'duplicate']:
            def answer(endpoint, fields):
                if fields['page'] == '1':
                    return {'total_count': 134, 'incomplete_results': False, 'items': [row(n, True) for n in range(1, 101)]}
                return {'total_count': 135 if mode == 'changed-total' else 134,
                        'incomplete_results': False, 'items': [row(n, True) for n in range(1, 35)]}
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                search_pages(answer, 'is:pr counties')

    def test_output_symlink_ancestor_and_internal_outputs_refuse(self):
        with tempfile.TemporaryDirectory(prefix='census-boundary-') as scratch:
            home = Path(scratch).resolve()
            checkout = home / 'checkout'
            checkout.mkdir()
            link = home / 'linked'
            link.symlink_to(checkout, target_is_directory=True)
            for output in [checkout / 'internal', link / 'indirect']:
                with self.subTest(output=output), self.assertRaises(ValueError):
                    external_output(output, checkout)
            self.assertEqual(external_output(home / 'external', checkout), home / 'external')


if __name__ == '__main__':
    unittest.main()

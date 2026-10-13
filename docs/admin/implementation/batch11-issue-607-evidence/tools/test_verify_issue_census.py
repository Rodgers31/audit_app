"""Actual published census validation, including recatalogued omissions."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from verify_issue_census import verify

ROOT = Path(__file__).resolve().parents[5]
PUBLISHED = Path(__file__).resolve().parents[1] / 'census-2026-10-10'


class PublishedCensusControls(unittest.TestCase):
    def test_actual_published_packet(self):
        result = verify(PUBLISHED / 'census-v1.zip', PUBLISHED / 'MANIFEST.json', ROOT)
        self.assertEqual((result['issues'], result['pr_rows_excluded'], result['requests']), (312, 314, 1102))
        self.assertFalse(result['behavioral_acceptance'])

    def mutated(self, mutate, mutate_declaration=None):
        with tempfile.TemporaryDirectory(prefix='census-verify-') as scratch:
            home = Path(scratch).resolve()
            with zipfile.ZipFile(PUBLISHED / 'census-v1.zip') as archive:
                members = {n: archive.read(n) for n in archive.namelist()}
            index = json.loads(members['INDEX.json'])
            mutate(index, members)
            members['INDEX.json'] = json.dumps(index).encode()
            declaration = json.loads((PUBLISHED / 'MANIFEST.json').read_text())
            target = home / 'altered.zip'
            with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in members.items():
                    archive.writestr(name, data)
            declaration['members'] = {n: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                                      for n, data in members.items()}
            declaration['archive_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
            if mutate_declaration is not None:
                mutate_declaration(declaration)
            manifest = home / 'MANIFEST.json'
            manifest.write_text(json.dumps(declaration))
            with self.assertRaises(ValueError):
                verify(target, manifest, ROOT)

    def test_recatalogued_missing_second_search_page_refuses(self):
        def missing(index, members):
            request = next(r for r in index['requests'] if r['endpoint'] == 'search/issues'
                           and r['fields'].get('page') == '2')
            index['requests'].remove(request)
            del members[request['path']]
        self.mutated(missing)

    def test_self_consistent_summary_cannot_replace_raw_issue_census(self):
        def changed(index, members):
            index['issue_numbers'].pop()
            index['non_pr_issues'] -= 1
            index['pr_rows_excluded'] += 1
            index['issue_states']['open'] -= 1
        self.mutated(changed)

    def test_empty_all_state_inventory_refuses(self):
        self.mutated(lambda index, members: index.update(issue_numbers=[], non_pr_issues=0))

    def test_recatalogued_missing_required_search_refuses(self):
        self.mutated(lambda index, members: index['searches'].pop('county-prs'))

    def test_recatalogued_all_searches_omitted_refuses(self):
        self.mutated(lambda index, members: index.update(searches={}))

    def test_recatalogued_changed_required_query_refuses(self):
        self.mutated(lambda index, members: index['searches']['county-prs'].update(
            query='repo:Rodgers31/audit_app is:pr'))

    def test_recatalogued_wrong_repository_refuses(self):
        self.mutated(lambda index, members: index.update(repository='other/repository'))

    def test_recatalogued_all_full_details_omitted_refuses(self):
        def empty(index, members):
            members['details.json.gz'] = gzip.compress(json.dumps({'issues': {}, 'prs': {}}).encode(), mtime=0)
            index['details_sha256'] = hashlib.sha256(members['details.json.gz']).hexdigest()
            index['full_issue_bodies_and_comments'] = []
            index['full_pr_bodies_issue_comments_reviews_and_inline_comments'] = []
        self.mutated(empty)

    def test_recatalogued_selected_issue_omitted_refuses(self):
        def missing(index, members):
            details = json.loads(gzip.decompress(members['details.json.gz']))
            del details['issues']['607']
            index['full_issue_bodies_and_comments'].remove('607')
            members['details.json.gz'] = gzip.compress(json.dumps(details).encode(), mtime=0)
            index['details_sha256'] = hashlib.sha256(members['details.json.gz']).hexdigest()
        self.mutated(missing)

    def test_normal_cli_does_not_write_helper_bytecode(self):
        with tempfile.TemporaryDirectory(prefix='census-readonly-cli-') as scratch:
            home = Path(scratch).resolve()
            for name in ('verify_issue_census.py', 'collect_issue_census.py'):
                shutil.copyfile(Path(__file__).with_name(name), home / name)
            environment = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'LANG': 'C.UTF-8'}
            command = [sys.executable, str(home / 'verify_issue_census.py'),
                       '--archive', str(PUBLISHED / 'census-v1.zip'),
                       '--manifest', str(PUBLISHED / 'MANIFEST.json'), '--checkout', str(ROOT)]
            result = subprocess.run(command, env=environment, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertFalse((home / '__pycache__').exists())

    def test_recatalogued_source_identity_disagrees_with_manifest_refuses(self):
        self.mutated(lambda index, members: index.update(head='0' * 40, tree='0' * 40))

    def test_recatalogued_nonexistent_captured_git_objects_refuse(self):
        self.mutated(lambda index, members: index.update(head='0' * 40, tree='0' * 40),
                     lambda declaration: declaration.update(captured_head='0' * 40, captured_tree='0' * 40))

    def test_recatalogued_empty_source_inventory_refuses(self):
        self.mutated(lambda index, members: index.update(source_hashes={}))

    def test_recatalogued_malformed_source_member_refuses(self):
        self.mutated(lambda index, members: index.update(source_hashes={'../outside.py': '0' * 64}))

    def test_recatalogued_external_generator_with_matching_hash_refuses(self):
        with tempfile.TemporaryDirectory(prefix='census-external-producer-') as scratch:
            producer = Path(scratch).resolve() / 'toy.py'
            producer.write_text('print("inert external producer")\n')
            digest = hashlib.sha256(producer.read_bytes()).hexdigest()
            self.mutated(lambda index, members: index.update(generator=str(producer), generator_sha256=digest),
                         lambda declaration: declaration.update(generator=str(producer), generator_sha256=digest))

    def test_checkout_symlink_refuses_before_source_read(self):
        with tempfile.TemporaryDirectory(prefix='census-source-alias-') as scratch:
            alias = Path(scratch).resolve() / 'checkout'
            alias.symlink_to(ROOT, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'Real checkout required'):
                verify(PUBLISHED / 'census-v1.zip', PUBLISHED / 'MANIFEST.json', alias)


if __name__ == '__main__':
    unittest.main()

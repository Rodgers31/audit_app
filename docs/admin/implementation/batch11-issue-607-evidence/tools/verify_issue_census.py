"""Verify the published read-only census without rerunning GitHub or browser tests."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True
from collect_issue_census import PAGE_SIZE, QUERIES, REPOSITORY, rest_pages, search_pages


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(archive, manifest, checkout):
    archive, manifest, checkout = Path(archive), Path(manifest), Path(checkout)
    require(not any(p.is_symlink() for p in [archive, manifest, *archive.parents, *manifest.parents]),
            'Symlinked census packet refused')
    require(checkout.is_absolute() and '..' not in checkout.parts
            and not any(p.is_symlink() for p in [checkout, *checkout.parents]),
            'Real checkout required')
    checkout = checkout.resolve()
    declaration = json.loads(manifest.read_text())
    require(type(declaration) is dict and declaration.get('schema') == 'batch11-607-census-publication-v1',
            'Invalid census publication schema')
    require(digest(archive.read_bytes()) == declaration.get('archive_sha256'), 'Census archive changed')
    with zipfile.ZipFile(archive) as packet:
        names = packet.namelist()
        require(names and len(names) == len(set(names)) and set(names) == set(declaration['members']),
                'Missing/duplicate/unpublished census member')
        for name in names:
            require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Unsafe census member')
            data = packet.read(name)
            require(digest(data) == declaration['members'][name]['sha256']
                    and len(data) == declaration['members'][name]['bytes'], 'Census member changed')
        index = json.loads(packet.read('INDEX.json'))
        require(index.get('schema') == 'batch11-607-census-v1' and index.get('source_stable') is True,
                'Invalid census execution metadata')
        producer = 'docs/admin/implementation/batch11-issue-607-evidence/tools/collect_issue_census.py'
        require(index.get('generator') == declaration.get('generator') == producer,
                'Known relative census producer required')
        require(index.get('generator_sha256') == declaration.get('generator_sha256')
                and type(index.get('generator_sha256')) is str
                and re.fullmatch('[a-f0-9]{64}', index['generator_sha256']),
                'Census generator identity differs')
        require(index.get('head') == declaration.get('captured_head')
                and index.get('tree') == declaration.get('captured_tree')
                and declaration.get('source_stable') is True
                and all(type(index.get(k)) is str and re.fullmatch('[a-f0-9]{40}', index[k])
                        for k in ('head', 'tree')), 'Census source identity differs')
        source = index.get('source_hashes')
        require(type(source) is dict and source, 'Nonempty measured source inventory required')
        for name, value in source.items():
            require(type(name) is str and name and '\\' not in name and not name.startswith('/')
                    and all(part and part not in ('.', '..') for part in name.split('/'))
                    and type(value) is str and re.fullmatch('[a-f0-9]{64}', value),
                    'Malformed measured source member')
        git = subprocess.run(['/usr/bin/git', 'rev-parse', index['head'] + '^{commit}',
                              index['head'] + '^{tree}'], cwd=checkout,
                             env={'PATH': '/usr/bin:/bin', 'HOME': '/dev/null'},
                             capture_output=True, text=True, timeout=30)
        require(git.returncode == 0 and git.stdout.splitlines() == [index['head'], index['tree']],
                'Captured Git commit/tree unavailable or unrelated')
        require(index.get('scope') == 'read-only issue/PR census; no behavioral, hosted, or production acceptance',
                'Census scope changed')
        require(index.get('repository') == REPOSITORY and index.get('page_size') == PAGE_SIZE,
                'Wrong census repository/page size')
        require(type(index.get('searches')) is dict and set(index['searches']) == set(QUERIES),
                'Missing/extra required census search')
        require(all(index['searches'][name]['query'] == 'repo:' + REPOSITORY + ' ' + query
                    for name, query in QUERIES.items()), 'Required census query changed')
        require(type(index.get('all_state_pages')) is list and index['all_state_pages']
                and all(type(n) is int and 0 <= n <= 100 for n in index['all_state_pages'])
                and all(n == 100 for n in index['all_state_pages'][:-1])
                and index['all_state_pages'][-1] < 100, 'Incomplete all-state REST pagination')
        require(type(index.get('non_pr_issues')) is int and index['non_pr_issues'] > 0
                and len(index['issue_numbers']) == len(set(index['issue_numbers'])) == index['non_pr_issues']
                and sum(index['all_state_pages']) == index['all_records']
                and index['non_pr_issues'] + index['pr_rows_excluded'] == index['all_records'],
                'Invalid issue/PR census counts')
        require(sum(index['issue_states'].values()) == index['non_pr_issues'], 'Issue states differ')
        for search in index['searches'].values():
            require(type(search['total_count']) is int and len(search['numbers']) ==
                    len(set(search['numbers'])) == sum(search['pages']) == search['total_count'],
                    'Incomplete search pagination')
        responses = {}
        require({r['path'] for r in index['requests']} == {n for n in names if n.startswith('raw/')},
                'Unbound raw census response')
        for request in index['requests']:
            data = packet.read(request['path'])
            require(type(request['exit']) is int and request['exit'] == 0
                    and digest(data) == request['compressed_sha256']
                    and digest(gzip.decompress(data)) == request['raw_sha256'], 'Raw API response differs')
            key = (request['endpoint'], tuple(sorted(request['fields'].items())))
            require(key not in responses, 'Duplicate API request identity')
            responses[key] = json.loads(gzip.decompress(data))

        def replay(endpoint, fields=None):
            key = (endpoint, tuple(sorted((fields or {}).items())))
            require(key in responses, 'Missing required paginated response')
            return responses[key]

        census, pages = rest_pages(replay, 'repos/' + REPOSITORY +
                                  '/issues?state=all&sort=created&direction=asc', nonempty=True)
        issues = [r for r in census if 'pull_request' not in r]
        require(pages == index['all_state_pages']
                and [r['number'] for r in issues] == index['issue_numbers']
                and {s: sum(r['state'] == s for r in issues) for s in ('open', 'closed')} == index['issue_states'],
                'Raw all-state issue census differs')
        for search in index['searches'].values():
            prefix = 'repo:' + REPOSITORY + ' '
            require(search['query'].startswith(prefix), 'Wrong search repository')
            found, pages, total = search_pages(replay, search['query'][len(prefix):])
            require(pages == search['pages'] and total == search['total_count']
                    and [r['number'] for r in found] == search['numbers'], 'Raw search census differs')
        details_bytes = packet.read('details.json.gz')
        require(digest(details_bytes) == index['details_sha256'], 'Full details changed')
        details = json.loads(gzip.decompress(details_bytes))
        require(type(details) is dict and set(details) == {'issues', 'prs'}, 'Invalid full details kinds')
        expected_issues = {str(n) for name, search in index['searches'].items() if 'issues' in name
                           for n in search['numbers']} | {'601', '607', '622', '623'}
        expected_prs = {str(n) for name, search in index['searches'].items() if 'prs' in name
                       for n in search['numbers']} | {'624'}
        require(set(details['issues']) == expected_issues and set(details['prs']) == expected_prs,
                'Missing/extra selected full body/comment details')
        require(sorted(details['issues'], key=int) == index['full_issue_bodies_and_comments']
                and sorted(details['prs'], key=int) == index['full_pr_bodies_issue_comments_reviews_and_inline_comments'],
                'Full body/comment inventory differs')
        for kind, rows in details.items():
            for number, row in rows.items():
                require(str(row['body']['number']) == number and len(row['comments']) == row['body']['comments'],
                        'Full issue body/comment count differs')
                base = 'repos/' + REPOSITORY
                comments, pages = rest_pages(replay, base + '/issues/' + number + '/comments', field='id')
                require(row['body'] == replay(base + '/issues/' + number)
                        and comments == row['comments'] and pages == row['comment_pages'],
                        'Full issue details differ from raw responses')
                if kind == 'prs':
                    require('pull_request' in row['body'] and str(row['pr']['number']) == number
                            and len(row['inline_comments']) == row['pr']['review_comments'], 'Full PR details differ')
                    reviews, pages = rest_pages(replay, base + '/pulls/' + number + '/reviews', field='id')
                    inline, inline_pages = rest_pages(replay, base + '/pulls/' + number + '/comments', field='id')
                    require(row['pr'] == replay(base + '/pulls/' + number)
                            and reviews == row['reviews'] and pages == row['review_pages']
                            and inline == row['inline_comments'] and inline_pages == row['inline_pages'],
                            'Full PR details differ from raw responses')
        generator = checkout / producer
        require(not any(p.is_symlink() for p in [generator, *generator.parents]) and generator.is_file(),
                'Real retained producer required')
        require(digest(generator.read_bytes()) == index['generator_sha256'],
                'Retained producer bytes differ')
    result = {'classification': 'published_read_only_census_integrity',
              'captured_head': index['head'], 'captured_tree': index['tree'],
              'captured_at': index['ended_at'], 'issues': index['non_pr_issues'],
              'pr_rows_excluded': index['pr_rows_excluded'], 'requests': len(index['requests']),
              'full_issue_details': len(details['issues']), 'full_pr_details': len(details['prs']),
              'behavioral_acceptance': False, 'hosted_acceptance': False, 'production_acceptance': False}
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--checkout', type=Path, required=True)
    args = parser.parse_args()
    verify(args.archive, args.manifest, args.checkout)

"""Read-only, complete issue/PR review census with portable raw response receipts.

This producer supplements the preserved author history. It makes no issue,
comment, review, workflow, or repository mutation. It cannot certify browser
acceptance or establish a failure's cause.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

REPOSITORY = 'Rodgers31/audit_app'
PAGE_SIZE = 100
QUERIES = {
    'county-exact': '"has exactly one h1"',
    'county-legacy-exact': '"normal 47-county list"',
    'county-issues': 'is:issue counties in:title,body,comments',
    'county-prs': 'is:pr counties in:title,body,comments',
    'budget-issues': 'is:issue budget in:title,body,comments',
    'budget-prs': 'is:pr budget in:title,body,comments',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(row, field='number'):
    require(type(row) is dict and type(row.get(field)) is int and row[field] > 0,
            'Malformed record identity')
    return row[field]


def issue(row):
    identity(row)
    require(type(row.get('title')) is str and row['title']
            and (row.get('body') is None or type(row['body']) is str)
            and row.get('state') in ('open', 'closed')
            and type(row.get('comments')) is int and row['comments'] >= 0,
            'Malformed issue/PR record')
    return row


def rest_pages(request, endpoint, *, field='number', nonempty=False):
    """Fetch through a short terminal page; never treat one full page as complete."""
    pages, records, seen = [], [], set()
    for page in range(1, 201):
        rows = request(endpoint, {'per_page': str(PAGE_SIZE), 'page': str(page)})
        require(type(rows) is list and len(rows) <= PAGE_SIZE, 'Malformed REST page')
        for row in rows:
            key = identity(row, field)
            require(key not in seen, 'Duplicate REST pagination identity')
            seen.add(key)
            if field == 'number':
                issue(row)
            records.append(row)
        pages.append(len(rows))
        if len(rows) < PAGE_SIZE:
            require(not nonempty or records, 'Empty issue census cannot establish completeness')
            return records, pages
    raise ValueError('REST census exceeded bounded page limit')


def search_pages(request, query):
    records, pages, seen, expected = [], [], set(), None
    for page in range(1, 11):
        response = request('search/issues', {'q': 'repo:' + REPOSITORY + ' ' + query,
                                            'per_page': str(PAGE_SIZE), 'page': str(page)})
        require(type(response) is dict and type(response.get('total_count')) is int
                and 0 <= response['total_count'] <= 1000
                and response.get('incomplete_results') is False
                and type(response.get('items')) is list, 'Incomplete/malformed search result')
        if expected is None:
            expected = response['total_count']
        require(response['total_count'] == expected, 'Search census changed during pagination')
        rows = response['items']
        require(len(rows) <= PAGE_SIZE, 'Oversized search page')
        for row in rows:
            issue(row)
            key = identity(row)
            require(key not in seen, 'Duplicate search pagination identity')
            require('is:pr' not in query or 'pull_request' in row, 'PR query returned issue row')
            require('is:issue' not in query or 'pull_request' not in row, 'Issue query returned PR row')
            records.append(row)
            seen.add(key)
        pages.append(len(rows))
        require(len(records) <= expected, 'Search result exceeds declared total')
        if len(records) == expected:
            return records, pages, expected
        require(len(rows) == PAGE_SIZE, 'Search ended before declared total')
    raise ValueError('Search pagination incomplete')


def external_output(output, checkout):
    output, checkout = Path(output).absolute(), Path(checkout).resolve()
    require('..' not in output.parts and not any(p.is_symlink() for p in [output, *output.parents]),
            'Symlink/traversal output refused')
    require(output.parent.is_dir() and not output.exists() and not output.is_relative_to(checkout),
            'Fresh external output required')
    return output


def collect(checkout, output):
    checkout = Path(checkout).resolve()
    output = external_output(output, checkout)
    output.mkdir()
    raw = output / 'raw'
    raw.mkdir()
    generator = Path(__file__).resolve()
    started = datetime.now(timezone.utc).isoformat()
    head, tree = subprocess.check_output(['git', 'rev-parse', 'HEAD', 'HEAD^{tree}'],
                                         cwd=checkout, text=True, timeout=30).splitlines()
    selected = [p for p in subprocess.check_output(['git', 'ls-files', '-z'], cwd=checkout,
                                                   timeout=30).decode().split('\0') if p]
    before = {p: digest((checkout / p).read_bytes()) for p in selected}
    requests = []
    environment = {'PATH': os.environ['PATH'], 'HOME': str(Path.home()),
                   'GH_PROMPT_DISABLED': '1', 'GH_PAGER': 'cat'}

    def request(endpoint, fields=None):
        fields = fields or {}
        command = ['gh', 'api', endpoint, '--method', 'GET']
        for key, value in sorted(fields.items()):
            command += ['-f', key + '=' + value]
        request_id = digest(json.dumps([endpoint, fields], sort_keys=True).encode())
        path = raw / (request_id + '.json.gz')
        require(not path.exists(), 'Duplicate API request identity')
        when = datetime.now(timezone.utc).isoformat()
        result = subprocess.run(command, env=environment, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=45, check=False)
        require(result.returncode == 0, 'Read-only GitHub request failed: ' + endpoint)
        value = json.loads(result.stdout)
        path.write_bytes(gzip.compress(result.stdout, mtime=0))
        requests.append({'endpoint': endpoint, 'fields': fields, 'command': command,
                         'requested_at': when, 'exit': result.returncode,
                         'path': path.relative_to(output).as_posix(),
                         'raw_sha256': digest(result.stdout), 'compressed_sha256': digest(path.read_bytes())})
        return value

    rows, sizes = rest_pages(request, 'repos/' + REPOSITORY + '/issues?state=all&sort=created&direction=asc', nonempty=True)
    issues = [r for r in rows if 'pull_request' not in r]
    prs_in_census = [r for r in rows if 'pull_request' in r]
    searches = {}
    for name, query in QUERIES.items():
        found, pages, total = search_pages(request, query)
        searches[name] = {'query': 'repo:' + REPOSITORY + ' ' + query,
                          'pages': pages, 'total_count': total,
                          'numbers': [identity(r) for r in found]}
    issue_numbers = {n for name, value in searches.items() if 'issues' in name
                     for n in value['numbers']}
    issue_numbers.update((601, 607, 622, 623))
    pr_numbers = {n for name, value in searches.items() if 'prs' in name for n in value['numbers']}
    pr_numbers.add(624)
    full = {'issues': {}, 'prs': {}}

    def details(kind, number):
        base = 'repos/' + REPOSITORY
        body = request(base + '/issues/' + str(number))
        issue(body)
        comments, comment_pages = rest_pages(request, base + '/issues/' + str(number) + '/comments', field='id')
        require(len(comments) == body['comments'], 'Issue comment count changed/incomplete')
        data = {'body': body, 'comments': comments, 'comment_pages': comment_pages}
        if kind == 'prs':
            require('pull_request' in body, 'Requested PR is an issue')
            pr = request(base + '/pulls/' + str(number))
            require(identity(pr) == number and type(pr.get('body')) in (str, type(None)), 'Malformed PR body')
            reviews, review_pages = rest_pages(request, base + '/pulls/' + str(number) + '/reviews', field='id')
            inline, inline_pages = rest_pages(request, base + '/pulls/' + str(number) + '/comments', field='id')
            require(len(inline) == pr['review_comments'], 'PR inline comment count changed/incomplete')
            data.update(pr=pr, reviews=reviews, review_pages=review_pages,
                        inline_comments=inline, inline_pages=inline_pages)
        else:
            require('pull_request' not in body, 'Requested issue is a PR')
        return kind, str(number), data

    with ThreadPoolExecutor(max_workers=4) as executor:
        for kind, number, data in executor.map(lambda item: details(*item),
                                               [('issues', n) for n in sorted(issue_numbers)] +
                                               [('prs', n) for n in sorted(pr_numbers)]):
            full[kind][number] = data
    after = {p: digest((checkout / p).read_bytes()) for p in selected}
    require(before == after, 'Checkout source changed during issue census')
    for r in requests:
        compressed = (output / r['path']).read_bytes()
        require(digest(compressed) == r['compressed_sha256']
                and digest(gzip.decompress(compressed)) == r['raw_sha256'], 'Raw response readback mismatch')
    index = {'schema': 'batch11-607-census-v1', 'repository': REPOSITORY,
             'scope': 'read-only issue/PR census; no behavioral, hosted, or production acceptance',
             'started_at': started, 'ended_at': datetime.now(timezone.utc).isoformat(),
             'generator': generator.relative_to(checkout).as_posix(), 'generator_sha256': digest(generator.read_bytes()),
             'head': head, 'tree': tree, 'source_hashes': before, 'source_stable': before == after,
             'page_size': PAGE_SIZE, 'all_state_pages': sizes, 'all_records': len(rows),
             'non_pr_issues': len(issues), 'pr_rows_excluded': len(prs_in_census),
             'issue_states': {s: sum(r['state'] == s for r in issues) for s in ('open', 'closed')},
             'issue_numbers': [identity(r) for r in issues], 'searches': searches,
             'full_issue_bodies_and_comments': sorted(full['issues'], key=int),
             'full_pr_bodies_issue_comments_reviews_and_inline_comments': sorted(full['prs'], key=int),
             'requests': sorted(requests, key=lambda r: r['path'])}
    (output / 'details.json.gz').write_bytes(gzip.compress(json.dumps(full, indent=2).encode(), mtime=0))
    index['details_sha256'] = digest((output / 'details.json.gz').read_bytes())
    (output / 'INDEX.json').write_text(json.dumps(index, indent=2) + '\n')
    require(json.loads((output / 'INDEX.json').read_text()) == index, 'Census index readback mismatch')
    print(json.dumps({k: index[k] for k in ('all_records', 'non_pr_issues', 'pr_rows_excluded', 'issue_states', 'source_stable')}))
    return index


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    collect(args.checkout, args.output)

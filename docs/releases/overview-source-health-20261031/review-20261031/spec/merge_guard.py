"""Fresh complete classified review census, with an explicit override opt-in."""
import argparse
import datetime
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def material(value):
    return {key: value[key] for key in ('reviews', 'inline', 'comments')}


def validate(value, pr, head, accepted):
    if (pr not in (863,) or value['number'] != pr or value['headRefOid'] != head
            or value['baseRefName'] != 'main' or value['state'] != 'OPEN'
            or value['isDraft'] is not False or value['closingIssuesReferences']):
        raise RuntimeError('PR identity/state/closing references changed')
    if value['reviewRequests'] or value['requests']['users'] or value['requests']['teams']:
        raise RuntimeError('Pending review request')
    query = value['graphql']; threads = query['reviewThreads']
    collections = [query['reviews'], query['comments'], threads]
    collections += [thread['comments'] for thread in threads['nodes']]
    if any(type(c['totalCount']) is not int or c['totalCount'] < 0 for c in collections):
        raise RuntimeError('Invalid review census count')
    if (len(value['reviews']) != query['reviews']['totalCount']
            or len(value['comments']) != query['comments']['totalCount']
            or threads['pageInfo']['hasNextPage'] is not False
            or len(threads['nodes']) != threads['totalCount']
            or sum(t['comments']['totalCount'] for t in threads['nodes']) != len(value['inline'])):
        raise RuntimeError('Incomplete review census')
    for thread in threads['nodes']:
        if (thread['isResolved'] is not True or thread['comments']['pageInfo']['hasNextPage'] is not False
                or len(thread['comments']['nodes']) != thread['comments']['totalCount']):
            raise RuntimeError('Unresolved/incomplete review thread')
    if value['reviewDecision'] == 'CHANGES_REQUESTED':
        raise RuntimeError('Aggregate changes requested')
    latest = {}
    for review in value['reviews']:
        if review['state'] == 'PENDING':
            raise RuntimeError('Pending review')
        if review['state'] not in ('APPROVED', 'COMMENTED', 'CHANGES_REQUESTED', 'DISMISSED'):
            raise RuntimeError('Unknown review state')
        latest[review['user']['login']] = review['state']
    if 'CHANGES_REQUESTED' in latest.values():
        raise RuntimeError('Reviewer requests changes')
    if material(value) != accepted:
        raise RuntimeError('New or changed unclassified review material')
    for check in value['statusCheckRollup']:
        if check.get('__typename') == 'CheckRun':
            good = check.get('status') == 'COMPLETED' and check.get('conclusion') in ('SUCCESS', 'NEUTRAL', 'SKIPPED')
        elif check.get('__typename') == 'StatusContext':
            good = check.get('state') == 'SUCCESS'
        else:
            good = False
        if not good:
            raise RuntimeError('A reported check is pending, failed or unknown')


def coordinate(pr, head, accepted, census, run, *, allow_override=False):
    validate(census(), pr, head, accepted)
    normal = run(['gh', 'pr', 'merge', str(pr), '--merge', '--match-head-commit', head])
    if normal.returncode == 0:
        return 'normal'
    reason = (normal.stdout + normal.stderr).lower()
    if 'base branch policy prohibits' not in reason and 'protected branch' not in reason:
        raise RuntimeError('Unexpected normal merge rejection')
    if allow_override is not True:
        return 'maintainer_override_required'
    validate(census(), pr, head, accepted)
    override = run(['gh', 'pr', 'merge', str(pr), '--merge', '--match-head-commit', head, '--admin'])
    if override.returncode:
        raise RuntimeError('Authorized override failed')
    return 'authorized_override'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pr', type=int, choices=(863,))
    parser.add_argument('--allow-admin', action='store_true', help='Only after separate explicit owner override authorization')
    args = parser.parse_args()
    identity = json.loads((ROOT / ('accepted-' + str(args.pr) + '.json')).read_text())
    def census():
        result = subprocess.run(['python3', str(ROOT / 'read-review-census.py'), str(args.pr)],
                                capture_output=True, text=True, check=True)
        path = Path(result.stdout.rsplit('SAVED ', 1)[1].strip())
        return json.loads(path.read_text())[0]
    def run(argv):
        result = subprocess.run(argv, capture_output=True, text=True)
        kind = 'override' if '--admin' in argv else 'normal'
        name = str(args.pr) + '-' + kind + '-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json'
        (ROOT / name).write_text(json.dumps(dict(argv=argv, exit_code=result.returncode,
            stdout=result.stdout, stderr=result.stderr), indent=2))
        return result
    print(coordinate(args.pr, identity['head'], identity['material'], census, run, allow_override=args.allow_admin))


if __name__ == '__main__':
    main()

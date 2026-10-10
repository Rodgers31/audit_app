"""Verify the published packet's integrity and its measured local acceptance.

This consumes archived execution results; it does not execute a browser or
certify hosted/production acceptance. Run replay.py for a fresh execution.
"""
import argparse
import gzip
import hashlib
import json
import math
import posixpath
import subprocess
from pathlib import Path, PurePosixPath

BASE = 'bcb5ff99854de595bbe3f7d60cc8796b7ada5a20'
NEW_TESTS = {'frontend/e2e/county-pagination-boundaries.spec.ts', 'frontend/e2e/county-pagination-contract.spec.ts'}
COHORTS = {'public', 'users', 'operations', 'overview-audit', 'etl-ui', 'coordinator'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_file(root, name):
    require(type(name) is str and bool(name), 'Empty/non-string path')
    rel = PurePosixPath(name)
    require(not rel.is_absolute() and '..' not in rel.parts and str(rel) == name, 'Unsafe path')
    target = root / name
    require(not any(p.is_symlink() for p in [root, target, *target.parents]), 'Symlinked input')
    require(target.is_file() and target.resolve().is_relative_to(root.resolve()), 'Missing/outside input')
    return target


def load(path):
    raw = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            require(key not in obj, 'Duplicate JSON key')
            obj[key] = value
        return obj
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def cases(report):
    require(type(report) is dict and type(report.get('errors')) is list and not report['errors'], 'Report errors/schema')
    require(type(report.get('suites')) is list and report['suites'], 'Empty suites')
    found = []
    def visit(suite):
        require(type(suite) is dict and type(suite.get('specs')) is list, 'Malformed suite')
        require(type(suite.get('suites', [])) is list, 'Malformed children')
        for spec in suite['specs']:
            require(type(spec) is dict, 'Malformed spec')
            require(all(type(spec.get(k)) is str and spec[k] for k in ['id', 'file', 'title']), 'Missing case identity')
            require(all(type(spec.get(k)) is int and spec[k] > 0 for k in ['line', 'column']), 'Case location')
            require(type(spec.get('tests')) is list and len(spec['tests']) == 1, 'Case project count')
            test = spec['tests'][0]
            require(type(test) is dict and test.get('projectName') == 'chromium', 'Wrong project')
            require(type(test.get('results')) is list and len(test['results']) == 1, 'Retry/missing result')
            result = test['results'][0]
            require(type(result) is dict and type(result.get('retry')) is int and result['retry'] == 0, 'Retried result')
            duration = result.get('duration')
            require(type(duration) in [int, float] and math.isfinite(duration) and duration >= 0, 'Result duration')
            status = result.get('status')
            require(status in ['passed', 'skipped', 'failed', 'timedOut'], 'Invalid/interrupted result')
            require(test.get('expectedStatus') in ['passed', 'skipped'], 'Unexpected expected-failure policy')
            require(test.get('status') == ('expected' if status == 'passed' else 'skipped' if status == 'skipped' else 'unexpected'), 'Contradictory result')
            if status in ['passed', 'skipped']:
                require('error' not in result and type(result.get('errors', [])) is list and not result.get('errors'), 'Hidden error')
                require(test['expectedStatus'] == status, 'Contradictory expectation')
            found.append((spec, status))
        for child in suite.get('suites', []):
            visit(child)
    for suite in report['suites']:
        visit(suite)
    require(found and len({spec['id'] for spec, _ in found}) == len(found), 'Empty/duplicate case identities')
    observed = {'expected': 0, 'unexpected': 0, 'skipped': 0, 'flaky': 0}
    for _, status in found:
        observed['expected' if status == 'passed' else 'skipped' if status == 'skipped' else 'unexpected'] += 1
    stats = report.get('stats')
    require(type(stats) is dict and all(type(stats.get(k)) is int and stats[k] >= 0 and stats[k] == v for k, v in observed.items()), 'Invalid/contradictory counters')
    duration = stats.get('duration')
    require(type(duration) in [int, float] and math.isfinite(duration) and duration >= 0, 'Invalid report duration')
    return found, observed


def suite_descriptor(spec, report):
    root_dir = report.get('config', {}).get('rootDir')
    require(type(root_dir) is str and root_dir.startswith('/app/frontend/e2e'), 'Wrong full-suite source root')
    full = posixpath.normpath(posixpath.join(root_dir, spec['file']))
    require(full.startswith('/app/frontend/e2e/'), 'Case outside original suite')
    descriptor = {k: spec[k] for k in ['file', 'line', 'column', 'title']}
    descriptor['file'] = full[len('/app/frontend/e2e/'):]
    return json.dumps(descriptor, separators=(',', ':'), ensure_ascii=False)


def verify(packet, checkout, manifest='packet-v1.json'):
    packet, checkout = Path(packet), Path(checkout)
    require(packet.is_dir() and checkout.is_dir(), 'Missing packet/checkout')
    data = load(relative_file(packet, manifest))
    require(type(data) is dict and type(data.get('schema')) is int and data['schema'] == 1, 'Unsupported packet schema')
    files = data.get('files')
    require(type(files) is dict and files, 'Empty file catalogue')
    actual = {p.relative_to(packet).as_posix() for p in packet.rglob('*') if p.is_file() or p.is_symlink()}
    require(actual == set(files) | {manifest}, 'Uncatalogued/missing packet files')
    for name, expected in files.items():
        require(type(expected) is str and len(expected) == 64 and all(c in '0123456789abcdef' for c in expected), 'Invalid digest')
        require(digest(relative_file(packet, name)) == expected, 'Packet hash mismatch: ' + name)
    source = load(relative_file(packet, data.get('current_source_receipt')))
    require(source.get('source_changed') == [] and source.get('helpers_changed') == [] and source.get('generator_unchanged') is True and source.get('timed_out') is False and type(source.get('child_exit')) is int and source['child_exit'] == 0, 'Source execution drift/failure')
    hashes = source.get('source_hashes')
    require(type(hashes) is dict and hashes, 'Empty source inventory')
    original_paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASE], cwd=checkout, text=True).splitlines()
    require(set(hashes) == set(original_paths) | NEW_TESTS, 'Incomplete tested source inventory')
    for name, expected in hashes.items():
        require(digest(relative_file(checkout, name)) == expected, 'Tested source mismatch: ' + name)
    runs = data.get('runs')
    require(type(runs) is list and runs, 'Empty run inventory')
    names = [r.get('name') if type(r) is dict else None for r in runs]
    require(all(type(n) is str and n for n in names) and len(set(names)) == len(names), 'Duplicate/missing run identity')
    required = {'focused-green', 'pending-original-green'} | {'full-' + c for c in COHORTS}
    require(required.issubset(names), 'Missing current acceptance run')
    inventory = load(relative_file(packet, data.get('current_inventory')))
    require(type(inventory) is dict and type(inventory.get('total')) is int and inventory['total'] == 329 and type(inventory.get('originalTotal')) is int and inventory['originalTotal'] == 323, 'Wrong original/current inventory')
    groups = inventory.get('cohorts')
    require(type(groups) is list and len(groups) == 6 and {c.get('name') for c in groups if type(c) is dict} == COHORTS, 'Incomplete cohort partition')
    all_cases = []
    for group in groups:
        require(type(group.get('cases')) is list and group['cases'] and all(type(c) is str and c for c in group['cases']), 'Malformed inventory case')
        all_cases.extend(group['cases'])
    require(len(all_cases) == 329 and len(set(all_cases)) == 329 and sorted(all_cases) == sorted(inventory.get('baseline', [])), 'Missing/duplicate partition case')
    categories = set()
    full_counts = {'expected': 0, 'unexpected': 0, 'skipped': 0, 'flaky': 0}
    for run in runs:
        require(type(run) is dict and run.get('category') in ['historical-red', 'diagnostic-positive', 'current-acceptance'], 'Run classification')
        categories.add(run['category'])
        report = load(relative_file(packet, run.get('report')))
        result, observed = cases(report)
        require(type(run.get('counts')) is dict and all(type(v) is int and v >= 0 for v in run['counts'].values()) and run['counts'] == observed, 'Declared counts mismatch')
        expected_ids = run.get('case_ids')
        require(type(expected_ids) is list and expected_ids and all(type(x) is str and x for x in expected_ids) and len(set(expected_ids)) == len(expected_ids), 'Malformed case inventory')
        require(sorted(expected_ids) == sorted(spec['id'] for spec, _ in result), 'Case substitution')
        if run['category'] == 'historical-red':
            require(observed['unexpected'] > 0, 'Red run contains no failure')
            receipt = load(relative_file(packet, run.get('receipt')))
            require(type(receipt.get('child_exit')) is int and receipt['child_exit'] > 0 and receipt.get('timed_out') is False and receipt.get('source_changed') == [] and receipt.get('helpers_changed') == [] and receipt.get('generator_unchanged') is True, 'Red is a setup/drift/timeout failure')
        if run['category'] == 'diagnostic-positive':
            require(observed['unexpected'] == 0 and observed['flaky'] == 0, 'Diagnostic positive contains failure')
            receipt = load(relative_file(packet, run.get('receipt')))
            require(type(receipt.get('child_exit')) is int and receipt['child_exit'] == 0 and receipt.get('timed_out') is False and receipt.get('source_changed') == [] and receipt.get('generator_unchanged') is True, 'Diagnostic child failed/drifted')
        if run['category'] == 'current-acceptance':
            require(observed['unexpected'] == 0 and observed['flaky'] == 0, 'Acceptance includes failures')
            receipt = load(relative_file(packet, run.get('receipt')))
            require(type(receipt.get('child_exit')) is int and receipt['child_exit'] == 0 and receipt.get('timed_out') is False and receipt.get('source_changed') == [] and receipt.get('helpers_changed') == [] and receipt.get('generator_unchanged') is True and receipt.get('source_hashes') == hashes, 'Unbound/drifted acceptance child')
        if run['name'] in required:
            require(run['category'] == 'current-acceptance', 'Required run is not acceptance')
        if run['name'] in ['focused-green', 'pending-original-green']:
            expected = 6 if run['name'] == 'focused-green' else 3
            require(observed == {'expected': expected, 'unexpected': 0, 'skipped': 0, 'flaky': 0}, 'Required focused cases omitted/skipped')
            if run['name'] == 'focused-green':
                expected_cases = [c for c in all_cases if 'frontend/e2e/' + json.loads(c)['file'] in NEW_TESTS]
                require(len(expected_cases) == 6 and sorted(suite_descriptor(s, report) for s, _ in result) == sorted(expected_cases), 'Focused case substitution')
            else:
                require(all(PurePosixPath(s['file']).name == 'smart-back.spec.ts' and s['line'] == 72 and s['column'] == 7 and s['title'] == 'scroll position is roughly preserved after smart-back' for s, _ in result), 'Original case substitution')
        if run['name'].startswith('full-'):
            cohort = run['name'][5:]
            require(cohort in COHORTS, 'Unknown full cohort')
            measured = [suite_descriptor(spec, report) for spec, _ in result]
            expected = next(c['cases'] for c in groups if c['name'] == cohort)
            require(sorted(measured) == sorted(expected), 'Full cohort case substitution')
            child = load(relative_file(packet, run.get('cohort_receipt')))
            require(type(child.get('child_exit')) is int and child['child_exit'] == 0 and type(child.get('verification_exit')) is int and child['verification_exit'] == 0, 'Cohort child failure')
            for key in full_counts:
                full_counts[key] += observed[key]
    require(full_counts == {'expected': 318, 'unexpected': 0, 'skipped': 11, 'flaky': 0}, 'Wrong full-suite accounting')
    require('current-acceptance' in categories and 'historical-red' in categories, 'Missing behavioral boundary evidence')
    return {'historical_integrity': True, 'local_recorded_acceptance': True, 'fresh_execution': False, 'hosted_acceptance': False, 'production_acceptance': False, 'source_files': len(hashes), 'runs': len(runs)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--checkout', type=Path, required=True)
    parser.add_argument('--manifest', default='packet-v1.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    require(not any(p.is_symlink() for p in [output, *output.parents]), 'Symlinked output')
    require(not output.resolve().is_relative_to(args.checkout.resolve()) and not output.resolve().is_relative_to(args.packet.resolve()), 'Output must be external')
    require(output.parent.is_dir() and not output.exists(), 'Output must be fresh')
    result = verify(args.packet, args.checkout, args.manifest)
    result['verifier_sha256'] = digest(Path(__file__))
    with output.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    require(load(output) == result, 'Output readback mismatch')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

"""Independently recheck sealed packet accounting, scope, and acceptance gates."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import posixpath
import subprocess
import sys
import time

sys.dont_write_bytecode = True
p = argparse.ArgumentParser()
p.add_argument('--checkout', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
repo, out = a.checkout.resolve(), a.output.absolute()
assert out.parent.is_dir() and not out.exists() and not out.is_relative_to(repo)
out.mkdir()
packet = repo / 'docs/admin/implementation/batch11-issue-607-evidence'
base = 'bcb5ff99854de595bbe3f7d60cc8796b7ada5a20'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
load = lambda path: json.loads(gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes())
helpers = [Path(__file__).resolve(), packet / 'tools/verify_packet.py', packet / 'tools/replay.py']
before = {str(f): sha(f) for f in helpers}
identity = subprocess.check_output(['git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], cwd=repo, text=True).splitlines()
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=repo).decode().strip('\0').split('\0')
source = {f: sha(repo / f) for f in tracked}
start = time.time()
executions = []
errors = []
details = {}
try:
    manifest = load(packet / 'packet-v1.json')
    actual_files = {f.relative_to(packet).as_posix() for f in packet.rglob('*') if f.is_file()}
    assert actual_files == set(manifest['files']) | {'packet-v1.json'}
    assert all(sha(packet / name) == digest for name, digest in manifest['files'].items())
    inventory = load(packet / manifest['current_inventory'])
    assert inventory['total'] == 329 and inventory['originalTotal'] == 323
    full = [r for r in manifest['runs'] if r['name'].startswith('full-')]
    assert len(full) == 6 and {r['name'][5:] for r in full} == {g['name'] for g in inventory['cohorts']}
    total = {'passed': 0, 'skipped': 0, 'failed': 0}
    failures = []
    consumed = {}
    all_descriptors = []
    for run in full:
        report_path = packet / run['report']
        report = load(report_path)
        assert report['errors'] == []
        specs = []
        def visit(suite):
            specs.extend(suite['specs'])
            for child in suite.get('suites', []):
                visit(child)
        for suite in report['suites']:
            visit(suite)
        assert len(specs) == len({s['id'] for s in specs})
        descriptors = []
        for spec in specs:
            descriptor = {k: spec[k] for k in ['file', 'line', 'column', 'title']}
            full_file = posixpath.normpath(posixpath.join(report['config']['rootDir'], spec['file']))
            assert full_file.startswith('/app/frontend/e2e/')
            descriptor['file'] = full_file[len('/app/frontend/e2e/'):]
            descriptors.append(json.dumps(descriptor, ensure_ascii=False, separators=(',', ':')))
        expected = next(g['cases'] for g in inventory['cohorts'] if g['name'] == run['name'][5:])
        assert sorted(descriptors) == sorted(expected)
        all_descriptors += descriptors
        counts = {'passed': 0, 'skipped': 0, 'failed': 0}
        for spec in specs:
            assert len(spec['tests']) == 1
            test = spec['tests'][0]
            assert test['projectName'] == 'chromium' and len(test['results']) == 1
            result = test['results'][0]
            assert type(result['retry']) is int and result['retry'] == 0
            counts[result['status']] += 1
            if result['status'] == 'failed':
                failures.append({'run': run['name'], 'id': spec['id'], 'file': spec['file'], 'line': spec['line'], 'title': spec['title'], 'error': result['error']})
        assert {k: report['stats'][k] for k in ['expected', 'unexpected', 'skipped', 'flaky']} == {'expected': counts['passed'], 'unexpected': counts['failed'], 'skipped': counts['skipped'], 'flaky': 0}
        for k, v in counts.items():
            total[k] += v
        consumed[run['report']] = sha(report_path)
    assert len(all_descriptors) == len(set(all_descriptors)) == 329
    assert total == {'passed': 316, 'skipped': 11, 'failed': 2}
    assert {f['file'] for f in failures} == {'accessibility.spec.ts', 'county-response-validation.spec.ts'}
    diff_cmd = ['git', 'diff', '--name-only', base + '...HEAD']
    changed = subprocess.check_output(diff_cmd, cwd=repo, text=True).splitlines()
    changed_source = [f for f in changed if not f.startswith('docs/admin/implementation/')]
    expected_changed = {'frontend/app/counties/CountiesPageClient.tsx', 'frontend/e2e/county-pagination-boundaries.spec.ts', 'frontend/e2e/county-pagination-contract.spec.ts', 'frontend/__tests__/countiesUrlStateSsr.test.tsx'}
    assert set(changed_source) == expected_changed
    original_scope = load(Path(__file__).resolve().parent / 'scope-controls.json')
    for name, info in original_scope['paths'].items():
        assert (repo / name).read_bytes() == subprocess.check_output(['git', 'show', base + ':' + name], cwd=repo)
        assert sha(repo / name) == info['sha256']
    assert sha(repo / 'frontend/__tests__/countiesUrlStateSsr.test.tsx') == sha(Path(__file__).resolve().parent / 'unit-detectors/valid.test.tsx')
    for mode in ['integrity', 'acceptance']:
        result_path = out / (mode + '.json')
        command = [sys.executable, str(packet / 'tools/verify_packet.py'), '--packet', str(packet), '--checkout', str(repo), '--output', str(result_path)]
        if mode == 'integrity':
            command.append('--integrity-only')
        child = subprocess.run(command, cwd=repo, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, text=True, capture_output=True, timeout=90)
        log = out / (mode + '.log')
        with log.open('x') as f:
            f.write(child.stdout + child.stderr)
        executions.append({'mode': mode, 'command': command, 'child_exit': child.returncode, 'log_sha256': sha(log)})
        if mode == 'integrity':
            assert child.returncode == 0
            result = load(result_path)
            assert result['local_recorded_acceptance'] is False and result['fresh_execution'] is False and result['hosted_acceptance'] is False and result['production_acceptance'] is False
            assert result['current_full_counts'] == {'expected': 316, 'unexpected': 2, 'skipped': 11, 'flaky': 0}
        else:
            assert child.returncode != 0 and not result_path.exists()
            assert 'Current full-suite acceptance blocked by unexpected failures' in child.stderr
    details = {'packet_sha256': sha(packet / 'packet-v1.json'), 'catalogued_files': len(manifest['files']), 'full_counts': total, 'full_report_hashes': consumed, 'failures': failures, 'changed_source_paths': changed_source, 'all_changed_paths': changed, 'local_recorded_acceptance': False}
except Exception as exc:
    errors.append({'type': type(exc).__name__, 'message': str(exc)})
after = {str(f): sha(f) for f in helpers}
source_changed = [f for f, digest in source.items() if not (repo / f).is_file() or sha(repo / f) != digest]
receipt = {'head': identity[0], 'tree': identity[1], 'started': start, 'ended': time.time(), 'helper_hashes_before': before, 'helper_hashes_after': after, 'source_hashes': source, 'source_changed': source_changed, 'executions': executions, 'errors': errors, 'details': details, 'reviewer_runtime': {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform()}, 'scope': 'Independent archived corpus accounting and gate execution; fresh browser acceptance is recorded separately; no hosted or production acceptance.'}
with (out / 'receipt.json').open('x') as f:
    json.dump(receipt, f, indent=2)
assert json.loads((out / 'receipt.json').read_text()) == receipt
assert not errors and before == after and not source_changed
print(json.dumps({k: v for k, v in receipt.items() if k not in ['source_hashes']}, indent=2))

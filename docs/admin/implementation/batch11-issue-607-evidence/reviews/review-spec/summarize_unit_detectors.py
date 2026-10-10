"""Reconcile preserved detector executions, including reviewer postcondition failures."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parent
repo = Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
load = lambda path: json.loads(path.read_text())
before = load(root / 'unit-detectors-v4-execution/source-before.json')
after = load(root / 'unit-detectors-v5-execution/receipt.json')
assert before['head'] == after['head'] == '6fcaed18327d4ebdb91b475c016d81ca624deda8'
assert before['tree'] == after['tree'] == '958d72062130267d0916ad14f9ab7ab6afb0af71'
assert before['source_hashes'] == after['source_hashes']
assert not after['source_changed'] and after['helper_hashes_before'] == after['helper_hashes_after']
assert all(sha(repo / name) == digest for name, digest in before['source_hashes'].items())
assert all(sha(Path(name)) == digest for name, digest in before['helpers'].items())
assert sha(repo / 'frontend/__tests__/countiesUrlStateSsr.test.tsx') == sha(root / 'unit-detectors-v4/valid.test.tsx')
observations = []
inputs = {}
for name, folder, passed, failed, skipped in [('valid', 'unit-detectors-v4-execution', 21, 0, 0), ('noop', 'unit-detectors-v4-execution', 0, 1, 20), ('same-url', 'unit-detectors-v5-execution', 0, 2, 19)]:
    report_path, log_path = root / folder / (name + '-report.json'), root / folder / (name + '.log')
    report = load(report_path)
    assert report['numRuntimeErrorTestSuites'] == 0
    assert (report['numTotalTests'], report['numPassedTests'], report['numFailedTests'], report['numPendingTests']) == (21, passed, failed, skipped)
    assertions = [a for suite in report['testResults'] for a in suite['assertionResults']]
    failures = [a for a in assertions if a['status'] == 'failed']
    assert len(assertions) == 21 and len(failures) == failed
    probes = [json.loads(value) for value in re.findall(r'SPEC_UNIT_PROBE (\{[^\n]+\})', log_path.read_text())]
    if name == 'noop':
        assert probes == [{'query': '', 'calls': [[None, '', '/counties?p=2']]}]
        assert '/noop.test.tsx:293:36' in failures[0]['failureMessages'][0]
        assert (root / 'unit-detectors-v4/noop.test.tsx').read_text().splitlines()[292].strip() == "expect(window.location.search).toBe('?p=2');"
    if name == 'same-url':
        assert len(probes) == 2 and {p['query'] for p in probes} == {'?p=1&from=navigation', '?p=2&from=navigation'}
        assert all(len(p['calls']) == 1 and p['calls'][0][:2] == [None, ''] and p['calls'][0][2].endswith('/counties' + p['query']) for p in probes)
        assert all('toHaveBeenCalled' in a['failureMessages'][0] and '/same-url-write.test.tsx:' in a['failureMessages'][0] for a in failures)
    for path in [report_path, log_path]:
        inputs[str(path)] = sha(path)
    observations.append({'variant': name, 'passed': passed, 'intentionally_failed': failed, 'unselected': skipped, 'actual_probes': probes, 'failed_assertions': failures})
launches = {name: load(root / ('unit-detectors-' + name + '-launch-receipt.json')) for name in ['v2', 'v4', 'v5']}
assert launches['v2']['child_exit'] == launches['v4']['child_exit'] == 1 and launches['v5']['child_exit'] == 0
assert all(r['producer_sha256_before'] == r['producer_sha256_after'] for r in launches.values())
for name in ['v2', 'v4']:
    inputs[str(root / ('unit-detectors-' + name + '-launch.log'))] = sha(root / ('unit-detectors-' + name + '-launch.log'))
    assert 'AssertionError' in (root / ('unit-detectors-' + name + '-launch.log')).read_text()
receipt = {'head': after['head'], 'tree': after['tree'], 'producer_sha256': sha(Path(__file__)), 'source_before_matches_after': True, 'source_changed': [], 'observations': observations, 'consumed_hashes': inputs, 'launches': launches, 'same_url_exact_child_execution': after['executions'], 'limits': ['First reviewer drivers aborted after valid and intended no-op execution because formatter output and JSON diagnostic schema differed from their postcondition assumptions; raw attempts remain preserved.', 'Pinned pretty-format obscures Expected formatting; explicit live probes and preserved assertion locations establish each synthetic mismatch.', 'Selected synthetic failures/skips are detector checks, not product causal reds, quarantines, or original browser acceptance.']}
with (root / 'unit-detector-reconciled.json').open('x') as f:
    json.dump(receipt, f, indent=2)
assert load(root / 'unit-detector-reconciled.json') == receipt
print(json.dumps({'head': receipt['head'], 'source_before_matches_after': True, 'counts': [{k: o[k] for k in ['variant', 'passed', 'intentionally_failed', 'unselected']} for o in observations], 'limits': receipt['limits']}, indent=2))

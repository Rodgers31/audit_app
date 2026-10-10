"""Independently account for the failed current public cohort without relabeling it."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
REPO = Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
BASE = 'bcb5ff99854de595bbe3f7d60cc8796b7ada5a20'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
path = ROOT / 'full-current-attempt3/public-report.json'
report = json.loads(path.read_text())
assert report['errors'] == []
specs = []


def visit(suite):
    specs.extend(suite['specs'])
    for child in suite.get('suites', []):
        visit(child)


for suite in report['suites']:
    visit(suite)
assert len(specs) == len({s['id'] for s in specs}) == 275
inventory = json.loads((ROOT / 'current-inventory.json').read_text())
expected = set(next(c['cases'] for c in inventory['cohorts'] if c['name'] == 'public'))
observed = set(json.dumps({k: s[k] for k in ['file', 'line', 'column', 'title']}, ensure_ascii=False, separators=(',', ':')) for s in specs)
assert observed == expected
counts = {'passed': 0, 'skipped': 0, 'failed': 0}
failures = []
added = set(inventory['added'])
for spec in specs:
    assert len(spec['tests']) == 1
    test = spec['tests'][0]
    assert test['projectName'] == 'chromium' and len(test['results']) == 1
    result = test['results'][0]
    assert type(result['retry']) is int and result['retry'] == 0
    counts[result['status']] += 1
    if spec['file'] == 'smart-back.spec.ts' or json.dumps({k: spec[k] for k in ['file', 'line', 'column', 'title']}, ensure_ascii=False, separators=(',', ':')) in added:
        assert result['status'] == 'passed'
    if result['status'] == 'failed':
        source = 'frontend/e2e/' + spec['file']
        pinned = subprocess.check_output(['git', 'show', BASE + ':' + source], cwd=REPO)
        assert (REPO / source).read_bytes() == pinned
        failures.append({'id': spec['id'], 'source': source, 'line': spec['line'], 'title': spec['title'], 'error': result['error'], 'source_sha256': sha(REPO / source)})
assert counts == {'passed': 262, 'skipped': 11, 'failed': 2}
assert {k: report['stats'][k] for k in ['expected', 'skipped', 'unexpected', 'flaky']} == {'expected': 262, 'skipped': 11, 'unexpected': 2, 'flaky': 0}
assert {f['source'] for f in failures} == {'frontend/e2e/accessibility.spec.ts', 'frontend/e2e/county-response-validation.spec.ts'}
capture = json.loads((ROOT / 'full-current-attempt3-capture.json').read_text())
assert capture['target_commit'] == '982a961a58ed3647ead6bc7900250efa7d882a94'
assert capture['child_exit'] == 1 and not capture['source_changed'] and capture['timed_out'] is False
result = {'head_of_consumed_run': capture['target_commit'], 'tree_of_consumed_run': capture['target_tree'], 'source_hashes': capture['source_hashes'], 'generator_sha256': sha(Path(__file__)), 'completed': time.time(), 'consumed_hashes': {str(p.relative_to(ROOT)): sha(p) for p in [path, ROOT / 'current-inventory.json', ROOT / 'full-current-attempt3-capture.json']}, 'counts': counts, 'failures': failures, 'current_full_acceptance': False, 'scope': 'Current public cohort failed; pagination/original smart-back passes do not replace the original full-inventory acceptance gate.'}
with (OUT / 'current-public-failure-controls.json').open('x') as f:
    json.dump(result, f, indent=2)
assert json.loads((OUT / 'current-public-failure-controls.json').read_text()) == result
print(json.dumps({'counts': counts, 'failures': [{k: v for k, v in f.items() if k != 'error'} for f in failures], 'current_full_acceptance': False}, indent=2))

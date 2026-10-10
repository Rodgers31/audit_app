"""Independently account for the first fresh unchanged original-case execution."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parent
repo = Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
base = 'bcb5ff99854de595bbe3f7d60cc8796b7ada5a20'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
load = lambda path: json.loads(path.read_text())
run = root / 'original100-v1'
receipt = load(run / 'receipt.json')
driver = load(root / 'original100-v1-driver-receipt.json')
runtime = load(root / 'original100-v1-runtime.json')
report = load(run / 'report.json')
assert runtime['child_exit'] == 0 and receipt['child_exit'] == driver['child_exit'] == 0
actual_runtime = json.loads(runtime['stdout'])
assert actual_runtime['viewport'] == {'width': 1280, 'height': 720}
assert actual_runtime['node'] == 'v22.23.3' and actual_runtime['arch'] == 'x64' and actual_runtime['platform'] == 'linux'
assert actual_runtime['playwright'] == '1.58.2' and actual_runtime['chromium'] == '145.0.7632.6'
assert actual_runtime['nodeSha'] == 'fde6a4bf8d0562f7751d1a2d6cb9b417c4cfe107bbcb0aa3e9a24e125e348f48'
assert actual_runtime['chromiumSha'] == '481fea1516a1f2b76454664272f12cd9dd1f20117b21e1f1498e08bc7f872c00'
assert receipt['head'] == driver['head'] == '6fcaed18327d4ebdb91b475c016d81ca624deda8'
assert receipt['tree'] == driver['tree'] == '958d72062130267d0916ad14f9ab7ab6afb0af71'
assert not receipt['timed_out'] and not receipt['source_changed'] and not driver['helper_changed']
assert driver['helper_hashes_before'] == driver['helper_hashes_after']
assert all(sha(Path(path)) == digest for path, digest in driver['helper_hashes_before'].items())
assert all(sha(repo / path) == digest for path, digest in receipt['source_hashes'].items())
assert report['errors'] == [] and report['config']['workers'] == 2
assert len(report['config']['projects']) == 1 and report['config']['projects'][0]['name'] == 'chromium' and report['config']['projects'][0]['retries'] == 0
specs = []
def visit(suite):
    specs.extend(suite['specs'])
    for child in suite.get('suites', []):
        visit(child)
for suite in report['suites']:
    visit(suite)
assert len(specs) == len({s['id'] for s in specs}) == 100
assert {s['file'] for s in specs} == {'smart-back.spec.ts'}
assert all(s['line'] == 72 and s['column'] == 7 and s['title'] == 'scroll position is roughly preserved after smart-back' for s in specs)
for spec in specs:
    assert len(spec['tests']) == 1
    test = spec['tests'][0]
    assert test['projectName'] == 'chromium' and test['expectedStatus'] == 'passed' and test['status'] == 'expected'
    assert len(test['results']) == 1 and test['results'][0]['status'] == 'passed' and test['results'][0]['retry'] == 0
assert {k: report['stats'][k] for k in ['expected', 'unexpected', 'skipped', 'flaky']} == {'expected': 100, 'unexpected': 0, 'skipped': 0, 'flaky': 0}
original_path = repo / 'frontend/e2e/smart-back.spec.ts'
assert original_path.read_bytes() == subprocess.check_output(['git', 'show', base + ':frontend/e2e/smart-back.spec.ts'], cwd=repo)
assert receipt['source_hashes']['frontend/e2e/smart-back.spec.ts'] == sha(original_path) == '0a39e8b46d52cbc8bb932048c847f77488cb4e60fc1c32fb21b07c58c58160ae'
result = {'head': receipt['head'], 'tree': receipt['tree'], 'producer_sha256': sha(Path(__file__)), 'completed': time.time(), 'counts': {'passed': 100, 'unexpected': 0, 'skipped': 0, 'flaky': 0, 'retries': 0}, 'original_case_ids': [s['id'] for s in specs], 'original_source_sha256': sha(original_path), 'configured_workers': 2, 'runtime': actual_runtime, 'consumed_hashes': {str(p): sha(p) for p in [run / 'report.json', run / 'receipt.json', root / 'original100-v1-driver-receipt.json', root / 'original100-v1-runtime.json']}, 'source_changed': [], 'helper_changed': False, 'limits': 'Fresh local diagnostic success; does not reproduce or resolve the naturally completed-200 #607 failure, historical #601 saved900/returned100 cause, or failed original full-inventory gate. No hosted/production acceptance.'}
with (root / 'original100-v1-independent-check.json').open('x') as f:
    json.dump(result, f, indent=2)
assert load(root / 'original100-v1-independent-check.json') == result
print(json.dumps({k: v for k, v in result.items() if k not in ['original_case_ids']}, indent=2))

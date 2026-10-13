"""Independent raw-case and source controls for the navigation Spec review."""
import base64
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent
REPO = Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
BASE = 'bcb5ff99854de595bbe3f7d60cc8796b7ada5a20'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(name):
    p = ROOT / name
    consumed[name] = sha(p.read_bytes())
    return json.loads(p.read_text())


def all_specs(report):
    def visit(suite):
        yield from suite['specs']
        for child in suite.get('suites', []):
            yield from visit(child)
    return [s for suite in report['suites'] for s in visit(suite)]


def assert_cases(name, counts):
    report = load(name)
    assert report['errors'] == []
    specs = all_specs(report)
    assert specs and len(set(s['id'] for s in specs)) == len(specs)
    observed = {'expected': 0, 'unexpected': 0, 'skipped': 0, 'flaky': 0}
    for s in specs:
        assert len(s['tests']) == 1
        t = s['tests'][0]
        assert t['projectName'] == 'chromium' and len(t['results']) == 1
        r = t['results'][0]
        assert type(r['retry']) is int and r['retry'] == 0
        key = {'passed': 'expected', 'failed': 'unexpected', 'timedOut': 'unexpected', 'skipped': 'skipped'}[r['status']]
        assert t['status'] == key
        observed[key] += 1
    assert observed == counts
    assert {k: report['stats'][k] for k in observed} == observed
    assert report['config']['workers'] == 2
    assert report['config']['projects'][0]['retries'] == 0
    assert load('runtime.json')['viewport'] == {'width': 1280, 'height': 720}
    return report, specs


started = time.time()
consumed = {}
checks = []
original = (REPO / 'frontend/e2e/smart-back.spec.ts').read_bytes()
pinned = subprocess.check_output(['git', 'show', f'{BASE}:frontend/e2e/smart-back.spec.ts'], cwd=REPO)
assert original == pinned and sha(original) == '0a39e8b46d52cbc8bb932048c847f77488cb4e60fc1c32fb21b07c58c58160ae'
assert (ROOT / 'pending-original-tests/smart-back.spec.ts').read_bytes().startswith(original)
checks.append('Original smart-back test bytes and appended controlled-test prefix equal the pinned test exactly.')
inventory = load('baseline-inventory.json')
current = load('current-inventory.json')
assert inventory['total'] == 323 and len(inventory['baseline']) == len(set(inventory['baseline'])) == 323
assert current['total'] == 329 and set(inventory['baseline']).issubset(current['baseline'])
assert set(current['baseline']) - set(inventory['baseline']) == set(current['added']) and len(current['added']) == 6
checks.append('All 323 original descriptors remain; exactly six additional descriptors exist.')
red_report, red_specs = assert_cases('pending-original-red-report.json', {'expected': 0, 'unexpected': 3, 'skipped': 0, 'flaky': 0})
green_report, green_specs = assert_cases('pending-original-green-report.json', {'expected': 3, 'unexpected': 0, 'skipped': 0, 'flaky': 0})
assert [s['id'] for s in red_specs] == [s['id'] for s in green_specs]
summaries = []
for label, specs in [('red', red_specs), ('green', green_specs)]:
    for spec in specs:
        result = spec['tests'][0]['results'][0]
        attachment = next(a for a in result['attachments'] if a['name'] == 'b11-pending-original')
        data = json.loads(base64.b64decode(attachment['body']))
        before = data['beforeRelease']
        alive = [e for e in before['events'] if e['kind'] == 'probe:alive']
        assert len(alive) == 1 and len(before['events']) < 5000 and before['rows'] == 10
        if label == 'red':
            assert 'smart-back.spec.ts:38' in result['error']['stack'] and 'Timeout: 5000ms' in result['error']['message']
            assert before['url'] == 'http://127.0.0.1:3141/counties'
            assert data['requests'] and all(r['status'] == 200 for r in data['requests'])
            assert any(e.get('showing') == 'Showing 11–20 of 47 Counties' for e in before['events'])
        else:
            assert before['url'] == 'http://127.0.0.1:3141/counties?p=2' and before['y'] > 100
            assert data['requests'] == []
        summaries.append({'label': label, 'id': spec['id'], 'status': result['status'], 'url': before['url'], 'rows': before['rows'], 'y': before['y'], 'server_responses': data['requests'], 'event_count': len(before['events'])})
checks.append('Same three original-case identities fail at unchanged line 38 under pending delivery, then pass after repair with no pagination Flight response.')
for name, expected_exit in [('pending-original-red.json', 1), ('pending-original-green.json', 0)]:
    receipt = load(name)
    assert receipt['child_exit'] == expected_exit and receipt['timed_out'] is False
    assert not receipt['source_changed'] and not receipt['helpers_changed'] and receipt['generator_unchanged'] is True
    log = ROOT / receipt['log']
    assert sha(log.read_bytes()) == receipt['log_sha256']
    consumed[receipt['log']] = sha(log.read_bytes())
assert_cases('baseline-original-100-report.json', {'expected': 100, 'unexpected': 0, 'skipped': 0, 'flaky': 0})
assert_cases('focused-green-report.json', {'expected': 6, 'unexpected': 0, 'skipped': 0, 'flaky': 0})
checks.append('Raw baseline 100-repeat and six focused acceptance reports reconcile without retries/skips.')
source_paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=REPO).decode().strip('\0').split('\0')
source_hashes = {p: sha((REPO / p).read_bytes()) for p in source_paths}
assert all(sha((ROOT / p).read_bytes()) == digest for p, digest in consumed.items())
identity = subprocess.check_output(['git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], cwd=REPO, text=True).splitlines()
report = {'head': identity[0], 'tree': identity[1], 'started': started, 'ended': time.time(), 'runtime': {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform()}, 'generator_sha256': sha(Path(__file__).read_bytes()), 'consumed_hashes': consumed, 'source_hashes': source_hashes, 'checks': checks, 'original_control': summaries, 'limitations': ['These controls independently inspect archived executions; they are not a fresh browser run.', 'The red run source recorder omitted the external pending-test directory; its separate generated-source record preserves the prefix and helper identities.', 'The pending-delivery red is not a reproduction of the historical naturally completed-200 failure.', 'No causal red or explanation for the historical native-auto Y=100 scroll failure exists in these records.']}
with (OUT / 'raw-controls-v2.json').open('x') as f:
    json.dump(report, f, indent=2)
assert json.loads((OUT / 'raw-controls-v2.json').read_text()) == report
print(json.dumps({k: v for k, v in report.items() if k not in ['source_hashes', 'consumed_hashes']}, indent=2))

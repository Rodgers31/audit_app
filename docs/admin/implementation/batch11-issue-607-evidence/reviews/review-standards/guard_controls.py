import argparse
import copy
import hashlib
import importlib.util
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def first_spec(report):
    pending = list(report['suites'])
    while pending:
        suite = pending.pop(0)
        if suite['specs']:
            return suite['specs'][0]
        pending.extend(suite.get('suites', []))
    raise ValueError('No original actual spec')

p = argparse.ArgumentParser()
p.add_argument('--checkout', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
checkout = a.checkout.resolve()
output = a.output.resolve()
if output.exists() or output.is_relative_to(checkout):
    raise ValueError('Fresh external output is required')
packet = checkout / 'docs/admin/implementation/batch11-issue-607-evidence'
checker = packet / 'tools/verify_packet.py'
paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=checkout).decode().strip('\0').split('\0')
source = {name: sha(checkout / name) for name in paths}
head = subprocess.check_output(['git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], cwd=checkout, text=True).splitlines()
module_spec = importlib.util.spec_from_file_location('standards_verify', checker)
module = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(module)
checker_before = sha(checker)
inputs = {}
controls = []
started = time.time()
for filename, expected in [('focused-green-report.json.gz', {'expected': 6, 'unexpected': 0, 'skipped': 0, 'flaky': 0}), ('baseline-original-100-report.json.gz', {'expected': 100, 'unexpected': 0, 'skipped': 0, 'flaky': 0}), ('pending-original-red-report.json.gz', {'expected': 0, 'unexpected': 3, 'skipped': 0, 'flaky': 0})]:
    path = packet / 'archives' / filename
    inputs[str(path.relative_to(packet))] = sha(path)
    measured, counts = module.cases(module.load(path))
    assert counts == expected and len(measured) == sum(counts.values())
    controls.append({'name': 'actual-report-' + filename, 'passed': True, 'counts': counts})
report = module.load(packet / 'archives/focused-green-report.json.gz')
mutations = [
    ('empty-suites', lambda r: r.update(suites=[])),
    ('empty-cases', lambda r: r.update(suites=[{'specs': [], 'suites': []}])),
    ('report-errors', lambda r: r.update(errors=[{'message': 'hidden'}])),
    ('boolean-counter', lambda r: r['stats'].update(expected=True)),
    ('incorrect-counter', lambda r: r['stats'].update(expected=7)),
    ('negative-report-duration', lambda r: r['stats'].update(duration=-1)),
    ('nan-report-duration', lambda r: r['stats'].update(duration=float('nan'))),
    ('missing-spec-id', lambda r: first_spec(r).pop('id')),
    ('boolean-case-line', lambda r: first_spec(r).update(line=True)),
    ('missing-result', lambda r: first_spec(r)['tests'][0].update(results=[])),
    ('extra-retry-result', lambda r: first_spec(r)['tests'][0]['results'].append(copy.deepcopy(first_spec(r)['tests'][0]['results'][0]))),
    ('retry-index', lambda r: first_spec(r)['tests'][0]['results'][0].update(retry=1)),
    ('boolean-retry', lambda r: first_spec(r)['tests'][0]['results'][0].update(retry=False)),
    ('boolean-result-duration', lambda r: first_spec(r)['tests'][0]['results'][0].update(duration=True)),
    ('hidden-passed-error', lambda r: first_spec(r)['tests'][0]['results'][0].update(error={'message': 'hidden'})),
    ('wrong-project', lambda r: first_spec(r)['tests'][0].update(projectName='firefox')),
    ('contradictory-status', lambda r: first_spec(r)['tests'][0].update(status='unexpected')),
    ('expected-failure-policy', lambda r: first_spec(r)['tests'][0].update(expectedStatus='failed')),
]
for name, mutate in mutations:
    candidate = copy.deepcopy(report)
    mutate(candidate)
    try:
        module.cases(candidate)
    except ValueError as exc:
        controls.append({'name': name, 'passed': True, 'rejection': str(exc)})
    else:
        raise AssertionError('Verifier accepted ' + name)
duplicate = copy.deepcopy(report)
duplicate['suites'].append({'specs': [copy.deepcopy(first_spec(duplicate))], 'suites': []})
try:
    module.cases(duplicate)
except ValueError as exc:
    controls.append({'name': 'duplicate-case', 'passed': True, 'rejection': str(exc)})
else:
    raise AssertionError('Verifier accepted duplicate identity')
with tempfile.TemporaryDirectory(prefix='b11-standards-load-') as tmp:
    root = Path(tmp)
    for name, text in [('duplicate-json-key', '{"same": 1, "same": 2}'), ('nonfinite-json-number', '{"n": NaN}')]:
        path = root / (name + '.json')
        path.write_text(text)
        try:
            module.load(path)
        except ValueError as exc:
            controls.append({'name': name, 'passed': True, 'rejection': str(exc)})
        else:
            raise AssertionError('Verifier accepted ' + name)
    good = root / 'good.json'
    good.write_text('{}')
    (root / 'link.json').symlink_to(good)
    for name in ['../escape.json', '/absolute.json', '', 'link.json', 'absent.json']:
        try:
            module.relative_file(root, name)
        except ValueError as exc:
            controls.append({'name': 'path-' + repr(name), 'passed': True, 'rejection': str(exc)})
        else:
            raise AssertionError('Verifier accepted unsafe path ' + repr(name))
original = checkout / 'frontend/e2e/smart-back.spec.ts'
assert sha(original) == '0a39e8b46d52cbc8bb932048c847f77488cb4e60fc1c32fb21b07c58c58160ae'
controls.append({'name': 'original-smart-back-launch-bytes', 'passed': True})
changed = [name for name, before in source.items() if sha(checkout / name) != before]
assert not changed
assert sha(checker) == checker_before
assert all(sha(packet / name) == before for name, before in inputs.items())
result = {'scope': 'Independent Standards actual-report and malformed-input controls; no browser, full-packet, hosted or production acceptance', 'head': head[0], 'tree': head[1], 'source_hashes': source, 'source_changed': changed, 'checker_sha256_before': checker_before, 'checker_sha256_after': sha(checker), 'generator_sha256': sha(__file__), 'inputs': inputs, 'controls': controls, 'child_exit': 0, 'started': started, 'ended': time.time(), 'runtime': {'executable': sys.executable, 'executable_sha256': sha(sys.executable), 'version': sys.version, 'platform': platform.platform()}}
with output.open('x') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
assert json.loads(output.read_text()) == result
print(json.dumps({'head': head[0], 'checker_sha256': checker_before, 'controls_passed': len(controls), 'source_changed': changed, 'receipt': str(output), 'receipt_sha256': sha(output)}))

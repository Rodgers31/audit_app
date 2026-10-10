"""Execute independent synthetic harness detectors in the released owned runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
p = argparse.ArgumentParser()
p.add_argument('--checkout', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--container', required=True)
p.add_argument('--docker-host', required=True)
a = p.parse_args()
repo, output = a.checkout.resolve(), a.output.absolute()
assert output.parent.is_dir() and not output.exists() and not output.resolve().is_relative_to(repo)
output.mkdir()
driver = Path(__file__).resolve()
inputs = driver.parent / 'unit-detectors'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
helpers = [driver, *sorted(inputs.iterdir())]
helper_before = {str(path): sha(path) for path in helpers}
paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=repo).decode().strip('\0').split('\0')
source_before = {path: sha(repo / path) for path in paths}
identity = subprocess.check_output(['git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], cwd=repo, text=True).splitlines()
env = {'PATH': os.environ['PATH'], 'DOCKER_HOST': a.docker_host}
docker = shutil.which('docker')
meta = json.loads(subprocess.check_output([docker, 'inspect', a.container], env=env))[0]
assert meta['Config']['Labels']['audit_app.owner'] == 'batch11-navigation'
assert meta['State']['Running'] is True and meta['HostConfig']['PortBindings'] in [None, {}]
assert any(Path(m['Source']).resolve() == repo and m['Destination'] == '/app' for m in meta['Mounts'])
mount = next(m for m in meta['Mounts'] if output.is_relative_to(Path(m['Source']).resolve()) and m['Destination'] == '/evidence')
target = '/evidence/' + output.relative_to(Path(mount['Source']).resolve()).as_posix()
runtime_path = '/opt/b11/node-v22.23.3-linux-x64/bin:/opt/b11/python/bin:/usr/local/bin:/usr/bin:/bin'
launch = [docker, 'exec', '-w', '/app/frontend', a.container, 'env', '-i', 'PATH=' + runtime_path, 'HOME=/evidence/home', 'CI=true', 'node', 'node_modules/jest/bin/jest.js', '--config', '/evidence/review-spec/unit-detectors/jest.config.cjs', '--runInBand', '--no-cache', '--json', '--runTestsByPath']
variants = [('valid', 'valid.test.tsx', None, 0, 21, 0), ('noop', 'noop.test.tsx', r'writes \?p=N with native replaceState', 1, 0, 1), ('same-url', 'same-url-write.test.tsx', 'preserves a new valid page', 1, 0, 2)]
start = time.time()
executions = []
for name, file, pattern, expected_exit, passed, failed in variants:
    command = launch + ['/evidence/review-spec/unit-detectors/' + file, '--outputFile', target + '/' + name + '-report.json']
    if pattern:
        command += ['--testNamePattern', pattern]
    with (output / (name + '.log')).open('x') as f:
        child = subprocess.run(command, env=env, cwd=repo / 'frontend', stdout=f, stderr=subprocess.STDOUT, timeout=120)
    result = json.loads((output / (name + '-report.json')).read_text())
    assert child.returncode == expected_exit and result['numPassedTests'] == passed and result['numFailedTests'] == failed
    assert result['numRuntimeErrorTestSuites'] == 0 and result['numTotalTests'] == 21
    results = [r for suite in result['testResults'] for r in suite['assertionResults']]
    failures = [r for r in results if r['status'] == 'failed']
    assert len(failures) == failed
    if name == 'noop':
        assert 'Expected:' in failures[0]['failureMessages'][0] and '?p=2' in failures[0]['failureMessages'][0]
    if name == 'same-url':
        assert all('not.toHaveBeenCalled' in r['failureMessages'][0] for r in failures)
    executions.append({'variant': name, 'command': command, 'child_exit': child.returncode, 'counts': {k: result[k] for k in ['numTotalTests', 'numPassedTests', 'numFailedTests', 'numPendingTests', 'numRuntimeErrorTestSuites']}, 'failures': failures, 'log_sha256': sha(output / (name + '.log')), 'report_sha256': sha(output / (name + '-report.json'))})
helper_after = {str(path): sha(path) for path in helpers}
source_changed = [path for path, digest in source_before.items() if not (repo / path).is_file() or sha(repo / path) != digest]
receipt = {'head': identity[0], 'tree': identity[1], 'started': start, 'ended': time.time(), 'source_hashes': source_before, 'source_changed': source_changed, 'helper_hashes_before': helper_before, 'helper_hashes_after': helper_after, 'executions': executions, 'container': {'id': meta['Id'], 'image': meta['Image'], 'labels': meta['Config']['Labels'], 'ports': meta['HostConfig']['PortBindings']}, 'reviewer_runtime': {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform()}, 'scope': 'Synthetic unit-harness detector checks only; intentional failed/skipped copies are excluded from browser inventory and product causal evidence.'}
with (output / 'receipt.json').open('x') as f:
    json.dump(receipt, f, indent=2)
assert helper_before == helper_after and not source_changed
assert json.loads((output / 'receipt.json').read_text()) == receipt
print(json.dumps({k: v for k, v in receipt.items() if k not in ['source_hashes', 'executions']}, indent=2))

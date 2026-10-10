import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
sys.dont_write_bytecode = True
BASE = 'bcb5ff99854de595bbe3f7d60cc8796b7ada5a20'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

p = argparse.ArgumentParser()
p.add_argument('--checkout', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--expected-head', required=True)
p.add_argument('--expected-manifest-sha256', required=True)
a = p.parse_args()
checkout, output = a.checkout.resolve(), a.output.absolute()
assert not output.exists() and output.parent.is_dir() and not output.resolve().is_relative_to(checkout)
output.mkdir()
started = time.time()
producer_before = sha(__file__)
packet = checkout / 'docs/admin/implementation/batch11-issue-607-evidence'
checker = packet / 'tools/verify_packet.py'
manifest = packet / 'packet-v1.json'
checker_before, manifest_before = sha(checker), sha(manifest)
assert manifest_before == a.expected_manifest_sha256
head = subprocess.check_output(['git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], cwd=checkout, text=True).splitlines()
assert head[0] == a.expected_head
paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=checkout).decode().strip('\0').split('\0')
assert paths and len(paths) == len(set(paths))
source = {name: sha(checkout / name) for name in paths}
status_before = subprocess.check_output(['git', 'status', '--porcelain'], cwd=checkout, text=True)
assert status_before == ''
commands = []

def execute(name, argv):
    env = {'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1', 'HOME': str(output)}
    child = subprocess.run(argv, cwd=checkout, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    log = output / (name + '.log')
    with log.open('xb') as f:
        f.write(child.stdout)
    commands.append({'name': name, 'argv': argv, 'child_exit': child.returncode, 'output_sha256': sha(log)})
    return child

full_diff = execute('full-three-dot-diff', ['git', 'diff', BASE + '...HEAD'])
assert full_diff.returncode == 0 and full_diff.stdout
commit_list = execute('commit-list', ['git', 'log', BASE + '..HEAD', '--oneline'])
assert commit_list.returncode == 0
scope = execute('changed-paths', ['git', 'diff', '--name-only', '-z', BASE + '...HEAD'])
changed_paths = scope.stdout.decode().strip('\0').split('\0')
allowed_frontend = {'frontend/app/counties/CountiesPageClient.tsx', 'frontend/__tests__/countiesUrlStateSsr.test.tsx', 'frontend/e2e/county-pagination-boundaries.spec.ts', 'frontend/e2e/county-pagination-contract.spec.ts'}
assert set(name for name in changed_paths if name.startswith('frontend/')) == allowed_frontend
assert all(name in allowed_frontend or name == 'docs/admin/implementation/BATCH_11_ISSUE_607_HANDOFF.md' or name.startswith('docs/admin/implementation/batch11-issue-607-evidence/') for name in changed_paths)
active = execute('active-diff-check', ['git', 'diff', '--check', BASE + '...HEAD', '--', 'frontend', 'docs/admin/implementation/BATCH_11_ISSUE_607_HANDOFF.md', 'docs/admin/implementation/batch11-issue-607-evidence/README.md', 'docs/admin/implementation/batch11-issue-607-evidence/LESSONS.md', 'docs/admin/implementation/batch11-issue-607-evidence/tools'])
assert active.returncode == 0
raw = execute('whole-diff-check', ['git', 'diff', '--check', BASE + '...HEAD'])
common = [sys.executable, str(checker), '--packet', str(packet), '--checkout', str(checkout), '--manifest', 'packet-v1.json']
default = execute('default-packet', common + ['--output', str(output / 'default-result.json')])
assert default.returncode == 1 and b'Current full-suite acceptance blocked by unexpected failures' in default.stdout
assert not (output / 'default-result.json').exists()
integrity = execute('integrity-packet', common + ['--integrity-only', '--output', str(output / 'integrity-result.json')])
assert integrity.returncode == 0
result = json.loads((output / 'integrity-result.json').read_text())
assert result['historical_integrity'] is True and result['local_recorded_acceptance'] is False
assert result['fresh_execution'] is False and result['hosted_acceptance'] is False and result['production_acceptance'] is False
assert result['verification_scope'] == 'integrity-only'
assert result['current_full_counts'] == {'expected': 316, 'unexpected': 2, 'skipped': 11, 'flaky': 0}
catalogue = json.loads(manifest.read_text())
assert len(catalogue['files']) == 755
assert all(('docs/admin/implementation/batch11-issue-607-evidence/' + name) in source for name in catalogue['files'])
changed = [name for name, before in source.items() if sha(checkout / name) != before]
assert not changed
assert sha(checker) == checker_before and sha(manifest) == manifest_before and sha(__file__) == producer_before
assert subprocess.check_output(['git', 'status', '--porcelain'], cwd=checkout, text=True) == status_before
receipt = {'head': head[0], 'tree': head[1], 'base': BASE, 'started': started, 'ended': time.time(), 'producer_argv': sys.argv, 'producer_sha256_before': producer_before, 'producer_sha256_after': sha(__file__), 'source_hashes': source, 'source_changed': changed, 'status_before': status_before, 'status_after': status_before, 'checker_sha256': checker_before, 'manifest_sha256': manifest_before, 'catalogue_members': len(catalogue['files']), 'all_catalogue_members_git_tracked': True, 'changed_path_count': len(changed_paths), 'commands': commands, 'integrity_result_sha256': sha(output / 'integrity-result.json'), 'observed_full_counts': result['current_full_counts'], 'local_recorded_acceptance': False, 'fresh_browser_execution': False, 'child_exit': 0, 'runtime': {'executable': sys.executable, 'executable_sha256': sha(sys.executable), 'version': sys.version, 'platform': platform.platform()}, 'scope': 'Independent actual committed diff and published-corpus check; integrity passes, behavioral acceptance is blocked'}
with (output / 'receipt.json').open('x') as f:
    json.dump(receipt, f, indent=2)
    f.write('\n')
assert json.loads((output / 'receipt.json').read_text()) == receipt
print(json.dumps({k: receipt[k] for k in ['head', 'tree', 'checker_sha256', 'manifest_sha256', 'catalogue_members', 'all_catalogue_members_git_tracked', 'observed_full_counts', 'local_recorded_acceptance', 'child_exit', 'scope']}))

import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

REPO = Path('/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app')
OUT = Path(__file__).resolve().parent
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def capture():
    changed = subprocess.check_output(['git', 'diff', '--name-only', 'f6c31e271297eece52f34102dc40a1e2ed7069a8...HEAD'], cwd=REPO, text=True).splitlines()
    paths = [REPO / p for p in changed]
    paths.append(REPO / 'frontend/scripts/ci-browser-cohorts.mjs')
    paths.extend([Path(__file__), OUT / 'independent-control.mjs'])
    return {str(p): sha(p) for p in paths}
before = capture()
identity = {key: subprocess.check_output(['git', 'rev-parse', value], cwd=REPO, text=True).strip() for key,value in [('commit','HEAD'),('tree','HEAD^{tree}')]}
steps = []
commands = [
  ['node', 'docs/admin/implementation/batch10-scroll-evidence/verify.mjs'],
  ['node', '--test', 'docs/admin/implementation/batch10-scroll-evidence/verify.test.mjs'],
  ['node', str(OUT / 'independent-control.mjs')],
]
for index, command in enumerate(commands):
    log = OUT / ('execution-' + str(index + 1) + '.log')
    started = datetime.now(timezone.utc).isoformat()
    with log.open('xb') as stream:
        child = subprocess.run(command, cwd=REPO, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
    steps.append({'command':command, 'started':started, 'child_exit':child.returncode, 'log':str(log), 'log_sha256':sha(log)})
    print(json.dumps(steps[-1]))
after = capture()
receipt = {**identity, 'source_before':before, 'source_after':after, 'source_changed':[p for p in before if after.get(p) != before[p]], 'generator':str(Path(__file__)), 'generator_sha256':before[str(Path(__file__))], 'node':subprocess.check_output(['node','--version'], text=True).strip(), 'commands':steps, 'verification_exit':0 if before == after and all(s['child_exit'] == 0 for s in steps) else 1, 'not_executed':['application browser replay', 'production build', 'database or provider actions', 'publisher regeneration']}
destination = OUT / 'execution-receipt.json'
with destination.open('x') as stream: json.dump(receipt, stream, indent=2)
assert json.loads(destination.read_text()) == receipt
print(json.dumps({'receipt':str(destination), 'readback_verified':True, 'verification_exit':receipt['verification_exit']}))
raise SystemExit(receipt['verification_exit'])

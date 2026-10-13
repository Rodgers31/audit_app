"""Owned append-only command receipts; raw child status is separate from source integrity."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
SOURCE = Path('/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inventory():
    files = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=SOURCE).decode().split('\0')
    result = {name: sha(SOURCE / name) for name in files if name and (SOURCE / name).is_file()}
    for name in [f.name for f in ROOT.iterdir() if f.is_file() and f.suffix in ('.py', '.ts', '.mjs', '.sh')]:
        if (ROOT / name).exists(): result[str(ROOT / name)] = sha(ROOT / name)
    return result

name, *command = sys.argv[1:]
if not name or Path(name).name != name or not command:
    raise SystemExit('fresh name and command required')
receipt = ROOT / (name + '.json')
log = ROOT / (name + '.log')
if receipt.exists() or log.exists():
    raise SystemExit('refusing inherited output')
generator = sha(Path(__file__))
before = inventory()
start = time.time()
identity = subprocess.check_output(['git', 'rev-parse', 'HEAD', 'HEAD^{tree}'], cwd=SOURCE, text=True).splitlines()
status = subprocess.check_output(['git', 'status', '--short'], cwd=SOURCE, text=True)
env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR') if key in os.environ}
with log.open('x') as out:
    try:
        child = subprocess.run(command, cwd=SOURCE, env=env, stdout=out, stderr=subprocess.STDOUT, timeout=1800)
        code = child.returncode
        timeout = False
    except subprocess.TimeoutExpired:
        code = None
        timeout = True
after = {name: sha(SOURCE / name) if (SOURCE / name).is_file() else None for name in before}
changed = [name for name in before if before[name] != after[name]]
data = {'generated_by': str(Path(__file__)), 'generator_sha256': generator, 'target_commit': identity[0],
        'target_tree': identity[1], 'source_hashes': before, 'starting_status': status, 'command': command,
        'started_at': start, 'ended_at': time.time(), 'child_exit': code, 'timeout': timeout,
        'source_changed_during_run': changed, 'generator_unchanged': generator == sha(Path(__file__)),
        'log': log.name, 'log_sha256': sha(log), 'verification_exit': 1 if changed or timeout else code}
with receipt.open('x') as out:
    json.dump(data, out, indent=2)
if json.loads(receipt.read_text()) != data:
    raise SystemExit('receipt readback mismatch')
print(json.dumps({key: data[key] for key in ('target_commit', 'command', 'child_exit', 'timeout', 'source_changed_during_run', 'verification_exit')}))
raise SystemExit(data['verification_exit'])

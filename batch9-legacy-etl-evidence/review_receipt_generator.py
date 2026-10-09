"""Recorder executed only against the PR596 coordinator-owned checkout."""
import ast
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/Users/roger/.codex/worktrees/batch9-pr596-review/audit_app')
OUT = Path(__file__).resolve().parent
name, command = sys.argv[1], sys.argv[2:]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def snapshot():
    files = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    included = ['backend/models.py', 'backend/database.py', 'backend/admin_etl_dispatch.py', 'backend/admin_etl_dispatch_worker.py']
    prefixes = ('etl/', 'backend/seeding/', 'backend/tests/test_batch9_legacy', 'backend/tests/batch9_legacy', '.github/scripts/run_backend_tests', '.github/scripts/tests/test_backend_test_launcher', 'batch9-legacy-etl-evidence/')
    return {p: digest(ROOT / p) for p in files if (p in included or p.startswith(prefixes)) and (ROOT / p).is_file()}

start = snapshot()
tree = ast.parse((ROOT / 'batch9-legacy-etl-evidence/verify_delivery.py').read_text())
selected = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'CURRENT_SOURCE_PATHS' for target in node.targets))
if not selected <= start.keys():
    raise RuntimeError('Incomplete review source snapshot: ' + str(sorted(selected - start.keys())))
generator_before = digest(Path(__file__))
if start['batch9-legacy-etl-evidence/review_receipt_generator.py'] != generator_before:
    raise RuntimeError('Archived review generator differs from executed generator')
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
clock_start = time.monotonic()
now = datetime.now(timezone.utc).isoformat()
selected_environment = {key: os.environ.get(key) for key in ('PYTHONDONTWRITEBYTECODE', 'PYTHON_DOTENV_DISABLED', 'TESTING', 'DATABASE_URL', 'BATCH9_LEGACY_DATABASE_URL', 'BATCH9_LEGACY_FIXTURE_PORT')}
with (OUT / (name + '.log')).open('w') as stream:
    result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
end = snapshot()
head_after = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
generator_after = digest(Path(__file__))
output = OUT / (name + '.log')
stable = start == end and head == head_after and generator_before == generator_after
record = {'generated_by': str(Path(__file__)), 'generator_sha256': generator_before, 'generator_after_sha256': generator_after, 'start_time': now, 'duration_seconds': time.monotonic() - clock_start, 'cwd': str(ROOT), 'target_commit': head, 'target_commit_after': head_after, 'selected_environment': selected_environment, 'source_before': start, 'source_after': end, 'source_stable': stable, 'command': command, 'exit_code': result.returncode, 'verdict': 'PASSED' if result.returncode == 0 and stable else 'FAILED', 'output_sha256': digest(output), 'output_path': str(output)}
(OUT / (name + '.json')).write_text(json.dumps(record, indent=2) + '\n')
print(name, result.returncode, 'stable', stable, output.read_text()[-1000:])
sys.exit(result.returncode or (0 if stable else 1))

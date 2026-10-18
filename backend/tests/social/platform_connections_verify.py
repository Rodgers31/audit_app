"""Write a source-bound local fixture receipt; no live network or DB access."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve()
    backend = here.parents[2]
    root = backend.parent
    paths = sorted((backend / 'social/platform_connections').glob('*.py')) + [here, here.with_name('test_platform_connections.py'), backend / 'alembic/versions/a703b15a0001_platform_connections.py']
    hashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    runs = []
    for optimized in (False, True):
        command = [sys.executable] + (['-O'] if optimized else []) + ['-m', 'pytest', '-q', 'tests/social/test_platform_connections.py']
        result = subprocess.run(command, cwd=backend, capture_output=True, text=True)
        runs.append({'command': command, 'cwd': str(backend), 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
    receipt = {'generated_by': str(here), 'generator_sha256': hashes[str(here.relative_to(root))], 'generated_at': datetime.now(timezone.utc).isoformat(), 'target_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(), 'uncommitted_source_hashes': hashes, 'verdict': 'PASSED' if all(run['exit_code'] == 0 for run in runs) else 'FAILED', 'scope': 'Sanitized HTTPX provider fixtures and isolated SQLite only; no live-provider or PostgreSQL acceptance', 'runs': runs}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    observed = json.loads(args.output.read_text())
    if observed['generator_sha256'] != hashlib.sha256(here.read_bytes()).hexdigest() or observed['uncommitted_source_hashes'] != hashes:
        raise RuntimeError('Receipt provenance readback failed')
    print(json.dumps({'receipt': str(args.output), 'verdict': observed['verdict'], 'commands': [run['command'] for run in runs], 'summaries': [run['stdout'].splitlines()[-1] for run in runs]}, indent=2))
    return 0 if observed['verdict'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())

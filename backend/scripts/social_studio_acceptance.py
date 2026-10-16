"""Source-bound local studio test receipts. No installs, providers or hosted checks."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(root):
    tracked = subprocess.check_output(['git', 'diff', '--name-only', '-z', '06896185005d822c4b29888138b984510dd1fdbd'], cwd=root).split(b'\0')
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=root).split(b'\0')
    return {os.fsdecode(p): digest(root / os.fsdecode(p)) for p in sorted(set(tracked + untracked)) if p and (root / os.fsdecode(p)).is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--optimized', action='store_true')
    parser.add_argument('--postgres', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = sources(root)
    env = {'PATH': '/opt/homebrew/bin:/usr/bin:/bin', 'PYTHONPATH': str(root / 'backend'), 'LANG': 'C', 'HOME': os.environ['HOME']}
    if args.postgres:
        env['B15_RENDERING_TEST_DATABASE_URL'] = 'postgresql+psycopg2://postgres:fixture-rendering-only@127.0.0.1:55402/b15_rendering_final'
    tests = ['backend/tests/social/test_studio.py', 'backend/tests/social/test_studio_regressions.py', 'backend/tests/social/test_studio_api.py']
    if args.postgres:
        tests.append('backend/tests/social/test_studio_postgres.py')
    command = [sys.executable, *(['-O'] if args.optimized else []), '-m', 'pytest', '--confcutdir=backend/tests/social', *tests, '-q', '--tb=short']
    with (args.output / 'stdout.log').open('xb') as stdout, (args.output / 'stderr.log').open('xb') as stderr:
        result = subprocess.run(command, cwd=root, env=env, stdout=stdout, stderr=stderr, timeout=180, check=False)
    unchanged = manifest == sources(root)
    receipt = {'generated_by': str(Path(__file__).resolve()), 'generator_sha256': digest(Path(__file__)), 'generated_at': datetime.now(timezone.utc).isoformat(), 'target_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(), 'worktree': str(root), 'command': command, 'source_sha256': manifest, 'source_unchanged': unchanged, 'returncode': result.returncode, 'stdout_sha256': digest(args.output / 'stdout.log'), 'stderr_sha256': digest(args.output / 'stderr.log'), 'verdict': 'PASS' if result.returncode == 0 and unchanged else 'FAILED'}
    path = args.output / 'receipt.json'
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    actual = json.loads(path.read_text())
    if actual['generator_sha256'] != digest(Path(__file__)) or actual['source_sha256'] != manifest or actual['verdict'] != receipt['verdict']:
        raise RuntimeError('Receipt provenance readback failed')
    print(json.dumps({'verdict': actual['verdict'], 'returncode': result.returncode, 'receipt': str(path)}))
    return 0 if actual['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())

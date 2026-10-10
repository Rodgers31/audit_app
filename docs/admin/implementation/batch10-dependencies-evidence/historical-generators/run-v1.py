#!/usr/bin/env python3
"""Append-only command capture for this lane's owned external output directory."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(os.environ['BATCH10_DEPENDENCIES_OUTPUT']).resolve()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(paths=None):
    if paths is None:
        tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
        added = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
        paths = sorted(set(p for p in tracked + added if p and not p.startswith('docs/admin/implementation/batch10-dependencies-evidence/raw/')))
    return {
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
        'tree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=ROOT).decode().strip(),
        'status': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).decode(),
        'files': {p: sha(ROOT / p) if (ROOT / p).is_file() else None for p in paths},
    }


def main():
    name, cwd, *command = sys.argv[1:]
    if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name) or not command:
        raise ValueError('name cwd command [args] required')
    if not OUT.is_dir():
        raise ValueError('owned output directory must already exist')
    destinations = [OUT / (name + suffix) for suffix in ('.json', '.stdout', '.stderr')]
    for dest in destinations:
        if dest.exists() or dest.is_symlink():
            raise FileExistsError(dest)
    before = identity()
    started = time.time()
    env = dict(os.environ)
    env.update(NEXT_PUBLIC_API_URL='http://127.0.0.1:18014', INTERNAL_API_URL='http://127.0.0.1:18014',
               NEXT_TELEMETRY_DISABLED='1', ONNXRUNTIME_NODE_INSTALL='skip',
               NATIVE_VERIFY_CACHE_DIR=str(OUT.parent / 'model-cache'),
               npm_config_cache=str(OUT.parent / 'npm-cache'), npm_config_engine_strict='true')
    # The checkout has no environment files. Next's loader therefore has no
    # private dotenv input; all public targets above are inert loopback.
    code, signal, error = None, None, None
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=1800)
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
        if code < 0:
            signal = -code
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, error = exc.stdout or b'', exc.stderr or b'', 'deadline exceeded'
    after = identity(before['files'])
    stable = before == after
    receipt = {
        'generated_by': str(Path(__file__).relative_to(ROOT)), 'generator_sha256': sha(Path(__file__)),
        'started_at_unix': started, 'ended_at_unix': time.time(), 'command': command, 'cwd': cwd,
        'source_before': before, 'source_after': after, 'source_stable': stable,
        'exit': code, 'signal': signal, 'error': error, 'verification_exit': 0 if code == 0 and stable and error is None else 1,
        'runtime': {'python': sys.version, 'platform': sys.platform, 'machine': os.uname().machine},
        'resolved_environment': {k: env[k] for k in ('NEXT_PUBLIC_API_URL', 'INTERNAL_API_URL', 'NEXT_TELEMETRY_DISABLED', 'ONNXRUNTIME_NODE_INSTALL', 'NATIVE_VERIFY_CACHE_DIR', 'npm_config_cache', 'npm_config_engine_strict')},
        'stdout_sha256': hashlib.sha256(stdout).hexdigest(), 'stderr_sha256': hashlib.sha256(stderr).hexdigest(),
    }
    for dest, value in zip(destinations, [json.dumps(receipt, indent=2).encode() + b'\n', stdout, stderr]):
        with dest.open('xb') as handle:
            handle.write(value)
    readback = json.loads(destinations[0].read_bytes())
    if readback != receipt or readback['generator_sha256'] != sha(Path(__file__)):
        raise RuntimeError('receipt readback mismatch')
    print(json.dumps({'name': name, 'exit': code, 'stable': stable, 'error': error,
                      'stdout_tail': stdout[-1500:].decode(errors='replace'), 'stderr_tail': stderr[-1500:].decode(errors='replace')}))
    return receipt['verification_exit']


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Append-only command capture for this lane's owned external output directory."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import signal as signals
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


def inputs(cwd, paths=None):
    """Bind disposable candidate bytes separately from the author checkout."""
    root = Path(cwd).resolve()
    if root.is_relative_to(ROOT):
        return {'root': str(root), 'files': {}}
    if paths is None:
        paths = []
        for directory, children, files in os.walk(root.parent if root.name == 'frontend' else root):
            children[:] = [n for n in children if n not in ('node_modules', '.next', '.git', '.cache', 'coverage')]
            for name in files:
                file = Path(directory) / name
                paths.append(str(file))
    return {'root': str(root), 'files': {p: sha(Path(p)) if Path(p).is_file() else None for p in sorted(paths)}}


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
    generator_hash = sha(Path(__file__))
    before = identity()
    input_before = inputs(cwd)
    started = time.time()
    env = dict(os.environ)
    env.update(NEXT_PUBLIC_API_URL='http://127.0.0.1:18014', INTERNAL_API_URL='http://127.0.0.1:18014',
               NEXT_PUBLIC_SUPABASE_URL='http://127.0.0.1:18014', NEXT_PUBLIC_SUPABASE_ANON_KEY='batch10-dependencies-inert-anon-key',
               PYTHON_DOTENV_DISABLED='1',
               NEXT_TELEMETRY_DISABLED='1', ONNXRUNTIME_NODE_INSTALL='skip',
               NATIVE_VERIFY_CACHE_DIR=str(OUT.parent / 'model-cache'),
               npm_config_cache=str(OUT.parent / 'npm-cache'), npm_config_engine_strict='true')
    # The checkout has no environment files. Next's loader therefore has no
    # private dotenv input; all public targets above are inert loopback.
    code, signal, error = None, None, None
    try:
        child = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = child.communicate(timeout=1800)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signals.SIGTERM)
            try:
                stdout, stderr = child.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signals.SIGKILL)
                stdout, stderr = child.communicate(timeout=10)
            error = 'deadline exceeded; owned process group terminated'
        code = child.returncode
        if code < 0:
            signal = -code
    except OSError as exc:
        stdout, stderr, error = b'', b'', str(exc)
    after = identity()
    # Keep deleted inputs in the inventory as explicit missing files.
    for path in before['files'].keys() - after['files'].keys():
        after['files'][path] = None
    input_after = inputs(cwd)
    for path in input_before['files'].keys() - input_after['files'].keys():
        input_after['files'][path] = None
    stable = before == after and input_before == input_after
    receipt = {
        'generated_by': str(Path(__file__).resolve().relative_to(ROOT)), 'generator_sha256': generator_hash,
        'started_at_unix': started, 'ended_at_unix': time.time(), 'command': command, 'cwd': cwd,
        'source_before': before, 'source_after': after, 'source_stable': stable,
        'input_before': input_before, 'input_after': input_after,
        'exit': code, 'signal': signal, 'error': error, 'verification_exit': 0 if code == 0 and stable and error is None else 1,
        'runtime': {'python': sys.version, 'platform': sys.platform, 'machine': os.uname().machine},
        'resolved_environment': {k: env[k] for k in ('NEXT_PUBLIC_API_URL', 'INTERNAL_API_URL', 'NEXT_PUBLIC_SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_ANON_KEY', 'PYTHON_DOTENV_DISABLED', 'NEXT_TELEMETRY_DISABLED', 'ONNXRUNTIME_NODE_INSTALL', 'NATIVE_VERIFY_CACHE_DIR', 'npm_config_cache', 'npm_config_engine_strict')},
        'stdout_sha256': hashlib.sha256(stdout).hexdigest(), 'stderr_sha256': hashlib.sha256(stderr).hexdigest(),
    }
    for dest, value in zip(destinations, [json.dumps(receipt, indent=2).encode() + b'\n', stdout, stderr]):
        with dest.open('xb') as handle:
            handle.write(value)
    readback = json.loads(destinations[0].read_bytes())
    if readback != receipt or readback['generator_sha256'] != generator_hash:
        raise RuntimeError('receipt readback mismatch')
    print(json.dumps({'name': name, 'exit': code, 'stable': stable, 'error': error,
                      'stdout_tail': stdout[-1500:].decode(errors='replace'), 'stderr_tail': stderr[-1500:].decode(errors='replace')}))
    return receipt['verification_exit']


if __name__ == '__main__':
    sys.exit(main())

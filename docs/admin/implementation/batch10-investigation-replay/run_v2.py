#!/usr/bin/env python3
"""Append-only current command capture; does not republish historical archives."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from replay_env import child_environment, external_output, refuse_dotenv, require

ROOT = Path(__file__).resolve().parents[4]
GIT = shutil.which('git', path=os.defpath)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    require(GIT is not None, 'git runtime unavailable')
    # Git itself also runs without ambient GIT_DIR/GIT_WORK_TREE/config overrides.
    return subprocess.check_output([GIT, *args], cwd=ROOT, env={'PATH': os.defpath, 'HOME': os.devnull}).decode()


def identity():
    require(Path(git('rev-parse', '--show-toplevel').strip()).resolve() == ROOT,
            'exact independent Git checkout required')
    paths = sorted(set(p for p in (git('ls-files', '-z') + git('ls-files', '--others', '--exclude-standard', '-z')).split('\0') if p))
    return {'head': git('rev-parse', 'HEAD').strip(), 'tree': git('rev-parse', 'HEAD^{tree}').strip(),
            'status': git('status', '--porcelain'),
            'files': {p: sha(ROOT / p) if (ROOT / p).is_file() else None for p in paths}}


def inputs(cwd):
    root = Path(cwd).resolve()
    if root.is_relative_to(ROOT):
        return {'root': str(root), 'files': {}}
    paths = []
    for directory, children, files in os.walk(root.parent if root.name == 'frontend' else root):
        children[:] = [n for n in children if n not in ('node_modules', '.next', '.git', '.cache', 'coverage')]
        for name in files:
            paths.append(str(Path(directory) / name))
    return {'root': str(root), 'files': {p: sha(p) if Path(p).is_file() else None for p in sorted(paths)}}


def main():
    name, cwd, *command = sys.argv[1:]
    require(bool(name) and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name) and bool(command),
            'name cwd absolute-command [args] required')
    require(Path(command[0]).is_absolute(), 'absolute executable required')
    cwd = str(Path(cwd).resolve())
    require(Path(cwd).is_dir(), 'child working directory absent')
    out = external_output(ROOT, os.environ['BATCH10_DEPENDENCIES_OUTPUT'])
    destinations = [out / (name + suffix) for suffix in ('.json', '.stdout', '.stderr')]
    for dest in destinations:
        require(not dest.exists() and not dest.is_symlink(), 'inherited output refused: ' + str(dest))
    before = identity()
    refuse_dotenv(ROOT, ROOT / 'frontend', cwd)
    input_before = inputs(cwd)
    generator_hash = sha(__file__)
    policy_hash = sha(Path(__file__).with_name('replay_env.py'))
    env = child_environment(out / (name + '-runtime'), command[0])
    started = time.time()
    code, child_signal, error = None, None, None
    try:
        child = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            stdout, stderr = child.communicate(timeout=1800)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                stdout, stderr = child.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                stdout, stderr = child.communicate(timeout=10)
            error = 'deadline exceeded; owned process group terminated'
        code = child.returncode
        if code < 0:
            child_signal = -code
    except OSError as exc:
        stdout, stderr, error = b'', b'', str(exc)
    after, input_after = identity(), inputs(cwd)
    for axis, old in ((after, before), (input_after, input_before)):
        for path in old['files'].keys() - axis['files'].keys():
            axis['files'][path] = None
    stable = before == after and input_before == input_after
    receipt = {
        'schema': 2, 'classification': 'CURRENT_COMMAND_CAPTURE', 'current_checkout_acceptance': False,
        'meaning': 'recorded child and source stability; does not establish issue 494/601/607 acceptance',
        'generated_by': str(Path(__file__).resolve().relative_to(ROOT)), 'generator_sha256': generator_hash,
        'environment_policy_sha256': policy_hash, 'started_at_unix': started, 'ended_at_unix': time.time(),
        'command': command, 'cwd': cwd, 'source_before': before, 'source_after': after, 'source_stable': stable,
        'input_before': input_before, 'input_after': input_after, 'exit': code, 'signal': child_signal, 'error': error,
        'verification_exit': 0 if code == 0 and stable and error is None else 1,
        'runtime': {'python': sys.version, 'platform': sys.platform, 'machine': os.uname().machine},
        'resolved_environment': env, 'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
        'stderr_sha256': hashlib.sha256(stderr).hexdigest(),
    }
    for dest, value in zip(destinations, [json.dumps(receipt, indent=2).encode() + b'\n', stdout, stderr]):
        with dest.open('xb') as handle:
            handle.write(value)
    require(json.loads(destinations[0].read_bytes()) == receipt, 'receipt readback mismatch')
    print(json.dumps({'name': name, 'exit': code, 'stable': stable, 'error': error}))
    return receipt['verification_exit']


if __name__ == '__main__':
    sys.exit(main())

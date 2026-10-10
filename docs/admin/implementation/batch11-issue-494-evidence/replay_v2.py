"""Portable, inert command capture and source export; historical v1 stays immutable."""
import argparse
import hashlib
import io
import json
import os
import signal
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def real_path(value):
    raw = os.fspath(value)
    need(Path(raw).is_absolute() and '..' not in raw.split('/'), 'absolute non-traversing path required')
    path = Path(raw)
    for ancestor in [*reversed(path.parents), path]:
        need(not ancestor.is_symlink(), 'symlink ancestor refused')
    return path.resolve()


def relative(value):
    need(type(value) is str and value and '\\' not in value, 'unsafe source member')
    parts = value.split('/')
    need(all(p and p not in ('.', '..') for p in parts) and not value.startswith('/'), 'unsafe source member')
    return value


def source_file(root, name):
    target = real_path(root / relative(name))
    need(target.is_relative_to(root) and target.is_file(), 'regular source member required')
    return target


def git(root, *args):
    return subprocess.check_output(['/usr/bin/git', *args], cwd=root,
                                   env={'PATH': '/usr/bin:/bin', 'HOME': '/dev/null'})


def identity(root):
    root = real_path(root)
    need(Path(git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve() == root,
         'exact Git root required')
    names = sorted(set(git(root, 'ls-files', '-z').decode().split('\0') +
                       git(root, 'ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')) - {''})
    need(bool(names), 'nonempty source inventory required')
    return {'head': git(root, 'rev-parse', 'HEAD').decode().strip(),
            'tree': git(root, 'rev-parse', 'HEAD^{tree}').decode().strip(),
            'status': git(root, 'status', '--porcelain=v1').decode(),
            'files': {name: sha(source_file(root, name).read_bytes()) for name in names}}


def output_directory(value, root):
    destination = real_path(value)
    need(not destination.is_relative_to(root) and not root.is_relative_to(destination), 'external output required')
    need(not destination.exists() or (destination.is_dir() and not any(destination.iterdir())), 'fresh output required')
    if not destination.exists():
        need(destination.parent.is_dir(), 'existing real output parent required')
        destination.mkdir()
    return destination


def publish(path, data):
    with path.open('xb') as stream:
        stream.write(data)
    need(path.read_bytes() == data, 'publication readback mismatch')


def child_environment(destination, executable, mode):
    owned = {name: destination / name for name in ('home', 'tmp', 'npm-cache', 'models', 'browsers')}
    for directory in owned.values():
        directory.mkdir()
    user, global_ = destination / 'npm-user', destination / 'npm-global'
    publish(user, b''); publish(global_, b'')
    environment = {'PATH': str(Path(executable).parent) + ':/usr/bin:/bin',
                   'HOME': str(owned['home']), 'TMPDIR': str(owned['tmp']), 'LANG': 'C.UTF-8',
                   'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1',
                   'NEXT_TELEMETRY_DISABLED': '1', 'ONNXRUNTIME_NODE_INSTALL': 'skip',
                   'npm_config_cache': str(owned['npm-cache']), 'npm_config_userconfig': str(user),
                   'npm_config_globalconfig': str(global_), 'npm_config_engine_strict': 'true',
                   'NATIVE_VERIFY_CACHE_DIR': str(owned['models']), 'PLAYWRIGHT_BROWSERS_PATH': str(owned['browsers'])}
    if mode == 'build':
        environment.update({'NEXT_PUBLIC_API_URL': 'http://127.0.0.1:18048', 'INTERNAL_API_URL': 'http://127.0.0.1:18048',
                            'NEXT_PUBLIC_SUPABASE_URL': 'http://127.0.0.1:18048',
                            'NEXT_PUBLIC_SUPABASE_ANON_KEY': 'batch11-review-inert-anon-key'})
    return environment


def run(root, destination, cwd, mode, command, timeout=1200):
    need(command and Path(command[0]).is_absolute(), 'absolute executable required')
    cwd = real_path(cwd)
    need(cwd.is_dir() and cwd.is_relative_to(root), 'cwd must belong to measured checkout')
    for directory in (root, root / 'frontend', cwd):
        for candidate in directory.glob('.env*'):
            need(candidate.name.endswith(('.example', '.sample', '.template')), 'runtime dotenv refused')
    before = identity(root)
    generator = sha(Path(__file__).read_bytes())
    env = child_environment(destination, command[0], mode)
    started = time.time(); error = None
    with (destination / 'stdout.log').open('xb') as stdout, (destination / 'stderr.log').open('xb') as stderr:
        child = subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True, stdout=stdout, stderr=stderr)
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            error = 'timeout; owned process group terminated'
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=10)
    try:
        after = identity(root)
    except Exception as failure:
        after = {'measurement_error': str(failure)}
    result = {'schema': 2, 'classification': 'CURRENT_COMMAND_CAPTURE', 'current_checkout_acceptance': False,
              'generator_sha256': generator, 'source_before': before, 'source_after': after,
              'source_stable': before == after, 'command': command, 'cwd': str(cwd), 'mode': mode,
              'environment': env, 'exit': child.returncode, 'error': error, 'pid': child.pid,
              'started_at': started, 'ended_at': time.time(),
              'stdout_sha256': sha((destination / 'stdout.log').read_bytes()),
              'stderr_sha256': sha((destination / 'stderr.log').read_bytes())}
    publish(destination / 'receipt.json', (json.dumps(result, indent=2) + '\n').encode())
    return child.returncode == 0 and error is None and before == after


def export(root, destination):
    before = identity(root)
    with tarfile.open(destination / 'source.tar', 'x') as archive:
        for name, digest in before['files'].items():
            data = source_file(root, name).read_bytes()
            need(sha(data) == digest, 'source changed during export')
            member = tarfile.TarInfo(name); member.size = len(data); member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
    need(identity(root) == before, 'source changed during export')
    manifest = {'schema': 2, 'classification': 'SOURCE_EXPORT', 'current_checkout_acceptance': False,
                'generator_sha256': sha(Path(__file__).read_bytes()), 'source': before,
                'archive_sha256': sha((destination / 'source.tar').read_bytes())}
    publish(destination / 'source-manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
    return True


def pack(root, corpus, destination):
    # A fresh generic byte archive does not reinterpret historical receipts.
    identity(root)
    corpus = real_path(corpus)
    need(corpus.is_dir() and not corpus.is_relative_to(root) and not root.is_relative_to(corpus), 'external corpus required')
    need(not destination.is_relative_to(corpus) and not corpus.is_relative_to(destination), 'output must be separate from corpus')
    selected = {}
    for target in sorted(corpus.rglob('*')):
        real_path(target)
        need(target.is_file() or target.is_dir(), 'regular corpus member required')
        if target.is_file():
            selected[relative(target.relative_to(corpus).as_posix())] = target.read_bytes()
    need(bool(selected), 'nonempty corpus required')
    with zipfile.ZipFile(destination / 'replay.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in selected.items():
            archive.writestr(name, data)
    need({n: sha(source_file(corpus, n).read_bytes()) for n in selected} ==
         {n: sha(data) for n, data in selected.items()}, 'corpus changed during packing')
    manifest = {'schema': 2, 'classification': 'REPLAY_BYTE_ARCHIVE', 'current_checkout_acceptance': False,
                'generator_sha256': sha(Path(__file__).read_bytes()),
                'archive_sha256': sha((destination / 'replay.zip').read_bytes()),
                'members': {n: sha(data) for n, data in selected.items()}}
    publish(destination / 'replay-manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('run', 'export', 'pack'))
    parser.add_argument('checkout'); parser.add_argument('output')
    parser.add_argument('--cwd'); parser.add_argument('--mode', choices=('plain', 'unit', 'build', 'native'), default='plain')
    parser.add_argument('--corpus')
    arguments = sys.argv[1:]
    separator = arguments.index('--') if '--' in arguments else len(arguments)
    args = parser.parse_args(arguments[:separator])
    command = arguments[separator + 1:]
    root = real_path(args.checkout)
    # Validate all source paths before creating any output or launching a child.
    identity(root)
    destination = output_directory(args.output, root)
    if args.operation == 'export':
        return 0 if export(root, destination) else 1
    if args.operation == 'pack':
        need(args.corpus is not None, '--corpus required')
        return 0 if pack(root, args.corpus, destination) else 1
    return 0 if run(root, destination, args.cwd or str(root), args.mode, command) else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)

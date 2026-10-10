"""Real bounded cache regression; run through replay_v2.py for process readback.

Uses five public packages with exact versions/resolution/integrity from the
supported lock. No application install, provider, deployment or credentials.
Historical repaired bytes model a plausible cache; hosted cache identity is
unavailable. The command control does not certify the complete application.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

OLD = 'eb456efd5d96b4073609489f7a2cd41b18db157b'
MEMBERS = {'node_modules/' + name for name in ('braces', 'sprintf-js', 'fill-range', 'to-regex-range', 'is-number')}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root):
    result = {}
    for path in root.rglob('*'):
        require(path.resolve() == path and not path.is_symlink(), 'Fixture alias refused')
        require(path.is_dir() or path.is_file(), 'Regular fixture required')
        if path.is_file():
            require(not path.name.startswith('.env') and not path.name.endswith('.env'), 'Fixture dotenv refused')
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('red', 'green'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--npm-cli', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cached', type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('cache_owned_capture', Path(__file__).with_name('replay_v2.py'))
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    root = replay.real_path(args.root)
    before = replay.identity(root)
    node, npm = replay.real_path(args.node), replay.real_path(args.npm_cli)
    require(node.is_file() and npm.is_file(), 'Existing read-only Node/npm runtime required')
    out = replay.real_path(args.out)
    require(not out.exists() and not out.is_relative_to(root) and not root.is_relative_to(out), 'Fresh external output required')
    require(out.parent.is_dir(), 'Existing real output parent required')
    canonical = json.loads((root / 'frontend/package-lock.json').read_text())
    package = dict(name='owned-tooling-cache-control', version='1.0.0', private=True,
        scripts=dict(postinstall='node scripts/apply-tooling-repairs.cjs'),
        devDependencies={'braces': '3.0.3', 'sprintf-js': '1.0.3'})
    out.mkdir()
    fixture = out / 'fixture'
    cached_identity = None
    if args.mode == 'green':
        require(args.cached is not None, 'Recorded red cache required')
        cached = replay.real_path(args.cached)
        require(cached.is_dir() and not cached.is_relative_to(root) and not root.is_relative_to(cached) and not cached.is_relative_to(out)
            and not out.is_relative_to(cached), 'Separate external cache required')
        receipt_path = replay.real_path(cached / 'receipt.json')
        require(receipt_path.is_file(), 'Regular cache receipt required')
        receipt = json.loads(receipt_path.read_text())
        require(receipt.get('mode') == 'red' and receipt.get('classification') == 'BOUNDED_INSTALL_CACHE_CONTROL', 'Recorded red cache required')
        cached_identity = files(cached / 'fixture')
        require(cached_identity == receipt.get('fixture_after'), 'Recorded cache bytes changed')
        require(json.loads((cached / 'fixture/package.json').read_text()) == package, 'Owned fixture entrypoint required')
        for name in ('apply-tooling-repairs.cjs', 'tooling-repairs.json'):
            require(sha(cached / 'fixture/scripts' / name) == sha(root / 'frontend/scripts' / name), 'Current reviewed installer required')
        shutil.copytree(cached / 'fixture', fixture)
    else:
        require(args.cached is None, 'Fresh red cache required')
        (fixture / 'scripts').mkdir(parents=True)
        (fixture / 'package.json').write_text(json.dumps(package, indent=2))
    home = out / 'home'; home.mkdir()
    cache = out / 'npm-cache'; cache.mkdir()
    for name in ('npm-userconfig', 'npm-globalconfig'):
        (out / name).write_text('')
    env = dict(PATH=str(node.parent) + ':/usr/bin:/bin', HOME=str(home), TMPDIR=str(out),
        npm_config_cache=str(cache), npm_config_userconfig=str(out / 'npm-userconfig'),
        npm_config_globalconfig=str(out / 'npm-globalconfig'), npm_config_audit='false', npm_config_fund='false',
        npm_config_registry='https://registry.npmjs.org/', npm_config_engine_strict='true')
    steps = []
    def measured(argv, label):
        started = datetime.now(timezone.utc).isoformat()
        with (out / (label + '.stdout.log')).open('xb') as stdout, (out / (label + '.stderr.log')).open('xb') as stderr:
            result = subprocess.run([str(node), str(npm), *argv], cwd=fixture, env=env, stdout=stdout, stderr=stderr, timeout=90)
        steps.append(dict(label=label, argv=argv, exit=result.returncode, started_at=started,
            ended_at=datetime.now(timezone.utc).isoformat(), stdout_sha256=sha(out / (label + '.stdout.log')),
            stderr_sha256=sha(out / (label + '.stderr.log'))))
        return result.returncode
    def locked():
        lock = json.loads((fixture / 'package-lock.json').read_text())
        require(lock.get('lockfileVersion') == 3 and set(lock['packages']) == MEMBERS | {''}, 'Exact bounded package graph required')
        for name in MEMBERS:
            require(all(lock['packages'][name].get(key) == canonical['packages'][name].get(key)
                for key in ('version', 'resolved', 'integrity')), 'Fixture public package differs from supported lock')
    if args.mode == 'red':
        for name in ('apply-tooling-repairs.cjs', 'tooling-repairs.json'):
            data = subprocess.check_output(['/usr/bin/git', 'show', OLD + ':frontend/scripts/' + name], cwd=root,
                env={'PATH': '/usr/bin:/bin'}, timeout=15)
            (fixture / 'scripts' / name).write_bytes(data)
        require(measured(['install', '--include=dev', '--include=optional'], 'historical-real-install') == 0,
            'Historical public install prerequisite failed')
        locked()
        target = fixture / 'node_modules/sprintf-js/dist/sprintf.min.js'
        oldbytes = target.read_bytes()
        oldmanifest = json.loads((fixture / 'scripts/tooling-repairs.json').read_text())
        expected = next(p for p in oldmanifest['patches'] if p['package'] == 'sprintf-js' and p['file'] == 'dist/sprintf.min.js')['repaired_sha256']
        require(hashlib.sha256(oldbytes).hexdigest() == expected, 'Exact historical repaired cache bytes required')
        for name in ('apply-tooling-repairs.cjs', 'tooling-repairs.json'):
            shutil.copyfile(root / 'frontend/scripts' / name, fixture / 'scripts' / name)
        require(measured(['install', '--include=dev', '--include=optional'], 'cached-real-install') != 0, 'Older repaired cache unexpectedly accepted')
        require('tooling repair: upstream bytes changed node_modules/sprintf-js/dist/sprintf.min.js'
            in (out / 'cached-real-install.stderr.log').read_text(), 'Unrelated negative install failure')
        require(target.read_bytes() == oldbytes, 'Refused cache was mutated')
    else:
        locked()  # Validate every public resolution before executing any install.
        command = json.loads((root / 'frontend/vercel.json').read_text())['installCommand'].split()
        require(command == ['npm', 'ci', '--include=dev', '--include=optional'], 'Current immutable hosted install policy required')
        marker = fixture / 'node_modules/owned-stale-cache-marker'; marker.write_text('owned old cache')
        oldlock = (fixture / 'package-lock.json').read_bytes()
        require(measured(command[1:], 'cached-real-ci') == 0, 'Current real npmci failed')
        require(not marker.exists() and (fixture / 'package-lock.json').read_bytes() == oldlock, 'Cache replacement or immutable lock failed')
        manifest = json.loads((fixture / 'scripts/tooling-repairs.json').read_text())
        for package in manifest['packages']:
            for name, identity in package['files'].items():
                require(sha(fixture / 'node_modules' / package['name'] / name) == identity['repaired_sha256'], 'Exact repaired package inventory mismatch')
        require(measured(['ls', '--all', '--json'], 'installed-graph') == 0, 'Installed fixture graph invalid')
    locked()
    after = replay.identity(root)
    require(before == after, 'Consumed source changed during cache control')
    receipt = dict(mode=args.mode, classification='BOUNDED_INSTALL_CACHE_CONTROL', current_checkout_acceptance=False,
        source_before=before, source_after=after, historical_git_head=OLD, node=str(node), node_sha256=sha(node),
        npm=str(npm), npm_cli_sha256=sha(npm), steps=steps, cached_identity=cached_identity,
        producer_sha256=sha(Path(__file__)), fixture_after=files(fixture),
        caveat='Controlled historical repaired cache; hosted cache identity unavailable; five-package proof only.')
    with (out / 'receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2)
    require(json.loads((out / 'receipt.json').read_text()) == receipt, 'Cache control receipt readback mismatch')
    print(json.dumps(dict(mode=args.mode, classification=receipt['classification'], steps=steps)))


if __name__ == '__main__':
    main()

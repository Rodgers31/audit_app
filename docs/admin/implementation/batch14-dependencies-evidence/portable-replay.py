"""Portable, bounded investigation replay. No product candidate is accepted here."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

PACKET = Path(__file__).resolve().parent
FROZEN = '3f3b1f1981b93c3317e204defbd235121c1df084'
CANDIDATE = {'package.json': '5a6a00d523e19a1d95af7b55c0967349008825505e541e2ae75b9140b48c4ad5',
             'package-lock.json': 'fda6befb45060e569b869902e165d8cd47f2dd0d0e19048ad968f7f8715e2d37'}
CONTRACT = json.loads((PACKET / 'replay-source-contract.json').read_text())


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def publish(p, value):
    encoded = json.dumps(value, indent=2, allow_nan=False) + '\n'
    with p.open('x') as f:
        f.write(encoded)
    if p.read_text() != encoded:
        raise RuntimeError('receipt readback mismatch: ' + str(p))


def installed_links(root):
    """Permit npm bin links and the frozen local plugin; bind every target."""
    modules = root / 'node_modules'
    if not modules.exists():
        return {}
    if modules.is_symlink() or not modules.is_dir():
        raise ValueError('installed module root must not be a link')
    links = {}
    for directory, directories, files in os.walk(modules, followlinks=False):
        for name in directories + files:
            q = Path(directory) / name
            if not q.is_symlink():
                if not q.is_dir() and not q.is_file():
                    raise ValueError('installed special file refused: ' + str(q))
                continue
            try:
                target = q.resolve(strict=True)
            except (OSError, RuntimeError) as error:
                raise ValueError('installed link is broken or cyclic: ' + str(q)) from error
            local = q == modules / 'eslint-plugin-local' and target == root / 'eslint-rules'
            binary = q.parent.name == '.bin' and modules in target.parents and target.is_file()
            if not (local or binary):
                raise ValueError('installed unbound link refused: ' + str(q))
            links[str(q)] = {'literal_target': os.readlink(q), 'resolved': str(target),
                             'target_sha256': None if local else digest(target)}
    return links


def checked_root(raw, candidate=False, installed=True):
    p = Path(raw)
    if not p.is_absolute() or p.is_symlink() or not p.is_dir():
        raise ValueError('invalid frontend root (absolute existing directory required): ' + str(p))
    p = p.resolve(strict=True)
    # A borrowed fixture must match the complete authoritative install contract.
    for q in p.iterdir():
        if q.name.lower() in {'.npmrc', 'npm-shrinkwrap.json'}:
            raise ValueError('unexpected project npm configuration: ' + str(q))
    actual = set()
    for folder in ['scripts', 'eslint-rules']:
        if (p / folder).is_symlink() or not (p / folder).is_dir():
            raise ValueError('fixture source inventory mismatch: linked/missing ' + folder)
        for q in (p / folder).rglob('*'):
            if q.is_symlink():
                raise ValueError('linked fixture input: ' + str(q))
            if q.is_file():
                actual.add(q.relative_to(p).as_posix())
    expected = {x for x in CONTRACT if x.startswith(('scripts/', 'eslint-rules/'))}
    if actual != expected:
        raise ValueError('fixture source inventory mismatch: ' + str(p))
    for name, sha in CONTRACT.items():
        q = p / name
        if q.is_symlink() or not q.is_file() or digest(q) != (CANDIDATE.get(name, sha) if candidate else sha):
            raise ValueError('fixture source hash mismatch: ' + str(q))
    if installed and not (p / 'node_modules/@istanbuljs/load-nyc-config').is_dir():
        raise ValueError('frontend is not installed: ' + str(p))
    installed_links(p)
    return p


def snapshot(roots=()):
    paths = {p for p in PACKET.rglob('*') if p.is_file() and '__pycache__' not in p.parts
             and (p.suffix in {'.py', '.cjs', '.patch'} or p.name == 'replay-source-contract.json')}
    for root in roots:
        paths.update(root / n for n in CONTRACT)
        # Bind installed JavaScript/JSON/patch inputs as well as the manifests.
        # Native binaries are not executed by these bounded CLI/repair probes.
        paths.update(p for p in (root / 'node_modules').rglob('*')
                     if p.is_file() and p.suffix in {'.js', '.cjs', '.mjs', '.json', '.patch'})
    return {str(p): digest(p) for p in sorted(paths)}


class Session:
    def __init__(self, output, roots=()):
        self.output = Path(output)
        if not self.output.is_absolute() or self.output.is_symlink() or self.output.exists():
            raise ValueError('output must be a fresh absolute external directory')
        resolved = self.output.resolve()
        repository = subprocess.run(['git', '-C', str(PACKET), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        repo_root = Path(repository.stdout.strip()) if repository.returncode == 0 else None
        for source in [PACKET, *([repo_root] if repo_root else []), *roots]:
            if resolved == source or source in resolved.parents or resolved in source.parents:
                raise ValueError('output must be external to measured source roots')
        self.output.mkdir(parents=True)
        self.roots = roots
        self.before = snapshot(roots)
        self.links_before = {str(root): installed_links(root) for root in roots}
        self.identity = {'available': False, 'reason': 'relocated packet outside a Git checkout'}
        if repo_root:
            self.identity = {'available': True, 'head': subprocess.check_output(['git', '-C', str(PACKET), 'rev-parse', 'HEAD'], text=True).strip(),
                         'tree': subprocess.check_output(['git', '-C', str(PACKET), 'rev-parse', 'HEAD^{tree}'], text=True).strip(),
                         'status': subprocess.check_output(['git', '-C', str(PACKET), 'status', '--porcelain'], text=True).splitlines()}
        self.node = shutil.which('node')
        self.npm = shutil.which('npm')
        if not self.node or not self.npm:
            raise ValueError('node and npm must be installed on PATH')
        self.tmp = tempfile.TemporaryDirectory(prefix='batch14-replay-')
        self.work = Path(self.tmp.name)
        for n in ['home', 'tmp', 'cache']:
            (self.work / n).mkdir()
        for n in ['user.npmrc', 'global.npmrc']:
            (self.work / n).write_text('')
        self.env = {'PATH': os.pathsep.join(dict.fromkeys([str(Path(self.node).parent), str(Path(self.npm).parent), '/usr/bin', '/bin', '/usr/sbin', '/sbin'])),
                    'HOME': str(self.work / 'home'), 'TMPDIR': str(self.work / 'tmp'),
                    'npm_config_cache': str(self.work / 'cache'),
                    'npm_config_userconfig': str(self.work / 'user.npmrc'),
                    'npm_config_globalconfig': str(self.work / 'global.npmrc'),
                    'npm_config_registry': 'https://registry.npmjs.org/',
                    'ONNXRUNTIME_NODE_INSTALL': 'skip', 'LANG': 'C', 'LC_ALL': 'C'}

    def run(self, name, argv, cwd, expected=0, diagnostic=None, timeout=120, install_contract=None):
        cwd = Path(cwd).resolve(strict=True)
        before = dict(self.before)
        if install_contract:
            install_root, install_candidate = install_contract
            before.update({str(install_root / n): digest(install_root / n) for n in CONTRACT})
        record = {'argv': [str(a) for a in argv], 'cwd': str(cwd),
                  'environment': self.env, 'generator': str(Path(__file__).resolve()),
                  'generator_sha256': digest(__file__), 'sources_before': before,
                  'installed_links_before': self.links_before,
                  'source_git_identity': self.identity, 'started_at': datetime.now(timezone.utc).isoformat()}
        child = subprocess.Popen(record['argv'], cwd=cwd, env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        timed_out = False
        try:
            stdout, stderr = child.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGKILL)
            stdout, stderr = child.communicate()
        except BaseException:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.communicate()
            raise
        code = child.returncode
        descendants = False
        try:
            os.killpg(child.pid, 0)
            descendants = True
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        record.update(timed_out=timed_out, surviving_process_group=descendants,
                      finished_at=datetime.now(timezone.utc).isoformat())
        for suffix, data in [('stdout', stdout), ('stderr', stderr)]:
            with (self.output / (name + '.' + suffix)).open('xb') as f:
                f.write(data)
        source_error = None
        try:
            for root in self.roots:
                checked_root(str(root), digest(root / 'package.json') == CANDIDATE['package.json'])
            if install_contract:
                checked_root(str(install_root), install_candidate, installed=False)
            unchanged = (all(not Path(p).is_symlink() and Path(p).is_file() and digest(p) == sha for p, sha in before.items())
                         and snapshot(self.roots) == self.before
                         and {str(root): installed_links(root) for root in self.roots} == self.links_before)
        except (OSError, ValueError) as error:
            unchanged = False
            source_error = str(error)
        valid = code == expected and unchanged and not timed_out and not descendants and (diagnostic is None or diagnostic.encode() in stdout + stderr)
        record.update(child_returncode=code, expected_returncode=expected, sources_unchanged=unchanged,
                      matched_diagnostic=diagnostic, source_error=source_error, verified=valid,
                      output_sha256={s: digest(self.output / (name + '.' + s)) for s in ['stdout', 'stderr']})
        publish(self.output / (name + '.receipt.json'), record)
        if not valid:
            raise RuntimeError('replay command failed: ' + name + ' (see retained receipt)')
        return stdout

    def close(self):
        self.tmp.cleanup()
        publish(self.output / 'cleanup.json', {'owned_temporary_root': str(self.work), 'absent': not self.work.exists()})


def install(session, name, root, candidate=False):
    checked_root(str(root), candidate, installed=False)
    return session.run(name, [session.npm, 'ci', '--include=dev', '--include=optional', '--no-audit', '--no-fund'], root,
                       expected=1 if candidate else 0,
                       diagnostic='tooling repair: missing locked sprintf-js' if candidate else 'source-bound-tooling-repairs', timeout=300, install_contract=(root, candidate))


def prepare(args):
    source = Path(args.source).resolve(strict=True)
    session = Session(args.output)
    try:
        for label in ['baseline', 'candidate']:
            root = session.output / label / 'frontend'
            for name in CONTRACT:
                q = root / name
                q.parent.mkdir(parents=True, exist_ok=True)
                q.write_bytes(subprocess.check_output(['git', '-C', str(source), 'show', FROZEN + ':frontend/' + name]))
            if label == 'candidate':
                for filename in ['package.json', 'package-lock.json']:
                    session.run('patch-' + filename, ['patch', '--batch', '-p2', '-i', str(PACKET / ('candidate-' + filename + '.patch'))], root)
            install(session, label + '-install', root, label == 'candidate')
    finally:
        session.close()
    publish(session.output / 'prepared.json', {'baseline': str(session.output / 'baseline/frontend'),
            'candidate': str(session.output / 'candidate/frontend'), 'frozen_commit': FROZEN,
            'meaning': 'candidate installation intentionally rejected; no compatibility acceptance'})


def replay(args):
    baseline = checked_root(args.baseline)
    candidate = checked_root(args.candidate, True)
    if baseline == candidate:
        raise ValueError('baseline and candidate roots must differ')
    session = Session(args.output, (baseline, candidate))
    try:
        if args.mode in {'spec', 'blocker'}:
            session.run(args.mode, [session.node, str(PACKET / 'replay-cases.cjs'), args.mode, str(baseline), str(candidate)], session.work)
        else:
            session.run('spec', [session.node, str(PACKET / 'replay-cases.cjs'), 'spec', str(baseline), str(candidate)], session.work)
            probe = PACKET / 'probe-argparse.cjs'
            for name, root in [('baseline', baseline), ('candidate', candidate)]:
                session.run(name + '-probe', [session.node, str(probe), str(root)], session.work)
            session.run('probe-absent', [session.node, str(probe), str(session.work / 'missing')], session.work, expected=1, diagnostic='ENOENT')
            session.run('probe-noargs', [session.node, str(probe)], session.work, expected=1, diagnostic='Usage:')
            clean = session.work / 'candidate-clean-install'
            clean.mkdir()
            for name in CONTRACT:
                q = clean / name
                q.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(candidate / name, q)
            install(session, 'candidate-clean-install', clean, True)
            session.run('blocker', [session.node, str(PACKET / 'replay-cases.cjs'), 'blocker', str(baseline), str(candidate)], session.work)
    finally:
        session.close()
    publish(session.output / 'result.json', {'replay_completed': True, 'mode': args.mode,
            'candidate_compatible': False, 'sources_before': session.before})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--source', required=True, help='repository containing the frozen commit')
    prep.add_argument('--output', required=True)
    for mode in ['spec', 'blocker', 'standards']:
        command = sub.add_parser(mode)
        command.add_argument('--baseline', required=True, help='absolute installed baseline frontend')
        command.add_argument('--candidate', required=True, help='absolute installed patched frontend')
        command.add_argument('--output', required=True, help='fresh absolute external receipt directory')
    args = parser.parse_args(argv)
    try:
        prepare(args) if args.mode == 'prepare' else replay(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        parser.exit(1, 'replay refused: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()

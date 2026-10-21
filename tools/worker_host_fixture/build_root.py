"""Image-build-only public runtime bundle. Never copy a live service filesystem."""
import hashlib
import importlib.metadata
import json
import os
import platform
import runpy
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/fixture-root')


def main():
    if os.getuid() != 0 or ROOT.exists():
        raise RuntimeError('Fresh build root required')
    ROOT.mkdir(mode=0o755)
    shutil.copytree('/usr', ROOT / 'usr', symlinks=True)
    for name in ('bin', 'sbin', 'lib', 'lib64'):
        target = Path('/' + name)
        if target.is_symlink():
            (ROOT / name).symlink_to(os.readlink(target))
        elif target.exists():
            shutil.copytree(target, ROOT / name, symlinks=True)
    (ROOT / 'etc').mkdir()
    # The official Python binary links libpython from /usr/local/lib. Preserve
    # the builder's loader cache; usr alone is not a runnable copied runtime.
    shutil.copyfile('/etc/ld.so.cache', ROOT / 'etc/ld.so.cache')
    # Debian's BLAS and other runtime sonames pass through alternatives links.
    # These links come only from the public build image, never a live host.
    shutil.copytree('/etc/alternatives', ROOT / 'etc/alternatives', symlinks=True)
    shutil.copytree('/etc/ssl', ROOT / 'etc/ssl', symlinks=True)
    HOSTS = runpy.run_path('/input/host/host_config.py')['HOSTS']
    (ROOT / 'etc/b29-hosts').write_text(HOSTS)
    (ROOT / 'etc/nsswitch.conf').write_text('hosts: files\npasswd: files\ngroup: files\n')
    (ROOT / 'etc/passwd').write_text('fixture:x:10001:10001:Inert fixture:/tmp:/bin/false\n')
    (ROOT / 'etc/group').write_text('fixture:x:10001:\n')
    for name in ('app', 'host'):
        (ROOT / name).mkdir()
    # The qualified rehearsal module resolves two source parents at import.
    # Preserve its bytes and give it a real, deep immutable source location.
    (ROOT / 'fixture/tools/worker_rehearsal').mkdir(parents=True)
    (ROOT / 'harness').symlink_to('fixture/tools/worker_rehearsal', target_is_directory=True)
    # Render's git clone supplies only tracked files; a separate build context
    # is used locally. Extensions and the one vendored data directory are fixed.
    source = Path('/input/backend')
    files = [p for p in source.rglob('*') if p.is_file() and
             (p.suffix in ('.py', '.sql', '.ini', '.json') or
              str(p.relative_to(source)).startswith('social/adapters/x_vendor/'))]
    if not files or sum(p.stat().st_size for p in files) > 32 * 1024 ** 2:
        raise RuntimeError('Bounded nonempty public source required')
    for p in files:
        if p.is_symlink() or any(q.is_symlink() for q in p.parents):
            raise RuntimeError('Source symlink refused')
        dest = ROOT / 'app' / p.relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)
    for origin, dest in (('/input/rehearsal', 'harness'), ('/input/host', 'host')):
        for p in Path(origin).glob('*.py'):
            if p.is_symlink():
                raise RuntimeError('Helper symlink refused')
            shutil.copyfile(p, ROOT / dest / p.name)
    # Preserve the independently qualified B27 observer; the new startup shim
    # runs it explicitly, adding boundary and backup observation only.
    (ROOT / 'harness/sitecustomize.py').rename(ROOT / 'harness/b27_sitecustomize.py')
    shutil.copyfile(ROOT / 'host/host_sitecustomize.py', ROOT / 'harness/sitecustomize.py')
    for name in ('state', 'evidence', 'tmp', 'dev', 'dev/shm'):
        dest = ROOT / name
        dest.mkdir(parents=True, exist_ok=True)
        os.chown(dest, 10001, 10001)
        dest.chmod(0o700)
    (ROOT / 'outside-denied-marker').write_text('Public synthetic denial control\n')
    inventory = {}
    for directory in ('app', 'harness', 'host'):
        for p in (ROOT / directory).rglob('*'):
            if p.is_file():
                p.chmod(0o444)
                inventory[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
            elif p.is_dir():
                p.chmod(0o555)
        (ROOT / directory).chmod(0o555)
    resolvers = list((ROOT / 'usr/lib').glob('*/libnss_wrapper.so'))
    if len(resolvers) != 1 or resolvers[0].is_symlink():
        raise RuntimeError('One immutable vendor resolver required')
    resolver = resolvers[0]
    manifest = dict(version=1, files=inventory, packages={d.metadata['Name']: d.version
        for d in importlib.metadata.distributions()}, production_accepted=False,
        python=platform.python_version(), architecture=platform.machine(),
        harness_realpath='/fixture/tools/worker_rehearsal',
        confinement='landlock-seccomp-v1',
        resolver={'path':'/' + str(resolver.relative_to(ROOT)),
                  'sha256':hashlib.sha256(resolver.read_bytes()).hexdigest()},
        hosts_sha256=hashlib.sha256(HOSTS.encode()).hexdigest(),
        os_release=Path('/etc/os-release').read_text(),
        os_packages=subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}=${Version}\n'], text=True))
    encoded = json.dumps(manifest, sort_keys=True, indent=2)
    (ROOT / 'manifest.json').write_text(encoded)
    (ROOT / 'manifest.json').chmod(0o444)
    if (ROOT / 'manifest.json').read_text() != encoded:
        raise RuntimeError('Manifest readback mismatch')


if __name__ == '__main__':
    main()

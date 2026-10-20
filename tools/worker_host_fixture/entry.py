"""Explicit maintenance image PID1; discard production environment before work."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys


def main():
    if os.getpid() != 1 or os.getuid() != 10001 or os.getgid() != 10001:
        raise RuntimeError('Actual outer fixture PID1 required')
    if os.environ.get('B28_CLEAN') != '1':
        # Only the public HTTP port is admitted; values are never logged. Exec
        # also removes the original credential-bearing environment from /proc.
        port = os.environ.get('PORT', '8000')
        if not re.fullmatch('[1-9][0-9]{0,4}', port) or int(port) > 65535:
            raise RuntimeError('Public port invalid')
        null_fd = os.open('/dev/null', os.O_RDONLY)
        os.dup2(null_fd, 0)
        os.closerange(3, 1048576)
        os.execve(sys.executable, [sys.executable, '-I', '-B', '-S', '/host/entry.py'],
                  {'B28_CLEAN': '1', 'B28_PORT': port, 'LC_ALL': 'C.UTF-8'})
    if set(os.environ) != {'B28_CLEAN', 'B28_PORT', 'LC_ALL'} or os.environ['LC_ALL'] != 'C.UTF-8':
        raise RuntimeError('Uncleared entry environment')
    sys.path.insert(0, '/host')
    from isolation import enter_namespaces, jail, require
    import socket
    from uuid import uuid4
    import platform
    manifest = json.loads(Path('/fixture-root/manifest.json').read_text())
    for p in Path('/host').glob('*.py'):
        require(not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()
                == manifest['files']['host/' + p.name], 'Outer helper differs from immutable bundle')
    cgroup = Path('/sys/fs/cgroup')
    require((cgroup / 'memory.max').read_text().strip() == str(512 * 1024 ** 2)
            and (cgroup / 'memory.swap.max').read_text().strip() == '0', '512MiB/no-swap service required')
    cpu = (cgroup / 'cpu.max').read_text().split()
    require(len(cpu) == 2 and all(x.isascii() and x.isdecimal() for x in cpu)
            and int(cpu[1]) > 0 and int(cpu[0]) * 2 == int(cpu[1]), 'Half-CPU service required')
    identity = dict(run_id=uuid4().hex[:12],
        manifest_sha256=hashlib.sha256(Path('/fixture-root/manifest.json').read_bytes()).hexdigest(),
        python=platform.python_version(), architecture=platform.machine(),
        private_tcp_translation={'127.0.0.4:443':'127.0.0.4:8443'})
    # This listener is opened before network isolation. Only the observer keeps
    # it. It serves fixed maintenance responses, never an app or artifact API.
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('0.0.0.0', int(os.environ['B28_PORT'])))
    listener.listen(8)
    listener.setblocking(False)
    identity['isolation'] = enter_namespaces()
    root_evidence = Path('/fixture-root/evidence')
    require(not list(root_evidence.iterdir()), 'Fresh image-owned evidence required')
    (root_evidence / 'identity.json').write_text(json.dumps(identity, sort_keys=True))
    print('HOST_FIXTURE_IDENTITY ' + json.dumps(identity, sort_keys=True), flush=True)
    observer = os.fork()
    if observer == 0:
        from observer import observe
        observe(listener, identity)
        os._exit(0)
    listener.close()
    # Import config before root confinement; it admits no production value.
    from host_config import environment
    values = environment(identity['run_id'])
    jail('/fixture-root')
    os.execve('/usr/local/bin/python', ['/usr/local/bin/python', '-B', '/host/boot.py'], values)


if __name__ == '__main__':
    main()

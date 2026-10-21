"""Namespace plus Landlock/seccomp boundary for the public host fixture.

No production environment is consumed. Actual outer PID1 is preserved. No mount
or production signal is attempted; content outside fixed public paths is denied.
Image UID0 is deliberately outside the single nonzero runtime UID map.
"""
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import socket
import stat
import struct
import sys

LIBC = ctypes.CDLL(None, use_errno=True)
NAMESPACES = ('user', 'mnt', 'net')
UID = 10001


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def call(result, operation):
    if result != 0:
        raise OSError(ctypes.get_errno(), operation)


def private_mounts(content):
    require(type(content) is str and 0 < len(content) <= 524288, 'Mount inventory bound')
    lines = content.splitlines()
    require(0 < len(lines) <= 2048, 'Mount census required')
    identities, roots = set(), 0
    for line in lines:
        parts = line.split(' - ')
        require(len(parts) == 2, 'Mount shape')
        left, right = parts[0].split(), parts[1].split()
        # Optional fields include shared/master propagation. Unknown fields also
        # refuse rather than silently assuming a mount is private.
        require(len(left) == 6 and len(right) == 3, 'Nonprivate/unknown mount')
        require(re.fullmatch('[1-9][0-9]*', left[0]) and left[0] not in identities,
                'Mount identity')
        identities.add(left[0])
        require(re.fullmatch('[0-9]+', left[1]) and re.fullmatch('[0-9]+:[0-9]+', left[2])
                and left[3].startswith('/') and left[4].startswith('/'), 'Mount fields')
        require(re.fullmatch('[A-Za-z0-9_.-]+', right[0]), 'Filesystem identity')
        for options in (left[5], right[2]):
            tokens = options.split(',')
            require(tokens[0] in ('ro', 'rw') and not {'ro', 'rw'} <= set(tokens)
                    and all(re.fullmatch(r'[A-Za-z0-9_.=:/\\+@%~-]+', x) for x in tokens),
                    'Mount options')
        roots += left[4] == '/'
    require(roots == 1, 'One root mount required')
    return len(lines)


def enter_namespaces():
    require(os.getpid() == 1 and os.getuid() == UID and os.getgid() == UID,
            'Actual nonroot outer PID1 required')
    before = {k: os.readlink('/proc/self/ns/' + k) for k in NAMESPACES}
    call(LIBC.unshare(0x10000000 | 0x00020000 | 0x40000000), 'unshare')
    Path('/proc/self/setgroups').write_text('deny')
    Path('/proc/self/uid_map').write_text(f'{UID} {UID} 1\n')
    Path('/proc/self/gid_map').write_text(f'{UID} {UID} 1\n')
    require(os.getuid() == UID and os.getgid() == UID, 'Mapped identity changed')
    after = {k: os.readlink('/proc/self/ns/' + k) for k in NAMESPACES}
    require(all(before[k] != after[k] for k in NAMESPACES), 'Namespace identity unchanged')
    mounts = private_mounts(Path('/proc/self/mountinfo').read_text())
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        req = struct.pack('16sH', b'lo', 0)
        flags = struct.unpack('16sH', fcntl.ioctl(sock.fileno(), 0x8913, req)[:18])[1]
        fcntl.ioctl(sock.fileno(), 0x8914, struct.pack('16sH', b'lo', flags | 1))
    require(len(Path('/proc/net/route').read_text().splitlines()) == 1, 'Outside route refused')
    with socket.socket() as sock:
        sock.settimeout(1)
        require(sock.connect_ex(('192.0.2.1', 443)) == errno.ENETUNREACH,
                'Outside connection not refused')
    return dict(before=before, after=after, private_mount_count=mounts,
                outside_connect_errno=errno.ENETUNREACH, outer_pid=1)


def drop_capabilities():
    class Header(ctypes.Structure):
        _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]
    class Data(ctypes.Structure):
        _fields_ = [('effective', ctypes.c_uint32), ('permitted', ctypes.c_uint32),
                    ('inheritable', ctypes.c_uint32)]
    # Drop the complete bounding set while CAP_SETPCAP is still available.
    last = int(Path('/proc/sys/kernel/cap_last_cap').read_text())
    require(0 <= last <= 63, 'Known capability range required')
    for number in range(last + 1):
        call(LIBC.prctl(24, number, 0, 0, 0), 'drop bounding capability')
    call(LIBC.prctl(47, 4, 0, 0, 0), 'clear ambient capabilities')
    header, data = Header(0x20080522, 0), (Data * 2)()
    call(LIBC.capset(ctypes.byref(header), ctypes.byref(data)), 'clear capabilities')
    call(LIBC.prctl(38, 1, 0, 0, 0), 'no new privileges')


def confine(*, keep_fds=()):
    require(keep_fds == (), 'Outside descriptor inheritance refused')
    for root in ('/', '/app', '/harness', '/host', '/fixture', '/fixture/tools'):
        info = Path(root).stat()
        require(info.st_uid == 65534 and stat.S_IMODE(info.st_mode) & 0o022 == 0,
                'Immutable unmapped public root required')
    stdio_boundary()
    resource.setrlimit(resource.RLIMIT_NOFILE, (512, 512))
    resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    for path in list(Path('/proc/self/fd').iterdir()):
        fd = int(path.name)
        if fd > 2:
            try:
                os.close(fd)
            except OSError as error:
                require(error.errno == errno.EBADF, 'Descriptor close failed')
    drop_capabilities()
    from confinement import install
    boundary = install()
    require(type(boundary) is dict and boundary.get('kind') == 'landlock-seccomp',
            'Mountless confinement refused')
    os.chdir('/')
    return boundary


def content_boundary():
    # Landlock confines content access rather than hiding path metadata. These
    # known-existing public/self paths must refuse an open, never merely miss.
    for name in ('/outside-denied-marker', '/proc/self/environ',
                 '/sys/fs/cgroup/memory.current'):
        try:
            with open(name, 'rb') as source:
                source.read(1)
        except PermissionError:
            pass
        else:
            raise RuntimeError('Outside content read admitted')
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM):
            pass
    except OSError as error:
        require(error.errno == errno.EPERM, 'UNIX socket refusal differs')
    else:
        raise RuntimeError('Pathname UNIX socket admitted')
    require(LIBC.prctl(21, 0, 0, 0, 0) == 2, 'Syscall filter absent')
    return True


def resolver_boundary():
    # sitecustomize runs before Python adds the script's /host directory.
    # Load only the already-inventoried immutable helper, without ambient imports.
    import runpy
    config = runpy.run_path('/host/host_config.py')
    path = config['resolver_library']()
    require(os.environ.get('B29_SANDBOX') == 'landlock-seccomp-v1'
            and os.environ.get('LD_PRELOAD') == path
            and os.environ.get('NSS_WRAPPER_HOSTS') == '/etc/b29-hosts',
            'Fixed synthetic resolver configuration required')
    manifest = json.loads(Path('/manifest.json').read_text())
    hosts = Path('/etc/b29-hosts')
    info = hosts.stat(follow_symlinks=False)
    require(manifest.get('confinement') == 'landlock-seccomp-v1'
            and stat.S_ISREG(info.st_mode) and info.st_uid == 65534
            and stat.S_IMODE(info.st_mode) & 0o022 == 0
            and hosts.read_bytes() == config['HOSTS'].encode()
            and manifest.get('hosts_sha256') == hashlib.sha256(config['HOSTS'].encode()).hexdigest()
            and manifest.get('resolver') == dict(path=path,
                sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest()),
            'Immutable vendor resolver differs')
    for name, address in (('b15-worker-db','127.0.0.2'), ('b15-worker-wire','127.0.0.3'),
                          ('b15-worker-api','127.0.0.1'), ('graph.facebook.com','127.0.0.4'),
                          ('auth.fixture.test','127.0.0.4'),
                          ('a'*32+'.r2.cloudflarestorage.com','127.0.0.4')):
        rows = socket.getaddrinfo(name, 443, socket.AF_INET, socket.SOCK_STREAM)
        require(rows and {row[4][0] for row in rows} == {address}, 'Private resolver differs')
    return True


def null_device():
    info = os.stat('/dev/null', follow_symlinks=False)
    require(stat.S_ISCHR(info.st_mode) and info.st_rdev == os.makedev(1, 3),
            'Real copied null device required')
    return True


def resolver_descriptor(fd):
    """Only the vendor resolver's already-readable, immutable public cache."""
    require(type(fd) is int and 3 <= fd < 512, 'Bounded non-stdio resolver FD required')
    actual = os.fstat(fd)
    expected = os.stat('/etc/b29-hosts', follow_symlinks=False)
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    return (stat.S_ISREG(actual.st_mode) and stat.S_ISREG(expected.st_mode)
            and actual.st_uid == expected.st_uid == 65534
            and actual.st_nlink == expected.st_nlink == 1
            and stat.S_IMODE(actual.st_mode) & 0o022 == 0
            and (actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino)
            and flags & os.O_ACCMODE == os.O_RDONLY
            and not flags & getattr(os, 'O_PATH', 0x200000))


def post_exec():
    """Executed afresh inside the copied root, after capabilities were dropped."""
    require(os.getuid() == UID and os.getgid() == UID, 'Nonzero fixed identity required')
    for root in ('/', '/app', '/harness', '/host', '/fixture', '/fixture/tools'):
        info = Path(root).stat()
        require(info.st_uid == 65534 and stat.S_IMODE(info.st_mode) & 0o022 == 0,
                'Source root writable or replaceable by fixture identity')
    if null_device() is not True:
        raise RuntimeError('Null device validation refused')
    require(content_boundary() is True, 'Outside content boundary refused')
    require(resolver_boundary() is True, 'Synthetic resolver refused')
    require(LIBC.prctl(39, 0, 0, 0, 0) == 1, 'No-new-privileges absent')
    class Header(ctypes.Structure):
        _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]
    class Data(ctypes.Structure):
        _fields_ = [('effective', ctypes.c_uint32), ('permitted', ctypes.c_uint32),
                    ('inheritable', ctypes.c_uint32)]
    header, data = Header(0x20080522, 0), (Data * 2)()
    call(LIBC.capget(ctypes.byref(header), ctypes.byref(data)), 'read post-exec capabilities')
    require(all(d.effective == d.permitted == d.inheritable == 0 for d in data),
            'Post-exec capabilities retained')
    checked = 0
    for cap in range(64):
        value = LIBC.prctl(23, cap, 0, 0, 0)
        if value == -1 and ctypes.get_errno() == errno.EINVAL:
            break
        require(value == 0 and LIBC.prctl(47, 1, cap, 0, 0) == 0,
                'Bounding/ambient capability retained')
        checked += 1
    require(checked > 0, 'Capability census absent')
    require(resource.getrlimit(resource.RLIMIT_NOFILE) == (512, 512)
            and resource.getrlimit(resource.RLIMIT_NPROC) == (128, 128), 'Resource bounds differ')
    helpers = {
        'import endpoints; endpoints.main("127.0.0.4",prewarm=True)': 'endpoint',
        'import wire; wire.main("127.0.0.3")': 'wire'}
    log_name = helpers.get(sys.orig_argv[-1]) if (len(sys.orig_argv) == 4
        and sys.orig_argv[:3] == [sys.executable, '-B', '-c']) else None
    if sys.orig_argv == [sys.executable, '-B', '/host/endpoint.py']:
        log_name = 'endpoint'
    stdio_boundary(log_name=log_name)
    allowed = set()
    if 'social.worker' in sys.orig_argv:
        # Import the public fixture checker by its fixed immutable location.
        # This pipe is the sole extra descriptor the actual launcher supplies.
        import runpy
        allowed.add(runpy.run_path('/host/custody.py')['receipt_descriptor'](sys.orig_argv))
    resolver_fds = []
    for fd in range(3, 512):
        try:
            os.fstat(fd)
        except OSError as error:
            require(error.errno == errno.EBADF, 'Descriptor census failed')
        else:
            if fd not in allowed:
                require(resolver_descriptor(fd) is True, 'Unexpected post-exec descriptor')
                resolver_fds.append(fd)
    require(len(resolver_fds) <= 1, 'Duplicate public resolver descriptors')
    with socket.socket() as sock:
        sock.settimeout(1)
        require(sock.connect_ex(('192.0.2.1', 443)) == errno.ENETUNREACH, 'Outside route available')
    try:
        fd = os.open('/app/.write-refusal-control', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except PermissionError:
        pass
    else:
        os.close(fd)
        raise RuntimeError('App source write admitted')
    return dict(uid=UID, capabilities_zero=True, no_new_privileges=True,
                outside_content_denied=True, source_write_refused=True, outside_unreachable=True)


def stdio_boundary(*, log_name=None):
    require(log_name in (None, 'endpoint', 'wire'), 'Fixed private helper log required')
    incoming = os.fstat(0)
    require(stat.S_ISCHR(incoming.st_mode) and incoming.st_rdev == os.makedev(1, 3),
            'Real null stdin required')
    for fd in (1, 2):
        observed = os.fstat(fd)
        if log_name is None:
            require(stat.S_ISFIFO(observed.st_mode), 'Only ordinary stdout/stderr pipes admitted')
        else:
            path = Path('/evidence/' + log_name + '.log')
            expected = path.stat()
            require(not path.is_symlink() and stat.S_ISREG(observed.st_mode)
                    and observed.st_uid == os.getuid() and observed.st_nlink == 1
                    and stat.S_IMODE(observed.st_mode) == 0o600
                    and (observed.st_dev, observed.st_ino) == (expected.st_dev, expected.st_ino),
                    'Exact private helper log descriptor required')

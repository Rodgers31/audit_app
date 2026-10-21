"""Unprivileged, mountless confinement for this public synthetic image only.

Landlock denies content access outside a fixed allowlist; it does not hide path
metadata. A seccomp filter closes UNIX-socket and process/FD acquisition routes.
Both policies are inherited by exec and children, and refuse unsupported hosts.
"""
import ctypes
import errno
import os
from pathlib import Path
import platform
import stat

LIBC = ctypes.CDLL(None, use_errno=True)
FS_RIGHTS = (1 << 15) - 1  # ABI3+: includes REFER and TRUNCATE.
READ = (1 << 0) | (1 << 2) | (1 << 3)
WRITE = FS_RIGHTS & ~((1 << 0) | (1 << 6) | (1 << 9) | (1 << 11) | (1 << 12))
DIRECTORIES = ('/usr', '/app', '/fixture/tools/worker_rehearsal', '/host',
               '/etc/ssl', '/etc/alternatives')
FILES = ('/manifest.json', '/etc/b29-hosts', '/etc/nsswitch.conf',
         '/etc/ld.so.cache', '/etc/passwd', '/etc/group')
WRITABLE = ('/state', '/evidence', '/tmp', '/dev/shm')


def checked(value, name):
    if value < 0:
        raise OSError(ctypes.get_errno(), name)
    return value


def syscall_numbers(machine):
    if machine == 'x86_64':
        return 0xc000003e, 41, 53, (101, 310, 311, 438, 312, 298, 321,
            425, 426, 427, 323, 165, 166, 155, 161, 272, 308, 304,
            428, 429, 430, 431, 432, 433, 442)
    if machine == 'aarch64':
        return 0xc00000b7, 198, 199, (117, 270, 271, 438, 272, 241, 280,
            425, 426, 427, 282, 40, 39, 41, 51, 97, 268, 265,
            428, 429, 430, 431, 432, 433, 442)
    raise RuntimeError('Unsupported syscall architecture')


def instructions(machine):
    architecture, socket_nr, pair_nr, denied = syscall_numbers(machine)
    # LD.W.ABS, JEQ.K, RET.K, ALU.AND.K. All jumps are local and explicit.
    allow, refuse = 0x7fff0000, 0x00050000 | errno.EPERM
    result = [(0x20, 0, 0, 4), (0x15, 1, 0, architecture),
              (0x06, 0, 0, 0x80000000), (0x20, 0, 0, 0)]
    if machine == 'x86_64':
        result += [(0x45, 0, 1, 0x40000000), (0x06, 0, 0, refuse)]
    # libc can fall back from clone3 to clone. Refuse new namespaces while
    # retaining ordinary process/thread creation inside the inherited sandbox.
    result += [(0x15, 0, 1, 435), (0x06, 0, 0, 0x00050000 | 38)]  # Linux ENOSYS.
    result += [(0x15, 0, 4, 56 if machine == 'x86_64' else 220),
               (0x20, 0, 0, 16), (0x45, 0, 1, 0x7e020080),
               (0x06, 0, 0, refuse), (0x06, 0, 0, allow)]
    for number in denied:
        result += [(0x15, 0, 1, number), (0x06, 0, 0, refuse)]
    # socket: only IPv4/IPv6. The independent private NET namespace supplies
    # the routing boundary. No pathname UNIX client or packet/netlink socket.
    result += [(0x15, 0, 5, socket_nr), (0x20, 0, 0, 16),
               (0x15, 2, 0, 2), (0x15, 1, 0, 10),
               (0x06, 0, 0, refuse), (0x06, 0, 0, allow)]
    # Connected UNIX stream pairs are needed by asyncio wakeups. Datagram
    # pairs are refused because they can reconnect to external pathname peers.
    result += [(0x15, 0, 10, pair_nr), (0x20, 0, 0, 16),
               (0x15, 0, 7, 1), (0x20, 0, 0, 24),
               (0x45, 5, 0, (~(1 | 0x80000 | 0x800)) & 0xffffffff),
               (0x54, 0, 0, 15), (0x15, 0, 3, 1),
               (0x20, 0, 0, 32), (0x15, 0, 1, 0),
               (0x06, 0, 0, allow), (0x06, 0, 0, refuse), (0x06, 0, 0, allow)]
    return result


def restrict_syscalls():
    class Filter(ctypes.Structure):
        _fields_ = [('code', ctypes.c_ushort), ('jt', ctypes.c_ubyte),
                    ('jf', ctypes.c_ubyte), ('k', ctypes.c_uint)]
    class Program(ctypes.Structure):
        _fields_ = [('len', ctypes.c_ushort), ('filter', ctypes.POINTER(Filter))]
    rows = instructions(platform.machine())
    array = (Filter * len(rows))(*(Filter(*row) for row in rows))
    program = Program(len(rows), array)
    checked(LIBC.prctl(22, 2, ctypes.byref(program), 0, 0), 'install seccomp')
    return True


def restrict_filesystem(*, observer=False):
    if type(observer) is not bool:
        raise ValueError('Explicit observer mode required')
    class Ruleset(ctypes.Structure):
        _fields_ = [('handled_access_fs', ctypes.c_uint64)]
    class Rule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [('allowed_access', ctypes.c_uint64), ('parent_fd', ctypes.c_int32)]
    syscall_numbers(platform.machine())  # These syscall IDs are common to both.
    abi = checked(LIBC.syscall(444, None, 0, 1), 'query Landlock')
    if abi < 3:
        raise RuntimeError('Landlock ABI3 with truncate protection required')
    attr = Ruleset(FS_RIGHTS)
    ruleset = checked(LIBC.syscall(444, ctypes.byref(attr), ctypes.sizeof(attr), 0), 'create Landlock')
    try:
        entries = [(p, READ, True) for p in DIRECTORIES]
        entries += [(p, (1 << 2), False) for p in FILES]
        entries += [(p, WRITE, True) for p in (('/evidence',) if observer else WRITABLE)]
        if observer:
            entries += [(p, READ, True) for p in ('/proc', '/sys/fs/cgroup')]
        entries += [('/dev/null', (1 << 1) | (1 << 2), False)]
        for path, rights, directory in entries:
            # Fixed canonical build paths only. Do not silently follow a rule
            # root replaced by a link to a wider or credential-bearing tree.
            info = os.stat(path, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode) or (directory and not stat.S_ISDIR(info.st_mode)):
                raise RuntimeError('Fixed policy path changed')
            if not directory:
                valid = (stat.S_ISCHR(info.st_mode) and info.st_rdev == os.makedev(1, 3)
                         if path == '/dev/null' else stat.S_ISREG(info.st_mode))
                if not valid:
                    raise RuntimeError('Fixed policy leaf type changed')
            descriptor = os.open(path, os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                rule = Rule(rights, descriptor)
                checked(LIBC.syscall(445, ruleset, 1, ctypes.byref(rule), 0), 'add Landlock rule')
            finally:
                os.close(descriptor)
        checked(LIBC.syscall(446, ruleset, 0), 'enforce Landlock')
    finally:
        os.close(ruleset)
    return abi


def install(*, observer=False):
    if os.getuid() != 10001 or os.getgid() != 10001 or LIBC.prctl(39, 0, 0, 0, 0) != 1:
        raise RuntimeError('Unprivileged no-new-privileges boundary required')
    abi = restrict_filesystem(observer=observer)
    if restrict_syscalls() is not True:
        raise RuntimeError('Syscall confinement refused')
    return dict(kind='landlock-seccomp', abi=abi, path_metadata_visible=True)

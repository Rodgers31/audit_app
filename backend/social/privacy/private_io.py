"""Bounded private-file IO, refusing links/shared paths and acknowledging readback."""
import os
from pathlib import Path
import stat


def read_private(path, maximum):
    if type(path) is not type(Path()) or type(maximum) is not int or maximum < 1:
        raise ValueError('PRIVATE_FILE_REFUSED')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1 or not 0 < info.st_size <= maximum:
            raise ValueError('PRIVATE_FILE_REFUSED')
        raw = stream.read(maximum + 1)
    if not 0 < len(raw) <= maximum:
        raise ValueError('PRIVATE_FILE_REFUSED')
    return raw


def write_private(path, raw):
    if type(path) is not type(Path()) or type(raw) is not bytes or not raw:
        raise ValueError('PRIVATE_FILE_REFUSED')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    if read_private(path, len(raw)) != raw:
        raise ValueError('PRIVATE_FILE_REFUSED')

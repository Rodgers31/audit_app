"""Strict, append-only evidence primitives; no application imports or credentials."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat


class Refusal(ValueError):
    """An input cannot establish the requested evidence."""


def require(condition, reason):
    if not condition:
        raise Refusal(reason)


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads(raw):
    def invalid(value):
        raise Refusal(f"nonfinite JSON number: {value}")
    try:
        value = json.loads(raw, object_pairs_hook=object_pairs, parse_constant=invalid)
    except (ValueError, TypeError) as exc:
        raise Refusal(f"invalid JSON: {exc}") from exc
    def finite(item):
        if type(item) is float:
            require(math.isfinite(item), "nonfinite JSON number")
        elif type(item) is list:
            for member in item:
                finite(member)
        elif type(item) is dict:
            for member in item.values():
                finite(member)
    finite(value)
    return value


def read_json(path):
    return loads(Path(path).read_bytes())


def fields(value, keys):
    require(type(value) is dict and set(value) == set(keys), f"expected fields: {sorted(keys)}")


def string(value):
    require(type(value) is str and bool(value.strip()), "nonempty string required")
    return value


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, f"integer >= {minimum} required")
    return value


def digest(value, length=64):
    require(type(value) is str and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None,
            f"{length}-character hex digest required")
    return value


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def identity(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def publish(path, value):
    """Fresh external destinations are checked by callers before launching work."""
    path = Path(path)
    data = canonical(value) + b'\n'
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
    # Equality alone lets False equal 0. Compare canonical serialized primitives.
    require(canonical(read_json(path)) == canonical(value), "receipt disk readback differs")
    return sha256(path)


class BoundEvidence:
    """Read original regular files through retained no-follow directory descriptors.

    Consumers use the returned bytes, then recheck every original pathname before
    returning a verdict. A same-byte inode replacement is still a substitution.
    Existing lightweight common APIs remain unchanged for runtime consumers.
    """

    def __init__(self, maximum_bytes=64 * 1024 * 1024):
        integer(maximum_bytes, 1)
        self.maximum_bytes = maximum_bytes
        self.directories = []
        self.files = []

    def __enter__(self):
        return self

    @staticmethod
    def _identity(info):
        return (info.st_dev, info.st_ino, info.st_mode)

    @staticmethod
    def _file_identity(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def read(self, path):
        raw = os.fspath(path)
        require(type(raw) is str and raw and '\x00' not in raw, 'original path required')
        # Do not resolve: it erases the aliases this boundary must reject.
        require('..' not in raw.split('/') and '.' not in raw.split('/')
                and '//' not in raw, 'original path alias/traversal refused')
        path = Path(raw).absolute()
        parent = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.directories.append((parent, None, None, self._identity(os.fstat(parent))))
        try:
            for part in path.parts[1:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                self.directories.append((child, parent, part, self._identity(os.fstat(child))))
                parent = child
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except OSError as exc:
            raise Refusal('original evidence symlink/absent directory or file') from exc
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                    'original evidence must be regular and have no hardlink alias')
            require(before.st_size <= self.maximum_bytes, 'original evidence byte ceiling')
            chunks, size = [], 0
            while True:
                block = os.read(fd, min(1024 * 1024, self.maximum_bytes + 1 - size))
                if not block:
                    break
                chunks.append(block); size += len(block)
                require(size <= self.maximum_bytes, 'original evidence byte ceiling')
            require(size == before.st_size and self._file_identity(os.fstat(fd)) == self._file_identity(before),
                    'original evidence changed during read')
            data = b''.join(chunks)
            self.files.append((fd, parent, path.name, self._file_identity(before),
                               hashlib.sha256(data).digest()))
            return data
        except BaseException:
            os.close(fd)
            raise

    def json(self, path):
        return loads(self.read(path))

    def check(self):
        try:
            def bindings():
                for fd, parent, name, expected in self.directories:
                    actual = os.fstat(fd) if parent is None else os.stat(name, dir_fd=parent, follow_symlinks=False)
                    require(self._identity(actual) == expected, 'original evidence directory binding changed/substituted')
                for fd, parent, name, expected, checksum in self.files:
                    require(self._file_identity(os.fstat(fd)) == expected
                            and self._file_identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected,
                            'original evidence file binding changed/substituted')
            bindings()
            for fd, parent, name, expected, checksum in self.files:
                os.lseek(fd, 0, os.SEEK_SET)
                hasher = hashlib.sha256()
                size = 0
                # Stop at one byte beyond the original size, even if a writer
                # grows the regular file after the metadata precheck.
                while True:
                    block = os.read(fd, min(1024 * 1024, expected[4] + 1 - size))
                    if not block:
                        break
                    size += len(block)
                    require(size <= expected[4], 'original evidence changed through consumption')
                    hasher.update(block)
                require(size == expected[4] and hasher.digest() == checksum
                        and self._file_identity(os.fstat(fd)) == expected,
                        'original evidence changed through consumption')
            # A late ancestor/leaf substitution must not survive the last read.
            bindings()
        except OSError as exc:
            raise Refusal('original evidence binding changed/substituted') from exc

    def __exit__(self, kind, value, traceback):
        try:
            if kind is None:
                self.check()
        finally:
            for fd, *_ in reversed(self.files): os.close(fd)
            for fd, *_ in reversed(self.directories): os.close(fd)

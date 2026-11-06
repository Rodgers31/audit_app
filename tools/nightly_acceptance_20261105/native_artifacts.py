"""Verify an offline, reviewed Debian artifact set before a local native build.

The lock producer must retain Debian's signed metadata and successful signature
verification. Hash integrity here does not substitute for signature/advisory
review, independent corpus qualification, or approval of a platform change.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlsplit

sys.dont_write_bytecode = True
from common import Refusal, digest, fields, identity, integer, loads, require, sha256, string
from native_environment import regular


def file_binding(value):
    # Reading may update atime; inode/content metadata must remain unchanged.
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def verify_native_assets(lock_path, directory):
    raw_lock = regular(lock_path).read_bytes()
    lock_sha256 = hashlib.sha256(raw_lock).hexdigest()
    lock = loads(raw_lock)
    fields(lock, ('schema', 'base_image', 'packages', 'repository_metadata'))
    require(lock['schema'] == 'ingestion-native-artifacts-v1', 'unknown native artifact lock')
    require(re.fullmatch(r'docker\.io/library/python@sha256:[0-9a-f]{64}',
                         string(lock['base_image'])) is not None, 'digest-bound base required')
    require(type(lock['packages']) is list and bool(lock['packages']), 'empty native package set')
    require(type(lock['repository_metadata']) is dict and bool(lock['repository_metadata']),
            'signed repository provenance missing')
    for name, checksum in lock['repository_metadata'].items():
        require(type(name) is str and name and str(Path(name)) == name
                and not Path(name).is_absolute() and '..' not in Path(name).parts,
                'invalid repository metadata path')
        digest(checksum)
    root = Path(directory).absolute()
    require(all(not p.is_symlink() for p in (root, *root.parents)) and root.is_dir(),
            'owned native artifact directory required')
    filenames, names, total = set(), set(), 0
    for package in lock['packages']:
        fields(package, ('name', 'version', 'architecture', 'filename', 'url', 'sha256', 'size'))
        require(re.fullmatch(r'[a-z0-9][a-z0-9+.-]+', string(package['name'])) is not None
                and package['name'] not in names, 'invalid/duplicate native package')
        names.add(package['name'])
        string(package['version'])
        require(package['architecture'] in ('amd64', 'all'), 'wrong native package architecture')
        filename = string(package['filename'])
        require(Path(filename).name == filename and filename.endswith('.deb')
                and filename not in filenames, 'invalid/duplicate native artifact filename')
        filenames.add(filename)
        url = urlsplit(string(package['url']))
        require(url.scheme == 'https' and url.hostname == 'deb.debian.org'
                and url.port in (None, 443) and not url.username and not url.password
                and not url.query and not url.fragment
                and url.path.startswith(('/debian/pool/', '/debian-security/pool/')),
                'nonofficial native artifact URL')
        size = integer(package['size'], 1)
        require(size <= 96 * 1024**2, 'native artifact file byte ceiling')
        total += size
        path = regular(root / filename)
        before = path.stat()
        require(before.st_size == size and sha256(path) == digest(package['sha256']),
                'native artifact bytes differ')
        require(file_binding(path.stat()) == file_binding(before),
                'native artifact changed during verification')
    require(total <= 256 * 1024**2, 'native artifact total byte ceiling')
    require({p.name for p in root.iterdir()} == filenames, 'native artifacts incomplete/extra')
    return {'schema': 'ingestion-native-artifact-integrity-v1',
            'lock_sha256': lock_sha256, 'package_count': len(names), 'bytes': total,
            'package_set_sha256': identity(lock['packages']),
            'verdict': 'OFFLINE_ARTIFACT_BYTES_VERIFIED_ADVISORY_AND_RUNTIME_REVIEW_SEPARATE'}


def snapshot_native_assets(lock, directory, destination):
    """Capture authenticated bytes in a fresh private build input directory.

    The caller first validates the lock. Original artifact paths are never
    mounted into an installer: a later source mutation cannot execute there.
    """
    root = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    destination = Path(destination)
    try:
        require(set(os.listdir(root)) == {p['filename'] for p in lock['packages']},
                'native source inventory changed')
        destination.mkdir(mode=0o700)
        for package in lock['packages']:
            source = os.open(package['filename'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
            try:
                before = os.fstat(source)
                require(stat.S_ISREG(before.st_mode) and before.st_size == package['size']
                        and before.st_nlink == 1, 'native source file binding differs')
                checksum, size = hashlib.sha256(), 0
                target = destination / package['filename']
                with target.open('xb') as output:
                    while True:
                        block = os.read(source, min(1024**2, package['size'] + 1 - size))
                        if not block:
                            break
                        size += len(block)
                        require(size <= package['size'], 'native source grew during capture')
                        checksum.update(block)
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
                    os.fchmod(output.fileno(), 0o400)
                require(file_binding(os.fstat(source)) == file_binding(before) and size == package['size']
                        and checksum.hexdigest() == package['sha256'], 'native source changed during capture')
            finally:
                os.close(source)
        destination.chmod(0o500)
    finally:
        os.close(root)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    try:
        import json
        print(json.dumps(verify_native_assets(args.lock, args.directory), sort_keys=True))
    except (Refusal, OSError, ValueError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        sys.exit(1)

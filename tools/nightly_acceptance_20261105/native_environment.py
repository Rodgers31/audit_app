"""Additive controlled-rootfs verification; runtime.py's v1 contract is unchanged.

The caller must launch the digest-bound image from the reviewed environment
manifest. This helper verifies the executable environment within that boundary;
it does not attest the host/container engine or grant production admission.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from common import Refusal, digest, fields, identity, loads, read_json, require, sha256
import runtime

JOBS = ('migrate', 'bootstrap', 'seed', 'validate')
OVERRIDES = ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'PYTHONPATH', 'PYTHONHOME',
             'TESSDATA_PREFIX', 'JAVA_HOME', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS',
             'JDK_JAVA_OPTIONS', 'POPPLER_PATH', 'GCONV_PATH', 'LOCPATH', 'GLIBC_TUNABLES')
OVERRIDE_PREFIXES = ('LD_', 'PYTHON', 'OPENSSL_', 'FONTCONFIG_', 'FC_', 'TESSDATA_', 'POPPLER_')
SAFE_PYTHON_ENVIRONMENT = {'PYTHONDONTWRITEBYTECODE': {'1'}, 'PYTHONHASHSEED': {'0'},
                           'PYTHONUNBUFFERED': {'1'}}


def regular(path):
    """Refuse aliases before consuming reviewed source artifacts."""
    path = Path(path).absolute()
    require('..' not in path.parts, 'environment artifact traversal')
    require(all(not p.is_symlink() for p in (path, *path.parents)),
            'environment artifact symlink')
    require(path.is_file(), 'environment artifact missing')
    return path


def member(root, name):
    require(type(name) is str and name and not name.startswith('/'),
            'relative environment artifact required')
    require(str(Path(name)) == name and '..' not in Path(name).parts,
            'noncanonical environment artifact')
    return regular(root / name)


def bound_json(path, expected):
    raw = regular(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest(expected), 'reviewed artifact bytes differ')
    return loads(raw)


def _load_environment(path):
    path = regular(path)
    raw = path.read_bytes()
    manifest_sha256 = hashlib.sha256(raw).hexdigest()
    value = loads(raw)
    fields(value, ('schema', 'base_image', 'image_id', 'image_archive_sha256',
                   'native_lock_sha256', 'corpus_sha256', 'profiles', 'runtimes'))
    require(value['schema'] == 'controlled-ingestion-environment-v1',
            'unknown controlled environment schema')
    require(type(value['base_image']) is str and re.fullmatch(
        r'docker\.io/library/python@sha256:[0-9a-f]{64}', value['base_image']) is not None,
        'digest-bound official Python base required')
    require(type(value['image_id']) is str and value['image_id'].startswith('sha256:'),
            'exact image ID required')
    digest(value['image_id'][7:])
    for key in ('image_archive_sha256', 'native_lock_sha256', 'corpus_sha256'):
        digest(value[key])
    fields(value['profiles'], JOBS)
    for entry in value['profiles'].values():
        fields(entry, ('path', 'sha256'))
        profile = member(path.parent, entry['path'])
        profile_value = bound_json(profile, entry['sha256'])
        fields(profile_value, ('schema', 'native'))
        require(profile_value['schema'] == 'reviewed-ingestion-native-v1',
                'unknown reviewed native profile')
    # One shared approved native base is intentional for these four jobs.
    require(len({entry['sha256'] for entry in value['profiles'].values()}) == 1,
            'jobs must share the complete approved native base')
    fields(value['runtimes'], ('production', 'qualification'))
    observations = {}
    for role, entry in value['runtimes'].items():
        fields(entry, ('prefix', 'path', 'sha256'))
        require(entry['prefix'] == {'production': '/opt/ingestion',
                                    'qualification': '/opt/qualification'}[role],
                'fixed installation prefix required')
        expected = member(path.parent, entry['path'])
        observation = runtime.validate_runtime(bound_json(expected, entry['sha256']))
        observations[role] = observation
        require(observation['qualification'] == 'PYTHON_AND_REVIEWED_NATIVE',
                'complete reviewed native runtime required')
        lock = runtime.ROOT / ('backend/ingestion-runtime.lock.json' if role == 'production'
                               else 'backend/ingestion-qualification.lock.json')
        require(observation['lock_sha256'] == sha256(lock), 'wrong runtime artifact role')
        require(observation['native_profile_sha256'] in {
            entry['sha256'] for entry in value['profiles'].values()}, 'runtime/profile binding differs')
    return value, observations, manifest_sha256


def load_environment(path):
    return _load_environment(path)[0]


def verify_environment(path, job, role='production'):
    require(type(job) is str and job in JOBS, 'unknown ingestion job')
    require(type(role) is str and role in ('production', 'qualification'),
            'unknown ingestion runtime role')
    unsafe = [name for name, value in os.environ.items()
              if (name in OVERRIDES or name.startswith(OVERRIDE_PREFIXES))
              and value not in SAFE_PYTHON_ENVIRONMENT.get(name, set())]
    require(not unsafe,
            'ambient interpreter/native override refuses controlled verification')
    path = regular(path)
    environment, observations, manifest_sha256 = _load_environment(path)
    entry = environment['runtimes'][role]
    require(str(Path(sys.prefix).resolve()) == entry['prefix'], 'wrong installed runtime prefix')
    lock = runtime.ROOT / ('backend/ingestion-runtime.lock.json' if role == 'production'
                           else 'backend/ingestion-qualification.lock.json')
    profile = member(path.parent, environment['profiles'][job]['path'])
    actual = runtime.verify(lock, profile)
    expected = observations[role]
    require(identity(actual) == identity(expected), 'controlled executable runtime differs')
    return {'schema': 'controlled-ingestion-verification-v1', 'job': job, 'role': role,
            'environment_sha256': manifest_sha256, 'image_id': environment['image_id'],
            'runtime_sha256': identity(actual), 'runtime': actual,
            'verdict': 'LOCAL_CONTROLLED_RUNTIME_VERIFIED_NOT_PRODUCTION_ADMISSION'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', type=Path, required=True)
    parser.add_argument('--job', choices=JOBS, required=True)
    parser.add_argument('--role', choices=('production', 'qualification'), default='production')
    args = parser.parse_args()
    import json
    print(json.dumps(verify_environment(args.environment, args.job, args.role), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (Refusal, OSError, runtime.subprocess.SubprocessError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        sys.exit(1)

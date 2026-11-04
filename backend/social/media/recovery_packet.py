"""Explicit, bounded local custody publication; never a live CLI or authority.

Caller supplies the authorized read-only snapshot/storage, existing destination
and independently approved references. No connection, token, flag or policy is
created. Preserve incomplete publication on error; never overwrite or clean up.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID
from sqlalchemy import text

from .recovery import (RecoveryScopeError, _require, _scope_input, _decode_json, capture_stage_a_payloads,
    capture_stage_a_rows, encode_rows, verify_stage_a_payloads)

MAX_MANIFEST = 65536
MAX_PACKET = 720896
FILES = {'rows.json': 131072, 'quarantine.bin': 262144, 'original.bin': 262144}
HASH_CONTEXT = {'runtime_sha256', 'policy_sha256', 'decision_sha256',
    'writer_inventory_sha256', 'appointments_sha256', 'dependencies_sha256'}


def _hash(data):
    return hashlib.sha256(data).hexdigest()


@_scope_input
def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('ascii')


def _context(value):
    _require(type(value) is dict and set(value) == HASH_CONTEXT | {
        'source_commit', 'source_tree', 'schema_revision'})
    for key in HASH_CONTEXT | {'source_commit', 'source_tree'}:
        _require(type(value[key]) is str and re.fullmatch(
            '[0-9a-f]{64}' if key in HASH_CONTEXT else '[0-9a-f]{40}', value[key]) is not None)
    _require(type(value['schema_revision']) is str and re.fullmatch('[a-z0-9]{1,64}', value['schema_revision']) is not None)


def _source_snapshot(db):
    _require(db.in_transaction())
    if db.get_bind().dialect.name == 'sqlite':
        return {'dialect': 'sqlite_fixture', 'snapshot': None, 'consistency_proven': False,
            'observed_at': datetime.now(timezone.utc).isoformat()}
    _require(db.get_bind().dialect.name == 'postgresql')
    row = db.execute(text('''SELECT current_database(),current_schema(),current_user,
        pg_current_snapshot()::text,transaction_timestamp(),statement_timestamp(),
        current_setting('transaction_read_only'),current_setting('transaction_isolation'),
        current_setting('row_security')''')).one()
    _require(row[6:] == ('on', 'repeatable read', 'off'))
    return {'dialect': 'postgresql', 'database': row[0], 'schema': row[1], 'role': row[2],
        'snapshot': row[3], 'transaction_started_at': row[4].astimezone(timezone.utc).isoformat(),
        'observed_at': row[5].astimezone(timezone.utc).isoformat(),
        'read_only': True, 'isolation': row[7], 'row_security': row[8]}


def _validate_snapshot(value):
    _require(type(value) is dict)
    if value.get('dialect') == 'sqlite_fixture':
        _require(set(value) == {'dialect', 'snapshot', 'consistency_proven', 'observed_at'}
            and value['snapshot'] is None and value['consistency_proven'] is False)
    else:
        _require(set(value) == {'dialect', 'database', 'schema', 'role', 'snapshot',
            'transaction_started_at', 'observed_at', 'read_only', 'isolation', 'row_security'}
            and value['dialect'] == 'postgresql' and value['read_only'] is True
            and value['isolation'] == 'repeatable read' and value['row_security'] == 'off')
        _require(all(type(value[k]) is str and 1 <= len(value[k]) <= 128 for k in ('database', 'schema', 'role')))
        _require(type(value['snapshot']) is str and len(value['snapshot']) <= 8192
            and re.fullmatch('[0-9]+:[0-9]+:(?:[0-9]+(?:,[0-9]+)*)?', value['snapshot']) is not None)
    try:
        for key in ('observed_at', 'transaction_started_at'):
            if key in value:
                _require(type(value[key]) is str and datetime.fromisoformat(value[key]).utcoffset() is not None)
    except (ValueError, TypeError):
        raise RecoveryScopeError() from None


def _root(path):
    _require(isinstance(path, Path) and path.is_absolute() and path.resolve(strict=True) == path)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    value = os.fstat(fd)
    if not (stat.S_ISDIR(value.st_mode) and value.st_uid == os.getuid()
            and stat.S_IMODE(value.st_mode) == 0o700):
        os.close(fd)
        raise RecoveryScopeError()
    return fd


def _read(directory, name, maximum):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
            and before.st_uid == os.getuid() and stat.S_IMODE(before.st_mode) in {0o400, 0o600}
            and 1 <= before.st_size <= maximum)
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
        identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid,
            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        _require(len(data) == before.st_size and identity(before) == identity(after))
        return data


@_scope_input
def _load(raw):
    return _decode_json(raw)


@_scope_input
def read_stage_a_packet(root, custody_id, expected_manifest_sha256):
    """Read original custody bytes; expected outer hash comes from another record."""
    _require(type(custody_id) is UUID and type(expected_manifest_sha256) is str
        and re.fullmatch('[0-9a-f]{64}', expected_manifest_sha256) is not None)
    parent = _root(root)
    try:
        directory = os.open(str(custody_id), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            metadata = os.fstat(directory)
            _require(metadata.st_uid == os.getuid() and stat.S_IMODE(metadata.st_mode) == 0o700)
            _require(set(os.listdir(directory)) == set(FILES) | {'manifest.json'})
            raw = _read(directory, 'manifest.json', MAX_MANIFEST)
            _require(_hash(raw) == expected_manifest_sha256)
            manifest = _load(raw)
            _require(type(manifest) is dict and set(manifest) == {'schema_version', 'purpose',
                'custody_id', 'generated_at', 'generated_by', 'generator_sha256',
                'generator_hash_scope', 'execution_identity_authenticated', 'context',
                'source_snapshot', 'actor_id', 'asset_id', 'post_id', 'files', 'objects'})
            _require(type(manifest['schema_version']) is int and manifest['schema_version'] == 1
                and manifest['purpose'] == 'stage_a_private_media_recovery'
                and manifest['custody_id'] == str(custody_id)
                and manifest['execution_identity_authenticated'] is False
                and manifest['generator_hash_scope'] == 'observed_file_bytes_only'
                and manifest['generated_by'] == 'backend/social/media/recovery_packet.py')
            _context(manifest['context'])
            _validate_snapshot(manifest['source_snapshot'])
            try:
                _require(type(manifest['generated_at']) is str
                    and datetime.fromisoformat(manifest['generated_at']).utcoffset() is not None)
                _require(all(type(manifest[k]) is str and str(UUID(manifest[k])) == manifest[k]
                    for k in ('actor_id', 'asset_id', 'post_id')))
            except (ValueError, TypeError):
                raise RecoveryScopeError() from None
            _require(type(manifest['generator_sha256']) is str and re.fullmatch('[0-9a-f]{64}', manifest['generator_sha256']) is not None)
            _require(type(manifest['files']) is dict and set(manifest['files']) == set(FILES))
            contents = {name: _read(directory, name, cap) for name, cap in FILES.items()}
            _require(sum(map(len, contents.values())) + len(raw) <= MAX_PACKET)
            for name, content in contents.items():
                recorded = manifest['files'][name]
                _require(type(recorded) is dict and set(recorded) == {'size', 'sha256'}
                    and type(recorded['size']) is int and recorded['size'] == len(content)
                    and recorded['sha256'] == _hash(content))
            rows = _load(contents['rows.json'])
            encode_rows(rows)
            _require(len(rows['social_media_assets']) == 1 and len(rows['social_media_uploads']) == 1
                and len(rows['social_posts']) == 1)
            _require(type(manifest['objects']) is dict and set(manifest['objects']) == {'quarantine.bin', 'original.bin'})
            asset, upload = rows['social_media_assets'][0], rows['social_media_uploads'][0]
            _require(type(asset) is dict and type(upload) is dict
                and type(rows['social_posts'][0]) is dict
                and type(asset.get('codec_metadata')) is dict)
            _require(str(asset['id']) == manifest['asset_id'] and str(asset['created_by']) == manifest['actor_id']
                and str(rows['social_posts'][0]['id']) == manifest['post_id'])
            keys = {'quarantine.bin': upload['quarantine_key'], 'original.bin': asset['storage_key']}
            fence = _load(upload['retained_write_fence'])
            _require(type(fence) is dict and set(fence) == {
                'version', 'scope_hash', 'quarantine_etag', 'original_etag'})
            payloads = {}
            for name, key in keys.items():
                record = manifest['objects'][name]
                _require(type(record) is dict and set(record) == {'key', 'snapshot'} and record['key'] == key)
                snapshot = record['snapshot']
                _require(type(snapshot) is dict and set(snapshot) == {'size', 'etag', 'version', 'sha256', 'mime_type'}
                    and type(snapshot['size']) is int and snapshot['size'] == len(contents[name])
                    and snapshot['mime_type'] == 'image/jpeg'
                    and type(snapshot['etag']) is str and 1 <= len(snapshot['etag']) <= 1024
                    and (snapshot['version'] is None or type(snapshot['version']) is str and 1 <= len(snapshot['version']) <= 1024))
                if name == 'quarantine.bin':
                    _require(snapshot['etag'] == fence['quarantine_etag'])
                else:
                    _require(snapshot['etag'] == asset['codec_metadata']['storage_etag']
                        and snapshot['version'] == asset['codec_metadata'].get('storage_version')
                        and snapshot['sha256'] == asset['sha256'])
                payloads[key] = contents[name]
            verify_stage_a_payloads(rows, payloads)
            _require(set(os.listdir(directory)) == set(FILES) | {'manifest.json'})
            current = os.fstat(directory)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid,
                s.st_nlink, s.st_mtime_ns, s.st_ctime_ns)
            _require(identity(current) == identity(metadata))
            return contents['rows.json'], payloads, manifest
        finally:
            os.close(directory)
    finally:
        os.close(parent)


@_scope_input
def publish_stage_a_packet(db, storage, actor_id, asset_id, post_id, root, custody_id, context):
    """Future authorized capture to one fresh child of an existing private root.

    Hashes record file observations; the caller must independently bind executed
    producer/runtime bytes. This manifest explicitly supplies no authenticated
    execution, approval, legal custody or global writer-consistency verdict.
    """
    _require(type(custody_id) is UUID)
    _context(context)
    parent = _root(root)  # Validate destination before any DB/object read.
    try:
        _require(str(custody_id) not in os.listdir(parent))
        source_snapshot = _source_snapshot(db)
        _validate_snapshot(source_snapshot)
        rows = capture_stage_a_rows(db, actor_id, asset_id, post_id)
        payloads, snapshots = capture_stage_a_payloads(rows, storage)
        asset, upload = rows['social_media_assets'][0], rows['social_media_uploads'][0]
        keys = {'quarantine.bin': upload['quarantine_key'], 'original.bin': asset['storage_key']}
        contents = {'rows.json': encode_rows(rows), **{name: payloads[key] for name, key in keys.items()}}
        manifest = {'schema_version': 1, 'purpose': 'stage_a_private_media_recovery',
            'custody_id': str(custody_id), 'generated_at': datetime.now(timezone.utc).isoformat(),
            'generated_by': 'backend/social/media/recovery_packet.py',
            'generator_sha256': _hash(Path(__file__).read_bytes()),
            'generator_hash_scope': 'observed_file_bytes_only', 'execution_identity_authenticated': False,
            'source_snapshot': source_snapshot,
            'context': dict(context), 'actor_id': str(actor_id), 'asset_id': str(asset_id), 'post_id': str(post_id),
            'files': {name: {'size': len(data), 'sha256': _hash(data)} for name, data in contents.items()},
            'objects': {name: {'key': key, 'snapshot': snapshots[key]} for name, key in keys.items()}}
        raw = _canonical(manifest)
        _require(len(raw) <= MAX_MANIFEST and sum(map(len, contents.values())) + len(raw) <= MAX_PACKET)
        os.mkdir(str(custody_id), mode=0o700, dir_fd=parent)
        directory = os.open(str(custody_id), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            for name, data in {**contents, 'manifest.json': raw}.items():
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data); stream.flush(); os.fsync(stream.fileno())
                _require(_read(directory, name, MAX_MANIFEST if name == 'manifest.json' else FILES[name]) == data)
            os.fsync(directory)
        finally:
            os.close(directory)
        os.fsync(parent)
        # Cross the filesystem again using the externally retainable manifest hash.
        stored, copied, checked = read_stage_a_packet(root, custody_id, _hash(raw))
        _require(stored == contents['rows.json'] and copied == payloads and checked == manifest)
        return _hash(raw)
    finally:
        os.close(parent)

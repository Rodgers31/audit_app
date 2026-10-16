"""Private, signed, append-only external erasure intents for database restoration.

Caller supplies a separately held signing key and custody directory. Local fsync
proves local persistence only; off-host custody is a separate operator gate.
An intent must persist before any effect. Replay enforces already approved
suppression; matching a callback receipt never creates authority.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

MAX_BYTES = 512_000


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('PRIVACY_LEDGER_REFUSED')
        result[key] = value
    return result


def validate_intent(value):
    if (type(value) is not dict or set(value) != {'schema_version', 'operation_id', 'plan_id', 'plan_hash', 'policy_hash', 'scope'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1):
        raise ValueError('PRIVACY_LEDGER_REFUSED')
    for key in ('operation_id', 'plan_id'):
        if type(value[key]) is not str or str(UUID(value[key])) != value[key] or UUID(value[key]).int == 0:
            raise ValueError('PRIVACY_LEDGER_REFUSED')
    for key in ('plan_hash', 'policy_hash'):
        if type(value[key]) is not str or re.fullmatch('[a-f0-9]{64}', value[key]) is None:
            raise ValueError('PRIVACY_LEDGER_REFUSED')
    scope = value['scope']
    if type(scope) is not dict or set(scope) != {'credentials', 'flows', 'media_assets'} or not any(scope.values()):
        raise ValueError('PRIVACY_LEDGER_REFUSED')
    for key in scope:
        if type(scope[key]) is not list or len(scope[key]) > 100:
            raise ValueError('PRIVACY_LEDGER_REFUSED')
        seen = set()
        for entry in scope[key]:
            fields = {'id', 'version'} if key == 'credentials' else {'id', 'content_hash', 'identity_hash'} if key == 'flows' else {'id', 'scope_hash'}
            if type(entry) is not dict or set(entry) != fields or type(entry['id']) is not str:
                raise ValueError('PRIVACY_LEDGER_REFUSED')
            uid = UUID(entry['id'])
            if str(uid) != entry['id'] or uid.int == 0 or uid in seen:
                raise ValueError('PRIVACY_LEDGER_REFUSED')
            seen.add(uid)
            if key == 'credentials' and (type(entry['version']) is not int or not 0 < entry['version'] < 2**63):
                raise ValueError('PRIVACY_LEDGER_REFUSED')
            if key == 'media_assets' and (type(entry['scope_hash']) is not str or re.fullmatch('[a-f0-9]{64}', entry['scope_hash']) is None):
                raise ValueError('PRIVACY_LEDGER_REFUSED')
            if key == 'flows' and any(type(entry[field]) is not str or re.fullmatch('[a-f0-9]{64}', entry[field]) is None for field in ('content_hash','identity_hash')):
                raise ValueError('PRIVACY_LEDGER_REFUSED')
    if len(canonical(value)) > MAX_BYTES:
        raise ValueError('PRIVACY_LEDGER_REFUSED')
    return value


def verify_entry(raw, public_key):
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BYTES or type(public_key) is not bytes or len(public_key) != 32:
            raise ValueError()
        value = json.loads(raw, object_pairs_hook=_pairs)
        if type(value) is not dict or set(value) != {'intent', 'signature', 'generated_by', 'generator_sha256', 'generated_at'} or type(value['signature']) is not str:
            raise ValueError()
        intent = validate_intent(value['intent'])
        if value['generated_by'] != 'backend/social/privacy/deletion_ledger.py' or type(value['generator_sha256']) is not str or re.fullmatch('[a-f0-9]{64}', value['generator_sha256']) is None or type(value['generated_at']) is not str:
            raise ValueError()
        datetime.fromisoformat(value['generated_at'].replace('Z', '+00:00'))
        body = {k: v for k, v in value.items() if k != 'signature'}
        Ed25519PublicKey.from_public_bytes(public_key).verify(bytes.fromhex(value['signature']), canonical(body))
        return intent
    except Exception:
        pass
    raise ValueError('PRIVACY_LEDGER_REFUSED')


class FileDeletionLedger:
    def __init__(self, directory: Path, signing_key: bytes):
        if type(directory) is not type(Path()) or type(signing_key) is not bytes or len(signing_key) != 32:
            raise ValueError('PRIVACY_LEDGER_REFUSED')
        self.directory = directory
        self._key = Ed25519PrivateKey.from_private_bytes(signing_key)
        from cryptography.hazmat.primitives import serialization
        self.public_key = self._key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    def persist(self, intent):
        validate_intent(intent)
        # No recursive mkdir: custody location must already be provisioned.
        directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(directory)
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('PRIVACY_LEDGER_REFUSED')
            name = intent['operation_id'] + '.json'
            body = {'intent': intent, 'generated_by': 'backend/social/privacy/deletion_ledger.py',
                'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'generated_at': datetime.now(timezone.utc).isoformat()}
            raw = canonical(dict(body, signature=self._key.sign(canonical(body)).hex()))
            try:
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            except FileExistsError:
                fd = None
            if fd is not None:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.fsync(directory)
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_nlink != 1
                        or info.st_uid != os.getuid()):
                    raise ValueError('PRIVACY_LEDGER_REFUSED')
                actual = stream.read(MAX_BYTES + 1)
                os.fsync(stream.fileno())
            os.fsync(directory)
            if verify_entry(actual, self.public_key) != intent:
                raise ValueError('PRIVACY_LEDGER_REFUSED')
            return hashlib.sha256(actual).hexdigest()
        finally:
            os.close(directory)

    def read(self, operation_id):
        if type(operation_id) is not UUID or operation_id.int == 0:
            raise ValueError('PRIVACY_LEDGER_REFUSED')
        directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(directory)
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('PRIVACY_LEDGER_REFUSED')
            fd = os.open(str(operation_id) + '.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid() or info.st_nlink != 1:
                    raise ValueError('PRIVACY_LEDGER_REFUSED')
                intent = verify_entry(stream.read(MAX_BYTES + 1), self.public_key)
            if intent['operation_id'] != str(operation_id):
                raise ValueError('PRIVACY_LEDGER_REFUSED')
            return intent
        finally:
            os.close(directory)

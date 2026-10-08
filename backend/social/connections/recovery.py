"""Explicit credential-envelope recovery; no environment or provider access.

The caller owns secret-store authorization and lifecycle. File exports are
plaintext secret containers requiring a private encrypted storage location.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import stat
from uuid import UUID

from .crypto import CredentialCipher
from ..service import SocialError

MAX_BACKUP_BYTES = 65536
MAX_KEY_VERSIONS = 64
PURPOSES = frozenset(('facebook_user', 'facebook_page', 'oauth_start', 'oauth_pending'))


class RecoveryError(ValueError):
    def __init__(self):
        super().__init__('CREDENTIAL_RECOVERY_REFUSED')


@dataclass(frozen=True, repr=False)
class RecoveryKeyring:
    active_version: str
    keys: dict[str, str] = field(repr=False)

    def cipher(self):
        try:
            if (type(self.active_version) is not str or type(self.keys) is not dict
                    or not 1 <= len(self.keys) <= MAX_KEY_VERSIONS
                    or any(type(k) is not str or type(v) is not str for k, v in self.keys.items())):
                raise RecoveryError()
            return CredentialCipher(self.active_version, dict(self.keys))
        except (ValueError, TypeError, AttributeError, SocialError):
            pass
        raise RecoveryError()


@dataclass(frozen=True, repr=False)
class RecoveryProbe:
    owner: UUID
    purpose: str
    key_version: str
    ciphertext: bytes = field(repr=False)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryError()
        result[key] = value
    return result


def parse_keyring(raw: bytes) -> RecoveryKeyring:
    """Strict v1 backup contract; never interpret digest keys as envelope keys."""
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BACKUP_BYTES:
            raise RecoveryError()
        value = json.loads(raw, object_pairs_hook=_pairs)
        if (type(value) is not dict or set(value) != {'schema_version', 'purpose', 'active_version', 'keys'}
                or type(value['schema_version']) is not int or value['schema_version'] != 1
                or value['purpose'] != 'meta_credential_envelopes'
                or type(value['active_version']) is not str
                or type(value['keys']) is not dict or not 1 <= len(value['keys']) <= MAX_KEY_VERSIONS
                or any(type(k) is not str or type(v) is not str for k, v in value['keys'].items())):
            raise RecoveryError()
        ring = RecoveryKeyring(value['active_version'], dict(value['keys']))
        ring.cipher()
        return ring
    except (ValueError, TypeError, UnicodeError, RecursionError, SocialError):
        pass
    raise RecoveryError()


def encode_keyring(ring: RecoveryKeyring) -> bytes:
    """Returns secret bytes to an explicit caller; never log this result."""
    try:
        if type(ring) is not RecoveryKeyring:
            raise RecoveryError()
        ring.cipher()
        raw = json.dumps({'schema_version': 1, 'purpose': 'meta_credential_envelopes',
                          'active_version': ring.active_version, 'keys': dict(ring.keys)},
                         sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')
        parse_keyring(raw)
        return raw
    except (ValueError, TypeError, AttributeError, UnicodeError, SocialError):
        pass
    raise RecoveryError()


def read_keyring_backup(path: Path) -> RecoveryKeyring:
    """Bounded descriptor read, refusing symlinks, pipes and shared files.

    Parent directories must be operator-controlled; this is not a defense
    against a malicious process running as the same operating-system user.
    """
    fd = None
    try:
        if type(path) is not type(Path()) or not all(hasattr(os, v) for v in ('O_NOFOLLOW', 'O_NONBLOCK', 'getuid')):
            raise RecoveryError()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or info.st_mode & 0o077 or not 1 <= info.st_size <= MAX_BACKUP_BYTES):
            raise RecoveryError()
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            return parse_keyring(stream.read(MAX_BACKUP_BYTES + 1))
    except (OSError, ValueError, TypeError):
        pass
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass  # Preserve the sanitized refusal even if cleanup fails.
    raise RecoveryError()


def write_keyring_backup(path: Path, ring: RecoveryKeyring):
    """Exclusive private export, fsynced before success; never overwrites.

    Failure leaves no authoritative new backup. The existing ring remains
    authoritative. A storage controller must still verify off-host durability.
    """
    fd = None
    created = False
    try:
        raw = encode_keyring(ring)
        if type(path) is not type(Path()) or not hasattr(os, 'O_NOFOLLOW'):
            raise RecoveryError()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        created = True
        with os.fdopen(fd, 'wb') as stream:
            fd = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Synchronize the directory entry, not just the file contents.
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return
    except (OSError, ValueError, TypeError):
        pass
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
    if created:
        try:
            path.unlink()
        except OSError:
            pass  # A leftover is unverified and must never be activated.
    raise RecoveryError()


def verify_restoration(original: RecoveryKeyring, restored: RecoveryKeyring,
                       probes: list[RecoveryProbe]) -> dict:
    """Decrypt caller-supplied old envelopes with independent cipher instances.

    Comparing real clear bundles proves recoverability of these probes only.
    It does not establish database coverage, key custody or deployment safety.
    """
    try:
        if (type(original) is not RecoveryKeyring or type(restored) is not RecoveryKeyring
                or original is restored or original.keys is restored.keys
                or type(probes) is not list or not 1 <= len(probes) <= 100):
            raise RecoveryError()
        first, second = original.cipher(), restored.cipher()
        versions = set()
        for probe in probes:
            if (type(probe) is not RecoveryProbe or type(probe.owner) is not UUID
                    or type(probe.owner.int) is not int or not 0 < probe.owner.int < 2**128
                    or type(probe.purpose) is not str or probe.purpose not in PURPOSES
                    or type(probe.key_version) is not str or type(probe.ciphertext) is not bytes
                    or not 1 <= len(probe.ciphertext) <= 1_000_000):
                raise RecoveryError()
            expected = first.decrypt(probe.owner, probe.purpose, probe.key_version, probe.ciphertext)
            actual = second.decrypt(probe.owner, probe.purpose, probe.key_version, probe.ciphertext)
            if actual != expected:
                raise RecoveryError()
            versions.add(probe.key_version)
        return {'status': 'VERIFIED_BY_EXECUTION', 'scope': 'supplied_credential_envelopes',
                'envelopes_decrypted': len(probes), 'versions_decrypted': sorted(versions),
                'production_authorized': False, 'digest_keys_verified': False}
    except (SocialError, ValueError, TypeError, AttributeError):
        pass
    raise RecoveryError()

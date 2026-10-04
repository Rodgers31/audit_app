"""Versioned Fernet envelopes bound to their persisted owner and purpose."""
import json
import re
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from ..contracts import canonical_json
from ..service import SocialError


class CredentialCipher:
    def __init__(self, active_version: str, keys: dict[str, str]):
        try:
            if not keys or active_version not in keys or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', v) for v in keys):
                raise ValueError()
            self._keys = {version: Fernet(key.encode('ascii')) for version, key in keys.items()}
        except (ValueError, TypeError, AttributeError, UnicodeError):
            raise SocialError('ENCRYPTION_UNAVAILABLE', 'The stable social credential key ring is unavailable.', 503) from None
        self.active_version = active_version

    def encrypt(self, owner: UUID, purpose: str, bundle: dict):
        envelope = {'schema_version': 1, 'owner_id': str(owner), 'provider': 'meta', 'purpose': purpose, 'bundle': bundle}
        return self.active_version, self._keys[self.active_version].encrypt(canonical_json(envelope).encode())

    def decrypt(self, owner: UUID, purpose: str, key_version: str, ciphertext: bytes):
        try:
            key = self._keys[key_version]
            value = json.loads(key.decrypt(ciphertext))
            if set(value) != {'schema_version', 'owner_id', 'provider', 'purpose', 'bundle'} or type(value['schema_version']) is not int or value['schema_version'] != 1 or value['owner_id'] != str(owner) or value['provider'] != 'meta' or value['purpose'] != purpose or not isinstance(value['bundle'], dict):
                raise ValueError()
            return value['bundle']
        except (KeyError, InvalidToken, ValueError, TypeError, UnicodeError):
            raise SocialError('CREDENTIAL_UNREADABLE', 'This credential cannot be verified with the configured key ring. Restore the required key or reconnect.', 503) from None

    def rotate(self, owner: UUID, purpose: str, version: str, ciphertext: bytes):
        return self.encrypt(owner, purpose, self.decrypt(owner, purpose, version, ciphertext))

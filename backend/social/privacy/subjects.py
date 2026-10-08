"""Separate injected digest keys. No environment, cipher or key generation."""
import hashlib
import hmac
import re
from types import MappingProxyType


class SubjectKeyError(ValueError):
    def __init__(self):
        super().__init__('PRIVACY_SUBJECT_KEYS_UNAVAILABLE')


class SubjectDigester:
    def __init__(self, active_version, keys):
        if (type(keys) is not dict or not 1 <= len(keys) <= 16
                or type(active_version) is not str or active_version not in keys
                or any(type(v) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', v)
                       or type(k) is not bytes or len(k) != 32 for v, k in keys.items())):
            raise SubjectKeyError()
        self.active_version = active_version
        self.keys = MappingProxyType(dict(keys))

    def __repr__(self):
        return 'SubjectDigester(<redacted>)'

    def digest(self, app_id, subject, version=None):
        version = self.active_version if version is None else version
        if (type(app_id) is not str or not re.fullmatch(r'[1-9][0-9]{0,63}', app_id)
                or type(subject) is not str or not re.fullmatch(r'[1-9][0-9]{0,63}', subject)
                or type(version) is not str or version not in self.keys):
            raise SubjectKeyError()
        return hmac.new(self.keys[version], ('meta-asid-v1\0' + app_id + '\0' + subject).encode('ascii'), hashlib.sha256).hexdigest()

    def candidates(self, app_id, subject):
        return tuple((version, self.digest(app_id, subject, version)) for version in sorted(self.keys))

"""Default-off assembly for signed privacy ingress on the existing API service.

No key generation, dotenv loading, provider calls, worker, or publishing adapter.
Existing callback receipt semantics remain pending review, never deletion complete.
"""
import base64
import binascii
import json
import os

from ..connections.crypto import CredentialCipher
from ..service import SocialError
from .runtime import PrivacyRegistration, install_privacy
from .service import PrivacyConfig
from .subjects import SubjectDigester


MESSAGE = 'Explicit Meta privacy configuration is required before enabling callbacks or connections.'


def _object(value, maximum):
    if type(value) is not str or not 1 <= len(value) <= 65536:
        raise ValueError()

    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError()
            result[key] = item
        return result

    result = json.loads(value, object_pairs_hook=unique)
    if (type(result) is not dict or not 1 <= len(result) <= maximum
            or any(type(k) is not str or type(v) is not str for k, v in result.items())):
        raise ValueError()
    return result


def _key(value):
    if len(value) != 44:
        raise ValueError()
    key = base64.b64decode(value, altchars=b'-_', validate=True)
    if len(key) != 32 or base64.urlsafe_b64encode(key).decode('ascii') != value:
        raise ValueError()
    return key


def configure_meta_privacy(app, session_factory, environ=None):
    """Install only explicitly enabled, fully validated privacy dependencies.

    A connection opt-in without privacy indexing refuses application startup.
    Privacy ingress remains independent so disabling new OAuth flows does not
    disable requests concerning existing grants. Validation performs no I/O.
    """
    # Privacy capabilities must also be redacted on disabled/unmatched routes.
    from .access_logs import install_private_access_filter
    install_private_access_filter()
    values = os.environ if environ is None else environ
    registration = None
    try:
        privacy = values.get('META_PRIVACY_ENABLED', 'false')
        connections = values.get('META_CONNECTIONS_ENABLED', 'false')
        if privacy not in ('true', 'false') or connections not in ('true', 'false'):
            raise ValueError()
        if privacy == 'false':
            if connections == 'true':
                raise ValueError()
            return None
        envelope_keys = _object(values.get('SOCIAL_CREDENTIAL_KEYS'), 64)
        digest_keys = _object(values.get('META_PRIVACY_SUBJECT_KEYS'), 16)
        raw_envelopes = {_key(key) for key in envelope_keys.values()}
        raw_digests = {version: _key(key) for version, key in digest_keys.items()}
        if raw_envelopes.intersection(raw_digests.values()):
            raise ValueError()  # Subject lookup and credential encryption use separate keys.
        registration = PrivacyRegistration(
            PrivacyConfig(values.get('META_APP_ID'), values.get('META_APP_SECRET'),
                          values.get('META_PRIVACY_STATUS_URL'), enabled=True),
            SubjectDigester(values.get('META_PRIVACY_SUBJECT_ACTIVE_KEY_VERSION'), raw_digests),
            CredentialCipher(values.get('SOCIAL_CREDENTIAL_ACTIVE_KEY_VERSION'), envelope_keys),
            session_factory,
        )
        registration.validate()
    except (ValueError, TypeError, AttributeError, UnicodeError, binascii.Error, SocialError):
        pass
    else:
        # No partial app mutation if validation fails. Duplicate registration
        # keeps install_privacy's existing explicit refusal rather than replacing it.
        install_privacy(app, registration)
        return registration
    # Outside the decoder/validator handler: do not retain secret-bearing context.
    raise SocialError('PRIVACY_CONFIGURATION_INVALID', MESSAGE, 503)

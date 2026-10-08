"""Recovery failures must not retain decoder objects or untrusted versions."""
import base64
from uuid import UUID

import pytest

from social.connections.crypto import CredentialCipher
from social.service import SocialError

KEY = base64.urlsafe_b64encode(bytes(range(32))).decode('ascii')
OWNER = UUID('11111111-1111-4111-8111-111111111111')


def test_recovery_bad_key_drops_secret_decoder_context():
    marker = 'fixture-private-key-\N{LATIN SMALL LETTER E WITH ACUTE}'
    with pytest.raises(SocialError) as failure:
        CredentialCipher('v1', {'v1': marker})
    assert failure.value.code == 'ENCRYPTION_UNAVAILABLE'
    assert failure.value.__context__ is None
    assert failure.value.__cause__ is None


def test_recovery_unknown_version_drops_untrusted_context():
    cipher = CredentialCipher('v1', {'v1': KEY})
    _, data = cipher.encrypt(OWNER, 'facebook_page', {'access_token': 'fixture-token'})
    with pytest.raises(SocialError) as failure:
        cipher.decrypt(OWNER, 'facebook_page', 'fixture-private-version', data)
    assert failure.value.code == 'CREDENTIAL_UNREADABLE'
    assert failure.value.__context__ is None
    assert failure.value.__cause__ is None

"""Recovery verification must use separately reconstructed input containers."""
from dataclasses import replace

import pytest

from social.connections.recovery import RecoveryError, parse_keyring, encode_keyring, verify_restoration
from test_connections_recovery import ring, probe


@pytest.mark.parametrize('alias', ['ring', 'mapping'])
def test_recovery_refuses_aliased_original_and_restored_inputs(ring, alias):
    restored = ring if alias == 'ring' else replace(ring)
    with pytest.raises(RecoveryError) as caught:
        verify_restoration(ring, restored, [probe(ring)])
    assert caught.value.__context__ is None


def test_independently_reconstructed_backup_still_verifies(ring):
    restored = parse_keyring(encode_keyring(ring))
    assert restored is not ring and restored.keys is not ring.keys
    result = verify_restoration(ring, restored, [probe(ring)])
    assert result['status'] == 'VERIFIED_BY_EXECUTION'
    assert result['production_authorized'] is False

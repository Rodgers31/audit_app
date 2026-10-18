"""Real retained envelopes, historical ownership and transactional rotation failures."""
from uuid import uuid4
from cryptography.fernet import Fernet
import pytest
from sqlalchemy import event, select
from social.connections.crypto import CredentialCipher
from social.connections.rotation import rotate_retained_envelopes
from social.connections.models import SocialCredential, SocialOAuthFlow
from social.privacy.models import SocialPrivacyOwnership
from test_privacy_support import config, db, graph, connected, connection, start


def test_full_rotation_pending_flows_preserves_generation_and_restart_reads(db, config, graph):
    connected(db, config, graph)
    start(connection(db, config, graph))
    old=CredentialCipher(config.active_key_version,config.encryption_keys)
    candidate=CredentialCipher('next',dict(config.encryption_keys, next=Fernet.generate_key().decode()))
    with db.begin():
        before={c.id:(c.version,old.decrypt(c.id,c.credential_kind,c.key_version,c.encrypted_bundle)) for c in db.scalars(select(SocialCredential))}
        owners=[o.reference_key for o in db.scalars(select(SocialPrivacyOwnership))]
    result=rotate_retained_envelopes(db,old_cipher=old,candidate_cipher=candidate)
    assert result['envelopes_rotated']>=3 and result['retirement_authorized'] is False
    db.expire_all()
    with db.begin():
        for c in db.scalars(select(SocialCredential)):
            assert c.key_version=='next' and (c.version,candidate.decrypt(c.id,c.credential_kind,c.key_version,c.encrypted_bundle))==before[c.id]
        assert [o.reference_key for o in db.scalars(select(SocialPrivacyOwnership))]==owners
        for flow in db.scalars(select(SocialOAuthFlow)):
            if flow.encrypted_verifier:
                candidate.decrypt(flow.id,'oauth_start',flow.key_version,flow.encrypted_verifier)


def test_rotation_failure_rolls_back_every_envelope(db,config,graph):
    connected(db,config,graph)
    old=CredentialCipher(config.active_key_version,config.encryption_keys)
    candidate=CredentialCipher('next',dict(config.encryption_keys,next=Fernet.generate_key().decode()))
    with db.begin():
        before={c.id:bytes(c.encrypted_bundle) for c in db.scalars(select(SocialCredential))}
    def fail(*args): raise OSError('synthetic fsync/commit failure')
    event.listen(db,'before_commit',fail)
    try:
        with pytest.raises(OSError):rotate_retained_envelopes(db,old_cipher=old,candidate_cipher=candidate)
    finally:event.remove(db,'before_commit',fail)
    with db.begin():
        assert {c.id:bytes(c.encrypted_bundle) for c in db.scalars(select(SocialCredential))}==before

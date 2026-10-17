"""Explicit bounded transactional rotation; never retires keys or rewrites history."""
from sqlalchemy import select
from .models import SocialCredential, SocialOAuthFlow
from .service import ConnectionService
from ..service import SocialError


def rotate_retained_envelopes(db, *, old_cipher, candidate_cipher, maximum=1000):
    if type(maximum) is not int or not 1 <= maximum <= 1000 or old_cipher.active_version == candidate_cipher.active_version:
        raise SocialError('ROTATION_REFUSED', 'An explicit new active key and bounded inventory are required.', 409)
    with db.begin():
        controls = ConnectionService(db, None)._controls_lock()
        if controls.publishing_enabled is not False:
            raise SocialError('ROTATION_PAUSE_REQUIRED', 'Pause publishing before rotating retained envelopes.', 409)
        credentials = db.scalars(select(SocialCredential).order_by(SocialCredential.id).limit(maximum + 1).with_for_update().execution_options(populate_existing=True)).all()
        flows = db.scalars(select(SocialOAuthFlow).order_by(SocialOAuthFlow.id).limit(maximum + 1).with_for_update().execution_options(populate_existing=True)).all()
        if len(credentials) + len(flows) > maximum or any(c.refresh_lease_token for c in credentials) or any(f.status == 'exchanging' for f in flows):
            raise SocialError('ROTATION_REFUSED', 'An inventory bound or active operation prevents rotation.', 409)
        count = 0
        expected = []
        for row in credentials:
            bundle = old_cipher.decrypt(row.id, row.credential_kind, row.key_version, row.encrypted_bundle)
            if candidate_cipher.decrypt(row.id, row.credential_kind, row.key_version, row.encrypted_bundle) != bundle:
                raise SocialError('ROTATION_REFUSED', 'Candidate history continuity is unavailable.', 409)
            version, encrypted = candidate_cipher.encrypt(row.id, row.credential_kind, bundle)
            if candidate_cipher.decrypt(row.id, row.credential_kind, version, encrypted) != bundle:
                raise SocialError('ROTATION_REFUSED', 'Candidate readback failed.', 409)
            row.key_version, row.encrypted_bundle = version, encrypted
            expected.append((row, 'encrypted_bundle', row.credential_kind, version, encrypted, bundle))
            count += 1
        for row in flows:
            for field, purpose in (('encrypted_verifier', 'oauth_start'), ('encrypted_pending_grant', 'oauth_pending')):
                encrypted = getattr(row, field)
                if encrypted is not None:
                    bundle = old_cipher.decrypt(row.id, purpose, row.key_version, encrypted)
                    if candidate_cipher.decrypt(row.id, purpose, row.key_version, encrypted) != bundle:
                        raise SocialError('ROTATION_REFUSED', 'Candidate history continuity is unavailable.', 409)
                    version, encrypted = candidate_cipher.encrypt(row.id, purpose, bundle)
                    if candidate_cipher.decrypt(row.id, purpose, version, encrypted) != bundle:
                        raise SocialError('ROTATION_REFUSED', 'Candidate readback failed.', 409)
                    row.key_version = version
                    setattr(row, field, encrypted)
                    expected.append((row, field, purpose, version, encrypted, bundle))
                    count += 1
        db.flush()
        if db.bind.dialect.name == 'postgresql':
            from sqlalchemy import text
            db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
        for row, field, purpose, version, encrypted, bundle in expected:
            db.refresh(row)
            if row.key_version != version or getattr(row, field) != encrypted or candidate_cipher.decrypt(row.id, purpose, row.key_version, getattr(row, field)) != bundle:
                raise SocialError('ROTATION_PERSISTENCE_UNCONFIRMED', 'Stored envelopes differ; rotation was rolled back.', 503)
    return {'status': 'ROTATED', 'envelopes_rotated': count, 'retirement_authorized': False,
            'retained_history': 'privacy_confirmation_envelopes_and_all_backups_require_old_keys'}

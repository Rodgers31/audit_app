"""Additive models. The integrator owns the single Alembic migration and RLS."""
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, LargeBinary, String, Text, UniqueConstraint, Uuid
from ..models import Base, TZ, created, uid, updated


class SocialCredential(Base):
    __tablename__ = 'social_credentials'
    id = uid()
    provider = Column(Text, nullable=False, default='meta')
    credential_kind = Column(Text, nullable=False)
    parent_credential_id = Column(Uuid(as_uuid=True), ForeignKey('social_credentials.id'))
    encrypted_bundle = Column(LargeBinary, nullable=False)
    key_version = Column(Text, nullable=False)
    access_expires_at = Column(TZ)
    refresh_expires_at = Column(TZ)  # Meta Facebook Login does not issue a refresh token.
    data_access_expires_at = Column(TZ)
    version = Column(BigInteger, nullable=False, default=1, server_default='1')
    refresh_lease_token = Column(Uuid(as_uuid=True))
    refresh_lease_expires_at = Column(TZ)
    last_refresh_at = Column(TZ)
    revoked_at = Column(TZ)
    created_at = created()
    updated_at = updated()
    __table_args__ = (
        CheckConstraint("provider = 'meta' AND credential_kind IN ('facebook_user','facebook_page')", name='ck_social_credential_kind'),
        CheckConstraint("(credential_kind = 'facebook_user' AND parent_credential_id IS NULL) OR (credential_kind = 'facebook_page' AND parent_credential_id IS NOT NULL)", name='ck_social_credential_parent'),
        CheckConstraint('version > 0 AND length(encrypted_bundle) > 0 AND length(key_version) > 0', name='ck_social_credential_envelope'),
        CheckConstraint('(refresh_lease_token IS NULL) = (refresh_lease_expires_at IS NULL)', name='ck_social_credential_lease'),
        CheckConstraint('refresh_expires_at IS NULL', name='ck_social_meta_no_refresh'),
        Index('ix_social_credential_access_expiry', 'access_expires_at'),
        Index('ix_social_credential_data_expiry', 'data_access_expires_at'),
        Index('ix_social_credential_parent', 'parent_credential_id'),
    )


class SocialOAuthFlow(Base):
    __tablename__ = 'social_oauth_flows'
    id = uid()
    actor_id = Column(Uuid(as_uuid=True), nullable=False)
    provider = Column(Text, nullable=False, default='meta')
    state_hash = Column(String(64), nullable=False, unique=True)
    binding_hash = Column(String(64), nullable=False)
    encrypted_verifier = Column(LargeBinary)  # Encrypted start nonce for idempotent start response.
    encrypted_pending_grant = Column(LargeBinary)
    key_version = Column(Text, nullable=False)
    redirect_uri = Column(Text, nullable=False)
    return_path = Column(Text, nullable=False, default='/admin/social/accounts')
    reconnect_account_id = Column(Uuid(as_uuid=True), ForeignKey('social_accounts.id'))
    status = Column(Text, nullable=False, default='initiated')
    expires_at = Column(TZ, nullable=False)
    consumed_at = Column(TZ)
    created_at = created()
    updated_at = updated()
    __table_args__ = (
        CheckConstraint("provider = 'meta' AND status IN ('initiated','exchanging','awaiting_selection','completed','failed','expired')", name='ck_social_oauth_status'),
        CheckConstraint('length(state_hash) = 64 AND length(binding_hash) = 64', name='ck_social_oauth_hashes'),
        CheckConstraint("return_path = '/admin/social/accounts'", name='ck_social_oauth_return'),
        CheckConstraint("(status = 'initiated' AND consumed_at IS NULL AND encrypted_verifier IS NOT NULL AND encrypted_pending_grant IS NULL) OR (status = 'exchanging' AND consumed_at IS NOT NULL AND encrypted_verifier IS NULL AND encrypted_pending_grant IS NULL) OR (status = 'awaiting_selection' AND consumed_at IS NOT NULL AND encrypted_verifier IS NULL AND encrypted_pending_grant IS NOT NULL) OR (status IN ('completed','failed','expired') AND encrypted_verifier IS NULL AND encrypted_pending_grant IS NULL)", name='ck_social_oauth_secrets'),
        Index('ix_social_oauth_expiry', 'expires_at'),
        Index('ix_social_oauth_actor', 'actor_id', 'created_at'),
    )

CONNECTION_TABLES = (SocialCredential.__table__, SocialOAuthFlow.__table__)

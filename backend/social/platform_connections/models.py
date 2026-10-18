"""Separate credential namespace; Meta-only credential constraints stay unchanged."""
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, ForeignKey, Index, LargeBinary, String, Text, Uuid
from ..models import Base, TZ, created, uid, updated


class PlatformOAuthFlow(Base):
    __tablename__ = 'social_platform_oauth_flows'
    id = uid()
    platform = Column(Text, nullable=False)
    actor_id = Column(Uuid(as_uuid=True), nullable=False)
    binding_hash = Column(String(64), nullable=False)
    state_hash = Column(String(64), nullable=False, unique=True)
    redirect_uri = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default='initiated')
    encrypted_secret = Column(LargeBinary)
    key_version = Column(Text, nullable=False)
    expires_at = Column(TZ, nullable=False)
    consumed_at = Column(TZ)
    created_at = created()
    updated_at = updated()
    __table_args__ = (
        CheckConstraint("platform IN ('threads','x','tiktok')", name='ck_platform_oauth_platform'),
        CheckConstraint("status IN ('initiated','exchanging','awaiting_confirmation','completed','failed','expired')", name='ck_platform_oauth_status'),
        CheckConstraint('length(state_hash)=64 AND length(binding_hash)=64', name='ck_platform_oauth_hashes'),
        CheckConstraint("(status='initiated' AND consumed_at IS NULL AND encrypted_secret IS NOT NULL) OR (status='awaiting_confirmation' AND consumed_at IS NOT NULL AND encrypted_secret IS NOT NULL) OR (status IN ('exchanging','completed','failed','expired') AND encrypted_secret IS NULL)", name='ck_platform_oauth_secret'),
        Index('ix_platform_oauth_expiry', 'expires_at'),
    )


class PlatformCredential(Base):
    __tablename__ = 'social_platform_credentials'
    id = uid()
    account_id = Column(Uuid(as_uuid=True), ForeignKey('social_accounts.id'), nullable=False, unique=True)
    platform = Column(Text, nullable=False)
    encrypted_bundle = Column(LargeBinary, nullable=False)
    key_version = Column(Text, nullable=False)
    version = Column(BigInteger, nullable=False, default=1, server_default='1')
    access_expires_at = Column(TZ, nullable=False)
    data_access_expires_at = Column(TZ)
    # No invented lifetime for provider refresh credentials.
    refresh_expires_at = Column(TZ)
    issued_at = Column(TZ, nullable=False)
    refresh_claim = Column(Uuid(as_uuid=True))
    revoked_at = Column(TZ)
    created_at = created()
    updated_at = updated()
    __table_args__ = (
        CheckConstraint("platform IN ('threads','x','tiktok')", name='ck_platform_credential_platform'),
        CheckConstraint('version > 0 AND length(encrypted_bundle)>0 AND length(key_version)>0', name='ck_platform_credential_envelope'),
        CheckConstraint("platform <> 'threads' OR refresh_expires_at IS NULL", name='ck_threads_no_refresh_expiry'),
    )


class SocialPlatformConnectionBudget(Base):
    __tablename__ = 'social_platform_connection_budgets'
    client_key = Column(String(64), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False, server_default='false')
    access_verified = Column(Boolean, nullable=False, default=False, server_default='false')
    limit_microusd = Column(BigInteger, nullable=False, default=0, server_default='0')
    reserved_microusd = Column(BigInteger, nullable=False, default=0, server_default='0')
    version = Column(BigInteger, nullable=False, default=1, server_default='1')
    __table_args__ = (
        CheckConstraint('length(client_key)=64', name='ck_platform_connection_budget_key'),
        CheckConstraint('reserved_microusd>=0 AND limit_microusd>=reserved_microusd AND version>0', name='ck_platform_connection_budget_bounds'),
    )


PLATFORM_CONNECTION_TABLES = (PlatformOAuthFlow.__table__, PlatformCredential.__table__, SocialPlatformConnectionBudget.__table__)

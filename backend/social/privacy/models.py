"""Sensitive, private ownership and callback history; no raw subjects."""
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, LargeBinary, String, Text, UniqueConstraint, Uuid, event, func
from ..models import Base, J, TZ, created, uid


class SocialPrivacyOwnership(Base):
    __tablename__ = 'social_privacy_ownership'
    id = uid()
    app_id = Column(String(64), nullable=False)
    digest_version = Column(String(32), nullable=False)
    subject_digest = Column(String(64), nullable=False)
    reference_key = Column(Text, nullable=False, unique=True)
    flow_id = Column(Uuid(as_uuid=True), ForeignKey('social_oauth_flows.id'), nullable=False)
    credential_id = Column(Uuid(as_uuid=True), ForeignKey('social_credentials.id'))
    credential_version = Column(BigInteger)
    account_id = Column(Uuid(as_uuid=True), ForeignKey('social_accounts.id'))
    page_id = Column(String(64))
    generation_at = Column(TZ, nullable=False)
    created_at = created()
    __table_args__ = (
        CheckConstraint("length(app_id) BETWEEN 1 AND 64 AND length(subject_digest)=64 AND length(digest_version) BETWEEN 1 AND 32", name='ck_social_privacy_subject'),
        CheckConstraint('(credential_id IS NULL) = (credential_version IS NULL) AND (credential_version IS NULL OR credential_version > 0)', name='ck_social_privacy_credential'),
        CheckConstraint('credential_id IS NOT NULL OR (account_id IS NULL AND page_id IS NULL)', name='ck_social_privacy_reference'),
        Index('ix_social_privacy_subject', 'app_id', 'digest_version', 'subject_digest', 'generation_at'),
        Index('ix_social_privacy_credential', 'credential_id', 'credential_version'),
        Index('ix_social_privacy_flow', 'flow_id'),
    )


class SocialPrivacyReceipt(Base):
    __tablename__ = 'social_privacy_receipts'
    id = uid()
    app_id = Column(String(64), nullable=False)
    kind = Column(Text, nullable=False)
    digest_version = Column(String(32), nullable=False)
    subject_digest = Column(String(64), nullable=False)
    event_key = Column(String(64), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    issued_at = Column(BigInteger)
    provider_expires = Column(BigInteger)
    received_at = Column(TZ, nullable=False, server_default=func.now())  # Database timestamp; no application clock override.
    affected = Column(J, nullable=False)
    resolution = Column(Text, nullable=False)
    state = Column(Text, nullable=False)
    audit_id = Column(Uuid(as_uuid=True), ForeignKey('social_audit_events.id'), nullable=False)
    confirmation_hash = Column(String(64), unique=True)
    confirmation_key_version = Column(Text)
    encrypted_confirmation = Column(LargeBinary)
    status_url_base = Column(Text)
    __table_args__ = (
        UniqueConstraint('app_id', 'kind', 'digest_version', 'event_key', name='uq_social_privacy_event'),
        CheckConstraint("kind IN ('data_deletion','deauthorization') AND state IN ('pending_retention_review','blocked_future_mutations','ownership_unresolved')", name='ck_social_privacy_receipt_state'),
        CheckConstraint("(kind='data_deletion' AND confirmation_hash IS NOT NULL AND encrypted_confirmation IS NOT NULL AND confirmation_key_version IS NOT NULL AND status_url_base IS NOT NULL) OR (kind='deauthorization' AND confirmation_hash IS NULL AND encrypted_confirmation IS NULL AND confirmation_key_version IS NULL AND status_url_base IS NULL)", name='ck_social_privacy_confirmation'),
        Index('ix_social_privacy_receipt_subject', 'app_id', 'kind', 'digest_version', 'subject_digest'),
    )


class SocialPrivacyRequestVariant(Base):
    __tablename__ = 'social_privacy_request_variants'
    id = uid()
    app_id = Column(String(64), nullable=False)
    kind = Column(Text, nullable=False)
    fingerprint = Column(String(64), nullable=False)
    receipt_id = Column(Uuid(as_uuid=True), ForeignKey('social_privacy_receipts.id'), nullable=False)
    received_at = Column(TZ, nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint('app_id', 'kind', 'fingerprint', name='uq_social_privacy_variant'),)


@event.listens_for(SocialPrivacyOwnership, 'before_update')
@event.listens_for(SocialPrivacyOwnership, 'before_delete')
@event.listens_for(SocialPrivacyReceipt, 'before_update')
@event.listens_for(SocialPrivacyReceipt, 'before_delete')
@event.listens_for(SocialPrivacyRequestVariant, 'before_update')
@event.listens_for(SocialPrivacyRequestVariant, 'before_delete')
def immutable_privacy_history(mapper, connection, target):
    raise ValueError('Privacy history requires an approved retention migration')


PRIVACY_TABLES = (SocialPrivacyOwnership.__table__, SocialPrivacyReceipt.__table__, SocialPrivacyRequestVariant.__table__)

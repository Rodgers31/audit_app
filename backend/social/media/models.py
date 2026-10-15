"""Parent owns migration/registration. Shares the existing social Base."""
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, event, inspect

from ..models import Base, TZ, created


class SocialMediaUpload(Base):
    __tablename__ = 'social_media_uploads'
    asset_id = Column(Uuid(as_uuid=True), ForeignKey('social_media_assets.id'), primary_key=True)
    actor_id = Column(Uuid(as_uuid=True), nullable=False)
    initiation_key = Column(Uuid(as_uuid=True), nullable=False)
    request_hash = Column(String(64), nullable=False)
    quarantine_key = Column(Text, nullable=False, unique=True)
    declared_mime_type = Column(Text, nullable=False)
    declared_size = Column(BigInteger, nullable=False)
    version = Column(BigInteger, nullable=False, default=1)
    expires_at = Column(TZ, nullable=False)
    grant_renewal_deadline = Column(TZ, nullable=False)
    grant_epoch = Column(BigInteger, nullable=False, default=0, server_default='0')
    grant_expires_at = Column(TZ)
    grant_settled_epoch = Column(BigInteger, nullable=False, default=0, server_default='0')
    write_quiescence_receipt_hash = Column(String(64))
    pending_released = Column(Integer, nullable=False, default=0, server_default='0')
    completion_key = Column(Uuid(as_uuid=True))
    completion_hash = Column(String(64))
    reservation_released = Column(Integer, nullable=False, default=0)
    quarantine_cleaned = Column(Integer, nullable=False, default=0)
    reserved_bytes = Column(BigInteger, nullable=False)
    retained_write_fence = Column(Text)
    finalization_epoch = Column(BigInteger)
    finalization_settled = Column(Integer, nullable=False, default=0)
    created_at = created()
    __table_args__ = (UniqueConstraint('actor_id', 'initiation_key', name='uq_social_media_intent'), CheckConstraint('declared_size > 0 AND version > 0 AND reserved_bytes >= 0 AND reservation_released IN (0,1) AND quarantine_cleaned IN (0,1) AND finalization_settled IN (0,1) AND (finalization_epoch IS NULL OR finalization_epoch > 0)', name='ck_social_media_upload_bounds'), CheckConstraint('grant_epoch >= 0 AND grant_settled_epoch >= 0 AND grant_settled_epoch <= grant_epoch AND pending_released IN (0,1)', name='ck_social_media_grant_bounds'), CheckConstraint('retained_write_fence IS NULL OR (length(retained_write_fence) <= 4096 AND grant_settled_epoch < grant_epoch AND pending_released = 1 AND reservation_released = 0 AND quarantine_cleaned = 0 AND finalization_settled = 1 AND reserved_bytes >= 2 * declared_size)', name='ck_social_media_retained_fence'), Index('ix_social_media_upload_expiry', 'expires_at'))


@event.listens_for(SocialMediaUpload, 'before_update')
def immutable_retained_fence(mapper, connection, target):
    history = inspect(target).attrs.retained_write_fence.history
    if history.deleted and history.deleted[0] is not None and history.has_changes():
        raise ValueError('Retained write fencing cannot be removed or replaced')


class SocialMediaBudget(Base):
    __tablename__ = 'social_media_budgets'
    # A singleton global scope and one scope per uploader; no blob bodies.
    scope = Column(Text, primary_key=True)
    bytes_used = Column(BigInteger, nullable=False, default=0)
    pending_count = Column(Integer, nullable=False, default=0)
    __table_args__ = (CheckConstraint('bytes_used >= 0 AND pending_count >= 0', name='ck_social_media_budget_nonnegative'),)

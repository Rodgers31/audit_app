"""Minimal durable provider hints; model registration has no HTTP dependencies."""
from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, String, Text, UniqueConstraint

from .models import Base, TZ, created, uid


class SocialPlatformEvent(Base):
    __tablename__ = 'social_platform_event_inbox'
    id = uid()
    provider = Column(Text, nullable=False)
    dedupe_hash = Column(String(64), nullable=False)
    account_id = Column(ForeignKey('social_accounts.id'), nullable=False)
    event_type = Column(Text, nullable=False)
    remote_id = Column(String(256), nullable=False)
    post_id = Column(String(64))
    event_at = Column(TZ, nullable=False)
    received_at = created()
    processed_at = Column(TZ)
    processing_state = Column(Text, nullable=False, default='pending', server_default='pending')
    __table_args__ = (
        UniqueConstraint('provider', 'dedupe_hash', name='uq_social_platform_event_dedupe'),
        CheckConstraint("provider IN ('threads','tiktok')", name='ck_social_platform_event_provider'),
        CheckConstraint("processing_state IN ('pending','processed','unmatched')", name='ck_social_platform_event_state'),
        Index('ix_social_platform_event_pending', 'processing_state', 'received_at', 'id'),
        Index('ix_social_platform_event_retention', 'received_at'),
    )

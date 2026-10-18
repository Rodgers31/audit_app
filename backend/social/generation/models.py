"""Private additive generation state; evidence/rules/decisions are append-only."""
from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Index, Integer, Text, UniqueConstraint, Uuid, event, text
from ..models import Base, J, created, uid, immutable_record


class GenerationControls(Base):
    __tablename__ = 'social_generation_controls'
    id = Column(Integer, primary_key=True, default=1)
    version = Column(Integer, nullable=False, default=1)
    drafts_enabled = Column(Boolean, nullable=False, default=False, server_default=text('false'))
    shadow_enabled = Column(Boolean, nullable=False, default=False, server_default=text('false'))
    source_allowlist = Column(J, nullable=False, default=list)
    targets = Column(J, nullable=False, default=list)
    __table_args__ = (CheckConstraint('id = 1 AND version > 0', name='ck_social_generation_controls'),)


class SourceCursor(Base):
    __tablename__ = 'social_source_cursors'
    id = uid()
    source_type = Column(Text, nullable=False)
    source_key = Column(Text, nullable=False)
    detector_version = Column(Integer, nullable=False)
    evidence_version = Column(Integer, nullable=False)
    sequence = Column(Integer, nullable=False, default=0)
    fingerprint = Column(Text, nullable=False)
    report_state = Column(J, nullable=True)
    observed_at = created()
    __table_args__ = (UniqueConstraint('source_type', 'source_key', 'detector_version', name='uq_social_source_cursor'), CheckConstraint('sequence >= 0 AND evidence_version > 0 AND detector_version > 0', name='ck_social_cursor_versions'))


class SourceEvent(Base):
    __tablename__ = 'social_source_events'
    id = uid()
    cursor_id = Column(Uuid(as_uuid=True), ForeignKey('social_source_cursors.id'), nullable=False)
    sequence = Column(Integer, nullable=False)
    evidence_version = Column(Integer, nullable=False)
    fingerprint = Column(Text, nullable=False)
    observation = Column(J, nullable=False)
    created_at = created()
    __table_args__ = (UniqueConstraint('cursor_id', 'sequence', name='uq_social_source_event_sequence'), UniqueConstraint('cursor_id', 'evidence_version', name='uq_social_source_event_evidence'), CheckConstraint('sequence > 0 AND evidence_version > 0', name='ck_social_source_event_versions'))


class AutomationRuleVersion(Base):
    __tablename__ = 'social_automation_rule_versions'
    id = uid()
    rule_id = Column(Uuid(as_uuid=True), nullable=False)
    version = Column(Integer, nullable=False)
    definition = Column(J, nullable=False)
    definition_hash = Column(Text, nullable=False)
    created_by = Column(Uuid(as_uuid=True), nullable=False)
    created_at = created()
    __table_args__ = (UniqueConstraint('rule_id', 'version', name='uq_social_rule_version'), CheckConstraint('version > 0', name='ck_social_rule_version'))


class ShadowDecision(Base):
    __tablename__ = 'social_shadow_decisions'
    id = uid()
    rule_version_id = Column(Uuid(as_uuid=True), ForeignKey('social_automation_rule_versions.id'), nullable=False)
    post_id = Column(Uuid(as_uuid=True), ForeignKey('social_posts.id'), nullable=False)
    revision_id = Column(Uuid(as_uuid=True), ForeignKey('social_post_revisions.id'), nullable=False)
    content_hash = Column(Text, nullable=False)
    context_hash = Column(Text, nullable=False)
    outcome = Column(Text, nullable=False)
    reasons = Column(J, nullable=False)
    account_ids = Column(J, nullable=False)
    inputs = Column(J, nullable=False)
    created_at = created()
    __table_args__ = (UniqueConstraint('rule_version_id', 'revision_id', 'context_hash', name='uq_social_shadow_context'), CheckConstraint("outcome IN ('would_allow','human_review')", name='ck_social_shadow_outcome'), Index('ix_social_shadow_created', 'created_at'), Index('ix_social_shadow_post', 'post_id', 'created_at'))


for model in (SourceEvent, AutomationRuleVersion, ShadowDecision):
    event.listen(model, 'before_update', immutable_record)
    event.listen(model, 'before_delete', immutable_record)

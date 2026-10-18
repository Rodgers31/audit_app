"""Operating evidence, authorized snapshots and decisions are independent history."""
from sqlalchemy import Column, ForeignKey, Integer, Text, Uuid, UniqueConstraint, CheckConstraint, event
from ..models import Base, J, TZ, uid, created, immutable_record


class OperatingEvidence(Base):
    __tablename__ = 'social_policy_operating_evidence'
    id = uid()
    rule_version_id = Column(Uuid(as_uuid=True), ForeignKey('social_automation_rule_versions.id'), nullable=False)
    evidence = Column(J, nullable=False)
    evidence_hash = Column(Text, nullable=False)
    approved_by = Column(Uuid(as_uuid=True), nullable=False)
    created_at = created()


class AuthorizedPolicySnapshot(Base):
    __tablename__ = 'social_authorized_policy_snapshots'
    id = uid()
    rule_version_id = Column(Uuid(as_uuid=True), ForeignKey('social_automation_rule_versions.id'), nullable=False)
    operating_evidence_id = Column(Uuid(as_uuid=True), ForeignKey('social_policy_operating_evidence.id'), nullable=False)
    version = Column(Integer, nullable=False)
    snapshot = Column(J, nullable=False)
    snapshot_hash = Column(Text, nullable=False)
    approved_by = Column(Uuid(as_uuid=True), nullable=False)
    valid_until = Column(TZ, nullable=False)
    created_at = created()
    __table_args__ = (CheckConstraint('version > 0', name='ck_social_authorized_policy_version'),)


class PolicySelection(Base):
    __tablename__ = 'social_policy_selection'
    id = Column(Integer, primary_key=True, default=1)
    snapshot_id = Column(Uuid(as_uuid=True), ForeignKey('social_authorized_policy_snapshots.id'))
    __table_args__ = (CheckConstraint('id = 1', name='ck_social_policy_selection'),)


class PolicyDecision(Base):
    __tablename__ = 'social_policy_decisions'
    id = uid()
    snapshot_id = Column(Uuid(as_uuid=True), ForeignKey('social_authorized_policy_snapshots.id'), nullable=False)
    policy_version = Column(Integer, nullable=False)
    post_id = Column(Uuid(as_uuid=True), ForeignKey('social_posts.id'), nullable=False)
    revision_id = Column(Uuid(as_uuid=True), ForeignKey('social_post_revisions.id'), nullable=False, unique=True)
    content_hash = Column(Text, nullable=False)
    inputs = Column(J, nullable=False)
    decision_hash = Column(Text, nullable=False)
    created_at = created()
    __table_args__ = (UniqueConstraint('id', 'snapshot_id', 'policy_version', 'post_id', 'revision_id', 'content_hash', name='uq_social_policy_authority'),)


for model in (OperatingEvidence, AuthorizedPolicySnapshot, PolicyDecision):
    event.listen(model, 'before_update', immutable_record)
    event.listen(model, 'before_delete', immutable_record)

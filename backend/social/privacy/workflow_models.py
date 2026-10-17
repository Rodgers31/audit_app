"""Separate immutable authority and mutable execution; callback receipts stay frozen."""
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Text, Uuid, event
from ..models import Base, J, created, uid, updated


class PrivacyPlan(Base):
    __tablename__ = 'social_privacy_plans'
    id = uid()  # Authenticated command UUID; idempotency survives receipt expiry.
    receipt_id = Column(Uuid(as_uuid=True), ForeignKey('social_privacy_receipts.id'), nullable=False)
    proposed_by = Column(Uuid(as_uuid=True), nullable=False)
    policy_key = Column(Text, nullable=False)
    policy_hash = Column(Text, nullable=False)
    evidence = Column(Text, nullable=False)
    scope = Column(J, nullable=False)
    plan_hash = Column(Text, nullable=False)
    created_at = created()
    __table_args__ = (CheckConstraint('length(plan_hash)=64 AND length(policy_hash)=64', name='ck_privacy_plan_hash'),)


class PrivacyDecision(Base):
    __tablename__ = 'social_privacy_decisions'
    id = uid()
    plan_id = Column(Uuid(as_uuid=True), ForeignKey('social_privacy_plans.id'), nullable=False, unique=True)
    approved_by = Column(Uuid(as_uuid=True), nullable=False)
    plan_hash = Column(Text, nullable=False)
    decision = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    created_at = created()
    __table_args__ = (CheckConstraint("decision IN ('approved','rejected')", name='ck_privacy_decision'),)


class PrivacyExecution(Base):
    __tablename__ = 'social_privacy_executions'
    id = uid()  # Stable operation identity across process failure/reconciliation.
    plan_id = Column(Uuid(as_uuid=True), ForeignKey('social_privacy_plans.id'), nullable=False, unique=True)
    state = Column(Text, nullable=False)
    version = Column(BigInteger, nullable=False, default=1, server_default='1')
    result = Column(J, nullable=False, default=dict)
    created_at = created()
    updated_at = updated()
    __table_args__ = (CheckConstraint("state IN ('prepared','executing','outcome_unknown','completed') AND version>0", name='ck_privacy_execution'),)


class PrivacyExecutionEvent(Base):
    __tablename__ = 'social_privacy_execution_events'
    id = uid()
    execution_id = Column(Uuid(as_uuid=True), ForeignKey('social_privacy_executions.id'), nullable=False)
    state = Column(Text, nullable=False)
    details = Column(J, nullable=False)
    created_at = created()


for _model in (PrivacyPlan, PrivacyDecision, PrivacyExecutionEvent):
    @event.listens_for(_model, 'before_update')
    @event.listens_for(_model, 'before_delete')
    def immutable_authority(mapper, connection, target):
        raise ValueError('Privacy authority and execution history are immutable')

WORKFLOW_TABLES = (PrivacyPlan.__table__, PrivacyDecision.__table__, PrivacyExecution.__table__, PrivacyExecutionEvent.__table__)

from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, event, inspect

from ..models import Base, J, TZ, created, uid


class RenderJob(Base):
    __tablename__ = 'social_render_jobs'
    id = uid()
    revision_id = Column(Uuid(as_uuid=True), ForeignKey('social_post_revisions.id'), nullable=False)
    actor_id = Column(Uuid(as_uuid=True), nullable=False)
    composition = Column(J, nullable=False)
    input_hash = Column(String(64), nullable=False)
    attempt = Column(Integer, nullable=False, default=1)
    retry_of_id = Column(Uuid(as_uuid=True), ForeignKey('social_render_jobs.id'))
    runtime_hash = Column(String(64))
    state = Column(Text, nullable=False, default='queued')
    version = Column(BigInteger, nullable=False, default=1)
    cancel_requested = Column(Integer, nullable=False, default=0)
    token = Column(Uuid(as_uuid=True))
    started_at = Column(TZ)
    finished_at = Column(TZ)
    sha256 = Column(String(64))
    inspection = Column(J)
    safe_error = Column(Text)
    approved_sha256 = Column(String(64))
    approved_by = Column(Uuid(as_uuid=True))
    approved_at = Column(TZ)
    created_at = created()
    __table_args__ = (
        UniqueConstraint('actor_id', 'input_hash', 'attempt', name='uq_social_render_input'),
        CheckConstraint('(attempt=1 AND retry_of_id IS NULL) OR (attempt=2 AND retry_of_id IS NOT NULL)', name='ck_social_render_attempt'),
        CheckConstraint("state IN ('queued','running','ready','failed','cancelled') AND version>0 AND cancel_requested IN (0,1)", name='ck_social_render_state'),
        CheckConstraint("state<>'ready' OR (sha256 IS NOT NULL AND inspection IS NOT NULL AND runtime_hash IS NOT NULL)", name='ck_social_render_ready'),
        CheckConstraint("approved_sha256 IS NULL OR (state='ready' AND approved_sha256=sha256 AND approved_by IS NOT NULL AND approved_at IS NOT NULL)", name='ck_social_render_approval'),
        Index('ix_social_render_queue', 'state', 'created_at'),
    )
    __mapper_args__ = {'version_id_col': version, 'version_id_generator': False}


@event.listens_for(RenderJob, 'before_update')
def immutable_input(mapper, connection, row):
    history = inspect(row)
    for key in ('revision_id', 'actor_id', 'composition', 'input_hash', 'attempt', 'retry_of_id'):
        if history.attrs[key].history.has_changes():
            raise ValueError('Render inputs are immutable; create a new composition')
    for key in ('sha256', 'inspection', 'runtime_hash', 'approved_sha256', 'approved_by', 'approved_at'):
        change = history.attrs[key].history
        if change.has_changes() and change.deleted and change.deleted[0] is not None:
            raise ValueError('Render derivative and approval evidence are immutable')


class MetricCollection(Base):
    __tablename__ = 'social_metric_collections'
    id = uid()
    account_id = Column(Uuid(as_uuid=True), ForeignKey('social_accounts.id'), nullable=False)
    target_id = Column(Uuid(as_uuid=True), ForeignKey('social_post_targets.id'), nullable=False)
    platform = Column(Text, nullable=False)
    remote_id = Column(Text, nullable=False)
    state = Column(Text, nullable=False)
    reason = Column(Text)
    created_at = created()
    __table_args__ = (CheckConstraint("state IN ('reserved','collected','unavailable','failed')", name='ck_social_metric_collection_state'), Index('ix_social_metric_quota', 'account_id', 'created_at'), Index('ix_social_metric_target', 'target_id', 'created_at'))


class MetricObservation(Base):
    __tablename__ = 'social_metric_observations'
    id = uid()
    collection_id = Column(Uuid(as_uuid=True), ForeignKey('social_metric_collections.id'), nullable=False)
    metric = Column(J, nullable=False)
    __table_args__ = (Index('ix_social_metric_collection', 'collection_id'),)


@event.listens_for(MetricObservation, 'before_update')
@event.listens_for(MetricObservation, 'before_delete')
def immutable_observation(mapper, connection, row):
    raise ValueError('Provider observations are append-only')

"""Additive social persistence; no startup, credentials or database access."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, Numeric, SmallInteger, String, Text, UniqueConstraint, Uuid, event, func, inspect, text)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from models import Base

J = JSON().with_variant(JSONB(), "postgresql")
TZ = DateTime(timezone=True)


def uid():
    return Column(Uuid(as_uuid=True), primary_key=True, default=uuid4)


def created():
    return Column(TZ, nullable=False, server_default=func.now(), default=lambda: datetime.now(timezone.utc))


def updated():
    return Column(TZ, nullable=False, server_default=func.now(), default=lambda: datetime.now(timezone.utc))


class SocialPost(Base):
    __tablename__ = "social_posts"
    id = uid()
    origin_type = Column(Text, nullable=False, default="manual")
    creation_method = Column(Text, nullable=False, default="admin")
    title = Column(Text, nullable=False)
    content_type = Column(Text, nullable=False)
    editorial_state = Column(Text, nullable=False, default="draft")
    current_revision_id = Column(Uuid(as_uuid=True), nullable=True)
    source_event_id = Column(Uuid(as_uuid=True))  # FK belongs to the later source-event migration.
    duplicated_from_id = Column(Uuid(as_uuid=True), ForeignKey("social_posts.id"))
    replaces_post_id = Column(Uuid(as_uuid=True), ForeignKey("social_posts.id"))
    created_by = Column(Uuid(as_uuid=True))  # Supabase identity, intentionally no profile FK.
    row_version = Column(BigInteger, nullable=False, default=1, server_default="1")
    created_at = created()
    updated_at = updated()
    archived_at = Column(TZ)
    __table_args__ = (
        CheckConstraint("origin_type IN ('manual','generated')", name="ck_social_post_origin"),
        CheckConstraint("creation_method IN ('admin','pipeline','duplicate')", name="ck_social_post_creation"),
        CheckConstraint("editorial_state IN ('draft','pending_review','approved','rejected','archived')", name="ck_social_post_editorial"),
        CheckConstraint("row_version > 0", name="ck_social_post_version"),
        ForeignKeyConstraint(["current_revision_id", "id"], ["social_post_revisions.id", "social_post_revisions.post_id"], name="fk_social_current_revision", deferrable=True, initially="DEFERRED", use_alter=True),
        Index("ix_social_post_editorial_updated", "editorial_state", "updated_at"),
    )
    __mapper_args__ = {"version_id_col": row_version, "version_id_generator": False}


class SocialPostRevision(Base):
    __tablename__ = "social_post_revisions"
    id = uid()
    post_id = Column(Uuid(as_uuid=True), ForeignKey("social_posts.id"), nullable=False)
    revision_no = Column(Integer, nullable=False)
    document = Column(J, nullable=False)
    content_hash = Column(String(64), nullable=False)
    evidence_snapshot = Column(J, nullable=False, default=dict)
    generator_metadata = Column(J)
    created_by = Column(Uuid(as_uuid=True))
    created_at = created()
    __table_args__ = (UniqueConstraint("post_id", "revision_no", name="uq_social_revision_number"), UniqueConstraint("id", "post_id", name="uq_social_revision_owner"), CheckConstraint("revision_no > 0", name="ck_social_revision_number"))


class SocialMediaAsset(Base):
    __tablename__ = "social_media_assets"
    id = uid()
    parent_asset_id = Column(Uuid(as_uuid=True), ForeignKey("social_media_assets.id"))
    storage_provider = Column(Text, nullable=False)
    bucket = Column(Text, nullable=False)
    storage_key = Column(Text, nullable=False)
    original_filename = Column(Text, nullable=False)
    mime_type = Column(Text)
    byte_size = Column(BigInteger)
    sha256 = Column(String(64))
    width = Column(Integer)
    height = Column(Integer)
    duration_ms = Column(BigInteger)
    frame_rate = Column(Numeric)
    codec_metadata = Column(J, nullable=False, default=dict)
    default_alt_text = Column(Text)
    state = Column(Text, nullable=False, default="pending")
    inspection_error = Column(Text)
    lease_token = Column(Uuid(as_uuid=True))
    lease_epoch = Column(BigInteger, nullable=False, default=0, server_default="0")
    lease_expires_at = Column(TZ)
    created_by = Column(Uuid(as_uuid=True), nullable=False)
    created_at = created()
    updated_at = updated()
    deleted_at = Column(TZ)
    __table_args__ = (
        UniqueConstraint("storage_provider", "bucket", "storage_key", name="uq_social_asset_object"),
        CheckConstraint("state IN ('pending','inspecting','ready','failed','archived')", name="ck_social_asset_state"),
        CheckConstraint("byte_size IS NULL OR byte_size > 0", name="ck_social_asset_size"),
        CheckConstraint("width IS NULL OR width > 0", name="ck_social_asset_width"),
        CheckConstraint("height IS NULL OR height > 0", name="ck_social_asset_height"),
        CheckConstraint("duration_ms IS NULL OR duration_ms > 0", name="ck_social_asset_duration"),
        CheckConstraint("state <> 'ready' OR (mime_type IS NOT NULL AND byte_size IS NOT NULL AND sha256 IS NOT NULL)", name="ck_social_asset_ready"),
        Index("ix_social_asset_state", "state"),
    )


class SocialRevisionAsset(Base):
    __tablename__ = "social_revision_assets"
    revision_id = Column(Uuid(as_uuid=True), ForeignKey("social_post_revisions.id"), primary_key=True)
    asset_id = Column(Uuid(as_uuid=True), ForeignKey("social_media_assets.id"), primary_key=True)


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    id = uid()
    platform = Column(Text, nullable=False)
    api_product = Column(Text, nullable=False)
    connection_method = Column(Text, nullable=False)
    external_account_id = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    handle = Column(Text)
    profile_url = Column(Text)
    credential_id = Column(Uuid(as_uuid=True))  # Staged FK when OAuth/encrypted credentials land.
    connection_state = Column(Text, nullable=False, default="unverified")
    granted_scopes = Column(JSON().with_variant(ARRAY(Text()), "postgresql"), nullable=False, default=list)
    capability_snapshot = Column(J, nullable=False, default=dict)
    capabilities_checked_at = Column(TZ)
    last_api_success_at = Column(TZ)
    publishing_enabled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    hold_reason = Column(Text)
    rate_state = Column(J, nullable=False, default=dict)
    publish_lease_target_id = Column(Uuid(as_uuid=True), ForeignKey("social_post_targets.id", use_alter=True, name="fk_social_account_lease_target"))
    publish_lease_token = Column(Uuid(as_uuid=True))
    publish_lease_expires_at = Column(TZ)
    created_at = created()
    updated_at = updated()
    __table_args__ = (
        UniqueConstraint("platform", "api_product", "external_account_id", name="uq_social_account_identity"),
        CheckConstraint("platform IN ('facebook','instagram','threads','x','tiktok')", name="ck_social_account_platform"),
        CheckConstraint("connection_state IN ('connected','unverified','expired','revoked','disconnected','blocked')", name="ck_social_account_connection"),
        Index("ix_social_account_connection", "connection_state"),
    )


class SocialPublication(Base):
    __tablename__ = "social_publications"
    id = uid()
    post_id = Column(Uuid(as_uuid=True), ForeignKey("social_posts.id"), nullable=False)
    revision_id = Column(Uuid(as_uuid=True), nullable=False)
    authorization_kind = Column(Text, nullable=False, default="human")
    approved_by = Column(Uuid(as_uuid=True))
    approved_at = Column(TZ, nullable=False)
    policy_id = Column(Uuid(as_uuid=True))  # Staged policy FK; unsupported for this batch.
    policy_version = Column(Integer)
    approved_hash = Column(String(64), nullable=False)
    scheduled_for = Column(TZ)
    schedule_timezone = Column(Text)
    requested_local_time = Column(Text)
    start_deadline = Column(TZ)
    retry_deadline = Column(TZ)
    content_valid_until = Column(TZ)
    dispatch_requested_at = Column(TZ)
    revoked_at = Column(TZ)
    cancel_requested_at = Column(TZ)
    version = Column(BigInteger, nullable=False, default=1, server_default="1")
    created_at = created()
    updated_at = updated()
    __table_args__ = (
        ForeignKeyConstraint(["revision_id", "post_id"], ["social_post_revisions.id", "social_post_revisions.post_id"], name="fk_social_publication_revision"),
        UniqueConstraint("revision_id", name="uq_social_publication_revision"),
        CheckConstraint("authorization_kind = 'human' AND approved_by IS NOT NULL AND policy_id IS NULL AND policy_version IS NULL", name="ck_social_publication_human"),
        CheckConstraint("version > 0", name="ck_social_publication_version"),
        Index("uq_social_publication_active_post", "post_id", unique=True, postgresql_where=text("revoked_at IS NULL"), sqlite_where=text("revoked_at IS NULL")),
        Index("ix_social_publication_schedule", "scheduled_for"),
    )
    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}


class SocialPostTarget(Base):
    __tablename__ = "social_post_targets"
    id = uid()
    publication_id = Column(Uuid(as_uuid=True), ForeignKey("social_publications.id"), nullable=False)
    account_id = Column(Uuid(as_uuid=True), ForeignKey("social_accounts.id"), nullable=False)
    resolved_payload = Column(J, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    capability_version = Column(Text, nullable=False)
    state = Column(Text, nullable=False, default="ready")
    next_action = Column(Text)
    next_action_at = Column(TZ)
    lease_owner = Column(Text)
    lease_token = Column(Uuid(as_uuid=True))
    lease_epoch = Column(BigInteger, nullable=False, default=0, server_default="0")
    lease_expires_at = Column(TZ)
    submit_count = Column(Integer, nullable=False, default=0, server_default="0")
    checkpoint = Column(J, nullable=False, default=dict)
    primary_remote_id = Column(Text)
    remote_refs = Column(J, nullable=False, default=dict)
    remote_url = Column(Text)
    visibility_state = Column(Text, nullable=False, default="unknown")
    confirmation_kind = Column(Text)
    error_code = Column(Text)
    safe_error_message = Column(Text)
    published_at = Column(TZ)
    created_at = created()
    updated_at = updated()
    __table_args__ = (
        UniqueConstraint("publication_id", "account_id", name="uq_social_target_account"),
        CheckConstraint("state IN ('ready','queued','claimed','dispatching','processing','retry_wait','reconciling','blocked','published','failed','outcome_unknown','cancelled')", name="ck_social_target_state"),
        CheckConstraint("submit_count >= 0 AND submit_count <= 5 AND lease_epoch >= 0", name="ck_social_target_counters"),
        CheckConstraint("state <> 'published' OR (primary_remote_id IS NOT NULL AND confirmation_kind IS NOT NULL AND published_at IS NOT NULL AND visibility_state = 'public')", name="ck_social_target_published_proof"),
        Index("uq_social_target_remote", "account_id", "primary_remote_id", unique=True, postgresql_where=text("primary_remote_id IS NOT NULL"), sqlite_where=text("primary_remote_id IS NOT NULL")),
        Index("ix_social_target_due", "next_action_at", "id", postgresql_where=text("state IN ('queued','retry_wait','processing','reconciling')"), sqlite_where=text("state IN ('queued','retry_wait','processing','reconciling')")),
        Index("ix_social_target_expired_lease", "lease_expires_at", postgresql_where=text("lease_token IS NOT NULL"), sqlite_where=text("lease_token IS NOT NULL")),
    )


class SocialPublishAttempt(Base):
    __tablename__ = "social_publish_attempts"
    id = uid()
    target_id = Column(Uuid(as_uuid=True), ForeignKey("social_post_targets.id"), nullable=False)
    sequence = Column(Integer, nullable=False)
    operation_id = Column(Uuid(as_uuid=True), nullable=False, unique=True)
    operation = Column(Text, nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    lease_epoch = Column(BigInteger, nullable=False)
    dispatch_started_at = Column(TZ)
    completed_at = Column(TZ)
    outcome = Column(Text, nullable=False)
    http_status = Column(Integer)
    provider_code = Column(Text)
    provider_request_id = Column(Text)
    receipt = Column(J, nullable=False, default=dict)
    estimated_cost_microusd = Column(BigInteger, nullable=False, default=0, server_default="0")
    cost_reservation_state = Column(Text, nullable=False, default="none")
    duration_ms = Column(Integer)
    created_at = created()
    __table_args__ = (UniqueConstraint("target_id", "sequence", name="uq_social_attempt_sequence"), CheckConstraint("sequence > 0 AND lease_epoch >= 0 AND estimated_cost_microusd >= 0", name="ck_social_attempt_counters"), Index("ix_social_attempt_target_time", "target_id", "created_at"))


class SocialAuditEvent(Base):
    __tablename__ = "social_audit_events"
    id = uid()
    post_id = Column(Uuid(as_uuid=True), ForeignKey("social_posts.id"))
    target_id = Column(Uuid(as_uuid=True), ForeignKey("social_post_targets.id"))
    account_id = Column(Uuid(as_uuid=True), ForeignKey("social_accounts.id"))
    actor_id = Column(Uuid(as_uuid=True))
    actor_kind = Column(Text, nullable=False)
    action = Column(Text, nullable=False)
    previous_state = Column(Text)
    new_state = Column(Text)
    reason = Column(Text)
    details = Column(J, nullable=False, default=dict)
    request_id = Column(Text, nullable=False)
    created_at = created()
    __table_args__ = (Index("ix_social_audit_post_time", "post_id", "created_at"), Index("ix_social_audit_actor_time", "actor_id", "created_at"))


class SocialCommandReceipt(Base):
    __tablename__ = "social_command_receipts"
    id = uid()
    actor_key = Column(Text, nullable=False)
    route_key = Column(Text, nullable=False)
    idempotency_key = Column(Uuid(as_uuid=True), nullable=False)
    request_hash = Column(String(64), nullable=False)
    resource_id = Column(Uuid(as_uuid=True))
    http_status = Column(Integer, nullable=False)
    response = Column(J, nullable=False)
    created_at = created()
    expires_at = Column(TZ, nullable=False)
    __table_args__ = (UniqueConstraint("actor_key", "route_key", "idempotency_key", name="uq_social_command_key"), Index("ix_social_receipt_expiry", "expires_at"))


class SocialControls(Base):
    __tablename__ = "social_controls"
    id = Column(SmallInteger, primary_key=True, default=1)
    publishing_enabled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    generation_enabled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    auto_approve_enabled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    auto_schedule_enabled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    auto_publish_enabled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    platform_controls = Column(J, nullable=False, default=dict)
    budget_controls = Column(J, nullable=False, default=dict)
    version = Column(BigInteger, nullable=False, default=1, server_default="1")
    updated_by = Column(Uuid(as_uuid=True))
    updated_at = updated()
    __table_args__ = (CheckConstraint("id = 1 AND version > 0", name="ck_social_controls_singleton"), CheckConstraint("NOT generation_enabled AND NOT auto_approve_enabled AND NOT auto_schedule_enabled AND NOT auto_publish_enabled", name="ck_social_controls_automation_off"))
    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}


class SocialWorkerHeartbeat(Base):
    __tablename__ = "social_worker_heartbeats"
    worker_id = Column(Uuid(as_uuid=True), primary_key=True)
    deployment_version = Column(Text, nullable=False)
    started_at = Column(TZ, nullable=False)
    heartbeat_at = Column(TZ, nullable=False)
    last_scan_at = Column(TZ)
    last_success_at = Column(TZ)
    active_claims = Column(Integer, nullable=False, default=0)
    state = Column(Text, nullable=False)
    last_error_code = Column(Text)
    __table_args__ = (Index("ix_social_worker_heartbeat", "heartbeat_at"), CheckConstraint("active_claims >= 0", name="ck_social_worker_claims"))


@event.listens_for(SocialPostRevision, "before_update")
@event.listens_for(SocialPostRevision, "before_delete")
@event.listens_for(SocialAuditEvent, "before_update")
@event.listens_for(SocialAuditEvent, "before_delete")
def immutable_record(mapper, connection, target):
    raise ValueError("Social revisions and audit history are immutable")


@event.listens_for(SocialPostTarget, "before_update")
def immutable_payload(mapper, connection, target):
    state = inspect(target)
    for key in ("publication_id", "account_id", "resolved_payload", "payload_hash", "capability_version"):
        if state.attrs[key].history.has_changes():
            raise ValueError("Approved social target payload is immutable")


SOCIAL_TABLES = tuple(table for table in Base.metadata.sorted_tables if table.name.startswith("social_"))


@event.listens_for(SocialPublication, "before_update")
def immutable_authorization(mapper, connection, target):
    state = inspect(target)
    for key in ("post_id", "revision_id", "authorization_kind", "approved_by", "approved_at", "policy_id", "policy_version", "approved_hash"):
        if state.attrs[key].history.has_changes():
            raise ValueError("Social authorization is immutable")


@event.listens_for(SocialMediaAsset, "before_update")
def immutable_ready_asset(mapper, connection, target):
    state = inspect(target)
    original = state.attrs.state.history.deleted
    if (original and original[0] == "ready") or (not original and target.state == "ready"):
        for key in ("storage_provider", "bucket", "storage_key", "sha256", "mime_type", "byte_size", "width", "height", "duration_ms", "frame_rate", "codec_metadata"):
            if state.attrs[key].history.has_changes():
                raise ValueError("Inspected ready asset bytes and identity are immutable")

"""Add immutable manual social workflow and durable queue; no operational seeds.

Future credentials/source-event/policy foreign keys belong to later migrations.
No OAuth, generation or upload infrastructure is precreated. Browser roles have
no direct access; ordinary API/worker database sessions own this boundary."""
from alembic import op
import sqlalchemy as sa

revision = "f38c61a9d203"
down_revision = "c415a10d2026"
branch_labels = None
depends_on = None

SOCIAL_TABLE_NAMES = (
    'social_accounts',
    'social_command_receipts',
    'social_controls',
    'social_media_assets',
    'social_posts',
    'social_worker_heartbeats',
    'social_post_revisions',
    'social_publications',
    'social_revision_assets',
    'social_post_targets',
    'social_audit_events',
    'social_publish_attempts',
)


def upgrade():
    op.execute(sa.text("""
    CREATE TABLE social_accounts (
        id UUID NOT NULL,
        platform TEXT NOT NULL,
        api_product TEXT NOT NULL,
        connection_method TEXT NOT NULL,
        external_account_id TEXT NOT NULL,
        display_name TEXT NOT NULL,
        handle TEXT,
        profile_url TEXT,
        credential_id UUID,
        connection_state TEXT NOT NULL,
        granted_scopes TEXT[] NOT NULL,
        capability_snapshot JSONB NOT NULL,
        capabilities_checked_at TIMESTAMP WITH TIME ZONE,
        last_api_success_at TIMESTAMP WITH TIME ZONE,
        publishing_enabled BOOLEAN DEFAULT false NOT NULL,
        hold_reason TEXT,
        rate_state JSONB NOT NULL,
        publish_lease_target_id UUID,
        publish_lease_token UUID,
        publish_lease_expires_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_social_account_identity UNIQUE (platform, api_product, external_account_id),
        CONSTRAINT ck_social_account_platform CHECK (platform IN ('facebook','instagram','threads','x','tiktok')),
        CONSTRAINT ck_social_account_connection CHECK (connection_state IN ('connected','unverified','expired','revoked','disconnected','blocked'))
    )
    """))
    op.execute(sa.text("""
    CREATE TABLE social_command_receipts (
        id UUID NOT NULL,
        actor_key TEXT NOT NULL,
        route_key TEXT NOT NULL,
        idempotency_key UUID NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        resource_id UUID,
        http_status INTEGER NOT NULL,
        response JSONB NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_social_command_key UNIQUE (actor_key, route_key, idempotency_key)
    )
    """))
    op.execute(sa.text("""
    CREATE TABLE social_controls (
        id SMALLINT NOT NULL,
        publishing_enabled BOOLEAN DEFAULT false NOT NULL,
        generation_enabled BOOLEAN DEFAULT false NOT NULL,
        auto_approve_enabled BOOLEAN DEFAULT false NOT NULL,
        auto_schedule_enabled BOOLEAN DEFAULT false NOT NULL,
        auto_publish_enabled BOOLEAN DEFAULT false NOT NULL,
        platform_controls JSONB NOT NULL,
        budget_controls JSONB NOT NULL,
        version BIGINT DEFAULT '1' NOT NULL,
        updated_by UUID,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT ck_social_controls_singleton CHECK (id = 1 AND version > 0),
        CONSTRAINT ck_social_controls_automation_off CHECK (NOT generation_enabled AND NOT auto_approve_enabled AND NOT auto_schedule_enabled AND NOT auto_publish_enabled)
    )
    """))
    op.execute(sa.text("""
    CREATE TABLE social_media_assets (
        id UUID NOT NULL,
        parent_asset_id UUID,
        storage_provider TEXT NOT NULL,
        bucket TEXT NOT NULL,
        storage_key TEXT NOT NULL,
        original_filename TEXT NOT NULL,
        mime_type TEXT,
        byte_size BIGINT,
        sha256 VARCHAR(64),
        width INTEGER,
        height INTEGER,
        duration_ms BIGINT,
        frame_rate NUMERIC,
        codec_metadata JSONB NOT NULL,
        default_alt_text TEXT,
        state TEXT NOT NULL,
        inspection_error TEXT,
        lease_token UUID,
        lease_epoch BIGINT DEFAULT '0' NOT NULL,
        lease_expires_at TIMESTAMP WITH TIME ZONE,
        created_by UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        deleted_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (id),
        CONSTRAINT uq_social_asset_object UNIQUE (storage_provider, bucket, storage_key),
        CONSTRAINT ck_social_asset_state CHECK (state IN ('pending','inspecting','ready','failed','archived')),
        CONSTRAINT ck_social_asset_size CHECK (byte_size IS NULL OR byte_size > 0),
        CONSTRAINT ck_social_asset_width CHECK (width IS NULL OR width > 0),
        CONSTRAINT ck_social_asset_height CHECK (height IS NULL OR height > 0),
        CONSTRAINT ck_social_asset_duration CHECK (duration_ms IS NULL OR duration_ms > 0),
        CONSTRAINT ck_social_asset_ready CHECK (state <> 'ready' OR (mime_type IS NOT NULL AND byte_size IS NOT NULL AND sha256 IS NOT NULL)),
        FOREIGN KEY(parent_asset_id) REFERENCES social_media_assets (id)
    )
    """))
    op.execute(sa.text("""
    CREATE TABLE social_posts (
        id UUID NOT NULL,
        origin_type TEXT NOT NULL,
        creation_method TEXT NOT NULL,
        title TEXT NOT NULL,
        content_type TEXT NOT NULL,
        editorial_state TEXT NOT NULL,
        current_revision_id UUID,
        source_event_id UUID,
        duplicated_from_id UUID,
        replaces_post_id UUID,
        created_by UUID,
        row_version BIGINT DEFAULT '1' NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        archived_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (id),
        CONSTRAINT ck_social_post_origin CHECK (origin_type IN ('manual','generated')),
        CONSTRAINT ck_social_post_creation CHECK (creation_method IN ('admin','pipeline','duplicate')),
        CONSTRAINT ck_social_post_editorial CHECK (editorial_state IN ('draft','pending_review','approved','rejected','archived')),
        CONSTRAINT ck_social_post_version CHECK (row_version > 0),
        FOREIGN KEY(duplicated_from_id) REFERENCES social_posts (id),
        FOREIGN KEY(replaces_post_id) REFERENCES social_posts (id)
    )
    """))
    op.execute(sa.text("""
    CREATE TABLE social_worker_heartbeats (
        worker_id UUID NOT NULL,
        deployment_version TEXT NOT NULL,
        started_at TIMESTAMP WITH TIME ZONE NOT NULL,
        heartbeat_at TIMESTAMP WITH TIME ZONE NOT NULL,
        last_scan_at TIMESTAMP WITH TIME ZONE,
        last_success_at TIMESTAMP WITH TIME ZONE,
        active_claims INTEGER NOT NULL,
        state TEXT NOT NULL,
        last_error_code TEXT,
        PRIMARY KEY (worker_id),
        CONSTRAINT ck_social_worker_claims CHECK (active_claims >= 0)
    )
    """))
    op.execute(sa.text("""
    CREATE TABLE social_post_revisions (
        id UUID NOT NULL,
        post_id UUID NOT NULL,
        revision_no INTEGER NOT NULL,
        document JSONB NOT NULL,
        content_hash VARCHAR(64) NOT NULL,
        evidence_snapshot JSONB NOT NULL,
        generator_metadata JSONB,
        created_by UUID,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_social_revision_number UNIQUE (post_id, revision_no),
        CONSTRAINT uq_social_revision_owner UNIQUE (id, post_id),
        CONSTRAINT ck_social_revision_number CHECK (revision_no > 0),
        FOREIGN KEY(post_id) REFERENCES social_posts (id)
    )
    """))
    op.execute(sa.text("""
    CREATE TABLE social_publications (
        id UUID NOT NULL,
        post_id UUID NOT NULL,
        revision_id UUID NOT NULL,
        authorization_kind TEXT NOT NULL,
        approved_by UUID,
        approved_at TIMESTAMP WITH TIME ZONE NOT NULL,
        policy_id UUID,
        policy_version INTEGER,
        approved_hash VARCHAR(64) NOT NULL,
        scheduled_for TIMESTAMP WITH TIME ZONE,
        schedule_timezone TEXT,
        requested_local_time TEXT,
        start_deadline TIMESTAMP WITH TIME ZONE,
        retry_deadline TIMESTAMP WITH TIME ZONE,
        content_valid_until TIMESTAMP WITH TIME ZONE,
        dispatch_requested_at TIMESTAMP WITH TIME ZONE,
        revoked_at TIMESTAMP WITH TIME ZONE,
        cancel_requested_at TIMESTAMP WITH TIME ZONE,
        version BIGINT DEFAULT '1' NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT fk_social_publication_revision FOREIGN KEY(revision_id, post_id) REFERENCES social_post_revisions (id, post_id),
        CONSTRAINT uq_social_publication_revision UNIQUE (revision_id),
        CONSTRAINT ck_social_publication_human CHECK (authorization_kind = 'human' AND approved_by IS NOT NULL AND policy_id IS NULL AND policy_version IS NULL),
        CONSTRAINT ck_social_publication_version CHECK (version > 0),
        FOREIGN KEY(post_id) REFERENCES social_posts (id)
    )
    """))
    op.execute(sa.text("""
    CREATE TABLE social_revision_assets (
        revision_id UUID NOT NULL,
        asset_id UUID NOT NULL,
        PRIMARY KEY (revision_id, asset_id),
        FOREIGN KEY(revision_id) REFERENCES social_post_revisions (id),
        FOREIGN KEY(asset_id) REFERENCES social_media_assets (id)
    )
    """))
    op.execute(sa.text("""
    CREATE TABLE social_post_targets (
        id UUID NOT NULL,
        publication_id UUID NOT NULL,
        account_id UUID NOT NULL,
        resolved_payload JSONB NOT NULL,
        payload_hash VARCHAR(64) NOT NULL,
        capability_version TEXT NOT NULL,
        state TEXT NOT NULL,
        next_action TEXT,
        next_action_at TIMESTAMP WITH TIME ZONE,
        lease_owner TEXT,
        lease_token UUID,
        lease_epoch BIGINT DEFAULT '0' NOT NULL,
        lease_expires_at TIMESTAMP WITH TIME ZONE,
        submit_count INTEGER DEFAULT '0' NOT NULL,
        checkpoint JSONB NOT NULL,
        primary_remote_id TEXT,
        remote_refs JSONB NOT NULL,
        remote_url TEXT,
        visibility_state TEXT NOT NULL,
        confirmation_kind TEXT,
        error_code TEXT,
        safe_error_message TEXT,
        published_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_social_target_account UNIQUE (publication_id, account_id),
        CONSTRAINT ck_social_target_state CHECK (state IN ('ready','queued','claimed','dispatching','processing','retry_wait','reconciling','blocked','published','failed','outcome_unknown','cancelled')),
        CONSTRAINT ck_social_target_counters CHECK (submit_count >= 0 AND submit_count <= 5 AND lease_epoch >= 0),
        CONSTRAINT ck_social_target_published_proof CHECK (state <> 'published' OR (primary_remote_id IS NOT NULL AND confirmation_kind IS NOT NULL AND published_at IS NOT NULL AND visibility_state = 'public')),
        FOREIGN KEY(publication_id) REFERENCES social_publications (id),
        FOREIGN KEY(account_id) REFERENCES social_accounts (id)
    )
    """))
    op.execute(sa.text("""
    CREATE TABLE social_audit_events (
        id UUID NOT NULL,
        post_id UUID,
        target_id UUID,
        account_id UUID,
        actor_id UUID,
        actor_kind TEXT NOT NULL,
        action TEXT NOT NULL,
        previous_state TEXT,
        new_state TEXT,
        reason TEXT,
        details JSONB NOT NULL,
        request_id TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(post_id) REFERENCES social_posts (id),
        FOREIGN KEY(target_id) REFERENCES social_post_targets (id),
        FOREIGN KEY(account_id) REFERENCES social_accounts (id)
    )
    """))
    op.execute(sa.text("""
    CREATE TABLE social_publish_attempts (
        id UUID NOT NULL,
        target_id UUID NOT NULL,
        sequence INTEGER NOT NULL,
        operation_id UUID NOT NULL,
        operation TEXT NOT NULL,
        request_fingerprint VARCHAR(64) NOT NULL,
        lease_epoch BIGINT NOT NULL,
        dispatch_started_at TIMESTAMP WITH TIME ZONE,
        completed_at TIMESTAMP WITH TIME ZONE,
        outcome TEXT NOT NULL,
        http_status INTEGER,
        provider_code TEXT,
        provider_request_id TEXT,
        receipt JSONB NOT NULL,
        estimated_cost_microusd BIGINT DEFAULT '0' NOT NULL,
        cost_reservation_state TEXT NOT NULL,
        duration_ms INTEGER,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_social_attempt_sequence UNIQUE (target_id, sequence),
        CONSTRAINT ck_social_attempt_counters CHECK (sequence > 0 AND lease_epoch >= 0 AND estimated_cost_microusd >= 0),
        FOREIGN KEY(target_id) REFERENCES social_post_targets (id),
        UNIQUE (operation_id)
    )
    """))
    op.execute(sa.text("""
    ALTER TABLE social_accounts ADD CONSTRAINT fk_social_account_lease_target FOREIGN KEY(publish_lease_target_id) REFERENCES social_post_targets (id)
    """))
    op.execute(sa.text("""
    CREATE INDEX ix_social_account_connection ON social_accounts (connection_state)
    """))
    op.execute(sa.text("""
    CREATE INDEX ix_social_receipt_expiry ON social_command_receipts (expires_at)
    """))
    op.execute(sa.text("""
    CREATE INDEX ix_social_asset_state ON social_media_assets (state)
    """))
    op.execute(sa.text("""
    ALTER TABLE social_posts ADD CONSTRAINT fk_social_current_revision FOREIGN KEY(current_revision_id, id) REFERENCES social_post_revisions (id, post_id) DEFERRABLE INITIALLY DEFERRED
    """))
    op.execute(sa.text("""
    CREATE INDEX ix_social_post_editorial_updated ON social_posts (editorial_state, updated_at)
    """))
    op.execute(sa.text("""
    CREATE INDEX ix_social_worker_heartbeat ON social_worker_heartbeats (heartbeat_at)
    """))
    op.execute(sa.text("""
    CREATE INDEX ix_social_publication_schedule ON social_publications (scheduled_for)
    """))
    op.execute(sa.text("""
    CREATE UNIQUE INDEX uq_social_publication_active_post ON social_publications (post_id) WHERE revoked_at IS NULL
    """))
    op.execute(sa.text("""
    CREATE INDEX ix_social_target_due ON social_post_targets (next_action_at, id) WHERE state IN ('queued','retry_wait','processing','reconciling')
    """))
    op.execute(sa.text("""
    CREATE INDEX ix_social_target_expired_lease ON social_post_targets (lease_expires_at) WHERE lease_token IS NOT NULL
    """))
    op.execute(sa.text("""
    CREATE UNIQUE INDEX uq_social_target_remote ON social_post_targets (account_id, primary_remote_id) WHERE primary_remote_id IS NOT NULL
    """))
    op.execute(sa.text("""
    CREATE INDEX ix_social_audit_actor_time ON social_audit_events (actor_id, created_at)
    """))
    op.execute(sa.text("""
    CREATE INDEX ix_social_audit_post_time ON social_audit_events (post_id, created_at)
    """))
    op.execute(sa.text("""
    CREATE INDEX ix_social_attempt_target_time ON social_publish_attempts (target_id, created_at)
    """))
    op.execute(sa.text("""
    CREATE FUNCTION social_deny_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Social history is immutable' USING ERRCODE = '23514'; END $$;
    CREATE TRIGGER social_revision_immutable BEFORE UPDATE OR DELETE ON social_post_revisions FOR EACH ROW EXECUTE FUNCTION social_deny_history_mutation();
    CREATE TRIGGER social_audit_immutable BEFORE UPDATE OR DELETE ON social_audit_events FOR EACH ROW EXECUTE FUNCTION social_deny_history_mutation();
    CREATE FUNCTION social_guard_target_payload() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
     IF ROW(NEW.publication_id, NEW.account_id, NEW.resolved_payload, NEW.payload_hash, NEW.capability_version)
        IS DISTINCT FROM ROW(OLD.publication_id, OLD.account_id, OLD.resolved_payload, OLD.payload_hash, OLD.capability_version)
     THEN RAISE EXCEPTION 'Approved target payload is immutable' USING ERRCODE = '23514'; END IF;
     RETURN NEW;
    END $$;
    CREATE TRIGGER social_target_payload_immutable BEFORE UPDATE ON social_post_targets FOR EACH ROW EXECUTE FUNCTION social_guard_target_payload();
    CREATE FUNCTION social_guard_authorization() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
     IF ROW(NEW.post_id, NEW.revision_id, NEW.authorization_kind, NEW.approved_by, NEW.approved_at, NEW.policy_id, NEW.policy_version, NEW.approved_hash)
        IS DISTINCT FROM ROW(OLD.post_id, OLD.revision_id, OLD.authorization_kind, OLD.approved_by, OLD.approved_at, OLD.policy_id, OLD.policy_version, OLD.approved_hash)
     THEN RAISE EXCEPTION 'Publication authorization is immutable' USING ERRCODE = '23514'; END IF;
     RETURN NEW;
    END $$;
    CREATE TRIGGER social_publication_authorization_immutable BEFORE UPDATE ON social_publications FOR EACH ROW EXECUTE FUNCTION social_guard_authorization();
    CREATE FUNCTION social_guard_ready_asset() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
     IF (OLD.state = 'ready' OR EXISTS (SELECT 1 FROM social_revision_assets ra JOIN social_publications p ON p.revision_id = ra.revision_id WHERE ra.asset_id = OLD.id)) AND ROW(NEW.storage_provider, NEW.bucket, NEW.storage_key, NEW.sha256, NEW.mime_type, NEW.byte_size, NEW.width, NEW.height, NEW.duration_ms, NEW.frame_rate, NEW.codec_metadata)
        IS DISTINCT FROM ROW(OLD.storage_provider, OLD.bucket, OLD.storage_key, OLD.sha256, OLD.mime_type, OLD.byte_size, OLD.width, OLD.height, OLD.duration_ms, OLD.frame_rate, OLD.codec_metadata)
     THEN RAISE EXCEPTION 'Ready asset bytes and identity are immutable' USING ERRCODE = '23514'; END IF;
     RETURN NEW;
    END $$;
    CREATE TRIGGER social_ready_asset_immutable BEFORE UPDATE ON social_media_assets FOR EACH ROW EXECUTE FUNCTION social_guard_ready_asset();
    """))
    for table in SOCIAL_TABLE_NAMES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        for role in ("anon", "authenticated"):
            # Supabase defaults may grant browser roles access; local roles are optional.
            op.execute(sa.text(f"""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                        EXECUTE 'REVOKE ALL ON {table} FROM {role}';
                    END IF;
                END $$
            """))


def downgrade():
    bind = op.get_bind()
    # Serialize the empty-history decision with concurrent API/worker writers.
    bind.execute(sa.text("LOCK TABLE " + ", ".join(SOCIAL_TABLE_NAMES) + " IN ACCESS EXCLUSIVE MODE"))
    for table in SOCIAL_TABLE_NAMES:
        if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM " + table + " LIMIT 1)")).scalar():
            raise RuntimeError("Social history exists; export and reconcile before removing schema")
    op.execute(sa.text('DROP FUNCTION social_deny_history_mutation() CASCADE'))
    op.execute(sa.text('DROP FUNCTION social_guard_target_payload() CASCADE'))
    op.execute(sa.text('DROP FUNCTION social_guard_authorization() CASCADE'))
    op.execute(sa.text('DROP FUNCTION social_guard_ready_asset() CASCADE'))
    op.execute(sa.text("DROP TABLE " + ", ".join(SOCIAL_TABLE_NAMES) + " CASCADE"))

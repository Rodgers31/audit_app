"""Private indexed ownership and immutable callback receipts; no backfill/enablement."""
from alembic import op
import sqlalchemy as sa

revision = 'd8f4a619b203'
down_revision = 'b73e19a4f602'
branch_labels = None
depends_on = None

TABLES = ('social_privacy_ownership', 'social_privacy_receipts', 'social_privacy_request_variants')
DDL = (
    """
CREATE TABLE social_privacy_ownership (
	id UUID NOT NULL,
	app_id VARCHAR(64) NOT NULL,
	digest_version VARCHAR(32) NOT NULL,
	subject_digest VARCHAR(64) NOT NULL,
	reference_key TEXT NOT NULL,
	flow_id UUID NOT NULL,
	credential_id UUID,
	credential_version BIGINT,
	account_id UUID,
	page_id VARCHAR(64),
	generation_at TIMESTAMP WITH TIME ZONE NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_social_privacy_subject CHECK (length(app_id) BETWEEN 1 AND 64 AND length(subject_digest)=64 AND length(digest_version) BETWEEN 1 AND 32),
	CONSTRAINT ck_social_privacy_credential CHECK ((credential_id IS NULL) = (credential_version IS NULL) AND (credential_version IS NULL OR credential_version > 0)),
	CONSTRAINT ck_social_privacy_reference CHECK (credential_id IS NOT NULL OR (account_id IS NULL AND page_id IS NULL)),
	UNIQUE (reference_key),
	FOREIGN KEY(flow_id) REFERENCES social_oauth_flows (id),
	FOREIGN KEY(credential_id) REFERENCES social_credentials (id),
	FOREIGN KEY(account_id) REFERENCES social_accounts (id)
)
    """,
    """
CREATE INDEX ix_social_privacy_credential ON social_privacy_ownership (credential_id, credential_version)
    """,
    """
CREATE INDEX ix_social_privacy_flow ON social_privacy_ownership (flow_id)
    """,
    """
CREATE INDEX ix_social_privacy_subject ON social_privacy_ownership (app_id, digest_version, subject_digest, generation_at)
    """,
    """
CREATE TABLE social_privacy_receipts (
	id UUID NOT NULL,
	app_id VARCHAR(64) NOT NULL,
	kind TEXT NOT NULL,
	digest_version VARCHAR(32) NOT NULL,
	subject_digest VARCHAR(64) NOT NULL,
	event_key VARCHAR(64) NOT NULL,
	request_fingerprint VARCHAR(64) NOT NULL,
	issued_at BIGINT,
	provider_expires BIGINT,
	received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	affected JSONB NOT NULL,
	resolution TEXT NOT NULL,
	state TEXT NOT NULL,
	audit_id UUID NOT NULL,
	confirmation_hash VARCHAR(64),
	confirmation_key_version TEXT,
	encrypted_confirmation BYTEA,
	status_url_base TEXT,
	PRIMARY KEY (id),
	CONSTRAINT uq_social_privacy_event UNIQUE (app_id, kind, digest_version, event_key),
	CONSTRAINT ck_social_privacy_receipt_state CHECK (kind IN ('data_deletion','deauthorization') AND state IN ('pending_retention_review','blocked_future_mutations','ownership_unresolved')),
	CONSTRAINT ck_social_privacy_confirmation CHECK ((kind='data_deletion' AND confirmation_hash IS NOT NULL AND encrypted_confirmation IS NOT NULL AND confirmation_key_version IS NOT NULL AND status_url_base IS NOT NULL) OR (kind='deauthorization' AND confirmation_hash IS NULL AND encrypted_confirmation IS NULL AND confirmation_key_version IS NULL AND status_url_base IS NULL)),
	FOREIGN KEY(audit_id) REFERENCES social_audit_events (id),
	UNIQUE (confirmation_hash)
)
    """,
    """
CREATE INDEX ix_social_privacy_receipt_subject ON social_privacy_receipts (app_id, kind, digest_version, subject_digest)
    """,
    """
CREATE TABLE social_privacy_request_variants (
	id UUID NOT NULL,
	app_id VARCHAR(64) NOT NULL,
	kind TEXT NOT NULL,
	fingerprint VARCHAR(64) NOT NULL,
	receipt_id UUID NOT NULL,
	received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_social_privacy_variant UNIQUE (app_id, kind, fingerprint),
	FOREIGN KEY(receipt_id) REFERENCES social_privacy_receipts (id)
)
    """,
)


def upgrade():
    op.add_column('social_oauth_flows', sa.Column('privacy_blocked_at', sa.DateTime(timezone=True)))
    for statement in DDL:
        op.execute(sa.text(statement))
    for table in TABLES:
        op.execute(sa.text(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON {table} FROM PUBLIC'))
        for role in ('anon', 'authenticated'):
            op.execute(sa.text(f"""DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                    EXECUTE 'REVOKE ALL ON {table} FROM {role}';
                END IF;
            END $$"""))
    op.execute(sa.text("""CREATE FUNCTION social_privacy_immutable() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'Privacy history requires an approved retention migration' USING ERRCODE='23514'; END;
        $$ LANGUAGE plpgsql"""))
    for table in TABLES:
        op.execute(sa.text(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION social_privacy_immutable()'))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text('LOCK TABLE social_oauth_flows, ' + ', '.join(TABLES) + ' IN ACCESS EXCLUSIVE MODE'))
    if any(bind.execute(sa.text('SELECT EXISTS (SELECT 1 FROM ' + table + ' LIMIT 1)')).scalar() for table in TABLES):
        raise RuntimeError('Privacy history exists; approve retention and export before removing schema')
    if bind.execute(sa.text('SELECT EXISTS (SELECT 1 FROM social_oauth_flows WHERE privacy_blocked_at IS NOT NULL LIMIT 1)')).scalar():
        raise RuntimeError('Privacy blocked flows exist; reconcile before removing schema')
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute(sa.text('DROP FUNCTION social_privacy_immutable()'))
    op.drop_column('social_oauth_flows', 'privacy_blocked_at')

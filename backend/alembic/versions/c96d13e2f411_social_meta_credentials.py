"""Encrypted Meta grants and durable session-bound account connection flows.

No app registration, OAuth exchange, live secrets or publishing is enabled.
Downgrade refuses removal once credential/flow history exists.
"""
from alembic import op
import sqlalchemy as sa

revision = "c96d13e2f411"
down_revision = "f38c61a9d203"
branch_labels = None
depends_on = None

TABLES = ("social_oauth_flows", "social_credentials")
DDL = (
    """
CREATE TABLE social_credentials (
    id UUID NOT NULL, 
    provider TEXT NOT NULL, 
    credential_kind TEXT NOT NULL, 
    parent_credential_id UUID, 
    encrypted_bundle BYTEA NOT NULL, 
    key_version TEXT NOT NULL, 
    access_expires_at TIMESTAMP WITH TIME ZONE, 
    refresh_expires_at TIMESTAMP WITH TIME ZONE, 
    data_access_expires_at TIMESTAMP WITH TIME ZONE, 
    version BIGINT DEFAULT '1' NOT NULL, 
    refresh_lease_token UUID, 
    refresh_lease_expires_at TIMESTAMP WITH TIME ZONE, 
    last_refresh_at TIMESTAMP WITH TIME ZONE, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_social_credential_kind CHECK (provider = 'meta' AND credential_kind IN ('facebook_user','facebook_page')), 
    CONSTRAINT ck_social_credential_parent CHECK ((credential_kind = 'facebook_user' AND parent_credential_id IS NULL) OR (credential_kind = 'facebook_page' AND parent_credential_id IS NOT NULL)), 
    CONSTRAINT ck_social_credential_envelope CHECK (version > 0 AND length(encrypted_bundle) > 0 AND length(key_version) > 0), 
    CONSTRAINT ck_social_credential_lease CHECK ((refresh_lease_token IS NULL) = (refresh_lease_expires_at IS NULL)), 
    CONSTRAINT ck_social_meta_no_refresh CHECK (refresh_expires_at IS NULL), 
    FOREIGN KEY(parent_credential_id) REFERENCES social_credentials (id)
)
    """,
    """
CREATE INDEX ix_social_credential_access_expiry ON social_credentials (access_expires_at)
    """,
    """
CREATE INDEX ix_social_credential_data_expiry ON social_credentials (data_access_expires_at)
    """,
    """
CREATE INDEX ix_social_credential_parent ON social_credentials (parent_credential_id)
    """,
    """
CREATE TABLE social_oauth_flows (
    id UUID NOT NULL, 
    actor_id UUID NOT NULL, 
    provider TEXT NOT NULL, 
    state_hash VARCHAR(64) NOT NULL, 
    binding_hash VARCHAR(64) NOT NULL, 
    encrypted_verifier BYTEA, 
    encrypted_pending_grant BYTEA, 
    key_version TEXT NOT NULL, 
    redirect_uri TEXT NOT NULL, 
    return_path TEXT NOT NULL, 
    reconnect_account_id UUID, 
    status TEXT NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    consumed_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_social_oauth_status CHECK (provider = 'meta' AND status IN ('initiated','exchanging','awaiting_selection','completed','failed','expired')), 
    CONSTRAINT ck_social_oauth_hashes CHECK (length(state_hash) = 64 AND length(binding_hash) = 64), 
    CONSTRAINT ck_social_oauth_return CHECK (return_path = '/admin/social/accounts'), 
    CONSTRAINT ck_social_oauth_secrets CHECK ((status = 'initiated' AND consumed_at IS NULL AND encrypted_verifier IS NOT NULL AND encrypted_pending_grant IS NULL) OR (status = 'exchanging' AND consumed_at IS NOT NULL AND encrypted_verifier IS NULL AND encrypted_pending_grant IS NULL) OR (status = 'awaiting_selection' AND consumed_at IS NOT NULL AND encrypted_verifier IS NULL AND encrypted_pending_grant IS NOT NULL) OR (status IN ('completed','failed','expired') AND encrypted_verifier IS NULL AND encrypted_pending_grant IS NULL)), 
    UNIQUE (state_hash), 
    FOREIGN KEY(reconnect_account_id) REFERENCES social_accounts (id)
)
    """,
    """
CREATE INDEX ix_social_oauth_actor ON social_oauth_flows (actor_id, created_at)
    """,
    """
CREATE INDEX ix_social_oauth_expiry ON social_oauth_flows (expires_at)
    """,
)


def upgrade():
    for statement in DDL:
        op.execute(sa.text(statement))
    op.create_foreign_key('fk_social_account_credential', 'social_accounts', 'social_credentials', ['credential_id'], ['id'])
    for table in TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"REVOKE ALL ON {table} FROM PUBLIC"))
        for role in ("anon", "authenticated"):
            op.execute(sa.text(f"""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                        EXECUTE 'REVOKE ALL ON {table} FROM {role}';
                    END IF;
                END $$
            """))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE social_accounts, " + ", ".join(TABLES) + " IN ACCESS EXCLUSIVE MODE"))
    if any(bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM " + table + " LIMIT 1)")).scalar() for table in TABLES):
        raise RuntimeError("Social connection history exists; export and reconcile before removing schema")
    op.drop_constraint('fk_social_account_credential', 'social_accounts', type_='foreignkey')
    for table in TABLES:
        op.drop_table(table)

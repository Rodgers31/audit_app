"""Durable Threads/X OAuth, provider grants and disabled X budget ledger."""
from alembic import op
import sqlalchemy as sa

revision = 'a703b15a0001'
down_revision = 'a545b14a0001'
branch_labels = None
depends_on = None
TABLES = ('social_platform_oauth_flows', 'social_platform_credentials', 'social_platform_budgets', 'social_platform_connection_budgets', 'social_platform_event_inbox')


def upgrade():
    op.execute("SET LOCAL lock_timeout='2s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("""CREATE TABLE social_platform_oauth_flows (
        id uuid PRIMARY KEY, platform text NOT NULL CHECK(platform IN ('threads','x','tiktok')),
        actor_id uuid NOT NULL, binding_hash varchar(64) NOT NULL,
        state_hash varchar(64) NOT NULL UNIQUE, redirect_uri text NOT NULL,
        status text NOT NULL DEFAULT 'initiated', encrypted_secret bytea,
        key_version text NOT NULL, expires_at timestamptz NOT NULL,
        consumed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_platform_oauth_status CHECK(status IN ('initiated','exchanging','awaiting_confirmation','completed','failed','expired')),
        CONSTRAINT ck_platform_oauth_hashes CHECK(length(state_hash)=64 AND length(binding_hash)=64),
        CONSTRAINT ck_platform_oauth_secret CHECK(
          (status='initiated' AND consumed_at IS NULL AND encrypted_secret IS NOT NULL) OR
          (status='awaiting_confirmation' AND consumed_at IS NOT NULL AND encrypted_secret IS NOT NULL) OR
          (status IN ('exchanging','completed','failed','expired') AND encrypted_secret IS NULL)))""")
    op.create_index('ix_platform_oauth_expiry', TABLES[0], ['expires_at'])
    op.execute("""CREATE TABLE social_platform_credentials (
        id uuid PRIMARY KEY, account_id uuid NOT NULL UNIQUE REFERENCES social_accounts(id),
        platform text NOT NULL CHECK(platform IN ('threads','x','tiktok')), encrypted_bundle bytea NOT NULL,
        key_version text NOT NULL, version bigint NOT NULL DEFAULT 1,
        access_expires_at timestamptz NOT NULL, data_access_expires_at timestamptz, refresh_expires_at timestamptz,
        issued_at timestamptz NOT NULL, refresh_claim uuid, revoked_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_platform_credential_envelope CHECK(version>0 AND length(encrypted_bundle)>0 AND length(key_version)>0),
        CONSTRAINT ck_threads_no_refresh_expiry CHECK(platform<>'threads' OR refresh_expires_at IS NULL))""")
    op.execute("""CREATE TABLE social_platform_budgets (
        account_id uuid PRIMARY KEY REFERENCES social_accounts(id),
        access_verified boolean NOT NULL DEFAULT false, enabled boolean NOT NULL DEFAULT false,
        limit_microusd bigint NOT NULL DEFAULT 0, reserved_microusd bigint NOT NULL DEFAULT 0,
        spent_microusd bigint NOT NULL DEFAULT 0, version bigint NOT NULL DEFAULT 1,
        CONSTRAINT ck_social_platform_budget_bounds CHECK(limit_microusd>=0 AND reserved_microusd>=0
          AND spent_microusd>=0 AND reserved_microusd+spent_microusd<=limit_microusd AND version>0))""")
    op.execute("""CREATE TABLE social_platform_connection_budgets (
        client_key varchar(64) PRIMARY KEY CHECK(length(client_key)=64),
        enabled boolean NOT NULL DEFAULT false, access_verified boolean NOT NULL DEFAULT false,
        limit_microusd bigint NOT NULL DEFAULT 0, reserved_microusd bigint NOT NULL DEFAULT 0,
        version bigint NOT NULL DEFAULT 1,
        CONSTRAINT ck_platform_connection_budget_bounds CHECK(reserved_microusd>=0 AND limit_microusd>=reserved_microusd AND version>0))""")
    op.execute("""CREATE TABLE social_platform_event_inbox (
        id uuid PRIMARY KEY, provider text NOT NULL,
        dedupe_hash varchar(64) NOT NULL, account_id uuid NOT NULL REFERENCES social_accounts(id),
        event_type text NOT NULL, remote_id varchar(256) NOT NULL, post_id varchar(64),
        event_at timestamptz NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
        processed_at timestamptz, processing_state text NOT NULL DEFAULT 'pending',
        CONSTRAINT uq_social_platform_event_dedupe UNIQUE(provider,dedupe_hash),
        CONSTRAINT ck_social_platform_event_provider CHECK(provider IN ('threads','tiktok')),
        CONSTRAINT ck_social_platform_event_state CHECK(processing_state IN ('pending','processed','unmatched')))""")
    op.create_index('ix_social_platform_event_pending',TABLES[4],['processing_state','received_at','id'])
    op.create_index('ix_social_platform_event_retention',TABLES[4],['received_at'])
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON {table} FROM PUBLIC')
        for role in ('anon', 'authenticated'):
            op.execute(f"DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN EXECUTE 'REVOKE ALL ON {table} FROM {role}'; END IF; END $$")


def downgrade():
    op.execute("SET LOCAL lock_timeout='2s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    conn = op.get_bind()
    conn.execute(sa.text('LOCK TABLE ' + ','.join(TABLES) + ' IN ACCESS EXCLUSIVE MODE'))
    conn.execute(sa.text('SET LOCAL row_security=off'))
    if any(conn.execute(sa.text('SELECT EXISTS(SELECT 1 FROM ' + table + ')')).scalar_one() for table in TABLES):
        raise RuntimeError('Retained provider grants, authorization state or budgets prevent destructive downgrade')
    for table in reversed(TABLES):
        op.drop_table(table)

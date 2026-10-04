"""Private inspected media intake and bounded storage reservations.

No bucket, credentials, runtime flags or maintenance process is provisioned.
Downgrade refuses to remove recorded uploads or budgets.
"""
from alembic import op
import sqlalchemy as sa

revision = "a42b86e1d310"
down_revision = "c96d13e2f411"
branch_labels = None
depends_on = None

TABLES = ("social_media_uploads", "social_media_budgets")
DDL = (
    """
CREATE TABLE social_media_budgets (
	scope TEXT NOT NULL,
	bytes_used BIGINT NOT NULL,
	pending_count INTEGER NOT NULL,
	PRIMARY KEY (scope),
	CONSTRAINT ck_social_media_budget_nonnegative CHECK (bytes_used >= 0 AND pending_count >= 0)
)
    """,
    """
CREATE TABLE social_media_uploads (
	asset_id UUID NOT NULL,
	actor_id UUID NOT NULL,
	initiation_key UUID NOT NULL,
	request_hash VARCHAR(64) NOT NULL,
	quarantine_key TEXT NOT NULL,
	declared_mime_type TEXT NOT NULL,
	declared_size BIGINT NOT NULL,
	version BIGINT NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	completion_key UUID,
	completion_hash VARCHAR(64),
	reservation_released INTEGER NOT NULL,
	quarantine_cleaned INTEGER NOT NULL,
	reserved_bytes BIGINT NOT NULL,
	finalization_epoch BIGINT,
	finalization_settled INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (asset_id),
	CONSTRAINT uq_social_media_intent UNIQUE (actor_id, initiation_key),
	CONSTRAINT ck_social_media_upload_bounds CHECK (declared_size > 0 AND version > 0 AND reserved_bytes >= 0 AND reservation_released IN (0,1) AND quarantine_cleaned IN (0,1) AND finalization_settled IN (0,1) AND (finalization_epoch IS NULL OR finalization_epoch > 0)),
	FOREIGN KEY(asset_id) REFERENCES social_media_assets (id),
	UNIQUE (quarantine_key)
)
    """,
    """
CREATE INDEX ix_social_media_upload_expiry ON social_media_uploads (expires_at)
    """,
)


def upgrade():
    for statement in DDL:
        op.execute(sa.text(statement))
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
    bind.execute(sa.text("LOCK TABLE " + ", ".join(TABLES) + " IN ACCESS EXCLUSIVE MODE"))
    if any(bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM " + table + " LIMIT 1)")).scalar() for table in TABLES):
        raise RuntimeError("Social media history exists; export and reconcile before removing schema")
    for table in TABLES:
        op.drop_table(table)

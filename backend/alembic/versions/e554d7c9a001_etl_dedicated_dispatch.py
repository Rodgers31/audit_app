"""Add dedicated ETL commands, worker lease and durable domain exclusion.

No existing job is converted, claimed or cleaned up. Downgrade refuses history.
"""
from alembic import op
import sqlalchemy as sa

revision = "e554d7c9a001"
down_revision = "d8f4a619b203"
branch_labels = None
depends_on = None

TABLES = ('etl_dispatch_commands', 'etl_dispatch_worker', 'etl_dispatch_domains')
DDL = (
    """
CREATE TABLE etl_dispatch_commands (
	id UUID NOT NULL,
	actor_id VARCHAR(64) NOT NULL,
	idempotency_key UUID NOT NULL,
	source VARCHAR(20) NOT NULL,
	domain VARCHAR(100) NOT NULL,
	dry_run BOOLEAN NOT NULL,
	generation UUID NOT NULL,
	claim_token UUID,
	execution_started BOOLEAN DEFAULT false NOT NULL,
	status VARCHAR(20) NOT NULL,
	version BIGINT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE,
	finished_at TIMESTAMP WITH TIME ZONE,
	job_id INTEGER,
	outcome VARCHAR(30),
	audit_id INTEGER NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_etl_dispatch_actor_key UNIQUE (actor_id, idempotency_key),
	CONSTRAINT ck_etl_dispatch_mapping CHECK (source = 'oag' AND domain = 'audits'),
	CONSTRAINT ck_etl_dispatch_version CHECK (version BETWEEN 1 AND 9007199254740991),
	CONSTRAINT ck_etl_dispatch_times CHECK (created_at <= updated_at AND (started_at IS NULL OR created_at <= started_at) AND (finished_at IS NULL OR (finished_at <= updated_at AND (started_at IS NULL OR started_at <= finished_at)))),
	CONSTRAINT ck_etl_dispatch_state CHECK ((status='queued' AND started_at IS NULL AND finished_at IS NULL AND job_id IS NULL AND outcome IS NULL AND claim_token IS NULL AND NOT execution_started) OR (status='running' AND started_at IS NOT NULL AND finished_at IS NULL AND outcome IS NULL AND claim_token IS NOT NULL) OR (status='completed' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND job_id IS NOT NULL AND job_id > 0 AND outcome IS NOT NULL AND outcome='completed') OR (status='failed' AND finished_at IS NOT NULL AND outcome IS NOT NULL AND outcome='failed') OR (status='interrupted' AND started_at IS NOT NULL AND finished_at IS NOT NULL AND outcome IS NOT NULL AND outcome='execution_unverified')),
	FOREIGN KEY(job_id) REFERENCES ingestion_jobs (id),
	UNIQUE (audit_id),
	FOREIGN KEY(audit_id) REFERENCES admin_audit_log (id)
)

""",
    """CREATE INDEX ix_etl_dispatch_history ON etl_dispatch_commands (created_at, id)""",
    """CREATE INDEX ix_etl_dispatch_queue ON etl_dispatch_commands (status, created_at)""",
    """
CREATE TABLE etl_dispatch_worker (
	id SERIAL NOT NULL,
	generation UUID NOT NULL,
	last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	ready BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_etl_dispatch_single_worker CHECK (id = 1),
	CONSTRAINT ck_etl_dispatch_lease_times CHECK (last_seen_at < expires_at)
)

""",
    """
CREATE TABLE etl_dispatch_domains (
	domain VARCHAR(100) NOT NULL,
	command_id UUID,
	claim_token UUID,
	PRIMARY KEY (domain),
	CONSTRAINT ck_etl_dispatch_domain CHECK (domain = 'audits'),
	CONSTRAINT ck_etl_dispatch_domain_claim CHECK ((command_id IS NULL) = (claim_token IS NULL)),
	UNIQUE (command_id),
	FOREIGN KEY(command_id) REFERENCES etl_dispatch_commands (id)
)

""",
)

def upgrade():
    for statement in DDL:
        op.execute(sa.text(statement))
    for table in TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"REVOKE ALL ON {table} FROM PUBLIC"))
        for role in ("anon", "authenticated"):
            op.execute(sa.text(f"""DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                    EXECUTE 'REVOKE ALL ON {table} FROM {role}';
                END IF;
            END $$"""))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE " + ", ".join(TABLES) + " IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM etl_dispatch_commands)")):
        raise RuntimeError("Dispatch history exists; reconcile and export before removing schema")
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM etl_dispatch_worker WHERE ready AND expires_at > clock_timestamp())")):
        raise RuntimeError("Stop dedicated worker before removing schema")
    for table in reversed(TABLES):
        op.drop_table(table)

"""Shared native/dispatch domain ownership; no activation or claim clearing."""
from alembic import op
import sqlalchemy as sa

revision = "e572b8c9a001"
down_revision = "e554d7c9a001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("""CREATE TABLE seeding_domain_claims (
        id UUID PRIMARY KEY,
        domain VARCHAR(100) NOT NULL,
        kind VARCHAR(20) NOT NULL,
        command_id UUID UNIQUE REFERENCES etl_dispatch_commands(id),
        acquired_at TIMESTAMP WITH TIME ZONE NOT NULL,
        entered_at TIMESTAMP WITH TIME ZONE,
        entry_id UUID UNIQUE,
        returned_at TIMESTAMP WITH TIME ZONE,
        released_at TIMESTAMP WITH TIME ZONE,
        job_id INTEGER REFERENCES ingestion_jobs(id),
        reconciled_by VARCHAR(64),
        reconciliation TEXT,
        CONSTRAINT ck_seeding_claim_domain CHECK (length(domain) BETWEEN 1 AND 100),
        CONSTRAINT ck_seeding_claim_kind CHECK ((kind='native' AND command_id IS NULL) OR (kind='dispatch' AND command_id IS NOT NULL)),
        CONSTRAINT ck_seeding_claim_receipt CHECK ((returned_at IS NULL AND job_id IS NULL AND (released_at IS NULL OR (acquired_at <= released_at AND (entered_at IS NULL OR reconciled_by IS NOT NULL)))) OR (returned_at IS NOT NULL AND job_id IS NOT NULL AND job_id > 0 AND acquired_at <= returned_at AND (released_at IS NULL OR returned_at <= released_at))),
        -- Operator release after reconciliation; no runtime path writes these.
        CONSTRAINT ck_seeding_claim_reconciliation CHECK ((reconciled_by IS NULL) = (reconciliation IS NULL) AND (reconciled_by IS NULL OR (released_at IS NOT NULL AND length(reconciled_by) <= 64 AND length(reconciliation) <= 4000 AND length(ltrim(rtrim(reconciled_by))) >= 1 AND length(ltrim(rtrim(reconciliation))) >= 1))),
        CONSTRAINT ck_seeding_claim_entry CHECK ((entered_at IS NULL) = (entry_id IS NULL) AND (kind <> 'native' OR entered_at IS NOT NULL) AND (entered_at IS NULL OR acquired_at <= entered_at) AND (returned_at IS NULL OR (entered_at IS NOT NULL AND entered_at <= returned_at)))
    )"""))
    op.execute(sa.text("CREATE UNIQUE INDEX uq_seeding_active_domain ON seeding_domain_claims(domain) WHERE released_at IS NULL"))
    # Preserve interrupted Batch 7 exclusions, without assuming writer death.
    # A command that started may have run work: record it as entered (with an
    # entry nobody holds) so it can be neither acknowledged nor treated as
    # never-entered; only operator reconciliation can release it.
    op.execute(sa.text("""INSERT INTO seeding_domain_claims(id,domain,kind,command_id,acquired_at,entered_at,entry_id)
        SELECT d.claim_token,d.domain,'dispatch',d.command_id,c.started_at,
            CASE WHEN c.execution_started THEN c.started_at END,
            CASE WHEN c.execution_started THEN gen_random_uuid() END
        FROM etl_dispatch_domains d JOIN etl_dispatch_commands c ON c.id=d.command_id
        WHERE d.command_id IS NOT NULL"""))
    op.execute(sa.text("ALTER TABLE seeding_domain_claims ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("REVOKE ALL ON seeding_domain_claims FROM PUBLIC"))
    for role in ("anon", "authenticated"):
        op.execute(sa.text(f"""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                EXECUTE 'REVOKE ALL ON seeding_domain_claims FROM {role}';
            END IF;
        END $$"""))


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE seeding_domain_claims IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM seeding_domain_claims)")):
        raise RuntimeError("Seeding ownership history exists; reconcile and export before removing schema")
    op.drop_table("seeding_domain_claims")

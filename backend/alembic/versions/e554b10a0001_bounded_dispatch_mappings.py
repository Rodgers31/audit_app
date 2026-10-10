"""Bounded native dispatch mappings; no activation or history conversion."""
from alembic import op
import sqlalchemy as sa

revision = "e554b10a0001"
down_revision = "e583b9c9a001"
branch_labels = None
depends_on = None

MAPPING = "(source='oag' AND domain='audits') OR (source='treasury' AND domain='fiscal_summary') OR (source='cob' AND domain='counties_budget') OR (source='knbs' AND domain='population')"
DOMAINS = "domain IN ('audits','fiscal_summary','counties_budget','population')"


def stopped():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE etl_dispatch_worker, etl_dispatch_domains, etl_dispatch_commands IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM etl_dispatch_worker WHERE ready)")):
        raise RuntimeError("Stop dedicated worker before changing dispatch mappings")
    return bind


def upgrade():
    stopped()
    op.add_column("etl_dispatch_domains", sa.Column("ready", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.drop_constraint("ck_etl_dispatch_mapping", "etl_dispatch_commands", type_="check")
    op.create_check_constraint("ck_etl_dispatch_mapping", "etl_dispatch_commands", MAPPING)
    op.drop_constraint("ck_etl_dispatch_domain", "etl_dispatch_domains", type_="check")
    op.create_check_constraint("ck_etl_dispatch_domain", "etl_dispatch_domains", DOMAINS)
    # Existing tables retain their RLS, revocations, indexes and complete history.


def downgrade():
    bind = stopped()
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM etl_dispatch_commands WHERE source <> 'oag')")) or bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM etl_dispatch_domains WHERE domain <> 'audits')")):
        raise RuntimeError("New mapping history exists; reconcile and export before downgrade")
    op.drop_constraint("ck_etl_dispatch_mapping", "etl_dispatch_commands", type_="check")
    op.create_check_constraint("ck_etl_dispatch_mapping", "etl_dispatch_commands", "source='oag' AND domain='audits'")
    op.drop_constraint("ck_etl_dispatch_domain", "etl_dispatch_domains", type_="check")
    op.create_check_constraint("ck_etl_dispatch_domain", "etl_dispatch_domains", "domain='audits'")
    op.drop_column("etl_dispatch_domains", "ready")

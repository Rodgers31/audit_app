"""Opt-in native CRA recommendation mapping; preserve prior source contracts."""
from alembic import op
import sqlalchemy as sa

revision = "e602b11a0001"
down_revision = "e554b10a0001"
branch_labels = None
depends_on = None

PREVIOUS_MAPPING = "(source='oag' AND domain='audits') OR (source='treasury' AND domain='fiscal_summary') OR (source='cob' AND domain='counties_budget') OR (source='knbs' AND domain='population')"
PREVIOUS_DOMAINS = "domain IN ('audits','fiscal_summary','counties_budget','population')"


def stopped():
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE etl_dispatch_worker, etl_dispatch_domains, etl_dispatch_commands IN ACCESS EXCLUSIVE MODE"))
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM etl_dispatch_worker WHERE ready)")):
        raise RuntimeError("Stop dedicated worker before changing native source mappings")
    return bind


def constraints(mapping, domains):
    op.drop_constraint("ck_etl_dispatch_mapping", "etl_dispatch_commands", type_="check")
    op.create_check_constraint("ck_etl_dispatch_mapping", "etl_dispatch_commands", mapping)
    op.drop_constraint("ck_etl_dispatch_domain", "etl_dispatch_domains", type_="check")
    op.create_check_constraint("ck_etl_dispatch_domain", "etl_dispatch_domains", domains)


def upgrade():
    stopped()
    constraints(PREVIOUS_MAPPING + " OR (source='cra' AND domain='cra')",
                "domain IN ('audits','fiscal_summary','counties_budget','population','cra')")


def downgrade():
    bind = stopped()
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM etl_dispatch_commands WHERE source='cra')")) or bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM etl_dispatch_domains WHERE domain='cra')")):
        raise RuntimeError("CRA mapping history exists; reconcile and export before downgrade")
    constraints(PREVIOUS_MAPPING, PREVIOUS_DOMAINS)

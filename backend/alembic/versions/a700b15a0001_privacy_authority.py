"""Separate durable privacy authority and execution; no enablement or grants."""
from alembic import op
import sqlalchemy as sa

revision = 'a700b15a0001'
down_revision = 'a545b14a0001'
branch_labels = None
depends_on = None
TABLES = ('social_privacy_plans', 'social_privacy_decisions', 'social_privacy_executions', 'social_privacy_execution_events')


def upgrade():
    op.create_table(TABLES[0],
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('receipt_id', sa.Uuid(), sa.ForeignKey('social_privacy_receipts.id'), nullable=False),
        sa.Column('proposed_by', sa.Uuid(), nullable=False),
        sa.Column('policy_key', sa.Text(), nullable=False), sa.Column('policy_hash', sa.Text(), nullable=False),
        sa.Column('evidence', sa.Text(), nullable=False), sa.Column('scope', sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column('plan_hash', sa.Text(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('length(plan_hash)=64 AND length(policy_hash)=64', name='ck_privacy_plan_hash'))
    op.create_table(TABLES[1],
        sa.Column('id', sa.Uuid(), primary_key=True), sa.Column('plan_id', sa.Uuid(), sa.ForeignKey(TABLES[0]+'.id'), nullable=False, unique=True),
        sa.Column('approved_by', sa.Uuid(), nullable=False), sa.Column('plan_hash', sa.Text(), nullable=False),
        sa.Column('decision', sa.Text(), nullable=False), sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("decision IN ('approved','rejected')", name='ck_privacy_decision'))
    op.create_table(TABLES[2],
        sa.Column('id', sa.Uuid(), primary_key=True), sa.Column('plan_id', sa.Uuid(), sa.ForeignKey(TABLES[0]+'.id'), nullable=False, unique=True),
        sa.Column('state', sa.Text(), nullable=False), sa.Column('version', sa.BigInteger(), nullable=False, server_default='1'),
        sa.Column('result', sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("state IN ('prepared','executing','outcome_unknown','completed') AND version>0", name='ck_privacy_execution'))
    op.create_table(TABLES[3],
        sa.Column('id', sa.Uuid(), primary_key=True), sa.Column('execution_id', sa.Uuid(), sa.ForeignKey(TABLES[2]+'.id'), nullable=False),
        sa.Column('state', sa.Text(), nullable=False), sa.Column('details', sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for table in TABLES:
        op.execute(sa.text(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON {table} FROM PUBLIC'))
        for role in ('anon', 'authenticated'):
            op.execute(sa.text(f"""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN EXECUTE 'REVOKE ALL ON {table} FROM {role}'; END IF; END $$"""))
    # Existing worker/login contract is deliberately unchanged: no credential,
    # authority or execution access is granted to the delivery worker.
    for table in (TABLES[0], TABLES[1], TABLES[3]):
        op.execute(sa.text(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION social_privacy_immutable()'))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text('LOCK TABLE ' + ','.join(TABLES) + ' IN ACCESS EXCLUSIVE MODE'))
    if any(conn.execute(sa.text('SELECT EXISTS(SELECT 1 FROM '+table+' LIMIT 1)')).scalar() for table in TABLES):
        raise RuntimeError('Privacy authority/history exists; explicit retention review required')
    for table in reversed(TABLES):
        op.drop_table(table)

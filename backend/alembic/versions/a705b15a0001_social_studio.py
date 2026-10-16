"""Local editorial derivatives and provider-semantic metric history.

Lane candidate: coordinator serializes predecessor before integration.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = 'a705b15a0001'
down_revision = 'a545b14a0001'
branch_labels = None
depends_on = None
TABLES = ('social_render_jobs', 'social_metric_collections', 'social_metric_observations')


def upgrade():
    op.execute("SET LOCAL lock_timeout='2s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.create_table('social_render_jobs',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('revision_id', sa.Uuid(), sa.ForeignKey('social_post_revisions.id'), nullable=False),
        sa.Column('actor_id', sa.Uuid(), nullable=False),
        sa.Column('composition', pg.JSONB(), nullable=False),
        sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('retry_of_id', sa.Uuid(), sa.ForeignKey('social_render_jobs.id')),
        sa.Column('runtime_hash', sa.String(64)),
        sa.Column('state', sa.Text(), nullable=False),
        sa.Column('version', sa.BigInteger(), nullable=False),
        sa.Column('cancel_requested', sa.Integer(), nullable=False),
        sa.Column('token', sa.Uuid()),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.Column('sha256', sa.String(64)),
        sa.Column('inspection', pg.JSONB()),
        sa.Column('safe_error', sa.Text()),
        sa.Column('approved_sha256', sa.String(64)),
        sa.Column('approved_by', sa.Uuid()),
        sa.Column('approved_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('actor_id', 'input_hash', 'attempt', name='uq_social_render_input'),
        sa.CheckConstraint('(attempt=1 AND retry_of_id IS NULL) OR (attempt=2 AND retry_of_id IS NOT NULL)', name='ck_social_render_attempt'),
        sa.CheckConstraint("state IN ('queued','running','ready','failed','cancelled') AND version>0 AND cancel_requested IN (0,1)", name='ck_social_render_state'),
        sa.CheckConstraint("state<>'ready' OR (sha256 IS NOT NULL AND inspection IS NOT NULL AND runtime_hash IS NOT NULL)", name='ck_social_render_ready'),
        sa.CheckConstraint("approved_sha256 IS NULL OR (state='ready' AND approved_sha256=sha256 AND approved_by IS NOT NULL AND approved_at IS NOT NULL)", name='ck_social_render_approval'))
    op.create_index('ix_social_render_queue', 'social_render_jobs', ['state', 'created_at'])
    op.create_table('social_metric_collections',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('account_id', sa.Uuid(), sa.ForeignKey('social_accounts.id'), nullable=False),
        sa.Column('target_id', sa.Uuid(), sa.ForeignKey('social_post_targets.id'), nullable=False),
        sa.Column('platform', sa.Text(), nullable=False),
        sa.Column('remote_id', sa.Text(), nullable=False),
        sa.Column('state', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("state IN ('reserved','collected','unavailable','failed')", name='ck_social_metric_collection_state'))
    op.create_index('ix_social_metric_quota', 'social_metric_collections', ['account_id', 'created_at'])
    op.create_index('ix_social_metric_target', 'social_metric_collections', ['target_id', 'created_at'])
    op.create_table('social_metric_observations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('collection_id', sa.Uuid(), sa.ForeignKey('social_metric_collections.id'), nullable=False),
        sa.Column('metric', pg.JSONB(), nullable=False))
    op.create_index('ix_social_metric_collection', 'social_metric_observations', ['collection_id'])
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON {table} FROM PUBLIC')
        for role in ('anon', 'authenticated'):
            op.execute(f"DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN EXECUTE 'REVOKE ALL ON {table} FROM {role}'; END IF; END $$")
    schema = op.get_bind().execute(sa.text('SELECT current_schema()')).scalar_one()
    quoted = op.get_bind().dialect.identifier_preparer.quote_identifier(schema)
    op.execute(f'''CREATE FUNCTION social_studio_history_guard() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,{quoted},pg_temp AS $$
        BEGIN
          IF TG_OP='DELETE' OR TG_TABLE_NAME='social_metric_observations' THEN
            RAISE EXCEPTION 'Studio history is immutable' USING ERRCODE='23514';
          END IF;
          IF (NEW.revision_id,NEW.actor_id,NEW.composition,NEW.input_hash,NEW.attempt,NEW.retry_of_id)
            IS DISTINCT FROM (OLD.revision_id,OLD.actor_id,OLD.composition,OLD.input_hash,OLD.attempt,OLD.retry_of_id) THEN
            RAISE EXCEPTION 'Render inputs are immutable' USING ERRCODE='23514';
          END IF;
          IF (OLD.sha256 IS NOT NULL AND (NEW.sha256,NEW.inspection,NEW.runtime_hash)
            IS DISTINCT FROM (OLD.sha256,OLD.inspection,OLD.runtime_hash)) OR
            (OLD.approved_sha256 IS NOT NULL AND (NEW.approved_sha256,NEW.approved_by,NEW.approved_at)
            IS DISTINCT FROM (OLD.approved_sha256,OLD.approved_by,OLD.approved_at)) THEN
            RAISE EXCEPTION 'Derivative and approval evidence are immutable' USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$''')
    op.execute('REVOKE ALL ON FUNCTION social_studio_history_guard() FROM PUBLIC')
    for table in ('social_render_jobs', 'social_metric_observations'):
        op.execute(f'CREATE TRIGGER social_studio_history_guard BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION social_studio_history_guard()')
    # Do not grant delivery-worker access to render/analytics tables.


def downgrade():
    op.execute("SET LOCAL lock_timeout='2s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute('LOCK TABLE ' + ','.join(TABLES) + ' IN ACCESS EXCLUSIVE MODE')
    op.execute('SET LOCAL row_security=off')
    if any(op.get_bind().execute(sa.text('SELECT EXISTS(SELECT 1 FROM ' + table + ')')).scalar_one() for table in TABLES):
        raise RuntimeError('Retained rendering/analytics history prevents destructive downgrade')
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute('DROP FUNCTION social_studio_history_guard()')

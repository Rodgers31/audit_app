"""Private semantic evidence, generated-draft dedup and immutable shadow rules.

Candidate predecessor is frozen main; coordinator serializes batch predecessors.
No control seed, grants, automatic authorization or execution is added.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = 'a704b15a0001'
down_revision = 'a545b14a0001'
branch_labels = None
depends_on = None
TABLES = ('social_generation_controls', 'social_source_cursors', 'social_source_events', 'social_automation_rule_versions', 'social_shadow_decisions')


def ident():
    return sa.Column('id', sa.Uuid(), primary_key=True)


def stamp():
    return sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade():
    op.create_table(TABLES[0], sa.Column('id', sa.Integer(), primary_key=True), sa.Column('version', sa.Integer(), nullable=False), sa.Column('drafts_enabled', sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column('shadow_enabled', sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column('source_allowlist', pg.JSONB(), nullable=False), sa.Column('targets', pg.JSONB(), nullable=False), sa.CheckConstraint('id = 1 AND version > 0', name='ck_social_generation_controls'))
    op.create_table(TABLES[1], ident(), sa.Column('source_type', sa.Text(), nullable=False), sa.Column('source_key', sa.Text(), nullable=False), sa.Column('detector_version', sa.Integer(), nullable=False), sa.Column('evidence_version', sa.Integer(), nullable=False), sa.Column('sequence', sa.Integer(), nullable=False), sa.Column('fingerprint', sa.Text(), nullable=False), sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint('source_type', 'source_key', 'detector_version', name='uq_social_source_cursor'), sa.CheckConstraint('sequence >= 0 AND evidence_version > 0 AND detector_version > 0', name='ck_social_cursor_versions'))
    op.create_table(TABLES[2], ident(), sa.Column('cursor_id', sa.Uuid(), sa.ForeignKey('social_source_cursors.id'), nullable=False), sa.Column('sequence', sa.Integer(), nullable=False), sa.Column('evidence_version', sa.Integer(), nullable=False), sa.Column('fingerprint', sa.Text(), nullable=False), sa.Column('observation', pg.JSONB(), nullable=False), stamp(), sa.UniqueConstraint('cursor_id', 'sequence', name='uq_social_source_event_sequence'), sa.UniqueConstraint('cursor_id', 'evidence_version', name='uq_social_source_event_evidence'), sa.CheckConstraint('sequence > 0 AND evidence_version > 0', name='ck_social_source_event_versions'))
    op.create_table(TABLES[3], ident(), sa.Column('rule_id', sa.Uuid(), nullable=False), sa.Column('version', sa.Integer(), nullable=False), sa.Column('definition', pg.JSONB(), nullable=False), sa.Column('definition_hash', sa.Text(), nullable=False), sa.Column('created_by', sa.Uuid(), nullable=False), stamp(), sa.UniqueConstraint('rule_id', 'version', name='uq_social_rule_version'), sa.CheckConstraint('version > 0', name='ck_social_rule_version'))
    op.create_table(TABLES[4], ident(), sa.Column('rule_version_id', sa.Uuid(), sa.ForeignKey('social_automation_rule_versions.id'), nullable=False), sa.Column('post_id', sa.Uuid(), sa.ForeignKey('social_posts.id'), nullable=False), sa.Column('revision_id', sa.Uuid(), sa.ForeignKey('social_post_revisions.id'), nullable=False), sa.Column('content_hash', sa.Text(), nullable=False), sa.Column('context_hash', sa.Text(), nullable=False), sa.Column('outcome', sa.Text(), nullable=False), sa.Column('reasons', pg.JSONB(), nullable=False), sa.Column('account_ids', pg.JSONB(), nullable=False), sa.Column('inputs', pg.JSONB(), nullable=False), stamp(), sa.UniqueConstraint('rule_version_id', 'revision_id', 'context_hash', name='uq_social_shadow_context'), sa.CheckConstraint("outcome IN ('would_allow','human_review')", name='ck_social_shadow_outcome'))
    op.create_index('ix_social_shadow_created', TABLES[4], ['created_at'])
    op.create_index('ix_social_shadow_post', TABLES[4], ['post_id', 'created_at'])
    op.create_foreign_key('fk_social_post_source_event', 'social_posts', 'social_source_events', ['source_event_id'], ['id'])
    op.create_unique_constraint('uq_social_post_source_event', 'social_posts', ['source_event_id'])
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON {table} FROM PUBLIC')
        for role in ('anon', 'authenticated'):
            op.execute(f"DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN EXECUTE 'REVOKE ALL ON {table} FROM {role}'; END IF; END $$")
    for table in TABLES[2:]:
        op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION social_deny_history_mutation()')


def downgrade():
    op.drop_constraint('uq_social_post_source_event', 'social_posts', type_='unique')
    op.drop_constraint('fk_social_post_source_event', 'social_posts', type_='foreignkey')
    for table in reversed(TABLES):
        op.drop_table(table)

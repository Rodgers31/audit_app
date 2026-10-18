"""Dormant exact-revision policy authority; no acceptance seeds or activation.

Candidate predecessor is exact PR704. Root serializes the batch chain. Existing
worker roles are not granted new access by this migration.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = 'a706b15a0001'
down_revision = 'a704b15a0001'
branch_labels = None
depends_on = None
TABLES = ('social_policy_operating_evidence', 'social_authorized_policy_snapshots', 'social_policy_selection', 'social_policy_decisions')
AUTH_CHECK = "(authorization_kind = 'human' AND approved_by IS NOT NULL AND policy_id IS NULL AND policy_version IS NULL AND policy_decision_id IS NULL) OR (authorization_kind = 'policy' AND approved_by IS NULL AND policy_id IS NOT NULL AND policy_version IS NOT NULL AND policy_version > 0 AND policy_decision_id IS NOT NULL)"


def stamp():
    return sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def ident():
    return sa.Column('id', sa.Uuid(), primary_key=True)


# Keep the original guarded function unchanged for its source-bound worker role
# contract. An additional trigger protects the new immutable authority link.
POLICY_GUARD = """
    BEGIN
     IF NEW.policy_decision_id IS DISTINCT FROM OLD.policy_decision_id
     THEN RAISE EXCEPTION 'Publication policy decision is immutable' USING ERRCODE = '23514'; END IF;
     RETURN NEW;
    END """


def upgrade():
    op.create_table(TABLES[0], ident(), sa.Column('rule_version_id', sa.Uuid(), sa.ForeignKey('social_automation_rule_versions.id'), nullable=False), sa.Column('evidence', pg.JSONB(), nullable=False), sa.Column('evidence_hash', sa.Text(), nullable=False), sa.Column('approved_by', sa.Uuid(), nullable=False), stamp())
    op.create_table(TABLES[1], ident(), sa.Column('rule_version_id', sa.Uuid(), sa.ForeignKey('social_automation_rule_versions.id'), nullable=False), sa.Column('operating_evidence_id', sa.Uuid(), sa.ForeignKey(TABLES[0]+'.id'), nullable=False), sa.Column('version', sa.Integer(), nullable=False), sa.Column('snapshot', pg.JSONB(), nullable=False), sa.Column('snapshot_hash', sa.Text(), nullable=False), sa.Column('approved_by', sa.Uuid(), nullable=False), sa.Column('valid_until', sa.DateTime(timezone=True), nullable=False), stamp(), sa.CheckConstraint('version > 0', name='ck_social_authorized_policy_version'))
    op.create_table(TABLES[2], sa.Column('id', sa.Integer(), primary_key=True), sa.Column('snapshot_id', sa.Uuid(), sa.ForeignKey(TABLES[1]+'.id')), sa.CheckConstraint('id = 1', name='ck_social_policy_selection'))
    op.create_table(TABLES[3], ident(), sa.Column('snapshot_id', sa.Uuid(), sa.ForeignKey(TABLES[1]+'.id'), nullable=False), sa.Column('policy_version', sa.Integer(), nullable=False), sa.Column('post_id', sa.Uuid(), sa.ForeignKey('social_posts.id'), nullable=False), sa.Column('revision_id', sa.Uuid(), sa.ForeignKey('social_post_revisions.id'), nullable=False, unique=True), sa.Column('content_hash', sa.Text(), nullable=False), sa.Column('inputs', pg.JSONB(), nullable=False), sa.Column('decision_hash', sa.Text(), nullable=False), stamp(), sa.UniqueConstraint('id', 'snapshot_id', 'policy_version', 'post_id', 'revision_id', 'content_hash', name='uq_social_policy_authority'))
    op.add_column('social_publications', sa.Column('policy_decision_id', sa.Uuid()))
    op.drop_constraint('ck_social_publication_human', 'social_publications', type_='check')
    op.create_check_constraint('ck_social_publication_human', 'social_publications', AUTH_CHECK)
    op.create_foreign_key('fk_social_publication_policy_authority', 'social_publications', TABLES[3], ['policy_decision_id', 'policy_id', 'policy_version', 'post_id', 'revision_id', 'approved_hash'], ['id', 'snapshot_id', 'policy_version', 'post_id', 'revision_id', 'content_hash'])
    op.drop_constraint('ck_social_controls_automation_off', 'social_controls', type_='check')
    op.create_check_constraint('ck_social_controls_automation_off', 'social_controls', 'NOT generation_enabled AND (NOT auto_publish_enabled OR auto_schedule_enabled) AND (NOT auto_schedule_enabled OR auto_approve_enabled)')
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON {table} FROM PUBLIC')
        for role in ('anon', 'authenticated'):
            op.execute(f"DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN EXECUTE 'REVOKE ALL ON {table} FROM {role}'; END IF; END $$")
    for table in (TABLES[0], TABLES[1], TABLES[3]):
        op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION social_deny_history_mutation()')
    op.execute('CREATE FUNCTION social_guard_policy_decision() RETURNS trigger LANGUAGE plpgsql AS $$' + POLICY_GUARD + '$$')
    op.execute('CREATE TRIGGER social_publication_policy_immutable BEFORE UPDATE ON social_publications FOR EACH ROW EXECUTE FUNCTION social_guard_policy_decision()')


def downgrade():
    # Refuse rather than discard durable policy authority or disable active work.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT current_setting('transaction_isolation')")).scalar() != 'read committed':
        raise RuntimeError('Policy downgrade requires READ COMMITTED')
    op.execute("SET LOCAL lock_timeout='2s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute('LOCK TABLE social_controls, social_publications, ' + ','.join(TABLES) + ' IN ACCESS EXCLUSIVE MODE')
    op.execute('SET LOCAL row_security=off')
    retained = ' OR '.join('EXISTS(SELECT 1 FROM ' + table + ')' for table in TABLES)
    retained += " OR EXISTS(SELECT 1 FROM social_publications WHERE authorization_kind='policy' OR policy_decision_id IS NOT NULL)"
    retained += ' OR EXISTS(SELECT 1 FROM social_controls WHERE generation_enabled OR auto_approve_enabled OR auto_schedule_enabled OR auto_publish_enabled)'
    if connection.execute(sa.text('SELECT ' + retained)).scalar():
        raise RuntimeError('Policy history/controls prevent downgrade')
    op.execute('DROP TRIGGER social_publication_policy_immutable ON social_publications')
    op.execute('DROP FUNCTION social_guard_policy_decision()')
    op.drop_constraint('fk_social_publication_policy_authority', 'social_publications', type_='foreignkey')
    op.drop_constraint('ck_social_publication_human', 'social_publications', type_='check')
    op.drop_column('social_publications', 'policy_decision_id')
    op.create_check_constraint('ck_social_publication_human', 'social_publications', "authorization_kind = 'human' AND approved_by IS NOT NULL AND policy_id IS NULL AND policy_version IS NULL")
    op.drop_constraint('ck_social_controls_automation_off', 'social_controls', type_='check')
    op.create_check_constraint('ck_social_controls_automation_off', 'social_controls', 'NOT generation_enabled AND NOT auto_approve_enabled AND NOT auto_schedule_enabled AND NOT auto_publish_enabled')
    for table in reversed(TABLES):
        op.drop_table(table)

"""Permanent payload fences, bounded admission protocol and deletion ledger."""
from alembic import op
import sqlalchemy as sa

revision = 'a701b15a0001'
down_revision = 'a700b15a0001'
branch_labels = None
depends_on = None

RETAINED = ('retained_write_fence IS NULL OR (length(retained_write_fence) <= 4096 '
    'AND grant_settled_epoch < grant_epoch AND pending_released = 1 '
    'AND reservation_released = 0 AND quarantine_cleaned = 0 '
    'AND finalization_settled = 1 '
    'AND reserved_bytes >= (2 - fenced_copies) * declared_size + fenced_copies)')


def upgrade():
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.add_column('social_media_uploads', sa.Column('write_protocol', sa.Text()))
    op.add_column('social_media_uploads', sa.Column('fenced_copies', sa.Integer(), server_default='0', nullable=False))
    op.create_check_constraint('ck_social_media_write_protocol', 'social_media_uploads',
        "(write_protocol IS NULL OR write_protocol = 'conditional_create_v1') AND fenced_copies BETWEEN 0 AND 2 AND (fenced_copies = 0 OR write_protocol IS NOT NULL)")
    op.drop_constraint('ck_social_media_retained_fence', 'social_media_uploads', type_='check')
    op.create_check_constraint('ck_social_media_retained_fence', 'social_media_uploads', RETAINED)
    op.create_table('social_media_deletions',
        sa.Column('operation_id', sa.Uuid(), primary_key=True),
        sa.Column('asset_id', sa.Uuid(), sa.ForeignKey('social_media_assets.id'), nullable=False),
        sa.Column('authority_id', sa.Uuid(), nullable=False),
        sa.Column('receipt_id', sa.Uuid(), nullable=False),
        *[sa.Column(name, sa.String(64), nullable=False) for name in
          ('command_hash', 'scope_hash', 'policy_hash', 'binding_hash')],
        sa.Column('mode', sa.Text(), nullable=False),
        sa.Column('state', sa.Text(), nullable=False),
        sa.Column('quarantine_fenced', sa.Integer(), nullable=False),
        sa.Column('original_fenced', sa.Integer(), nullable=False),
        sa.Column('result_hash', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("mode IN ('quarantine','all') AND state IN ('admitted','uncertain','complete') AND quarantine_fenced IN (0,1) AND original_fenced IN (0,1)", name='ck_social_media_deletion_state'),
        sa.CheckConstraint("(state = 'complete') = (result_hash IS NOT NULL AND completed_at IS NOT NULL)", name='ck_social_media_deletion_result'))
    op.create_index('ix_social_media_deletion_asset', 'social_media_deletions', ['asset_id'])
    op.execute('ALTER TABLE social_media_deletions ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON social_media_deletions FROM PUBLIC')
    op.execute("""DO $$ DECLARE r text; BEGIN
      FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
          EXECUTE format('REVOKE ALL ON social_media_deletions FROM %I', r);
        END IF;
      END LOOP; END $$""")
    op.execute("""CREATE FUNCTION social_media_retirement_guard() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog AS $$ BEGIN
      IF TG_TABLE_NAME = 'social_media_uploads' THEN
        IF TG_OP = 'DELETE' THEN
          IF OLD.write_protocol IS NOT NULL OR OLD.retained_write_fence IS NOT NULL THEN
            RAISE EXCEPTION 'media admission and fence history is immutable';
          END IF;
          RETURN OLD;
        END IF;
        IF NEW.write_protocol IS DISTINCT FROM OLD.write_protocol OR NEW.fenced_copies < OLD.fenced_copies THEN
          RAISE EXCEPTION 'media write protocol and fence history are immutable';
        END IF;
      ELSE
        IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'media deletion history is immutable'; END IF;
        IF OLD.state = 'complete' OR
          ROW(NEW.operation_id,NEW.asset_id,NEW.authority_id,NEW.receipt_id,NEW.command_hash,NEW.scope_hash,NEW.policy_hash,NEW.binding_hash,NEW.mode,NEW.created_at)
          IS DISTINCT FROM
          ROW(OLD.operation_id,OLD.asset_id,OLD.authority_id,OLD.receipt_id,OLD.command_hash,OLD.scope_hash,OLD.policy_hash,OLD.binding_hash,OLD.mode,OLD.created_at)
          OR NEW.quarantine_fenced < OLD.quarantine_fenced OR NEW.original_fenced < OLD.original_fenced THEN
          RAISE EXCEPTION 'media deletion history is immutable';
        END IF;
      END IF;
      RETURN NEW; END $$""")
    op.execute('CREATE TRIGGER social_media_write_protocol_guard BEFORE UPDATE OR DELETE ON social_media_uploads FOR EACH ROW EXECUTE FUNCTION social_media_retirement_guard()')
    op.execute('CREATE TRIGGER social_media_deletion_guard BEFORE UPDATE OR DELETE ON social_media_deletions FOR EACH ROW EXECUTE FUNCTION social_media_retirement_guard()')


def downgrade():
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute('LOCK TABLE social_media_uploads, social_media_deletions IN ACCESS EXCLUSIVE MODE')
    if op.get_bind().execute(sa.text('SELECT EXISTS(SELECT 1 FROM social_media_deletions) OR EXISTS(SELECT 1 FROM social_media_uploads WHERE write_protocol IS NOT NULL)')).scalar():
        raise RuntimeError('Permanent fence/write-protocol history prevents downgrade')
    op.execute('DROP TRIGGER social_media_write_protocol_guard ON social_media_uploads')
    op.drop_table('social_media_deletions')
    op.execute('DROP FUNCTION social_media_retirement_guard()')
    op.drop_constraint('ck_social_media_retained_fence', 'social_media_uploads', type_='check')
    op.create_check_constraint('ck_social_media_retained_fence', 'social_media_uploads', RETAINED.replace('(2 - fenced_copies) * declared_size + fenced_copies', '2 * declared_size'))
    op.drop_constraint('ck_social_media_write_protocol', 'social_media_uploads', type_='check')
    op.drop_column('social_media_uploads', 'fenced_copies')
    op.drop_column('social_media_uploads', 'write_protocol')

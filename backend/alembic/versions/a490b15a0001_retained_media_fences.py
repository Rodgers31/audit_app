"""Persist retained create-only fences without changing inspected originals."""
from alembic import op
import sqlalchemy as sa

revision = 'a490b15a0001'
down_revision = 'a611b12a0001'
branch_labels = None
depends_on = None

CONSTRAINT = ('retained_write_fence IS NULL OR (length(retained_write_fence) <= 4096 '
    'AND grant_settled_epoch < grant_epoch AND pending_released = 1 '
    'AND reservation_released = 0 AND quarantine_cleaned = 0 '
    'AND finalization_settled = 1 AND reserved_bytes >= 2 * declared_size)')


def upgrade():
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.add_column('social_media_uploads', sa.Column('retained_write_fence', sa.Text(), nullable=True))
    op.create_check_constraint('ck_social_media_retained_fence', 'social_media_uploads', CONSTRAINT)
    op.execute("""CREATE FUNCTION social_retained_fence_immutable() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $$ BEGIN
        IF OLD.retained_write_fence IS NOT NULL AND NEW.retained_write_fence IS DISTINCT FROM OLD.retained_write_fence THEN
          RAISE EXCEPTION 'retained media fence is immutable';
        END IF;
        RETURN NEW; END $$""")
    op.execute('CREATE TRIGGER social_retained_fence_immutable BEFORE UPDATE ON social_media_uploads '
        'FOR EACH ROW EXECUTE FUNCTION social_retained_fence_immutable()')


def downgrade():
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    # Serialize the history check and destructive DDL with every upload writer.
    op.execute('LOCK TABLE social_media_uploads IN ACCESS EXCLUSIVE MODE')
    if op.get_bind().execute(sa.text('SELECT EXISTS(SELECT 1 FROM social_media_uploads WHERE retained_write_fence IS NOT NULL)')).scalar():
        raise RuntimeError('Retained media history prevents destructive downgrade')
    op.execute('DROP TRIGGER social_retained_fence_immutable ON social_media_uploads')
    op.execute('DROP FUNCTION social_retained_fence_immutable()')
    op.drop_constraint('ck_social_media_retained_fence', 'social_media_uploads', type_='check')
    op.drop_column('social_media_uploads', 'retained_write_fence')

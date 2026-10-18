"""Private complete-at-allocation owned media write history; no backfill."""
from alembic import op
import sqlalchemy as sa

revision = 'a706b17a0001'
down_revision = 'a705b15a0001'
branch_labels = None
depends_on = None
TABLES = ('social_media_write_owners', 'social_media_write_attempts')


def upgrade():
    op.execute("SET LOCAL lock_timeout='2s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.create_table(TABLES[0],
        sa.Column('asset_id', sa.Uuid(), sa.ForeignKey('social_media_uploads.asset_id'), primary_key=True),
        sa.Column('generation', sa.Uuid(), nullable=False, unique=True),
        sa.Column('binding_hash', sa.String(64), nullable=False),
        sa.Column('state', sa.Text(), nullable=False),
        sa.Column('receipt_id', sa.Uuid(), unique=True),
        sa.Column('command_hash', sa.String(64)),
        sa.Column('result_hash', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("state IN ('open','closed','settled')", name='ck_social_media_write_owner_state'),
        sa.CheckConstraint("(state = 'settled') = (receipt_id IS NOT NULL AND command_hash IS NOT NULL AND result_hash IS NOT NULL)", name='ck_social_media_write_owner_result'))
    op.create_table(TABLES[1],
        sa.Column('asset_id', sa.Uuid(), sa.ForeignKey('social_media_write_owners.asset_id'), primary_key=True),
        sa.Column('kind', sa.Text(), primary_key=True),
        sa.Column('epoch', sa.BigInteger(), primary_key=True),
        sa.Column('operation_id', sa.Uuid(), nullable=False, unique=True),
        sa.Column('state', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('grant','finalize') AND epoch > 0 AND state IN ('admitted','not_issued','issued','completed')", name='ck_social_media_write_attempt_state'),
        sa.CheckConstraint("(kind='grant' AND state IN ('admitted','not_issued','issued')) OR (kind='finalize' AND state IN ('admitted','completed'))", name='ck_social_media_write_attempt_kind'))
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON {table} FROM PUBLIC')
        op.execute(f"""DO $$ DECLARE r text; BEGIN
          FOREACH r IN ARRAY ARRAY['anon','authenticated'] LOOP
            IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
              EXECUTE format('REVOKE ALL ON {table} FROM %I',r);
            END IF;
          END LOOP; END $$""")
    op.execute("""CREATE FUNCTION social_media_owned_guard() RETURNS trigger
      LANGUAGE plpgsql SET search_path = pg_catalog AS $$
      DECLARE parent_state text; attempt_count bigint; covered boolean; BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'owned media history is immutable'; END IF;
      IF TG_TABLE_NAME='social_media_write_owners' THEN
        IF TG_OP='INSERT' THEN
          EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I.social_media_uploads u WHERE u.asset_id=$1
            AND u.version=1 AND u.grant_epoch=0 AND u.finalization_epoch IS NULL
            AND u.retained_write_fence IS NULL AND u.reservation_released=0 FOR UPDATE)',TG_TABLE_SCHEMA)
            INTO covered USING NEW.asset_id;
          IF covered IS NOT TRUE OR NEW.state<>'open' THEN RAISE EXCEPTION 'historical media coverage refused'; END IF;
        ELSIF ROW(NEW.asset_id,NEW.generation,NEW.binding_hash,NEW.created_at)
          IS DISTINCT FROM ROW(OLD.asset_id,OLD.generation,OLD.binding_hash,OLD.created_at)
          OR OLD.state='settled' OR NOT ((OLD.state='open' AND NEW.state='closed')
            OR (OLD.state='closed' AND NEW.state IN ('closed','settled'))) THEN
          RAISE EXCEPTION 'owned media identity and closure are immutable';
        END IF;
      ELSIF TG_OP='INSERT' THEN
        EXECUTE format('SELECT state FROM %I.social_media_write_owners WHERE asset_id=$1 FOR UPDATE',TG_TABLE_SCHEMA)
          INTO parent_state USING NEW.asset_id;
        EXECUTE format('SELECT count(*) FROM %I.social_media_write_attempts WHERE asset_id=$1',TG_TABLE_SCHEMA)
          INTO attempt_count USING NEW.asset_id;
        IF parent_state IS DISTINCT FROM 'open' OR NEW.state<>'admitted' OR attempt_count>=32 THEN
          RAISE EXCEPTION 'owned media write admission closed';
        END IF;
      ELSIF OLD.state<>'admitted' OR NEW.state='admitted'
        OR ROW(NEW.asset_id,NEW.kind,NEW.epoch,NEW.operation_id,NEW.created_at)
          IS DISTINCT FROM ROW(OLD.asset_id,OLD.kind,OLD.epoch,OLD.operation_id,OLD.created_at) THEN
        RAISE EXCEPTION 'owned media attempt is immutable';
      END IF;
      RETURN NEW; END $$""")
    for table in TABLES:
        op.execute(f'CREATE TRIGGER owned_media_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION social_media_owned_guard()')


def downgrade():
    op.execute("SET LOCAL lock_timeout='2s'")
    op.execute('LOCK TABLE social_media_write_owners, social_media_write_attempts IN ACCESS EXCLUSIVE MODE')
    if op.get_bind().execute(sa.text('SELECT EXISTS(SELECT 1 FROM social_media_write_owners)')).scalar():
        raise RuntimeError('Owned write history prevents downgrade')
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute('DROP FUNCTION social_media_owned_guard()')

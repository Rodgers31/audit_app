"""Sticky global social worker owner and immutable generation history."""
from alembic import op
import sqlalchemy as sa

revision = 'a545b14a0001'
down_revision = 'a490b15a0001'
branch_labels = None
depends_on = None
TABLES = ('social_worker_runtime_ownership', 'social_worker_runtime_history')

# Invoker triggers: no SECURITY DEFINER or new delegated authority.
GUARDS = {
    'social_worker_owner_guard': """
BEGIN
  IF TG_OP='UPDATE' THEN
    RAISE EXCEPTION 'Global worker ownership is immutable';
  ELSIF TG_OP='DELETE' THEN
    IF NOT EXISTS(SELECT 1 FROM social_worker_runtime_history WHERE generation=OLD.generation
        AND owner_id=OLD.owner_id AND event='released') THEN
      RAISE EXCEPTION 'Positive versioned release required';
    END IF;
    RETURN OLD;
  END IF;
  IF NEW.generation <> (SELECT COALESCE(MAX(generation),0)+1 FROM social_worker_runtime_history) THEN
    RAISE EXCEPTION 'Global worker generation mismatch';
  END IF;
  RETURN NEW;
END
""",
    'social_worker_owner_acquired': """
BEGIN
  INSERT INTO social_worker_runtime_history(generation,event,owner_id,deployment_version,proof)
    VALUES(NEW.generation,'acquired',NEW.owner_id,NEW.deployment_version,'{}'::jsonb);
  RETURN NEW;
END
""",
    'social_worker_history_guard': """
BEGIN
  IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Global worker history is immutable'; END IF;
  IF NOT EXISTS(SELECT 1 FROM social_worker_runtime_ownership WHERE id=1
      AND generation=NEW.generation AND owner_id=NEW.owner_id
      AND deployment_version=NEW.deployment_version) THEN
    RAISE EXCEPTION 'Global worker history requires current ownership';
  END IF;
  IF NEW.event='released' AND NOT (
      NEW.proof->'version'='1'::jsonb AND NEW.proof->'generation'=to_jsonb(NEW.generation)
      AND NEW.proof->>'owner_id'=NEW.owner_id::text
      AND NEW.proof->'worker_exit_code'='0'::jsonb
      AND NEW.proof->'process_joined'='true'::jsonb
      AND NEW.proof->'providers_closed'='true'::jsonb
      AND NEW.proof->'executor_closed'='true'::jsonb
      AND NEW.proof->'claims_drained'='true'::jsonb) IS TRUE THEN
    RAISE EXCEPTION 'Positive versioned release required';
  END IF;
  RETURN NEW;
END
""",
}


def upgrade():
    op.execute("SET LOCAL lock_timeout='2s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute('''CREATE TABLE social_worker_runtime_ownership (
        id integer PRIMARY KEY CHECK(id=1), owner_id uuid NOT NULL UNIQUE,
        generation bigint NOT NULL UNIQUE CHECK(generation>0),
        deployment_version text NOT NULL CHECK(length(deployment_version) BETWEEN 1 AND 128),
        acquired_at timestamptz NOT NULL DEFAULT clock_timestamp())''')
    op.execute('''CREATE TABLE social_worker_runtime_history (
        generation bigint NOT NULL CHECK(generation>0), event text NOT NULL CHECK(event IN ('acquired','released')),
        owner_id uuid NOT NULL, deployment_version text NOT NULL,
        proof jsonb NOT NULL, recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(generation,event))''')
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON {table} FROM PUBLIC')
        for role in ('anon', 'authenticated'):
            op.execute(f"DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN EXECUTE 'REVOKE ALL ON {table} FROM {role}'; END IF; END $$")
    schema = op.get_bind().execute(sa.text('SELECT current_schema()')).scalar_one()
    quoted = op.get_bind().dialect.identifier_preparer.quote_identifier(schema)
    for name, body in GUARDS.items():
        # Pin every invoker trigger's name resolution to the installed schema.
        op.execute(sa.text(f'CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,{quoted},pg_temp AS $$' + body + '$$'))
        op.execute(f'REVOKE ALL ON FUNCTION {name}() FROM PUBLIC')
    op.execute('CREATE TRIGGER social_worker_owner_guard BEFORE INSERT OR UPDATE OR DELETE ON social_worker_runtime_ownership FOR EACH ROW EXECUTE FUNCTION social_worker_owner_guard()')
    op.execute('CREATE TRIGGER social_worker_owner_acquired AFTER INSERT ON social_worker_runtime_ownership FOR EACH ROW EXECUTE FUNCTION social_worker_owner_acquired()')
    op.execute('CREATE TRIGGER social_worker_history_guard BEFORE INSERT OR UPDATE OR DELETE ON social_worker_runtime_history FOR EACH ROW EXECUTE FUNCTION social_worker_history_guard()')


def downgrade():
    op.execute("SET LOCAL lock_timeout='2s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    conn = op.get_bind()
    conn.execute(sa.text('LOCK TABLE ' + ','.join(TABLES) + ' IN ACCESS EXCLUSIVE MODE'))
    conn.execute(sa.text('SET LOCAL row_security=off'))
    if any(conn.execute(sa.text('SELECT EXISTS(SELECT 1 FROM ' + table + ')')).scalar_one() for table in TABLES):
        raise RuntimeError('Global worker history prevents destructive downgrade')
    for table in reversed(TABLES):
        op.drop_table(table)
    for name in GUARDS:
        op.execute(f'DROP FUNCTION {name}()')

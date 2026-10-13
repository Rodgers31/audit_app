"""Add durable root transaction provenance without admitting unknown history.

Revision ID: a611b12a0001
Revises: e602b11a0001
"""
from uuid import uuid4

from alembic import op
from sqlalchemy import text

revision = "a611b12a0001"
down_revision = "e602b11a0001"
branch_labels = None
depends_on = None

# Frozen here rather than importing mutable application code into history.
CAPTURE_BODY = """BEGIN
  IF TG_RELID <> 'public.admin_audit_log'::regclass OR TG_OP <> 'INSERT' OR TG_WHEN <> 'AFTER' THEN
    RAISE EXCEPTION 'invalid audit capture context';
  END IF;
  INSERT INTO public.admin_audit_provenance(audit_id, root_xid, incarnation)
    SELECT NEW.id, pg_catalog.pg_current_xact_id(), incarnation FROM public.admin_audit_storage WHERE singleton;
  IF NOT FOUND THEN RAISE EXCEPTION 'audit storage identity missing'; END IF;
  RETURN NEW;
END"""
IMMUTABLE_BODY = """BEGIN
  RAISE EXCEPTION 'audit history is append only';
END"""
IDENTITY_BODY = """SELECT s.system_identifier::text, d.oid, c.timeline_id,
  pg_catalog.pg_is_in_recovery() FROM pg_catalog.pg_control_system() s,
  pg_catalog.pg_control_checkpoint() c, pg_catalog.pg_database d
  WHERE d.datname = pg_catalog.current_database()"""


def prepare():
    db = op.get_bind()
    if db.dialect.name != "postgresql":
        raise RuntimeError("Durable admin audit migration requires PostgreSQL")
    op.execute("SET LOCAL lock_timeout='2s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("LOCK TABLE public.etl_dispatch_worker, public.admin_audit_log IN ACCESS EXCLUSIVE MODE")
    if db.scalar(text("SELECT EXISTS(SELECT FROM public.etl_dispatch_worker WHERE ready)")) is not False:
        raise RuntimeError("Stop dedicated worker before changing audit storage")
    return db


def upgrade():
    db = prepare()
    if db.scalar(text("""SELECT EXISTS(SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relname IN ('admin_audit_provenance','admin_audit_storage'))
      OR EXISTS(SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
      WHERE n.nspname='public' AND p.proname IN ('audit_log_capture','audit_log_immutable','audit_log_identity'))
      OR EXISTS(SELECT FROM pg_policy WHERE polrelid='public.admin_audit_log'::regclass)
      OR EXISTS(SELECT FROM pg_trigger WHERE tgrelid='public.admin_audit_log'::regclass AND NOT tgisinternal)""")) is not False:
        raise RuntimeError("Partial or preexisting audit storage must be reviewed")
    # Control functions require actual authority; no guessed system/timeline.
    identity = db.execute(text(IDENTITY_BODY)).one()
    if (len(identity) != 4 or type(identity[0]) is not str or not identity[0].isascii()
            or not identity[0].isdigit() or not 0 < int(identity[0]) < 2**64
            or type(identity[1]) is not int or not 0 < identity[1] < 2**32
            or type(identity[2]) is not int or not 0 < identity[2] < 2**32
            or identity[3] is not False):
        raise RuntimeError("Audit storage identity cannot be verified outside recovery")
    op.execute("ALTER TABLE public.admin_audit_log ADD CONSTRAINT ck_admin_audit_positive_id CHECK(id>0)")
    for role in ("audit_log_reader", "audit_log_writer"):
        existing = db.execute(text("SELECT rolsuper,rolbypassrls,rolcanlogin,rolcreaterole,rolcreatedb,rolreplication FROM pg_roles WHERE rolname=:role"), {"role": role}).all()
        if existing:
            if len(existing) != 1 or len(existing[0]) != 6 or any(value is not False for value in existing[0]):
                raise RuntimeError("Unsafe existing audit role must be reviewed")
        else:
            op.execute(f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS")
        if db.scalar(text("SELECT EXISTS(SELECT FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=:role)"), {"role": role}) is not False:
            raise RuntimeError("Audit group role cannot inherit other authority")
        if db.scalar(text("SELECT has_schema_privilege(:role,'public','CREATE')"), {"role": role}) is not False:
            raise RuntimeError("Audit group role cannot create public schema objects")
        op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    op.execute("""CREATE TABLE public.admin_audit_storage (
      singleton boolean PRIMARY KEY CONSTRAINT ck_audit_storage_singleton CHECK(singleton),
      schema_version integer NOT NULL CONSTRAINT ck_audit_storage_version CHECK(schema_version=1),
      incarnation uuid NOT NULL, system_identifier text NOT NULL,
      database_oid oid NOT NULL, timeline integer NOT NULL,
      certified boolean NOT NULL DEFAULT false)""")
    db.execute(text("""INSERT INTO public.admin_audit_storage
      VALUES(true,1,:incarnation,:system,:database,:timeline,false)"""),
      {"incarnation": uuid4(), "system": identity[0], "database": identity[1], "timeline": identity[2]})
    op.execute("""CREATE TABLE public.admin_audit_provenance (
      audit_id integer PRIMARY KEY REFERENCES public.admin_audit_log(id),
      root_xid xid8 NOT NULL, incarnation uuid NOT NULL)""")
    for name, body, security, language, returns in (
        ("audit_log_capture", CAPTURE_BODY, "SECURITY DEFINER", "plpgsql", "trigger"),
        ("audit_log_immutable", IMMUTABLE_BODY, "SECURITY INVOKER", "plpgsql", "trigger"),
        ("audit_log_identity", IDENTITY_BODY, "SECURITY DEFINER", "sql",
         "TABLE(system_identifier text, database_oid oid, timeline integer, in_recovery boolean)"),
    ):
        op.execute(f"CREATE FUNCTION public.{name}() RETURNS {returns} LANGUAGE {language} {security} SET search_path=pg_catalog AS $audit$ {body} $audit$")
        op.execute(f"REVOKE ALL ON FUNCTION public.{name}() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.audit_log_identity() TO audit_log_reader")
    for table, name, event, function in (
        ("admin_audit_log", "audit_log_capture", "AFTER INSERT FOR EACH ROW", "audit_log_capture"),
        ("admin_audit_log", "audit_log_immutable", "BEFORE UPDATE OR DELETE OR TRUNCATE FOR EACH STATEMENT", "audit_log_immutable"),
        ("admin_audit_provenance", "audit_provenance_immutable", "BEFORE UPDATE OR DELETE OR TRUNCATE FOR EACH STATEMENT", "audit_log_immutable"),
    ):
        # PostgreSQL syntax puts the table between the event and FOR EACH.
        event, each = event.split(" FOR EACH ")
        op.execute(f"CREATE TRIGGER {name} {event} ON public.{table} FOR EACH {each} EXECUTE FUNCTION public.{function}()")
        op.execute(f"ALTER TABLE public.{table} ENABLE ALWAYS TRIGGER {name}")
    for table in ("admin_audit_log", "admin_audit_provenance", "admin_audit_storage"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
        columns = db.execute(text("SELECT attname FROM pg_attribute WHERE attrelid=CAST(:table AS regclass) AND attnum>0 AND NOT attisdropped"), {"table": 'public.' + table}).scalars().all()
        # Table REVOKE does not remove old column ACLs.
        for column in columns:
            quoted = db.dialect.identifier_preparer.quote(column)
            op.execute(f"REVOKE SELECT({quoted}),INSERT({quoted}),UPDATE({quoted}),REFERENCES({quoted}) ON public.{table} FROM PUBLIC")
        # Supabase public roles must not read private administrator evidence.
        for role in ("anon", "authenticated"):
            if db.scalar(text("SELECT EXISTS(SELECT FROM pg_roles WHERE rolname=:role)"), {"role": role}):
                op.execute(f"REVOKE ALL ON public.{table} FROM {role}")
                for column in columns:
                    quoted = db.dialect.identifier_preparer.quote(column)
                    op.execute(f"REVOKE SELECT({quoted}),INSERT({quoted}),UPDATE({quoted}),REFERENCES({quoted}) ON public.{table} FROM {role}")
        op.execute(f"GRANT SELECT ON public.{table} TO audit_log_reader")
    op.execute("CREATE POLICY audit_log_read ON public.admin_audit_log FOR SELECT TO audit_log_reader,audit_log_writer USING(true)")
    op.execute("CREATE POLICY audit_log_write ON public.admin_audit_log FOR INSERT TO audit_log_writer WITH CHECK(true)")
    op.execute("CREATE POLICY audit_provenance_read ON public.admin_audit_provenance FOR SELECT TO audit_log_reader USING(true)")
    op.execute("CREATE POLICY audit_storage_read ON public.admin_audit_storage FOR SELECT TO audit_log_reader USING(true)")
    op.execute("GRANT SELECT ON public.admin_audit_log TO audit_log_writer")
    op.execute("GRANT INSERT(actor_id,actor_email,action,target_type,target_id,payload,created_at) ON public.admin_audit_log TO audit_log_writer")
    op.execute("REVOKE ALL ON SEQUENCE public.admin_audit_log_id_seq FROM PUBLIC,audit_log_reader,audit_log_writer")
    for role in ('anon','authenticated'):
        if db.scalar(text('SELECT EXISTS(SELECT FROM pg_roles WHERE rolname=:role)'),{'role':role}):
            op.execute(f'REVOKE ALL ON SEQUENCE public.admin_audit_log_id_seq FROM {role}')
    op.execute("GRANT USAGE ON SEQUENCE public.admin_audit_log_id_seq TO audit_log_writer")
    if db.scalar(text("""SELECT EXISTS(SELECT FROM pg_roles r
      WHERE r.rolname IN ('anon','authenticated','audit_log_reader')
      AND has_sequence_privilege(r.oid,'public.admin_audit_log_id_seq','USAGE,SELECT,UPDATE'))""")) is not False:
        raise RuntimeError('Public application roles inherit private audit sequence authority')
    if db.scalar(text("""SELECT EXISTS(SELECT FROM pg_roles r, pg_class c
      WHERE r.rolname IN ('anon','authenticated')
      AND c.oid IN ('public.admin_audit_log'::regclass,'public.admin_audit_provenance'::regclass,'public.admin_audit_storage'::regclass)
      AND (r.rolsuper OR r.rolbypassrls OR has_table_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')
        OR has_any_column_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE')))""")) is not False:
        raise RuntimeError("Public application roles inherit private audit authority")


def downgrade():
    db = prepare()
    if db.scalar(text("SELECT EXISTS(SELECT FROM public.admin_audit_log) OR EXISTS(SELECT FROM public.admin_audit_storage WHERE certified)")) is not False:
        raise RuntimeError("Audit history or certification exists; audit storage cannot be removed")
    for table, trigger in (("admin_audit_log", "audit_log_capture"), ("admin_audit_log", "audit_log_immutable"),
                           ("admin_audit_provenance", "audit_provenance_immutable")):
        op.execute(f"DROP TRIGGER {trigger} ON public.{table}")
    op.execute("DROP POLICY audit_log_read ON public.admin_audit_log")
    op.execute("DROP POLICY audit_log_write ON public.admin_audit_log")
    op.execute("ALTER TABLE public.admin_audit_log DROP CONSTRAINT ck_admin_audit_positive_id")
    # Keep private RLS enabled; downgrade never restores public audit access.
    op.execute("DROP TABLE public.admin_audit_provenance, public.admin_audit_storage")
    op.execute("DROP FUNCTION public.audit_log_capture(), public.audit_log_immutable(), public.audit_log_identity()")
    for role in ("audit_log_reader", "audit_log_writer"):
        op.execute(f"REVOKE ALL ON public.admin_audit_log FROM {role}")
        op.execute(f"REVOKE INSERT(actor_id,actor_email,action,target_type,target_id,payload,created_at) ON public.admin_audit_log FROM {role}")
        op.execute(f"REVOKE ALL ON SEQUENCE public.admin_audit_log_id_seq FROM {role}")
        op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role}")
        # Cluster roles can serve another database; never drop shared role state.

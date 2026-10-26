"""Durable audit admission and authenticated xid8 bookmarks.

An external incarnation is custody authority, not a value inferred from restored
data. Restores/clones must revoke it before service startup. See Batch 12 handoff.
"""
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import hmac
import json
import os
import re
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from database import get_db
from request_database import _create_engine
from github_database_tls import connection_args

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


def unavailable():
    raise HTTPException(503, "Audit visibility evidence is unavailable.")


@lru_cache(maxsize=1)
def reader_engine(url):
    # Separate restricted connection; no SET ROLE on a writer session.
    if not make_url(url).drivername.startswith("postgresql"):
        unavailable()
    return _create_engine(url, connection_args(), pool_size=1, pool_timeout=.5,
                          statement_ms=5000, lock_ms=1000, use_deadline=True,
                          isolation_level="REPEATABLE READ")


def get_audit_db(db: Session = Depends(get_db)):
    url = os.getenv("ADMIN_AUDIT_DATABASE_URL")
    if db.get_bind().dialect.name == "postgresql" and url:
        with Session(reader_engine(url)) as reader:
            yield reader
    else:
        # SQLite retains the local contract. PostgreSQL still passes full
        # capability admission; a default writer/owner connection is refused.
        yield db


def snapshot8(value):
    if (type(value) is not str or len(value) > 4096 or not re.fullmatch(
        r"[0-9]{1,20}:[0-9]{1,20}:(?:[0-9]{1,20}(?:,[0-9]{1,20})*)?", value
    )):
        raise HTTPException(422, "Invalid audit visibility snapshot.")
    low, high, active = value.split(":")
    low, high = int(low), int(high)
    ids = [int(i) for i in active.split(",")] if active else []
    if (not 3 <= low <= high <= 2**64 - 1 or ids != sorted(set(ids))
            or any(i < low or i >= high for i in ids)):
        raise HTTPException(422, "Invalid audit visibility snapshot.")
    return value


def bookmark(value):
    if type(value) is not str or len(value) > 4096:
        raise HTTPException(422, "Invalid audit visibility snapshot.")
    parts = value.split(":", 2)
    if len(parts) != 3 or parts[0] != "v3":
        raise HTTPException(422, "Refresh to obtain an audit visibility snapshot.")
    try:
        if str(UUID(parts[1])) != parts[1]:
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "Invalid audit visibility snapshot.") from None
    signed = parts[2].rsplit(":", 1)
    if len(signed) != 2 or not re.fullmatch(r"[0-9a-f]{64}", signed[1]):
        raise HTTPException(422, "Invalid audit visibility snapshot.")
    return parts[1], snapshot8(signed[0]), signed[1]


def authority():
    incarnation = os.getenv("ADMIN_AUDIT_INCARNATION")
    key = os.getenv("ADMIN_AUDIT_BOOKMARK_KEY")
    try:
        if str(UUID(incarnation)) != incarnation:
            unavailable()
    except (ValueError, TypeError, AttributeError):
        unavailable()
    if type(key) is not str or not re.fullmatch(r"[0-9a-f]{64}", key):
        unavailable()
    return incarnation, bytes.fromhex(key)


def signature(scope, visible, captured, ceiling, actor_id, key):
    try:
        if str(UUID(scope)) != scope:
            unavailable()
    except (ValueError, TypeError, AttributeError):
        unavailable()
    snapshot8(visible)
    if (type(captured) is not datetime or captured.tzinfo is None or captured.utcoffset() is None
            or type(ceiling) is not int or not 0 <= ceiling <= 2**31 - 1
            or type(actor_id) is not str or not 1 <= len(actor_id) <= 64
            or type(key) is not bytes or len(key) != 32):
        unavailable()
    fields = json.dumps({"scope": scope, "snapshot": visible,
        "as_of": captured.astimezone(timezone.utc).isoformat(), "ceiling": ceiling,
        "actor": actor_id}, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, fields, hashlib.sha256).hexdigest()


def issue_bookmark(scope, visible, captured, ceiling, actor_id, key):
    value = f"v3:{scope}:{visible}:{signature(scope, visible, captured, ceiling, actor_id, key)}"
    if len(value) > 4096:
        unavailable()
    return value


def capability(db):
    scope, key = authority()
    db.execute(text("SET LOCAL lock_timeout = '2s'"))
    db.execute(text("SET LOCAL statement_timeout = '5s'"))
    # Admission, provenance completeness, snapshot capture and row reads share
    # one population even when an operator de-certifies storage concurrently.
    if db.scalar(text("SELECT current_setting('transaction_isolation')")) != "repeatable read":
        unavailable()
    tables = ("admin_audit_log", "admin_audit_provenance", "admin_audit_storage")
    db.execute(text("LOCK TABLE public.admin_audit_log, public.admin_audit_provenance, public.admin_audit_storage IN ACCESS SHARE MODE"))
    role = db.execute(text("SELECT rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolreplication FROM pg_roles WHERE rolname=current_user")).one()
    if len(role) != 5 or any(value is not False for value in role):
        unavailable()
    membership = db.execute(text("""SELECT
      ARRAY(SELECT DISTINCT p.rolname::text FROM pg_auth_members m
        JOIN pg_roles p ON p.oid=m.roleid
        WHERE m.member=(SELECT oid FROM pg_roles WHERE rolname=current_user)
        ORDER BY p.rolname::text) AS audit_reader_parents,
      EXISTS(SELECT FROM pg_auth_members m
        WHERE m.member=(SELECT oid FROM pg_roles WHERE rolname=current_user)
        AND m.admin_option) AS delegates""")).one()
    if (len(membership) != 2 or type(membership[0]) is not list
            or len(membership[0]) != 1 or type(membership[0][0]) is not str
            or membership[0][0] != 'audit_log_reader' or membership[1] is not False):
        unavailable()
    # Group flags are not inherited as ordinary object privileges. Validate
    # the same private group contract as migration, including later drift.
    groups = db.execute(text("""SELECT r.rolname,r.rolsuper,r.rolbypassrls,r.rolcanlogin,
      r.rolcreaterole,r.rolcreatedb,r.rolreplication,
      EXISTS(SELECT FROM pg_auth_members m WHERE m.member=r.oid) AS inherits
      FROM pg_roles r WHERE r.rolname IN ('audit_log_reader','audit_log_writer')
      ORDER BY r.rolname""")).all()
    if (len(groups) != 2
            or any(len(row) != 8 or any(value is not False for value in row[1:]) for row in groups)
            or [row[0] for row in groups] != ['audit_log_reader', 'audit_log_writer']):
        unavailable()
    if db.scalar(text("""SELECT
      has_schema_privilege('audit_log_reader','public','CREATE')
      OR has_schema_privilege('audit_log_writer','public','CREATE')
      OR NOT has_schema_privilege('audit_log_reader','public','USAGE')
      OR NOT has_schema_privilege('audit_log_writer','public','USAGE')
      OR has_sequence_privilege('audit_log_writer','public.admin_audit_log_id_seq','SELECT,UPDATE')
      OR NOT has_sequence_privilege('audit_log_writer','public.admin_audit_log_id_seq','USAGE')
      OR NOT has_table_privilege('audit_log_writer','public.admin_audit_log','SELECT')
      OR has_table_privilege('audit_log_writer','public.admin_audit_log','UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
      OR has_any_column_privilege('audit_log_writer','public.admin_audit_log','UPDATE,REFERENCES')
      OR has_column_privilege('audit_log_writer','public.admin_audit_log','id','INSERT')
      OR EXISTS(SELECT FROM unnest(ARRAY['actor_id','actor_email','action','target_type','target_id','payload','created_at']) n
        WHERE NOT has_column_privilege('audit_log_writer','public.admin_audit_log',n,'INSERT'))
      OR EXISTS(SELECT FROM pg_class c WHERE c.oid IN
        ('public.admin_audit_provenance'::regclass,'public.admin_audit_storage'::regclass)
        AND (has_table_privilege('audit_log_writer',c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
          OR has_any_column_privilege('audit_log_writer',c.oid,'SELECT,INSERT,UPDATE,REFERENCES')))
      OR EXISTS(SELECT FROM pg_class c WHERE c.oid IN
        ('public.admin_audit_log'::regclass,'public.admin_audit_provenance'::regclass,'public.admin_audit_storage'::regclass)
        AND (NOT has_table_privilege('audit_log_reader',c.oid,'SELECT')
          OR has_table_privilege('audit_log_reader',c.oid,'REFERENCES')
          OR has_any_column_privilege('audit_log_reader',c.oid,'REFERENCES')))
      AS unsafe_audit_group_authority""")) is not False:
        unavailable()
    if db.scalar(text("SELECT has_schema_privilege('public','CREATE')")) is not False:
        unavailable()
    if (db.scalar(text("SELECT has_sequence_privilege('public.admin_audit_log_id_seq','USAGE,SELECT,UPDATE')")) is not False
            or db.scalar(text("""SELECT EXISTS(SELECT FROM pg_roles r
              WHERE r.rolname IN ('anon','authenticated')
              AND has_sequence_privilege(r.oid,'public.admin_audit_log_id_seq','USAGE,SELECT,UPDATE'))""")) is not False):
        unavailable()
    if db.scalar(text("""SELECT EXISTS(SELECT FROM pg_roles r, pg_class c
      WHERE r.rolname IN ('anon','authenticated')
      AND c.oid IN ('public.admin_audit_log'::regclass,'public.admin_audit_provenance'::regclass,'public.admin_audit_storage'::regclass)
      AND (r.rolsuper OR r.rolbypassrls OR has_table_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
        OR has_any_column_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,REFERENCES')))""")) is not False:
        unavailable()
    for table in tables:
        checks = db.execute(text("""SELECT c.relkind='r' AND c.relpersistence='p' AS ordinary,
          c.relrowsecurity, c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) AS owns,
          has_table_privilege(c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') AS mutates,
          has_any_column_privilege(c.oid,'INSERT,UPDATE,REFERENCES') AS writes_column,
          row_security_active(c.oid) AS rls,
          to_regclass(:name)=c.oid AS resolves
          FROM pg_class c WHERE c.oid=CAST(:qualified AS regclass)"""),
          {"name": table, "qualified": "public." + table}).one()
        if (any(getattr(checks, field) is not True for field in ("ordinary", "relrowsecurity", "rls", "resolves"))
                or any(getattr(checks, field) is not False for field in ("owns", "mutates", "writes_column"))):
            unavailable()
    columns = db.execute(text("""SELECT attname,format_type(atttypid,atttypmod),attnotnull
      FROM pg_attribute WHERE attrelid='public.admin_audit_provenance'::regclass
      AND attnum>0 AND NOT attisdropped ORDER BY attnum""")).all()
    if ([tuple(c[:2]) for c in columns] != [("audit_id", "integer"), ("root_xid", "xid8"), ("incarnation", "uuid")]
            or any(c[2] is not True for c in columns)):
        unavailable()
    constraints = db.execute(text("""SELECT c.conname,c.contype,c.convalidated,
      c.conkey::text,c.confrelid::regclass::text,c.confkey::text,
      CASE WHEN c.conindid=0 THEN true ELSE i.indisvalid AND i.indisready AND i.indisunique END AS ready
      FROM pg_constraint c LEFT JOIN pg_index i ON i.indexrelid=c.conindid
      WHERE c.conrelid='public.admin_audit_provenance'::regclass ORDER BY c.conname""")).all()
    if [tuple(c) for c in constraints] != [
        ("admin_audit_provenance_audit_id_fkey", "f", True, "{1}", "admin_audit_log", "{1}", True),
        ("admin_audit_provenance_pkey", "p", True, "{1}", "-", None, True),
    ]:
        unavailable()
    if any(c.convalidated is not True or c.ready is not True for c in constraints):
        unavailable()
    audit_constraints = db.execute(text("""SELECT conname,convalidated,pg_get_constraintdef(oid)
      FROM pg_constraint WHERE conrelid='public.admin_audit_log'::regclass
      AND conname IN ('admin_audit_log_pkey','ck_admin_audit_positive_id') ORDER BY conname""")).all()
    if ([tuple(c) for c in audit_constraints] != [
        ("admin_audit_log_pkey", True, "PRIMARY KEY (id)"),
        ("ck_admin_audit_positive_id", True, "CHECK ((id > 0))")]
            or any(c[1] is not True for c in audit_constraints)):
        unavailable()
    expected_policies = {
        "admin_audit_log": [("audit_log_read", "r", True, ["audit_log_reader", "audit_log_writer"], "true", None),
                            ("audit_log_write", "a", True, ["audit_log_writer"], None, "true")],
        "admin_audit_provenance": [("audit_provenance_read", "r", True, ["audit_log_reader"], "true", None)],
        "admin_audit_storage": [("audit_storage_read", "r", True, ["audit_log_reader"], "true", None)],
    }
    for table, expected in expected_policies.items():
        rows = db.execute(text("""SELECT polname,polcmd,polpermissive,
          ARRAY(SELECT rolname::text FROM pg_roles WHERE oid=ANY(polroles) ORDER BY rolname),
          pg_get_expr(polqual,polrelid),pg_get_expr(polwithcheck,polrelid)
          FROM pg_policy WHERE polrelid=CAST(:t AS regclass) ORDER BY polname"""), {"t": "public." + table}).all()
        if [tuple(r) for r in rows] != expected or any(r[2] is not True for r in rows):
            unavailable()
    expected_triggers = {
        ("admin_audit_log", "audit_log_capture"): (5, CAPTURE_BODY, True),
        ("admin_audit_log", "audit_log_immutable"): (58, IMMUTABLE_BODY, False),
        ("admin_audit_provenance", "audit_provenance_immutable"): (58, IMMUTABLE_BODY, False),
    }
    triggers = db.execute(text("""SELECT c.relname,t.tgname,t.tgenabled,t.tgtype,p.prosrc,p.prosecdef,p.proconfig,
      p.proowner=c.relowner AS owned,t.tgqual IS NULL AS unconditional,t.tgnargs=0 AS noargs
      FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_class c ON c.oid=t.tgrelid
      WHERE t.tgrelid IN ('public.admin_audit_log'::regclass,'public.admin_audit_provenance'::regclass)
      AND NOT t.tgisinternal""")).all()
    if (len(triggers) != len(expected_triggers)
            or {(t.relname, t.tgname) for t in triggers} != set(expected_triggers)):
        unavailable()
    for t in triggers:
        expected = expected_triggers.get((t.relname, t.tgname))
        if (expected is None or (t.tgtype, t.prosrc.strip(), t.prosecdef) != expected
                or t.tgenabled != "A" or t.proconfig != ["search_path=pg_catalog"]
                or type(t.prosecdef) is not bool
                or t.owned is not True or t.unconditional is not True or t.noargs is not True):
            unavailable()
    identity_function = db.execute(text("""SELECT prosrc,prosecdef,proconfig,
      proowner=(SELECT relowner FROM pg_class WHERE oid='public.admin_audit_storage'::regclass) AS owned
      FROM pg_proc WHERE oid='public.audit_log_identity()'::regprocedure""")).one()
    if (identity_function.prosrc.strip() != IDENTITY_BODY or identity_function.prosecdef is not True
            or identity_function.proconfig != ["search_path=pg_catalog"] or identity_function.owned is not True):
        unavailable()
    state_columns = db.execute(text("""SELECT attname,format_type(atttypid,atttypmod),attnotnull
      FROM pg_attribute WHERE attrelid='public.admin_audit_storage'::regclass
      AND attnum>0 AND NOT attisdropped ORDER BY attnum""")).all()
    if ([tuple(c[:2]) for c in state_columns] != [("singleton", "boolean"), ("schema_version", "integer"),
        ("incarnation", "uuid"), ("system_identifier", "text"), ("database_oid", "oid"),
        ("timeline", "integer"), ("certified", "boolean")]
            or any(c[2] is not True for c in state_columns)):
        unavailable()
    state_constraints = db.execute(text("""SELECT conname,convalidated,pg_get_constraintdef(oid)
      FROM pg_constraint WHERE conrelid='public.admin_audit_storage'::regclass ORDER BY conname""")).all()
    if ([tuple(c) for c in state_constraints] != [
        ("admin_audit_storage_pkey", True, "PRIMARY KEY (singleton)"),
        ("ck_audit_storage_singleton", True, "CHECK (singleton)"),
        ("ck_audit_storage_version", True, "CHECK ((schema_version = 1))")]
            or any(c[1] is not True for c in state_constraints)):
        unavailable()
    states = db.execute(text("SELECT singleton,schema_version,incarnation::text,system_identifier,database_oid,timeline,certified FROM public.admin_audit_storage")).all()
    if len(states) != 1 or states[0].singleton is not True:
        unavailable()
    state = states[0]
    current = db.execute(text("SELECT * FROM public.audit_log_identity()")).one()
    if (type(state.schema_version) is not int or state.schema_version != 1
            or type(state.database_oid) is not int or type(state.timeline) is not int
            or type(state.system_identifier) is not str or state.incarnation != scope or state.certified is not True
            or type(current[1]) is not int or type(current[2]) is not int or current[3] is not False
            or tuple(current) != (state.system_identifier, state.database_oid, state.timeline, False)):
        unavailable()
    if db.scalar(text("SELECT EXISTS(SELECT FROM pg_prepared_xacts WHERE database=current_database())")) is not False:
        unavailable()
    # Unknown history is unavailable, even when client filters would hide it.
    if db.scalar(text("""SELECT EXISTS(SELECT FROM public.admin_audit_log a
      LEFT JOIN public.admin_audit_provenance p ON p.audit_id=a.id
      WHERE p.audit_id IS NULL OR p.incarnation<>CAST(:scope AS uuid)
      OR p.root_xid<'3'::xid8 OR p.root_xid>=pg_snapshot_xmax(pg_current_snapshot()))"""), {"scope": scope}) is not False:
        unavailable()
    return scope, key

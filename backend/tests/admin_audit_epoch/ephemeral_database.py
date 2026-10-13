"""Fresh full-head databases for existing inert writer fixtures.

History is never truncated. Only an empty, uncertified, exactly owned template
may be copied. Fixed-name process fixtures retain their original target guard.
"""
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
import json
import os
import re
from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

BACKEND = Path(__file__).resolve().parents[2]
PROFILES = (
    (55522, "batch10_mappings", "batch10-inert-local", "batch10_mappings"),
    (55485, "batch7_worker", "batch7-inert-local", "batch7_etl_worker"),
    (55495, "batch9_readiness", "batch9-inert-local", "batch9_native_readiness"),
    (55506, "batch9_review_596", "batch9-review-inert-local", "batch9-review-596"),
    (55507, "batch9_review_596", "batch9-review-inert-local", "batch9-review-596"),
    (55483, "batch7_coordinator", "batch7-inert-coordinator-local", "batch7_coordinator"),
    (55494, "batch7_coordinator", "batch7-inert-coordinator-local", "batch7_coordinator"),
)
_LIVE = {}


def close_owned_connections(connections):
    """Attempt every known owned probe; preserve any uncertain close result."""
    errors = []
    for connection in connections:
        try:
            connection.close()
        except Exception as error:
            errors.append(error)
    if errors:
        raise RuntimeError("Owned readiness probe cleanup remains unverified") from errors[0]


def profile(raw):
    url = make_url(raw)
    if (url.drivername != "postgresql+psycopg2" or url.host != "127.0.0.1"
            or url.query or any(k.startswith("PG") for k in os.environ)
            or (url.port, url.username, url.password, url.database) not in PROFILES):
        raise ValueError("Exact established inert fixture profile required")
    return url


def head():
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if heads != ["a611b12a0001"]:
        raise RuntimeError("Reviewed single durable audit head required")
    return heads[0]


def valid_identity(row):
    return (len(row) == 3 and type(row[0]) is int and 0 < row[0] < 2**32
        and type(row[1]) is str and bool(row[1]) and type(row[2]) is str
        and row[2].isascii() and row[2].isdigit() and 0 < int(row[2]) < 2**64)


def bound_connection(connection, name, user):
    row = connection.execute(text("SELECT current_database(),current_user,current_schema()")).one()
    if len(row) != 3 or tuple(row) != (name, user, "public"):
        raise RuntimeError("Actual fixture connection target/principal mismatch")


def identity(connection, name, user):
    row = connection.execute(text("""SELECT oid,pg_get_userbyid(datdba),
        (SELECT system_identifier::text FROM pg_control_system())
        FROM pg_database WHERE datname=:name"""), {"name": name}).one_or_none()
    values = tuple(row) if row is not None else ()
    if not valid_identity(values) or values[1] != user:
        raise RuntimeError("Actual fixture database owner/identity mismatch")
    return values


def owned_connection(connection, name, user, expected=None):
    """Bind every history read to the actual registered database and login."""
    bound_connection(connection, name, user)
    actual = identity(connection, name, user)
    if expected is not None and actual != expected:
        raise RuntimeError("Fixture connection identity changed")
    return actual


def empty_full_head(connection, expected_storage=None):
    # Do not infer visibility from role flags. A restricted table owner can
    # read all rows, but RLS must never turn retained history into an empty
    # template. PostgreSQL's off setting raises if filtering would apply.
    connection.execute(text('SET LOCAL row_security = off'))
    if connection.scalar(text('SHOW row_security')) != 'off':
        raise RuntimeError('Complete fixture population visibility required')
    versions = connection.execute(text("SELECT version_num FROM public.alembic_version")).all()
    if [tuple(row) for row in versions] != [(head(),)]:
        raise RuntimeError("Fixture template must use the actual full migration head")
    tables = connection.execute(text("""SELECT c.relname,c.relkind,c.relpersistence
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p','f','m') ORDER BY c.relname""")).all()
    names = [r[0] for r in tables]
    required = {'alembic_version','admin_audit_storage','admin_audit_log','admin_audit_provenance',
                'etl_dispatch_commands','etl_dispatch_worker','ingestion_jobs','seeding_domain_claims',
                'etl_dispatch_domains','countries'}
    if (not required <= set(names) or len(names) != len(set(names))
            or any(len(r)!=3 or type(r[0]) is not str or not re.fullmatch('[a-z][a-z0-9_]*',r[0])
                   or r[1] not in ('r','p') or r[2]!='p' for r in tables)):
        raise RuntimeError('Complete ordinary fixture table inventory required')
    for table in names:
        if table in ('alembic_version','admin_audit_storage'):
            continue
        if table=='batch7_coordinator_control':
            columns=connection.execute(text("""SELECT attname,format_type(atttypid,atttypmod),attnotnull
                FROM pg_attribute WHERE attrelid='public.batch7_coordinator_control'::regclass
                AND attnum>0 AND NOT attisdropped ORDER BY attnum""")).all()
            rows=connection.execute(text('SELECT * FROM public.batch7_coordinator_control')).all()
            if [tuple(r) for r in columns]!=[('mode','text',True)] or [tuple(r) for r in rows]!=[('normal',)]:
                raise RuntimeError('Refusing to copy or erase retained fixture history')
            continue
        if connection.scalar(text('SELECT EXISTS(SELECT FROM public."' + table + '")')) is not False:
            raise RuntimeError("Refusing to copy or erase retained fixture history")
    rows = connection.execute(text("SELECT singleton,schema_version,incarnation::text,system_identifier,database_oid::bigint,timeline,certified FROM public.admin_audit_storage")).all()
    state = tuple(rows[0]) if len(rows) == 1 else ()
    try:
        valid = (len(state)==7 and state[0] is True and type(state[1]) is int and state[1]==1
            and type(state[2]) is str and str(UUID(state[2]))==state[2]
            and type(state[3]) is str and state[3].isascii() and state[3].isdigit()
            and 0<int(state[3])<2**64 and type(state[4]) is int and 0<state[4]<2**32
            and type(state[5]) is int and 0<state[5]<2**32 and state[6] is False)
    except (ValueError,TypeError,AttributeError):
        valid=False
    if not valid:
        raise RuntimeError('Uncertified fixture storage identity required')
    if expected_storage is None:
        actual=tuple(connection.execute(text('SELECT * FROM public.audit_log_identity()')).one())
        if (len(actual)!=4 or type(actual[0]) is not str or type(actual[1]) is not int
                or type(actual[2]) is not int or actual[3] is not False
                or actual!=(state[3],state[4],state[5],False)):
            raise RuntimeError('Actual fixture storage identity mismatch')
    elif state != expected_storage:
        raise RuntimeError('Copied fixture storage identity mismatch')
    return state


class EmptyTemplate:
    def __init__(self, raw):
        self.url = profile(raw)
        self.template = "batch12_audit_template_" + uuid4().hex
        self.control = create_engine(self.url.set(database="postgres"),
            isolation_level="AUTOCOMMIT", poolclass=NullPool,
            connect_args={"hostaddr": "127.0.0.1", "connect_timeout": 5})
        self.created = {}
        self.pending = set()
        self.original = None
        self.storage_identity = {}
        base = create_engine(self.url, poolclass=NullPool,
            connect_args={"hostaddr": "127.0.0.1", "connect_timeout": 5})
        try:
            with base.connect() as c:
                self.original = owned_connection(c, self.url.database, self.url.username)
                self.original_storage = empty_full_head(c)
            with self.control.connect() as c:
                bound_connection(c, "postgres", self.url.username)
                if c.scalar(text("SELECT current_user")) != self.url.username:
                    raise RuntimeError("Actual fixture control owner mismatch")
                if identity(c, self.url.database, self.url.username) != self.original:
                    raise RuntimeError("Fixture source identity changed before copy")
                self.pending.add(self.template)
                c.execute(text(f'CREATE DATABASE "{self.template}" TEMPLATE "{self.url.database}"'))
                self.created[self.template] = identity(c, self.template, self.url.username)
                self.pending.remove(self.template)
            self._refresh(self.template)
        except BaseException:
            self.close()
            raise
        finally:
            base.dispose()

    def _refresh(self, name):
        # Copied empty fixture state is a new database, never restored evidence.
        if name not in self.created:
            raise ValueError("Only this fixture's newly created database may be refreshed")
        engine = create_engine(self.url.set(database=name), poolclass=NullPool)
        try:
            with engine.begin() as c:
                owned_connection(c, name, self.url.username, self.created[name])
                expected = self.original_storage if name==self.template else self.storage_identity[self.template]
                empty_full_head(c, expected)
                c.execute(text("""UPDATE public.admin_audit_storage SET incarnation=:scope,
                    system_identifier=i.system_identifier,database_oid=i.database_oid,
                    timeline=i.timeline,certified=false FROM public.audit_log_identity() i"""),
                    {"scope": uuid4()})
                self.storage_identity[name] = empty_full_head(c)
        finally:
            engine.dispose()

    def drop(self, name, expected):
        registered = self.created.get(name)
        if name == self.url.database and self.original is not None:
            registered = self.original
        if registered is None or not valid_identity(expected) or not valid_identity(registered) or expected != registered:
            raise ValueError("Only an exactly registered fixture database may be removed")
        if name == self.url.database and self.original is not None:
            original = create_engine(self.url, poolclass=NullPool)
            try:
                with original.connect() as c:
                    owned_connection(c, name, self.url.username, registered)
                    empty_full_head(c, self.original_storage)
            finally:
                original.dispose()
        with self.control.connect() as c:
            bound_connection(c, "postgres", self.url.username)
            if c.scalar(text("SELECT current_user")) != self.url.username:
                raise RuntimeError("Actual fixture control owner mismatch")
            if identity(c, name, self.url.username) != expected:
                raise RuntimeError("Fixture identity changed; removal refused")
            c.execute(text(f'DROP DATABASE "{name}"'))
            if c.scalar(text("SELECT EXISTS(SELECT FROM pg_database WHERE datname=:n)"), {"n": name}) is not False:
                raise RuntimeError("Owned fixture database remains after removal")
        self.created.pop(name, None)
        print("AUDIT_FIXTURE_DATABASE " + json.dumps({"name": name, "identity": expected, "absent": True}), flush=True)

    @contextmanager
    def database(self, *, fixed_name=False):
        if type(fixed_name) is not bool:
            raise ValueError("Explicit boolean fixture name mode required")
        name = self.url.database if fixed_name else "batch12_audit_case_" + uuid4().hex
        if fixed_name and self.original is not None:
            # The only pre-existing database removable here was verified empty.
            self.drop(name, self.original)
            self.original = None
        with self.control.connect() as c:
            bound_connection(c, "postgres", self.url.username)
            if identity(c, self.template, self.url.username) != self.created[self.template]:
                raise RuntimeError("Fixture template identity changed")
            self.pending.add(name)
            c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE "{self.template}"'))
            self.created[name] = identity(c, name, self.url.username)
            self.pending.remove(name)
        raw = self.url.set(database=name).render_as_string(hide_password=False)
        engine = None
        try:
            self._refresh(name)
            engine = create_engine(raw)
            _LIVE[raw] = (self, name, self.created[name])
            print("AUDIT_FIXTURE_DATABASE " + json.dumps({"name": name, "identity": self.created[name], "head": head(), "created": True}), flush=True)
            yield engine
        finally:
            _LIVE.pop(raw, None)
            if engine is not None:
                engine.dispose()
            self.drop(name, self.created[name])

    def close(self):
        errors = []
        try:
            for name, expected in list(self.created.items()):
                try:
                    self.drop(name, expected)
                except Exception as error:
                    errors.append((name, str(error)))
            if self.pending:
                errors.append((sorted(self.pending), "CREATE outcome/identity remains unverified"))
            if errors:
                print("AUDIT_FIXTURE_UNCERTAIN " + json.dumps({"cleanup": False, "errors": errors}), flush=True)
                raise RuntimeError("Owned fixture cleanup remains unverified")
        finally:
            self.control.dispose()


def validate_created_engine(engine):
    """A database-name pattern alone cannot authorize a child process."""
    raw = engine.url.render_as_string(hide_password=False)
    entry = _LIVE.get(raw)
    if entry is None:
        raise ValueError("An active owned per-case fixture is required")
    template, name, expected = entry
    registered = template.created.get(name)
    if registered is None or not valid_identity(expected) or not valid_identity(registered) or registered != expected:
        raise ValueError("A current owned per-case registration is required")
    with engine.connect() as c:
        owned_connection(c, name, template.url.username, expected)
    return raw

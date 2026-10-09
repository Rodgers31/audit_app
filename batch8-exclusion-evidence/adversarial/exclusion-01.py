"""Durable domain authority shared by every native CLI invocation and dispatch.

An execution lock is a continuity check, never proof that an abandoned writer
stopped. Only synchronous runner return plus its terminal observation permits
normal release. Unknown execution requires explicit operational reconciliation.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from models import EtlDispatchDomain, IngestionJob, IngestionStatus, SeedingDomainClaim

_dispatch_scope = ContextVar("authenticated_dispatch_scope", default=None)


class DomainOwnershipError(RuntimeError):
    """A safe bounded diagnostic: no database/provider exception payload."""


def clock(db):
    if db.get_bind().dialect.name == "postgresql":
        return db.scalar(select(func.clock_timestamp()))
    return datetime.now(timezone.utc)


def reserve(db, domain, identity, command_id=None):
    if type(domain) is not str or not 1 <= len(domain) <= 100 or not isinstance(identity, UUID):
        raise DomainOwnershipError("Invalid domain ownership request")
    dialect = db.get_bind().dialect.name
    insertion = {"postgresql": pg_insert, "sqlite": sqlite_insert}.get(dialect)
    if insertion is None:
        raise DomainOwnershipError("Domain ownership storage unsupported")
    # The unique active-domain index is the acquisition commit point, including
    # native/native and native/worker contenders using separate DB connections.
    return db.scalar(insertion(SeedingDomainClaim).values(id=identity, domain=domain,
        kind="native" if command_id is None else "dispatch", command_id=command_id,
        acquired_at=clock(db)).on_conflict_do_nothing().returning(SeedingDomainClaim.id)) is not None


def terminal_observation(db, claim, job_id):
    if type(job_id) is not int or job_id <= 0:
        return None
    job = db.get(IngestionJob, job_id)
    if job is None or job.domain != claim.domain or type(job.meta) is not dict or job.meta.get("seeding_claim_id") != str(claim.id):
        return None
    if job.status not in (IngestionStatus.COMPLETED, IngestionStatus.COMPLETED_WITH_ERRORS, IngestionStatus.FAILED):
        return None
    if type(job.errors) is not list or (job.status == IngestionStatus.COMPLETED and job.errors) or not all(type(v) is int and 0 <= v <= 2147483647 for v in (job.items_processed, job.items_created, job.items_updated)):
        return None
    if db.get_bind().dialect.name == "postgresql":
        start, end = db.execute(select(
            func.timezone(func.current_setting("TimeZone"), IngestionJob.started_at),
            func.timezone(func.current_setting("TimeZone"), IngestionJob.finished_at))
            .where(IngestionJob.id == job_id)).one()
    else:
        start, end = job.started_at, job.finished_at
    def aware(value):
        return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value
    start, end, acquired = aware(start), aware(end), aware(claim.acquired_at)
    tolerance = timedelta(seconds=5)
    if start is None or end is None or not acquired - tolerance <= start <= end <= clock(db) + tolerance:
        return None
    return job


class DomainExecution:
    def __init__(self, factory, domain, identity):
        self.factory, self.domain, self.identity = factory, domain, identity
        with factory() as db:
            self.engine = db.get_bind()
        self.connection = None
        self.pid = None
        self.key = int.from_bytes(sha256(("seeding:" + domain).encode()).digest()[:8], "big") & ((1 << 63) - 1)
        self.entered = False
        self.uncertain = False

    def open(self):
        if self.engine.dialect.name == "postgresql":
            self.connection = self.engine.connect()
            self.pid = self.connection.scalar(text("SELECT pg_backend_pid()"))
            if not self.connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": self.key}):
                self.close()
                raise DomainOwnershipError("Domain execution is already owned")
            self.connection.commit()

    def continuous(self):
        if self.connection is None:
            return self.engine.dialect.name == "sqlite"
        if self.connection.closed or self.connection.invalidated:
            return False
        return self.connection.scalar(text("""SELECT pg_backend_pid()=:pid AND EXISTS (
            SELECT 1 FROM pg_locks WHERE locktype='advisory' AND pid=:pid AND granted
            AND classid=:high AND objid=:low AND objsubid=1)"""),
            {"pid": self.pid, "high": self.key >> 32, "low": self.key & 0xffffffff}) is True

    def acknowledge(self, job_id):
        if self.uncertain or not self.continuous():
            raise DomainOwnershipError("Execution unverified; domain ownership retained")
        with self.factory.begin() as db:
            claim = db.get(SeedingDomainClaim, self.identity, with_for_update=True)
            if claim is None or claim.released_at is not None or claim.returned_at is not None or terminal_observation(db, claim, job_id) is None:
                raise DomainOwnershipError("Terminal observation unverified; domain ownership retained")
            claim.returned_at = clock(db)
            claim.job_id = job_id
            if claim.kind == "native":
                claim.released_at = claim.returned_at
        # Commit before reporting normal release. Ambiguous commits do not retry.

    def close(self):
        if self.connection is not None:
            try:
                # An invalid connection may have lost its lock. Closing never
                # changes durable authority, and never reconnects to clear it.
                if not self.connection.closed and not self.connection.invalidated:
                    self.connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self.key})
                    self.connection.commit()
            finally:
                self.connection.close()
                self.connection = None


@contextmanager
def dispatch_scope(execution):
    token = _dispatch_scope.set(execution)
    try:
        yield
    finally:
        _dispatch_scope.reset(token)


def enter_domain(factory, domain):
    scope = _dispatch_scope.get()
    if scope is not None:
        with factory() as db:
            same_engine = db.get_bind() is scope.engine
        if type(scope) is not DomainExecution or not same_engine or scope.domain != domain or scope.entered or not scope.continuous():
            raise DomainOwnershipError("Dispatch ownership scope invalid")
        scope.entered = True
        return scope
    execution = DomainExecution(factory, domain, uuid4())
    try:
        execution.open()
        with factory.begin() as db:
            # Legacy RUNNING observations/retained dispatch rows are uncertainty,
            # not permission to take over during an additive schema transition.
            legacy = db.get(EtlDispatchDomain, domain) if domain == "audits" else None
            if legacy is not None and legacy.command_id is not None or db.scalar(select(IngestionJob.id).where(IngestionJob.domain == domain, IngestionJob.status == IngestionStatus.RUNNING).limit(1)) or not reserve(db, domain, execution.identity):
                raise DomainOwnershipError("Domain ownership unavailable; reconcile retained execution")
        execution.entered = True
        return execution
    except BaseException:
        execution.close()
        raise

"""Durable domain authority shared by every native CLI invocation and dispatch.

An execution lock is a continuity check, never proof that an abandoned writer
stopped. Only synchronous runner return plus its terminal observation permits
normal release. Unknown execution requires explicit operational reconciliation.

Entry is durable and one-use: native acquisition records it with the claim; a
dispatch claim records it only when the CLI enters with the exact correlated
command, token, worker generation and dry-run intent. Acknowledgement requires the
entry nonce the entering object received. The claim stores only a one-way digest
of it, so neither another object nor a database reader can acknowledge; only a
database writer could, by changing the row directly.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import re
from uuid import UUID, uuid4

from sqlalchemy import func, inspect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from models import (EtlDispatchCommand, EtlDispatchDomain, EtlDispatchWorker, IngestionJob,
    IngestionStatus, SeedingDomainClaim)

_dispatch_scope = ContextVar("authenticated_dispatch_scope", default=None)


class DomainOwnershipError(RuntimeError):
    """A safe bounded diagnostic: no database/provider exception payload."""


def _require_claim_storage(connection):
    """Prove the actual active-domain arbiter, on the admission transaction.

    A table/index name or successful insert is insufficient: without the partial
    unique domain index, ON CONFLICT silently admits another retained owner.
    Inspect fresh connection-local metadata, never a cached startup verdict.
    PostgreSQL's table read also holds ACCESS SHARE until this transaction ends;
    ordinary DROP/ALTER cannot replace the checked table during admission. This
    does not fence arbitrary privileged concurrent index DDL during a run.
    """
    try:
        # Select every required claim column without reading any claim data.
        connection.execute(select(SeedingDomainClaim.__table__).limit(0))
        dialect = connection.dialect.name
        if dialect == "postgresql":
            ready = connection.scalar(text("""SELECT EXISTS (
                SELECT 1 FROM pg_class t
                JOIN pg_index i ON i.indrelid=t.oid
                JOIN pg_attribute a ON a.attrelid=t.oid AND a.attname='domain'
                WHERE t.oid=to_regclass('seeding_domain_claims') AND t.relkind IN ('r','p')
                AND i.indisunique AND i.indisvalid AND i.indisready AND i.indislive
                AND i.indimmediate AND i.indnkeyatts=1 AND i.indkey[0]=a.attnum
                AND i.indexprs IS NULL AND pg_get_expr(i.indpred,i.indrelid)='(released_at IS NULL)'
            )"""))
        elif dialect == "sqlite":
            ready = False
            # SQLite resolves TEMP before main and folds ASCII identifier case.
            # Metadata matching must use that same identity before checking main.
            shadow = connection.scalar(text("SELECT EXISTS (SELECT 1 FROM sqlite_temp_master WHERE name='seeding_domain_claims' COLLATE NOCASE)"))
            if not shadow and connection.scalar(text("SELECT type FROM sqlite_master WHERE name='seeding_domain_claims' COLLATE NOCASE")) == "table":
                for index in inspect(connection).get_indexes("seeding_domain_claims"):
                    predicate = index.get("dialect_options", {}).get("sqlite_where")
                    if (index.get("unique") and index.get("column_names") == ["domain"]
                            and re.fullmatch(r'\(*\s*(?:"released_at"|released_at)\s+IS\s+NULL\s*\)*',
                                str(predicate).strip(), re.IGNORECASE)):
                        ready = True
                        break
        else:
            ready = False
        if not ready:
            raise DomainOwnershipError("Domain ownership storage incomplete; shared migration required")
    except SQLAlchemyError:
        raise DomainOwnershipError("Domain ownership storage unavailable; shared migration required") from None


def clock(db):
    if db.get_bind().dialect.name == "postgresql":
        return db.scalar(select(func.clock_timestamp()))
    return datetime.now(timezone.utc)


def entry_digest(entry):
    """What the claim stores for an entry nonce; the nonce itself is never stored."""
    return UUID(bytes=sha256(b"seeding-entry:" + entry.bytes).digest()[:16])


def reserve(db, domain, identity, command_id=None, entry=None):
    """Atomically acquire the domain. A native claim is entered as it is acquired.

    A native claim reserved without an entry nonce can never be acknowledged by
    anyone: it stays retained until explicit operational reconciliation.
    """
    native = command_id is None
    if (type(domain) is not str or not 1 <= len(domain) <= 100 or not isinstance(identity, UUID)
            or not (native or isinstance(command_id, UUID)) or not (entry is None or native and isinstance(entry, UUID))):
        raise DomainOwnershipError("Invalid domain ownership request")
    dialect = db.get_bind().dialect.name
    insertion = {"postgresql": pg_insert, "sqlite": sqlite_insert}.get(dialect)
    if insertion is None:
        raise DomainOwnershipError("Domain ownership storage unsupported")
    _require_claim_storage(db.connection())
    now = clock(db)
    # The unique active-domain index is the acquisition commit point, including
    # native/native and native/worker contenders using separate DB connections.
    return db.scalar(insertion(SeedingDomainClaim).values(id=identity, domain=domain,
        kind="native" if native else "dispatch", command_id=command_id, acquired_at=now,
        entered_at=now if native else None, entry_id=entry_digest(entry or uuid4()) if native else None)
        .on_conflict_do_nothing().returning(SeedingDomainClaim.id)) is not None


def unclaimed_running(db, domain):
    """A RUNNING observation from a writer outside this seam (e.g. written before
    the migration). Only a tag resolving to an active claim for this domain is
    governed by that claim; an arbitrary string is not ownership evidence.
    No age limit: an old row is uncertainty, never permission to take over."""
    for meta in db.scalars(select(IngestionJob.meta).where(
            IngestionJob.domain == domain, IngestionJob.status == IngestionStatus.RUNNING)):
        if not (type(meta) is dict and type(meta.get("seeding_claim_id")) is str):
            return True
        try:
            identity = UUID(meta["seeding_claim_id"])
        except ValueError:
            return True
        ownership = db.get(SeedingDomainClaim, identity)
        if ownership is None or ownership.domain != domain or ownership.released_at is not None:
            return True
    return False


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
    def __init__(self, factory, domain, identity, command_id=None, generation=None):
        self.factory, self.domain, self.identity = factory, domain, identity
        # Dispatch correlation. Both are re-proven against durable rows at entry.
        self.command_id, self.generation = command_id, generation
        with factory() as db:
            self.engine = db.get_bind()
        self.connection = None
        self.pid = None
        self.key = int.from_bytes(sha256(("seeding:" + domain).encode()).digest()[:8], "big") & ((1 << 63) - 1)
        self.entered = False
        self.entry = None

    def open(self):
        if self.engine.dialect.name == "postgresql":
            # A transaction-scoped lock in a transaction held open until close().
            # The open transaction pins one backend even behind a transaction
            # pooler, and the lock can never outlive it on a pooled connection.
            self.connection = self.engine.connect()
            # The lock transaction idles for the whole domain run; a server-side
            # idle cutoff would end it and strand the claim (fail closed).
            self.connection.execute(text("SET LOCAL idle_in_transaction_session_timeout = 0"))
            self.pid = self.connection.scalar(text("SELECT pg_backend_pid()"))
            if not self.connection.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": self.key}):
                self.close()
                raise DomainOwnershipError("Domain execution is already owned")
            if not self.continuous():  # e.g. an autocommit engine already dropped it
                self.close()
                raise DomainOwnershipError("Domain execution lock is not held")
        try:
            if self.connection is not None:
                _require_claim_storage(self.connection)
            else:
                with self.factory() as db:
                    _require_claim_storage(db.connection())
        except BaseException:
            self.close()
            raise

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
        if not self.entered or not isinstance(self.entry, UUID) or not self.continuous():
            raise DomainOwnershipError("Execution unverified; domain ownership retained")
        with self._acknowledgement_transaction() as db:
            claim = db.get(SeedingDomainClaim, self.identity, with_for_update=True)
            # Bound to this object's own durable entry: same domain, kind and
            # command, and the nonce (not its stored digest) this object entered with.
            if (claim is None or claim.domain != self.domain or claim.entry_id != entry_digest(self.entry)
                    or claim.entered_at is None or claim.command_id != self.command_id
                    or claim.kind != ("native" if self.command_id is None else "dispatch")
                    or claim.released_at is not None or claim.returned_at is not None
                    or terminal_observation(db, claim, job_id) is None):
                raise DomainOwnershipError("Terminal observation unverified; domain ownership retained")
            claim.returned_at = clock(db)
            claim.job_id = job_id
            if claim.kind == "native":
                claim.released_at = claim.returned_at
        # Commit before reporting normal release. Ambiguous commits do not retry.

    @contextmanager
    def _acknowledgement_transaction(self):
        if self.engine.dialect.name == "postgresql":
            # Commit the acknowledgement on the transaction that holds the
            # continuity lock. If that backend dies at any point, its claim
            # update rolls back with it; a second connection must not release
            # authority on the strength of an earlier continuity check.
            # A rejected observation rolls back only its savepoint, preserving
            # the existing lock for a correctly bound observation. Successful
            # validation commits the outer lock transaction exactly once.
            with self.factory(bind=self.connection, join_transaction_mode="create_savepoint") as db:
                with db.begin():
                    yield db
            self.connection.commit()
        else:
            with self.factory.begin() as db:
                yield db

    def close(self):
        if self.connection is not None:
            try:
                # Ending the transaction releases the lock. Closing never changes
                # durable authority, and never reconnects to clear it.
                if not self.connection.closed and not self.connection.invalidated:
                    self.connection.rollback()
            except BaseException:
                # Never return a connection in an unknown state to the pool.
                self.connection.invalidate()
                raise
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


def _enter_dispatch(factory, scope, domain, dry_run):
    """Consume the exact correlated dispatch claim once, before any handler runs."""
    from admin_etl_dispatch import fresh, mapped  # only reachable from the adapter process

    if (type(scope) is not DomainExecution or scope.domain != domain or scope.entered or scope.entry is not None
            or type(dry_run) is not bool
            or not all(isinstance(v, UUID) for v in (scope.identity, scope.command_id, scope.generation))):
        raise DomainOwnershipError("Dispatch ownership scope invalid")
    with factory() as db:
        same_engine = db.get_bind() is scope.engine
    if not same_engine or not scope.continuous():
        raise DomainOwnershipError("Dispatch ownership scope invalid")
    entry = uuid4()
    with factory.begin() as db:
        _require_claim_storage(db.connection())
        # Same lock order as the worker's claim/finish and the adapter.
        worker = db.get(EtlDispatchWorker, 1, with_for_update=True)
        now = clock(db)
        row = db.get(EtlDispatchDomain, domain, with_for_update=True)
        command = db.get(EtlDispatchCommand, scope.command_id, with_for_update=True)
        claim = db.get(SeedingDomainClaim, scope.identity, with_for_update=True)
        if (not fresh(worker, now) or worker.generation != scope.generation
                or row is None or row.command_id != scope.command_id or row.claim_token != scope.identity
                or command is None or command.status != "running" or command.execution_started is not True
                or command.domain != domain or command.dry_run is not dry_run
                or not mapped(command.source, domain)
                or command.claim_token != scope.identity
                or command.generation != scope.generation
                or claim is None or claim.kind != "dispatch" or claim.domain != domain
                or claim.command_id != scope.command_id or claim.entered_at is not None
                or claim.returned_at is not None or claim.released_at is not None):
            raise DomainOwnershipError("Dispatch ownership scope invalid")
        claim.entered_at, claim.entry_id = now, entry_digest(entry)
    scope.entered, scope.entry = True, entry
    return scope


def enter_domain(factory, domain, dry_run):
    scope = _dispatch_scope.get()
    if scope is not None:
        return _enter_dispatch(factory, scope, domain, dry_run)
    execution = DomainExecution(factory, domain, uuid4())
    entry = uuid4()
    try:
        execution.open()
        with factory.begin() as db:
            # Legacy RUNNING observations/retained dispatch rows are uncertainty,
            # not permission to take over during an additive schema transition.
            legacy = db.get(EtlDispatchDomain, domain)
            if legacy is not None and legacy.command_id is not None or unclaimed_running(db, domain) or not reserve(db, domain, execution.identity, entry=entry):
                raise DomainOwnershipError("Domain ownership unavailable; reconcile retained execution")
        execution.entered, execution.entry = True, entry
        return execution
    except BaseException:
        execution.close()
        raise

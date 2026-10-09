"""Legacy loader authority using the reviewed native domain claim protocol.

Reference rows are shared by thirteen native domains. Acquire that conservative
set in lexical order before any loader effect, regardless of the document kind.
Learning hub and IMF WEO write independent tables and remain concurrent.
"""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import logging
import sys
from threading import get_ident

from sqlalchemy import event, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from models import EtlDispatchDomain, IngestionJob, IngestionStatus, SeedingDomainClaim
from seeding.exclusion import DomainOwnershipError, enter_domain

logger = logging.getLogger(__name__)
LEGACY_DOMAINS = (
    "audits", "counties_budget", "county_officials", "debt_timeline",
    "economic_indicators", "fiscal_summary", "national_budget", "national_debt",
    "national_gdp", "pending_bills", "population", "revenue_by_source", "stalled_projects",
)
_scope = ContextVar("legacy_loader_writer", default=None)


def caller():
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return get_ident(), task


def engine_for(bind):
    if not isinstance(bind, Engine) or bind.dialect.name not in ("postgresql", "sqlite"):
        raise DomainOwnershipError("Legacy writer ownership storage unavailable")
    return bind


def check_ready(engine):
    """Read-only startup check. A missing migration never selects an unlocked path."""
    factory = sessionmaker(bind=engine_for(engine))
    try:
        with factory() as db:
            db.execute(select(SeedingDomainClaim).limit(0))
            db.execute(select(IngestionJob).limit(0))
            db.execute(select(EtlDispatchDomain).limit(0))
        indexes = inspect(engine).get_indexes("seeding_domain_claims")
        def active_domain_index(index):
            predicate = index.get("dialect_options", {}).get(engine.dialect.name + "_where")
            predicate = "".join(str(predicate).lower().replace("(", "").replace(")", "").split())
            return (index.get("unique") and index.get("column_names") == ["domain"]
                    and predicate == "released_atisnull")
        if not any(active_domain_index(index) for index in indexes):
            raise DomainOwnershipError("Legacy writer requires the unique active-domain index")
    except SQLAlchemyError:
        raise DomainOwnershipError("Legacy writer requires the shared ownership migration") from None


class WriterScope:
    def __init__(self, engine):
        self.engine = engine_for(engine)
        self.factory = sessionmaker(bind=self.engine)
        self.owner = caller()
        self.executions = []
        self.jobs = {}
        self.sessions = set()
        self.failed = False
        self.uncertain = False
        self.manual_token = None
        self.pending_domain = None

    def note_failure(self, exc_type):
        self.failed = True
        self.uncertain |= not issubclass(exc_type, Exception) or issubclass(exc_type, SQLAlchemyError)

    def validate(self, engine):
        if self.owner != caller() or self.engine is not engine_for(engine):
            raise DomainOwnershipError("Legacy ownership cannot be inherited by another caller")

    def acquire(self):
        check_ready(self.engine)
        for domain in LEGACY_DOMAINS:
            self.pending_domain = domain
            execution = enter_domain(self.factory, domain, False)
            self.executions.append(execution)
            with self.factory.begin() as db:
                job = IngestionJob(domain=domain, status=IngestionStatus.RUNNING,
                    dry_run=False, started_at=datetime.now(timezone.utc),
                    items_processed=0, items_created=0, items_updated=0, errors=[],
                    meta={"seeding_claim_id": str(execution.identity), "writer": "legacy_etl",
                          "counts_scope": "ownership_only"})
                db.add(job)
                db.flush()
                self.jobs[domain] = job.id
        self.pending_domain = None

    def finish(self):
        try:
            self._finish()
        except SQLAlchemyError:
            self.uncertain = True
            raise DomainOwnershipError("Legacy ownership receipt uncertain; ownership retained") from None

    def _finish(self):
        if self.sessions or self.uncertain:
            raise DomainOwnershipError("Legacy writer return uncertain; ownership retained")
        if not all(execution.continuous() for execution in self.executions):
            raise DomainOwnershipError("Legacy continuity lost; ownership retained")
        # These are ownership observations, never a fabricated financial census.
        # Only a synchronous caller return, after all sessions close, reaches here.
        with self.factory.begin() as db:
            for execution in self.executions:
                job = db.get(IngestionJob, self.jobs[execution.domain])
                job.status = IngestionStatus.FAILED if self.failed else IngestionStatus.COMPLETED
                job.finished_at = datetime.now(timezone.utc)
                job.errors = ["legacy loader call failed"] if self.failed else []
        for execution in reversed(self.executions):
            # Shared API proves and commits each release on its lock backend.
            execution.acknowledge(self.jobs[execution.domain])

    def close(self):
        for execution in reversed(self.executions):
            try:
                execution.close()
            except SQLAlchemyError:
                logger.error("Legacy continuity connection lost; durable ownership retained")


def acquire_scope(engine):
    active = WriterScope(engine)
    try:
        active.acquire()
        return active
    except DomainOwnershipError:
        # No loader was called. Return only the partial set with honest receipts.
        active.failed = True
        try:
            active.finish()
            if active.pending_domain is not None:
                with active.factory.begin() as db:
                    now = datetime.now(timezone.utc)
                    db.add(IngestionJob(domain=active.pending_domain, status=IngestionStatus.FAILED,
                        dry_run=False, started_at=now, finished_at=now, items_processed=0,
                        items_created=0, items_updated=0, errors=["legacy writer ownership refused"],
                        meta={"writer": "legacy_etl", "ownership_refused": True, "counts_scope": "ownership_only"}))
        except SQLAlchemyError:
            # Observation storage cannot turn the original refusal into a
            # generic pipeline error that its optional-source handling swallows.
            logger.error("Legacy refusal observation unavailable; no loader work started")
        finally:
            active.close()
        logger.error("Legacy writer ownership refused; no loader work started")
        raise
    except SQLAlchemyError:
        active.close()
        logger.error("Legacy ownership storage failed; acquired claims retained")
        raise DomainOwnershipError("Legacy ownership storage unavailable; acquired claims retained") from None
    except BaseException:
        active.close()
        raise


@contextmanager
def writer_scope(engine):
    active = _scope.get()
    if active is not None:
        active.validate(engine)
        try:
            yield active
        except Exception as exc:
            active.note_failure(type(exc))
            raise
        return
    active = acquire_scope(engine)
    try:
        token = _scope.set(active)
        returned = False
        try:
            try:
                yield active
                returned = True
            except Exception as exc:
                active.note_failure(type(exc))
                returned = True
                raise
        finally:
            _scope.reset(token)
            if returned:
                active.finish()
            else:
                logger.error("Legacy writer interrupted; ownership retained across restart")
    finally:
        active.close()


def owned_write(method):
    @wraps(method)
    async def wrapped(self, *args, **kwargs):
        with writer_scope(self.engine):
            return await method(self, *args, **kwargs)
    return wrapped


class OwnedSession(Session):
    """Manual loader sessions own writes until close; closed sessions cannot reopen."""
    def __init__(self, *args, **kwargs):
        if kwargs.get("binds") is not None:
            raise DomainOwnershipError("Legacy sessions require one owned engine")
        kwargs["close_resets_only"] = False
        super().__init__(*args, **kwargs)
        engine = engine_for(self.get_bind())
        self._ownership = _scope.get()
        if self._ownership is None:
            self._ownership = acquire_scope(engine)
            self._ownership.manual_token = _scope.set(self._ownership)
        else:
            self._ownership.validate(engine)
        self._ownership.sessions.add(self)
        self._ownership_closed = False

    def get_bind(self, *args, **kwargs):
        bind = super().get_bind(*args, **kwargs)
        ownership = getattr(self, "_ownership", None)
        if ownership is not None and bind is not ownership.engine:
            raise DomainOwnershipError("Legacy sessions cannot change their owned engine")
        return bind

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            self._ownership.note_failure(exc_type)
        self.close()

    def close(self):
        if self._ownership_closed:
            return
        self._ownership.validate(self.get_bind())
        exc_type = sys.exc_info()[0]
        if exc_type is not None:
            self._ownership.note_failure(exc_type)
        self._ownership.uncertain |= self.info.get("legacy_commit_in_progress", False)
        try:
            super().close()
        except BaseException:
            self._ownership.uncertain = True
            raise
        finally:
            self._ownership_closed = True
            self._ownership.sessions.discard(self)
            # Manual sessions share a lifetime independent of close order. A
            # decorated loader call owns its own finalization instead.
            if self._ownership.manual_token is not None and not self._ownership.sessions:
                _scope.reset(self._ownership.manual_token)
                try:
                    self._ownership.finish()
                finally:
                    self._ownership.close()

    def connection(self, *args, **kwargs):
        # A raw Connection can commit independently of ORM return/uncertainty.
        # The supported manual callers use query/add/execute/commit/close.
        raise DomainOwnershipError("Raw connections cannot escape legacy writer ownership")

    def bind_mapper(self, *args, **kwargs):
        raise DomainOwnershipError("Legacy sessions cannot change their owned engine")

    def bind_table(self, *args, **kwargs):
        raise DomainOwnershipError("Legacy sessions cannot change their owned engine")

    def commit(self):
        self._ownership.validate(self.get_bind())
        try:
            return super().commit()
        except BaseException:
            self._ownership.uncertain = True
            raise

    def execute(self, *args, **kwargs):
        self._ownership.validate(self.get_bind())
        try:
            return super().execute(*args, **kwargs)
        except SQLAlchemyError:
            self._ownership.uncertain = True
            raise

    def flush(self, *args, **kwargs):
        self._ownership.validate(self.get_bind())
        try:
            return super().flush(*args, **kwargs)
        except SQLAlchemyError:
            self._ownership.uncertain = True
            raise


@event.listens_for(OwnedSession, "before_commit")
def _before_commit(session):
    session._ownership.validate(session.get_bind())
    session.info["legacy_commit_in_progress"] = True


@event.listens_for(OwnedSession, "after_commit")
def _after_commit(session):
    session.info["legacy_commit_in_progress"] = False


@event.listens_for(OwnedSession, "before_flush")
def _before_flush(session, flush_context, instances):
    session._ownership.validate(session.get_bind())


@event.listens_for(OwnedSession, "do_orm_execute")
def _before_execute(state):
    state.session._ownership.validate(state.session.get_bind())

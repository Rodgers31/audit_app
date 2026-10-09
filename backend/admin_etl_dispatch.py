"""Private, default-off dispatch acceptance and bounded operational receipts.

Database transactions are authoritative. The API never imports the worker/runner.
"""
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4
import os

from fastapi import HTTPException
from pydantic import AfterValidator, BaseModel, ConfigDict, StrictBool, StrictInt, field_validator, model_validator
from sqlalchemy import func, select, text, update

from models import AdminAuditLog, EtlDispatchCommand, EtlDispatchWorker
from routers.admin_operations import DISPATCH_ERROR, PRIVATE_HEADERS, bounded_integer
from utils.audit_policy import safe_audit_payload

SOURCES = ("treasury", "cob", "oag", "knbs", "opendata", "cra")
SOURCE_DOMAINS = {"oag": "audits"}
Source = Literal["treasury", "cob", "oag", "knbs", "opendata", "cra"]
Status = Literal["queued", "running", "completed", "failed", "interrupted"]
UNAVAILABLE = "Dedicated worker dispatch is unavailable."
UNSUPPORTED = "This source has no approved dispatch mapping."


def utc_datetime(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("UTC-aware timestamp required")
    return value.astimezone(timezone.utc)


UtcDatetime = Annotated[datetime, AfterValidator(utc_datetime)]


def enabled():
    return os.environ.get("ADMIN_ETL_DISPATCH_ENABLED") == "true"


def canonical_uuid(value):
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError("Canonical UUID required")
    parsed = UUID(value)
    if str(parsed) != value:
        raise ValueError("Canonical UUID required")
    return parsed


class TriggerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dry_run: StrictBool = False
    dispatch_generation: UUID | None = None

    @field_validator("dispatch_generation", mode="before")
    @classmethod
    def generation_shape(cls, value):
        return None if value is None else canonical_uuid(value)


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    source: Source
    dry_run: StrictBool
    status: Status
    version: StrictInt
    created_at: UtcDatetime
    updated_at: UtcDatetime
    started_at: UtcDatetime | None
    finished_at: UtcDatetime | None
    job_id: StrictInt | None
    outcome: Literal["completed", "failed", "execution_unverified"] | None

    @model_validator(mode="after")
    def coherent_receipt(self):
        if not 1 <= self.version <= 9007199254740991 or self.updated_at < self.created_at:
            raise ValueError("Invalid receipt ordering")
        if self.started_at and not self.created_at <= self.started_at <= self.updated_at:
            raise ValueError("Invalid start")
        if self.finished_at and not (self.started_at or self.created_at) <= self.finished_at <= self.updated_at:
            raise ValueError("Invalid finish")
        if self.job_id is not None and not 1 <= self.job_id <= 2147483647:
            raise ValueError("Invalid observation")
        if self.status == "queued":
            valid = all(v is None for v in (self.started_at, self.finished_at, self.job_id, self.outcome))
        elif self.status == "running":
            valid = self.started_at is not None and self.finished_at is None and self.outcome is None
        elif self.status == "completed":
            valid = self.started_at is not None and self.finished_at is not None and self.job_id is not None and self.outcome == "completed"
        elif self.status == "failed":
            valid = self.finished_at is not None and self.outcome == "failed"
        else:
            valid = self.started_at is not None and self.finished_at is not None and self.outcome == "execution_unverified"
        if not valid:
            raise ValueError("Invalid receipt state")
        return self


class WorkerCapability(BaseModel):
    status: Literal["ready", "unavailable"]
    last_seen_at: UtcDatetime | None
    expires_at: UtcDatetime | None


class SourceCapability(BaseModel):
    available: StrictBool
    reason: str


class DispatchCapability(BaseModel):
    timestamp: UtcDatetime
    evidence: Literal["worker_dispatch"]
    available: StrictBool
    reason: str
    generation: UUID | None
    worker: WorkerCapability
    sources: dict[Source, SourceCapability]


class Accepted(BaseModel):
    ok: Literal[True] = True
    accepted: Literal[True] = True
    replayed: StrictBool
    audit_recorded: Literal[True] = True
    command: Command


class CommandPage(BaseModel):
    entries: list[Command]
    page: StrictInt
    page_size: StrictInt
    total: StrictInt
    has_more: StrictBool


def unavailable():
    raise HTTPException(503, detail=dict(DISPATCH_ERROR), headers=PRIVATE_HEADERS)


def db_clock(db):
    if db.get_bind().dialect.name != "postgresql":
        unavailable()
    return db.scalar(select(func.clock_timestamp()))


def fresh(worker, now):
    return worker is not None and worker.ready is True and worker.last_seen_at <= now < worker.expires_at


def retire_expired(db):
    """Observe lease loss durably, without running or replaying any command.

    Polling must not leave a dead process reporting running indefinitely. This
    only fences receipts; the durable domain exclusion is deliberately untouched.
    The worker row serializes this transition with heartbeat/claim/completion.
    """
    worker = db.scalar(select(EtlDispatchWorker).where(EtlDispatchWorker.id == 1).with_for_update())
    now = db_clock(db)
    conditions = [EtlDispatchCommand.status == "running"]
    if fresh(worker, now):
        conditions.append(EtlDispatchCommand.generation != worker.generation)
    db.execute(update(EtlDispatchCommand).where(*conditions).values(status="interrupted",
        finished_at=now, updated_at=now, outcome="execution_unverified", version=EtlDispatchCommand.version + 1))
    return worker, now


def capability(db):
    now = datetime.now(timezone.utc)
    worker = None
    available = False
    generation = last_seen_at = expires_at = None
    if enabled():
        try:
            db_clock(db)
            worker, now = retire_expired(db)
            available = fresh(worker, now)
            if worker is not None:
                generation, last_seen_at, expires_at = worker.generation, worker.last_seen_at, worker.expires_at
            db.commit()
        except Exception:
            db.rollback()
            worker = None
            available = False
            generation = last_seen_at = expires_at = None
    reason = "Dedicated worker is ready for supported sources." if available else UNAVAILABLE
    return DispatchCapability(timestamp=now, evidence="worker_dispatch", available=available, reason=reason,
        generation=generation if available else None,
        worker=WorkerCapability(status="ready" if available else "unavailable",
            last_seen_at=last_seen_at, expires_at=expires_at),
        sources={s: SourceCapability(available=available and s in SOURCE_DOMAINS,
            reason=reason if s in SOURCE_DOMAINS or not available else UNSUPPORTED) for s in SOURCES})


def accept(db, actor, source, body, key):
    if source not in SOURCES:
        raise HTTPException(404, "Unknown ETL source")
    # Embedded/direct callers must uphold the same strict intent boundary as
    # FastAPI. Python equality would otherwise let 0/1 impersonate booleans on
    # a replay, and model_construct can bypass normal Pydantic validation.
    if not isinstance(body, TriggerBody) or type(body.dry_run) is not bool or body.dispatch_generation is not None and not isinstance(body.dispatch_generation, UUID):
        raise HTTPException(422, "Invalid operations parameters")
    # Disabled acceptance must not connect, retire receipts or replay old work,
    # regardless of whether the request supplies an idempotency key.
    if not enabled():
        unavailable()
    try:
        intent_key = canonical_uuid(key)
    except (ValueError, TypeError, AttributeError):
        if not enabled():
            unavailable()
        raise HTTPException(422, "Invalid operations parameters") from None
    try:
        # Serialize one actor/key, including duplicates racing the first commit.
        # Hash collisions cause harmless contention; identity uses the full columns.
        db_clock(db)
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:actor), hashtext(:key))"), {"actor": actor.id, "key": str(intent_key)})
        worker, now = retire_expired(db)
        original = db.scalar(select(EtlDispatchCommand).where(EtlDispatchCommand.actor_id == actor.id, EtlDispatchCommand.idempotency_key == intent_key))
        if original is not None:
            if original.source != source or original.dry_run != body.dry_run:
                raise HTTPException(409, "Idempotency key intent conflicts")
            receipt = Accepted(replayed=True, command=Command.model_validate(original))
            db.commit()
            return receipt
        if not enabled():
            unavailable()
        if body.dispatch_generation is None:
            raise HTTPException(422, "Invalid operations parameters")
        now = db_clock(db)
        if not fresh(worker, now):
            unavailable()
        if worker.generation != body.dispatch_generation:
            raise HTTPException(409, "Dispatch generation is stale")
        if source not in SOURCE_DOMAINS:
            unavailable()
        command_id = uuid4()
        # The legacy helper intentionally commits separately. Acceptance cannot
        # use it: this audit and command share the same commit/rollback boundary.
        audit = AdminAuditLog(actor_id=actor.id, actor_email=actor.email, action="etl.trigger",
            target_type="etl_command", target_id=str(command_id),
            payload=safe_audit_payload("etl.trigger", {"dry_run": body.dry_run}))
        db.add(audit)
        db.flush()
        command = EtlDispatchCommand(id=command_id, actor_id=actor.id, idempotency_key=intent_key,
            source=source, domain=SOURCE_DOMAINS[source], dry_run=body.dry_run,
            generation=worker.generation, status="queued", version=1,
            created_at=now, updated_at=now, audit_id=audit.id)
        db.add(command)
        db.flush()
        receipt = Accepted(replayed=False, command=Command.model_validate(command))
        db.commit()
        return receipt
    except Exception:
        db.rollback()
        raise


def command_detail(db, command_id):
    try:
        identity = canonical_uuid(command_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "Invalid operations parameters") from None
    db_clock(db)
    retire_expired(db)
    db.commit()
    command = db.get(EtlDispatchCommand, identity)
    if command is None:
        raise HTTPException(404, "ETL command not found")
    return Command.model_validate(command)


def command_history(db, page, page_size, source=None, status=None):
    bounded_integer(page, 1, 10000)
    bounded_integer(page_size, 1, 50)
    if source is not None and source not in SOURCES or status is not None and status not in ("queued", "running", "completed", "failed", "interrupted"):
        raise HTTPException(422, "Invalid operations parameters")
    db_clock(db)
    retire_expired(db)
    db.commit()
    filters = []
    if source is not None:
        filters.append(EtlDispatchCommand.source == source)
    if status is not None:
        filters.append(EtlDispatchCommand.status == status)
    # Count and bounded page share one statement snapshot, even during accepts.
    totals = select(func.count().label("total")).select_from(EtlDispatchCommand).where(*filters).subquery()
    entries = select(EtlDispatchCommand).where(*filters).order_by(EtlDispatchCommand.created_at.desc(), EtlDispatchCommand.id.desc()).offset((page - 1) * page_size).limit(page_size).subquery()
    from sqlalchemy.orm import aliased
    entry = aliased(EtlDispatchCommand, entries)
    rows = db.execute(select(totals.c.total, entry).select_from(totals).outerjoin(entry, text("true")).order_by(entry.created_at.desc(), entry.id.desc())).all()
    count = rows[0][0]
    return CommandPage(entries=[Command.model_validate(row[1]) for row in rows if row[1] is not None],
        page=page, page_size=page_size, total=count, has_more=page * page_size < count)

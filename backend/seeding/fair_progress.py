"""Admission order for a bounded multi-domain run; never execution authority.

Dropped observations and application startup bookkeeping do not advance this
queue. Only a durable, actually entered live claim counts as an opportunity.
Failures still advance the opportunity so one failing source cannot starve
others. Source opt-ins retain their existing precedence over legacy work.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select, text

from models import IngestionJob, SeedingDomainClaim

PRIORITY_SOURCES = frozenset({'cra', 'opendata', 'county_borrowing'})


def admission_order(factory, domains):
    domains = list(domains)
    if (not 1 <= len(domains) <= 64 or len(set(domains)) != len(domains)
            or any(type(name) is not str or not 1 <= len(name) <= 100 for name in domains)):
        raise ValueError('Bounded distinct domain names required')
    with factory() as session:
        if session.get_bind().dialect.name == 'postgresql':
            session.execute(text('SET TRANSACTION READ ONLY'))
            session.execute(text("SET LOCAL statement_timeout='2s';SET LOCAL lock_timeout='500ms'"))
        rows = session.execute(select(SeedingDomainClaim.domain,
                func.max(SeedingDomainClaim.entered_at))
            .join(IngestionJob, IngestionJob.id == SeedingDomainClaim.job_id)
            .where(SeedingDomainClaim.domain.in_(domains),
                SeedingDomainClaim.entered_at.is_not(None),
                IngestionJob.dry_run.is_(False),
                IngestionJob.domain == SeedingDomainClaim.domain,
                IngestionJob.meta['bootstrap'].as_boolean().is_not(True))
            .group_by(SeedingDomainClaim.domain)).all()
    latest = {}
    for name, at in rows:
        if name not in domains or not isinstance(at, datetime) or name in latest:
            raise ValueError('Admission history is incomplete or malformed')
        latest[name] = at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc)
    never = datetime.min.replace(tzinfo=timezone.utc)
    priority = [name for name in domains if name in PRIORITY_SOURCES]
    legacy = [name for name in domains if name not in PRIORITY_SOURCES]
    return priority + sorted(legacy, key=lambda name: latest.get(name, never))

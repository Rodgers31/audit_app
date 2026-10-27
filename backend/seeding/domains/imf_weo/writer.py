"""Retain a complete country snapshot only when its observations change.

``vintage`` is the acquisition time of that changed snapshot, not a proven
IMF publication date. Unchanged checks live in the ingestion job. Existing
snapshots remain intact, including historical duplicate acquisitions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List

from sqlalchemy import func, insert, select, text, tuple_
from sqlalchemy.orm import Session

# Absolute import — sibling domains (audits, counties_budget, etc.) all
# import models this way because the seeder runs with `backend/` on
# PYTHONPATH. The nested relative path `....models` that I originally
# used errors out in the CI test collector: "ImportError: attempted
# relative import beyond top-level package".
from models import ImfWeoObservation
from ...types import DomainRunContext

logger = logging.getLogger("seeding.imf_weo.writer")
MAX_SNAPSHOT_ROWS = 512
IDENTITY = ('country_code', 'indicator', 'year')
CONTENT = ('value', 'is_projection', 'source')


def _number(value):
    if value is None:
        return None
    try:
        if isinstance(value, bool):
            raise ValueError('Boolean is not an IMF observation')
        number = Decimal(str(value)).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)
        if not number.is_finite() or abs(number) >= Decimal('1e16'):
            raise ValueError('IMF observation exceeds Numeric(20,4)')
        return number
    except (InvalidOperation, TypeError) as exc:
        raise ValueError('Invalid IMF numeric observation') from exc


def _records(records):
    if type(records) is not list or len(records) > MAX_SNAPSHOT_ROWS:
        raise ValueError('IMF snapshot must be a bounded list')
    rows, identities, observed_at = [], set(), None
    for record in records:
        if type(record) is not dict or set(record) != {*IDENTITY, *CONTENT, 'vintage'}:
            raise ValueError('Unexpected IMF observation shape')
        r = dict(record)
        for key, ceiling in (('country_code', 16), ('indicator', 32), ('source', 32)):
            if type(r[key]) is not str or not r[key].isascii() or not 1 <= len(r[key]) <= ceiling:
                raise ValueError('Invalid IMF observation identity')
        if (type(r['year']) is not int or not 1 <= r['year'] <= 9999
                or type(r['is_projection']) is not bool):
            raise ValueError('Invalid IMF period or projection flag')
        at = r['vintage']
        if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('IMF acquisition requires an aware timestamp')
        r['vintage'] = at.astimezone(timezone.utc)
        observed_at = observed_at or r['vintage']
        if r['vintage'] != observed_at:
            raise ValueError('One acquisition cannot combine different snapshot times')
        r['value'] = _number(r['value'])
        identity = tuple(r[k] for k in IDENTITY)
        if identity in identities:
            raise ValueError('Duplicate IMF observation identity')
        identities.add(identity)
        rows.append(r)
    return rows


@dataclass
class WriteStats:
    processed: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    snapshot_rows_inserted: int = 0
    retained_vintages: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


def persist_imf_weo(
    session: Session,
    records: List[Dict[str, Any]],
    context: DomainRunContext,
) -> WriteStats:
    """Compare latest complete cohorts; preserve changed cohorts atomically.

    Readers select a single country-wide vintage, so inserting only changed
    individual rows would hide unchanged companion indicators. Physical
    snapshot rows are reported separately from new/revised observation counts.
    Missing prior identities and changed stale/same-time captures refuse.

    **Transaction management is the CLI's job, not ours.** Do NOT call
    ``session.commit()`` or ``session.rollback()`` here — the outer
    ``seeding/cli.py`` wraps this handler in a single transaction that
    also writes the ``ingestion_jobs`` tracking row. If we commit early
    the CLI's tracking update writes to a new txn; if we rollback on
    error we take the IngestionJob row down with us, leaving the run
    invisible in the admin dashboard. Let exceptions propagate so the
    CLI can handle them consistently with every other domain.
    """
    records = _records(records)
    stats = WriteStats(processed=len(records))
    if not records:
        return stats

    if context.dry_run:
        stats.skipped = len(records)
        logger.info("[dry-run] would upsert %d IMF WEO rows", len(records))
        return stats

    dialect = session.get_bind().dialect.name
    if dialect not in ('postgresql', 'sqlite'):
        raise ValueError('Unsupported IMF snapshot database')
    with session.begin_nested():
        if dialect == 'postgresql':
            if session.scalar(text('SHOW transaction_isolation')) != 'read committed':
                raise ValueError('IMF snapshot comparison requires READ COMMITTED')
            # Readers remain admitted. Every competing table writer, including
            # legacy INSERTs, must settle before the latest snapshot is read.
            session.execute(text('LOCK TABLE imf_weo_observations IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        countries = sorted({r['country_code'] for r in records})
        latest = dict(session.execute(select(ImfWeoObservation.country_code,
            func.max(ImfWeoObservation.vintage)).where(
                ImfWeoObservation.country_code.in_(countries)
            ).group_by(ImfWeoObservation.country_code)).all())
        prior = []
        if latest:
            prior = session.execute(select(ImfWeoObservation).where(tuple_(
                ImfWeoObservation.country_code, ImfWeoObservation.vintage
            ).in_(list(latest.items()))).limit(MAX_SNAPSHOT_ROWS + 1)
                .execution_options(populate_existing=True)).scalars().all()
        if len(prior) > MAX_SNAPSHOT_ROWS:
            raise ValueError('Prior IMF snapshot exceeds comparison bound')
        before = {tuple(getattr(r, k) for k in IDENTITY): r for r in prior}
        incoming = {tuple(r[k] for k in IDENTITY): r for r in records}
        if not before.keys() <= incoming.keys():
            raise ValueError('Incomplete IMF snapshot would hide prior observations')
        changed_countries = set()
        for identity, record in incoming.items():
            old = before.get(identity)
            if old is None:
                stats.created += 1
                changed_countries.add(record['country_code'])
            elif tuple(record[k] for k in CONTENT) != tuple(getattr(old, k) for k in CONTENT):
                stats.updated += 1
                changed_countries.add(record['country_code'])
            else:
                stats.skipped += 1
        for country in changed_countries:
            old_at = latest.get(country)
            if old_at is not None:
                # SQLite's timestamp storage strips timezone; PostgreSQL does not.
                old_at = old_at.replace(tzinfo=timezone.utc) if old_at.tzinfo is None else old_at
                if records[0]['vintage'] <= old_at:
                    raise ValueError('Changed IMF snapshot requires a newer acquisition')
        snapshot = [r for r in records if r['country_code'] in changed_countries]
        if snapshot:
            result = session.execute(insert(ImfWeoObservation).values(snapshot).returning(ImfWeoObservation.id))
            inserted = result.scalars().all()
            if len(inserted) != len(snapshot):
                raise ValueError('IMF snapshot insertion was incomplete')
            stats.snapshot_rows_inserted = len(inserted)
        for country in countries:
            retained_at = records[0]['vintage'] if country in changed_countries else latest[country]
            if retained_at.tzinfo is None:
                retained_at = retained_at.replace(tzinfo=timezone.utc)
            stats.retained_vintages[country] = retained_at.astimezone(timezone.utc).isoformat()
    return stats


__all__ = ["persist_imf_weo", "WriteStats"]

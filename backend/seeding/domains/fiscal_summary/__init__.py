"""Fiscal summary seeding domain.

Seeds national fiscal data (budget, revenue, borrowing, debt service)
from National Treasury BPS, Controller of Budget, and CBK reports.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...http_client import create_http_client
from ...registries import register_domain
from ...types import DomainRunContext, DomainRunResult
from . import fetcher, parser, writer

logger = logging.getLogger("seeding.fiscal_summary")


@register_domain("fiscal_summary")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    errors: list[str] = []

    with create_http_client(settings) as client:
        try:
            payload = fetcher.fetch_fiscal_summary_payload(client, settings)
        except Exception as exc:
            logger.exception("Failed to fetch fiscal summary payload")
            return DomainRunResult(
                domain="fiscal_summary",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                items_processed=0,
                items_created=0,
                items_updated=0,
                errors=[f"Fetch failed: {exc}"],
            )

    try:
        records = parser.parse_fiscal_summary_payload(payload)
    except Exception as exc:
        logger.exception("Failed to parse fiscal summary payload")
        return DomainRunResult(
            domain="fiscal_summary",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            items_processed=0,
            items_created=0,
            items_updated=0,
            errors=[f"Parse failed: {exc}"],
        )

    # Validation gate: quarantine any fiscal-year row that fails plausibility
    # or reconciliation BEFORE it reaches the DB, so a bad live parse (wrong
    # table row / wrong units) can't overwrite a good last-known value. Clean
    # rows pass through unchanged; quarantined years keep their existing DB row
    # and are reported in `errors`. Degrades to "no gate" only if the guard
    # itself can't run — never blocks seeding outright. See trust_guards.
    try:
        from services.trust_guards import check_fiscal_summary

        clean_records = []
        quarantined = 0
        for rec in records:
            issues = check_fiscal_summary(rec)
            if issues:
                quarantined += 1
                errors.append(
                    f"Quarantined {getattr(rec, 'fiscal_year', '?')}: "
                    + "; ".join(issues)
                )
            else:
                clean_records.append(rec)
        if quarantined:
            logger.warning(
                "fiscal_summary: quarantined %d/%d implausible row(s); "
                "keeping last-known-good for those years",
                quarantined,
                len(records),
            )
        records = clean_records
    except Exception as exc:  # never let the gate break a seed run
        logger.warning("fiscal_summary validation gate skipped: %s", exc)

    try:
        created, updated = writer.write_fiscal_summary_records(
            session,
            records,
            payload.get("metadata", {}),
        )
    except Exception as exc:
        logger.exception("Failed to write fiscal summary records")
        return DomainRunResult(
            domain="fiscal_summary",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            items_processed=len(records),
            items_created=0,
            items_updated=0,
            errors=[f"Write failed: {exc}"],
        )

    finished_at = datetime.now(timezone.utc)
    logger.info(
        f"Fiscal summary seeding complete: {created} created, {updated} updated "
        f"in {(finished_at - started_at).total_seconds():.1f}s"
    )

    return DomainRunResult(
        domain="fiscal_summary",
        started_at=started_at,
        finished_at=finished_at,
        items_processed=len(records),
        items_created=created,
        items_updated=updated,
        errors=errors,
    )

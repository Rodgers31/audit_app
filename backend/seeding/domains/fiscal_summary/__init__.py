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
from ...refresh_completion import accepted_records, fiscal_components_complete
from ...types import DomainRunContext, DomainRunResult
from . import fetcher, parser, writer

logger = logging.getLogger("seeding.fiscal_summary")


def _incomplete(reason):
    from ...freshness import get, mark_partial
    if get('fiscal_summary').get('mode') == 'live':
        mark_partial('fiscal_summary', reason=reason)


@register_domain("fiscal_summary")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    errors: list[str] = []

    with create_http_client(settings) as client:
        try:
            payload = fetcher.fetch_fiscal_summary_payload(client, settings)
            if not isinstance(payload, dict) or not isinstance(payload.get('_run_facts', {}), dict):
                raise ValueError('Fiscal payload and run facts must be objects')
            run_facts = dict(payload.get('_run_facts') or {})
        except Exception as exc:
            logger.exception("Failed to fetch fiscal summary payload")
            _incomplete('fiscal_fetch_failed')
            return DomainRunResult(
                domain="fiscal_summary",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                items_processed=0,
                items_created=0,
                items_updated=0,
                errors=[f"Fetch failed: {exc}"],
            )

    # What the Budget Summary listing carried this run, readable or not. The
    # freshness gate reads it off the ingestion job, so it is attached to
    # every result below, failures included.

    try:
        records = parser.parse_fiscal_summary_payload(payload)
    except Exception as exc:
        logger.exception("Failed to parse fiscal summary payload")
        _incomplete('fiscal_parse_failed')
        return DomainRunResult(
            domain="fiscal_summary",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            items_processed=0,
            items_created=0,
            items_updated=0,
            errors=[f"Parse failed: {exc}"],
            metadata=run_facts,
        )

    # Validation gate: quarantine any fiscal-year row that fails plausibility
    # or reconciliation BEFORE it reaches the DB, so a bad live parse (wrong
    # table row / wrong units) can't overwrite a good last-known value. Clean
    # rows pass through unchanged; quarantined years keep their existing DB row
    # and are reported in `errors`. A broken guard cannot authorize persistence.
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
            _incomplete('fiscal_rows_quarantined')
            logger.warning(
                "fiscal_summary: quarantined %d/%d implausible row(s); "
                "keeping last-known-good for those years",
                quarantined,
                len(records),
            )
        records = clean_records
    except Exception as exc:
        logger.exception("fiscal_summary reconciliation unavailable")
        _incomplete('fiscal_reconciliation_unavailable')
        # Raising lets the native CLI roll back the entire domain transaction
        # and retain a FAILED observation, including dedicated dispatch runs.
        raise RuntimeError("Fiscal reconciliation unavailable") from exc

    try:
        if not records:
            _incomplete('no_fiscal_records_accepted')
            errors.append('No fiscal records accepted; published rows preserved')
        created, updated = writer.write_fiscal_summary_records(
            session,
            records,
            payload.get("metadata", {}),
        )
    except Exception as exc:
        logger.exception("Failed to write fiscal summary records")
        _incomplete('fiscal_write_failed')
        return DomainRunResult(
            domain="fiscal_summary",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            items_processed=len(records),
            items_created=0,
            items_updated=0,
            errors=[f"Write failed: {exc}"],
            metadata=run_facts,
        )

    finished_at = datetime.now(timezone.utc)
    from ...freshness import get
    accepted = accepted_records(len(records), created, updated)
    if records and not accepted:
        _incomplete('fiscal_writer_inventory_unconfirmed')
        errors.append('Writer did not confirm every accepted fiscal record')
        created, updated = 0, 0
    accepted_years = [getattr(record, 'fiscal_year', None) for record in records]
    components_complete = fiscal_components_complete(run_facts.get('refresh_components'), accepted_years)
    if not components_complete:
        _incomplete('fiscal_components_unconfirmed')
    run_facts['refresh_completion'] = {
        'complete': bool(records and not errors and components_complete
                         and get('fiscal_summary').get('mode') == 'live'
                         and not context.dry_run),
        'accepted_records': accepted,
        'accepted_years': accepted_years,
    }
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
        metadata=run_facts,
    )

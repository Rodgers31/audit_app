"""Explicit default-off producer under the existing native ingestion owner."""
from datetime import datetime, timezone

from seeding.registries import register_domain
from seeding.types import DomainRunResult
from seeding.freshness import mark_live, mark_refused
from seeding import county_borrowing_contract as source, county_borrowing_contract as parser
from . import writer


@register_domain('county_borrowing')
def run(session, settings, context):
    started = datetime.now(timezone.utc)
    receipts = []
    try:
        writer.require_enabled(settings)
        writer.require_ownership(session, context, lock=False)
        # All reviewed editions share the CLI's transaction and deadline. A
        # transport/parse/refusal aborts the domain, never an empty success.
        if type(source.EDITIONS) is not dict or not 1 <= len(source.EDITIONS) <= 8:
            raise source.CountyBorrowingRefused('County borrowing source edition inventory is empty or exceeds its bound')
        if (any(type(s.get('size_bytes')) is not int or s['size_bytes'] <= 0 for s in source.EDITIONS.values())
                or sum(s['size_bytes'] for s in source.EDITIONS.values()) > 64 * 1024 * 1024):
            raise source.CountyBorrowingRefused('County borrowing source inventory exceeds its aggregate byte bound')
        acquired = []
        for key in source.EDITIONS:
            payload, fetched_at = source.fetch_publication(key)
            parsed = parser.parse_publication(key, payload)
            acquired.append((key, payload, parsed, fetched_at))
        with session.begin_nested():
            for key, payload, parsed, fetched_at in acquired:
                stats = writer.persist(session, settings, context, key, payload, parsed, fetched_at)
                receipts.append({'edition': key, 'artifact_sha256': parsed['artifact_sha256'],
                    'scope': parsed['scope'], 'status': parsed['status'], **stats})
    except Exception as exc:
        detail = str(exc) if isinstance(exc, source.CountyBorrowingRefused) else type(exc).__name__
        mark_refused('county_borrowing', reason='reviewed_county_borrowing_source_refused', detail=detail)
        raise
    mark_live('county_borrowing', detail='Reviewed source coverage retained; selected instruments only, never complete county liabilities')
    return DomainRunResult(domain='county_borrowing', started_at=started, finished_at=datetime.now(timezone.utc),
        dry_run=context.dry_run, items_processed=len(receipts), items_created=sum(r['created'] for r in receipts),
        metadata={'source_coverage': receipts, 'complete_liability_coverage': False,
                  'instrument_observations': sum(r['instruments'] for r in receipts),
                  'evidence': 'source_coverage_only' if not any(r['instruments'] for r in receipts) else 'selected_instrument_stock'})

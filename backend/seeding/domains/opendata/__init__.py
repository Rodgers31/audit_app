"""Opt-in KNBS workbook ingestion through native OpenData ownership."""
from datetime import datetime, timezone

from ...freshness import mark_live, mark_refused
from ...registries import register_domain
from ...types import DomainRunResult
from . import parser, source, writer


def previous_pages(session, current_job):
    """Only terminal native receipts can supply conditional listing validators."""
    from sqlalchemy import select
    from models import IngestionJob, IngestionStatus
    from .discovery import RECEIPT_VERSION, prior_pages
    metadata = session.scalars(select(IngestionJob.meta).where(
        IngestionJob.domain == 'opendata', IngestionJob.id != current_job,
        IngestionJob.status.in_([IngestionStatus.COMPLETED, IngestionStatus.COMPLETED_WITH_ERRORS]))
        .order_by(IngestionJob.id.desc()).limit(8)).all()
    for meta in metadata:
        if type(meta) is dict and 'release_discovery' in meta:
            receipt = meta['release_discovery']
            if type(receipt) is not dict or receipt.get('version') != RECEIPT_VERSION:
                raise source.OpenDataSourceRefused('KNBS prior native receipt version refused')
            return prior_pages(receipt.get('pages'))
    return None


def last_recorded_edition(session):
    """Read-side history only; this is not fresh source/financial verification."""
    from sqlalchemy import select
    from models import SourceDocument, Extraction
    rows = session.execute(select(SourceDocument.id, Extraction.id,
        Extraction.extracted_json['artifact_sha256'].astext)
        .join(Extraction, Extraction.source_document_id == SourceDocument.id)
        .where(SourceDocument.url == source.URL, Extraction.extractor == parser.EXTRACTOR)
        .order_by(Extraction.id.desc()).limit(2)).all()
    if len(rows) > 1:
        raise source.OpenDataSourceRefused('KNBS recorded accepted edition identity is ambiguous')
    if not rows:
        return None
    document_id, extraction_id, digest = rows[0]
    if type(digest) is not str or digest != source.SHA256:
        raise source.OpenDataSourceRefused('KNBS recorded extraction identity differs')
    return {'source_document_id': document_id, 'extraction_id': extraction_id,
            'artifact_sha256': source.SHA256, 'report_url': source.REPORT_URL,
            'evidence': 'recorded_source_extraction_only_not_fresh_verification'}


@register_domain("opendata")
def run(session, settings, context):
    started = datetime.now(timezone.utc)
    try:
        if settings.opendata_ingestion_enabled is not True:
            raise source.OpenDataSourceRefused("OpenData ingestion is disabled; explicit reviewed-source opt-in required")
        writer.require_ownership(session, context, lock=False)
        discovery_receipt = None
        if settings.knbs_release_discovery_enabled is True:
            from .discovery import discover
            discovery_receipt, payload, fetched_at = discover(settings, previous_pages(session, context.job_id))
            # Re-prove ownership after transport even when there are no fact writes.
            writer.require_ownership(session, context)
            if payload is None:
                discovery_receipt['last_recorded_edition'] = last_recorded_edition(session)
                mark_refused('opendata', reason='release_quarantined', detail=discovery_receipt['reason'])
                return DomainRunResult(domain='opendata', started_at=started,
                    finished_at=datetime.now(timezone.utc), dry_run=context.dry_run,
                    errors=['KNBS review candidate quarantined: ' + discovery_receipt['reason']],
                    metadata={'release_discovery': discovery_receipt, 'extraction_status': 'not_accepted',
                              'verification_status': 'source_candidate_not_publication_qualified'})
        else:
            payload, fetched_at = source.fetch_publication()
        parsed = parser.parse_publication(payload)
        stats = writer.persist(session, context, payload, parsed, fetched_at)
        if discovery_receipt is not None:
            # Include newly inserted extraction history in the terminal receipt.
            discovery_receipt['last_recorded_edition'] = last_recorded_edition(session)
    except Exception as exc:
        # OpenDataSourceRefused messages are fixed, bounded diagnostics; other errors
        # are named by type only.
        detail = str(exc) if isinstance(exc, source.OpenDataSourceRefused) else type(exc).__name__
        mark_refused("opendata", reason="supported_workbook_unavailable_or_invalid", detail=detail)
        raise
    mark_live("opendata", detail="KNBS 2026 Table 5.13 workbook cells extracted with source discrepancies and labels retained; publication unqualified")
    result = DomainRunResult(domain="opendata", started_at=started, finished_at=datetime.now(timezone.utc),
        dry_run=context.dry_run, items_processed=parsed["numeric_cells"], items_created=stats["created"],
        metadata={"source_url": source.URL, "artifact_sha256": parsed["artifact_sha256"],
                  "publication_stage": "mixed_as_published", "sheet": parsed["sheet"],
                  "missing_cells": parsed["missing_cells"], "table": "5.13",
                  "verification_status": parsed["verification_status"], "unchanged": stats["unchanged"]})
    if discovery_receipt is not None:
        result.metadata['release_discovery'] = discovery_receipt
        result.metadata['extraction_status'] = 'accepted_pinned_replay' if stats['unchanged'] else 'pinned_preview' if context.dry_run else 'accepted_pinned_extraction'
    return result

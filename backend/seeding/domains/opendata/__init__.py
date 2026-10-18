"""Opt-in KNBS workbook ingestion through native OpenData ownership."""
from datetime import datetime, timezone

from ...freshness import mark_live, mark_refused
from ...registries import register_domain
from ...types import DomainRunResult
from . import parser, source, writer


@register_domain("opendata")
def run(session, settings, context):
    started = datetime.now(timezone.utc)
    try:
        if settings.opendata_ingestion_enabled is not True:
            raise source.OpenDataSourceRefused("OpenData ingestion is disabled; explicit reviewed-source opt-in required")
        writer.require_ownership(session, context, lock=False)
        payload, fetched_at = source.fetch_publication()
        parsed = parser.parse_publication(payload)
        stats = writer.persist(session, context, payload, parsed, fetched_at)
    except Exception as exc:
        # OpenDataSourceRefused messages are fixed, bounded diagnostics; other errors
        # are named by type only.
        detail = str(exc) if isinstance(exc, source.OpenDataSourceRefused) else type(exc).__name__
        mark_refused("opendata", reason="supported_workbook_unavailable_or_invalid", detail=detail)
        raise
    mark_live("opendata", detail="KNBS 2026 Table 5.13 workbook cells extracted with source discrepancies and labels retained; publication unqualified")
    return DomainRunResult(domain="opendata", started_at=started, finished_at=datetime.now(timezone.utc),
        dry_run=context.dry_run, items_processed=parsed["numeric_cells"], items_created=stats["created"],
        metadata={"source_url": source.URL, "artifact_sha256": parsed["artifact_sha256"],
                  "publication_stage": "mixed_as_published", "sheet": parsed["sheet"],
                  "missing_cells": parsed["missing_cells"], "table": "5.13",
                  "verification_status": parsed["verification_status"], "unchanged": stats["unchanged"]})

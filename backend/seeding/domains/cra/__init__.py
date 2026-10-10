"""Opt-in, bounded CRA recommendation ingestion, through native ownership."""
from datetime import datetime, timezone

from ...freshness import mark_live, mark_refused
from ...registries import register_domain
from ...types import DomainRunResult
from . import parser, source, writer


@register_domain("cra")
def run(session, settings, context):
    started = datetime.now(timezone.utc)
    try:
        if settings.cra_ingestion_enabled is not True:
            raise source.CraSourceRefused("CRA ingestion is disabled; explicit reviewed-source opt-in required")
        writer.require_ownership(session, context, lock=False)
        payload, fetched_at = source.fetch_publication()
        parsed = parser.parse_publication(payload)
        stats = writer.persist(session, context, payload, parsed, fetched_at)
    except Exception as exc:
        # CraSourceRefused messages are fixed, bounded diagnostics; other errors
        # are named by type only.
        detail = str(exc) if isinstance(exc, source.CraSourceRefused) else type(exc).__name__
        mark_refused("cra", reason="supported_recommendation_unavailable_or_invalid", detail=detail)
        raise
    mark_live("cra", detail="CRA FY2026/27 Table 5.2 recommendations validated from official PDF bytes")
    return DomainRunResult(domain="cra", started_at=started, finished_at=datetime.now(timezone.utc),
        dry_run=context.dry_run, items_processed=len(parsed["amounts_kes"]), items_created=stats["created"],
        metadata={"source_url": source.URL, "artifact_sha256": parsed["artifact_sha256"],
                  "fiscal_year": "FY2026/27", "publication_stage": "recommendation",
                  "table": "5.2", "unchanged": stats["unchanged"]})

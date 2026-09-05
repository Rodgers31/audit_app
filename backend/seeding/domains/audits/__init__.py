"""Audit findings seeding domain — registry-driven Layers 2→3→4.

The old path here discovered OAG PDFs, regex-scraped "findings" out of
concatenated page text in one pass, and persisted them with no page
numbers, no extractions rows and no md5 — which is how a report's cover
page (89.6% unmapped glyphs) became audit row 902. That path is gone.

The current flow, per dataset in the Layer-1 source registry:

1. **Fetch (L2)** — ``fetch_documents.fetch_document`` downloads the PDF,
   records md5/content_type/http_status/file_path/last_verified_at, and
   only then marks the document AVAILABLE.
2. **Extract (L3)** — the dataset's registered parser writes one
   ``extractions`` row per finding with its page number. No parser
   registered → the dataset is fetched and registered, never guessed at.
3. **Load (L4)** — ``loader.load_blue_book_extractions`` turns extractions
   into ``audits`` rows carrying ``extraction_id``/``page_ref``/
   ``source_hash``/``confidence_score``/``basis``, then lets
   ``services/publication_gate.py`` write the ``publishable`` verdict.

Discovery finds *new* documents via the OAG WordPress media API (the
same mechanism the old fetcher proved out); documents already registered
in ``source_documents`` are re-fetched from their recorded URLs. Nothing
here invents a URL.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...http_client import create_http_client
from ...registries import register_domain
from ...source_registry import SOURCE_REGISTRY, SourceDataset
from ...types import DomainRunContext, DomainRunResult
from . import fetcher  # retained for its FY-derivation helpers + tests

logger = logging.getLogger("seeding.audits")

# New documents fetched per dataset per run — bounds nightly wall-clock.
_MAX_NEW_DOCUMENTS_PER_RUN = 3


def _known_document_urls(session: Session, dataset: SourceDataset) -> List[str]:
    """URLs already registered in source_documents for this dataset."""
    from models import SourceDocument

    rows = session.execute(
        select(SourceDocument.url).where(
            SourceDocument.url.isnot(None),
            SourceDocument.url.ilike("%.pdf"),
            SourceDocument.publisher.ilike("%auditor%general%"),
        )
    ).all()
    urls = []
    for (url,) in rows:
        low = (url or "").lower()
        if all(kw in low for kw in dataset.match_keywords):
            urls.append(url)
    return urls


def _discovered_urls(client, dataset: SourceDataset) -> List[str]:
    """New candidate PDFs from the OAG WP media API, keyword-filtered."""
    try:
        discovered = fetcher._discover_audit_pdfs_via_wp_api(client)
    except Exception as exc:  # discovery is best-effort; failure is loud
        logger.warning("OAG discovery failed: %s", exc)
        return []
    return [
        u
        for u in discovered
        if all(kw in u.lower() for kw in dataset.match_keywords)
    ]


@register_domain("audits")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    errors: List[str] = []
    created = updated = processed = skipped = 0
    metadata: dict = {"documents": []}

    from models import Country

    country = session.execute(
        select(Country).where(Country.iso_code == "KEN")
    ).scalar_one_or_none()
    if country is None:
        return (
            DomainRunResult.empty(
                domain="audits", dry_run=context.dry_run, started_at=started_at
            )
            .with_error("Kenya country row missing — run bootstrap first")
            .mark_finished()
        )

    from models import DocumentType

    from ...extractors import get_parser
    from ...extractors.oag_county_audit import (
        CountyAuditError as QuarantinedDocument,
    )
    from ...fetch_documents import fetch_document
    from .loader import load_blue_book_extractions

    with create_http_client(settings) as client:
        for dataset_id in ("oag_national_audits", "oag_county_audits"):
            dataset = SOURCE_REGISTRY[dataset_id]
            parser = get_parser(dataset.parser_id)

            known = _known_document_urls(session, dataset)
            fresh = [
                u
                for u in _discovered_urls(client, dataset)
                if u not in set(known)
            ][:_MAX_NEW_DOCUMENTS_PER_RUN]
            candidates = known + fresh
            logger.info(
                "%s: %d known + %d newly discovered document(s)%s",
                dataset_id,
                len(known),
                len(fresh),
                "" if parser else " (no parser — fetch/register only)",
            )

            if context.dry_run:
                metadata["documents"].append(
                    {"dataset": dataset_id, "candidates": candidates}
                )
                continue

            for url in candidates:
                try:
                    doc = fetch_document(
                        session,
                        client,
                        settings,
                        url=url,
                        country_id=country.id,
                        publisher=dataset.publisher,
                        title=url.rsplit("/", 1)[-1],
                        doc_type=DocumentType[dataset.doc_type],
                        dataset_id=dataset_id,
                    )
                except Exception as exc:
                    errors.append(f"fetch failed for {url}: {exc}")
                    continue

                doc_stat = {"dataset": dataset_id, "doc_id": doc.id, "url": url}
                if parser is not None:
                    try:
                        ext_stats = parser(session, doc, settings)
                        doc_stat["extractions"] = ext_stats
                    except QuarantinedDocument as exc:
                        # A document the parser deliberately refused — a
                        # thematic or performance audit with no auditee, say.
                        # That is a SKIP with a reason, not an extraction
                        # failure: counting it as one marks a healthy run
                        # unhealthy and buries the real errors beside it.
                        doc_stat["skipped"] = getattr(exc, "reason", str(exc))
                        logger.info(
                            "Skipping doc %s — parser refused it (%s)",
                            doc.id,
                            doc_stat["skipped"],
                        )
                        metadata["documents"].append(doc_stat)
                        continue
                    except Exception as exc:
                        errors.append(f"extract failed for doc {doc.id}: {exc}")
                        logger.exception("Extraction failed for doc %s", doc.id)
                        metadata["documents"].append(doc_stat)
                        continue
                    load_stats = load_blue_book_extractions(
                        session, doc, settings, context
                    )
                    processed += load_stats.processed
                    created += load_stats.created
                    updated += load_stats.updated
                    skipped += load_stats.skipped
                    errors.extend(load_stats.errors)
                    doc_stat["loaded"] = {
                        "created": load_stats.created,
                        "updated": load_stats.updated,
                        "skipped": load_stats.skipped,
                    }
                metadata["documents"].append(doc_stat)

    # Provenance: the audits domain is "live" only if at least one document
    # was actually fetched AND extracted this run. Registering a document
    # without extracting it is not live data.
    from ...freshness import mark_fixture, mark_live

    extracted_docs = [
        d for d in metadata["documents"] if d.get("extractions")
    ]
    if extracted_docs:
        mark_live(
            "audits",
            detail=(
                f"{len(extracted_docs)} document(s) extracted; "
                f"{created} finding(s) created, {updated} updated"
            ),
        )
    else:
        mark_fixture(
            "audits",
            reason="no_document_extracted",
            detail=(
                f"{len(metadata['documents'])} document(s) seen, none "
                f"produced extractions"
            ),
        )

    return DomainRunResult(
        domain="audits",
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        items_processed=processed,
        items_created=created,
        items_updated=updated,
        dry_run=context.dry_run,
        errors=errors,
        metadata=metadata,
    )


__all__ = ["run"]

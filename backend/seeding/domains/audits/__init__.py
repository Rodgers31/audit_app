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

Discovery, per dataset:

* **County** (``oag_county_audits``): ``seeding/oag_discovery.py`` reads
  OAG's county listing, then each year page, then the dlp_document sitemap.
  Every discovered document from FY2021/22 on is registered in
  ``source_documents`` with its URL and discovery facts before anything is
  downloaded. The combined volumes (executives, assemblies) are then
  processed newest fiscal year first, inside a start budget, with a commit
  after each so the next run resumes where this one stopped.
* **National** (``oag_national_audits``): the OAG WordPress media API, as
  before. Documents already registered are re-fetched from their recorded
  URLs.

Nothing here invents a URL.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

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


def _extracted_something(ext_stats: dict) -> bool:
    """Did the parser write or change rows, rather than skip a current document?

    Fails towards committing: stats that do not say "skipped" are treated as
    work, because an unneeded commit costs a round trip and a missed one costs
    the night's re-extraction.
    """
    if not ext_stats:
        return False
    if ext_stats.get("skipped_unchanged") or ext_stats.get("reason") in (
        "already_extracted",
        "already_extracted_by_delegate",
    ):
        return False
    return True


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


def _registered_volumes(session: Session) -> Dict[str, dict]:
    """``{url: discovery facts}`` for combined county volumes registered by
    an earlier run.

    Lets a night on which OAG's listing is unreachable still resume the
    backlog it already knows about, instead of processing nothing.
    """
    from models import SourceDocument

    from ...oag_discovery import VOLUME_KINDS

    out: Dict[str, dict] = {}
    rows = session.execute(
        select(SourceDocument.url, SourceDocument.meta).where(
            SourceDocument.url.isnot(None),
            SourceDocument.publisher.ilike("%auditor%general%"),
        )
    ).all()
    for url, meta in rows:
        facts = (meta or {}).get("oag_discovery") or {}
        if facts.get("kind") in VOLUME_KINDS and facts.get("fiscal_year"):
            out[url] = facts
    return out


def register_discovered_documents(
    session: Session, *, country_id: int, dataset: SourceDataset, discovery
) -> Dict[str, int]:
    """Record every discovered county document in ``source_documents``.

    Registered BEFORE anything is downloaded, so each is citable by URL
    whether or not it is ever extracted. A new row is ``FAILED`` with no
    ``http_status`` until bytes land, the convention ``fetch_document`` already
    uses ("AVAILABLE is earned"). ``metadata.registration`` says it was
    discovered and not fetched, so the two are never confused with a real
    fetch failure. The per-county FY2021/22 reports are registered but not
    extracted. That year's combined volumes carry the same text, and
    extracting both would publish every finding twice.
    """
    from models import DocumentStatus, DocumentType, SourceDocument

    by_url = {
        d.url: d
        for d in session.execute(
            select(SourceDocument).where(
                SourceDocument.url.in_([doc.url for doc in discovery.documents])
            )
        ).scalars()
    } if discovery.documents else {}

    counts = {"registered_new": 0, "updated": 0, "unchanged": 0}
    now = datetime.now(timezone.utc)
    for found in discovery.documents:
        facts = found.as_meta()
        row = by_url.get(found.url)
        if row is None:
            session.add(
                SourceDocument(
                    country_id=country_id,
                    publisher=dataset.publisher,
                    title=found.filename,
                    url=found.url,
                    fetch_date=now,
                    doc_type=DocumentType[dataset.doc_type],
                    status=DocumentStatus.FAILED,
                    last_seen_at=now,
                    meta={
                        "dataset_id": dataset.dataset_id,
                        "oag_discovery": facts,
                        "registration": "discovered_not_fetched",
                    },
                )
            )
            counts["registered_new"] += 1
            continue
        meta = dict(row.meta or {})
        row.last_seen_at = now
        if meta.get("oag_discovery") != facts:
            meta["oag_discovery"] = facts
            meta.setdefault("dataset_id", dataset.dataset_id)
            row.meta = meta
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
    session.flush()
    return counts


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

    from models import DocumentType, SourceDocument

    from ...extractors import get_parser
    from ...extractors import oag_county_volume
    from ...oag_discovery import (
        FIRST_INGESTED_FISCAL_YEAR,
        KIND_SINGLE_ENTITY,
        classify_document,
        discover_county_audit_documents,
        fiscal_year_in_name,
        fy_start,
    )
    from .candidates import (
        split_county_audit_candidates,
        split_national_audit_candidates,
    )
    from ...extractors.oag_county_audit import (
        CountyAuditError as QuarantinedDocument,
    )
    from ...fetch_documents import fetch_document
    from .loader import load_blue_book_extractions

    domain_start = time.monotonic()
    volume_urls: Dict[str, dict] = {}
    volume_report: Optional[dict] = None

    with create_http_client(settings) as client:
        for dataset_id in ("oag_national_audits", "oag_county_audits"):
            dataset = SOURCE_REGISTRY[dataset_id]
            parser = get_parser(dataset.parser_id)

            known = _known_document_urls(session, dataset)
            if dataset_id == "oag_county_audits":
                discovery = discover_county_audit_documents(client)
                metadata["oag_county_discovery"] = discovery.as_meta()
                # An unreadable listing is not "OAG published nothing". Name it,
                # so the run reads COMPLETED_WITH_ERRORS rather than clean.
                errors.extend(
                    f"OAG county discovery: {e}" for e in discovery.errors
                )
                if not context.dry_run:
                    metadata["oag_county_registration"] = (
                        register_discovered_documents(
                            session,
                            country_id=country.id,
                            dataset=dataset,
                            discovery=discovery,
                        )
                    )
                volume_urls = _registered_volumes(session) if not context.dry_run else {}
                for vol in discovery.volumes():
                    volume_urls[vol.url] = vol.as_meta()
                ordered_volumes = sorted(
                    volume_urls,
                    key=lambda u: (
                        -fy_start(volume_urls[u]["fiscal_year"]),
                        0 if volume_urls[u]["kind"] == "executives" else 1,
                        u,
                    ),
                )
                # Documents registered before discovery existed (the FY2020/21
                # volumes the Blue Book walk owns) keep being offered. Anything
                # discovery has classified is decided by discovery. The
                # per-county reports are registered above and not re-fetched.
                discovered = {d.url for d in discovery.documents}
                legacy = []
                for u in known:
                    if u in discovered or u in volume_urls:
                        continue
                    name = u.rsplit("/", 1)[-1]
                    fy = fiscal_year_in_name(name)
                    if (
                        classify_document(u)[0] == KIND_SINGLE_ENTITY
                        and fy
                        and fy_start(fy) >= fy_start(FIRST_INGESTED_FISCAL_YEAR)
                    ):
                        # A per-county report for a year the combined volumes
                        # cover (document 2391: OAG re-uploaded it as "-1.pdf",
                        # so discovery no longer names this URL). The volume
                        # carries the same findings. Loading both would
                        # double-count them.
                        logger.info(
                            "Covered by the %s combined volumes, not re-fetched: %s",
                            fy,
                            name[:80],
                        )
                        continue
                    legacy.append(u)
                fresh: List[str] = []
                # Earlier documents first. They are cheap and steady-state
                # (the FY2020/21 volumes skip on md5), and nothing may run
                # AFTER the budgeted volume loop, or the start budget would
                # not bound the domain.
                candidates, rejected = split_county_audit_candidates(
                    legacy + ordered_volumes
                )
                for url, why in rejected:
                    logger.info(
                        "Not a county audit, skipped before download (%s): %s",
                        why,
                        url.rsplit("/", 1)[-1][:80],
                    )
                logger.info(
                    "%s: %d combined volume(s) (%s) + %d earlier document(s)",
                    dataset_id,
                    len(ordered_volumes),
                    ", ".join(
                        sorted({volume_urls[u]["fiscal_year"] for u in ordered_volumes})
                    )
                    or "none",
                    len(legacy),
                )
                volume_report = {
                    "discovered": len(ordered_volumes),
                    "start_budget_seconds": settings.audits_county_start_budget_seconds,
                    "processed": [],
                    "already_current": [],
                    "deferred": [],
                    "failed": [],
                }
            else:
                fresh = [
                    u
                    for u in _discovered_urls(client, dataset)
                    if u not in set(known)
                ][:_MAX_NEW_DOCUMENTS_PER_RUN]
                candidates, rejected = split_national_audit_candidates(known + fresh)
                for url, why in rejected:
                    logger.info(
                        "Not the Blue Book, skipped before download (%s): %s",
                        why,
                        url.rsplit("/", 1)[-1][:80],
                    )
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
                is_volume = url in volume_urls
                if is_volume:
                    label = f"{volume_urls[url]['fiscal_year']} {volume_urls[url]['kind']}"
                    registered = session.execute(
                        select(SourceDocument).where(SourceDocument.url == url)
                    ).scalar_one_or_none()
                    current = bool(
                        registered is not None
                        and oag_county_volume.already_extracted(session, registered)
                    )
                    elapsed = time.monotonic() - domain_start
                    if (
                        not current
                        and elapsed >= settings.audits_county_start_budget_seconds
                    ):
                        # Not an error: the backlog is taken over several
                        # nights, newest year first. Recorded so a run that
                        # processed k of N says so.
                        volume_report["deferred"].append(label)
                        continue
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
                        max_seconds=(
                            settings.audits_volume_download_timeout_seconds
                            if is_volume
                            else None
                        ),
                    )
                except Exception as exc:
                    errors.append(f"fetch failed for {url}: {exc}")
                    if is_volume:
                        volume_report["failed"].append(f"{label}: fetch: {str(exc)[:160]}")
                        # The FAILED status and fetch_error are worth keeping.
                        session.commit()
                    continue

                doc_stat = {"dataset": dataset_id, "doc_id": doc.id, "url": url}
                if parser is not None:
                    try:
                        from ...extractors.reconciliation import extract_and_load

                        ext_stats, load_stats = extract_and_load(
                            session, doc, settings, context, parser, load_blue_book_extractions
                        )
                        doc_stat["extractions"] = ext_stats
                        if ext_stats.get("partial"):
                            errors.append(f"document {doc.id}: partial extraction; coverage incomplete")
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
                        if is_volume:
                            # A combined volume the extractor cannot place is
                            # 47 counties' findings missing. That is an error,
                            # not a skip.
                            errors.append(
                                f"county volume {label} refused: {exc}"
                            )
                            volume_report["failed"].append(f"{label}: {exc}")
                        continue
                    except Exception as exc:
                        from ...extractors.reconciliation import record_failed_attempt

                        doc_stat["extraction_attempt"] = record_failed_attempt(doc, exc)
                        errors.append(f"extract failed for doc {doc.id}: {exc}")
                        logger.exception("Extraction failed for doc %s", doc.id)
                        metadata["documents"].append(doc_stat)
                        if is_volume:
                            volume_report["failed"].append(
                                f"{label}: {type(exc).__name__}: {str(exc)[:160]}"
                            )
                        continue
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
                ext = doc_stat.get("extractions") or {}
                if not is_volume and _extracted_something(ext):
                    # Bank it, as each volume is banked below. A change to the
                    # Blue Book walk re-reads the national book and the two
                    # FY2020/21 volumes once, before the county start budget
                    # applies. Rolled back by a timeout, that re-read would
                    # be repeated every night.
                    session.commit()
                if is_volume:
                    if ext.get("reason") == "already_extracted":
                        volume_report["already_current"].append(label)
                    else:
                        volume_report["processed"].append(
                            f"{label}: {ext.get('created', 0)} finding(s)"
                        )
                        # Bank this volume. The CLI commits once, at the end,
                        # and rolls the whole domain back on a timeout, so
                        # without this a run that ran out of time mid-backlog
                        # would keep nothing and the next would start over.
                        session.commit()

    # Provenance: the audits domain is "live" only if at least one document
    # was actually fetched AND extracted this run. Registering a document
    # without extracting it is not live data.
    from ...freshness import mark_fixture, mark_live

    if volume_report is not None:
        metadata["county_volumes"] = volume_report
        logger.info(
            "oag_county_audits volumes: %d discovered; %d processed this run, "
            "%d already current, %d deferred to the next run (start budget "
            "%ss), %d failed",
            volume_report["discovered"],
            len(volume_report["processed"]),
            len(volume_report["already_current"]),
            len(volume_report["deferred"]),
            volume_report["start_budget_seconds"],
            len(volume_report["failed"]),
        )
        if volume_report["deferred"]:
            logger.warning(
                "County volumes deferred to the next run: %s",
                "; ".join(volume_report["deferred"]),
            )

    extracted_docs = [
        d for d in metadata["documents"] if d.get("extractions")
    ]
    if extracted_docs:
        volumes_note = ""
        if volume_report is not None:
            volumes_note = (
                f"; county volumes {len(volume_report['processed'])} processed, "
                f"{len(volume_report['already_current'])} current, "
                f"{len(volume_report['deferred'])} deferred of "
                f"{volume_report['discovered']}"
            )
        mark_live(
            "audits",
            detail=(
                f"{len(extracted_docs)} document(s) extracted; "
                f"{created} finding(s) created, {updated} updated{volumes_note}"
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

"""Layer 2 — fetch a registered document and prove the bytes landed.

The audit found 48 source documents with ``status='AVAILABLE'`` and no URL
at all: availability that was never checked. This module is the only place
that may set a document AVAILABLE, and it does so only after the body has
been downloaded, validated as a PDF, and hashed.

Everything it learns is recorded on the ``source_documents`` row:
``url, file_path, md5, content_type, http_status, fetch_date,
last_verified_at``. A failed fetch records ``http_status`` and sets
``status='FAILED'`` — loudly, never silently (no-silent-fallbacks).
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from models import DocumentStatus, DocumentType, SourceDocument
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import SeedingSettings
from .http_client import PdfDownloadError, SeedingHttpClient
from .pdf_download import get_or_download_pdf

logger = logging.getLogger("seeding.fetch_documents")


def _md5_of_file(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_document(
    session: Session,
    client: SeedingHttpClient,
    settings: SeedingSettings,
    *,
    url: str,
    country_id: int,
    publisher: str,
    title: str,
    doc_type: DocumentType,
    dataset_id: Optional[str] = None,
) -> SourceDocument:
    """Download ``url`` and return its up-to-date ``SourceDocument`` row.

    Find-or-create keyed on URL. On success the row carries the file path,
    md5 and HTTP bookkeeping and is AVAILABLE. On failure the row is FAILED
    with the reason in ``metadata['fetch_error']`` — and the exception is
    re-raised so the caller cannot mistake failure for success.

    If the publisher re-issued the document (md5 moved), the previous md5 is
    preserved in ``metadata['previous_md5']`` — every figure derived from
    the old bytes is unverified until re-extracted.
    """
    doc = session.execute(
        select(SourceDocument).where(SourceDocument.url == url)
    ).scalar_one_or_none()
    if doc is None:
        doc = SourceDocument(
            country_id=country_id,
            publisher=publisher,
            title=title,
            url=url,
            fetch_date=datetime.now(timezone.utc),
            doc_type=doc_type,
            # PENDING does not exist in DocumentStatus; FAILED until bytes
            # land is the honest default — AVAILABLE is earned below.
            status=DocumentStatus.FAILED,
            meta={"dataset_id": dataset_id} if dataset_id else {},
        )
        session.add(doc)
        session.flush()

    # Same directory the nightly workflow persists via actions/cache
    # ("backend/data/seeding/cache/pdfs") — a fetched report survives
    # across runs and is not re-downloaded nightly.
    cache_dir = settings.cache_path.expanduser() / "pdfs"
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        pdf_path = get_or_download_pdf(
            client,
            url,
            cache_dir=cache_dir,
            ttl_seconds=settings.cache_ttl_seconds,
            max_seconds=settings.pdf_download_timeout_seconds,
            max_bytes=settings.pdf_download_max_bytes,
        )
    except PdfDownloadError as exc:
        meta = dict(doc.meta or {})
        meta["fetch_error"] = str(exc)[:500]
        doc.meta = meta
        doc.status = DocumentStatus.FAILED
        doc.http_status = getattr(exc, "http_status", None)
        doc.last_seen_at = datetime.now(timezone.utc)
        session.flush()
        logger.warning("Fetch FAILED for %s: %s", url, exc)
        raise

    new_md5 = _md5_of_file(pdf_path)
    now = datetime.now(timezone.utc)
    # A cache hit skips the network, so "verified now" would overstate.
    # The sidecar records when the bytes actually came off the wire; use
    # that as the verification instant.
    verified_at = now
    try:
        import json as _json
        import time as _time

        from .pdf_download import _cache_paths

        _, meta_path = _cache_paths(cache_dir, url)
        created = float(
            _json.loads(meta_path.read_text(encoding="utf-8")).get(
                "created_at", _time.time()
            )
        )
        verified_at = datetime.fromtimestamp(created, tz=timezone.utc)
    except Exception:  # sidecar missing/corrupt: fall back to now
        pass

    if doc.md5 and doc.md5 != new_md5:
        meta = dict(doc.meta or {})
        meta["previous_md5"] = doc.md5
        meta["md5_changed_at"] = now.isoformat()
        doc.meta = meta
        logger.warning(
            "Document %s was RE-ISSUED by the publisher (md5 %s -> %s). "
            "Figures derived from the old bytes are unverified until "
            "re-extracted.",
            doc.id,
            doc.md5,
            new_md5,
        )

    # The fetcher owns document metadata: a row whose title no longer
    # matches what the URL actually serves (doc 2392 was filed as "County
    # Audit Findings" while holding the national report) is corrected
    # here, with the old title preserved in metadata.
    if title and doc.title != title:
        meta = dict(doc.meta or {})
        meta.setdefault("previous_titles", []).append(doc.title)
        doc.meta = meta
        doc.title = title

    doc.md5 = new_md5
    doc.file_path = str(pdf_path)
    doc.content_type = (
        mimetypes.guess_type(url)[0] or "application/pdf"
    )
    doc.http_status = 200  # get_or_download_pdf validated a 200 PDF body
    doc.fetch_date = doc.fetch_date or now
    doc.last_verified_at = verified_at
    doc.last_seen_at = now
    doc.status = DocumentStatus.AVAILABLE
    if dataset_id:
        meta = dict(doc.meta or {})
        meta["dataset_id"] = dataset_id
        doc.meta = meta
    session.flush()
    logger.info(
        "Fetched document %s (%d bytes, md5 %s) -> %s",
        doc.id,
        pdf_path.stat().st_size,
        new_md5,
        pdf_path,
    )
    return doc


__all__ = ["fetch_document"]

"""Streaming download + cross-run disk cache for large source PDFs.

Government BIRR/audit PDFs are 12-50MB and the COB CDN's throughput is wildly
variable (the same 48MB county file measured ~50s one night and ~556s the
next). Two problems this module addresses — see issue #119:

(a) ``httpx``'s request timeout is *per-operation* (the max gap between
    received chunks), not total elapsed, so a slow-but-steady 48MB body can
    stream for ~9 minutes and consume the entire per-domain SIGALRM budget,
    aborting the run mid-parse. :meth:`SeedingHttpClient.download_to_file`
    enforces a TOTAL wall-clock cap and raises :class:`PdfDownloadError` (a
    plain ``Exception``) so the caller's fixture fallback recovers cleanly.

(b) The download dominates the domain's time budget. :func:`get_or_download_pdf`
    caches the fetched file on disk keyed by URL; once a report is fetched,
    later runs reuse it and skip the download entirely. The "latest report"
    URL embeds a WordPress Download Manager id that changes only when COB
    publishes a new report, so a long TTL is safe and a new report naturally
    misses the cache. Persist the cache dir across CI runs (actions/cache) for
    this to help the nightly job.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from .http_client import (
    PdfDownloadError,
    PdfDownloadIncomplete,
    SeedingHttpClient,
)

logger = logging.getLogger("seeding.pdf_download")

# A real PDF starts with "%PDF-". Cheap magic-byte check to avoid caching an
# HTML error page / CDN challenge that was served with a 200 + wrong body.
_PDF_MAGIC = b"%PDF-"


def _cache_paths(cache_dir: Path, url: str) -> Tuple[Path, Path]:
    """Return (pdf_path, meta_path) for ``url`` inside ``cache_dir``.

    Keyed on a SHA-256 of the *request* URL (the ``?wpdmdl=NNN`` link), which
    is stable for a given report and changes when a new report is published.
    """
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.pdf", cache_dir / f"{digest}.json"


def _part_path(cache_dir: Path, url: str) -> Path:
    """Durable partial-download path for ``url``.

    Keyed on the URL exactly like the cache entry, so a resumed transfer can
    only ever continue the SAME document. Persisted between runs (and cached
    by CI via actions/cache) — that is what lets a 12MB PDF on a 43 KB/s link
    finish across several nightly runs instead of never.
    """
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.part"


def _fresh_cache_hit(
    pdf_path: Path, meta_path: Path, ttl_seconds: int
) -> Optional[Tuple[int, float]]:
    """Return (size_bytes, age_seconds) if a usable cache entry exists.

    A hit requires a non-empty ``.pdf`` and a ``.json`` sidecar whose recorded
    ``created_at`` is within ``[now - ttl_seconds, now]``. Any missing, corrupt,
    expired, or future-dated state is treated as a miss (returns ``None``) so
    the caller re-downloads.
    """
    if ttl_seconds <= 0 or not pdf_path.exists() or not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        created_at = float(meta.get("created_at", 0.0))
        size = pdf_path.stat().st_size
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    age = time.time() - created_at
    # A negative age means created_at is in the future — a skewed clock or a
    # corrupted sidecar. Fail closed and re-download rather than trusting a
    # future timestamp as "fresh" indefinitely.
    if size <= 0 or age < 0 or age > ttl_seconds:
        return None
    return size, age


def _verify_pdf_magic(path: Path, url: str) -> None:
    """Raise :class:`PdfDownloadError` unless ``path`` starts with ``%PDF-``."""
    try:
        with path.open("rb") as handle:
            head = handle.read(len(_PDF_MAGIC))
    except OSError as exc:  # pragma: no cover - defensive
        raise PdfDownloadError(
            f"could not read downloaded file for {url}: {exc}"
        ) from exc
    if head != _PDF_MAGIC:
        raise PdfDownloadError(
            f"downloaded content is not a PDF (starts with {head!r}): {url}"
        )


def _verify_pdf_complete(path: Path, url: str) -> None:
    """Raise unless ``path`` looks like a WHOLE PDF, not a truncated one.

    The header check alone cannot detect truncation, and these publishers
    send no ``Content-Length`` — so a transfer cut short still starts with
    ``%PDF-`` and would be cached and parsed as if complete, silently losing
    most of the document. Every PDF ends with an ``%%EOF`` marker, so the
    trailer is the completeness signal available to us.

    Scans the last 2KB: the spec allows trailing whitespace/newlines after
    ``%%EOF``, and incrementally-updated PDFs carry several such markers.
    """
    _verify_pdf_magic(path, url)
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(0, size - 2048))
            tail = handle.read()
    except OSError as exc:  # pragma: no cover - defensive
        raise PdfDownloadError(
            f"could not read downloaded file for {url}: {exc}"
        ) from exc
    if b"%%EOF" not in tail:
        raise PdfDownloadError(
            f"downloaded PDF is truncated ({size} bytes, no %%EOF trailer): "
            f"{url}"
        )


def _looks_like_whole_pdf(path: Path) -> bool:
    """Boolean form of :func:`_verify_pdf_complete`, for the download loop.

    The transport layer has no Content-Length to work with, so it asks this
    after each pass to decide whether the document is finished.
    """
    try:
        _verify_pdf_complete(path, "<in-progress>")
        return True
    except PdfDownloadError:
        return False


def get_or_download_pdf(
    client: SeedingHttpClient,
    url: str,
    *,
    cache_dir: Path,
    ttl_seconds: int,
    max_seconds: float,
    max_bytes: Optional[int] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Path:
    """Return a path to the PDF at ``url``, downloading only on a cache miss.

    On a hit (a non-empty cached file younger than ``ttl_seconds``) the cached
    path is returned with no network call. On a miss the body is streamed to a
    temp file *inside* ``cache_dir`` under a total ``max_seconds`` wall-clock
    cap, validated as a real PDF, then atomically moved into place so a partial
    or aborted download never poisons the cache.

    Raises :class:`PdfDownloadError` on timeout, oversize, or non-PDF content.
    The returned file lives in the persistent cache — callers must NOT delete
    it.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    pdf_path, meta_path = _cache_paths(cache_dir, url)

    hit = _fresh_cache_hit(pdf_path, meta_path, ttl_seconds)
    if hit is not None:
        size, age = hit
        logger.info(
            "PDF cache hit (%d bytes, age %.0fs): %s", size, age, url
        )
        return pdf_path

    part_path = _part_path(cache_dir, url)
    resumed_from = part_path.stat().st_size if part_path.exists() else 0
    logger.info(
        "PDF cache miss; streaming download (cap %.0fs, resuming from %d "
        "bytes): %s",
        max_seconds,
        resumed_from,
        url,
    )
    try:
        size = client.download_to_file(
            url,
            pdf_path,
            max_seconds=max_seconds,
            max_bytes=max_bytes,
            headers=headers,
            # Durable partial: kept on timeout so the next run continues
            # instead of restarting. Without this a document slower than the
            # cap can never be fetched at all.
            resume_part=part_path,
            completion_check=_looks_like_whole_pdf,
        )
        # Header AND trailer: these servers send no Content-Length, so a
        # truncated body is otherwise indistinguishable from a whole one.
        _verify_pdf_complete(pdf_path, url)
    except PdfDownloadIncomplete as exc:
        logger.warning(
            "PDF download incomplete: %d bytes on disk (advanced %d bytes "
            "this run). Progress RETAINED — the next run resumes from here. "
            "%s",
            exc.bytes_downloaded,
            exc.bytes_downloaded - resumed_from,
            url,
        )
        raise
    except BaseException:
        # A completed-but-invalid body (wrong magic, truncated, byte cap) is
        # not resumable progress — drop the partial so the next run restarts
        # clean, then re-raise unchanged for the caller's fallback.
        part_path.unlink(missing_ok=True)
        pdf_path.unlink(missing_ok=True)
        raise
    else:
        # Whole, validated PDF is now at pdf_path; the partial is spent.
        part_path.unlink(missing_ok=True)

    # Metadata is best-effort. The PDF is already safely in place, so a failed
    # sidecar write must NOT turn a successful download into an exception (which
    # the domain would catch and fall back to the fixture for). Without the
    # sidecar the next run simply treats it as a cache miss and re-downloads.
    try:
        meta_path.write_text(
            json.dumps({"url": url, "created_at": time.time(), "bytes": size}),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning(
            "PDF cached but metadata sidecar write failed (%s); next run will "
            "re-download: %s", exc, pdf_path,
        )
    logger.info("PDF downloaded and cached (%d bytes): %s", size, pdf_path)
    return pdf_path


__all__ = ["get_or_download_pdf"]

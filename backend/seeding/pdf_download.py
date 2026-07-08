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

from .http_client import PdfDownloadError, SeedingHttpClient

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


def _fresh_cache_hit(
    pdf_path: Path, meta_path: Path, ttl_seconds: int
) -> Optional[Tuple[int, float]]:
    """Return (size_bytes, age_seconds) if a usable cache entry exists.

    A hit requires a non-empty ``.pdf`` and a ``.json`` sidecar whose recorded
    ``created_at`` is within ``ttl_seconds``. Any missing/corrupt/expired state
    is treated as a miss (returns ``None``) so the caller re-downloads.
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
    if size <= 0 or age > ttl_seconds:
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

    logger.info(
        "PDF cache miss; streaming download (cap %.0fs): %s", max_seconds, url
    )
    # Temp file in the same directory as the cache so os.replace() is atomic
    # (a rename across filesystems is not).
    fd, tmp_name = tempfile.mkstemp(
        suffix=".pdf", prefix="pdf_dl_", dir=str(cache_dir)
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        size = client.download_to_file(
            url,
            tmp_path,
            max_seconds=max_seconds,
            max_bytes=max_bytes,
            headers=headers,
        )
        _verify_pdf_magic(tmp_path, url)
        os.replace(tmp_path, pdf_path)
    except BaseException:
        # Clean up the partial temp on ANY failure (incl. a SIGALRM-driven
        # DomainTimeoutError) — then re-raise unchanged so the caller's
        # fallback / the CLI handler still sees the original exception.
        tmp_path.unlink(missing_ok=True)
        raise

    meta_path.write_text(
        json.dumps({"url": url, "created_at": time.time(), "bytes": size}),
        encoding="utf-8",
    )
    logger.info("PDF downloaded and cached (%d bytes): %s", size, pdf_path)
    return pdf_path


__all__ = ["get_or_download_pdf"]

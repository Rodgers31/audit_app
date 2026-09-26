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

(c) A publisher can re-issue a document under the SAME link. COB's CBIRR
    download (``?wpdmdl=16482``) sends no ETag, Last-Modified or
    Content-Length, but it does name the file it is serving
    (``Content-disposition: attachment;filename="CGBIRR FY 2025_26 August
    2026 Final 5.pdf"``) — and "Final 5" says there were four before it. A
    caller that passes ``fingerprint`` (see :func:`probe_fingerprint`) gets
    a cache entry keyed on URL AND that fingerprint: a changed filename is a
    miss, and the stale partial is discarded rather than resumed onto. Every
    entry also records the SHA-256 of its bytes, so what was ingested is
    identified by content, not by the link that happened to serve it.
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


def probe_fingerprint(
    client: SeedingHttpClient,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """What the server says it is serving at ``url``, without the body.

    Built from whichever of Content-Disposition, ETag, Last-Modified and
    Content-Length the HEAD response carries. ``None`` when the probe fails
    or the server says nothing identifying — the caller then falls back to
    the URL-keyed cache and should record that the version was unverified.
    """
    try:
        response = client.head(
            url, raise_for_status=False, headers=headers, timeout=60.0
        )
    except Exception as exc:  # a probe must never block the download
        logger.warning("fingerprint probe failed for %s: %s", url, exc)
        return None
    if getattr(response, "status_code", 500) >= 400:
        return None
    hdrs = {k.lower(): v for k, v in (getattr(response, "headers", {}) or {}).items()}
    # A CDN challenge page answers 200 with HTML; its length is not the
    # document's identity, and treating it as one evicts a good cache entry.
    if "html" in hdrs.get("content-type", "").lower():
        return None
    # The file name alone when the server gives one: it is what changes on a
    # re-issue ("... Final 5.pdf"), and it does not change per request the
    # way a per-response ETag can (which would make every run a miss and
    # discard the resumable partial every night).
    if hdrs.get("content-disposition"):
        return f"content-disposition={hdrs['content-disposition']}"
    parts = [
        f"{name}={hdrs[name]}"
        for name in ("etag", "last-modified", "content-length")
        if hdrs.get(name)
    ]
    return "; ".join(parts) or None


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def cached_pdf_meta(cache_dir: Path, url: str) -> Dict[str, object]:
    """The sidecar of the cached entry for ``url`` (``{}`` if none)."""
    _, meta_path = _cache_paths(Path(cache_dir), url)
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return meta if isinstance(meta, dict) else {}


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
    # Validate the BYTES, not just the bookkeeping. Reported by review on
    # PR #136: this returned on size + TTL alone, so an entry written by the
    # earlier magic-bytes-only implementation kept serving a truncated PDF for
    # the whole 30-day TTL — and CI restores this directory across runs with a
    # rolling key, so such entries genuinely persist. A miss is cheap; a
    # silently truncated source document is not.
    if not _looks_like_whole_pdf(pdf_path):
        logger.warning(
            "Discarding cached PDF %s — it is truncated (no final %%%%EOF). "
            "Re-downloading; a cache entry written before the completeness "
            "check existed can look valid to the size test alone.",
            pdf_path.name,
        )
        pdf_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        created_at = float(meta.get("created_at", 0.0))
        size = pdf_path.stat().st_size
    except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError):
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

    Requires the last non-whitespace bytes to BE ``%%EOF`` — not merely to
    contain it somewhere in the tail. Reported by review on PR #136: an
    incrementally-updated PDF carries one marker per revision, so a transfer
    cut shortly after an EARLIER marker still had ``%%EOF`` within the window
    and was declared complete. That is not a cosmetic difference here: with no
    Content-Length, this function is the resumable downloader's completion
    signal, so a false "whole" STOPS the download and caches the truncation.

    Real government PDFs satisfy the stricter rule — verified against the five
    documents fetched on 2026-08-29, whose tails are ``...startxref\r\n<n>\r\n
    %%EOF\r\n``. Trailing whitespace after the marker is permitted by the spec
    and is stripped before the comparison.
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
    if not tail.rstrip().endswith(b"%%EOF"):
        where = "no %%EOF trailer" if b"%%EOF" not in tail else (
            "%%EOF present but not final — this is a truncated incremental "
            "revision, not a whole document"
        )
        raise PdfDownloadError(
            f"downloaded PDF is truncated ({size} bytes, {where}): {url}"
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
    fingerprint: Optional[str] = None,
) -> Path:
    """Return a path to the PDF at ``url``, downloading only on a cache miss.

    ``fingerprint`` (optional) is what the server currently says it serves at
    ``url``; an entry recorded under a different one is a miss. Callers that
    share a cache entry must pass the same value, or each will evict the
    other's download.

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

    part_path = _part_path(cache_dir, url)
    part_meta = part_path.with_suffix(".part.json")
    # True when a cached file exists but cannot be served (a re-issue, or a
    # version never recorded). It stays on disk until a validated
    # replacement is atomically moved over it: evicting first left the cache
    # empty whenever the replacement then failed (a CDN challenge, a
    # timeout), and counties_budget shares this entry.
    superseded = False
    try:
        part_fp = json.loads(part_meta.read_text(encoding="utf-8")).get("fingerprint")
    except (OSError, ValueError, AttributeError):
        part_fp = None
    if part_path.exists() and part_fp is not None and part_fp != fingerprint:
        # The partial belongs to a KNOWN issue, and tonight's is different
        # or cannot be checked. cob.go.ke honours Range with no If-Range
        # validator, so resuming would splice one document's head onto
        # another's tail — and the result passes both PDF checks.
        part_path.unlink(missing_ok=True)
        part_meta.unlink(missing_ok=True)
    if fingerprint is not None:
        sidecar = cached_pdf_meta(cache_dir, url)
        recorded = sidecar.get("fingerprint")
        legacy = bool(sidecar) and "fingerprint" not in sidecar
        if pdf_path.exists() and not legacy and recorded != fingerprint:
            # Includes a recorded NULL: the probe failed the night these
            # bytes were fetched, so which issue they are was never known.
            # Adopting them under tonight's name would relabel the old file
            # as the re-issue.
            logger.warning(
                "Cached PDF for %s was recorded under %r; the server now "
                "serves %r. Downloading again (the cached copy is kept until "
                "the new one is validated).",
                url,
                recorded,
                fingerprint,
            )
            superseded = True
        elif pdf_path.exists() and legacy:
            # An entry written before fingerprints existed (every entry in
            # the CI cache on the day this shipped). Evicting it would cost a
            # 50MB re-download at COB's 43 KB/s — several nights, during
            # which counties_budget starves too. Adopt it, and say so: its
            # version was never checked against the server.
            sidecar.update(
                fingerprint=fingerprint,
                fingerprint_adopted=True,
                sha256=sidecar.get("sha256") or _sha256_of(pdf_path),
            )
            try:
                meta_path.write_text(json.dumps(sidecar), encoding="utf-8")
            except OSError:
                pass
            logger.warning(
                "Adopted pre-fingerprint cache entry for %s as %r; its version "
                "was not verified against the server.",
                url,
                fingerprint,
            )
        try:
            part_meta.write_text(json.dumps({"fingerprint": fingerprint}), encoding="utf-8")
        except OSError:
            pass

    hit = None if superseded else _fresh_cache_hit(pdf_path, meta_path, ttl_seconds)
    if hit is not None:
        size, age = hit
        logger.info(
            "PDF cache hit (%d bytes, age %.0fs): %s", size, age, url
        )
        return pdf_path

    resumed_from = part_path.stat().st_size if part_path.exists() else 0
    staging = pdf_path.with_suffix(".incoming.pdf")
    logger.info(
        "PDF cache miss; streaming download (cap %.0fs, resuming from %d "
        "bytes): %s",
        max_seconds,
        resumed_from,
        url,
    )
    try:
        # Into a staging file, validated there, and only then moved over the
        # cache entry. download_to_file replaces its destination as soon as
        # the transfer completes — before anyone has checked the body is a
        # PDF — so downloading straight onto pdf_path let a 200 HTML
        # challenge page overwrite the previous good copy.
        size = client.download_to_file(
            url,
            staging,
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
        _verify_pdf_complete(staging, url)
        os.replace(staging, pdf_path)
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
        # clean, then re-raise unchanged for the caller's fallback. The cache
        # entry itself was never touched: whatever is there is the previous
        # copy, which a later run re-judges on its own merits.
        part_path.unlink(missing_ok=True)
        part_meta.unlink(missing_ok=True)
        staging.unlink(missing_ok=True)
        raise
    else:
        # Whole, validated PDF is now at pdf_path; the partial is spent.
        part_path.unlink(missing_ok=True)
        part_meta.unlink(missing_ok=True)

    # Metadata is best-effort. The PDF is already safely in place, so a failed
    # sidecar write must NOT turn a successful download into an exception (which
    # the domain would catch and fall back to the fixture for). Without the
    # sidecar the next run simply treats it as a cache miss and re-downloads.
    try:
        meta_path.write_text(
            json.dumps(
                {
                    "url": url,
                    "created_at": time.time(),
                    "bytes": size,
                    "sha256": _sha256_of(pdf_path),
                    "fingerprint": fingerprint,
                }
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning(
            "PDF cached but metadata sidecar write failed (%s); next run will "
            "re-download: %s", exc, pdf_path,
        )
    logger.info("PDF downloaded and cached (%d bytes): %s", size, pdf_path)
    return pdf_path


__all__ = ["cached_pdf_meta", "get_or_download_pdf", "probe_fingerprint"]

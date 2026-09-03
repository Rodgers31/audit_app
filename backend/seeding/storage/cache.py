"""Basic file-backed HTTP response cache used by the seeding client."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger("seeding.cache")


def _canonical_url(url: str, params: Optional[Any]) -> str:
    if params in (None, {}, []):
        return url
    query = httpx.QueryParams(params)
    return str(httpx.URL(url=url, params=query))


class SimpleHTTPCache:
    """Persist GET responses to disk using hashed file names."""

    def __init__(self, base_path: Path, ttl_seconds: int = 3600) -> None:
        self._base_path = Path(base_path).expanduser()
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._ttl_seconds = ttl_seconds

    def _cache_key(self, method: str, full_url: str) -> Path:
        digest = hashlib.sha256(
            f"{method.upper()}:{full_url}".encode("utf-8")
        ).hexdigest()
        return self._base_path / digest

    def get(
        self,
        method: str,
        url: str,
        params: Optional[Any] = None,
    ) -> Optional[httpx.Response]:
        full_url = _canonical_url(url, params)
        base = self._cache_key(method, full_url)
        meta_path = base.with_suffix(".json")
        body_path = base.with_suffix(".bin")

        if not meta_path.exists() or not body_path.exists():
            return None

        try:
            with meta_path.open("r", encoding="utf-8") as meta_file:
                meta = json.load(meta_file)
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug(
                "Failed to load cache metadata",
                extra={"url": full_url, "error": str(exc)},
            )
            self._purge_paths(meta_path, body_path)
            return None

        created_at = meta.get("created_at")
        if created_at is None or (time.time() - float(created_at)) > self._ttl_seconds:
            self._purge_paths(meta_path, body_path)
            return None

        try:
            content = body_path.read_bytes()
        except OSError as exc:
            logger.debug(
                "Failed to read cache body", extra={"url": full_url, "error": str(exc)}
            )
            self._purge_paths(meta_path, body_path)
            return None

        request = httpx.Request(method.upper(), full_url)
        headers = httpx.Headers(meta.get("headers", []))
        response = httpx.Response(
            status_code=meta.get("status_code", 200),
            headers=headers,
            content=content,
            request=request,
        )
        response.extensions["seeding_cache"] = True
        return response

    def set(self, response: httpx.Response) -> None:
        if response.request is None:
            return
        method = response.request.method
        full_url = str(response.request.url)
        base = self._cache_key(method, full_url)
        meta_path = base.with_suffix(".json")
        body_path = base.with_suffix(".bin")

        # ``response.content`` is the DECODED body — httpx has already
        # gunzipped it. Persisting the original Content-Encoding alongside
        # decoded bytes makes every cache HIT fail with
        # "Error -3 while decompressing data: incorrect header check",
        # because httpx dutifully tries to gunzip plain text. That silently
        # broke live fetches for every gzip-serving publisher (World Bank,
        # CBK, the OAG media API) on the second run inside the TTL, and each
        # one fell back to a fixture. Content-Length is dropped for the same
        # reason: it describes the COMPRESSED body and no longer matches.
        _DROP = {"content-encoding", "content-length", "transfer-encoding"}
        stored_headers = [
            (k, v)
            for k, v in response.headers.multi_items()
            if k.lower() not in _DROP
        ]
        metadata = {
            "method": method,
            "url": full_url,
            "status_code": response.status_code,
            "headers": stored_headers,
            "created_at": time.time(),
        }

        try:
            with meta_path.open("w", encoding="utf-8") as meta_file:
                json.dump(metadata, meta_file)
            body_path.write_bytes(response.content)
        except OSError as exc:
            logger.debug(
                "Failed to persist cache entry",
                extra={"url": full_url, "error": str(exc)},
            )
            self._purge_paths(meta_path, body_path)

    def _purge_paths(self, meta_path: Path, body_path: Path) -> None:
        for path in (meta_path, body_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue

    def clear(self) -> None:
        for path in self._base_path.glob("*"):
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                continue


__all__ = ["SimpleHTTPCache"]

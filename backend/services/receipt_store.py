"""Immutable receipt bytes. Public serializers consume metadata, never this store.

ReceiptStore is the production adapter contract; LocalReceiptStore is an explicitly
local implementation, not a claim about storage surviving a deployment.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Protocol


class ReceiptStore(Protocol):
    def put(self, body: bytes) -> str: ...
    def read(self, digest: str) -> bytes: ...


def configured_receipt_store(settings) -> ReceiptStore:
    """One binding for HTTP and PDF paths; selected durable storage never falls back."""
    backend = getattr(settings, "receipt_storage_backend", "local")
    max_bytes = getattr(settings, "receipt_max_bytes", None)
    if backend == "local":
        return LocalReceiptStore(
            Path(settings.storage_path) / "response-receipts",
            max_bytes=64 * 1024 * 1024 if max_bytes is None else max_bytes,
        )
    if backend not in ("supabase", "r2"):
        raise ValueError("Unknown receipt storage backend")
    if max_bytes is None:
        raise ValueError("Durable receipt byte limit must be explicitly configured")
    from config.secrets import get_secret
    if backend == "r2":
        from services.r2_receipt_store import R2ReceiptStore, validate_destination
        validate_destination(settings.receipt_r2_account_id, settings.receipt_r2_bucket, settings.receipt_r2_jurisdiction)
        return R2ReceiptStore(
            settings.receipt_r2_account_id, settings.receipt_r2_bucket,
            get_secret("RECEIPT_R2_ACCESS_KEY_ID"),
            get_secret("RECEIPT_R2_SECRET_ACCESS_KEY"),
            get_secret("RECEIPT_R2_CONTROL_TOKEN"),
            jurisdiction=settings.receipt_r2_jurisdiction,
            max_bytes=max_bytes,
            part_max_bytes=R2ReceiptStore.DEFAULT_PART_BYTES if getattr(settings, "receipt_part_max_bytes", None) is None else settings.receipt_part_max_bytes,
            timeout_seconds=settings.receipt_storage_timeout_seconds,
        )
    from services.supabase_receipt_store import SupabaseReceiptStore, validate_destination
    validate_destination(settings.receipt_supabase_url, settings.receipt_supabase_bucket)
    return SupabaseReceiptStore(
        settings.receipt_supabase_url,
        settings.receipt_supabase_bucket,
        get_secret("RECEIPT_SUPABASE_SECRET_KEY"),
        max_bytes=max_bytes,
        part_max_bytes=SupabaseReceiptStore.DEFAULT_PART_BYTES if getattr(settings, "receipt_part_max_bytes", None) is None else settings.receipt_part_max_bytes,
        timeout_seconds=settings.receipt_storage_timeout_seconds,
    )


class LocalReceiptStore:
    storage_scope = "local"

    def __init__(self, root: Path, *, max_bytes: int = 64 * 1024 * 1024):
        if type(max_bytes) is not int or not 1 <= max_bytes <= 64 * 1024 * 1024:
            raise ValueError("Receipt byte limit must be an integer within 1..67108864")
        self.root = Path(root)
        self.max_bytes = max_bytes

    def _path(self, digest: str) -> Path:
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Receipt digest must be lowercase SHA256")
        return self.root / digest[:2] / digest

    def put(self, body: bytes) -> str:
        if not isinstance(body, bytes) or not body or len(body) > self.max_bytes:
            raise ValueError("Receipt body absent or exceeds byte limit")
        digest = hashlib.sha256(body).hexdigest()
        path = self._path(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".receipt-")
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(body)
                out.flush()
                os.fsync(out.fileno())
            # Link is atomic and refuses overwrite. Existing objects must match.
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
            with open(path, "rb") as retained:
                if hashlib.sha256(retained.read()).hexdigest() != digest:
                    raise ValueError("Existing receipt object digest mismatch")
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            os.unlink(temporary)
        return digest

    def read(self, digest: str) -> bytes:
        path = self._path(digest)
        if path.stat().st_size > self.max_bytes:
            raise ValueError("Receipt exceeds read limit")
        body = path.read_bytes()
        if not body or hashlib.sha256(body).hexdigest() != digest:
            raise ValueError("Receipt readback digest mismatch")
        return body

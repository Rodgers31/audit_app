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


class LocalReceiptStore:
    def __init__(self, root: Path, *, max_bytes: int = 64 * 1024 * 1024):
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

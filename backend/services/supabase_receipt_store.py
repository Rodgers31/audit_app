"""Optional private Supabase receipt storage; no provisioning or lifecycle API.

This adapter proves byte retention at the requested boundary, not the provider's
backup, quota, retention or disaster recovery guarantees.
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from urllib.parse import urlsplit

import httpx


class ReceiptStorageError(RuntimeError):
    """Safe to persist/log: never includes credentials, URLs or provider bodies."""


_SAFE_TRANSFER_REASONS = frozenset(
    {
        "Receipt storage exceeded transfer time limit",
        "Receipt storage returned encoded bytes",
        "Receipt storage returned invalid or excessive size",
        "Receipt storage exceeded read limit",
        "Receipt storage returned partial bytes",
    }
)


def validate_destination(project_url: str, bucket: str) -> str:
    """Hosted project endpoints only; credentials cannot be redirected elsewhere."""
    if not isinstance(project_url, str) or not re.fullmatch(
        r"https://[a-z0-9]{20}\.supabase\.co/?", project_url
    ):
        raise ValueError("Receipt storage requires a hosted HTTPS Supabase project URL")
    if not isinstance(bucket, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9_-]{0,62}", bucket
    ):
        raise ValueError("Receipt bucket must be a simple lowercase identifier")
    return project_url.rstrip("/")


class SupabaseReceiptStore:
    storage_scope = "supabase_private"

    def __init__(
        self,
        project_url: str,
        bucket: str,
        secret_key: str,
        *,
        max_bytes: int = 64 * 1024 * 1024,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.project_url = validate_destination(project_url, bucket)
        self.bucket = bucket
        # Modern server secret keys go on apikey, not Authorization: Bearer.
        # Reject public/anon keys and whitespace before constructing headers.
        if not isinstance(secret_key, str) or not re.fullmatch(
            r"sb_secret_[A-Za-z0-9_-]{20,256}", secret_key
        ):
            raise ValueError("Receipt storage requires a server Supabase secret key")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 64 * 1024 * 1024:
            raise ValueError("Receipt byte limit must be an integer within 1..67108864")
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 120
        ):
            raise ValueError(
                "Receipt timeout must be finite and within (0, 120] seconds"
            )
        self.max_bytes = max_bytes
        self._timeout = timeout_seconds
        self._transport = transport
        self._headers = {
            "apikey": secret_key,
            "Accept-Encoding": "identity",
            "User-Agent": "KenyaAuditAppReceiptStore/1.0",
        }

    @property
    def project_ref(self) -> str:
        return urlsplit(self.project_url).hostname.split(".")[0]

    def _object_path(self, digest: str) -> str:
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Receipt digest must be lowercase SHA256")
        return f"{self.bucket}/sha256/{digest[:2]}/{digest}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        limit: int,
        body: bytes | None = None,
        deadline: float,
    ) -> tuple[int, bytes]:
        headers = dict(self._headers)
        if body is not None:
            headers.update(
                {"Content-Type": "application/octet-stream", "x-upsert": "false"}
            )
        # Per-call clients have no retained connection/process state. Disable
        # env proxies and redirects so a server key stays at the validated host.
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ReceiptStorageError(
                    "Receipt storage exceeded transfer time limit"
                )
            with httpx.Client(
                timeout=remaining,
                transport=self._transport,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                with client.stream(
                    method,
                    f"{self.project_url}/storage/v1/{path}",
                    headers=headers,
                    content=body,
                ) as response:
                    if time.monotonic() >= deadline:
                        raise ReceiptStorageError(
                            "Receipt storage exceeded transfer time limit"
                        )
                    status = response.status_code
                    # Error bodies may contain keys, source data or HTML; never read them.
                    if status != 200:
                        return status, b""
                    if (
                        response.headers.get("content-encoding", "identity").lower()
                        != "identity"
                    ):
                        raise ReceiptStorageError(
                            "Receipt storage returned encoded bytes"
                        )
                    declared = response.headers.get("content-length")
                    if declared is not None and (
                        not re.fullmatch(r"[0-9]+", declared) or int(declared) > limit
                    ):
                        raise ReceiptStorageError(
                            "Receipt storage returned invalid or excessive size"
                        )
                    chunks = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() >= deadline:
                            raise ReceiptStorageError(
                                "Receipt storage exceeded transfer time limit"
                            )
                        if len(chunks) + len(chunk) > limit:
                            raise ReceiptStorageError(
                                "Receipt storage exceeded read limit"
                            )
                        chunks.extend(chunk)
                    # EOF may itself arrive late after the final body chunk.
                    if time.monotonic() >= deadline:
                        raise ReceiptStorageError(
                            "Receipt storage exceeded transfer time limit"
                        )
                    if declared is not None and len(chunks) != int(declared):
                        raise ReceiptStorageError(
                            "Receipt storage returned partial bytes"
                        )
                    return status, bytes(chunks)
        except ReceiptStorageError as exc:
            # A custom transport can raise this public type too. Only our fixed
            # boundary reasons are safe; never trust arbitrary exception text.
            if (
                type(exc) is ReceiptStorageError
                and len(exc.args) == 1
                and isinstance(exc.args[0], str)
                and exc.args[0] in _SAFE_TRANSFER_REASONS
            ):
                raise ReceiptStorageError(exc.args[0]) from None
            raise ReceiptStorageError("Receipt storage transport failed") from None
        except Exception:
            # Suppress chained exceptions too: transports may echo request headers.
            raise ReceiptStorageError("Receipt storage transport failed") from None

    def _private_bucket(self, deadline: float) -> None:
        import json

        status, body = self._request(
            "GET", f"bucket/{self.bucket}", limit=16 * 1024, deadline=deadline
        )
        if status != 200:
            raise ReceiptStorageError(f"Receipt bucket check refused (HTTP {status})")
        try:
            metadata = json.loads(body)
        except (ValueError, UnicodeError):
            raise ReceiptStorageError("Receipt bucket metadata malformed") from None
        if (
            not isinstance(metadata, dict)
            or metadata.get("id") != self.bucket
            or metadata.get("public") is not False
        ):
            raise ReceiptStorageError("Receipt bucket must be confirmed private")
        bucket_limit = metadata.get("file_size_limit")
        if bucket_limit is not None and (
            type(bucket_limit) is not int or bucket_limit < self.max_bytes
        ):
            raise ReceiptStorageError(
                "Receipt byte limit exceeds or cannot validate bucket capacity"
            )

    def put(self, body: bytes) -> str:
        digest, _ = self.put_and_read(body)
        return digest

    def put_and_read(self, body: bytes) -> tuple[str, bytes]:
        """Retain and return verified readback without a second full download.

        Optional ingestion optimization; put/read remain the provider-neutral
        contract. No cached byte check is reused by subsequent independent reads.
        """
        if not isinstance(body, bytes) or not body or len(body) > self.max_bytes:
            raise ValueError("Receipt body absent or exceeds byte limit")
        digest = hashlib.sha256(body).hexdigest()
        deadline = time.monotonic() + self._timeout
        self._private_bucket(deadline)
        status, _ = self._request(
            "POST",
            f"object/{self._object_path(digest)}",
            limit=16 * 1024,
            body=body,
            deadline=deadline,
        )
        # Supabase reports duplicate insert as 400 (older API) or 409.
        # Neither is success until authenticated readback proves the exact bytes.
        if status not in (200, 201, 400, 409):
            raise ReceiptStorageError(f"Receipt upload refused (HTTP {status})")
        retained = self._read(digest, deadline)
        if len(retained) != len(body) or retained != body:
            raise ReceiptStorageError("Receipt upload readback mismatch")
        if time.monotonic() >= deadline:
            raise ReceiptStorageError("Receipt storage exceeded transfer time limit")
        return digest, retained

    def read(self, digest: str) -> bytes:
        return self._read(digest, time.monotonic() + self._timeout)

    def _read(self, digest: str, deadline: float) -> bytes:
        path = self._object_path(digest)
        self._private_bucket(deadline)
        status, body = self._request(
            "GET",
            f"object/authenticated/{path}",
            limit=self.max_bytes,
            deadline=deadline,
        )
        if status != 200:
            raise ReceiptStorageError(f"Receipt read refused (HTTP {status})")
        if not body or hashlib.sha256(body).hexdigest() != digest:
            raise ReceiptStorageError("Receipt readback digest mismatch")
        if time.monotonic() >= deadline:
            raise ReceiptStorageError("Receipt storage exceeded transfer time limit")
        return body

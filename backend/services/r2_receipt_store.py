"""Private R2 source receipts: signed insert-only IO and direct-public-access checks.

Runtime credentials can overwrite/delete objects; this adapter never does so.
The control-plane token is account-wide read access, not a bucket-only secret.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time

import httpx
from botocore.auth import S3SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

from .receipt_manifest import ReceiptManifestCodec
from .receipt_storage_errors import ReceiptStorageError, _SAFE_TRANSFER_REASONS


def validate_destination(account_id: str, bucket: str, jurisdiction: str = "default") -> str:
    if not isinstance(account_id, str) or not re.fullmatch(r"[a-f0-9]{32}", account_id):
        raise ValueError("Receipt R2 account must be a lowercase account identifier")
    if not isinstance(bucket, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket):
        raise ValueError("Receipt R2 bucket must be a simple lowercase identifier")
    if jurisdiction not in ("default", "eu", "us"):
        raise ValueError("Receipt R2 jurisdiction must be explicitly supported")
    suffix = "" if jurisdiction == "default" else "." + jurisdiction
    return f"https://{account_id}{suffix}.r2.cloudflarestorage.com"


def _unique_json(encoded: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate metadata field")
            result[key] = value
        return result
    return json.loads(encoded, object_pairs_hook=unique)


class R2ReceiptStore(ReceiptManifestCodec):
    storage_scope = "r2_private"

    def __init__(self, account_id: str, bucket: str, access_key: str, secret_key: str, control_token: str, *, jurisdiction: str = "default", max_bytes: int = 64 * 1024 * 1024, part_max_bytes: int = ReceiptManifestCodec.DEFAULT_PART_BYTES, timeout_seconds: float = 30.0, transport: httpx.BaseTransport | None = None):
        self.endpoint = validate_destination(account_id, bucket, jurisdiction)
        for credential in (access_key, secret_key, control_token):
            if not isinstance(credential, str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,256}", credential):
                raise ValueError("Receipt R2 server credentials must be explicitly configured")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 64 * 1024 * 1024:
            raise ValueError("Receipt byte limit must be an integer within 1..67108864")
        if type(part_max_bytes) is not int or not 1 <= part_max_bytes <= self.DEFAULT_PART_BYTES:
            raise ValueError("Receipt part byte limit must be an integer within 1..33554432")
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 120:
            raise ValueError("Receipt timeout must be finite and within (0, 120] seconds")
        self.account_id, self.bucket, self.jurisdiction = account_id, bucket, jurisdiction
        self.max_bytes, self.part_max_bytes = max_bytes, part_max_bytes
        self._timeout, self._transport = timeout_seconds, transport
        self._credentials = Credentials(access_key, secret_key)
        self._control_token = control_token

    def _object_path(self, digest: str, *, kind: str = "manifests") -> str:
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Receipt digest must be lowercase SHA256")
        if kind not in ("chunks", "manifests"):
            raise ValueError("Unknown receipt object namespace")
        return f"receipts-v1/{kind}/{digest[:2]}/{digest}"

    def _request(self, method: str, path: str, *, limit: int, deadline: float, body: bytes | None = None, control: bool = False) -> tuple[int, bytes]:
        try:
            headers = {"Accept-Encoding": "identity", "User-Agent": "KenyaAuditAppReceiptStore/1.0"}
            if control:
                url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/r2/buckets/{self.bucket}{path}"
                headers.update({"Authorization": "Bearer " + self._control_token, "cf-r2-jurisdiction": self.jurisdiction})
            else:
                url = f"{self.endpoint}/{self.bucket}/{path}"
                if body is not None:
                    headers.update({"Content-Type": "application/octet-stream", "Content-Length": str(len(body)), "If-None-Match": "*", "x-amz-storage-class": "STANDARD"})
                request = AWSRequest(method=method, url=url, data=body, headers=headers)
                S3SigV4Auth(self._credentials, "s3", "auto").add_auth(request)
                headers = dict(request.headers)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ReceiptStorageError("Receipt storage exceeded transfer time limit")
            with httpx.Client(timeout=remaining, transport=self._transport, trust_env=False, follow_redirects=False) as client:
                with client.stream(method, url, headers=headers, content=body) as response:
                    if time.monotonic() >= deadline:
                        raise ReceiptStorageError("Receipt storage exceeded transfer time limit")
                    status = response.status_code
                    if status != 200 or method == "PUT":
                        return status, b""  # Discard provider/error bodies, including successful PUT bodies.
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise ReceiptStorageError("Receipt storage returned encoded bytes")
                    declared = response.headers.get("content-length")
                    if declared is not None and (not re.fullmatch(r"[0-9]+", declared) or int(declared) > limit):
                        raise ReceiptStorageError("Receipt storage returned invalid or excessive size")
                    chunks = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() >= deadline:
                            raise ReceiptStorageError("Receipt storage exceeded transfer time limit")
                        if len(chunks) + len(chunk) > limit:
                            raise ReceiptStorageError("Receipt storage exceeded read limit")
                        chunks.extend(chunk)
                    if time.monotonic() >= deadline:
                        raise ReceiptStorageError("Receipt storage exceeded transfer time limit")
                    if declared is not None and len(chunks) != int(declared):
                        raise ReceiptStorageError("Receipt storage returned partial bytes")
                    return status, bytes(chunks)
        except ReceiptStorageError as exc:
            if type(exc) is ReceiptStorageError and len(exc.args) == 1 and isinstance(exc.args[0], str) and exc.args[0] in _SAFE_TRANSFER_REASONS:
                raise ReceiptStorageError(exc.args[0]) from None
            raise ReceiptStorageError("Receipt storage transport failed") from None
        except Exception:
            raise ReceiptStorageError("Receipt storage transport failed") from None

    def _metadata(self, path: str, deadline: float) -> dict:
        status, body = self._request("GET", path, limit=64 * 1024, deadline=deadline, control=True)
        if status != 200:
            raise ReceiptStorageError(f"Receipt R2 privacy check refused (HTTP {status})")
        try:
            envelope = _unique_json(body)
            if not isinstance(envelope, dict) or envelope.get("success") is not True or type(envelope.get("errors")) is not list or len(envelope["errors"]) != 0 or not isinstance(envelope.get("result"), dict):
                raise ValueError()
            return envelope["result"]
        except (ValueError, UnicodeError, RecursionError):
            raise ReceiptStorageError("Receipt R2 privacy metadata malformed") from None

    def _private_bucket(self, deadline: float) -> None:
        bucket = self._metadata("", deadline)
        if bucket.get("name") != self.bucket or bucket.get("storage_class") != "Standard" or bucket.get("jurisdiction") != self.jurisdiction:
            raise ReceiptStorageError("Receipt R2 bucket identity or storage class mismatch")
        managed = self._metadata("/domains/managed", deadline)
        if managed.get("enabled") is not False or not isinstance(managed.get("bucketId"), str) or not managed["bucketId"] or not isinstance(managed.get("domain"), str) or not managed["domain"]:
            raise ReceiptStorageError("Receipt R2 direct public access must be confirmed disabled")
        custom = self._metadata("/domains/custom", deadline)
        domains = custom.get("domains")
        if not isinstance(domains, list) or any(not isinstance(domain, dict) or domain.get("enabled") is not False or not isinstance(domain.get("domain"), str) or not domain["domain"] for domain in domains):
            raise ReceiptStorageError("Receipt R2 direct public access must be confirmed disabled")
        return None

    def _insert(self, path: str, body: bytes, deadline: float) -> None:
        status, _ = self._request("PUT", path, limit=16 * 1024, body=body, deadline=deadline)
        if status not in (200, 201, 412):
            raise ReceiptStorageError(f"Receipt upload refused (HTTP {status})")

    def _get(self, path: str, limit: int, deadline: float) -> bytes:
        status, body = self._request("GET", path, limit=limit, deadline=deadline)
        if status != 200:
            raise ReceiptStorageError(f"Receipt read refused (HTTP {status})")
        return body

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
        deadline = time.monotonic() + self._timeout
        digest = hashlib.sha256(body).hexdigest()
        encoded, parts = self._manifest(body, digest)
        bucket_limit = self._private_bucket(deadline)
        if (
            bucket_limit is not None
            and max(len(encoded), *(len(part) for part in parts)) > bucket_limit
        ):
            raise ReceiptStorageError("Receipt physical object exceeds bucket capacity")
        # Verify each part before publishing the manifest. Partial attempts can
        # leave immutable orphan parts, but cannot certify an incomplete source.
        reconstructed = bytearray()
        for part in parts:
            part_digest = hashlib.sha256(part).hexdigest()
            path = self._object_path(part_digest, kind="chunks")
            self._insert(path, part, deadline)
            retained_part = self._get(path, len(part), deadline)
            if retained_part != part:
                raise ReceiptStorageError("Receipt part readback digest mismatch")
            reconstructed.extend(retained_part)
        self._insert(self._object_path(digest), encoded, deadline)
        # Manifest readback binds the already verified parts in this same
        # bounded operation; no second source download or cross-operation cache.
        if self._get(self._object_path(digest), len(encoded), deadline) != encoded:
            raise ReceiptStorageError("Receipt manifest readback mismatch")
        retained = bytes(reconstructed)
        if (
            len(retained) != len(body)
            or retained != body
            or hashlib.sha256(retained).hexdigest() != digest
        ):
            raise ReceiptStorageError("Receipt upload readback mismatch")
        if time.monotonic() >= deadline:
            raise ReceiptStorageError("Receipt storage exceeded transfer time limit")
        return digest, retained

    def read(self, digest: str) -> bytes:
        return self._read(digest, time.monotonic() + self._timeout)

    def _read(self, digest: str, deadline: float) -> bytes:
        path = self._object_path(digest)
        bucket_limit = self._private_bucket(deadline)
        encoded = self._get(
            path,
            min(self.MANIFEST_MAX_BYTES, bucket_limit)
            if bucket_limit is not None
            else self.MANIFEST_MAX_BYTES,
            deadline,
        )
        manifest = self._parse_manifest(encoded, digest, bucket_limit)
        reconstructed = bytearray()
        for part in manifest["parts"]:
            retained = self._get(
                self._object_path(part["sha256"], kind="chunks"),
                part["byte_size"],
                deadline,
            )
            if (
                len(retained) != part["byte_size"]
                or hashlib.sha256(retained).hexdigest() != part["sha256"]
            ):
                raise ReceiptStorageError("Receipt part readback digest mismatch")
            reconstructed.extend(retained)
        body = bytes(reconstructed)
        if len(body) != manifest["byte_size"]:
            raise ReceiptStorageError("Receipt reconstructed size mismatch")
        if not body or hashlib.sha256(body).hexdigest() != digest:
            raise ReceiptStorageError("Receipt readback digest mismatch")
        if time.monotonic() >= deadline:
            raise ReceiptStorageError("Receipt storage exceeded transfer time limit")
        return body

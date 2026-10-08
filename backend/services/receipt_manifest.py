"""Strict version-one receipt manifest codec shared by durable providers."""
import hashlib
import json
import re

from .receipt_storage_errors import ReceiptStorageError


class ReceiptManifestCodec:
    MANIFEST_MAX_BYTES = 64 * 1024
    MAX_PARTS = 64
    DEFAULT_PART_BYTES = 32 * 1024 * 1024

    def _manifest(self, body: bytes, digest: str) -> tuple[bytes, list[bytes]]:
        # Refuse unsupported segmentation before allocating/slicing any parts.
        part_count = (len(body) + self.part_max_bytes - 1) // self.part_max_bytes
        if part_count > self.MAX_PARTS:
            raise ValueError(
                "Receipt requires too many parts for configured part limit"
            )
        parts = [
            body[start : start + self.part_max_bytes]
            for start in range(0, len(body), self.part_max_bytes)
        ]
        manifest = {
            "version": 1,
            "type": "source-receipt-chunks",
            "sha256": digest,
            "byte_size": len(body),
            "part_count": len(parts),
            "parts": [
                {
                    "index": i,
                    "sha256": hashlib.sha256(part).hexdigest(),
                    "byte_size": len(part),
                }
                for i, part in enumerate(parts)
            ],
        }
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        if len(encoded) > self.MANIFEST_MAX_BYTES:
            raise ValueError("Receipt manifest exceeds byte limit")
        return encoded, parts

    def _parse_manifest(
        self, encoded: bytes, digest: str, bucket_limit: int | None
    ) -> dict:
        def unique_object(pairs):
            result = {}
            for name, value in pairs:
                if name in result:
                    raise ValueError("Duplicate manifest field")
                result[name] = value
            return result

        try:
            manifest = json.loads(encoded, object_pairs_hook=unique_object)
        except (ValueError, UnicodeError, RecursionError):
            raise ReceiptStorageError("Receipt manifest malformed") from None
        if (
            not isinstance(manifest, dict)
            or set(manifest)
            != {"version", "type", "sha256", "byte_size", "part_count", "parts"}
            or type(manifest["version"]) is not int
            or manifest["version"] != 1
            or manifest["type"] != "source-receipt-chunks"
            or manifest["sha256"] != digest
            or type(manifest["byte_size"]) is not int
            or not 1 <= manifest["byte_size"] <= self.max_bytes
            or not isinstance(manifest["parts"], list)
            or not 1 <= len(manifest["parts"]) <= self.MAX_PARTS
            or type(manifest["part_count"]) is not int
            or manifest["part_count"] != len(manifest["parts"])
        ):
            raise ReceiptStorageError("Receipt manifest shape or identity mismatch")
        total = 0
        for index, part in enumerate(manifest["parts"]):
            if (
                not isinstance(part, dict)
                or set(part) != {"index", "sha256", "byte_size"}
                or type(part["index"]) is not int
                or part["index"] != index
                or not isinstance(part["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", part["sha256"])
                or type(part["byte_size"]) is not int
                or not 1 <= part["byte_size"] <= self.part_max_bytes
                or bucket_limit is not None
                and part["byte_size"] > bucket_limit
            ):
                raise ReceiptStorageError("Receipt manifest part invalid")
            total += part["byte_size"]
        if total != manifest["byte_size"]:
            raise ReceiptStorageError("Receipt manifest size mismatch")
        return manifest


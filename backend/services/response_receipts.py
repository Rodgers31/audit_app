"""Shared metadata-only acquisition persistence over the existing Extraction model."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
import logging
from datetime import datetime, timezone
from typing import Any

from models import Extraction
from .receipt_store import ReceiptStore

logger = logging.getLogger(__name__)

# Runtime authority is deliberately absent from the serialized receipt. A JSON
# dictionary (including a previously exported valid receipt) has no capability.
_CAPABILITY = object()


def _fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class CapturedReceipt(dict):
    """Opaque acquisition capability with mutation-detecting snapshots."""

    def __init__(self, value, *, _capability=None):
        if _capability is not _CAPABILITY:
            raise TypeError("Receipts require actual byte acquisition")
        super().__init__(value)
        self._acquisition = _fingerprint(self._acquisition_fields())
        self._sealed = None
        self._store = None
        self._bound_source = []

    def _acquisition_fields(self):
        return {
            k: v for k, v in self.items() if k not in ("observations", "parser_version")
        }

    def __deepcopy__(self, memo):
        copied = CapturedReceipt(deepcopy(dict(self), memo), _capability=_CAPABILITY)
        # Copy the original immutable snapshots, never bless current mutations.
        copied._acquisition, copied._sealed = self._acquisition, self._sealed
        copied._store = self._store
        copied._bound_source = self._bound_source
        memo[id(self)] = copied
        return copied

    def __reduce_ex__(self, protocol):
        # Even non-JSON serialization must not recreate runtime authority.
        return dict, (dict(self),)


def acquisition_is_intact(receipt):
    try:
        return isinstance(
            receipt, CapturedReceipt
        ) and receipt._acquisition == _fingerprint(receipt._acquisition_fields())
    except (TypeError, ValueError, OverflowError):
        return False


def copy_receipt(receipt, **parser_fields):
    """Carry acquisition authority through controlled parser annotations."""
    if not acquisition_is_intact(receipt):
        raise ValueError("Acquisition receipt is untrusted or changed")
    if receipt._sealed is not None or "observations" in receipt:
        raise ValueError(
            "Parser annotations require an unsealed acquisition without a manifest"
        )
    if set(parser_fields) - {
        "parser_version",
        "source_kind",
        "digest_scope",
        "content_encoding",
    }:
        raise ValueError("Parser cannot manufacture acquisition metadata")
    copied = deepcopy(receipt)
    copied.update(parser_fields)
    copied._acquisition = _fingerprint(copied._acquisition_fields())
    return copied


def seal_receipt(receipt, observations=None):
    """Seal an actual source parser's manifest before normalized ingress."""
    if not acquisition_is_intact(receipt) or receipt._sealed is not None:
        raise ValueError("Parser manifest requires an intact unsealed acquisition")
    if observations is not None:
        receipt["observations"] = deepcopy(observations)
    if not isinstance(receipt.get("observations"), list):
        raise ValueError("Source parser observation manifest is missing")
    receipt._sealed = _fingerprint(dict(receipt))
    return receipt


def receipt_is_sealed(receipt):
    try:
        return acquisition_is_intact(receipt) and receipt._sealed == _fingerprint(
            dict(receipt)
        )
    except (TypeError, ValueError, OverflowError):
        return False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def capture_response(
    response, store: ReceiptStore | None, *, source_kind="api", acquisition_kind=None
) -> dict:
    """Retain exact decoded response body bytes consumed by parsers.

    httpx decompresses transfer encoding; digest is explicitly over response.content,
    never a reserialized JSON value or normalized observation.
    """
    body = response.content
    digest = hashlib.sha256(body).hexdigest()
    acquired = now_iso()
    receipt = {
        "version": 1, "source_kind": source_kind,
        "request": {"method": response.request.method, "url": str(response.request.url)},
        "request_url": str(response.request.url), "parser_version": "unparsed-acquisition-v1",
        "response_url": str(response.url), "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "content_encoding": response.headers.get("content-encoding"),
        "digest_scope": "response.content", "acquired_at": acquired,
        "digest": digest, "byte_size": len(body), "storage_key": None,
        "storage_scope": "local", "byte_check": {"status": "missing", "sha256": None, "checked_at": acquired},
    }
    if acquisition_kind is not None:
        receipt.update(
            status=None,
            content_type=None,
            acquired_at=None,
            acquisition_kind=acquisition_kind,
        )
    try:
        if store is None:
            raise ValueError("receipt_store_unconfigured")
        key = store.put(body)
        retained = store.read(key)
        if key != digest or retained != body:
            raise ValueError("receipt_readback_mismatch")
        receipt["storage_key"] = key
        receipt["byte_check"] = {"status": "matched", "sha256": digest, "checked_at": now_iso()}
    except Exception as exc:  # Adapter failures retain the observation, with explicit missing-byte evidence.
        receipt["failure_reason"] = f"{type(exc).__name__}: {exc}"
        logger.error("Receipt bytes not retained; observations remain qualified, restart loses bytes: %s", exc)
    captured = CapturedReceipt(receipt, _capability=_CAPABILITY)
    captured._store = store
    return captured


def capture_local_bytes(body, store, *, url, claimed_receipt=None):
    """Read-back binds local PDF bytes; sidecar JSON never supplies HTTP authority."""
    import httpx

    response = httpx.Response(200, content=body, request=httpx.Request("GET", url))
    receipt = capture_response(
        response, store, source_kind="pdf", acquisition_kind="local_cached_bytes"
    )
    if isinstance(claimed_receipt, dict) and (
        claimed_receipt.get("digest") != receipt["digest"]
        or claimed_receipt.get("byte_size") != receipt["byte_size"]
    ):
        receipt["byte_check"]["status"] = "conflict"
        receipt["claimed_digest"] = claimed_receipt.get("digest")
        receipt._acquisition = _fingerprint(receipt._acquisition_fields())
    return receipt


def response_receipt(response, store, *, source_kind="api"):
    """Reuse only an intact capability bound to the actual parser input bytes."""
    recorded = response.extensions.get("response_receipt")
    if (
        acquisition_is_intact(recorded)
        and recorded.get("digest") == hashlib.sha256(response.content).hexdigest()
        and recorded.get("byte_size") == len(response.content)
    ):
        return copy_receipt(recorded, source_kind=source_kind)
    cached = response.extensions.get("seeding_cache")
    return capture_response(
        response,
        store,
        source_kind=source_kind,
        acquisition_kind="cached_response_without_acquisition_receipt"
        if cached
        else None,
    )


def persist_receipt(session, source_document, receipt: dict, *, extractor="http-response-v1", page_number=None):
    """Persist a response/PDF receipt once per acquisition, without source bytes."""
    if not receipt_is_sealed(receipt):
        raise ValueError(
            "Receipt persistence requires an intact captured parser manifest"
        )
    association = (
        source_document.id,
        source_document.country_id,
        source_document.publisher,
        source_document.url,
    )
    if receipt._bound_source and receipt._bound_source[0] != association:
        raise ValueError(
            "Captured receipt is already bound to a different source document"
        )
    cache = session.info.setdefault("response_receipt_extractions_v1", {})
    identity = (
        source_document.id,
        receipt["digest"],
        receipt["acquired_at"],
        extractor,
        receipt._sealed,
    )
    extraction = cache.get(identity)
    if extraction is None or extraction not in session:
        stored = deepcopy(dict(receipt))
        if stored.get("byte_check", {}).get("status") == "matched":
            try:
                body = receipt._store.read(receipt["storage_key"])
                if (
                    hashlib.sha256(body).hexdigest() != receipt["digest"]
                    or len(body) != receipt["byte_size"]
                ):
                    raise ValueError("receipt_readback_mismatch")
            except Exception as exc:
                # Ingestion validates retention again before the immutable DB
                # snapshot. This is once per acquisition, never per public read.
                stored["byte_check"] = {
                    "status": "missing",
                    "sha256": None,
                    "checked_at": now_iso(),
                }
                stored[
                    "failure_reason"
                ] = f"retention_check_failed: {type(exc).__name__}: {exc}"
                logger.error("Receipt retention failed before persistence: %s", exc)
        extraction = Extraction(
            source_document_id=source_document.id,
            page_number=page_number,
            extractor=extractor,
            extracted_json={"response_receipt": stored},
        )
        session.add(extraction)
        session.flush()
        cache[identity] = extraction
        if not receipt._bound_source:
            receipt._bound_source.append(association)
    return extraction


def persist_evidence(session, source_document, evidence: list[dict] | None) -> list[dict]:
    """One immutable Extraction per acquisition in this session, reused by rows.

    _response_receipt is an ingestion-only envelope, removed from each association.
    A database failure propagates to the caller's savepoint; no fabricated ID.
    """
    out = []
    for observation in evidence or []:
        item = dict(observation)
        receipt = item.pop("_response_receipt", None)
        association = (
            source_document.id,
            source_document.country_id,
            source_document.publisher,
            source_document.url,
        )
        if (
            not receipt_is_sealed(receipt)
            or receipt._bound_source
            and receipt._bound_source[0] != association
        ):
            # Keep a usable legacy observation, never an input-provided FK or
            # asserted acquisition. This also prevents replay of exported refs.
            item["receipt"] = {"extraction_id": None, "digest": None}
            item["checks"] = dict.fromkeys(
                ("identity", "value", "transport", "bytes", "locator"), False
            )
            item["reconciliation"] = {
                "status": "not_checked",
                "reason": "untrusted_or_changed_acquisition_envelope",
            }
            out.append(item)
            continue
        kind = receipt.get("source_kind")
        extraction = persist_receipt(session, source_document, receipt,
            extractor="pdf-receipt-v1" if kind == "pdf" else "http-response-v1",
            page_number=item.get("locator", {}).get("page") if kind == "pdf" else None)
        item["receipt"] = {"extraction_id": extraction.id, "digest": receipt["digest"],
                           "source_document_id": source_document.id}
        out.append(item)
    return out

"""Shared metadata-only acquisition persistence over the existing Extraction model."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from models import Extraction
from .receipt_store import ReceiptStore

logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def capture_response(response, store: ReceiptStore | None, *, source_kind="api") -> dict:
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
        "response_url": str(response.url), "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "content_encoding": response.headers.get("content-encoding"),
        "digest_scope": "response.content", "acquired_at": acquired,
        "digest": digest, "byte_size": len(body), "storage_key": None,
        "storage_scope": "local", "byte_check": {"status": "missing", "sha256": None, "checked_at": acquired},
    }
    try:
        if store is None:
            raise ValueError("receipt_store_unconfigured")
        key = store.put(body)
        retained = store.read(key)
        if key != digest or retained != body:
            raise ValueError("receipt_readback_mismatch")
        receipt["storage_key"] = key
        receipt["byte_check"] = {"status": "matched", "sha256": digest, "checked_at": now_iso()}
    except (OSError, ValueError) as exc:
        receipt["failure_reason"] = f"{type(exc).__name__}: {exc}"
        logger.error("Receipt bytes not retained; observations remain qualified, restart loses bytes: %s", exc)
    return receipt


def persist_receipt(session, source_document, receipt: dict, *, extractor="http-response-v1", page_number=None):
    """Persist a response/PDF receipt once per acquisition, without source bytes."""
    cache = session.info.setdefault("response_receipt_extractions_v1", {})
    identity = (source_document.id, receipt["digest"], receipt["acquired_at"], extractor)
    extraction = cache.get(identity)
    if extraction is None or extraction not in session:
        extraction = Extraction(source_document_id=source_document.id, page_number=page_number,
            extractor=extractor, extracted_json={"response_receipt": receipt})
        session.add(extraction)
        session.flush()
        cache[identity] = extraction
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
        if receipt is None:
            out.append(item)
            continue
        extraction = persist_receipt(session, source_document, receipt)
        item["receipt"] = {"extraction_id": extraction.id, "digest": receipt["digest"],
                           "source_document_id": source_document.id}
        out.append(item)
    return out

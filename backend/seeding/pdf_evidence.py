"""Prospective PDF cell evidence; cached bytes never invent an HTTP acquisition.

PDF hashes here identify source bytes, independently of normalized row hashes.
The selected receipt adapter retains bytes independently of download caches.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from pathlib import Path
import hashlib

from services.receipt_store import configured_receipt_store
from services.response_receipts import (
    persist_receipt,
    persist_evidence,
    response_receipt,
    acquisition_is_intact,
    receipt_is_sealed,
    copy_receipt,
    capture_local_bytes,
    seal_receipt,
)


class PdfCellEvidence(dict):
    """Ingestion-only parser envelope, never constructible by JSON input.

    The persisted public observation is an ordinary JSON object. Configured
    datasets cannot supply their own successful PDF acquisition attestations.
    """


def bind_parse_receipt(receipt, parsed_records):
    """Cached normalized cells stay usable but cannot seal a new source claim."""
    from .parse_cache import fresh_parse_matches

    if fresh_parse_matches(parsed_records, receipt.get("digest")):
        return receipt
    untrusted = deepcopy(dict(receipt))
    untrusted[
        "parser_result_origin"
    ] = "cached_or_unbound_parse_not_independently_checked"
    return untrusted


def receipt_for_response(client, response, parser_version: str) -> dict:
    """Preserve the original acquisition when GET returned cached bytes."""
    store = getattr(client, "receipt_store", None)
    if store is None and hasattr(client, "_settings"):
        store = configured_receipt_store(client._settings)
    receipt = response_receipt(response, store, source_kind="pdf")
    return copy_receipt(receipt, parser_version=parser_version)


def receipt_for_pdf(
    client, settings, path: Path, url: str, parser_version: str
) -> dict:
    from .pdf_download import cached_pdf_meta

    body = path.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    recorded = (
        client.download_receipt(url) if hasattr(client, "download_receipt") else None
    )
    claimed = cached_pdf_meta(path.parent, url).get("response_receipt")
    store = getattr(client, "receipt_store", None)
    if store is None and settings is not None:
        store = configured_receipt_store(settings)
    if (
        acquisition_is_intact(recorded)
        and recorded.get("digest") == digest
        and recorded.get("byte_size") == len(body)
    ):
        # Actual runtime download capability, independently associated with
        # the file parsed now. A serialized sidecar cannot enter this branch.
        receipt = copy_receipt(
            recorded, parser_version=parser_version, source_kind="pdf"
        )
        try:
            if store is None or store.read(receipt["storage_key"]) != body:
                raise ValueError("receipt_readback_mismatch")
        except (OSError, ValueError, TypeError, RuntimeError):
            return copy_receipt(
                capture_local_bytes(body, store, url=url), parser_version=parser_version
            )
        return receipt
    return copy_receipt(
        capture_local_bytes(
            body,
            store,
            url=url,
            claimed_receipt=recorded if isinstance(recorded, dict) else claimed,
        ),
        parser_version=parser_version,
    )


def cell_evidence(
    *,
    receipt: dict,
    identity: dict,
    raw_value,
    value,
    raw_unit: str,
    factor,
    locator: dict | None,
    identity_checked: bool = True,
    unit_checked: bool = True,
    rounding: int | None = None,
) -> dict:
    """Describe an actually parsed cell and check its explicit scale operation.

    Callers supply a locator only from the parser's source row, never from an
    amount search. Missing or ambiguous source cells remain qualified.
    """
    raw_unit_label = raw_unit
    raw_unit = {"KES million": "million_KES", "KES billion": "billion_KES"}.get(
        raw_unit, raw_unit
    )
    identity = deepcopy(identity)
    source_period = identity.get("period")
    if isinstance(source_period, str) and "/" in source_period:
        from .utils import normalize_fiscal_label

        identity["period"] = normalize_fiscal_label(source_period)
    try:
        raw, normalized, scale = map(
            lambda v: Decimal(str(v)), (raw_value, value, factor)
        )
        expected = raw * scale
        if rounding is not None:
            expected = expected.quantize(
                Decimal(1).scaleb(-rounding), rounding=ROUND_HALF_EVEN
            )
        value_checked = (
            all(v.is_finite() for v in (raw, normalized, scale))
            and scale > 0
            and expected == normalized
        )
    except (InvalidOperation, ValueError, TypeError):
        value_checked = False
    checked = receipt.get("byte_check", {})
    bytes_checked = checked.get("status") == "matched" and checked.get(
        "sha256"
    ) == receipt.get("digest")
    status = receipt.get("status")
    transport = (
        type(status) is int
        and 200 <= status < 300
        and str(receipt.get("content_type") or "").split(";")[0].strip().lower()
        == "application/pdf"
    )
    found = (
        isinstance(locator, dict)
        and type(locator.get("page")) is int
        and locator["page"] > 0
        and bool(locator.get("cell") or locator.get("text_span"))
    )
    return PdfCellEvidence(
        {
            "version": 1,
            "source_kind": "pdf",
            "identity": deepcopy(identity),
            "source_period": source_period,
            "raw_value": str(raw_value),
            "raw_unit": raw_unit,
            "raw_unit_label": raw_unit_label,
            "value": str(value),
            "unit": identity["unit"],
            "locator": deepcopy(locator) if locator else {},
            "transformation": {
                "operation": "identity" if str(factor) == "1" else "multiply",
                "factor": str(factor),
                "rounding": rounding,
                "rounding_mode": "ROUND_HALF_EVEN" if rounding is not None else None,
            },
            "checks": {
                "identity": identity_checked and unit_checked,
                "value": value_checked,
                "transport": transport,
                "bytes": bytes_checked,
                "locator": found,
            },
            "reconciliation": {
                "status": "matched" if value_checked else "conflict",
                "reason": "Parsed PDF cell scaled to stored amount"
                if value_checked
                else "Parsed PDF cell does not reproduce stored amount",
            },
            "_response_receipt": deepcopy(receipt),
        }
    )


def bind_pdf_evidence(
    session, source_document, evidence: list, *, identity: dict, values: dict
) -> list:
    """Bind real local Extraction IDs, refusing changed row identity or value."""
    from .utils import normalize_fiscal_label

    out = []
    for original in evidence:
        if not isinstance(original, PdfCellEvidence):
            untrusted = dict(original)
            untrusted.pop("_response_receipt", None)
            out.extend(persist_evidence(session, source_document, [untrusted]))
            continue
        observation = deepcopy(original)
        observed = observation.get("identity", {})
        receipt = observation["_response_receipt"]
        if not receipt_is_sealed(receipt):
            out.extend(persist_evidence(session, source_document, [observation]))
            continue
        manifest = receipt.get("observations", [])
        raw_agrees = any(
            all(
                entry.get(k) == observation.get(k)
                for k in (
                    "identity",
                    "locator",
                    "raw_value",
                    "raw_unit",
                    "transformation",
                )
            )
            for entry in manifest
            if isinstance(entry, dict)
        )
        if not raw_agrees:
            observation["checks"]["locator"] = False
            observation["reconciliation"] = {
                "status": "conflict" if manifest else "unverified",
                "reason": "PDF observation differs from parser manifest"
                if manifest
                else "PDF parser manifest missing",
            }
        expected = dict(identity, measure=observed.get("measure"))

        def canonical(field, value):
            if field == "period":
                return (
                    normalize_fiscal_label(value)
                    if isinstance(value, str) and "/" in value
                    else value
                )
            if field == "geography" and isinstance(value, str):
                return value.lower().removesuffix(" county").strip()
            return value

        matches = all(
            canonical(k, observed.get(k)) == canonical(k, v)
            for k, v in expected.items()
            if k != "entity_id"
        )
        matches = matches and observed.get("entity_id") in (
            None,
            expected.get("entity_id"),
        )
        if matches:
            observation["identity"] = expected
        else:
            observation["checks"]["identity"] = False
            observation["reconciliation"] = {
                "status": "conflict",
                "reason": "PDF identity differs from persisted row",
            }
        try:
            same_value = Decimal(str(values[observed["measure"]])) == Decimal(
                observation["value"]
            )
        except (KeyError, InvalidOperation, ValueError, TypeError):
            same_value = False
        if not same_value:
            observation["checks"]["value"] = False
            observation["reconciliation"] = {
                "status": "conflict",
                "reason": "PDF value differs from persisted row",
            }
        receipt = observation.pop("_response_receipt")
        extraction = persist_receipt(
            session, source_document, receipt, extractor="pdf-receipt-v1"
        )
        observation["receipt"] = {
            "extraction_id": extraction.id,
            "digest": receipt["digest"],
            "source_document_id": source_document.id,
        }
        out.append(observation)
    return out


def seal_pdf_observations(evidence: list) -> None:
    """Freeze the parser's raw-cell manifest before writers bind row identities."""
    manifests = {}
    for item in evidence:
        receipt = item["_response_receipt"]
        key = (receipt["digest"], receipt["acquired_at"])
        manifests.setdefault(key, []).append(
            {
                k: deepcopy(item[k])
                for k in (
                    "identity",
                    "locator",
                    "raw_value",
                    "raw_unit",
                    "transformation",
                )
            }
        )
    for item in evidence:
        receipt = item["_response_receipt"]
        receipt["observations"] = deepcopy(
            manifests[(receipt["digest"], receipt["acquired_at"])]
        )
        if acquisition_is_intact(receipt):
            seal_receipt(receipt)

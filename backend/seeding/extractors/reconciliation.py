"""Review boundary for changing OAG evidence already stored in the database.

Automatic runs may add findings or move page citations, but cannot revise
content or retire evidence. A review
is a source-checked proposal bound to the exact old rows, candidate and PDF.
It is never inferred from a count, a new extractor version, or a changed URL.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


class ReconciliationRequired(RuntimeError):
    def __init__(self, proposal):
        self.proposal = proposal
        super().__init__(
            f"document {proposal['document_id']}: reconciliation review required; "
            f"{len(proposal['retire_ids'])} retirements, "
            f"{len(proposal['update_ids'])} revisions; published evidence preserved"
        )


class IncompleteExtraction(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def _row(row):
    return {
        "payload": row.extracted_json,
        "page": row.page_number,
        "confidence": float(row.confidence) if row.confidence is not None else None,
    }


def row_changed(old, new):
    return _row(old) != _row(new)


def validate_candidates(doc, extractor_id, rows, key):
    seen = set()
    for row in rows:
        payload = row.extracted_json
        if row.source_document_id != doc.id or row.extractor != extractor_id:
            raise IncompleteExtraction(
                "candidate belongs to another source or extractor"
            )
        if not isinstance(payload, dict):
            raise IncompleteExtraction("candidate payload is not an object")
        for name in ("title", "finding_text", "entity_name", "fiscal_year"):
            if not isinstance(payload.get(name), str) or not payload[name].strip():
                raise IncompleteExtraction(f"candidate lacks {name}")
        schemas = {
            "oag_blue_book": "oag_blue_book/v1",
            "oag_county_volume": "oag_county_volume/v1",
        }
        if (
            extractor_id not in schemas
            or payload.get("schema") != schemas[extractor_id]
        ):
            raise IncompleteExtraction("candidate schema does not match extractor")
        if extractor_id == "oag_county_volume":
            if payload.get("volume_kind") not in ("executives", "assemblies"):
                raise IncompleteExtraction("county candidate lacks a valid volume kind")
            if (
                not isinstance(payload.get("county_name"), str)
                or not payload["county_name"].strip()
            ):
                raise IncompleteExtraction(
                    "county candidate lacks an attributed county"
                )
        for value in (
            row.page_number,
            payload.get("paragraph_no"),
            payload.get("vote")
            if extractor_id == "oag_blue_book"
            else payload.get("chapter_no"),
        ):
            if type(value) is not int or value <= 0:
                raise IncompleteExtraction("candidate has an invalid page or identity")
        if (
            type(payload.get("pdf_page")) is not int
            or payload["pdf_page"] != row.page_number
        ):
            raise IncompleteExtraction("candidate page disagrees with its citation")
        if row.confidence is not None and (
            isinstance(row.confidence, bool)
            or not math.isfinite(float(row.confidence))
            or not 0 <= float(row.confidence) <= 1
        ):
            raise IncompleteExtraction("candidate confidence is invalid")
        amounts = payload.get("amounts")
        if not isinstance(amounts, list) or any(
            type(n) not in (int, float) or not math.isfinite(n) or n < 0
            for n in amounts
        ):
            raise IncompleteExtraction(
                "candidate amounts must be finite, nonnegative numbers"
            )
        identity = key(payload)
        if identity in seen:
            raise IncompleteExtraction("duplicate candidate identity")
        seen.add(identity)
        _digest(_row(row))  # Reject non-JSON and non-finite values throughout.


def _meaning(row):
    # Page movements in a complete reissue do not change a finding's content.
    # Keep amount, attribution, fiscal period, text, opinion and confidence in
    # this comparison: a count or an apparently complete PDF cannot verify them.
    value = _row(row)
    return {
        **value,
        "page": None,
        "payload": {
            k: v
            for k, v in value["payload"].items()
            if k not in ("pdf_page", "printed_page")
        },
    }


def require_review(session, doc, extractor_id, old, rows, matched, vanished, review):
    from models import Audit

    changed = [row.id for row, new in matched if _meaning(row) != _meaning(new)]
    if not vanished and not changed:
        if not rows:
            raise IncompleteExtraction("no findings extracted")
        return
    if not doc.md5 or not doc.file_path or not Path(doc.file_path).is_file():
        raise IncompleteExtraction("reconciliation requires the exact source file")
    with Path(doc.file_path).open("rb") as source:
        source_sha256 = hashlib.file_digest(source, "sha256").hexdigest()
    audit_ids = []
    for offset in range(0, len(old), 500):
        audit_ids.extend(
            a.id
            for a in session.query(Audit).filter(
                Audit.extraction_id.in_([r.id for r in old[offset : offset + 500]])
            )
        )
    audit_ids.sort()
    proposal = {
        "document_id": doc.id,
        "extractor": extractor_id,
        "source_md5": doc.md5,
        "source_sha256": source_sha256,
        "previous_sha256": _digest([{"id": r.id, **_row(r)} for r in old]),
        "candidate_sha256": _digest([_row(r) for r in rows]),
        "previous_count": len(old),
        "candidate_count": len(rows),
        "retire_ids": [r.id for r in vanished],
        "update_ids": changed,
        "audit_ids": audit_ids,
        "source_url": doc.url,
        "retired_rows": [{"id": r.id, **_row(r)} for r in vanished],
        "revised_rows": [
            {"id": r.id, "before": _row(r), "after": _row(new)}
            for r, new in matched
            if r.id in changed
        ],
    }
    if (
        not isinstance(review, dict)
        or review.get("proposal") != proposal
        or review.get("source_complete") is not True
        or not isinstance(review.get("reason"), str)
        or not review["reason"].strip()
    ):
        raise ReconciliationRequired(proposal)
    from datetime import datetime, timezone

    doc.meta = {
        **(doc.meta if isinstance(doc.meta, dict) else {}),
        "last_reconciliation_review": {
            **review,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def extract_and_load(session, doc, settings, context, parser, loader):
    """One source is one transaction: a loader failure cannot bank a replacement."""
    with session.begin_nested():
        stats = parser(session, doc, settings)
        fresh = stats.pop("fresh_extraction_ids", None) or ()
        loaded = loader(session, doc, settings, context, fresh_extraction_ids=fresh)
        if loaded.errors:
            raise IncompleteExtraction(f"loading document {doc.id}: {loaded.errors}")
        doc.meta = {
            **(doc.meta if isinstance(doc.meta, dict) else {}),
            "last_extraction_attempt": {
                "status": "partial" if stats.get("partial") else "complete"
            },
        }
        session.flush()
        return stats, loaded


def record_failed_attempt(doc, exc):
    """Call after rollback so the failure is visible without marking bytes current."""
    from datetime import datetime, timezone

    attempt = {
        "status": "partial",
        "attempted_at": datetime.now(timezone.utc).isoformat(),
        "error": f"{type(exc).__name__}: {exc}",
        "source_md5": doc.md5,
    }
    if doc.file_path and Path(doc.file_path).is_file():
        with Path(doc.file_path).open("rb") as source:
            attempt["source_sha256"] = hashlib.file_digest(source, "sha256").hexdigest()
    if isinstance(exc, ReconciliationRequired):
        attempt["proposal"] = exc.proposal
    doc.meta = {
        **(doc.meta if isinstance(doc.meta, dict) else {}),
        "last_extraction_attempt": attempt,
    }
    return attempt

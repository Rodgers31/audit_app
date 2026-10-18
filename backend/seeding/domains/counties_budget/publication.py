"""Explicit publisher date from retained PDF bytes; no JSON self-attestation.

Only full calendar dates following a publisher publication label on the first
three pages are supported. Report periods, month-only dates, upload metadata,
PDF creation dates and retrieval timestamps never establish publication dates.
"""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from services.response_receipts import acquisition_is_intact, copy_receipt, receipt_is_sealed, seal_receipt, persist_receipt

_AUTHORITY = object()
_LABEL = re.compile(r"^(?:Publication date|Published on):[ \t]*(.+?)[ \t]*$", re.IGNORECASE)
_MONTHS = {name.lower(): i for i, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class PublicationDateEvidence:
    """Runtime-only, mutation-detecting authority; serialization loses admission."""
    def __init__(self, value, receipt, *, _authority=None):
        if _authority is not _AUTHORITY:
            raise TypeError("Publication dates require actual retained PDF parsing")
        self.value, self.receipt = deepcopy(value), deepcopy(receipt)
        self._snapshot = _hash(self.value)

    def __deepcopy__(self, memo):
        copied = PublicationDateEvidence(self.value, self.receipt, _authority=_AUTHORITY)
        copied._snapshot = self._snapshot
        memo[id(self)] = copied
        return copied

    def __reduce_ex__(self, protocol):
        return dict, (self.value,)


def _full_date(raw):
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw):
        return date.fromisoformat(raw)
    match = re.fullmatch(r"([0-9]{1,2}) ([A-Za-z]+) ([0-9]{4})", raw)
    if match and match[2].lower() in _MONTHS:
        return date(int(match[3]), _MONTHS[match[2].lower()], int(match[1]))
    raise ValueError("Explicit full publisher publication date unavailable")


def capture_publication_date(path: Path, receipt):
    """Read actual PDF text under an intact fresh financial-parser acquisition.

    Failure returns an explicit unavailable reason, never a guessed date.
    Retention/DB failures during later binding propagate and roll back ingestion.
    """
    if not acquisition_is_intact(receipt) or receipt.get("parser_result_origin"):
        return None, "publication_acquisition_unavailable"
    try:
        url = urlsplit(receipt["request_url"])
        if (url.scheme != "https" or url.hostname not in ("cob.go.ke", "www.cob.go.ke")
                or url.username or url.password or url.port not in (None, 443)
                or receipt.get("status") != 200 or type(receipt.get("status")) is not int
                or str(receipt.get("content_type", "")).split(";")[0].strip().lower() != "application/pdf"):
            return None, "publication_official_pdf_required"
        size = receipt.get("byte_size")
        if type(size) is not int or not 0 < size <= 64 * 1024 * 1024 or path.stat().st_size != size:
            return None, "publication_retained_bytes_mismatch"
        body = path.read_bytes()
        if (hashlib.sha256(body).hexdigest() != receipt.get("digest")
                or len(body) != receipt.get("byte_size")
                or receipt.get("byte_check", {}).get("status") != "matched"
                or receipt._store.read(receipt["storage_key"]) != body):
            return None, "publication_retained_bytes_mismatch"
        import pdfplumber
        candidates = []
        with pdfplumber.open(path, pages=[1, 2, 3]) as pdf:
            for page in pdf.pages:
                try:
                    text = page.extract_text() or ""
                    if len(text) > 100000:
                        return None, "publication_page_text_limit"
                    for line in text.splitlines():
                        match = _LABEL.fullmatch(line.strip())
                        if match:
                            candidates.append((_full_date(match[1]), page.page_number, line.strip()))
                finally:
                    page.close()
        if len(candidates) != 1:
            return None, "publication_date_missing_or_ambiguous"
        published, page, span = candidates[0]
        acquired = datetime.fromisoformat(receipt["acquired_at"])
        if acquired.tzinfo is None or published > acquired.date():
            return None, "publication_date_chronology_invalid"
        if hashlib.sha256(path.read_bytes()).hexdigest() != receipt["digest"]:
            return None, "publication_source_changed_during_parse"
        value = {"version": 1, "publication_date": published.isoformat(), "digest": receipt["digest"],
                 "request_url": receipt["request_url"], "locator": {"page": page, "text_span": span}}
        captured = copy_receipt(receipt, parser_version="cob-publication-date-v1")
        seal_receipt(captured, [value])
        return PublicationDateEvidence(value, captured, _authority=_AUTHORITY), None
    except (ValueError, TypeError, KeyError, OSError, AttributeError):
        return None, "publication_date_evidence_invalid"


def bind_publication_date(session, source, evidence, *, digest):
    """Bind only the actual parser capability to its unchanged retained receipt."""
    if (not isinstance(evidence, PublicationDateEvidence) or evidence._snapshot != _hash(evidence.value)
            or not receipt_is_sealed(evidence.receipt) or evidence.receipt.get("observations") != [evidence.value]
            or evidence.value.get("digest") != digest or evidence.value.get("request_url") != source.url):
        return None, "publication_parser_authority_unavailable"
    extraction = persist_receipt(session, source, evidence.receipt,
        extractor="cob-publication-date-v1", page_number=evidence.value["locator"]["page"])
    stored = extraction.extracted_json["response_receipt"]
    if stored.get("byte_check", {}).get("status") != "matched":
        return None, "publication_retained_bytes_unavailable"
    return {**deepcopy(evidence.value), "extraction_id": extraction.id}, None

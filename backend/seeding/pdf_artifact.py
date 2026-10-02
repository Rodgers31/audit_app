"""PDF-byte identity, independent of canonical extraction-JSON hashes.

Versioned metadata is additive. Legacy rows have no binding; the loader must
never synthesize one from the latest document row. No filesystem path is stored
in an identity or exported by the historical projection.
"""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ARTIFACT_KEY = "pdf_artifact_v1"
BINDING_KEY = "pdf_artifact_binding_v1"
_ARTIFACT_FIELDS = {
    "schema_version",
    "sha256",
    "md5",
    "size_bytes",
    "source_document_id",
    "source_url",
    "report_title",
    "publisher",
    "validation",
    "verification_time",
    "verification_time_reason",
}


def file_identity(path: Path) -> dict:
    """Hash actual bytes after the existing fetcher's PDF validation."""
    from .pdf_download import _verify_pdf_magic, _verify_pdf_complete

    _verify_pdf_magic(path, "local artifact")
    _verify_pdf_complete(path, "local artifact")
    sha, md5 = hashlib.sha256(), hashlib.md5()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    return {"sha256": sha.hexdigest(), "md5": md5.hexdigest(), "size_bytes": size}


def safe_public_url(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value)
        return bool(
            url.scheme in ("http", "https")
            and url.hostname
            and url.username is None
            and url.password is None
            and not any(
                re.search(
                    r"token|password|secret|signature|credential|api.?key|authorization",
                    key,
                    re.I,
                )
                for key, _ in parse_qsl(url.query)
            )
        )
    except ValueError:
        return False


def valid_artifact(value) -> bool:
    if not isinstance(value, dict) or set(value) != _ARTIFACT_FIELDS:
        return False
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        return False
    for key, length in (("sha256", 64), ("md5", 32)):
        if (
            not isinstance(value[key], str)
            or re.fullmatch("[0-9a-f]{%d}" % length, value[key]) is None
        ):
            return False
    if any(
        type(value[k]) is not int or value[k] <= 0
        for k in ("size_bytes", "source_document_id")
    ):
        return False
    if not safe_public_url(value["source_url"]):
        return False
    if any(
        not isinstance(value[k], str) or not value[k].strip()
        for k in ("report_title", "publisher")
    ):
        return False
    if value["validation"] != "pdf_magic_and_final_eof":
        return False
    timestamp, reason = value["verification_time"], value["verification_time_reason"]
    if timestamp is None:
        return reason == "download_time_not_available"
    if not isinstance(timestamp, str) or reason is not None:
        return False
    try:
        return datetime.fromisoformat(timestamp).tzinfo is not None
    except ValueError:
        return False


def artifact_for_document(doc):
    meta = doc.meta if isinstance(doc.meta, dict) else {}
    return meta.get(ARTIFACT_KEY)


def artifact_matches_document(artifact, doc) -> bool:
    return bool(
        valid_artifact(artifact)
        and doc is not None
        and artifact["source_document_id"] == doc.id
        and artifact["source_url"] == doc.url
        and artifact["report_title"] == doc.title
        and artifact["publisher"] == doc.publisher
        and artifact["md5"] == doc.md5
    )


def extraction_artifact(doc):
    """Snapshot only a fetched identity whose bytes still match at read time.

    Missing identity is legacy absence. A present but inconsistent identity is
    a failed boundary, not a reason to extract with an invented current hash.
    """
    from .extractors.reconciliation import IncompleteExtraction

    meta = doc.meta if isinstance(doc.meta, dict) else {}
    if ARTIFACT_KEY not in meta:
        return None
    identity = meta[ARTIFACT_KEY]
    if not artifact_matches_document(identity, doc):
        raise IncompleteExtraction("invalid PDF artifact/document association")
    actual = file_identity(Path(doc.file_path))
    if any(identity[k] != actual[k] for k in actual):
        raise IncompleteExtraction("PDF bytes changed since fetch")
    return copy.deepcopy(identity)


def valid_binding(binding) -> bool:
    return bool(
        isinstance(binding, dict)
        and set(binding)
        == {"schema_version", "artifact", "extractor", "text_visibility", "pdf_pages"}
        and type(binding["schema_version"]) is int
        and binding["schema_version"] == 1
        and valid_artifact(binding["artifact"])
        and binding["extractor"] == "oag_county_volume"
        and binding["text_visibility"] == "visible_only"
        and type(binding["pdf_pages"]) is int
        and binding["pdf_pages"] > 0
    )

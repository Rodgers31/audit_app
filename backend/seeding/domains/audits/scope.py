"""Opt-in execution boundary for the five retained county audit editions.

The pinned readiness packet is source evidence, never production authorization.
Accepting its exact bytes avoids treating an arbitrary URL list as reviewed scope.
Changes to that packet require a new code/source review, not an operator bypass.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ... import pdf_artifact
from ...oag_discovery import CountyAuditDiscovery, OagDocument

MANIFEST_SHA256 = "9388815ee8233d727558a2b47aef6bf3c4c6b6f1565dac22a4c8c10bbe9b6277"
MAX_MANIFEST_BYTES = 128 * 1024


class AuditSourceScopeError(ValueError):
    """Refuse source-scope drift before offering further work."""


def read_manifest(path: Path) -> bytes:
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_MANIFEST_BYTES + 1)
    except OSError as exc:
        raise AuditSourceScopeError("audit source manifest is unreadable") from exc
    parse_manifest(raw)
    return raw


def parse_manifest(raw):
    if raw is None:
        return None
    if (
        type(raw) is not bytes
        or not raw
        or len(raw) > MAX_MANIFEST_BYTES
        or hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256
    ):
        raise AuditSourceScopeError(
            "audit source manifest is not the reviewed five-edition packet"
        )
    data = json.loads(raw)
    entries = data["deferred_sources"]
    if data["schema"] != "round11_oag_catchup_readiness/v1" or len(entries) != 5:
        raise AuditSourceScopeError(
            "audit source manifest schema or source count changed"
        )
    return entries


def discovery_for(entries):
    # Retain FY/institution/listing context the registered parser needs, without
    # presenting this retained association as a current publisher observation.
    return CountyAuditDiscovery(
        documents=[
            OagDocument(
                url=e["source_url"],
                fiscal_year=e["fiscal_year"],
                kind=e["institution"],
                found_on="year_page",
                listed_at=e["listed_at"],
            )
            for e in entries
        ]
    )


def receipt_for(entries):
    return {
        "manifest_sha256": MANIFEST_SHA256,
        "inventory_basis": "reviewed_retained_manifest_not_live_discovery",
        "whole_world_coverage": False,
        "selected": [
            {
                k: e[k]
                for k in ("source_url", "fiscal_year", "institution", "sha256", "md5")
            }
            for e in entries
        ],
        "attempted": [],
        "deferred": [],
        "refused": [],
        "processed": [],
        "already_current": [],
    }


def verify_registered(session, entries, *, country_id, publisher, doc_type):
    from models import Country, SourceDocument
    from sqlalchemy import select

    country = session.get(Country, country_id)
    if country is None or country.iso_code != "KEN":
        raise AuditSourceScopeError(
            "selected sources require the Kenya country identity"
        )
    expected = {e["source_url"]: e for e in entries}
    # Read only the selected records: malformed unrelated rows cannot enlarge
    # scope or force the bounded path to consume the broader registered queue.
    rows = session.execute(
        select(SourceDocument).where(SourceDocument.url.in_(expected))
    ).scalars()
    for doc in rows:
        e = expected[doc.url]
        if (
            doc.country_id != country_id
            or doc.publisher != publisher
            or doc.doc_type != doc_type
            or doc.meta is not None
            and not isinstance(doc.meta, dict)
            or doc.md5 is not None
            and doc.md5 != e["md5"]
        ):
            raise AuditSourceScopeError(
                f"registered source identity changed: {e['label']}"
            )
        meta = doc.meta or {}
        facts = meta.get("oag_discovery")
        if facts is not None and (
            not isinstance(facts, dict)
            or any(
                facts.get(k) != value
                for k, value in (
                    ("fiscal_year", e["fiscal_year"]),
                    ("kind", e["institution"]),
                    ("listed_at", e["listed_at"]),
                )
            )
        ):
            raise AuditSourceScopeError(
                f"registered source edition changed: {e['label']}"
            )
        if pdf_artifact.ARTIFACT_KEY in meta:
            artifact = meta[pdf_artifact.ARTIFACT_KEY]
            if (
                not pdf_artifact.artifact_matches_document(artifact, doc)
                or artifact["sha256"] != e["sha256"]
            ):
                raise AuditSourceScopeError(
                    f"registered artifact changed: {e['label']}"
                )


def verify_fetched(doc, entry, *, country_id, publisher, doc_type):
    if (
        doc.url != entry["source_url"]
        or doc.country_id != country_id
        or doc.publisher != publisher
        or doc.doc_type != doc_type
        or doc.md5 != entry["md5"]
    ):
        raise AuditSourceScopeError(
            f"fetched source identity changed: {entry['label']}"
        )
    try:
        actual = pdf_artifact.file_identity(Path(doc.file_path))
    except (OSError, TypeError, ValueError) as exc:
        raise AuditSourceScopeError(
            f"fetched PDF unavailable or invalid: {entry['label']}"
        ) from exc
    if any(actual[k] != entry[k] for k in ("sha256", "md5")):
        raise AuditSourceScopeError(f"fetched PDF edition changed: {entry['label']}")


def verify_extractions(session, doc, entry, stats):
    if (
        not isinstance(stats, dict)
        or any(
            type(stats.get(k, 0)) is not int or stats.get(k, 0) < 0
            for k in ("created", "skipped")
        )
        or stats.get("created", 0) + stats.get("skipped", 0) <= 0
        or "partial" in stats
        and type(stats["partial"]) is not bool
        or stats.get("partial")
    ):
        raise AuditSourceScopeError(
            f"invalid or partial extraction outcome: {entry['label']}"
        )
    verify_extraction_evidence(session, doc, entry)


def verify_extraction_evidence(session, doc, entry):
    from models import Extraction
    from sqlalchemy import select, func

    # Project guard fields only; do not transfer every full finding a second
    # time on a cached turn merely to validate edition and artifact association.
    payload = Extraction.extracted_json
    present = (
        payload.has_key(pdf_artifact.BINDING_KEY)
        if session.get_bind().dialect.name == "postgresql"
        else func.json_type(payload, "$." + pdf_artifact.BINDING_KEY).isnot(None)
    )
    rows = session.execute(
        select(
            present,
            Extraction.extractor,
            payload["schema"],
            payload["fiscal_year"],
            payload["volume_kind"],
            payload[pdf_artifact.BINDING_KEY],
        ).where(Extraction.source_document_id == doc.id)
    ).all()
    if not rows:
        raise AuditSourceScopeError(f"extraction evidence missing: {entry['label']}")
    for has_binding, extractor, schema, fiscal_year, kind, binding in rows:
        if (
            extractor != "oag_county_volume"
            or schema != "oag_county_volume/v1"
            or fiscal_year != entry["fiscal_year"]
            or kind != entry["institution"]
        ):
            raise AuditSourceScopeError(
                f"extraction schema/edition/evidence changed: {entry['label']}"
            )
        # Legacy absence stays absence. A present malformed binding is never
        # certified by the document's latest hash or the caller's stats.
        if has_binding and (
            not pdf_artifact.valid_binding(binding)
            or not pdf_artifact.artifact_matches_document(binding["artifact"], doc)
            or binding["artifact"]["sha256"] != entry["sha256"]
            or binding["pdf_pages"] != entry["pdf_pages"]
        ):
            raise AuditSourceScopeError(
                f"extraction artifact evidence changed: {entry['label']}"
            )

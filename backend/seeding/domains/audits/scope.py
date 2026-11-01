"""Opt-in execution boundary for exact reviewed county audit packets.

The pinned readiness packet is source evidence, never production authorization.
Accepting its exact bytes avoids treating an arbitrary URL list as reviewed scope.
Changes to that packet require a new code/source review, not an operator bypass.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from ... import pdf_artifact
from ...oag_discovery import CountyAuditDiscovery, OagDocument

MANIFEST_SHA256 = "9388815ee8233d727558a2b47aef6bf3c4c6b6f1565dac22a4c8c10bbe9b6277"
CATALOGUE_MANIFEST_SHA256 = "dfcdf69d76f5f2b9d837b22cb711cbad155747fa217871c9443fcecb21af5489"
PACKETS = {
    MANIFEST_SHA256: ('round11_oag_catchup_readiness/v1', 5),
    CATALOGUE_MANIFEST_SHA256: ('source802_oag_catalogue_acceptance/v1', 4),
}
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
        or hashlib.sha256(raw).hexdigest() not in PACKETS
    ):
        raise AuditSourceScopeError(
            "audit source manifest is not a reviewed exact-edition packet"
        )
    data = json.loads(raw)
    entries = data["deferred_sources"]
    schema, count = PACKETS[hashlib.sha256(raw).hexdigest()]
    if data["schema"] != schema or len(entries) != count:
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


def receipt_for(entries, *, raw=None):
    if type(entries) is not list or not entries or any(type(e) is not dict for e in entries):
        raise AuditSourceScopeError('concrete nonempty reviewed source entries required')
    keys = ('source_url', 'fiscal_year', 'institution', 'sha256', 'md5')
    if raw is None:
        # The adopted-volume observation has only the packaged legacy edition
        # inventory. Preserve that caller, but never label another selection
        # with the original five-edition manifest's provenance.
        from .observation import accepted_editions
        legacy = list(accepted_editions().values())[3:]
        try:
            if [{k: e[k] for k in keys} for e in entries] != [{k: e[k] for k in keys} for e in legacy]:
                raise ValueError('changed legacy entries')
        except (KeyError, TypeError, ValueError):
            raise AuditSourceScopeError('exact reviewed manifest bytes required for source receipt') from None
        digest = MANIFEST_SHA256
    else:
        if parse_manifest(raw) != entries:
            raise AuditSourceScopeError('source receipt does not match reviewed entries')
        digest = hashlib.sha256(raw).hexdigest()
    return {
        "manifest_sha256": digest,
        "inventory_basis": "reviewed_retained_manifest_not_live_discovery",
        "whole_world_coverage": False,
        "selected": [
            {
                k: e[k]
                for k in keys
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

    # Acquisitions and report authority are metadata, not findings. Canonical
    # historical local-byte refusals also remain metadata; this classifier
    # grants no transport, date or native report authority to any receipt.
    auxiliary = ('native-report-authority-v1', 'pdf-receipt-v1')
    payload = Extraction.extracted_json
    receipt = payload['response_receipt']
    postgres = session.get_bind().dialect.name == 'postgresql'
    wrapper = (
        (func.jsonb_typeof(payload) == 'object')
        & (payload.op('-')('response_receipt') == {})
        & (func.jsonb_typeof(receipt) == 'object')
        if postgres else
        (func.json_type(payload) == 'object')
        & (func.json_remove(payload, '$.response_receipt') == '{}')
        & (func.json_type(payload, '$.response_receipt') == 'object')
    )
    metadata = session.execute(select(
        wrapper, Extraction.extractor, receipt['version'], receipt['source_kind'],
        receipt['parser_version'], receipt['request']['method'],
        receipt['request']['url'], receipt['request_url'], receipt['response_url'],
        receipt['digest'], receipt['byte_size'], receipt['storage_key'],
        receipt['byte_check']['status'], receipt['byte_check']['sha256'],
        (func.jsonb_typeof(receipt['version']) if postgres else func.json_type(payload, '$.response_receipt.version')),
        (func.jsonb_typeof(receipt['byte_size']) if postgres else func.json_type(payload, '$.response_receipt.byte_size')),
    ).where(Extraction.source_document_id == doc.id,
            Extraction.extractor.in_(auxiliary)).limit(1001)).all()
    if len(metadata) > 1000:
        raise AuditSourceScopeError(f'auxiliary receipt inventory exceeds review bound: {entry["label"]}')
    for (shape, extractor, version, source_kind, parser, method, request_url,
         requested, response_url, digest, size, key, byte_status, byte_digest, version_type, size_type) in metadata:
        parsers = (('native-report-authority-v1',) if extractor == 'native-report-authority-v1'
                   else ('native-report-input-v1', 'native-report-authority-v1'))
        if (shape is not True or type(version) is not int or version != 1
                or version_type != ('number' if postgres else 'integer')
                or source_kind != 'pdf' or parser not in parsers or method != 'GET'
                or request_url != doc.url or requested != doc.url
                or type(response_url) is not str or not response_url
                or type(digest) is not str or re.fullmatch('[a-f0-9]{64}', digest) is None
                or type(size) is not int or size <= 0
                or size_type != ('number' if postgres else 'integer')
                or key is not None and key != digest
                or byte_status not in ('matched', 'missing', 'conflict')
                or byte_status == 'matched' and (key != digest or byte_digest != digest)):
            raise AuditSourceScopeError(f'auxiliary receipt schema/source changed: {entry["label"]}')

    # Project guard fields only; do not transfer every full finding a second
    # time on a cached turn merely to validate edition and artifact association.
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
        ).where(Extraction.source_document_id == doc.id,
                Extraction.extractor.notin_(auxiliary))
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

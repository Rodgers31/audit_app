"""Qualified publisher listing plus read-only adopted-volume observations.

Only HTML is fetched here. PDF authority is the reviewed retained edition and
actual local bytes; this never claims a fresh download or registers a source.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from ... import oag_discovery as od, pdf_artifact
from .scope import AuditSourceScopeError, verify_extraction_evidence

ACCEPTED_SHA256 = "62f26e0d93c8a3a25e1f2ae813c362aa0e10908e0ffff33fd496342674cf1dab"
MAX_OBSERVATION_AGE_SECONDS = 86400


def accepted_editions():
    # Ship the unchanged hash-pinned authority with the backend package.
    path = Path(__file__).with_name("accepted-source-manifest.json")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ACCEPTED_SHA256:
        raise AuditSourceScopeError("retained county edition authority changed")
    return {
        e["url"]: {
            **e,
            "source_url": e["url"],
            "pdf_pages": e["pages"],
            "label": f"{e['fiscal_year']} {e['institution']}",
        }
        for e in json.loads(raw)
    }


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False
        ).encode()
    ).hexdigest()


def _require_reviewed_inventory(inventory):
    expected = {
        (edition["fiscal_year"], edition["url"])
        for edition in accepted_editions().values()
    }
    if not expected.issubset(set(inventory)):
        raise AuditSourceScopeError(
            "publisher no longer lists every reviewed county edition"
        )


def observe_listing(client):
    """Read the parent and every in-window year page with HTTP caching disabled.

    The publisher's qualified year pages define this inventory. Individual PDFs
    and the supplementary document sitemap are outside this observational pass.
    The ordinary scheduled discovery retains its existing sitemap behavior.
    """
    discovery = od.CountyAuditDiscovery()
    receipt = {
        "schema": "oag_county_observation/v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "inventory_basis": "live_publisher_year_pages",
        "whole_world_coverage": False,
        "byte_authority": "reviewed_retained_editions_not_fresh_pdf_downloads",
        "accepted_manifest_sha256": ACCEPTED_SHA256,
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "pages": [],
        "adopted": [],
    }

    def read(url):
        response = client.get(url, raise_for_status=True)
        # Reject redirects to another page/host and non-HTML WAF responses.
        if (
            str(response.url) != url
            or response.status_code != 200
            or "text/html" not in response.headers.get("content-type", "").lower()
        ):
            raise AuditSourceScopeError(
                "publisher listing response identity/type changed"
            )
        receipt["pages"].append(
            {
                "url": url,
                "sha256": hashlib.sha256(response.content).hexdigest(),
                "size_bytes": len(response.content),
            }
        )
        return response.text

    try:
        pages = od.parse_listing(read(od.LISTING_URL))
        if not pages:
            raise AuditSourceScopeError("publisher listing linked no fiscal years")
        discovery.year_pages = pages
        discovery.listing_fiscal_years = [p.fiscal_year for p in pages]
        docs = []
        for page in pages:
            if page.fiscal_year < od.FIRST_INGESTED_FISCAL_YEAR:
                continue
            found, conflicts = od.parse_year_page(read(page.url), page)
            if not found:
                discovery.errors.append(f"year page {page.fiscal_year} linked no PDF")
            discovery.errors.extend(conflicts)
            docs.extend(found)
        # Cross-year duplicate URLs and conflicting filename spans cannot certify.
        if len({d.url for d in docs}) != len(docs):
            discovery.errors.append("publisher repeats a PDF across year pages")
        discovery.documents = docs
        labels = {(d.fiscal_year, d.kind) for d in discovery.volumes()}
        for page in pages:
            if page.fiscal_year >= od.FIRST_INGESTED_FISCAL_YEAR:
                for kind in od.VOLUME_KINDS:
                    if (page.fiscal_year, kind) not in labels:
                        discovery.errors.append(
                            f"no discovered {page.fiscal_year} {kind} volume"
                        )
        _require_reviewed_inventory(
            (document.fiscal_year, document.url) for document in discovery.volumes()
        )
    except Exception as exc:
        discovery.errors.append(
            f"listing observation refused: {type(exc).__name__}: {str(exc)[:180]}"
        )
    receipt["discovery"] = discovery.as_meta()
    return discovery, receipt


def verify_adopted_volume(session, volume):
    """Verify bytes, edition, complete extraction and its actual adopted rows.

    Read-only even when unselected rows are malformed. Legacy binding absence
    stays absence and requires the existing extracted-MD5/complete-parser proof.
    """
    from models import (
        Audit,
        Country,
        DocumentStatus,
        DocumentType,
        Entity,
        EntityType,
        Extraction,
        FiscalPeriod,
        SourceDocument,
    )
    from ...extractors.oag_blue_book import source_hash_of
    from ...extractors.oag_county_audit import _known_counties
    from ...extractors.oag_county_volume import canonical_county, county_from_auditee
    from services.audit_citations import audited_institution, page_number

    entry = accepted_editions().get(volume.url)
    if (
        entry is None
        or (volume.fiscal_year, volume.kind)
        != (entry["fiscal_year"], entry["institution"])
        or volume.listed_at
        != f"{od.OAG_ORIGIN}/{volume.fiscal_year.replace('/', '-')}-county-government-audit-reports/"
    ):
        raise AuditSourceScopeError("unreviewed publisher edition")
    doc = session.execute(
        select(SourceDocument).where(SourceDocument.url == volume.url)
    ).scalar_one_or_none()
    country = session.get(Country, doc.country_id) if doc else None
    if (
        doc is None
        or country is None
        or country.iso_code != "KEN"
        or doc.publisher != "Office of the Auditor-General"
        or doc.doc_type != DocumentType.AUDIT
        or doc.status != DocumentStatus.AVAILABLE
        or doc.md5 != entry["md5"]
        or not isinstance(doc.meta, dict)
    ):
        raise AuditSourceScopeError("adopted source identity/status unavailable")
    facts, stats = doc.meta.get("oag_discovery"), doc.meta.get("extraction_stats")
    if (
        not isinstance(facts, dict)
        or any(
            facts.get(k) != v
            for k, v in (
                ("fiscal_year", volume.fiscal_year),
                ("kind", volume.kind),
                ("listed_at", volume.listed_at),
            )
        )
        or doc.meta.get("dataset_id") != "oag_county_audits"
        or doc.meta.get("extracted_md5") != doc.md5
        or not isinstance(stats, dict)
        or stats.get("extractor") != "oag_county_volume"
        or stats.get("fiscal_year") != volume.fiscal_year
        or stats.get("volume_kind") != volume.kind
        or stats.get("partial") is not False
        or type(stats.get("chapters_attributed")) is not int
        or stats["chapters_attributed"] != 47
        or type(stats.get("contents_entries")) is not int
        or stats["contents_entries"] != 47
        or type(stats.get("pages")) is not int
        or stats["pages"] != entry["pages"]
        or type(stats.get("findings")) is not int
        or stats["findings"] <= 0
        or type(stats.get("rejected_cid")) is not int
        or stats["rejected_cid"] != 0
        or any(
            stats.get(k) != []
            for k in (
                "refused",
                "chapters_with_no_finding",
                "unreadable_chapter_pages",
                "missing_counties",
            )
        )
    ):
        raise AuditSourceScopeError("adopted edition lacks complete extraction proof")
    if "last_extraction_attempt" in doc.meta:
        attempt = doc.meta["last_extraction_attempt"]
        if not isinstance(attempt, dict) or attempt.get("status") != "complete":
            raise AuditSourceScopeError("adopted edition has incomplete latest attempt")
    try:
        actual = pdf_artifact.file_identity(Path(doc.file_path))
    except (OSError, ValueError, TypeError) as exc:
        raise AuditSourceScopeError("retained adopted PDF unavailable/invalid") from exc
    if any(actual[k] != entry[k] for k in ("sha256", "md5")):
        raise AuditSourceScopeError("retained adopted PDF edition changed")
    if pdf_artifact.ARTIFACT_KEY in doc.meta:
        identity = pdf_artifact.extraction_artifact(doc)
        if identity["sha256"] != entry["sha256"]:
            raise AuditSourceScopeError("adopted PDF artifact changed")
    verify_extraction_evidence(session, doc, entry)
    extractions = (
        session.query(Extraction)
        .filter_by(source_document_id=doc.id)
        .order_by(Extraction.id)
        .all()
    )
    if len(extractions) != stats["findings"]:
        raise AuditSourceScopeError(
            "stored finding count differs from complete extraction"
        )
    audits = (
        session.query(Audit)
        .filter_by(source_document_id=doc.id)
        .order_by(Audit.id)
        .all()
    )
    by_ext = {a.extraction_id: a for a in audits}
    if len(audits) != len(extractions) or len(by_ext) != len(audits):
        raise AuditSourceScopeError(
            "adopted rows do not account for every extraction exactly once"
        )
    known = _known_counties(session)
    county_names = set()
    state = []
    for ext in extractions:
        payload = ext.extracted_json
        audit = by_ext.get(ext.id)
        entity = session.get(Entity, audit.entity_id) if audit else None
        period = session.get(FiscalPeriod, audit.period_id) if audit else None
        names = [payload.get(k) for k in ("entity_name", "auditee")]
        resolved = [
            canonical_county(county_from_auditee(n), known)
            if isinstance(n, str) and county_from_auditee(n)
            else None
            for n in names
        ]
        institution = audited_institution(
            payload,
            county_name=entity.canonical_name if entity else "",
            document_meta=doc.meta,
        )
        role = (
            "assemblies"
            if institution and "County Assembly" in institution
            else "executives"
            if institution and "County Executive" in institution
            else None
        )
        if (
            audit is None
            or entity is None
            or entity.country_id != doc.country_id
            or entity.type != EntityType.COUNTY
            or period is None
            or period.country_id != doc.country_id
            or period.start_date.isoformat()[:10] != f"{volume.fiscal_year[:4]}-07-01"
            or period.end_date.isoformat()[:10] != f"{volume.fiscal_year[5:]}-06-30"
            or any(n != entity.canonical_name.removesuffix(" County") for n in resolved)
            or role != volume.kind
            or audit.audit_year != int(volume.fiscal_year[5:])
            or not isinstance(payload.get("finding_text"), str)
            or not payload["finding_text"].strip()
            or audit.finding_text != payload["finding_text"]
            or audit.source_hash != source_hash_of(payload)
            or page_number(ext.page_number) is None
            or page_number(ext.page_number) != page_number(payload.get("pdf_page"))
            or page_number(audit.page_ref) != page_number(ext.page_number)
        ):
            raise AuditSourceScopeError(
                "adopted row attribution/text/hash/locator changed"
            )
        county_names.add(entity.canonical_name)
        # Bind persisted row state, including publication/amount/provenance, so a
        # later changed after-state cannot reuse this observation as current.
        state.append(
            {
                "extraction": {
                    c.key: getattr(ext, c.key) for c in ext.__mapper__.column_attrs
                },
                "audit": {
                    c.key: getattr(audit, c.key) for c in audit.__mapper__.column_attrs
                },
                "county": {
                    c.key: getattr(entity, c.key)
                    for c in entity.__mapper__.column_attrs
                },
                "period": {
                    c.key: getattr(period, c.key)
                    for c in period.__mapper__.column_attrs
                },
            }
        )
    if len(county_names) != 47:
        raise AuditSourceScopeError(
            "adopted volume does not attribute all 47 county chapters"
        )
    return {
        "source_document_id": doc.id,
        "url": doc.url,
        "fiscal_year": volume.fiscal_year,
        "institution": volume.kind,
        **actual,
        "findings": len(extractions),
        "chapters": len(county_names),
        "binding": "individual_pdf_artifacts"
        if pdf_artifact.ARTIFACT_KEY in doc.meta
        else "legacy_extracted_md5_complete_parser",
        "state_sha256": _digest(
            {
                "source": {
                    c.key: getattr(doc, c.key) for c in doc.__mapper__.column_attrs
                },
                "rows": state,
            }
        ),
    }


def observation_gaps(session, meta, *, now=None):
    """Recheck observed unselected state at the real coverage consumer boundary."""
    receipt = meta.get("oag_county_observation")
    if not isinstance(receipt, dict):
        return ["missing qualified county observation"]
    try:
        if (
            receipt.get("schema") != "oag_county_observation/v1"
            or receipt.get("inventory_basis") != "live_publisher_year_pages"
            or receipt.get("whole_world_coverage") is not False
            or receipt.get("byte_authority")
            != "reviewed_retained_editions_not_fresh_pdf_downloads"
            or receipt.get("accepted_manifest_sha256") != ACCEPTED_SHA256
            or receipt.get("generator_sha256")
            != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            or receipt.get("discovery") != meta.get("oag_county_discovery")
        ):
            raise AuditSourceScopeError("observation authority/producer changed")
        observed = datetime.fromisoformat(receipt["observed_at"])
        if (
            observed.tzinfo is None
            or not 0
            <= ((now or datetime.now(timezone.utc)) - observed).total_seconds()
            <= MAX_OBSERVATION_AGE_SECONDS
        ):
            raise AuditSourceScopeError("listing observation stale or future-dated")
        discovery = receipt["discovery"]
        if (
            discovery.get("listing_url") != od.LISTING_URL
            or discovery.get("errors") != []
        ):
            raise AuditSourceScopeError("publisher listing incomplete")
        from ...county_audit_coverage import _discovered_volume_labels

        if _discovered_volume_labels(discovery) is None:
            raise AuditSourceScopeError("publisher volume inventory malformed")
        if set(discovery["volumes_by_fiscal_year"]) != {
            fy
            for fy in discovery["listing_fiscal_years"]
            if fy >= od.FIRST_INGESTED_FISCAL_YEAR
        }:
            raise AuditSourceScopeError(
                "publisher inventory differs from listed fiscal years"
            )
        pages = receipt["pages"]
        expected_pages = {od.LISTING_URL} | {
            f"{od.OAG_ORIGIN}/{fy.replace('/', '-')}-county-government-audit-reports/"
            for fy in discovery["listing_fiscal_years"]
            if fy >= od.FIRST_INGESTED_FISCAL_YEAR
        }
        import re

        if (
            not isinstance(pages, list)
            or any(
                not isinstance(p, dict)
                or type(p.get("size_bytes")) is not int
                or p["size_bytes"] <= 0
                or not isinstance(p.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", p["sha256"])
                for p in pages
            )
            or len(pages) != len(expected_pages)
            or {p.get("url") for p in pages} != expected_pages
        ):
            raise AuditSourceScopeError("publisher page evidence incomplete")
        from .scope import receipt_for

        # The first three reviewed editions are the adopted current cohorts;
        # the remaining five match the independently pinned execution packet.
        entries = list(accepted_editions().values())[3:]
        selected = {e["source_url"] for e in entries}
        expected_scope = receipt_for(entries)
        scope = meta.get("audit_source_scope")
        if (
            not isinstance(scope, dict)
            or scope.get("whole_world_coverage") is not False
            or any(
                scope.get(k) != expected_scope[k]
                for k in ("manifest_sha256", "inventory_basis", "selected")
            )
        ):
            raise AuditSourceScopeError(
                "observation lost its bounded execution authority"
            )
        outcomes = []
        for key in ("processed", "already_current"):
            values = scope.get(key)
            if not isinstance(values, list) or any(
                not isinstance(url, str) for url in values
            ):
                raise AuditSourceScopeError("bounded source outcomes malformed")
            outcomes.extend(values)
        attempted = scope.get("attempted")
        if (
            len(outcomes) != len(selected)
            or set(outcomes) != selected
            or not isinstance(attempted, list)
            or any(not isinstance(url, str) for url in attempted)
            or len(attempted) != len(selected)
            or set(attempted) != selected
            or scope.get("deferred") != []
            or scope.get("refused") != []
        ):
            raise AuditSourceScopeError("bounded source outcomes incomplete")
        inventory = [
            (fy, url)
            for fy, urls in discovery["volumes_by_fiscal_year"].items()
            for url in urls
        ]
        _require_reviewed_inventory(inventory)
        expected = []
        for fy, url in inventory:
            if url in selected:
                continue
            kind, _ = od.classify_document(url)
            expected.append(
                verify_adopted_volume(
                    session,
                    od.OagDocument(
                        url,
                        fy,
                        kind,
                        "year_page",
                        f"{od.OAG_ORIGIN}/{fy.replace('/', '-')}-county-government-audit-reports/",
                    ),
                )
            )
        if receipt.get("adopted") != expected:
            raise AuditSourceScopeError(
                "observed adopted state changed or lacks full outcome evidence"
            )
    except (ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
        return [f"qualified county observation refused: {exc}"]
    return []

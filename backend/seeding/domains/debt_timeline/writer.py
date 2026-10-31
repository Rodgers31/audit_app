"""Writer for debt timeline records to database."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import TYPE_CHECKING, Any

from models import Country, DebtTimeline, DocumentType, SourceDocument
from sqlalchemy.orm import Session
from services.response_receipts import persist_evidence

if TYPE_CHECKING:
    from .parser import DebtTimelineRecord

logger = logging.getLogger("seeding.debt_timeline.writer")


def _get_or_create_source_document(
    session: Session, metadata: dict[str, Any], title: str | None = None,
    source_url: str | None = None,
) -> SourceDocument:
    """Get or create the source document a debt-timeline row traces to.

    ``title`` is the row's own source when it declares one. The series spans
    two different CBK publications — the /public-debt/ table for 2013-2021 and
    the Statistical Bulletin for 2022-2025 — so assigning one payload-level
    document to every year made half the series cite a document that does not
    contain it.
    """
    title = title or metadata.get(
        "source", "CBK Annual Reports & National Treasury BPS"
    )

    kenya = session.query(Country).filter(Country.iso_code == "KEN").first()
    if not kenya:
        raise ValueError("Kenya country not found. Run bootstrap_data.py first.")
    query = (
        session.query(SourceDocument)
        .filter(
            SourceDocument.title == title,
            SourceDocument.doc_type == DocumentType.REPORT,
            SourceDocument.country_id == kenya.id,
        )
    )
    if source_url is not None:
        from urllib.parse import urlsplit
        parsed = urlsplit(source_url)
        if (parsed.scheme != "https" or parsed.hostname not in ("www.centralbank.go.ke", "centralbank.go.ke")
                or parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443)):
            raise ValueError("Official CBK source URL required")
        query = query.filter(
            SourceDocument.url == source_url,
            SourceDocument.publisher == "Central Bank of Kenya",
        )
    else:
        query = query.filter(
            SourceDocument.url == "https://www.centralbank.go.ke/statistics/government-finance-statistics/",
            SourceDocument.publisher == "Central Bank of Kenya / National Treasury",
        )
    doc = query.first()
    if doc:
        return doc

    doc = SourceDocument(
        country_id=kenya.id,
        publisher=("Central Bank of Kenya" if source_url is not None
                   else "Central Bank of Kenya / National Treasury"),
        title=title,
        url=source_url or "https://www.centralbank.go.ke/statistics/government-finance-statistics/",
        fetch_date=datetime.now(timezone.utc),
        doc_type=DocumentType.REPORT,
        meta={
            "notes": metadata.get("notes", ""),
            "units": metadata.get("units", "billions_kes"),
        },
    )
    session.add(doc)
    session.flush()
    return doc


def _raw_kes(value: Any) -> Any:
    """Normalise a money value to raw KES at the DB boundary.

    Fetchers/parsers (and their fixtures) carry the historical billions
    convention; the table stores raw KES with a declared ``unit`` column
    since the stage1 3a migration. No national debt aggregate legitimately
    sits between 1e6 and 1e9, so the scale test is unambiguous and this
    is idempotent for already-raw inputs.
    """
    if value is None:
        return None
    # A bool is an int in Python and would silently become 1e9 KES; NaN/inf
    # would poison the table. Both are parser bugs — fail closed, loudly.
    if isinstance(value, bool):
        raise ValueError(f"boolean is not a money value: {value!r}")
    v = Decimal(str(value))
    if not v.is_finite():
        raise ValueError(f"non-finite money value: {value!r}")
    if v < 0:
        raise ValueError(f"negative debt-timeline value: {value!r}")
    return v * Decimal("1e9") if v < 1_000_000 else v


def _observed_evidence(record, measure: str, value) -> list[dict]:
    """Only current acquisition manifests can replace an existing measure.

    A configured fixture, serialized receipt or changed normalized cell does
    not establish a refresh. Retention qualification remains a separate gate.
    """
    from urllib.parse import urlsplit
    from services.response_receipts import receipt_is_sealed

    matches = []
    for item in record.source_evidence or []:
        receipt = item.get("_response_receipt")
        if not receipt_is_sealed(receipt):
            continue
        identity = item.get("identity", {})
        expected = {"measure": measure, "entity_id": None, "geography": "KEN",
                    "period": str(record.year), "unit": "KES",
                    "basis": "current_prices" if measure == "gdp" else "actual", "dimensions": {}}
        if identity != expected or any(item.get("checks", {}).get(k) is not True
                                      for k in ("identity", "value", "transport", "locator")):
            continue
        if item.get("reconciliation", {}).get("status") != "matched":
            continue
        if measure == "gdp":
            if urlsplit(receipt.get("request_url", "")).hostname != "api.worldbank.org":
                continue
        elif not record.source_url or receipt.get("request_url") != record.source_url:
            continue
        manifest_fields = ("identity", "locator", "raw_value", "raw_unit", "transformation")
        if not any(all(entry.get(k) == item.get(k) for k in manifest_fields)
                   for entry in receipt.get("observations", [])):
            continue
        try:
            normalized = Decimal(item["value"])
            transform = item["transformation"]
            reproduced = Decimal(item["raw_value"]) * Decimal(transform["factor"])
            rounding = transform.get("rounding")
            if rounding is not None:
                if type(rounding) is not int or not -20 <= rounding <= 20:
                    continue
                reproduced = reproduced.quantize(Decimal(1).scaleb(-rounding), rounding=ROUND_HALF_EVEN)
            if (value is None or not normalized.is_finite() or not reproduced.is_finite()
                    or normalized != reproduced or normalized != value
                    or measure == "gdp" and normalized <= 0):
                continue
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
        matches.append(item)
    return matches if len(matches) == 1 else []


def write_debt_timeline_records(
    session: Session,
    records: list[DebtTimelineRecord],
    metadata: dict[str, Any],
) -> tuple[int, int]:
    """Upsert debt timeline records into the database (raw KES)."""
    created = 0
    updated = 0

    doc_cache: dict[tuple, SourceDocument] = {}
    gdp_doc = None

    def _doc_for(record) -> SourceDocument:
        key = (record.source, record.source_url)
        if key not in doc_cache:
            doc_cache[key] = _get_or_create_source_document(
                session, metadata, title=record.source, source_url=record.source_url,
            )
        return doc_cache[key]

    for record in records:
        existing = (
            session.query(DebtTimeline).filter(DebtTimeline.year == record.year).first()
        )
        values = {key: _raw_kes(getattr(record, key)) for key in ("external", "domestic", "total", "gdp")}
        observed = {key: _observed_evidence(record, key, values[key]) for key in values}
        stocks_observed = all(observed[key] for key in ("external", "domestic", "total"))
        if stocks_observed:
            # Independently valid cells from different bulletins do not form
            # one observed stock. Deep copies retain the same sealed manifest.
            receipts = [observed[key][0]["_response_receipt"]
                        for key in ("external", "domestic", "total")]
            stocks_observed = (len({(r._acquisition, r._sealed) for r in receipts}) == 1
                               and abs(values["external"] + values["domestic"] - values["total"])
                               <= values["total"] * Decimal("0.005"))
        source_doc = _doc_for(record) if stocks_observed or existing is None else None
        if stocks_observed:
            association = (source_doc.id, source_doc.country_id, source_doc.publisher, source_doc.url)
            stocks_observed = all(not item["_response_receipt"]._bound_source
                                  or item["_response_receipt"]._bound_source[0] == association
                                  for key in ("external", "domestic", "total") for item in observed[key])
        gdp_observed = bool(observed["gdp"])
        if gdp_observed:
            from ..national_gdp import _ensure_gdp_source_document
            if gdp_doc is None:
                gdp_doc = _ensure_gdp_source_document(session)
            association = (gdp_doc.id, gdp_doc.country_id, gdp_doc.publisher, gdp_doc.url)
            receipt = observed["gdp"][0]["_response_receipt"]
            gdp_observed = not receipt._bound_source or receipt._bound_source[0] == association
        if existing and not stocks_observed and not gdp_observed:
            continue
        if existing and not stocks_observed and existing.unit != "KES":
            raise ValueError("Retained debt stock requires declared raw KES before GDP refresh")

        replaced = ({"external", "domestic", "total"} if stocks_observed else set())
        if gdp_observed:
            replaced.add("gdp")
        incoming = ([item for key in values if key in replaced for item in observed[key]]
                    if existing else record.source_evidence or [])

        evidence = [item for item in (existing.meta or {}).get("source_evidence", [])
                    if item.get("identity", {}).get("measure") not in replaced] if existing else []
        for item in incoming:
            if item.get("identity", {}).get("measure") == "gdp":
                from ..national_gdp import _ensure_gdp_source_document
                if gdp_doc is None:
                    gdp_doc = _ensure_gdp_source_document(session)
                evidence_doc = gdp_doc
            else:
                evidence_doc = source_doc
            evidence.extend(persist_evidence(session, evidence_doc, [item]))
        if existing:
            if stocks_observed:
                existing.external = values["external"]
                existing.domestic = values["domestic"]
                existing.total = values["total"]
                existing.source_document_id = source_doc.id
            if gdp_observed:
                existing.gdp = values["gdp"]
            existing.gdp_ratio = (Decimal(str(existing.total)) / existing.gdp * 100).quantize(
                Decimal("0.1")) if gdp_observed else None
            existing.unit = "KES"
            existing.meta = {**(existing.meta or {}), "source_evidence": evidence}
            existing.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            row = DebtTimeline(
                year=record.year,
                external=_raw_kes(record.external),
                domestic=_raw_kes(record.domestic),
                total=_raw_kes(record.total),
                gdp=_raw_kes(record.gdp),
                gdp_ratio=record.gdp_ratio,
                unit="KES",
                source_document_id=source_doc.id,
                meta={"source_evidence": evidence},
            )
            session.add(row)
            created += 1

    session.flush()
    logger.info(f"Debt timeline: {created} created, {updated} updated")
    return created, updated

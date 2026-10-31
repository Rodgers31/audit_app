"""Writer for debt timeline records to database."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
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
        source_doc = _doc_for(record)
        existing = (
            session.query(DebtTimeline).filter(DebtTimeline.year == record.year).first()
        )

        evidence = []
        for item in record.source_evidence or []:
            if item.get("identity", {}).get("measure") == "gdp":
                from ..national_gdp import _ensure_gdp_source_document
                if gdp_doc is None:
                    gdp_doc = _ensure_gdp_source_document(session)
                evidence_doc = gdp_doc
            else:
                evidence_doc = source_doc
            evidence.extend(persist_evidence(session, evidence_doc, [item]))
        if existing:
            existing.external = _raw_kes(record.external)
            existing.domestic = _raw_kes(record.domestic)
            existing.total = _raw_kes(record.total)
            existing.gdp = _raw_kes(record.gdp)
            existing.gdp_ratio = record.gdp_ratio
            existing.unit = "KES"
            existing.source_document_id = source_doc.id
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

"""Layer-4 loader: extractions → audit rows with full provenance, gated.

Positive controls throughout: the publication gate must FIRE against a
no-URL document and a cid row, the loader must SKIP an extraction it
cannot attribute, and a re-run must not duplicate rows.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from models import (
    Audit,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    Extraction,
    FigureBasis,
    Severity,
    SourceDocument,
)
from seeding.config import SeedingSettings
from seeding.domains.audits.loader import load_blue_book_extractions
from seeding.extractors.oag_blue_book import EXTRACTOR_ID
from seeding.types import DomainRunContext


@pytest.fixture()
def blue_book_doc(db_session, seed_country):
    doc = SourceDocument(
        id=2392,
        country_id=seed_country.id,
        publisher="Office of the Auditor-General",
        title="AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf",
        url=(
            "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/"
            "AUDITOR-GENERALS-REPORT-ON-NATIONAL-GOVERNMENT-2024-2025.pdf"
        ),
        md5="7e6a6850102a3cadcba38e1f7af9cae3",
        fetch_date=datetime(2026, 8, 29, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def _extraction(doc, page, payload_overrides=None, confidence=0.90):
    payload = {
        "schema": "oag_blue_book/v1",
        "vote": 1071,
        "entity_name": "The National Treasury",
        "fiscal_year": "2024/2025",
        "paragraph_no": 2,
        "title": "Pending Accounts Payable",
        "finding_text": (
            "Pending Accounts Payable The statement of financial position "
            "reflects trade and other payables balance of Kshs.20,811,926,257."
        ),
        "pdf_page": page,
        "printed_page": page - 13,
        "subreport": "REPORT ON THE FINANCIAL STATEMENTS",
        "opinion": "Unmodified Opinion",
        "heading": "Emphasis of Matter",
        "sub_section": None,
        "severity": "INFO",
        "amounts": [20_811_926_257.0],
        "extraction_method": "pdfplumber",
    }
    payload.update(payload_overrides or {})
    return Extraction(
        source_document_id=doc.id,
        page_number=page,
        extracted_json=payload,
        extractor=EXTRACTOR_ID,
        confidence=confidence,
    )


@pytest.fixture()
def settings():
    return SeedingSettings()


@pytest.fixture()
def context():
    return DomainRunContext(since=None, dry_run=False)


class TestLoader:
    def test_extraction_becomes_fully_provenanced_audit(
        self, db_session, blue_book_doc, settings, context
    ):
        ext = _extraction(blue_book_doc, page=14)
        db_session.add(ext)
        db_session.commit()

        stats = load_blue_book_extractions(
            db_session, blue_book_doc, settings, context
        )
        assert stats.created == 1

        audit = db_session.query(Audit).one()
        assert audit.extraction_id == ext.id
        assert audit.page_ref == "p.14"
        assert audit.source_hash is not None and len(audit.source_hash) == 64
        assert audit.confidence_score == pytest.approx(0.90)
        assert audit.basis == FigureBasis.ACTUAL
        assert audit.severity == Severity.INFO
        assert float(audit.amount) == 20_811_926_257.0
        assert audit.audit_year == 2025
        assert audit.external_reference == "OAG-BB-2024/2025-V1071-P2"
        # The gate fired and published it (doc has a URL, text is clean).
        assert audit.publishable is True
        assert audit.quarantine_reason is None

        entity = db_session.query(Entity).filter_by(id=audit.entity_id).one()
        assert entity.canonical_name == "The National Treasury"
        assert entity.type == EntityType.MINISTRY

    def test_rerun_is_idempotent(
        self, db_session, blue_book_doc, settings, context
    ):
        db_session.add(_extraction(blue_book_doc, page=14))
        db_session.commit()
        load_blue_book_extractions(db_session, blue_book_doc, settings, context)
        stats2 = load_blue_book_extractions(
            db_session, blue_book_doc, settings, context
        )
        assert stats2.created == 0
        assert db_session.query(Audit).count() == 1

    def test_multiple_amounts_leave_amount_null(
        self, db_session, blue_book_doc, settings, context
    ):
        db_session.add(
            _extraction(
                blue_book_doc,
                page=15,
                payload_overrides={
                    "amounts": [122_176_370_707.0, 113_732_718_491.0],
                    "paragraph_no": 3,
                },
            )
        )
        db_session.commit()
        load_blue_book_extractions(db_session, blue_book_doc, settings, context)
        audit = db_session.query(Audit).one()
        # Two figures = no single "amount involved"; both stay in provenance.
        assert audit.amount is None
        assert audit.provenance[0]["amounts"] == [
            122_176_370_707.0,
            113_732_718_491.0,
        ]

    def test_unattributable_extraction_is_skipped_not_guessed(
        self, db_session, blue_book_doc, settings, context
    ):
        db_session.add(
            _extraction(
                blue_book_doc, page=16, payload_overrides={"fiscal_year": None}
            )
        )
        db_session.commit()
        stats = load_blue_book_extractions(
            db_session, blue_book_doc, settings, context
        )
        assert stats.created == 0
        assert stats.skipped == 1
        assert db_session.query(Audit).count() == 0

    def test_commission_vote_typed_as_commission(
        self, db_session, blue_book_doc, settings, context
    ):
        db_session.add(
            _extraction(
                blue_book_doc,
                page=890,
                payload_overrides={
                    "vote": 2021,
                    "entity_name": "National Land Commission",
                },
            )
        )
        db_session.commit()
        load_blue_book_extractions(db_session, blue_book_doc, settings, context)
        entity = db_session.query(Entity).filter_by(
            canonical_name="National Land Commission"
        ).one()
        assert entity.type == EntityType.COMMISSION


class TestGateBackfill:
    def test_no_url_document_withheld_with_reason(
        self, db_session, seed_country, settings, context, blue_book_doc
    ):
        # POSITIVE CONTROL: the gate must fire against a no-URL document.
        no_url_doc = SourceDocument(
            id=1836,
            country_id=seed_country.id,
            publisher="Office of the Auditor General",
            title="A report nobody can open",
            url=None,
            fetch_date=datetime(2024, 12, 15, tzinfo=timezone.utc),
            doc_type=DocumentType.AUDIT,
            status=DocumentStatus.AVAILABLE,
        )
        entity = Entity(
            id=900,
            country_id=seed_country.id,
            type=EntityType.MINISTRY,
            canonical_name="Ministry of Health",
            slug="ministry-of-health-loader-test",
        )
        db_session.add_all([no_url_doc, entity])
        db_session.flush()
        from models import FiscalPeriod

        period = FiscalPeriod(
            id=900,
            country_id=seed_country.id,
            label="FY2023/24",
            start_date=datetime(2023, 7, 1),
            end_date=datetime(2024, 6, 30),
        )
        db_session.add(period)
        db_session.flush()
        db_session.add_all(
            [
                Audit(
                    entity_id=entity.id,
                    period_id=period.id,
                    finding_text="A finding citing an unopenable document",
                    severity=Severity.WARNING,
                    source_document_id=no_url_doc.id,
                ),
                Audit(
                    entity_id=entity.id,
                    period_id=period.id,
                    finding_text="(cid:31)(cid:30) glyph junk row",
                    severity=Severity.CRITICAL,
                    source_document_id=blue_book_doc.id,
                ),
            ]
        )
        db_session.commit()

        from services.publication_gate import backfill_publishable_audits

        stats = backfill_publishable_audits(db_session)
        assert stats == {"published": 0, "withheld": 2}

        rows = {
            a.finding_text[:6]: (a.publishable, a.quarantine_reason)
            for a in db_session.query(Audit).all()
        }
        assert rows["A find"] == (False, "source_document_has_no_url")
        assert rows["(cid:3"] == (False, "finding_text_unreadable_cid")

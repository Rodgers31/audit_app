"""Retired invented rows are not genuine evidence waiting for a citation."""
from models import Audit, Severity
from services.publication_gate import count_withheld_audits, count_withheld_by_reason


def test_retired_fixture_is_not_counted_as_pending_evidence(
    db_session, seed_entity, seed_source_doc, seed_fiscal_period
):
    seed_source_doc.meta = {"source": "oag_national_audit_data.json"}
    seed_source_doc.url = None
    db_session.add(
        Audit(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            source_document_id=seed_source_doc.id,
            finding_text="Retired fixture",
            severity=Severity.WARNING,
        )
    )
    db_session.commit()
    assert count_withheld_audits(db_session) == 0
    assert sum(count_withheld_by_reason(db_session).values()) == 0


def test_genuine_unsourced_finding_is_still_disclosed(
    db_session, seed_entity, seed_source_doc, seed_fiscal_period
):
    seed_source_doc.url = None
    db_session.add(
        Audit(
            entity_id=seed_entity.id,
            period_id=seed_fiscal_period.id,
            source_document_id=seed_source_doc.id,
            finding_text="Unresolved genuine finding",
            severity=Severity.WARNING,
        )
    )
    db_session.commit()
    assert count_withheld_audits(db_session) == 1
    assert count_withheld_by_reason(db_session)["source_document_has_no_url"] == 1


def test_url_cannot_republish_fixture_but_real_extraction_survives(
    db_session, seed_entity, seed_source_doc, seed_fiscal_period
):
    from models import Extraction
    from services.publication_gate import (
        backfill_publishable_audits,
        publishable_audit_criterion,
    )

    seed_source_doc.meta = {"source": "oag_national_audit_data.json"}
    ext = Extraction(
        source_document_id=seed_source_doc.id,
        extractor="oag_blue_book",
        page_number=23,
        extracted_json={"finding_text": "Actual report finding"},
    )
    db_session.add(ext)
    db_session.flush()
    for ext_id in (None, ext.id):
        db_session.add(
            Audit(
                entity_id=seed_entity.id,
                period_id=seed_fiscal_period.id,
                source_document_id=seed_source_doc.id,
                extraction_id=ext_id,
                page_ref="p.23",
                finding_text="Finding",
                severity=Severity.WARNING,
                publishable=True,
            )
        )
    db_session.flush()
    assert (
        db_session.query(Audit)
        .filter(publishable_audit_criterion())
        .one()
        .extraction_id
        == ext.id
    )
    backfill_publishable_audits(db_session)
    db_session.expire_all()
    retired = db_session.query(Audit).filter(Audit.extraction_id.is_(None)).one()
    assert retired.publishable is False
    assert retired.quarantine_reason == "retired_legacy_fixture"
    assert count_withheld_audits(db_session) == 0

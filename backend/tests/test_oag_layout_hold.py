"""Unresolved source layout cannot silently become a publishable fact.

Uses real parser/ORM/loader; the national_doc fixture explicitly doubles PDF
reading with bounded source text. It does not qualify the real publisher PDF.
"""
from copy import deepcopy

import pytest
from sqlalchemy import select

from models import Audit, Extraction
from seeding.config import SeedingSettings
from seeding.domains.audits.loader import load_blue_book_extractions
from seeding.extractors import oag_blue_book as bb
from seeding.types import DomainRunContext
from test_blue_book_national_walk import national_doc


@pytest.mark.parametrize('existing', [False, True], ids=['addition', 'revision'])
@pytest.mark.parametrize('qualifications', [None, [], {}, 'unconfirmed', [dict(
    kind='tagged_table_cell_overlap', requires_human_review=True,
    disposition='qualified_embedded_text_visible_fidelity_unconfirmed')]],
    ids=['null','empty-list','object','string','explicit-visible-hold'])
def test_layout_hold_preserves_evidence_and_never_creates_or_revises_fact(
        db_session, national_doc, existing, qualifications):
    settings = SeedingSettings()
    context = DomainRunContext(None, False)
    bb.extract_blue_book(db_session, national_doc, settings)
    extraction = db_session.scalars(select(Extraction).where(
        Extraction.source_document_id == national_doc.id,
        Extraction.extractor == bb.EXTRACTOR_ID).order_by(Extraction.id)).first()
    if existing:
        initial = load_blue_book_extractions(db_session, national_doc, settings, context)
        assert initial.created == 5 and not initial.errors
    before = db_session.scalar(select(Audit).where(Audit.extraction_id == extraction.id))
    original = before.finding_text if before else None
    payload = deepcopy(extraction.extracted_json)
    payload['finding_text'] += ' Unqualified new text must not replace retained evidence.'
    payload['layout_qualifications'] = qualifications
    extraction.extracted_json = payload
    db_session.flush()
    stats = load_blue_book_extractions(db_session, national_doc, settings, context)
    assert stats.skipped == 1
    assert any('layout fidelity held' in e for e in stats.errors)
    db_session.expire_all()
    assert db_session.get(Extraction, extraction.id).extracted_json == payload
    after = db_session.scalar(select(Audit).where(Audit.extraction_id == extraction.id))
    assert (after.finding_text if after else None) == original

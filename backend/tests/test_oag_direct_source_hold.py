"""Independent direct-L3 hold probe; owned PG, bounded PDF/parser double."""
from copy import deepcopy
import pytest
from sqlalchemy import select, func
from models import Audit, Extraction
from seeding.config import SeedingSettings
from seeding.extractors import oag_blue_book as bb
from seeding.extractors.reconciliation import IncompleteExtraction, ReconciliationRequired
from test_blue_book_national_walk import national_doc, _published


def test_exact_review_cannot_adopt_layout_qualified_source_through_direct_parser(db_session, national_doc, monkeypatch):
    _published(db_session, national_doc)
    settings=SeedingSettings()
    pages=bb.read_pages(national_doc.file_path, ocr_enabled=False)
    result=bb.parse_blue_book(pages, national_doc.url)
    target=result.findings[0]
    target.layout_qualifications=[dict(kind='tagged_table_cell_overlap',cell_text=target.title,
        requires_human_review=True,disposition='qualified_embedded_text_visible_fidelity_unconfirmed')]
    monkeypatch.setattr(bb,'parse_blue_book',lambda *args:deepcopy(result))
    with pytest.raises(ReconciliationRequired) as caught:
        bb.extract_blue_book(db_session,national_doc,settings)
    before=dict(audits=db_session.scalar(select(func.count()).select_from(Audit)),
        extraction_ids=db_session.scalars(select(Extraction.id).order_by(Extraction.id)).all(),
        meta=deepcopy(national_doc.meta))
    error=None
    try:
        stats=bb.extract_blue_book(db_session,national_doc,settings,review={
            'proposal':caught.value.proposal,'source_complete':True,
            'reason':'Exact proposal review cannot waive known visible fidelity hold'})
    except IncompleteExtraction as exc:
        error=str(exc)
    after=dict(audits=db_session.scalar(select(func.count()).select_from(Audit)),
        extraction_ids=db_session.scalars(select(Extraction.id).order_by(Extraction.id)).all(),
        current=bb.extraction_is_current(national_doc))
    print('DIRECT_SOURCE_HOLD_RESULT', dict(error=error,before=before,after=after))
    assert error is not None, 'Exact review adopted qualified source via direct parser: '+repr(after)
    assert before['audits']==after['audits'] and before['extraction_ids']==after['extraction_ids']


@pytest.mark.parametrize('qualification', [None, [], {}, 'unconfirmed', [dict(requires_human_review=True)]],
    ids=['null','empty-list','object','string','review-required'])
@pytest.mark.parametrize('reviewed', [False, True], ids=['unapproved','exact-review'])
def test_additive_direct_replacement_cannot_skip_layout_hold(db_session, national_doc, qualification, reviewed):
    pages = bb.read_pages(national_doc.file_path, ocr_enabled=False)
    result = bb.parse_blue_book(pages, national_doc.url)
    rows = [Extraction(source_document_id=national_doc.id, extractor=bb.EXTRACTOR_ID,
        page_number=f.pdf_page, confidence=.9,
        extracted_json=bb.finding_to_extracted_json(f, result.fiscal_year_label)) for f in result.findings]
    rows[0].extracted_json['layout_qualifications'] = qualification
    before = deepcopy(national_doc.meta)
    with pytest.raises(ReconciliationRequired) as caught:
        bb.replace_extractions(db_session, national_doc, bb.EXTRACTOR_ID, rows, bb.blue_book_row_key)
    assert caught.value.proposal['retire_ids'] == caught.value.proposal['update_ids'] == []
    if reviewed:
        with pytest.raises(IncompleteExtraction, match='layout fidelity held'):
            bb.replace_extractions(db_session, national_doc, bb.EXTRACTOR_ID, rows, bb.blue_book_row_key,
                review=dict(proposal=caught.value.proposal, source_complete=True, reason='Exact review cannot waive visibility'))
    assert db_session.scalar(select(func.count()).select_from(Extraction)) == 0
    assert db_session.scalar(select(func.count()).select_from(Audit)) == 0
    assert national_doc.meta == before

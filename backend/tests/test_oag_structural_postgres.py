"""Real PostgreSQL persistence boundary; bounded text input is an inert double.

Run with a disposable PostgreSQL db_session fixture. This does not perform a
production replay or approve a reconciliation proposal.
"""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from models import Country, DocumentType, Extraction, SourceDocument
from seeding.config import SeedingSettings
from seeding.extractors import oag_blue_book as bb
from seeding.extractors.reconciliation import ReconciliationRequired


def prepare(db_session, tmp_path, monkeypatch):
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("requires disposable PostgreSQL")
    db_session.add(Country(id=1,iso_code="KEN",name="Kenya",currency="KES",timezone="Africa/Nairobi",default_locale="en_KE"))
    db_session.flush()
    path = tmp_path / "inert-source.pdf"
    path.write_bytes(b"inert fixture identity; read_pages is explicitly doubled")
    doc = SourceDocument(country_id=1,publisher="OAG",title="Inert fixture source",url="https://www.oagkenya.go.ke/fixture-2024-2025.pdf",doc_type=DocumentType.AUDIT,file_path=str(path),md5="fixture-only",fetch_date=datetime(2026,11,4,tzinfo=timezone.utc),meta={"retained_control": True})
    db_session.add(doc)
    db_session.flush()
    source = json.loads((Path(__file__).parent / "fixtures/oag_structural_2024_2025.json").read_text())
    text = next(p["text"] for p in source["pages"] if p["page_number"] == 510)
    pages = [bb.PageText(i,"","pdfplumber") for i in range(1,510)] + [bb.PageText(510,text,"pdfplumber")]
    clean = []
    findings, rejected = bb.segment_chapter(pages,1112,"State Department for Lands and Physical Planning",497,497,13,clean_statements=clean)
    result = bb.BlueBookResult("2024/2025",findings,1,rejected,0,clean_statements=clean)
    monkeypatch.setattr(bb,"read_pages",lambda *a,**kw:pages)
    monkeypatch.setattr(bb,"parse_blue_book",lambda *a,**kw:copy.deepcopy(result))
    return doc, result


def test_clean_statement_metadata_keeps_real_paragraph_and_page(db_session,tmp_path,monkeypatch):
    doc,result = prepare(db_session,tmp_path,monkeypatch)
    stats = bb.extract_blue_book(db_session,doc,SeedingSettings())
    db_session.flush()
    db_session.expire_all()
    stored = db_session.get(SourceDocument,doc.id)
    clean = next(p for p in stored.meta["clean_statements"] if p["paragraph_no"] == 1594)
    assert (clean["pdf_page"],clean["printed_page"]) == (510,497)
    assert clean["observation_type"] == "clean_statement"
    assert clean["severity"] == "INFO"
    assert clean["opinion"] == "Unmodified Opinion"
    rows = db_session.query(Extraction).filter_by(source_document_id=doc.id).all()
    assert all(r.extracted_json["paragraph_no"] != 1594 for r in rows)
    parent = next(r for r in rows if r.extracted_json["paragraph_no"] == 1596)
    assert "Long Outstanding Pending Accounts Payable" in parent.extracted_json["finding_text"]
    assert (parent.page_number,parent.extracted_json["printed_page"]) == (510,497)
    assert stats["created"] == len(result.findings)


def test_reconciliation_hold_preserves_old_rows_and_document_metadata(db_session,tmp_path,monkeypatch):
    doc,result = prepare(db_session,tmp_path,monkeypatch)
    old = Extraction(source_document_id=doc.id,page_number=510,extractor=bb.EXTRACTOR_ID,confidence=.9,extracted_json=bb.finding_to_extracted_json(result.findings[-1],"2024/2025"))
    old.extracted_json = {**old.extracted_json,"finding_text":"Published historical prefix"}
    db_session.add(old)
    db_session.flush()
    old_id = old.id
    before = copy.deepcopy(doc.meta)
    with pytest.raises(ReconciliationRequired) as caught:
        bb.extract_blue_book(db_session,doc,SeedingSettings())
    db_session.expire_all()
    assert db_session.get(Extraction,old_id).extracted_json["finding_text"] == "Published historical prefix"
    assert db_session.get(SourceDocument,doc.id).meta == before
    assert db_session.query(Extraction).filter_by(source_document_id=doc.id).count() == 1
    assert caught.value.proposal["update_ids"] == [old_id]

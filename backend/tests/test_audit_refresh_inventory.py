"""Audit completeness accounts for reconciled, loaded and unchanged evidence."""
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from seeding.config import SeedingSettings
from seeding.domains.audits.loader import load_blue_book_extractions
from seeding.domains.audits.refresh_outcome import verify_outcome
from seeding.extractors import oag_blue_book as bb
from seeding.refresh_completion import required_refresh_failures
from seeding.types import DomainRunContext
from tests.test_blue_book_national_walk import national_doc, PAGES


def job_for(stats, loaded, processed):
    return SimpleNamespace(domain='audits', status='completed', errors=[], dry_run=False,
        items_processed=processed, meta={'source_mode':'live',
            'refresh_completion':{'complete':True,'accepted_documents':1,'errors':0,'deferred':False},
            'documents':[{'doc_id':2392,'parser_id':'oag_blue_book','extraction_outcome':'accepted',
                          'extractions':stats,'loaded':loaded}]})


@pytest.mark.parametrize('additive', [False, True], ids=['retained-only','one-new-finding'])
def test_real_reextraction_accepts_complete_reconciled_inventory(db_session, national_doc, monkeypatch, additive):
    from models import Audit, Extraction
    settings=SeedingSettings()
    context=DomainRunContext(None,False)
    first=bb.extract_blue_book(db_session,national_doc,settings)
    first_load=load_blue_book_extractions(db_session,national_doc,settings,context,
        fresh_extraction_ids=first['fresh_extraction_ids'])
    assert first_load.processed==first_load.created==5
    before={r.id:(r.extraction_id,r.finding_text,r.amount) for r in db_session.query(Audit)}
    national_doc.meta={**national_doc.meta,'extractor_version':0}
    if additive:
        pages=[*PAGES[:-1],replace(PAGES[-1],text=PAGES[-1].text[:-1]+
            '1405. Unconfirmed Project Deliveries\nThe Department did not provide the project delivery records.\n2')]
        monkeypatch.setattr(bb,'read_pages',lambda *a,**kw:pages)
    stats=bb.extract_blue_book(db_session,national_doc,settings)
    assert stats['kept']==5 and stats['created']==int(additive)
    assert stats['findings']==5+int(additive)
    verify_outcome(db_session,national_doc,stats,'oag_blue_book')
    loaded=load_blue_book_extractions(db_session,national_doc,settings,context,
        fresh_extraction_ids=stats['fresh_extraction_ids'])
    assert loaded.processed==stats['findings']
    assert loaded.created==int(additive) and loaded.updated==0 and loaded.unchanged==5
    assert required_refresh_failures([job_for(stats,asdict(loaded),loaded.processed)])==[]
    after={r.id:(r.extraction_id,r.finding_text,r.amount) for r in db_session.query(Audit)}
    assert all(after[identity]==value for identity,value in before.items())
    assert db_session.query(Extraction).filter_by(source_document_id=national_doc.id).count()==loaded.processed


def test_real_unchanged_loader_replay_has_complete_accounting(db_session, national_doc):
    settings=SeedingSettings()
    context=DomainRunContext(None,False)
    first=bb.extract_blue_book(db_session,national_doc,settings)
    load_blue_book_extractions(db_session,national_doc,settings,context,
        fresh_extraction_ids=first['fresh_extraction_ids'])
    stats=bb.extract_blue_book(db_session,national_doc,settings)
    verify_outcome(db_session,national_doc,stats,'oag_blue_book')
    loaded=load_blue_book_extractions(db_session,national_doc,settings,context)
    assert loaded.created==loaded.updated==0
    assert loaded.unchanged==loaded.processed==5
    assert required_refresh_failures([job_for(stats,asdict(loaded),loaded.processed)])==[]


@pytest.mark.parametrize('loaded', [
    {'processed':10,'created':1,'updated':0,'unchanged':0,'skipped':0},
    {'processed':10,'created':1,'updated':0,'skipped':0},
    {'processed':10,'created':1,'updated':0,'unchanged':8,'skipped':0},
    {'processed':10,'created':1,'updated':0,'unchanged':10,'skipped':0},
    {'processed':10,'created':1,'updated':0,'unchanged':True,'skipped':0},
    {'processed':10,'created':1,'updated':0,'unchanged':float('nan'),'skipped':0},
], ids=['undercounted','missing-unchanged','one-unaccounted','overcounted','boolean','nan'])
def test_summary_never_accepts_unaccounted_loader_inventory(loaded):
    assert required_refresh_failures([job_for({'existing':10},loaded,10)])


@pytest.mark.parametrize('stats', [
    {'findings':10,'created':1,'kept':9,'updated':0,'existing':0},
    {'findings':10,'created':0,'kept':9,'updated':1,'existing':0},
    {'created':10,'skipped':0,'shape':'county_volume'},
    {'created':0,'skipped':10,'reason':'already_extracted'},
    {'created':0,'existing':10,'skipped_unchanged':True},
], ids=['blue-book-kept','blue-book-revised','volume-full-total','volume-unchanged','national-unchanged'])
def test_summary_accepts_exact_reconciled_and_unchanged_inventories(stats):
    loaded={'processed':10,'created':0,'updated':0,'unchanged':10,'skipped':0}
    assert required_refresh_failures([job_for(stats,loaded,10)])==[]

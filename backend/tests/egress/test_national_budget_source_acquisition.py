"""Registration/replay cannot manufacture source-acquisition evidence."""
from dataclasses import replace
from datetime import datetime, timezone
from copy import deepcopy
import hashlib

import httpx
import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from harness import budget_records, seed_country
from models import BudgetLine, DocumentStatus, DocumentType, Extraction, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains.national_budget.writer import persist_national_budget_records
from seeding.pdf_evidence import cell_evidence, seal_pdf_observations
from seeding.types import DomainRunContext
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_local_bytes, capture_response


def records():
    # Two records exercise both initial lookup and the invocation-local cache.
    return [replace(r, source_url='https://cob.go.ke/fixture-registration-only.pdf')
            for r in budget_records(2)]


def snapshot(source):
    return {c.key: getattr(source, 'meta' if c.key == 'metadata' else c.key)
            for c in SourceDocument.__table__.columns}


@pytest.mark.parametrize('status', list(DocumentStatus))
@pytest.mark.parametrize('verified', [False, True])
def test_fixture_registration_preserves_existing_source(pg_fixture, status, verified):
    engine, _ = pg_fixture
    country_id, _ = seed_country(engine)
    values = records()
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with Session(engine) as db:
        source = SourceDocument(country_id=country_id, publisher='Existing publisher',
            title='Existing acquisition', url=values[0].source_url,
            doc_type=DocumentType.REPORT, status=status, fetch_date=old,
            last_seen_at=old, last_verified_at=old if verified else None,
            md5='a'*32 if verified else None, http_status=200 if verified else None,
            content_type='application/pdf' if verified else None,
            file_path='/retained/original.pdf' if verified else None,
            meta={'acquisition': 'preserve', 'nested': {'value': 1}})
        db.add(source)
        db.commit()
        before = snapshot(source)
        identity = source.id
    with Session(engine) as db:
        result = persist_national_budget_records(db, values, SeedingSettings(),
            DomainRunContext(since=None, dry_run=False))
        assert not result.errors and result.created == 2
        db.commit()
    with Session(engine) as db:
        assert snapshot(db.get(SourceDocument, identity)) == before
        assert db.query(BudgetLine).count() == 2


def test_new_fixture_registration_is_unfetched_and_replay_preserves_it(pg_fixture):
    engine, _ = pg_fixture
    seed_country(engine)
    values = records()
    with Session(engine) as db:
        result = persist_national_budget_records(db, values, SeedingSettings(),
            DomainRunContext(since=None, dry_run=False))
        assert not result.errors and result.created == 2
        db.commit()
        source = db.scalar(select(SourceDocument))
        assert source.status == DocumentStatus.FAILED
        assert source.md5 is source.http_status is source.last_verified_at is None
        before = snapshot(source)
    with Session(engine) as db:
        result = persist_national_budget_records(db, values, SeedingSettings(),
            DomainRunContext(since=None, dry_run=False))
        assert not result.errors and result.created == result.updated == 0
        db.commit()
    with Session(engine) as db:
        assert snapshot(db.scalar(select(SourceDocument))) == before
        assert db.query(BudgetLine).count() == 2


PDF = b'%PDF-1.7\nowned transport control\n%%EOF'


def acquired_records(tmp_path, mode='live'):
    values = records()
    url = values[0].source_url
    store = LocalReceiptStore(tmp_path/'receipt-store')
    if mode == 'local':
        receipt = capture_local_bytes(PDF, store, url=url)
    else:
        body = b'<html>not a PDF</html>' if mode == 'wrong-body' else PDF+b'continued' if mode == 'truncated' else PDF
        response = httpx.Response(206 if mode == 'partial' else 200, content=body,
            headers={'content-type':'application/json' if mode == 'wrong-type' else 'application/pdf'},
            request=httpx.Request('GET', url if mode != 'wrong-url' else url+'/different'))
        receipt = capture_response(response, store, source_kind='pdf')
    output, all_evidence = [], []
    for record in values:
        evidence = [cell_evidence(receipt=receipt, identity={
            'measure':name, 'entity_id':None, 'geography':'KEN', 'period':record.period_label,
            'unit':'KES', 'basis':'actual', 'dimensions':{'category':record.category,
                'subcategory':record.subcategory, 'line_type':None}},
            raw_value=value, value=value, raw_unit='KES', factor=1,
            locator={'page':1,'cell':record.category+'/'+name})
            for name,value in [('allocated_amount',record.allocated_amount),
                               ('actual_spent',record.actual_spent)]]
        all_evidence.extend(evidence)
        output.append(replace(record,provenance_extra={**record.provenance_extra,
                                                     'source_evidence':evidence}))
    if mode != 'unsealed':
        seal_pdf_observations(all_evidence)
    if mode == 'plain':
        output = [replace(r,provenance_extra={**r.provenance_extra,
            'source_evidence':[dict(e,_response_receipt=dict(e['_response_receipt']))
                               for e in r.provenance_extra['source_evidence']]}) for r in output]
    elif mode == 'mutated':
        for item in all_evidence:
            item['_response_receipt']['acquired_at'] = '2000-01-01T00:00:00+00:00'
    elif mode == 'missing-bytes':
        store._path(receipt['digest']).unlink()
    return output, receipt, store


@pytest.mark.parametrize('existing_unfetched',[False,True])
def test_real_bound_pdf_initializes_unfetched_source(pg_fixture,tmp_path,existing_unfetched):
    engine,probe=pg_fixture
    country_id,_=seed_country(engine)
    values,receipt,_=acquired_records(tmp_path)
    if existing_unfetched:
        with Session(engine) as db:
            db.add(SourceDocument(country_id=country_id,publisher='Controller of Budget',
                title='Old unfetched fixture registration',url=values[0].source_url,
                doc_type=DocumentType.BUDGET,status=DocumentStatus.FAILED,
                fetch_date=datetime(2020,1,1),last_seen_at=datetime(2020,1,1),
                meta={'preserve':'registered','padding':'x'*65536}))
            db.commit()
    with Session(engine) as db:
        with probe.capture():
            result=persist_national_budget_records(db,values,SeedingSettings(),
                DomainRunContext(since=None,dry_run=False))
            db.flush()
        assert result.created==2 and not result.errors
        db.commit()
    selections=probe.selected('source_documents')
    assert not any('metadata' in sample.columns for sample in selections)
    assert sum(sample.selected_value_bytes for sample in selections)<1024
    with Session(engine) as db:
        source=db.scalar(select(SourceDocument))
        observed=datetime.fromisoformat(receipt['acquired_at']).replace(tzinfo=None)
        assert source.status==DocumentStatus.AVAILABLE
        assert source.http_status==200 and source.content_type=='application/pdf'
        assert source.md5==hashlib.md5(PDF).hexdigest()
        assert source.fetch_date==source.last_verified_at==source.last_seen_at==observed
        assert db.query(Extraction).count()==1
        rows=list(db.scalars(select(BudgetLine).order_by(BudgetLine.id)))
        assert [(r.allocated_amount,r.actual_spent) for r in rows]==[(100,50),(101,51)]
        evidence=[e for r in rows for e in r.provenance[-1]['source_evidence']]
        assert len(evidence)==4
        assert all(all(e['checks'].values()) for e in evidence)
        assert len({e['receipt']['extraction_id'] for e in evidence})==1
        before=snapshot(source)
    # A later fixture replay has no acquisition authority and preserves it.
    with Session(engine) as db:
        persist_national_budget_records(db,records(),SeedingSettings(),
            DomainRunContext(since=None,dry_run=False))
        db.commit()
        assert snapshot(db.scalar(select(SourceDocument)))==before


@pytest.mark.parametrize('mode',['local','plain','unsealed','mutated','wrong-url','missing-bytes',
                                'wrong-body','truncated','partial','wrong-type'])
def test_unqualified_pdf_cannot_initialize_source(pg_fixture,tmp_path,mode):
    engine,_=pg_fixture
    seed_country(engine)
    values,_,_=acquired_records(tmp_path,mode)
    with Session(engine) as db:
        result=persist_national_budget_records(db,values,SeedingSettings(),
            DomainRunContext(since=None,dry_run=False))
        assert not result.errors
        db.commit()
        source=db.scalar(select(SourceDocument))
        assert source.status==DocumentStatus.FAILED
        assert source.md5 is source.http_status is source.content_type is source.last_verified_at is None


@pytest.mark.parametrize('status,history',[(DocumentStatus.ARCHIVED,False),
    (DocumentStatus.AVAILABLE,True),(DocumentStatus.FAILED,True)])
def test_fresh_pdf_does_not_rewrite_archive_or_existing_acquisition(pg_fixture,tmp_path,status,history):
    engine,_=pg_fixture
    country_id,_=seed_country(engine)
    values,_,_=acquired_records(tmp_path)
    with Session(engine) as db:
        source=SourceDocument(country_id=country_id,publisher='Controller of Budget',title='Retained source',
            url=values[0].source_url,doc_type=DocumentType.BUDGET,status=status,
            fetch_date=datetime(2020,1,1),last_seen_at=datetime(2020,1,1),
            md5='f'*32 if history else None,http_status=200 if history else None,
            content_type='application/pdf' if history else None,
            last_verified_at=datetime(2020,1,1) if history else None,
            file_path='/retained/history.pdf' if history else None,meta={'preserve':'history'})
        db.add(source);db.commit();before=snapshot(source)
    with Session(engine) as db:
        persist_national_budget_records(db,values,SeedingSettings(),DomainRunContext(since=None,dry_run=False))
        db.commit()
        assert snapshot(db.scalar(select(SourceDocument)))==before


@pytest.mark.parametrize('lose_initialization_read',[False,True])
def test_retained_bytes_read_once_for_initialization_not_each_cell(pg_fixture,tmp_path,lose_initialization_read):
    engine,_=pg_fixture
    seed_country(engine)
    values,_,store=acquired_records(tmp_path)
    read=store.read
    calls=[]
    def counted(key):
        calls.append(key)
        if lose_initialization_read and len(calls)==2:
            raise RuntimeError('Owned retention failure after receipt persistence')
        return read(key)
    store.read=counted
    with Session(engine) as db:
        persist_national_budget_records(db,values,SeedingSettings(),DomainRunContext(since=None,dry_run=False))
        db.commit()
        source=db.scalar(select(SourceDocument))
        assert source.status==(DocumentStatus.FAILED if lose_initialization_read else DocumentStatus.AVAILABLE)
        if lose_initialization_read:
            assert source.md5 is source.http_status is source.last_verified_at is None
    # Four cells share one immutable receipt: one persistence check plus one
    # first-acquisition initialization read, independent of cell/record count.
    assert len(calls)==2


def test_failed_financial_write_rolls_back_first_acquisition_fields(pg_fixture,tmp_path):
    engine,_=pg_fixture
    country_id,_=seed_country(engine)
    values,_,_=acquired_records(tmp_path)
    with Session(engine) as db:
        source=SourceDocument(country_id=country_id,publisher='Controller of Budget',title='Unfetched',
            url=values[0].source_url,doc_type=DocumentType.BUDGET,status=DocumentStatus.FAILED,
            fetch_date=datetime(2020,1,1),last_seen_at=datetime(2020,1,1))
        db.add(source);db.commit();before=snapshot(source)
    def fail_line(conn,cursor,statement,parameters,context,many):
        if statement.startswith('INSERT INTO budget_lines'):
            raise RuntimeError('Owned financial-write refusal')
    event.listen(engine,'before_cursor_execute',fail_line)
    try:
        with Session(engine) as db:
            with pytest.raises(RuntimeError,match='Owned financial-write refusal'):
                persist_national_budget_records(db,values,SeedingSettings(),DomainRunContext(since=None,dry_run=False))
                db.flush()
            db.rollback()
    finally:
        event.remove(engine,'before_cursor_execute',fail_line)
    with Session(engine) as db:
        assert snapshot(db.scalar(select(SourceDocument)))==before
        assert db.query(Extraction).count()==db.query(BudgetLine).count()==0


def test_unrelated_persisted_reference_cannot_supply_acquisition_timestamp(pg_fixture,tmp_path):
    from seeding.domains.national_budget.writer import _initialize_pdf_acquisition
    engine,_=pg_fixture
    country_id,_=seed_country(engine)
    values,_,_=acquired_records(tmp_path)
    original=values[0].provenance_extra['source_evidence'][0]
    raw=original['_response_receipt']
    with Session(engine) as db:
        source=SourceDocument(country_id=country_id,publisher='Controller of Budget',title='Unfetched',
            url=values[0].source_url,doc_type=DocumentType.BUDGET,status=DocumentStatus.FAILED,
            fetch_date=datetime(2020,1,1),last_seen_at=datetime(2020,1,1))
        db.add(source);db.flush()
        stored=deepcopy(dict(raw))
        stored['acquired_at']='2099-01-01T00:00:00+00:00'
        extraction=Extraction(source_document_id=source.id,extractor='pdf-receipt-v1',
            extracted_json={'response_receipt':stored})
        db.add(extraction);db.flush()
        ref={'receipt':{'extraction_id':extraction.id,'digest':raw['digest'],
                        'source_document_id':source.id}}
        _initialize_pdf_acquisition(db,source,[original],[ref],set())
        assert source.status==DocumentStatus.FAILED
        assert source.last_verified_at is None and source.md5 is None


def test_pdf_artifact_history_is_not_initialized_as_a_new_acquisition(pg_fixture,tmp_path):
    engine,_=pg_fixture
    country_id,_=seed_country(engine)
    values,_,_=acquired_records(tmp_path)
    with Session(engine) as db:
        source=SourceDocument(country_id=country_id,publisher='Controller of Budget',title='Historical binding',
            url=values[0].source_url,doc_type=DocumentType.BUDGET,status=DocumentStatus.FAILED,
            fetch_date=datetime(2020,1,1),last_seen_at=datetime(2020,1,1),
            meta={'pdf_artifact_v1':{'md5':'f'*32,'sha256':'e'*64}})
        db.add(source);db.commit();before=snapshot(source)
    with Session(engine) as db:
        persist_national_budget_records(db,values,SeedingSettings(),DomainRunContext(since=None,dry_run=False))
        db.commit()
        assert snapshot(db.scalar(select(SourceDocument)))==before

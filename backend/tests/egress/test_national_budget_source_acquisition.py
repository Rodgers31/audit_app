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


@pytest.mark.parametrize('count', [1, 40])
@pytest.mark.parametrize('stale', [False, True])
def test_missing_proof_has_per_source_bounds_and_preserves_history(pg_fixture, count, stale):
    from seeding.native_report_authority import KEY
    engine, probe = pg_fixture
    country_id, _ = seed_country(engine)
    values = [replace(r, source_url=records()[0].source_url) for r in budget_records(count)]
    meta = {'padding': 'x' * 65536, 'acquisition': {'preserve': True}}
    if stale:
        meta[KEY] = {'national_budget': {'extraction_id': 19}, 'audits': {'preserve': True}}
    with Session(engine) as db:
        source = SourceDocument(country_id=country_id, publisher='Controller of Budget',
            title='Historical source', url=values[0].source_url, doc_type=DocumentType.BUDGET,
            status=DocumentStatus.FAILED, fetch_date=datetime(2020, 1, 1), meta=deepcopy(meta))
        db.add(source); db.flush()
        old = Extraction(source_document_id=source.id, extractor='old-immutable-evidence',
            extracted_json={'retained': 'original'})
        db.add(old); db.commit()
        sid, eid = source.id, old.id
    with Session(engine) as db:
        with probe.capture():
            result = persist_national_budget_records(db, values, SeedingSettings(), DomainRunContext(None, False))
            db.flush()
        samples = probe.selected('source_documents')
        writes = [s for s in probe.samples if s.sql.startswith('UPDATE source_documents')]
        print({'rows': count, 'stale': stale, 'source_reads': len(samples),
            'source_writes': len(writes), 'columns': [s.columns for s in samples],
            'returned_bytes': sum(s.selected_value_bytes for s in samples)})
        # Resolution + row lock + pre/post-constraint scalar projections.
        assert len(samples) == 4
        assert len(writes) == int(stale)
        assert not any('metadata' in s.columns for s in samples)
        assert sum(s.selected_value_bytes for s in samples) < 1024
        assert result.created == count and not result.errors
        db.commit()
    if stale:
        del meta[KEY]['national_budget']
    with Session(engine) as db:
        assert db.get(SourceDocument, sid).meta == meta
        assert db.get(Extraction, eid).extracted_json == {'retained': 'original'}
        rows = list(db.scalars(select(BudgetLine).order_by(BudgetLine.id)))
        assert [(r.allocated_amount, r.actual_spent) for r in rows] == [(100+i, 50+i) for i in range(count)]


@pytest.mark.parametrize('container', [None, {}, [], 'wrong', True, 1], ids=['null', 'empty', 'array', 'string', 'bool', 'int'])
def test_missing_proof_container_shapes(pg_fixture, container):
    from seeding.native_report_authority import KEY, persist_native_report
    engine, _ = pg_fixture
    country_id, _ = seed_country(engine)
    with Session(engine) as db:
        source = SourceDocument(country_id=country_id, publisher='Controller of Budget',
            title='Shape control', url=records()[0].source_url, doc_type=DocumentType.BUDGET,
            status=DocumentStatus.FAILED, fetch_date=datetime(2020, 1, 1), meta={KEY: container, 'padding': 'x' * 65536})
        db.add(source); db.commit()
        before = deepcopy(source.meta)
        if container is None or type(container) is dict:
            persist_native_report(db, source, None, context=DomainRunContext(None, False), domain='national_budget')
            db.commit()
            assert source.meta == before
        else:
            with pytest.raises(ValueError, match='binding container invalid'):
                persist_native_report(db, source, None, context=DomainRunContext(None, False), domain='national_budget')
            db.rollback()
            assert source.meta == before


@pytest.mark.parametrize('has_binding', [False, True])
def test_invalidation_uses_locked_current_metadata_and_rolls_back(pg_fixture, monkeypatch, has_binding):
    import seeding.native_report_authority as authority
    engine, _ = pg_fixture
    country_id, _ = seed_country(engine)
    with Session(engine) as db:
        source = SourceDocument(country_id=country_id, publisher='Controller of Budget',
            title='Current source', url=records()[0].source_url, doc_type=DocumentType.BUDGET,
            status=DocumentStatus.FAILED, fetch_date=datetime(2020, 1, 1), meta={'old': True})
        db.add(source); db.commit(); sid = source.id
    current = {'new': 'x' * 65536, authority.KEY: {'national_budget': {'stale': True}, 'audits': {'keep': True}}}
    if not has_binding:
        del current[authority.KEY]['national_budget']
    original_lock = authority.lock_native_domain
    def replace_before_lock(db, domain):
        with Session(engine) as other:
            other.get(SourceDocument, sid).meta = deepcopy(current)
            other.commit()
        original_lock(db, domain)
    monkeypatch.setattr(authority, 'lock_native_domain', replace_before_lock)
    with Session(engine) as db:
        source = db.get(SourceDocument, sid)
        assert source.meta == {'old': True}
        authority.persist_native_report(db, source, None, context=DomainRunContext(None, False), domain='national_budget')
        assert source.meta == {**current, authority.KEY: {'audits': {'keep': True}}}
        db.rollback()
    with Session(engine) as db:
        assert db.get(SourceDocument, sid).meta == current


def test_suppressed_invalidation_refuses_and_preserves_old_binding(pg_fixture):
    from sqlalchemy import text
    from seeding.native_report_authority import KEY, persist_native_report
    engine, _ = pg_fixture
    country_id, _ = seed_country(engine)
    meta = {KEY: {'national_budget': {'stale': True}}, 'padding': 'x' * 65536}
    with Session(engine) as db:
        source = SourceDocument(country_id=country_id, publisher='Controller of Budget',
            title='Suppressed write', url=records()[0].source_url, doc_type=DocumentType.BUDGET,
            status=DocumentStatus.FAILED, fetch_date=datetime(2020, 1, 1), meta=deepcopy(meta))
        db.add(source); db.commit(); sid = source.id
    with engine.begin() as db:
        db.execute(text('CREATE FUNCTION keep_metadata() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN NEW.metadata=OLD.metadata; RETURN NEW; END $$'))
        db.execute(text('CREATE TRIGGER keep_metadata BEFORE UPDATE ON source_documents FOR EACH ROW EXECUTE FUNCTION keep_metadata()'))
    with Session(engine) as db:
        with pytest.raises(ValueError, match='invalidation readback differs'):
            persist_native_report(db, db.get(SourceDocument, sid), None, context=DomainRunContext(None, False), domain='national_budget')
        db.rollback()
        assert db.get(SourceDocument, sid).meta == meta


def arm_deferred_binding(db):
    from sqlalchemy import text
    db.execute(text("CREATE FUNCTION armed_deferred_binding() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN UPDATE source_documents SET metadata=jsonb_set(metadata #- '{arm}','{native_report_authority_v1}', jsonb_build_object('national_budget',jsonb_build_object('stale',true))) WHERE id=NEW.id; RETURN NEW; END $$"))
    db.execute(text("CREATE CONSTRAINT TRIGGER armed_deferred_binding AFTER UPDATE ON source_documents DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (NEW.metadata->>'arm'='yes') EXECUTE FUNCTION armed_deferred_binding()"))


def test_absent_binding_still_flushes_deferred_constraint_before_success(pg_fixture):
    from seeding.native_report_authority import persist_native_report
    engine, _ = pg_fixture
    country_id, _ = seed_country(engine)
    with Session(engine) as db:
        source = SourceDocument(country_id=country_id, publisher='Controller of Budget',
            title='Deferred no-op control', url=records()[0].source_url,
            doc_type=DocumentType.BUDGET, status=DocumentStatus.FAILED,
            fetch_date=datetime(2020, 1, 1), meta={'padding': 'x' * 65536})
        db.add(source); db.commit(); sid = source.id
    with engine.begin() as db:
        arm_deferred_binding(db)
    with Session(engine) as db:
        source = db.get(SourceDocument, sid)
        source.meta = {**source.meta, 'arm': 'yes'}
        with pytest.raises(ValueError, match='invalidation readback differs'):
            persist_native_report(db, source, None, context=DomainRunContext(None, False), domain='national_budget')
        db.rollback()


def test_absent_binding_commit_does_not_leave_deferred_stale_binding(pg_fixture):
    from seeding.native_report_authority import KEY, persist_native_report
    engine, _ = pg_fixture
    country_id, _ = seed_country(engine)
    with Session(engine) as db:
        source = SourceDocument(country_id=country_id, publisher='Controller of Budget',
            title='Deferred no-op control', url=records()[0].source_url,
            doc_type=DocumentType.BUDGET, status=DocumentStatus.FAILED,
            fetch_date=datetime(2020, 1, 1), meta={'padding': 'x' * 65536})
        db.add(source); db.commit(); sid = source.id
    with engine.begin() as db:
        arm_deferred_binding(db)
    with Session(engine) as db:
        source = db.get(SourceDocument, sid)
        source.meta = {**source.meta, 'arm': 'yes'}
        try:
            persist_native_report(db, source, None, context=DomainRunContext(None, False), domain='national_budget')
        except ValueError as error:
            assert 'invalidation readback differs' in str(error)
            db.rollback()
            return
        db.commit()
    with Session(engine) as db:
        assert 'national_budget' not in db.get(SourceDocument, sid).meta.get(KEY, {}), 'Invalidation returned success but deferred commit restored stale binding'

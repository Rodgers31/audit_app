"""Required owned PostgreSQL writer/API/provenance controls (no live services).

The runtime qualification harness supplies FISCAL_TEST_POSTGRES_URL. Absence
is a prerequisite failure, never an integration pass or a live/PDF skip.
"""
import asyncio
from copy import deepcopy
import os
from pathlib import Path

import pytest


@pytest.fixture()
def fiscal_pg(monkeypatch):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from models import Base
    url=os.environ.get('FISCAL_TEST_POSTGRES_URL')
    if url!='postgresql+psycopg2://postgres@127.0.0.1:55432/fiscal_fixture':
        pytest.fail('required owned fiscal PostgreSQL fixture not provisioned')
    engine=create_engine(url)
    with engine.connect()as connection:
        assert connection.execute(text('select current_database()')).scalar()=='fiscal_fixture'
    Base.metadata.create_all(engine)
    try:
        with Session(engine)as db:yield db
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def candidate():
    import test_fiscal_framework_split as prior
    from seeding.domains.fiscal_summary.fetcher import _apply_fiscal_framework
    from seeding.domains.fiscal_summary.actuals import read_apdmr, apply_apdmr
    payload=prior._payload_as_revenue_step_leaves_it()
    _apply_fiscal_framework(payload,[(prior.URL_2627,prior._edition()),
        (prior.URL_2324,prior._edition('fy2023_24','FY 2023/24')),
        ('https://www.treasury.go.ke/sites/default/files/Budget%20summary/Budget-Summary-for-the-FY-2022_23.pdf',
         prior._edition('fy2022_23','FY 2022/23'))])
    apply_apdmr(payload,read_apdmr(Path(__file__).parent/'fixtures/fiscal_actuals/apdmr-2022-23.pdf'))
    return payload


def write(db,payload):
    from models import Country
    from seeding.domains.fiscal_summary.parser import parse_fiscal_summary_payload
    from seeding.domains.fiscal_summary.writer import write_fiscal_summary_records
    if not db.query(Country).count():
        db.add(Country(iso_code='KEN',name='Kenya',currency='KES',timezone='Africa/Nairobi',default_locale='en_KE'));db.flush()
    return write_fiscal_summary_records(db,parse_fiscal_summary_payload(payload),payload.get('metadata',{}))


def test_real_pg_writer_api_provenance_replay_and_rollback(fiscal_pg,monkeypatch):
    import main
    from models import FiscalSummary, SourceDocument
    from fastapi.testclient import TestClient
    from database import get_db
    db=fiscal_pg;payload=candidate()
    assert write(db,payload)==(5,0);db.commit()
    rows=db.query(FiscalSummary).order_by(FiscalSummary.fiscal_year).all()
    assert [float(r.total_revenue)for r in rows]==[2041119000000,2288900000000,2420200000000,2784400000000,2985700000000]
    assert float(rows[0].debt_service_cost)==1201033000000
    before=[(r.id,r.source_document_id,deepcopy(r.meta))for r in rows]
    assert write(db,payload)==(0,5);db.commit()
    assert [(r.id,r.source_document_id,r.meta)for r in rows]==before
    assert db.query(SourceDocument).count()==1
    main.clear_all_caches()
    main.app.dependency_overrides[get_db]=lambda:db
    monkeypatch.setattr(main,'get_db',lambda:iter([db]))
    try:
        with TestClient(main.app)as client:
            response=client.get('/api/v1/fiscal/summary')
            assert response.status_code==200,response.text
            historical=next(r for r in response.json()['history']if r['fiscal_year']=='FY 2022/23')
            assert historical['total_revenue']==2041119000000
            assert historical['debt_service_cost']==1201033000000
            assert historical['debt_service_per_shilling']==58.8
            other=next(r for r in response.json()['history']if r['fiscal_year']=='FY 2023/24')
            assert other['tax_revenue']==2167800000000
            assert other['non_tax_revenue']==121100000000
            assert historical['tax_revenue'] is None
            assert historical['non_tax_revenue'] is None
            assert historical['absent_reasons']['tax_revenue']
            proof=client.get('/api/v1/provenance/verify/fiscal_summaries?year=2022')
            assert proof.status_code==200,proof.text
            assert proof.json()['fiscal_measures']['total_revenue']==2041119000000
            out=client.get('/api/v1/dashboards/national/fiscal-outturns')
            assert out.status_code==200,out.text
            latest=out.json()['series'][0]
            assert latest['expenditure']==4785.2
            assert latest['column']=='Approved'
    finally:main.app.dependency_overrides.clear()
    altered=deepcopy(payload);altered['fiscal_years'][0]['total_revenue']=999
    altered['fiscal_years'][0]['fiscal_measure_contract']['measures'].pop('total_revenue')
    write(db,altered);db.rollback()
    db.expire_all()
    assert float(db.query(FiscalSummary).filter_by(fiscal_year='FY 2022/23').one().total_revenue)==2041119000000


def test_real_pg_legacy_api_does_not_borrow_budget_citation(fiscal_pg):
    import main
    from models import FiscalSummary
    from test_fiscal_measure_publication import legacy_row
    db=fiscal_pg;row=legacy_row();db.add(row);db.commit()
    main.clear_all_caches()
    body=asyncio.run(main.get_fiscal_summary(db=db))
    historical=body['current']
    for field in ('total_revenue','tax_revenue','non_tax_revenue','debt_service_cost','debt_service_per_shilling'):
        assert historical[field] is None
    assert historical['measure_qualifications']=={}


def test_real_pg_duplicate_input_and_partial_write_roll_back(fiscal_pg):
    from models import FiscalSummary
    from seeding.domains.fiscal_summary.parser import parse_fiscal_summary_payload
    db=fiscal_pg;payload=candidate();write(db,payload);db.commit()
    duplicate=deepcopy(payload);duplicate['fiscal_years'].append(duplicate['fiscal_years'][0])
    with pytest.raises(ValueError,match='duplicate'):parse_fiscal_summary_payload(duplicate)
    altered=deepcopy(payload);altered['fiscal_years'][1]['total_revenue']=True
    with pytest.raises(ValueError,match='boolean'):write(db,altered)
    db.rollback()
    assert db.query(FiscalSummary).count()==5
    assert float(db.query(FiscalSummary).filter_by(fiscal_year='FY 2022/23').one().total_revenue)==2041119000000


def test_real_pg_acquired_pdf_persists_actual_source_extraction(fiscal_pg,tmp_path):
    import httpx
    from models import FiscalSummary,SourceDocument,Extraction
    from seeding.config import SeedingSettings
    from seeding.http_client import SeedingHttpClient
    from seeding.domains.fiscal_summary.actuals import fetch_apdmr,apply_apdmr,APDMR_URL,APDMR_SHA256
    settings=SeedingSettings(_env_file=None,cache_path=tmp_path/'cache',storage_path=tmp_path/'storage',pdf_cache_ttl_seconds=0)
    body=(Path(__file__).parent/'fixtures/fiscal_actuals/apdmr-2022-23.pdf').read_bytes()
    # Inert HTTP transport, real official bytes, store readback, capability,
    # parser, writer and PostgreSQL. Live TLS is a separate source probe.
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=body,headers={'content-type':'application/pdf'})))as transport:
        with SeedingHttpClient(settings,client=transport)as client:
            payload=apply_apdmr({'fiscal_years':[{'fiscal_year':'FY 2022/23'}]},fetch_apdmr(client,settings))
    db=fiscal_pg;assert write(db,payload)==(1,0);db.commit()
    row=db.query(FiscalSummary).one()
    doc=db.query(SourceDocument).filter_by(id=row.source_document_id).one()
    assert doc.url==APDMR_URL
    assert doc.meta['source_sha256']==APDMR_SHA256
    proof=row.meta['fiscal_measure_contract']['measures']['total_revenue']
    extraction=db.query(Extraction).filter_by(id=proof['extraction_id']).one()
    assert extraction.source_document_id==doc.id
    assert extraction.page_number==37
    assert extraction.extracted_json['response_receipt']['digest']==APDMR_SHA256
    assert any(o['identity']['measure']=='total_revenue'and float(o['value'])==2041119000000
               for o in extraction.extracted_json['response_receipt']['observations'])
    assert any(o['identity']['measure']=='debt_service_cost'and float(o['value'])==1201033000000
               for o in extraction.extracted_json['response_receipt']['observations'])


def test_real_pg_cached_replay_preserves_exact_original_association(fiscal_pg,tmp_path):
    import httpx
    import main
    from models import FiscalSummary,Extraction
    from seeding.config import SeedingSettings
    from seeding.http_client import SeedingHttpClient
    from seeding.domains.fiscal_summary.actuals import fetch_apdmr,apply_apdmr
    settings=SeedingSettings(_env_file=None,cache_path=tmp_path/'cache',storage_path=tmp_path/'storage',pdf_cache_ttl_seconds=3600)
    body=(Path(__file__).parent/'fixtures/fiscal_actuals/apdmr-2022-23.pdf').read_bytes()
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=body,headers={'content-type':'application/pdf'})))as transport:
        with SeedingHttpClient(settings,client=transport)as client:
            payload=apply_apdmr({'fiscal_years':[{'fiscal_year':'FY 2022/23'}]},fetch_apdmr(client,settings))
    db=fiscal_pg;write(db,payload);db.commit()
    row=db.query(FiscalSummary).one();before=deepcopy(row.meta);source_id=row.source_document_id
    main.clear_all_caches()
    api=asyncio.run(main.get_fiscal_summary(db=db))
    assert api['current']['total_revenue']==2041119000000
    assert api['current']['debt_service_per_shilling']==58.8
    with httpx.Client(transport=httpx.MockTransport(lambda r:pytest.fail('fresh-client cache replay must not download')))as transport:
        with SeedingHttpClient(settings,client=transport)as client:
            parsed=fetch_apdmr(client,settings)
            assert '_response_receipt' not in parsed
            replay=apply_apdmr({'fiscal_years':[{'fiscal_year':'FY 2022/23'}]},parsed)
    assert write(db,replay)==(0,1);db.commit();db.refresh(row)
    assert row.source_document_id==source_id
    assert row.meta==before
    assert db.query(Extraction).count()==1


@pytest.mark.parametrize('hostile',['publisher','country','duplicate','retention'])
def test_real_pg_hostile_source_association_and_retention_refuse(fiscal_pg,tmp_path,hostile):
    import httpx
    from datetime import datetime,timezone
    from models import Country,FiscalSummary,SourceDocument,DocumentType,Extraction
    from seeding.config import SeedingSettings
    from seeding.http_client import SeedingHttpClient
    from seeding.domains.fiscal_summary.actuals import fetch_apdmr,apply_apdmr,APDMR_SHA256,APDMR_URL
    settings=SeedingSettings(_env_file=None,cache_path=tmp_path/'cache',storage_path=tmp_path/'storage',pdf_cache_ttl_seconds=3600)
    body=(Path(__file__).parent/'fixtures/fiscal_actuals/apdmr-2022-23.pdf').read_bytes()
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=body,headers={'content-type':'application/pdf'})))as transport:
        with SeedingHttpClient(settings,client=transport)as client:
            parsed=fetch_apdmr(client,settings)
            payload=apply_apdmr({'fiscal_years':[{'fiscal_year':'FY 2022/23'}]},parsed)
    db=fiscal_pg
    if hostile=='retention':
        receipt=parsed['_response_receipt'];key=receipt['storage_key']
        receipt._store._path(key).unlink()
        with pytest.raises(ValueError,match='retention unconfirmed'):write(db,payload)
        assert db.query(FiscalSummary).count()==0
        assert db.query(Extraction).count()==0
        return
    write(db,payload);db.commit()
    row=db.query(FiscalSummary).one();original_id=row.source_document_id
    doc=db.get(SourceDocument,original_id)
    if hostile=='publisher':doc.publisher='Wrong publisher'
    elif hostile=='country':
        other=Country(iso_code='ZZZ',name='Inert other',currency='KES',timezone='UTC',default_locale='en')
        db.add(other);db.flush();doc.country_id=other.id
    else:
        db.add(SourceDocument(country_id=doc.country_id,publisher=doc.publisher,title=doc.title,
            url=APDMR_URL,fetch_date=doc.fetch_date,doc_type=DocumentType.REPORT,meta={'source_sha256':APDMR_SHA256}))
    db.commit()
    with httpx.Client(transport=httpx.MockTransport(lambda r:pytest.fail('cache expected')))as transport:
        with SeedingHttpClient(settings,client=transport)as client:
            replay=apply_apdmr({'fiscal_years':[{'fiscal_year':'FY 2022/23'}]},fetch_apdmr(client,settings))
    with pytest.raises(ValueError,match='ambiguous|association missing'):write(db,replay)
    db.expire_all()
    assert db.query(FiscalSummary).one().source_document_id==original_id


@pytest.mark.parametrize('hostile',['source_id','primary_source_id','extractor','period','basis','unit','parser'])
def test_real_pg_retained_manifest_tampering_refuses(fiscal_pg,tmp_path,hostile):
    import httpx
    from models import FiscalSummary,Extraction
    from seeding.config import SeedingSettings
    from seeding.http_client import SeedingHttpClient
    from seeding.domains.fiscal_summary.actuals import fetch_apdmr,apply_apdmr
    settings=SeedingSettings(_env_file=None,cache_path=tmp_path/'cache',storage_path=tmp_path/'storage',pdf_cache_ttl_seconds=3600)
    body=(Path(__file__).parent/'fixtures/fiscal_actuals/apdmr-2022-23.pdf').read_bytes()
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=body,headers={'content-type':'application/pdf'})))as transport:
        with SeedingHttpClient(settings,client=transport)as client:
            payload=apply_apdmr({'fiscal_years':[{'fiscal_year':'FY 2022/23'}]},fetch_apdmr(client,settings))
    db=fiscal_pg;write(db,payload);db.commit()
    row=db.query(FiscalSummary).one();original_source=row.source_document_id
    proof=row.meta['fiscal_measure_contract']['measures']['total_revenue']
    extraction=db.get(Extraction,proof['extraction_id'])
    if hostile=='source_id':
        meta=deepcopy(row.meta);meta['fiscal_measure_contract']['measures']['total_revenue']['source_document_id']=True;row.meta=meta
    elif hostile=='primary_source_id':
        from models import SourceDocument
        row.source_document_id=db.query(SourceDocument).filter(SourceDocument.id!=original_source).one().id
    elif hostile=='extractor':extraction.extractor='unknown-parser'
    else:
        data=deepcopy(extraction.extracted_json)
        if hostile=='parser':data['response_receipt']['parser_version']='unknown-parser'
        else:data['response_receipt']['observations'][0]['identity'][hostile]='wrong'
        extraction.extracted_json=data
    db.commit()
    with httpx.Client(transport=httpx.MockTransport(lambda r:pytest.fail('cache expected')))as transport:
        with SeedingHttpClient(settings,client=transport)as client:
            replay=apply_apdmr({'fiscal_years':[{'fiscal_year':'FY 2022/23'}]},fetch_apdmr(client,settings))
    with pytest.raises(ValueError,match='retained fiscal'):write(db,replay)
    db.expire_all()
    expected_source=original_source if hostile!='primary_source_id'else db.query(SourceDocument).filter(SourceDocument.id!=original_source).one().id
    assert db.query(FiscalSummary).one().source_document_id==expected_source


def test_real_pg_direct_writer_duplicate_periods_refuse_atomically(fiscal_pg):
    from models import FiscalSummary
    from seeding.domains.fiscal_summary.parser import parse_fiscal_summary_payload
    from seeding.domains.fiscal_summary.writer import write_fiscal_summary_records
    db=fiscal_pg;payload=candidate();write(db,payload);db.commit()
    records=parse_fiscal_summary_payload(payload)
    with pytest.raises(ValueError,match='duplicate fiscal year'):
        write_fiscal_summary_records(db,[records[0],records[0]],{})
    db.expire_all()
    assert db.query(FiscalSummary).count()==5
    assert float(db.query(FiscalSummary).filter_by(fiscal_year='FY 2022/23').one().total_revenue)==2041119000000


def test_real_pg_direct_contradictory_record_preserves_last_good(fiscal_pg):
    from models import FiscalSummary
    from seeding.domains.fiscal_summary.parser import parse_fiscal_summary_payload
    from seeding.domains.fiscal_summary.writer import write_fiscal_summary_records
    db=fiscal_pg;payload=candidate();write(db,payload);db.commit()
    row=db.query(FiscalSummary).filter_by(fiscal_year='FY 2022/23').one()
    before=(row.total_revenue,row.source_document_id,deepcopy(row.meta))
    records=parse_fiscal_summary_payload(payload);records[0].total_revenue=2042
    with pytest.raises(ValueError,match='proof contradicts writer amount'):
        write_fiscal_summary_records(db,records,{})
    db.expire_all();row=db.query(FiscalSummary).filter_by(fiscal_year='FY 2022/23').one()
    assert (row.total_revenue,row.source_document_id,row.meta)==before


@pytest.mark.parametrize('contract',[{'version':'future-v2','measures':{}},{'version':'fiscal-measures-v1','measures':[]}])
def test_real_pg_direct_writer_unknown_contract_preserves_rows(fiscal_pg,contract):
    from models import FiscalSummary
    from seeding.domains.fiscal_summary.parser import parse_fiscal_summary_payload
    from seeding.domains.fiscal_summary.writer import write_fiscal_summary_records
    db=fiscal_pg;payload=candidate();write(db,payload);db.commit()
    records=parse_fiscal_summary_payload(payload);records[0].fiscal_measure_contract=contract
    with pytest.raises(ValueError,match='unknown or malformed fiscal measure contract'):
        write_fiscal_summary_records(db,records,{})
    assert db.query(FiscalSummary).count()==5


def test_real_pg_failed_actual_fetch_preserves_last_good_acquisition(fiscal_pg,tmp_path):
    import httpx
    from models import FiscalSummary
    from seeding.config import SeedingSettings
    from seeding.http_client import SeedingHttpClient
    from seeding.domains.fiscal_summary.actuals import fetch_apdmr,apply_apdmr
    from seeding.domains.fiscal_summary.fetcher import fetch_fiscal_summary_payload
    from services.fiscal_qualification import fiscal_values
    fixture=Path(__file__).parent/'fixtures/fiscal_actuals/apdmr-2022-23.pdf'
    settings=SeedingSettings(_env_file=None,cache_path=tmp_path/'cache',storage_path=tmp_path/'storage',pdf_cache_ttl_seconds=0)
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=fixture.read_bytes(),headers={'content-type':'application/pdf'})))as transport:
        with SeedingHttpClient(settings,client=transport)as client:
            payload=apply_apdmr({'fiscal_years':[{'fiscal_year':'FY 2022/23'}]},fetch_apdmr(client,settings))
    db=fiscal_pg;write(db,payload);db.commit()
    row=db.query(FiscalSummary).one();before=(row.source_document_id,deepcopy(row.meta),row.total_revenue,row.debt_service_cost)
    # Exact live failure plus absent PDF cache; the real fetcher returns its older fallback.
    for path in (tmp_path/'cache').rglob('*.pdf'):
        path.unlink()
    def unavailable(request):raise httpx.ConnectError('inert unavailable official source',request=request)
    with httpx.Client(transport=httpx.MockTransport(unavailable))as transport:
        with SeedingHttpClient(settings,client=transport)as client:
            fallback=fetch_fiscal_summary_payload(client,settings)
    assert next(r for r in fallback['fiscal_years']if r['fiscal_year']=='FY 2022/23')['total_revenue']==2042
    write(db,fallback);db.commit();db.refresh(row)
    assert (row.source_document_id,row.total_revenue,row.debt_service_cost)==(before[0],before[2],before[3])
    assert row.meta['fiscal_measure_contract']==before[1]['fiscal_measure_contract']
    assert row.meta['source_evidence']==before[1]['source_evidence']
    assert set(row.meta['retained_measure_fields'])=={'total_revenue','debt_service_cost'}
    assert fiscal_values(row)['debt_service_per_shilling']==58.8


@pytest.mark.parametrize('field,bad',[('basis','total_including_aia'),('vintage','unknown'),('vintage','Approved'),('source',{}),('fiscal_year','FY 2023/24'),('precision_kes',0)])
def test_real_pg_invalid_proof_semantics_preserves_last_good(fiscal_pg,field,bad):
    from models import FiscalSummary
    from seeding.domains.fiscal_summary.parser import parse_fiscal_summary_payload
    from seeding.domains.fiscal_summary.writer import write_fiscal_summary_records
    db=fiscal_pg;payload=candidate();write(db,payload);db.commit()
    row=db.query(FiscalSummary).filter_by(fiscal_year='FY 2022/23').one()
    before=(row.total_revenue,row.source_document_id,deepcopy(row.meta))
    records=parse_fiscal_summary_payload(payload)
    records[0].fiscal_measure_contract=deepcopy(records[0].fiscal_measure_contract)
    records[0].fiscal_measure_contract['measures']['total_revenue'][field]=bad
    with pytest.raises(ValueError,match='invalid fiscal measure proof semantics'):
        write_fiscal_summary_records(db,records,{})
    db.expire_all();row=db.query(FiscalSummary).filter_by(fiscal_year='FY 2022/23').one()
    assert (row.total_revenue,row.source_document_id,row.meta)==before


def test_fy2022_23_outturn_links_two_sources_and_preserves_rows_on_refusal(
    fiscal_pg, monkeypatch, tmp_path
):
    import hashlib
    from types import SimpleNamespace

    import httpx

    from models import Extraction, FiscalSummary, SourceDocument
    from seeding.config import SeedingSettings
    from seeding.domains.fiscal_summary import actuals, historical_outturn as outturn
    from seeding.http_client import SeedingHttpClient
    from seeding import fiscal_historical_sources as reviewed
    from services.fiscal_qualification import fiscal_values, published_framework

    # The large official editions are covered by the exact-byte replay.
    # This fixture mutates only the reviewed bytes and PDF-reader seam.
    bodies = {
        actuals.APDMR_URL: (Path(__file__).parent / "fixtures/fiscal_actuals/apdmr-2022-23.pdf").read_bytes(),
        outturn.OUTTURN_URL: b"%PDF-1.7\nFixture outturn\n%%EOF",
        outturn.REVENUE_URL: b"%PDF-1.7\nFixture tax\n%%EOF",
    }
    for url, variable in ((outturn.OUTTURN_URL, "OUTTURN_SHA256"), (outturn.REVENUE_URL, "REVENUE_SHA256")):
        digest = hashlib.sha256(bodies[url]).hexdigest()
        monkeypatch.setattr(outturn, variable, digest)
        monkeypatch.setattr(reviewed, variable, digest)
        monkeypatch.setitem(outturn.EDITIONS, url, (digest, *outturn.EDITIONS[url][1:]))

    values = {
        "total_revenue": 2360.5, "ordinary_revenue": 2041.1, "ministerial_aia": 319.4,
        "expenditure": 3221.0, "recurrent": 2311.6, "interest": 687.3, "development": 493.7,
        "county_transfers": 415.8, "equitable_share": 399.6, "contingency": 0.0,
        "grants": 23.1, "fiscal_balance": -837.4, "adjustment_to_cash_basis": 37.0,
        "statistical_discrepancy": -30.1, "total_financing": 770.3,
        "net_foreign_financing": 310.8, "net_domestic_financing": 459.5, "nominal_gdp": 14299.2,
    }
    monkeypatch.setattr(outturn, "_read_outturn", lambda _path: SimpleNamespace(
        values=values, fiscal_year=actuals.FY, identified_by="printed_actual_column",
        column_label="Actual", checks=[], tax_split_ok=False,
        tax_split_reason="edition_prints_no_tax_or_non_tax_row",
    ))
    unavailable = set()
    changed = set()

    def serve(request):
        url = str(request.url)
        if url in unavailable:
            return httpx.Response(503, content=b"fixture unavailable")
        body = bodies[url]
        if url in changed:
            body = body.replace(b"Fixture", b"Changed")
        return httpx.Response(200, content=body, headers={"content-type": "application/pdf"})

    settings = SeedingSettings(_env_file=None, cache_path=tmp_path / "cache",
        storage_path=tmp_path / "storage", max_retries=1, http_cache_enabled=False)
    with SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(serve))) as client:
        baseline = {"fiscal_years": [{"fiscal_year": actuals.FY}]}
        actuals.apply_apdmr(baseline, actuals.fetch_apdmr(client, settings))
        payload = deepcopy(baseline)
        outturn.apply_historical_outturn(payload, client, settings)
        db = fiscal_pg
        assert write(db, payload) == (1, 0)
        db.commit()
        row = db.query(FiscalSummary).one()
        expected = fiscal_values(row)
        assert expected["tax_revenue"] == 1_961_974_000_000
        assert expected["non_tax_revenue"] == 79_145_000_000
        assert expected["debt_service_per_shilling"] == 58.8
        assert published_framework(row)["total_expenditure_billion"] == 3221
        import main
        main.clear_all_caches()
        served = asyncio.run(main.get_fiscal_summary(db=db))["current"]
        assert served["tax_revenue"] == expected["tax_revenue"]
        assert served["debt_service_per_shilling"] == 58.8
        for field, url in (("tax_revenue", outturn.REVENUE_URL),
                           ("total_borrowing", outturn.OUTTURN_URL),
                           ("total_revenue", actuals.APDMR_URL)):
            proof = expected["measure_qualifications"][field]
            source = db.get(SourceDocument, proof["source_document_id"])
            extraction = db.get(Extraction, proof["extraction_id"])
            assert source.url == url == proof["source"]["url"]
            assert extraction.source_document_id == source.id
            assert extraction.extracted_json["response_receipt"]["digest"] == proof["source"]["sha256"]
        assert db.query(Extraction).count() == 3
        assert write(db, payload) == (0, 1)
        db.commit()
        assert db.query(Extraction).count() == 3
        snapshot = (deepcopy(row.meta), row.source_document_id, row.updated_at)
        exported = deepcopy(payload)
        exported["fiscal_years"][0].pop("historical_outturn_evidence")
        with pytest.raises(ValueError, match="both sealed acquisitions"):
            write(db, exported)
        db.rollback()
        for url, reject in ((outturn.OUTTURN_URL, unavailable), (outturn.REVENUE_URL, changed)):
            reject.add(url)
            retry = deepcopy(baseline)
            with pytest.raises((ValueError, httpx.HTTPError)):
                outturn.apply_historical_outturn(retry, client, settings)
            reject.clear()
            assert retry == baseline
            assert write(db, retry) == (0, 1)
            db.commit()
            assert (row.meta, row.source_document_id, row.updated_at) == snapshot
            assert fiscal_values(row) == expected
        assert db.query(Extraction).count() == 3

        from seeding.domains.fiscal_summary import fetcher
        from seeding.refresh_completion import fiscal_components_complete

        def no_other_budget_sources(*_args, **_kwargs):
            return None, "fixture not selected"

        # Keep the actual fetcher's completeness decision. Only the unrelated
        # source probes are fixtures; the historical acquisition still runs.
        legacy_url = "https://www.treasury.go.ke/fixture-budget-summary.pdf"
        monkeypatch.setattr(fetcher, "load_json_resource", lambda **_: deepcopy(baseline))
        monkeypatch.setattr(fetcher, "_fetch_cob_headlines", lambda *_: (None, None, actuals.FY))
        monkeypatch.setattr(fetcher, "_overlay_live_budget_headline", lambda data, *_a, **_k: (data, "promoted"))
        monkeypatch.setattr(fetcher, "_fetch_budget_estimates", no_other_budget_sources)
        monkeypatch.setattr(fetcher, "_fetch_revenue_estimates", no_other_budget_sources)
        monkeypatch.setattr(fetcher, "_fetch_budget_summary_editions", lambda *_: (
            [], {fetcher.LISTING_EDITIONS_FACT: {legacy_url: {"status": "unreadable(ConnectError)"}}}
        ))
        monkeypatch.setattr(fetcher, "_apply_fiscal_framework", lambda data, *_a, **_k: (data, "applied=[]"))
        refreshed = fetcher.fetch_fiscal_summary_payload(client, settings)["_run_facts"]
        assert refreshed["historical_outturn"]["state"] == "verified"
        assert refreshed["refresh_components"]["framework"]["unreadable_editions"] == {
            legacy_url: "unreadable(ConnectError)"
        }
        assert not fiscal_components_complete(refreshed["refresh_components"], [actuals.FY])
        unavailable.add(outturn.REVENUE_URL)
        monkeypatch.setattr(fetcher, "_fetch_budget_summary_editions", lambda *_: (
            [], {fetcher.LISTING_EDITIONS_FACT: {legacy_url: {"status": "read"}}}
        ))
        held = fetcher.fetch_fiscal_summary_payload(client, settings)["_run_facts"]
        assert held["historical_outturn"]["state"] == "unconfirmed"
        assert not fiscal_components_complete(held["refresh_components"], [actuals.FY])

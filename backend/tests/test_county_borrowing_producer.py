"""Synthetic source->native owner->real PostgreSQL->public reader/API controls."""
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
from hashlib import sha256, md5
from io import BytesIO
from pathlib import Path
import os

import pdfplumber
import pytest
from sqlalchemy import select, text

from models import (Entity, CountyDebtInstrument, CountyDebtObservation, SourceDocument,
    Extraction, Loan, DebtCategory, FigureBasis, IngestionJob, IngestionStatus)
from seeding import county_borrowing_contract as contract
from seeding.config import SeedingSettings
from seeding.domains.county_borrowing import writer, run
from seeding.types import DomainRunContext
from services.county_debt import county_debt_rows, record_county_debt_observation
from services.county_borrowing_coverage import county_borrowing_coverage
from services.financial_publication import county_debt_summary
from county_borrowing_fixture import borrowing_pg, owned, pdf_bytes  # noqa: F401


@pytest.fixture
def specimen(monkeypatch, tmp_path):
    lines = ['County: Kisii county; Identity namespace: owned-synthetic-register;',
        'Contract reference: SYNTH-1; Lender: Synthetic Bank; Issue date: 2020-01-01;',
        'As at: 2025-06-30; Currency: KES; Unit: units; Basis: actual;',
        'Obligation: direct_county_borrowing; Principal: 100.00; Outstanding: 20.00;',
        'Interest rate: not reported;']
    body=pdf_bytes(['OWNED SYNTHETIC - not live evidence', *lines])
    with pdfplumber.open(BytesIO(body)) as pdf:
        text_page=' '.join(pdf.pages[0].extract_text().split())
    spec={'id':'owned_synthetic', 'url':'https://example.invalid/owned-county.pdf',
        'sha256':sha256(body).hexdigest(), 'md5':md5(body,usedforsecurity=False).hexdigest(), 'size_bytes':len(body), 'page_count':1,
        'pages':{'1':sha256(text_page.encode()).hexdigest()}, 'publisher':'Owned synthetic fixture',
        'title':'Owned synthetic contract stock', 'scope':'owned_synthetic_contract',
        'county_slugs':['kisii-county'], 'status':'selected_instrument_stock',
        'reason':'Synthetic control only; not a Kenyan financial qualification',
        'reporting_period_end':'2025-06-30', 'instruments':[{
            'county_slug':'kisii-county','obligation_kind':'direct_county_borrowing',
            'identity_namespace':'owned-synthetic-register', 'instrument_reference':'SYNTH-1',
            'lender':'Synthetic Bank','issue_date':'2020-01-01T00:00:00', 'currency':'KES',
            'as_at':'2025-06-30','page_ref':'p.1','basis':'actual',
            'principal':'100.00','outstanding':'20.00','debt_category':'county_guaranteed',
            'source_evidence': {
                'format':'labelled_contract_stock_v1', 'statement':' '.join(lines),
                'currency_text':'KES', 'unit':'units', 'unit_text':'units', 'stock_label':'Outstanding',
                'fields':{'county_name':'Kisii county', 'identity_namespace':'owned-synthetic-register', 'instrument_reference':'SYNTH-1',
                    'lender':'Synthetic Bank', 'issue_date':'2020-01-01', 'as_at':'2025-06-30',
                    'principal':'100.00', 'outstanding':'20.00', 'interest_rate':None}}}]}
    monkeypatch.setattr(contract, 'EDITIONS', {spec['id']:spec})
    settings=SeedingSettings(_env_file=None,county_borrowing_ingestion_enabled=True,storage_path=tmp_path)
    return spec, body, settings


def persist(factory, ctx, specimen, parsed=None, fetched_at=None):
    spec, body, settings=specimen
    with factory.begin() as db:
        return writer.persist(db,settings,ctx,spec['id'],body,
            contract.parse_publication(spec['id'],body) if parsed is None else parsed,
            datetime.now(timezone.utc) if fetched_at is None else fetched_at)


def summary(factory):
    with factory() as db:
        entity=db.scalar(select(Entity).where(Entity.slug=='kisii-county'))
        return county_debt_summary(county_debt_rows(db,[entity.id]))


def effects(factory):
    with factory() as db:
        return tuple(db.scalar(text('SELECT count(*) FROM '+t)) for t in
            ('source_documents','extractions','county_debt_instruments','county_debt_observations'))


def test_source_to_stock_and_exact_replay(borrowing_pg, specimen):
    _,factory=borrowing_pg
    with owned(factory) as ctx:
        assert persist(factory,ctx,specimen)=={'created':1,'unchanged':0,'instruments':1}
        assert summary(factory)['total_debt']==20
        assert persist(factory,ctx,specimen)=={'created':0,'unchanged':1,'instruments':1}
        assert effects(factory)==(1,1,1,1)
        with factory() as db:
            doc=db.scalar(select(SourceDocument)); extraction=db.scalar(select(Extraction)); obs=db.scalar(select(CountyDebtObservation))
            assert obs.provenance['extraction_id']==extraction.id
            assert doc.meta['artifact_sha256']==specimen[0]['sha256']==obs.provenance['artifact_sha256']
            assert county_borrowing_coverage(db,[db.get(CountyDebtInstrument,obs.instrument_id).entity_id])[db.get(CountyDebtInstrument,obs.instrument_id).entity_id]['sources'][0]['pdf_pages']==[1]
        store=writer.configured_receipt_store(specimen[2])
        assert store.read(specimen[0]['sha256'])==specimen[1]


def test_no_write_dry_run(borrowing_pg,specimen):
    _,factory=borrowing_pg
    with owned(factory,True) as ctx:
        assert persist(factory,ctx,specimen)=={'created':0,'unchanged':0,'instruments':0}
        assert effects(factory)==(0,0,0,0)
        assert not (specimen[2].storage_path/'response-receipts').exists()


@pytest.mark.parametrize('change',[True,{},float('nan'),-1,'20.0'])
def test_direct_caller_cannot_change_parsed_evidence(borrowing_pg,specimen,change):
    _,factory=borrowing_pg
    with owned(factory) as ctx:
        parsed=contract.parse_publication(specimen[0]['id'],specimen[1]);parsed['instruments'][0]['outstanding']=change
        with pytest.raises(contract.CountyBorrowingRefused):persist(factory,ctx,specimen,parsed)
        assert effects(factory)==(0,0,0,0)


@pytest.mark.parametrize('kind',['proposal','national_guarantee','inherited_debt','pending_bills','national_creditor_aggregate'])
def test_non_contract_measures_refuse_before_database_effects(borrowing_pg,specimen,kind):
    _,factory=borrowing_pg
    specimen[0]['instruments'][0]['obligation_kind']=kind
    with owned(factory) as ctx:
        with pytest.raises(contract.CountyBorrowingRefused,match='actual county contract'):persist(factory,ctx,specimen)
        assert effects(factory)==(0,0,0,0)


def test_direct_calls_disabled_unowned_or_lost_lock_cannot_write(borrowing_pg,specimen):
    _,factory=borrowing_pg
    with pytest.raises(contract.CountyBorrowingRefused):persist(factory,DomainRunContext(since=None,dry_run=False),specimen)
    with owned(factory) as ctx:
        specimen[2].county_borrowing_ingestion_enabled=False
        with pytest.raises(contract.CountyBorrowingRefused,match='disabled'):persist(factory,ctx,specimen)
        specimen[2].county_borrowing_ingestion_enabled=True
        ctx.ownership.close()
        with pytest.raises(contract.CountyBorrowingRefused,match='lock'):persist(factory,ctx,specimen)
    assert effects(factory)==(0,0,0,0)


@pytest.mark.parametrize('delta',[-10000,10000])
def test_stale_and_future_fetches_refuse(borrowing_pg,specimen,delta):
    _,factory=borrowing_pg
    with owned(factory) as ctx:
        with pytest.raises(contract.CountyBorrowingRefused,match='fetch time'):
            persist(factory,ctx,specimen,fetched_at=datetime.now(timezone.utc)+timedelta(seconds=delta))
        assert effects(factory)==(0,0,0,0)


def test_caught_writer_error_rolls_back_source_and_instrument(borrowing_pg,specimen):
    _,factory=borrowing_pg
    specimen[0]['instruments'][0]['outstanding']='-1'
    with owned(factory) as ctx:
        with factory.begin() as db:
            with pytest.raises(ValueError,match='monetary'):
                writer.persist(db,specimen[2],ctx,specimen[0]['id'],specimen[1],
                    contract.parse_publication(specimen[0]['id'],specimen[1]),datetime.now(timezone.utc))
        assert effects(factory)==(0,0,0,0)


def test_latest_null_blocks_old_nonzero_and_zero_is_not_missing(borrowing_pg,specimen):
    _,factory=borrowing_pg
    with owned(factory) as ctx:persist(factory,ctx,specimen)
    with factory.begin() as db:
        instrument=db.scalar(select(CountyDebtInstrument));doc=db.scalar(select(SourceDocument))
        args=dict(entity_id=instrument.entity_id,identity_namespace=instrument.identity_namespace,
            instrument_reference=instrument.instrument_reference,lender=instrument.lender,
            issue_date=instrument.issue_date,currency='KES',source_document_id=doc.id,
            page_ref='p.1',basis=FigureBasis.ACTUAL,principal='100.00')
        record_county_debt_observation(db,as_at=date(2026,6,30),outstanding=None,**args)
    assert summary(factory)['total_debt'] is None
    with factory.begin() as db:
        record_county_debt_observation(db,as_at=date(2026,6,30),outstanding='0.00',correct=True,**args)
    out=summary(factory)
    assert out['total_debt']==0 and out['debt_source_coverage']['status']=='dated_explicit_zero'
    with factory.begin() as db:
        with pytest.raises(ValueError,match='explicit correction'):
            record_county_debt_observation(db,as_at=date(2026,6,30),outstanding='5.00',**args)
    assert summary(factory)['total_debt']==0


def test_actual_native_cli_runs_and_releases_owner(borrowing_pg,specimen,monkeypatch):
    import seeding.cli as cli
    import seeding.registries as registries
    from argparse import Namespace
    _,factory=borrowing_pg
    monkeypatch.setenv('SEED_COUNTY_BORROWING_INGESTION_ENABLED','true')
    monkeypatch.setattr(cli,'SessionLocal',factory)
    monkeypatch.setitem(registries.REGISTRY._handlers,'county_borrowing',run)
    monkeypatch.setattr(contract,'fetch_publication',lambda key:(specimen[1],datetime.now(timezone.utc)))
    args=Namespace(domain=['county_borrowing'],all=False,since=None,dry_run=False)
    assert cli.run_seed_command(args,specimen[2])==0
    with factory() as db:
        job=db.scalar(select(IngestionJob).where(IngestionJob.domain=='county_borrowing'))
        assert job.status==IngestionStatus.COMPLETED
        assert job.meta['instrument_observations']==1
        assert db.scalar(text('SELECT count(*) FROM seeding_domain_claims WHERE returned_at IS NOT NULL AND released_at IS NOT NULL'))==1
    assert summary(factory)['total_debt']==20


def test_reviewed_official_editions_keep_null_and_scoped_coverage(borrowing_pg,monkeypatch,tmp_path):
    root=os.environ.get('B83_COUNTY_OFFICIAL_EVIDENCE')
    if not root:pytest.skip('Requires separately retained hash-identified official PDFs')
    import json
    specs=json.loads((Path(contract.__file__).with_name('fixtures')/'county_borrowing_editions.json').read_text())
    monkeypatch.setattr(contract,'EDITIONS',{s['id']:s for s in specs})
    _,factory=borrowing_pg
    settings=SeedingSettings(_env_file=None,county_borrowing_ingestion_enabled=True,storage_path=tmp_path)
    with owned(factory) as ctx:
        for spec,index in zip(specs,[1,2]):
            body=(Path(root)/f'source-{index}.pdf').read_bytes()
            assert sha256(body).hexdigest()==spec['sha256']
            with factory.begin() as db:
                writer.persist(db,settings,ctx,spec['id'],body,contract.parse_publication(spec['id'],body),datetime.now(timezone.utc))
    assert effects(factory)==(2,2,0,0)
    with factory() as db:
        entities=db.scalars(select(Entity)).all()
        coverage=county_borrowing_coverage(db,[e.id for e in entities])
        assert {coverage[e.id]['status'] for e in entities}=={'not_reported_in_checked_source','withheld_or_conflicting'}
        for e in entities:
            out=county_debt_summary(county_debt_rows(db,[e.id]),source_coverage=coverage[e.id])
            assert out['total_debt'] is None and out['debt_source_coverage']['complete_liability_coverage'] is False

@pytest.mark.parametrize('missing',[('county_debt_instruments','county_debt_observations'),('county_debt_observations',)])
def test_absent_or_partial_schema_refuses_before_effects(borrowing_pg,specimen,missing):
    _,factory=borrowing_pg
    with factory.begin() as db:
        for table in missing:db.execute(text('DROP TABLE '+table+' CASCADE'))
    with owned(factory) as ctx:
        with pytest.raises((contract.CountyBorrowingRefused,RuntimeError),match='schema'):
            persist(factory,ctx,specimen)
    with factory() as db:
        assert db.scalar(text('SELECT count(*) FROM source_documents'))==0
        assert db.scalar(text('SELECT count(*) FROM extractions'))==0


def test_reissue_and_stored_tampering_refuse(borrowing_pg,specimen):
    _,factory=borrowing_pg
    spec,body,settings=specimen
    with owned(factory) as ctx:
        persist(factory,ctx,specimen)
        with factory.begin() as db:
            doc=db.scalar(select(SourceDocument));doc.meta={**doc.meta,'artifact_bytes':True}
        with pytest.raises(contract.CountyBorrowingRefused,match='provenance'):persist(factory,ctx,specimen)
        with pytest.raises(contract.CountyBorrowingRefused,match='edition changed'):
            contract.parse_publication(spec['id'],body.replace(b'20.00',b'25.00'))
    assert effects(factory)==(1,1,1,1)


def test_two_concurrent_replays_use_one_source_and_instrument(borrowing_pg,specimen):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    _,factory=borrowing_pg
    with owned(factory) as ctx:
        barrier=Barrier(2)
        def invoke():
            barrier.wait(timeout=5)
            return persist(factory,ctx,specimen)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:invoke(),range(2)))
        assert sorted(r['created'] for r in results)==[0,1]
    assert effects(factory)==(1,1,1,1)


def test_mixed_legacy_and_competing_sources_withhold_instead_of_adding(borrowing_pg,specimen):
    _,factory=borrowing_pg
    with owned(factory) as ctx:persist(factory,ctx,specimen)
    with factory.begin() as db:
        instrument=db.scalar(select(CountyDebtInstrument)); doc=db.scalar(select(SourceDocument))
        db.add(Loan(entity_id=instrument.entity_id,lender='Owned legacy loan',issue_date=instrument.issue_date,
            currency='KES',debt_category=DebtCategory.COUNTY_GUARANTEED,principal=100,outstanding=10,
            source_document_id=doc.id,basis=FigureBasis.ACTUAL,provenance={'as_at':'2025-06-30'},page_ref='p.1'))
    assert summary(factory)['total_debt_absent_reason']=='mixed_instrument_representations'
    with factory.begin() as db:
        instrument=db.scalar(select(CountyDebtInstrument)); doc=db.scalar(select(SourceDocument))
        db.query(Loan).delete()
        competitor=SourceDocument(country_id=doc.country_id,publisher='Owned competing source',title='Owned competing account',
            url='https://example.invalid/competing.pdf',doc_type=doc.doc_type,fetch_date=datetime.now(timezone.utc))
        db.add(competitor);db.flush()
        record_county_debt_observation(db,entity_id=instrument.entity_id,identity_namespace=instrument.identity_namespace,
            instrument_reference=instrument.instrument_reference,lender=instrument.lender,issue_date=instrument.issue_date,
            currency='KES',as_at=date(2025,6,30),source_document_id=competitor.id,page_ref='p.1',
            basis=FigureBasis.ACTUAL,outstanding=20)
    assert summary(factory)['total_debt_absent_reason']=='duplicate_instrument_observations'


def test_source_to_actual_public_api(borrowing_pg,specimen,monkeypatch):
    import main,database
    from fastapi.testclient import TestClient
    _,factory=borrowing_pg
    with owned(factory) as ctx:persist(factory,ctx,specimen)
    assert main.AUTO_SEEDER_ENABLED is False
    def get_db():
        with factory() as db:yield db
    monkeypatch.setattr(main,'get_db',get_db)
    main.app.dependency_overrides[database.get_db]=get_db
    client=TestClient(main.app,raise_server_exceptions=False)
    try:
        for path in ['/api/v1/counties/code:045','/api/v1/counties/code:045/comprehensive','/api/v1/counties/code:045/debt']:
            main.clear_all_caches()
            response=client.get(path)
            assert response.status_code==200,(path,response.text[:500])
            body=response.json();body=body['debt'] if path.endswith('/comprehensive') else body
            assert body['total_debt']==20,(path,body)
            assert body['debt_source_coverage']['status']=='selected_instrument_stock'
    finally:
        client.close();main.app.dependency_overrides.pop(database.get_db,None);main.clear_all_caches()


def test_coverage_refuses_a_source_reassociated_to_another_country(borrowing_pg,specimen):
    from models import Country
    _,factory=borrowing_pg
    with owned(factory) as ctx:persist(factory,ctx,specimen)
    with factory.begin() as db:
        country=Country(iso_code='SYN',name='Other owned synthetic country',currency='KES',timezone='UTC',default_locale='en')
        db.add(country);db.flush()
        doc=db.scalar(select(SourceDocument));doc.country_id=country.id
    with factory() as db:
        entity=db.scalar(select(Entity).where(Entity.slug=='kisii-county'))
        with pytest.raises(RuntimeError,match='provenance'):
            county_borrowing_coverage(db,[entity.id])

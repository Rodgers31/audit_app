"""PR799 source coverage stays honest at actual summary and HTTP boundaries."""
from datetime import datetime, timezone
from types import SimpleNamespace
from copy import deepcopy

import pytest
from sqlalchemy import event

from models import DebtCategory, FigureBasis, SourceDocument, Extraction, Entity, EntityType
from seeding import county_borrowing_contract as contract
from services.financial_publication import county_debt_summary


def debt_row(amount):
    return SimpleNamespace(entity_id=1, lender='Owned Bank', currency='KES', outstanding=amount,
        principal=100, basis=FigureBasis.ACTUAL, quarantine_reason=None,
        source_document=SimpleNamespace(meta=None), provenance={'as_at':'2025-06-30'},
        debt_category=DebtCategory.COUNTY_GUARANTEED)


def citation():
    return {'url':'https://example.invalid/source.pdf', 'source_document_id':1,
        'extraction_id':2, 'scope':'owned_checked_scope', 'pdf_pages':[1]}


@pytest.mark.parametrize('amount',[0,20])
@pytest.mark.parametrize('coverage',[
    {'status':'withheld_or_conflicting','sources':[citation()],'complete_liability_coverage':False},
    {'status':'not_integrated','sources':[{'url':'javascript:forged'}],'complete_liability_coverage':False},
    {'status':'not_reported_in_checked_source','sources':[],'complete_liability_coverage':False},
    {'status':'made_up','sources':[citation()],'complete_liability_coverage':False},
    {'status':'not_reported_in_checked_source','sources':[citation()],'complete_liability_coverage':True},
])
def test_invalid_or_conflicting_coverage_is_not_overridden_by_known_stock(amount,coverage):
    result=county_debt_summary([debt_row(amount)],source_coverage=deepcopy(coverage))
    assert result['total_debt']==amount
    assert result['debt_source_coverage']['status']=='withheld_or_conflicting'
    assert result['debt_source_coverage']['complete_liability_coverage'] is False


@pytest.mark.parametrize('amount,status',[(0,'dated_explicit_zero'),(20,'selected_instrument_stock')])
def test_independently_supported_stock_keeps_its_normal_status(amount,status):
    result=county_debt_summary([debt_row(amount)])
    assert result['debt_source_coverage']['status']==status


def retained_coverage(db,country_id,key='treasury_guaranteed_stock_2025'):
    stamp=datetime.now(timezone.utc)
    doc=SourceDocument(**contract.document_fields(key,country_id),
        meta=contract.document_metadata(key),fetch_date=stamp,last_verified_at=stamp,
        last_seen_at=stamp,created_at=stamp)
    db.add(doc);db.flush()
    spec=contract.edition(key)
    extraction=Extraction(source_document_id=doc.id,extractor=contract.EXTRACTOR,
        page_number=min(map(int,spec['pages'])),confidence=None,
        extracted_json=contract.expected_extraction(key),created_at=stamp)
    db.add(extraction);db.flush()
    return doc,extraction


PATHS=['/api/v1/counties','/api/v1/counties/code:047',
    '/api/v1/counties/code:047/comprehensive','/api/v1/counties/code:047/debt']


def response_debt(path,body):
    if path=='/api/v1/counties':return next(r for r in body if r['name']=='Nairobi')
    return body['debt'] if path.endswith('/comprehensive') else body


@pytest.mark.parametrize('path',PATHS)
def test_actual_county_api_projects_checked_scope(client,db_session,seed_entity,path):
    import main
    seed_entity.canonical_name='Nairobi County'
    doc,extraction=retained_coverage(db_session,seed_entity.country_id)
    # The Kisii-only audit account must never be attributed to Nairobi.
    retained_coverage(db_session,seed_entity.country_id,'oag_kisii_2024')
    doc_id,ext_id=doc.id,extraction.id
    db_session.commit();main.clear_all_caches()
    response=client.get(path)
    assert response.status_code==200,(path,response.text[:500])
    data=response_debt(path,response.json())
    assert data['total_debt'] is None
    coverage=data['debt_source_coverage']
    assert coverage['status']=='not_reported_in_checked_source'
    assert coverage['complete_liability_coverage'] is False
    assert len(coverage['sources'])==1
    source=coverage['sources'][0]
    assert (source['source_document_id'],source['extraction_id'])==(doc_id,ext_id)
    assert source['scope']=='national_guaranteed_stock_register'
    assert source['reporting_period_end']=='2025-06-30'


@pytest.mark.parametrize('path',PATHS)
def test_actual_county_api_refuses_invalid_source_projection(client,db_session,seed_entity,path):
    import main
    seed_entity.canonical_name='Nairobi County'
    doc,_=retained_coverage(db_session,seed_entity.country_id)
    doc.md5='0'*32;db_session.commit();main.clear_all_caches()
    response=client.get(path)
    assert response.status_code>=500,(path,response.text[:500])


def test_county_list_batches_coverage_for_multiple_entities(client,db_session,seed_entity):
    import main
    other=Entity(country_id=seed_entity.country_id,type=EntityType.COUNTY,
        canonical_name='Mombasa County',slug='mombasa-county')
    db_session.add(other);retained_coverage(db_session,seed_entity.country_id)
    db_session.commit();main.clear_all_caches()
    statements=[]
    def before_cursor(conn,cursor,statement,parameters,context,executemany):
        if 'county_borrowing' in str(parameters):statements.append(statement)
    engine=db_session.get_bind();event.listen(engine,'before_cursor_execute',before_cursor)
    try:response=client.get('/api/v1/counties')
    finally:event.remove(engine,'before_cursor_execute',before_cursor)
    assert response.status_code==200,response.text[:500]
    rows=response.json();assert len(rows)==2
    assert all(r['debt_source_coverage']['status']=='not_reported_in_checked_source' for r in rows)
    assert len(statements)==1,statements

from county_borrowing_fixture import borrowing_pg, owned  # noqa: E402,F401
from test_county_borrowing_producer import specimen, persist  # noqa: E402,F401


@pytest.mark.parametrize('path',['/api/v1/counties','/api/v1/counties/code:045',
    '/api/v1/counties/code:045/comprehensive','/api/v1/counties/code:045/debt'])
@pytest.mark.parametrize('kind',['not_integrated','checked_absence','conflicting_stock','ineligible_stock'])
def test_current_postgres_api_coverage(path,kind,borrowing_pg,specimen,monkeypatch):
    """Actual source/writer/PG/HTTP path; the financial specimen is synthetic."""
    import main,database
    from fastapi.testclient import TestClient
    _,factory=borrowing_pg
    if kind!='not_integrated':
        specimen[0]['status']=('not_reported_in_checked_source' if kind=='checked_absence'
                               else 'withheld_or_conflicting' if kind=='conflicting_stock'
                               else 'selected_instrument_stock')
        if kind=='checked_absence':specimen[0]['instruments']=[]
        with owned(factory) as ctx:persist(factory,ctx,specimen)
        if kind=='ineligible_stock':
            from models import CountyDebtObservation
            from sqlalchemy import select
            with factory.begin() as db:
                db.scalar(select(CountyDebtObservation)).quarantine_reason='owned test exclusion'
    def db_dependency():
        with factory() as db:yield db
    monkeypatch.setattr(main,'get_db',db_dependency)
    old=dict(main.app.dependency_overrides)
    main.app.dependency_overrides[database.get_db]=db_dependency
    client=TestClient(main.app,raise_server_exceptions=False)
    main.clear_all_caches()
    try:
        response=client.get(path)
        assert response.status_code==200,(path,response.text[:500])
        body=response.json()
        if path=='/api/v1/counties':body=next(row for row in body if row['name']=='Kisii')
        elif path.endswith('/comprehensive'):body=body['debt']
        expected={'not_integrated':'not_integrated','checked_absence':'not_reported_in_checked_source',
                  'conflicting_stock':'withheld_or_conflicting','ineligible_stock':'withheld_or_conflicting'}[kind]
        assert body['debt_source_coverage']['status']==expected
        assert body['debt_source_coverage']['complete_liability_coverage'] is False
        assert body['total_debt']==(20 if kind=='conflicting_stock' else None)
        sources=body['debt_source_coverage']['sources']
        assert len(sources)==(0 if kind=='not_integrated' else 1)
        if sources:
            assert sources[0]['url']==specimen[0]['url']
            assert sources[0]['artifact_sha256']==specimen[0]['sha256']
            assert sources[0]['reporting_period_end']=='2025-06-30'
    finally:
        client.close();main.app.dependency_overrides.clear();main.app.dependency_overrides.update(old)
        main.clear_all_caches()


@pytest.mark.parametrize('ids',[[],[True],[1,1],list(range(1,49))])
def test_coverage_rejects_invalid_or_oversized_entity_cohort_before_query(ids):
    from unittest.mock import Mock
    from services.county_borrowing_coverage import county_borrowing_coverage
    db=Mock()
    with pytest.raises(ValueError,match='1..47'):
        county_borrowing_coverage(db,ids)
    db.execute.assert_not_called()


def test_actual_api_refuses_overfull_source_account_cohort(client,db_session,seed_entity):
    import main
    seed_entity.canonical_name='Nairobi County'
    doc,ext=retained_coverage(db_session,seed_entity.country_id)
    for _ in range(8):
        db_session.add(Extraction(source_document_id=doc.id,extractor=contract.EXTRACTOR,
            page_number=ext.page_number,confidence=None,
            extracted_json=deepcopy(ext.extracted_json),created_at=ext.created_at))
    db_session.commit();main.clear_all_caches()
    response=client.get('/api/v1/counties')
    assert response.status_code>=500,response.text[:500]


def test_writer_resolves_existing_bootstrap_slug_by_official_county_identity(borrowing_pg,specimen):
    from sqlalchemy import select
    from models import CountyDebtInstrument
    _,factory=borrowing_pg
    with factory.begin() as db:
        entity=db.scalar(select(Entity).where(Entity.slug=='kisii-county'))
        entity.slug='kisii-045'
        entity_id=entity.id
    with owned(factory) as ctx:
        assert persist(factory,ctx,specimen)['instruments']==1
    with factory() as db:
        instrument=db.scalar(select(CountyDebtInstrument))
        assert instrument.entity_id==entity_id
        assert db.get(Entity,entity_id).slug=='kisii-045'


def test_reader_projects_scoped_audit_for_existing_bootstrap_slug(db_session,seed_country):
    from services.county_borrowing_coverage import county_borrowing_coverage
    entity=Entity(country_id=seed_country.id,type=EntityType.COUNTY,
        canonical_name='Kisii County',slug='kisii-045')
    db_session.add(entity);db_session.flush()
    retained_coverage(db_session,seed_country.id,'oag_kisii_2024')
    coverage=county_borrowing_coverage(db_session,[entity.id])[entity.id]
    assert coverage['status']=='withheld_or_conflicting'
    assert coverage['sources'][0]['scope']=='kisii_executive_audit_finding_980'


def test_stored_slug_cannot_reassign_a_scoped_source_to_another_county(db_session,seed_country):
    from services.county_borrowing_coverage import county_borrowing_coverage
    entity=Entity(country_id=seed_country.id,type=EntityType.COUNTY,
        canonical_name='Mombasa County',slug='kisii-county')
    db_session.add(entity);db_session.flush()
    retained_coverage(db_session,seed_country.id,'oag_kisii_2024')
    coverage=county_borrowing_coverage(db_session,[entity.id])[entity.id]
    assert coverage=={'status':'not_integrated','sources':[],'complete_liability_coverage':False}


def test_duplicate_official_identity_refuses_read_projection(db_session,seed_country):
    from services.county_borrowing_coverage import county_borrowing_coverage
    entities=[Entity(country_id=seed_country.id,type=EntityType.COUNTY,
        canonical_name=name,slug=slug) for name,slug in [('Kisii County','kisii-county'),('Kisii','kisii-045')]]
    db_session.add_all(entities);db_session.flush()
    with pytest.raises(ValueError,match='distinct official county'):
        county_borrowing_coverage(db_session,[e.id for e in entities])


def test_duplicate_official_identity_refuses_writer_before_effects(borrowing_pg,specimen):
    from test_county_borrowing_producer import effects
    from sqlalchemy import select
    _,factory=borrowing_pg
    with factory.begin() as db:
        existing=db.scalar(select(Entity).where(Entity.slug=='kisii-county'))
        db.add(Entity(country_id=existing.country_id,type=EntityType.COUNTY,
            canonical_name='Kisii',slug='kisii-045'))
    with owned(factory) as ctx:
        with pytest.raises(contract.CountyBorrowingRefused,match='identities are ambiguous'):
            persist(factory,ctx,specimen)
    assert effects(factory)==(0,0,0,0)

"""Mandatory actual-PG fiscal/debt reader chain; no production source adoption."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fiscal_evidence import isolated_fiscal_debt_peer_worker
from sqlalchemy import text
from models import Country, DebtTimeline, FiscalSummary
from test_fiscal_measure_postgres import candidate, write
from test_fiscal_measure_publication import qualified_row
from test_refresh_review_debt import run_source, snapshots
from test_refresh_review_debt_boundary import capture


@pytest.fixture
def owned_fiscal_debt_pg(db_session):
    if db_session.get_bind().dialect.name != 'postgresql':
        pytest.fail('required isolated owned PostgreSQL fixture was not supplied')
    if db_session.scalar(text('select current_database()')) != 'fiscal_fixture':
        pytest.fail('wrong owned PostgreSQL fixture identity')
    return db_session


def public_client_setup(monkeypatch):
    import main
    main.clear_all_caches()
    monkeypatch.setattr(main, '_latest_imf_debt_to_gdp', lambda _: None)
    monkeypatch.setattr(main, '_published_debt_projections', lambda _: ([], None, 'not_published'))
    monkeypatch.setattr(main, '_get_regional_peers', lambda **_: [])


def test_verified_pg_writer_timeline_sustainability_and_provenance_share_one_pair(
    owned_fiscal_debt_pg, seed_country, client, tmp_path, monkeypatch,
):
    import main
    db = owned_fiscal_debt_pg
    public_client_setup(monkeypatch)
    result, rows, _, _ = run_source(db, tmp_path/'initial', monkeypatch)
    assert result.items_created == 2
    response = client.get('/api/v1/debt/timeline')
    assert response.status_code == 200, response.text
    public = response.json()['timeline'][-1]
    assert public['gdp_ratio'] == 13
    assert public['qualifications']['gdp_ratio']['status'] == 'verified'
    assert public['period']['stock_as_of_month'] == '2025-12'
    assert public['period']['gdp_calendar_year'] == 2025
    assert public['period']['vintage_date'] is None
    response = client.get('/api/v1/debt/sustainability')
    assert response.status_code == 200, response.text
    assert response.json()['debt_to_gdp']['value'] == 13
    assert response.json()['debt_to_gdp']['period'] == public['period']
    response = client.get('/api/v1/provenance/verify/debt_timeline?year=2025')
    assert response.status_code == 200, response.text
    assert response.json()['qualifications']['gdp_ratio']['status'] == 'verified'
    before = snapshots(rows)
    result, rows, _, state = run_source(db, tmp_path/'outage', monkeypatch, cbk=False, gdp=False)
    assert snapshots(rows) == before
    assert state['mode'] != 'live'
    assert all(y['measures']['total']['state'] == 'retained_qualified'
               for y in result.metadata['year_coverage']['years'])
    main.clear_all_caches()
    assert client.get('/api/v1/debt/timeline').json()['timeline'][-1]['gdp_ratio'] == 13


def test_stock_only_pg_refresh_derives_against_qualified_retained_gdp(
    owned_fiscal_debt_pg, seed_country, client, tmp_path, monkeypatch,
):
    import main
    from seeding.domains.debt_timeline.writer import write_debt_timeline_records
    db = owned_fiscal_debt_pg
    public_client_setup(monkeypatch)
    run_source(db, tmp_path/'initial', monkeypatch)
    record = capture(tmp_path/'changed-stock', monkeypatch)
    write_debt_timeline_records(db, [record], {})
    db.commit()
    row = db.query(DebtTimeline).filter_by(year=2025).one()
    assert row.gdp_ratio == Decimal('14.0')
    main.clear_all_caches()
    public = client.get('/api/v1/debt/timeline').json()['timeline'][-1]
    assert public['gdp_ratio'] == 14
    assert public['qualifications']['gdp_ratio']['status'] == 'verified'


@pytest.mark.parametrize('unit', ['USD', 'UNKNOWN'])
def test_non_kes_legacy_debt_scalars_are_withheld_with_their_qualification(
    owned_fiscal_debt_pg, seed_source_doc, client, monkeypatch, unit,
):
    db = owned_fiscal_debt_pg
    public_client_setup(monkeypatch)
    db.add(DebtTimeline(year=2025, external=40, domestic=60, total=100,
        gdp=200, gdp_ratio=50, unit=unit, source_document_id=seed_source_doc.id))
    db.commit()
    response = client.get('/api/v1/debt/timeline')
    assert response.status_code == 200, response.text
    row = response.json()['timeline'][0]
    for measure in ('external', 'domestic', 'total', 'gdp'):
        assert row['qualifications'][measure]['status'] == 'unavailable'
        assert row[measure] is None
        assert row['absent_reasons'][measure] == 'debt_requires_declared_raw_kes'
    assert row['gdp_ratio'] is None


@pytest.mark.parametrize('consumer', ['timeline_reconciliation', 'national_reconciliation', 'provenance'])
def test_unqualified_stock_total_cannot_escape_in_secondary_public_fields(
    owned_fiscal_debt_pg, seed_country, seed_source_doc, client, monkeypatch, consumer,
):
    import main
    from models import Entity, EntityType, Loan
    db = owned_fiscal_debt_pg
    public_client_setup(monkeypatch)
    db.add(DebtTimeline(year=2025, external=40e9, domestic=60e9, total=100e9,
        gdp=200e9, gdp_ratio=50, unit='KES', source_document_id=None))
    entity = Entity(country_id=seed_country.id, type=EntityType.NATIONAL,
        canonical_name='National Treasury', slug='national-treasury')
    db.add(entity)
    db.flush()
    db.add(Loan(entity_id=entity.id, lender='Synthetic Treasury fixture', principal=10e9,
        outstanding=10e9, currency='KES', issue_date=datetime(2020, 1, 1),
        maturity_date=datetime(2030, 1, 1), source_document_id=seed_source_doc.id))
    db.commit()
    if consumer == 'provenance':
        response = client.get('/api/v1/provenance/verify/debt_timeline?year=2025')
        assert response.status_code == 200, response.text
        assert response.json()['value'] is None
        assert response.json()['qualifications']['total']['reason'] == 'source_document_missing'
    else:
        path = '/api/v1/debt/national' if consumer == 'national_reconciliation' else '/api/v1/debt/timeline'
        response = client.get(path)
        assert response.status_code == 200, response.text
        body = response.json()
        if consumer == 'national_reconciliation':
            body = body['data']
        field = 'secondary_value_kes' if consumer == 'national_reconciliation' else 'primary_value_kes'
        assert body['reconciliation'][field] is None
        assert body['reconciliation']['status'] == 'unchecked'


def test_pg_framework_partial_cell_withholding_covers_fiscal_chart_budget_and_provenance(
    owned_fiscal_debt_pg, client, monkeypatch,
):
    import main
    db = owned_fiscal_debt_pg
    public_client_setup(monkeypatch)
    write(db, candidate())
    db.commit()
    row = db.query(FiscalSummary).filter_by(fiscal_year='FY 2026/27').one()
    meta = deepcopy(row.meta)
    meta['fiscal_framework']['interest_payments_billion'] = 999
    row.meta = meta
    db.commit()
    main.clear_all_caches()
    public = client.get('/api/v1/fiscal/summary').json()['current']
    assert public['fiscal_framework']['interest_payments_billion'] is None
    assert public['fiscal_framework']['absent_reasons']['interest_payments_billion']
    assert public['fiscal_framework']['total_expenditure_billion'] == 4785.2
    meta = deepcopy(row.meta)
    meta['fiscal_framework'].pop('measure_contract')
    row.meta = meta
    db.commit()
    main.clear_all_caches()
    public = client.get('/api/v1/fiscal/summary').json()['current']
    assert public['fiscal_framework'] is None
    assert public['fiscal_framework_absent_reason']
    assert public['borrowing_pct_of_budget'] is None
    outturn = client.get('/api/v1/dashboards/national/fiscal-outturns').json()['series'][0]
    assert outturn['expenditure'] is None
    assert outturn['absent_reason']
    response = client.get('/api/v1/budget/enhanced')
    assert response.status_code == 200, response.text
    provenance = client.get('/api/v1/provenance/verify/fiscal_summaries?year=2026')
    assert provenance.status_code == 200, provenance.text
    assert provenance.json()['fiscal_measures']['borrowing_pct_of_budget'] is None


def test_pg_matching_negative_revenue_never_reaches_any_fiscal_public_layer(
    owned_fiscal_debt_pg, seed_source_doc, client, monkeypatch,
):
    import main
    from services.financial_publication import fiscal_history_entry
    db = owned_fiscal_debt_pg
    public_client_setup(monkeypatch)
    row = qualified_row()
    row.source_document_id = seed_source_doc.id
    row.total_revenue = -2041e9
    row.meta['fiscal_measure_contract']['measures']['total_revenue']['value_kes'] = -2041e9
    db.add(row)
    db.commit()
    assert fiscal_history_entry(row)['total_revenue'] is None
    main.clear_all_caches()
    body = client.get('/api/v1/fiscal/summary').json()['current']
    assert body['total_revenue'] is None
    assert body['absent_reasons']['total_revenue']
    provenance = client.get('/api/v1/provenance/verify/fiscal_summaries?year=2022').json()
    assert provenance['fiscal_measures']['total_revenue'] is None


def test_actual_pg_authority_adapter_keeps_all_expected_periods_and_explicit_holds(
    owned_fiscal_debt_pg, seed_country, tmp_path, monkeypatch,
):
    from services.fiscal_authority import verify_fiscal_debt_authority
    db = owned_fiscal_debt_pg
    run_source(db, tmp_path/'initial', monkeypatch)
    report = verify_fiscal_debt_authority(db,
        fiscal_years=[f'FY {year}/{str(year+1)[-2:]}' for year in range(2022, 2027)],
        debt_years=list(range(2013, 2027)), now=datetime(2026, 11, 5, tzinfo=timezone.utc))
    assert report['database']['dialect'] == 'postgresql'
    assert report['database']['database'] == 'fiscal_fixture'
    assert report['production_accepted'] is False
    assert report['source_adoption_authorized'] is False
    assert len(report['fiscal']) == 5
    assert len(report['debt_coverage']['years']) == 14
    missing = [x for x in report['holds'] if x['reason'] == 'required_row_missing']
    assert len(missing) == 5
    assert any(x['component'] == 'debt_timeline.total' and x['period'] == 2013 for x in report['holds'])
    assert not any(x['component'] == 'debt_timeline.gdp' and x['period'] == 2026 for x in report['holds'])
    assert report['debt_coverage']['years'][-1]['measures']['gdp']['absence_reason'] == 'annual_period_not_ended'


@pytest.mark.parametrize('fiscal,debt', [([], [2025]), (['FY 2022/23'], []),
    (['FY 2022/23', 'FY2022/23'], [2025]), (['FY 2022/24'], [2025]),
    (['FY 2022/23'], [True]), (['FY 2022/23'], [2025, 2025])])
def test_authority_adapter_refuses_empty_or_ambiguous_expected_inventories(
    owned_fiscal_debt_pg, fiscal, debt,
):
    from services.fiscal_authority import verify_fiscal_debt_authority
    with pytest.raises(ValueError):
        verify_fiscal_debt_authority(owned_fiscal_debt_pg, fiscal_years=fiscal, debt_years=debt)


def test_authority_adapter_refuses_dirty_identity_maps_without_flushing(owned_fiscal_debt_pg):
    from services.fiscal_authority import verify_fiscal_debt_authority
    db = owned_fiscal_debt_pg
    write(db, candidate())
    db.commit()
    row = db.query(FiscalSummary).filter_by(fiscal_year='FY 2022/23').one()
    row.total_revenue = 888e9
    meta = deepcopy(row.meta)
    meta['fiscal_measure_contract']['measures']['total_revenue']['value_kes'] = 888e9
    row.meta = meta
    with pytest.raises(ValueError, match='pending|clean|dirty'):
        verify_fiscal_debt_authority(db, fiscal_years=['FY 2022/23'], debt_years=[2025])
    stored = db.connection().execute(text('select total_revenue from fiscal_summaries where id=:id'), {'id': row.id}).scalar_one()
    assert stored == Decimal('2041119000000')


def test_authority_adapter_refreshes_clean_but_stale_identity_maps(owned_fiscal_debt_pg):
    from services.fiscal_authority import verify_fiscal_debt_authority
    db = owned_fiscal_debt_pg
    write(db, candidate())
    db.commit()
    row = db.query(FiscalSummary).filter_by(fiscal_year='FY 2022/23').one()
    row_id = row.id
    meta = deepcopy(row.meta)
    meta['fiscal_measure_contract']['measures']['total_revenue']['value_kes'] = 888e9
    # Raw SQL changes the store without synchronizing the clean ORM identity.
    # The original fixture deliberately holds an outer transaction.
    db.connection().execute(FiscalSummary.__table__.update().where(FiscalSummary.id == row_id).values(total_revenue=888e9, metadata=meta))
    assert row.total_revenue == Decimal('2041119000000')  # Cached preimage.
    report = verify_fiscal_debt_authority(db, fiscal_years=['FY 2022/23'], debt_years=[2025])
    assert report['fiscal'][0]['public_values']['total_revenue'] == 888e9
    assert report['production_accepted'] is False


@pytest.mark.parametrize('bad', [None, [], True, 'matched'])
def test_authority_adapter_reports_malformed_retained_byte_checks_as_conflicting(
    owned_fiscal_debt_pg, seed_source_doc, bad,
):
    from models import Extraction
    from services.fiscal_authority import _retained_fiscal_association
    db = owned_fiscal_debt_pg
    digest = 'a' * 64
    extraction = Extraction(source_document_id=seed_source_doc.id, page_number=1,
        extractor='pdf-receipt-v1', extracted_json={'response_receipt': {'digest': digest, 'byte_check': bad}})
    db.add(extraction)
    db.commit()
    proof = {'source_document_id': seed_source_doc.id, 'extraction_id': extraction.id,
             'source': {'url': seed_source_doc.url, 'sha256': digest}}
    result = _retained_fiscal_association(db, proof)
    assert result['state'] == 'conflicting'


def seed_original_apdmr_receipt(db, tmp_path):
    import httpx
    from pathlib import Path
    from models import Extraction
    from seeding.config import SeedingSettings
    from seeding.http_client import SeedingHttpClient
    from seeding.domains.fiscal_summary.actuals import fetch_apdmr, apply_apdmr
    body = (Path(__file__).parent/'fixtures/fiscal_actuals/apdmr-2022-23.pdf').read_bytes()
    settings = SeedingSettings(_env_file=None, cache_path=tmp_path/'cache', storage_path=tmp_path/'store', pdf_cache_ttl_seconds=0)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body, headers={'content-type':'application/pdf'}))) as transport:
        with SeedingHttpClient(settings, client=transport) as source:
            payload = apply_apdmr({'fiscal_years':[{'fiscal_year':'FY 2022/23'}]}, fetch_apdmr(source,settings))
    write(db,payload)
    db.commit()
    row = db.query(FiscalSummary).one()
    proof = row.meta['fiscal_measure_contract']['measures']['total_revenue']
    from services.receipt_store import configured_receipt_store
    return row, db.get(Extraction, proof['extraction_id']), configured_receipt_store(settings)


@pytest.mark.parametrize('bad', ['value','period','basis','unit','vintage','page','parser','duplicate'])
def test_authority_adapter_checks_retained_fiscal_manifest_semantics_and_reports_holds(
    owned_fiscal_debt_pg, tmp_path, bad,
):
    from services.fiscal_authority import verify_fiscal_debt_authority
    db = owned_fiscal_debt_pg
    row, extraction, store = seed_original_apdmr_receipt(db,tmp_path)
    data = deepcopy(extraction.extracted_json)
    receipt = data['response_receipt']
    observation = next(o for o in receipt['observations'] if o['identity']['measure']=='total_revenue')
    if bad == 'value': observation['value'] = '888000000000'
    elif bad in ('period','basis','unit'): observation['identity'][bad] = 'FY 2023/24' if bad=='period' else 'unsupported'
    elif bad == 'vintage': observation['identity']['dimensions']['vintage'] = 'Actual'
    elif bad == 'page': observation['locator']['page'] = 38
    elif bad == 'parser': receipt['parser_version'] = 'unknown-parser-v1'
    else: receipt['observations'].append(deepcopy(observation))
    extraction.extracted_json = data
    db.commit()
    report = verify_fiscal_debt_authority(db, fiscal_years=['FY 2022/23'], debt_years=[2025])
    association = report['fiscal'][0]['retained_associations']['total_revenue']
    assert association['state'] == 'conflicting'
    assert any(h['component']=='fiscal_summary.total_revenue.source_association' for h in report['holds'])
    assert report['production_accepted'] is False


def test_authority_adapter_exposes_the_actual_accepted_manifest_observation(owned_fiscal_debt_pg,tmp_path):
    from services.fiscal_authority import verify_fiscal_debt_authority
    db = owned_fiscal_debt_pg
    row, extraction, store = seed_original_apdmr_receipt(db,tmp_path)
    report = verify_fiscal_debt_authority(db, fiscal_years=['FY 2022/23'], debt_years=[2025], receipt_store=store)
    association = report['fiscal'][0]['retained_associations']['total_revenue']
    assert association['state'] == 'retained_observation_bound'
    assert association['manifest_observation']['value_kes'] == '2041119000000.0'
    assert association['manifest_observation']['period'] == 'FY 2022/23'
    assert association['manifest_observation']['vintage'] == 'Preliminary'
    assert association['manifest_observation']['locator']['page'] == 37
    assert report['source_adoption_authorized'] is False


def test_authority_adapter_keeps_unconfirmed_nested_source_associations_as_holds(owned_fiscal_debt_pg):
    from services.fiscal_authority import verify_fiscal_debt_authority
    db = owned_fiscal_debt_pg
    write(db,candidate())
    db.commit()
    report = verify_fiscal_debt_authority(db, fiscal_years=['FY 2026/27'], debt_years=[2025])
    nested = report['fiscal'][0]['framework_retained_associations']
    assert nested['total_expenditure_billion']['state'] == 'unconfirmed'
    assert any(h['component']=='fiscal_summary.framework.total_expenditure_billion.source_association' for h in report['holds'])


def test_authority_adapter_cannot_promote_a_manifest_without_an_original_reader(owned_fiscal_debt_pg,tmp_path):
    from services.fiscal_authority import verify_fiscal_debt_authority
    db = owned_fiscal_debt_pg
    seed_original_apdmr_receipt(db,tmp_path)
    report = verify_fiscal_debt_authority(db,fiscal_years=['FY 2022/23'],debt_years=[2025])
    association = report['fiscal'][0]['retained_associations']['total_revenue']
    assert association['state'] == 'retained_manifest_observation_bound'
    assert association['original_bytes_checked_this_observation'] is False
    assert any(h['reason']=='bound_original_receipt_reader_required' for h in report['holds'])


@pytest.mark.parametrize('state', ['changed','unavailable'])
def test_authority_adapter_reads_original_bytes_and_distinguishes_outage_from_conflict(owned_fiscal_debt_pg,tmp_path,state):
    from services.fiscal_authority import verify_fiscal_debt_authority
    db = owned_fiscal_debt_pg
    seed_original_apdmr_receipt(db,tmp_path)
    class OriginalReader:
        def read(self,digest):
            if state == 'unavailable': raise FileNotFoundError('inert removed original')
            return b'%PDF-1.7\ninert different body\n%%EOF'
    report = verify_fiscal_debt_authority(db,fiscal_years=['FY 2022/23'],debt_years=[2025],receipt_store=OriginalReader())
    association = report['fiscal'][0]['retained_associations']['total_revenue']
    assert association['state'] == ('unconfirmed' if state=='unavailable' else 'conflicting')
    assert report['source_adoption_authorized'] is False

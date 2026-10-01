"""#302: county routes publish DB evidence and distinguish absence from outage.

Synthetic PostgreSQL cases reuse the real legacy parser/writer and HTTP client.
No fixture is a claim about a Kenyan published amount.
"""
from datetime import date, datetime, timezone

import pytest

import main
from models import Audit, Country, DocumentStatus, DocumentType, Entity, EntityType, FiscalPeriod, Severity, SourceDocument
from test_legacy_county_budget_publication import legacy_db, legacy_client, mandera, _row, _write


@pytest.mark.parametrize('changes,allocation,spent', [
    ({}, 2000, 1000),
    ({'allocated_amount': 0, 'actual_amount': 0}, 0, 0),
    ({'actual_amount': None}, 2000, None),
    ({'data_quality': 'estimated'}, None, None),
])
def test_financial_matches_supported_budget_account(legacy_db, legacy_client, mandera, tmp_path, changes, allocation, spent):
    _write(legacy_db, tmp_path, [_row(**changes)])
    budget = legacy_client.get('/api/v1/counties/mandera-county/budget').json()
    assert budget['total_budget'] == allocation  # live positive control
    assert budget['total_spent'] == spent
    for identifier in ('009', 'code:009', 'Mandera', mandera.slug, str(mandera.id)):
        response = legacy_client.get(f'/api/v1/counties/{identifier}/financial')
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['county_name'] == 'Mandera'
        assert body['financial_data'] == budget['financial_summary']
        assert body['financial_data']['fiscal_period']['label'] == 'FY2024/25'


@pytest.mark.parametrize('suffix', ['', '/financial', '/audits', '/audits/history', '/audits/list'])
def test_known_county_without_evidence_is_not_unknown(legacy_client, mandera, suffix):
    response = legacy_client.get(f'/api/v1/counties/mandera-county{suffix}')
    assert response.status_code == 200, response.text
    if suffix == '/financial':
        assert response.json()['financial_data']['total_allocation'] is None
        assert response.json()['financial_data']['absent_reasons']
    elif suffix in ('/audits', '/audits/history', '/audits/list'):
        assert response.json()['findings_reason'] == 'no_findings_recorded'


@pytest.mark.parametrize('suffix', ['', '/financial', '/audits', '/audits/history', '/audits/list'])
def test_county_routes_refuse_failure_and_unavailable_db(legacy_client, mandera, monkeypatch, suffix):
    monkeypatch.setattr(main, 'DATABASE_AVAILABLE', False)
    response = legacy_client.get(f'/api/v1/counties/mandera-county{suffix}')
    assert response.status_code == 503, response.text
    main.clear_all_caches()
    monkeypatch.setattr(main, 'DATABASE_AVAILABLE', True)
    def broken_db():
        raise RuntimeError('synthetic DB failure')
    monkeypatch.setattr(main, 'get_db', broken_db)
    # list uses Depends, while other old handlers call main.get_db directly.
    for dependency in list(main.app.dependency_overrides):
        main.app.dependency_overrides[dependency] = broken_db
    response = legacy_client.get(f'/api/v1/counties/mandera-county{suffix}')
    assert response.status_code == 500, response.text


@pytest.mark.parametrize('suffix', ['/financial', '/audits', '/audits/history', '/audits/list'])
def test_unknown_foreign_and_wrong_type_are_not_counties(legacy_db, legacy_client, mandera, suffix):
    foreign = Country(iso_code='TZA', name='Synthetic Tanzania', currency='TZS', timezone='UTC', default_locale='en')
    legacy_db.add(foreign)
    legacy_db.flush()
    for country_id, kind, slug in ((foreign.id, EntityType.COUNTY, 'foreign-nairobi'), (mandera.country_id, EntityType.MINISTRY, 'ministry-nairobi'), (mandera.country_id, EntityType.COUNTY, 'assembly-nairobi')):
        entity = Entity(country_id=country_id, type=kind, canonical_name=('Nairobi County Assembly' if slug == 'assembly-nairobi' else 'Nairobi County'), slug=slug)
        legacy_db.add(entity)
    legacy_db.commit()
    for identifier in ('999', 'code:999', 'not-a-county', '001', 'code:047', 'foreign-nairobi', 'ministry-nairobi', 'assembly-nairobi'):
        response = legacy_client.get(f'/api/v1/counties/{identifier}{suffix}')
        assert response.status_code == 404, response.text


def test_audit_routes_share_published_scope_amounts_and_citations(legacy_db, legacy_client, mandera):
    period = FiscalPeriod(country_id=mandera.country_id, label='FY2024/25', start_date=date(2024,7,1), end_date=date(2025,6,30))
    doc = SourceDocument(country_id=mandera.country_id, publisher='Synthetic OAG', title='Synthetic audit', url='https://example.invalid/synthetic.pdf', doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE, fetch_date=datetime(2025,12,1,tzinfo=timezone.utc))
    assembly = Entity(country_id=mandera.country_id, type=EntityType.COUNTY, canonical_name='Mandera County Assembly', slug='mandera-assembly')
    legacy_db.add_all([period, doc, assembly]); legacy_db.flush()
    for entity, amount, page, text in ((mandera, 0, 'p.7', 'Reported zero'), (mandera, None, 'p.8', 'No amount; KES 900 text is not an amount contract'), (mandera, 99, None, 'Withheld finding'), (assembly, 500, 'p.9', 'Assembly finding')):
        legacy_db.add(Audit(entity_id=entity.id, period_id=period.id, source_document_id=doc.id, finding_text=text, severity=Severity.WARNING, amount=amount, page_ref=page, provenance=[{'status':'unresolved'}]))
    legacy_db.commit()
    aggregate = legacy_client.get('/api/v1/counties/009/audits')
    assert aggregate.status_code == 200, aggregate.text
    body = aggregate.json()
    assert body['summary']['queries_count'] == 2
    assert body['summary']['total_amount_involved'] == 0
    assert body['summary']['amount_coverage']['status'] == 'partial'
    assert body['withheld_findings'] == 1
    assert [q['amount_involved'] for q in body['queries']].count(None) == 1
    assert all(q['source']['url'] == doc.url for q in body['queries'])
    assert {q['source']['page'] for q in body['queries']} == {7,8}
    assert body['missing_funds']['total_amount'] is None
    listing = legacy_client.get('/api/v1/counties/009/audits/list').json()
    history = legacy_client.get('/api/v1/counties/009/audits/history').json()
    assert listing['total'] == history['total'] == body['summary']['queries_count']
    assert history['years'] == [{'fiscal_year':'FY2024/25','count':2,'by_status':{'unresolved':2}}]
    assert {q['id'] for q in body['queries']} == {q['id'] for q in listing['items']}


@pytest.mark.parametrize('changes', [{}, {'allocated_amount':0, 'actual_amount':0}, {'actual_amount':None}, {'data_quality':'estimated'}], ids=['reported','zero','missing_spending','withheld'])
def test_actual_frontend_budget_service_over_postgresql_http(legacy_db, legacy_client, mandera, tmp_path, monkeypatch, changes):
    """Actual service/request/endpoints/Axios against an owned loopback server."""
    import json
    import os
    from pathlib import Path
    if legacy_db.bind.dialect.name != 'postgresql':
        pytest.skip('Set LEGACY_BUDGET_TEST_POSTGRES_URL for the real HTTP/PG contract')
    _write(legacy_db, tmp_path, [_row(**changes)])
    expected = legacy_client.get('/api/v1/counties/mandera-county/budget').json()
    receipt_dir = os.environ.get('ROUND8_SESSION3_RECEIPTS')
    name = 'withheld' if changes.get('data_quality') else 'zero' if changes.get('allocated_amount') == 0 else 'missing_spending' if 'actual_amount' in changes else 'reported'
    receipt = Path(receipt_dir) / f'ROUND8_SESSION_3_HTTP_{name}.json' if receipt_dir else tmp_path / 'capture.json'
    _run_frontend_http_probe(tmp_path, expected, receipt, 'budget')


@pytest.mark.parametrize('suffix', ['', '/financial', '/audits'])
def test_database_unavailable_cannot_serve_a_primed_county_cache(legacy_client, mandera, monkeypatch, suffix):
    assert legacy_client.get(f'/api/v1/counties/009{suffix}').status_code == 200
    monkeypatch.setattr(main, 'DATABASE_AVAILABLE', False)
    assert legacy_client.get(f'/api/v1/counties/009{suffix}').status_code == 503


def test_retired_audit_fixtures_do_not_change_withheld_coverage(legacy_db, legacy_client, mandera):
    period = FiscalPeriod(country_id=mandera.country_id, label='FY2024/25', start_date=date(2024,7,1), end_date=date(2025,6,30))
    doc = SourceDocument(country_id=mandera.country_id, publisher='Synthetic OAG', title='Retired fixture', url='https://example.invalid/retired.pdf', doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE, fetch_date=datetime(2025,12,1,tzinfo=timezone.utc), meta={'source':'oag_audit_data.json'})
    legacy_db.add_all([period, doc]); legacy_db.flush()
    legacy_db.add(Audit(entity_id=mandera.id, period_id=period.id, source_document_id=doc.id, finding_text='Retired fixture', severity=Severity.WARNING, page_ref='p.7'))
    legacy_db.commit()
    for suffix in ('/audits', '/audits/history', '/audits/list'):
        body = legacy_client.get(f'/api/v1/counties/009{suffix}').json()
        assert body['withheld_findings'] == 0, (suffix, body)


@pytest.mark.parametrize('outstanding,expected,reason', [(0, 0, None), (20, 20, None), ('NaN', None, 'outstanding_not_reported_or_invalid')])
def test_list_and_legacy_detail_consume_shared_debt_contract(legacy_db, legacy_client, mandera, tmp_path, outstanding, expected, reason):
    from decimal import Decimal
    from models import FigureBasis, Loan
    if outstanding == 'NaN' and legacy_db.bind.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL Numeric NaN requires LEGACY_BUDGET_TEST_POSTGRES_URL')
    doc = SourceDocument(country_id=mandera.country_id, publisher='Synthetic county', title='Synthetic borrowing account', url='https://example.invalid/loan.pdf', doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE, fetch_date=datetime(2025,12,1,tzinfo=timezone.utc))
    legacy_db.add(doc); legacy_db.flush()
    legacy_db.add(Loan(entity_id=mandera.id, lender='Synthetic commercial lender', principal=100, outstanding=Decimal(str(outstanding)), issue_date=datetime(2024,1,1), currency='KES', basis=FigureBasis.ACTUAL, source_document_id=doc.id, provenance=[{'as_at':'2025-06-30','instrument_id':'synthetic-one'}]))
    legacy_db.commit()
    listed = legacy_client.get('/api/v1/counties')
    detail = legacy_client.get('/api/v1/counties/mandera-county')
    assert listed.status_code == detail.status_code == 200
    for body in (listed.json()[0], detail.json()):
        assert body['debt'] == body['total_debt'] == expected
        assert body['total_debt_absent_reason'] == reason
        assert body['debt_currency'] == 'KES'
        assert body['debt_as_at'] == '2025-06-30'
        assert body['debt_accounting_basis'] == 'selected_instrument_outstanding'
        assert body['debt_coverage'] == 'selected_eligible_instruments_only'
    if legacy_db.bind.dialect.name == 'postgresql':
        import os
        from pathlib import Path
        receipt_dir = os.environ.get('ROUND8_SESSION3_RECEIPTS')
        receipt = Path(receipt_dir) / f'ROUND8_SESSION_3_DEBT_HTTP_{outstanding}.json' if receipt_dir else tmp_path / 'debt-capture.json'
        _run_frontend_http_probe(tmp_path, detail.json(), receipt, 'county-debt')



def _run_frontend_http_probe(tmp_path, expected, receipt, mode):
    import json
    from pathlib import Path
    import socket
    import subprocess
    import threading
    import time
    import uvicorn
    root = Path(__file__).resolve().parents[2]
    expected_file = tmp_path / 'expected.json'
    expected_file.write_text(json.dumps(expected))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); sock.listen(128)
        server = uvicorn.Server(uvicorn.Config(main.app, lifespan='off', log_level='error'))
        thread = threading.Thread(target=server.run, kwargs={'sockets':[sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started
            port = sock.getsockname()[1]
            run = subprocess.run(['node', str(root / 'frontend/__tests__/api/budget-service-http.cjs'), f'http://127.0.0.1:{port}', 'mandera-county', str(expected_file), str(receipt), mode], cwd=root, capture_output=True, text=True, timeout=30)
            assert run.returncode == 0, run.stdout + run.stderr
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive()


@pytest.mark.parametrize('category', ['Total', 'Education'])
@pytest.mark.parametrize('field', ['allocated_amount', 'actual_spent'])
@pytest.mark.parametrize('value', [None, 'NaN', -1])
def test_overview_refuses_incomplete_or_invalid_county_inputs(
    legacy_db, legacy_client, mandera, tmp_path, category, field, value
):
    """Real PostgreSQL Numeric invalidity must not crash or become zero."""
    from decimal import Decimal
    from models import BudgetLine

    if value == 'NaN' and legacy_db.bind.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL Numeric NaN requires LEGACY_BUDGET_TEST_POSTGRES_URL')
    _write(legacy_db, tmp_path, [_row(category=category)])
    line = legacy_db.query(BudgetLine).one()
    setattr(line, field, Decimal(value) if value == 'NaN' else value)
    legacy_db.commit()
    response = legacy_client.get('/api/v1/budget/overview')
    assert response.status_code == 503, response.text
    assert response.json()['detail']['reason'] == 'incomplete_or_invalid_county_amount'


@pytest.mark.parametrize('value', [0, 12])
@pytest.mark.parametrize('category', ['Total', 'Education'])
def test_overview_preserves_positive_and_zero_controls(
    legacy_db, legacy_client, mandera, tmp_path, value, category
):
    _write(legacy_db, tmp_path, [_row(category=category, allocated_amount=value, actual_amount=value)])
    response = legacy_client.get('/api/v1/budget/overview')
    assert response.status_code == 200, response.text
    assert response.json()['summary']['total_budget'] == value
    assert response.json()['summary']['total_spent'] == value


@pytest.mark.parametrize('foreign', [True, False], ids=['foreign_county', 'county_assembly'])
def test_overview_period_uses_the_same_official_county_scope(
    legacy_db, legacy_client, mandera, tmp_path, foreign
):
    from models import BudgetLine

    _write(legacy_db, tmp_path, [_row()])
    country_id = mandera.country_id
    if foreign:
        country = Country(iso_code='TZA', name='Synthetic Tanzania', currency='TZS', timezone='UTC', default_locale='en')
        legacy_db.add(country)
        legacy_db.flush()
        country_id = country.id
    entity = Entity(country_id=country_id, type=EntityType.COUNTY,
                    canonical_name='Mandera County' if foreign else 'Mandera County Assembly',
                    slug='synthetic-newer-institution')
    period = FiscalPeriod(country_id=country_id, label='FY2030/31', start_date=date(2030,7,1), end_date=date(2031,6,30))
    legacy_db.add_all([entity, period])
    legacy_db.flush()
    legacy_db.add(BudgetLine(entity_id=entity.id, period_id=period.id, category='Education', allocated_amount=9000, actual_spent=8000, currency='KES', source_document_id=legacy_db.query(BudgetLine).one().source_document_id))
    legacy_db.commit()
    response = legacy_client.get('/api/v1/budget/overview')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['fiscal_period'] == 'FY2024/25'
    assert body['summary']['total_budget'] == 2000
    assert body['summary']['total_spent'] == 1000

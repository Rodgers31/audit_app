"""Public fiscal/debt boundaries named in PR914, using inert evidence only."""
import asyncio
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fiscal_evidence import qualify_synthetic_row
from models import DebtTimeline
from test_refresh_review_debt import db, freshness, document, run_source
from test_refresh_review_debt_boundary import capture
from test_fiscal_measure_publication import qualified_row
from test_session3_adversarial_fiscal_outturns import framework


@pytest.mark.parametrize('field', ['appropriated_budget', 'total_revenue', 'tax_revenue',
    'non_tax_revenue', 'debt_service_cost', 'total_borrowing', 'recurrent_spending',
    'development_spending', 'county_allocation'])
def test_matching_negative_legacy_amount_and_proof_never_publish(field):
    from main import _fiscal_row_to_dict
    from services.financial_publication import fiscal_history_entry
    from services.fiscal_qualification import MONEY_BASES, measure_evidence
    row = qualified_row()
    setattr(row, field, -123_000_000_000)
    row.meta['fiscal_measure_contract']['measures'][field] = measure_evidence(
        -123_000_000_000, row.fiscal_year, next(iter(MONEY_BASES[field])),
        'Preliminary', 100_000_000,
        row.meta['fiscal_measure_contract']['measures']['total_revenue']['source'])
    for public in (_fiscal_row_to_dict(row), fiscal_history_entry(row)):
        assert public[field] is None
        assert public['absent_reasons'][field]


def framework_row():
    row = qualified_row()
    row.fiscal_year = 'FY 2023/24'
    row.meta['fiscal_framework'] = framework()
    return row


@pytest.mark.parametrize('consumer', ['summary', 'outturn', 'borrowing'])
def test_a_framework_locator_cannot_certify_all_nested_amounts(consumer):
    from main import _fiscal_row_to_dict
    from services.fiscal_outturns import fiscal_outturn
    from services.fiscal_qualification import fiscal_values, measure_evidence
    row = framework_row()
    # The legacy framework carries source location and arithmetic, but no
    # independently bound per-cell proofs. The top-level borrowing proof
    # cannot certify the expenditure denominator or unrelated split.
    row.meta['fiscal_framework'].pop('measure_contract', None)
    row.total_borrowing = 818.3e9
    row.meta['fiscal_measure_contract']['measures']['total_borrowing'] = measure_evidence(
        818.3e9, row.fiscal_year, 'treasury_fiscal_framework', 'Actual',
        100_000_000, deepcopy(row.meta['fiscal_framework']['source']))
    if consumer == 'summary':
        public = _fiscal_row_to_dict(row)
        assert public['fiscal_framework'] is None
        assert public['fiscal_framework_absent_reason']
    elif consumer == 'outturn':
        public = fiscal_outturn(row)
        assert public['revenue'] is None
        assert public['expenditure'] is None
        assert public['balance'] is None
        assert public['absent_reason']
    else:
        assert fiscal_values(row)['borrowing_pct_of_budget'] is None


def test_fixture_bootstrap_cannot_store_or_serve_its_ratio(db):
    import main
    from seeding.domains.debt_timeline.parser import DebtTimelineRecord
    from seeding.domains.debt_timeline.writer import write_debt_timeline_records
    record = DebtTimelineRecord(year=2025, external=400, domestic=600, total=1000,
        gdp=2000, gdp_ratio=50)
    write_debt_timeline_records(db, [record], {})
    db.commit()
    row = db.query(DebtTimeline).one()
    assert row.gdp_ratio is None
    public = asyncio.run(main.get_debt_timeline.__wrapped__(db=db))
    assert public['timeline'][0]['gdp_ratio'] is None


def legacy_debt(db):
    doc = document(db)
    row = DebtTimeline(year=2025, external=400e9, domestic=600e9, total=1000e9,
        gdp=2000e9, gdp_ratio=50, unit='KES', source_document_id=doc.id)
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize('consumer', ['timeline', 'sustainability'])
def test_legacy_ratio_is_withheld_at_every_actual_public_consumer(db, monkeypatch, consumer):
    import main
    legacy_debt(db)
    from models import FiscalSummary
    FiscalSummary.__table__.create(db.get_bind(), checkfirst=True)
    if consumer == 'timeline':
        body = asyncio.run(main.get_debt_timeline.__wrapped__(db=db))
        assert body['timeline'][0]['qualifications']['gdp_ratio']['status'] != 'verified'
        assert body['timeline'][0]['gdp_ratio'] is None
    else:
        monkeypatch.setattr(main, '_latest_imf_debt_to_gdp', lambda _: None)
        monkeypatch.setattr(main, '_published_debt_projections', lambda _: ([], None, 'not_published'))
        body, _ = main._debt_sustainability_snapshot(db)
        assert body['debt_to_gdp'] is None
        assert body['debt_to_gdp_absent_reason']


def test_gdp_refresh_cannot_qualify_retained_fixture_stock(db, tmp_path, monkeypatch):
    from seeding.domains.debt_timeline import writer
    legacy_debt(db)
    _, rows, qualifications, _ = run_source(db, tmp_path/'gdp-only', monkeypatch, cbk=False)
    row = next(r for r in rows if r.year == 2025)
    assert qualifications[row.id]['total']['status'] != 'verified'
    assert row.gdp_ratio is None


@pytest.mark.parametrize('top_state', ['framework_only', 'all_top_refreshed'])
def test_nested_last_good_survives_without_a_top_level_retention(top_state):
    from seeding.domains.fiscal_summary.writer import _retain_last_good
    from services.fiscal_qualification import published_framework
    row = framework_row()
    qualify_synthetic_row(row)
    incoming = SimpleNamespace(fiscal_year=row.fiscal_year, fiscal_framework=None, tax_split_absent_reason=None,
        tax_split_observation=None, fiscal_measure_contract=deepcopy(row.meta['fiscal_measure_contract']))
    if top_state == 'framework_only':
        row.meta['fiscal_measure_contract']['measures'] = {}
    retained = _retain_last_good(incoming, row)
    result = published_framework(SimpleNamespace(meta={'fiscal_framework': retained.fiscal_framework}, fiscal_year=row.fiscal_year))
    assert result is not None
    assert result['total_expenditure_billion'] == 3605.2
    assert result['statistical_discrepancy_billion'] == -16.8


def test_national_register_cannot_supply_an_unqualified_fallback_ratio(client, db_session, seed_country, seed_source_doc, monkeypatch):
    import main
    from models import Entity, EntityType, GDPData, Loan
    entity = Entity(country_id=seed_country.id, type=EntityType.NATIONAL,
        canonical_name='National Treasury', slug='national-treasury')
    db_session.add(entity)
    db_session.flush()
    db_session.add(Loan(entity_id=entity.id, lender='Treasury bonds', principal=100e9,
        outstanding=100e9, currency='KES', issue_date=__import__('datetime').date(2020,1,1),
        maturity_date=__import__('datetime').date(2030,1,1), source_document_id=seed_source_doc.id))
    db_session.add(GDPData(year=2024, gdp_value=1000e9, source_document_id=seed_source_doc.id))
    db_session.commit()
    monkeypatch.setattr(main, '_latest_imf_debt_to_gdp', lambda _: None)
    main.clear_all_caches()
    response = client.get('/api/v1/debt/national')
    assert response.status_code == 200, response.text
    body = response.json()['data']
    assert body['debt_to_gdp_ratio'] is None
    assert body['debt_to_gdp_computed_central_gov'] is None
    assert body['debt_sustainability']['debt_to_gdp'] is None
    assert body['debt_to_gdp_absent_reason']


def test_external_share_requires_one_stock_edition_even_when_months_match(db, tmp_path, monkeypatch):
    from seeding.domains.debt_timeline.publication import public_debt_rows
    from services.response_receipts import persist_evidence
    from models import SourceDocument
    _, rows, _, _ = run_source(db, tmp_path/'initial', monkeypatch)
    row = rows[-1]
    fresh = capture(tmp_path/'separate-acquisition', monkeypatch, domestic=780000, external=520000, total=1300000)
    external = [e for e in fresh.source_evidence if e['identity']['measure'] == 'external']
    source = db.get(SourceDocument, row.source_document_id)
    evidence = persist_evidence(db, source, external)
    row.meta = {**row.meta, 'source_evidence': [e for e in row.meta['source_evidence'] if e['identity']['measure'] != 'external'] + evidence}
    db.commit()
    public = public_debt_rows(db, [row])[row.id]
    assert public['qualifications']['external']['status'] == 'verified'
    assert public['qualifications']['total']['status'] == 'verified'
    assert public['external_debt_share'] is None
    assert public['external_debt_share_absent_reason']


@pytest.mark.parametrize('location', ['proof', 'source'])
def test_unknown_nested_numbers_in_measure_metadata_are_not_public_measures(location):
    from main import _fiscal_row_to_dict
    row = qualified_row()
    proof = row.meta['fiscal_measure_contract']['measures']['total_revenue']
    (proof if location == 'proof' else proof['source'])['unqualified_budget_billion'] = 777
    public = _fiscal_row_to_dict(row)
    assert public['total_revenue'] == 2041e9
    assert 'unqualified_budget_billion' not in str(public)


@pytest.mark.parametrize('missing_history', [False, True])
def test_gdp_requirements_keep_missing_history_and_disclose_unfinished_annual_period(monkeypatch, missing_history):
    from datetime import datetime, timezone
    from seeding.domains.debt_timeline import fetcher
    from seeding.observations import ObservedSeries
    year = datetime.now(timezone.utc).year
    years = [year-1, year] if not missing_history else [year-2, year-1, year]
    payload = {'timeline': [{'year': y, 'external': 400, 'domestic': 600, 'total': 1000,
        'gdp': None, 'gdp_ratio': None} for y in years]}
    monkeypatch.setattr(fetcher, '_fetch_wb_gdp', lambda _: ObservedSeries({year-1: Decimal('2000000000000')}))
    result = fetcher._enrich_with_wb_gdp(payload, None)
    component = result['metadata']['refresh_components']['gdp']
    assert year not in component['missing_years']
    assert component['unpublished_years'] == [year]
    assert component['required_periods'] == [y for y in years if y < year]
    assert component['missing_years'] == ([year-2] if missing_history else [])
    assert component['state'] == ('partial' if missing_history else 'live')
    assert result['timeline'][-1]['gdp'] is None
    assert result['timeline'][-1]['gdp_ratio'] is None


def test_unfinished_annual_gdp_is_withheld_even_when_a_legacy_column_is_populated(db):
    from datetime import datetime, timezone
    from seeding.domains.debt_timeline.publication import public_debt_rows
    row = legacy_debt(db)
    row.year = datetime.now(timezone.utc).year
    db.commit()
    public = public_debt_rows(db, [row])[row.id]
    assert public['gdp'] is None
    assert public['qualifications']['gdp']['status'] == 'unavailable'
    assert public['qualifications']['gdp']['reason'] == 'annual_gdp_period_not_ended'


@pytest.mark.parametrize('bad', ['basis', 'precision', 'version'])
def test_invalid_nested_source_proof_refuses_before_any_fiscal_batch_mutation(db, bad):
    from test_fiscal_measure_postgres import candidate, write
    FiscalSummary = __import__('models').FiscalSummary
    FiscalSummary.__table__.create(db.get_bind(), checkfirst=True)
    payload = candidate()
    framework = payload['fiscal_years'][-1]['fiscal_framework']
    if bad == 'version':
        framework['measure_contract']['version'] = 'future-unreviewed'
    else:
        proof = framework['measure_contract']['measures']['interest_payments_billion']
        proof['basis' if bad == 'basis' else 'precision_kes'] = 'ordinary_revenue_excl_aia' if bad == 'basis' else 1
    with pytest.raises(ValueError, match='framework.*proof|framework.*contract'):
        write(db, payload)
    assert db.query(FiscalSummary).count() == 0


def test_signed_framework_adjustments_keep_cent_normalization_without_a_positive_sign_rule():
    from services.fiscal_framework_qualification import bind_framework_evidence
    from services.fiscal_qualification import published_framework
    row = framework_row()
    data = row.meta['fiscal_framework']
    data['adjustment_to_cash_basis_billion'] = -2167.8
    data['total_financing_billion'] = 3031.5
    data['net_domestic_financing_billion'] = 2808.8
    bind_framework_evidence(data)
    result = published_framework(row)
    assert result is not None
    assert result['adjustment_to_cash_basis_billion'] == -2167.8
    assert result['measure_qualifications']['adjustment_to_cash_basis_billion']['value_kes'] == -2167800000000


def test_framework_financing_parts_need_their_own_reconciled_total():
    from services.fiscal_framework_qualification import bind_framework_evidence
    from services.fiscal_qualification import published_framework
    row = framework_row()
    row.meta['fiscal_framework']['net_foreign_financing_billion'] = 100
    bind_framework_evidence(row.meta['fiscal_framework'])
    result = published_framework(row)
    assert result is not None
    assert result['total_financing_billion'] == 818.3
    assert result['net_foreign_financing_billion'] is None
    assert result['net_domestic_financing_billion'] is None
    assert result['absent_reasons']['net_foreign_financing_billion']


def test_unknown_framework_vintage_requires_an_explicit_witness_field():
    from services.fiscal_framework_qualification import bind_framework_evidence
    from services.fiscal_qualification import published_framework
    row = framework_row()
    data = row.meta['fiscal_framework']
    data['source'].pop('column', None)
    bind_framework_evidence(data)
    assert published_framework(row) is not None  # Explicit None witnesses unknown vintage.
    data['measure_contract']['measures']['total_expenditure_billion'].pop('vintage')
    assert published_framework(row) is None


def test_framework_absence_metadata_cannot_carry_an_unknown_numeric_object():
    from services.fiscal_qualification import published_framework
    row = framework_row()
    row.meta['fiscal_framework']['tax_split_absent_reason'] = {'unqualified_amount': 123}
    public = published_framework(row)
    assert public is not None
    assert isinstance(public['tax_split_absent_reason'], str)
    assert public['tax_revenue_billion'] is None


def test_fiscal_public_metadata_uses_typed_known_values_only():
    from main import _fiscal_row_to_dict
    row = framework_row()
    row.meta.update(budget_basis={'unqualified_amount': 123}, split_basis={'unqualified_amount': 123},
                    retained_measure_fields=[{'unqualified_amount': 123}], tax_split_absent_reason={'unqualified_amount': 123})
    public = _fiscal_row_to_dict(row)
    assert public['budget_basis'] is None
    assert public['split_basis'] is None
    assert public['retained_measure_fields'] == []
    assert isinstance(public['tax_split_absent_reason'], (str, type(None)))


@pytest.mark.parametrize('field', ['ordinary_revenue_billion','total_expenditure_billion'])
def test_framework_witness_cannot_claim_more_digits_than_the_printed_quantum(field):
    from services.fiscal_framework_qualification import bind_framework_evidence
    from services.fiscal_qualification import published_framework
    row = framework_row()
    data = row.meta['fiscal_framework']
    data[field] += .000001  # One thousand KES was never printed in one-decimal billions.
    bind_framework_evidence(data)
    result = published_framework(row)
    if field == 'total_expenditure_billion':
        assert result is None
    else:
        assert result is not None
        assert result[field] is None
        assert result['absent_reasons'][field]

"""Measure-specific publication, including the serving FY2022/23 discrepancy."""
from copy import deepcopy
from types import SimpleNamespace

import pytest


def legacy_row():
    from models import FiscalSummary
    return FiscalSummary(fiscal_year='FY 2022/23', unit='KES',
        appropriated_budget=3_675_000_000_000, total_revenue=2_042_000_000_000,
        tax_revenue=1_780_000_000_000, non_tax_revenue=262_000_000_000,
        debt_service_cost=1_162_000_000_000, debt_service_per_shilling=56.9,
        page_ref='s.3.2, report p.16 (PDF p.37)', meta={
            'budget_basis': 'cob_gross', 'budget_basis_source': {
                'url':'https://cob.go.ke/download/report/?wpdmdl=15956',
                'page':'PDF p.37'},
            'tax_split_absent_reason':'edition_prints_no_tax_or_non_tax_row'})


def test_budget_locator_cannot_publish_unsourced_measures():
    from main import _fiscal_row_to_dict
    result = _fiscal_row_to_dict(legacy_row())
    for key in ('total_revenue','tax_revenue','non_tax_revenue','debt_service_cost',
                'debt_service_per_shilling'):
        assert result[key] is None, (key, result[key])
        assert result['absent_reasons'][key]


def test_overview_history_cannot_publish_unsourced_measures():
    from services.financial_publication import fiscal_history_entry
    result = fiscal_history_entry(legacy_row())
    assert result['total_revenue'] is None
    assert result['debt_service_cost'] is None


def evidence(field, value, *, basis='ordinary_revenue_excl_aia', vintage='Preliminary'):
    return {'value_kes':value, 'fiscal_year':'FY 2022/23', 'basis':basis,
        'vintage':vintage, 'precision_kes':1_000_000_000,
        'source':{'url':'https://www.treasury.go.ke/sites/default/files/BBB/2023-Budget-Review-and-Outlook-Paper_f.pdf',
                  'page':'Table 8, PDF p.21', 'sha256':'a8d6d4f38c9e4ec74134b98b1ed6164d8b4cd152714006740add1c9923e22986'}}


def qualified_row():
    row=legacy_row()
    row.total_revenue=2_041_000_000_000
    row.tax_revenue=1_887_000_000_000
    row.non_tax_revenue=154_000_000_000
    row.meta={'fiscal_measure_contract':{'version':'fiscal-measures-v1','measures':{
        f:evidence(f,getattr(row,f)) for f in ('total_revenue','tax_revenue','non_tax_revenue')}}}
    return row


def test_qualified_values_survive_with_their_own_basis_and_precision():
    from main import _fiscal_row_to_dict
    result=_fiscal_row_to_dict(qualified_row())
    assert result['total_revenue']==2_041_000_000_000
    assert result['tax_revenue']==1_887_000_000_000
    assert result['non_tax_revenue']==154_000_000_000
    assert result['measure_qualifications']['total_revenue']['precision_kes']==1_000_000_000
    assert result['debt_service_cost'] is None


@pytest.mark.parametrize('path,bad',[
    ('version',None),('version','future-v2'),('measures',[]),
    ('value_kes',True),('value_kes',float('nan')),('value_kes',float('inf')),
    ('value_kes',-1),('value_kes','2041000000000'),('value_kes',2042e9),
    ('precision_kes',True),('precision_kes',0),('precision_kes',float('nan')),
    ('fiscal_year','FY 2023/24'),('fiscal_year',None),('basis','total_revenue_incl_aia'),
    ('vintage','unknown'),('source',{}),('source',[]),('url','https://evil.example/source.pdf'),
    ('page','0'),('page','unknown'),('sha256','bad'),
])
def test_bad_measure_proof_never_publishes(path,bad):
    from main import _fiscal_row_to_dict
    row=qualified_row()
    c=row.meta['fiscal_measure_contract']
    if path in ('version','measures'): c[path]=bad
    elif path in ('url','page','sha256'): c['measures']['total_revenue']['source'][path]=bad
    else:c['measures']['total_revenue'][path]=bad
    result=_fiscal_row_to_dict(row)
    assert result['total_revenue'] is None
    assert result['absent_reasons']['total_revenue']


def test_stale_split_proofs_do_not_override_a_source_absence():
    from main import _fiscal_row_to_dict
    row=qualified_row()
    row.meta['tax_split_absent_reason']='edition_prints_no_tax_or_non_tax_row'
    result=_fiscal_row_to_dict(row)
    assert result['tax_revenue'] is None
    assert result['non_tax_revenue'] is None


def test_borrowing_ratio_requires_same_source_and_vintage_as_denominator():
    from services.fiscal_qualification import fiscal_values
    from fiscal_evidence import bind_framework
    from test_session3_adversarial_fiscal_outturns import framework
    row=qualified_row();row.total_borrowing=600e9
    row.meta['fiscal_framework']=framework()
    proof=evidence('total_borrowing',600e9,basis='treasury_fiscal_framework',vintage='Actual')
    row.meta['fiscal_measure_contract']['measures']['total_borrowing']=proof
    row.meta['fiscal_framework']['fiscal_year']=row.fiscal_year
    result=fiscal_values(row)
    assert result['borrowing_pct_of_budget'] is None


@pytest.mark.parametrize('contract',[{'version':'fiscal-measures-v1','measures':[]},
                                     {'version':'future-v2','measures':{}}])
def test_framework_contract_failure_is_atomic(contract):
    from seeding.domains.fiscal_summary.fetcher import _apply_fiscal_framework
    from test_fiscal_framework_split import _edition,URL_2627
    payload={'fiscal_years':[{'fiscal_year':'FY 2026/27','fiscal_measure_contract':contract}]}
    before=deepcopy(payload)
    with pytest.raises(ValueError):_apply_fiscal_framework(payload,[(URL_2627,_edition())])
    assert payload==before


def test_budget_overlay_cannot_certify_retained_debt_service():
    from seeding.domains.fiscal_summary.fetcher import _apply_budget_estimates
    from test_fiscal_headline_overlay import _Estimates
    estimate=_Estimates()
    estimate.source_sha256='a'*64
    payload={'fiscal_years':[{'fiscal_year':estimate.fiscal_year,
        'appropriated_budget':5485.7,'budget_basis':'cob_gross',
        'debt_service_cost':1234,'debt_service_source':{
            'url':'https://www.treasury.go.ke/retained.pdf','page':'PDF p.1'}}]}
    result,status=_apply_budget_estimates(payload,estimate)
    proof=result['fiscal_years'][0].get('fiscal_measure_contract',{}).get('measures',{}).get('debt_service_cost')
    assert proof is None


@pytest.mark.parametrize('contract',[{'version':'fiscal-measures-v1','measures':[]},
                                     {'version':'future-v2','measures':{}}])
def test_budget_contract_failure_is_atomic(contract):
    from seeding.domains.fiscal_summary.fetcher import _apply_budget_estimates
    from test_fiscal_headline_overlay import _Estimates
    payload={'fiscal_years':[{'fiscal_year':'FY 2026/27','fiscal_measure_contract':contract}]}
    before=deepcopy(payload)
    with pytest.raises(ValueError):_apply_budget_estimates(payload,_Estimates())
    assert payload==before


@pytest.mark.parametrize('field,bad',[('county_equitable_share_billion',True),
    ('county_equitable_share_billion',float('nan')),('county_equitable_share_billion',999999),
    ('recurrent_billion',999999),('development_billion',float('inf'))])
def test_nested_framework_numbers_cannot_bypass_measure_guards(field,bad):
    from main import _fiscal_row_to_dict
    from test_session3_adversarial_fiscal_outturns import framework
    row=qualified_row();row.fiscal_year='FY 2023/24'
    row.meta['fiscal_framework']=framework()
    row.meta['fiscal_framework'][field]=bad
    result=_fiscal_row_to_dict(row)['fiscal_framework']
    assert result[field] is None


def test_nested_tax_split_respects_explicit_absence():
    from main import _fiscal_row_to_dict
    from test_session3_adversarial_fiscal_outturns import framework
    row=qualified_row();row.fiscal_year='FY 2023/24'
    row.meta['fiscal_framework']=framework()
    row.meta['tax_split_absent_reason']='edition_prints_no_tax_or_non_tax_row'
    result=_fiscal_row_to_dict(row)['fiscal_framework']
    assert result['tax_revenue_billion'] is None
    assert result['non_tax_revenue_billion'] is None


@pytest.mark.parametrize('redemption',[True,float('nan'),-5000,1e18])
def test_unqualified_redemption_is_withheld(redemption):
    from main import _fiscal_row_to_dict
    row=qualified_row();row.meta['debt_redemption_billion']=redemption
    assert _fiscal_row_to_dict(row)['debt_redemption_billion'] is None


def test_qualified_measure_uses_its_own_source_even_with_legacy_contradiction():
    from main import _fiscal_row_to_dict
    row=qualified_row();row.meta['revenue_source']={'url':'https://cob.go.ke/unrelated-budget.pdf','page':'PDF p.1'}
    result=_fiscal_row_to_dict(row)
    assert result['revenue_source']==result['measure_qualifications']['total_revenue']['source']


@pytest.mark.parametrize('value',[True,False,float('nan'),float('inf'),-1])
def test_parsed_cfs_hostile_number_cannot_become_a_zero_proof(value):
    from seeding.domains.fiscal_summary.fetcher import _apply_budget_estimates
    from test_fiscal_headline_overlay import _Estimates
    estimate=_Estimates();estimate.debt_service_kes=value
    payload={'fiscal_years':[]};before=deepcopy(payload)
    with pytest.raises(ValueError):_apply_budget_estimates(payload,estimate)
    assert payload==before


def test_enhanced_does_not_join_fiscal_amounts_to_calendar_gdp(client, db_session, seed_country, seed_source_doc):
    from datetime import date
    from models import EconomicIndicator
    row=qualified_row();row.source_document_id=seed_source_doc.id
    db_session.add(row)
    db_session.add(EconomicIndicator(entity_id=None,
        indicator_type="total_national_gdp",value=15000000,unit="KES million",
        indicator_date=date(2023,12,31),source_document_id=seed_source_doc.id))
    db_session.commit()
    result=client.get("/api/v1/budget/enhanced")
    assert result.status_code==200
    context=result.json()["economic_context"]
    assert context["gdp_billion_kes"]==15000
    assert context["revenue_to_gdp_pct"] is None
    assert context["budget_to_gdp_pct"] is None
    assert context["fiscal_to_gdp_absent_reason"]=="compatible_fiscal_year_gdp_denominator_required"


def test_finite_inputs_cannot_publish_an_infinite_debt_ratio():
    from services.fiscal_qualification import fiscal_values
    row=qualified_row();row.total_revenue=1e-300;row.debt_service_cost=1e300
    proofs=row.meta['fiscal_measure_contract']['measures']
    proofs['total_revenue']=evidence('total_revenue',1e-300)
    proofs['debt_service_cost']=evidence('debt_service_cost',1e300,basis='total_debt_service_interest_and_principal')
    result=fiscal_values(row)
    assert result['debt_service_per_shilling'] is None
    assert result['absent_reasons']['debt_service_per_shilling']


def test_nested_revenue_parts_must_reconcile_with_their_own_total():
    from services.fiscal_qualification import published_framework
    from test_session3_adversarial_fiscal_outturns import framework
    row=qualified_row();row.meta['fiscal_framework']=framework()
    row.meta['fiscal_framework'].update(ordinary_revenue_billion=101,ministerial_aia_billion=1,total_revenue_incl_aia_billion=100)
    assert published_framework(row) is None


def test_overview_history_budget_citation_comes_from_accepted_proof():
    from services.financial_publication import fiscal_history_entry
    row=qualified_row();row.appropriated_budget=3675e9
    row.meta['budget_basis_source']={'url':'https://wrong.example/unrelated.pdf','page':'p99'}
    proof=evidence('appropriated_budget',3675e9,basis='cob_gross')
    row.meta['fiscal_measure_contract']['measures']['appropriated_budget']=proof
    assert fiscal_history_entry(row)['budget_basis_source']==proof['source']
    proof['source']['sha256']='bad'
    result=fiscal_history_entry(row)
    assert result['appropriated_budget'] is None
    assert result['budget_basis_source'] is None


def test_valid_vintage_cannot_contradict_the_printed_source_column():
    from main import _fiscal_row_to_dict
    row=qualified_row()
    for proof in row.meta['fiscal_measure_contract']['measures'].values():
        proof['source']['column']='Preliminary'
        proof['vintage']='Approved'
    result=_fiscal_row_to_dict(row)
    assert result['total_revenue'] is None
    assert result['tax_revenue'] is None
    assert result['non_tax_revenue'] is None
    assert result['measure_qualifications']=={}

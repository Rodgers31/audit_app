"""Independent actual apply/gate/verdict controls for PR860 review claims."""
from copy import deepcopy
from decimal import Decimal as D
import json
from pathlib import Path

import pytest
from seeding.config import SeedingSettings
from seeding.domains.fiscal_summary import fetcher,fiscal_framework as ff
from seeding.domains.fiscal_summary.budget_estimates import BudgetEstimates
from seeding.domains.fiscal_summary.revenue_estimates import FiscalFrameworkTable,build_revenue_series
from seeding.freshness import get,reset

NEW='https://www.treasury.go.ke/owned/Budget-Summary-FY-2026-27.pdf'
ALTERNATE='https://www.treasury.go.ke/owned/Alternate-Budget-Summary-FY-2026-27.pdf'
OLD='https://www.treasury.go.ke/owned/Budget-Summary-FY-2023-24.pdf'


def pages(name='fy2026_27'):
    doc=json.loads(((Path(__file__).parent / 'fixtures/budget_summary')/(name+'.json')).read_text())
    return [doc['pages'].get(str(i),'')for i in range(1,doc['_source']['page_count']+1)]


def edition(*,altered=False,broken=False):
    text=pages()
    if altered:
        # Two same-FY sources, each with matching narrative and all spending/
        # financing identities: only the recurrent/development allocation differs.
        text=[p.replace('3,538.7','3,548.7').replace('749.0','739.0')for p in text]
    if broken:text[62]=text[62].replace('3,538.7','3,548.7')
    return ff.read_edition(text,fiscal_year='FY 2026/27')


def estimates():
    return BudgetEstimates(fiscal_year='FY 2026/27',voted_gross_kes=D('2922706913184'),
        voted_current_kes=D('2078271468734'),voted_capital_kes=D('844435444450'),
        cfs_kes=D('2563000000000'),source_url='https://www.treasury.go.ke/owned/Approved-PBB-FY-2026-27.pdf',
        page_refs={'voted_total':1,'cfs_summary':2},checks=['owned coherent typed parser-output fixture'])


def revenue(missing):
    ordinary={'FY2026/27':[D('2901.9'),D('2985.7')]}
    total={'FY2026/27':[D('3534.2'),D('3629.7')]}
    aia={'FY2026/27':[D('632.4'),D('644.0')]}
    if not missing:
        ordinary['FY2025/26']=[D('2754.7'),D('2784.4')]
        total['FY2025/26']=[D('3321.7'),D('3399.1')]
        aia['FY2025/26']=[D('566.9'),D('614.6')]
    # Actual revenue builder gates run; omissions are source absence, not a
    # synthetic refused= status or a patched apply function.
    series,quarantine=build_revenue_series(FiscalFrameworkTable(ordinary_revenue=ordinary,total_revenues=total,ministerial_aia=aia,page=14),through_fiscal_year='FY 2026/27',source_url=NEW)
    assert quarantine=={}
    return series


@pytest.mark.parametrize('missing',[False,True],ids=['complete-series','missing-existing-year'])
@pytest.mark.parametrize('prior',[2754.7,2784.4],ids=['prior-original-column','prior-revised-column'])
def test_revenue_component_requires_current_per_year_coverage(monkeypatch,missing,prior):
    base={'fiscal_years':[
        {'fiscal_year':'FY 2025/26','appropriated_budget':4690,'budget_basis':'cob_gross','total_revenue':prior,
         'revenue_basis':'ordinary_revenue_excl_aia','revenue_source':{'url':NEW}},
        {'fiscal_year':'FY 2026/27','appropriated_budget':5485.7,'budget_basis':'cob_gross','total_revenue':2985.7,
         'revenue_basis':'ordinary_revenue_excl_aia','revenue_source':{'url':NEW}}]}
    series=revenue(missing);ed=edition()
    monkeypatch.setattr(fetcher,'load_json_resource',lambda **kw:deepcopy(base))
    monkeypatch.setattr(fetcher,'_fetch_cob_headlines',lambda *a:(None,None,None))
    monkeypatch.setattr(fetcher,'_fetch_budget_estimates',lambda *a:(estimates(),'owned typed fixture'))
    monkeypatch.setattr(fetcher,'_fetch_revenue_estimates',lambda *a,**kw:(series,'owned gated revenue source'))
    monkeypatch.setattr(fetcher,'_fetch_budget_summary_editions',lambda *a:([(NEW,ed)],
        {'budget_summary_listing_status':'read','budget_summary_editions':{NEW:{'fiscal_year':'FY 2026/27','status':'read'}}}))
    reset('fiscal_summary')
    try:
        result=fetcher.fetch_fiscal_summary_payload(None,SeedingSettings(_env_file=None,live_pdf_fetch_enabled=True,enrich_with_worldbank=False))
        components=result['_run_facts']['refresh_components'];mode=get('fiscal_summary')
        observed={'missing':missing,'prior_value':prior,'series_years':list(series),'freshness':mode,'components':components,'rows':result['fiscal_years']}
        assert components['budget']['state']=='live'
        assert components['framework']['state']=='live',observed
        if missing:
            assert components['revenue']['state']!='live',observed
            assert mode['mode']!='live',observed
        else:
            assert components['revenue']['state']=='live'and mode['mode']=='live',observed
    finally:reset('fiscal_summary')


@pytest.mark.parametrize('reverse',[False,True],ids=['A-then-B','B-then-A'])
def test_same_year_conflicting_approved_editions_refuse_before_promotion(reverse):
    a,b=edition(),edition(altered=True)
    # Each candidate independently passes actual narrative/column/arithmetic gates.
    sa=ff.split_for_fiscal_year(a,'FY 2026/27',known_ordinary_revenue=2985.7)
    sb=ff.split_for_fiscal_year(b,'FY 2026/27',known_ordinary_revenue=2985.7)
    assert sa.values['recurrent']==D('3538.7')and sb.values['recurrent']==D('3548.7')
    assert sa.values['development']==D('749.0')and sb.values['development']==D('739.0')
    candidates=[(NEW,a),(ALTERNATE,b)]
    if reverse:candidates.reverse()
    result,status=fetcher._apply_fiscal_framework({'fiscal_years':[{'fiscal_year':'FY 2026/27',
        'total_revenue':2985.7,'revenue_source':{'url':NEW}}]},candidates)
    row=result['fiscal_years'][0]
    assert 'recurrent_spending'not in row and 'fiscal_framework'not in row,{'status':status,'row':row}


def test_identical_same_year_editions_are_not_a_financial_conflict():
    a=edition()
    result,status=fetcher._apply_fiscal_framework({'fiscal_years':[{'fiscal_year':'FY 2026/27',
        'total_revenue':2985.7,'revenue_source':{'url':NEW}}]},[(NEW,a),(ALTERNATE,deepcopy(a))])
    row=result['fiscal_years'][0]
    assert status.startswith('applied=')and row['recurrent_spending']==3538.7


@pytest.mark.parametrize('revenue_source',[NEW,OLD],ids=['newer-actual-vintage','older-approved-vintage'])
def test_distinct_edition_year_vintages_keep_the_document_join(revenue_source):
    newest=edition();old=ff.read_edition(pages('fy2023_24'),fiscal_year='FY 2023/24')
    old_split=ff.split_for_fiscal_year(old,'FY 2023/24',known_ordinary_revenue=None)
    ordinary=2288.9 if revenue_source==NEW else float(old_split.values['ordinary_revenue'])
    result,status=fetcher._apply_fiscal_framework({'fiscal_years':[{'fiscal_year':'FY 2023/24',
        'total_revenue':ordinary,'revenue_source':{'url':revenue_source}}]},[(NEW,newest),(OLD,old)])
    row=next(r for r in result['fiscal_years']if r['fiscal_year']=='FY 2023/24')
    expected=3605.2 if revenue_source==NEW else 3599.3
    assert row['fiscal_framework']['total_expenditure_billion']==expected
    assert row['fiscal_framework']['source']['url']==revenue_source


def test_wrong_historical_source_cannot_borrow_latest_edition_column():
    before={'fiscal_year':'FY 2023/24','total_revenue':2288.9,'revenue_source':{'url':'https://www.treasury.go.ke/unrelated.pdf'}}
    result,_=fetcher._apply_fiscal_framework({'fiscal_years':[deepcopy(before)]},[(NEW,edition())])
    assert next(r for r in result['fiscal_years']if r['fiscal_year']=='FY 2023/24')==before


def test_single_unbalanced_edition_still_refuses_its_money():
    result,status=fetcher._apply_fiscal_framework({'fiscal_years':[{'fiscal_year':'FY 2026/27',
        'total_revenue':2985.7,'revenue_source':{'url':NEW}}]},[(NEW,edition(broken=True))])
    row=result['fiscal_years'][0]
    assert 'recurrent_spending'not in row and 'does_not_reconcile'in status

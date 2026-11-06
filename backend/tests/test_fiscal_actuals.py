"""Pinned official actual-table parsing and atomic source transition."""
from copy import deepcopy
from pathlib import Path

import pytest
from seeding.domains.fiscal_summary.actuals import read_apdmr, parse_apdmr_table, apply_apdmr

PDF=Path(__file__).parent/'fixtures/fiscal_actuals/apdmr-2022-23.pdf'


def test_real_official_actual_table_and_transition():
    parsed=read_apdmr(PDF)
    assert parsed['Ordinary Revenue']==2041.119
    assert parsed['Total Debt Service']==1201.033
    payload={'fiscal_years':[{'fiscal_year':'FY 2022/23','total_revenue':2042,'debt_service_cost':1162},
                             {'fiscal_year':'FY 2023/24','total_revenue':2288.9}]}
    sibling=deepcopy(payload['fiscal_years'][1])
    apply_apdmr(payload,parsed)
    row=payload['fiscal_years'][0]
    assert row['total_revenue']==2041.119
    assert row['debt_service_cost']==1201.033
    assert row['tax_revenue'] is None
    assert row['non_tax_revenue'] is None
    assert payload['fiscal_years'][1]==sibling
    before=deepcopy(payload)
    apply_apdmr(payload,parsed)
    assert payload==before


@pytest.mark.parametrize('bad',[None,{},[],True,{'Ordinary Revenue':True,'Total Debt Service':1201.033},
    {'Ordinary Revenue':float('nan'),'Total Debt Service':1201.033},
    {'Ordinary Revenue':2042,'Total Debt Service':1162}])
def test_direct_transition_refuses_unbound_values_without_partial_mutation(bad):
    payload={'fiscal_years':[{'fiscal_year':'FY 2022/23','total_revenue':2042}]}
    before=deepcopy(payload)
    with pytest.raises(ValueError):apply_apdmr(payload,bad)
    assert payload==before


def test_native_table_hostile_boundaries():
    import pdfplumber
    with pdfplumber.open(PDF)as pdf:
        cover=pdf.pages[0].extract_text();text=pdf.pages[36].extract_text()
    for before,after in [('Jun-23*','Jun-24*'),('Ksh Million','USD Million'),('*Provisional','Final'),
        ('1,201,033','NaN'),('Ordinary Revenue','Ordinary Receipts')]:
        assert before in text
        with pytest.raises(ValueError):parse_apdmr_table(cover,text.replace(before,after))
    for suffix in ['\nOrdinary Revenue','\nOrdinary Revenue NaN','\nOrdinary Revenue 1 2 3 4 5']:
        modified=text.replace('As a percentage of Export',suffix+'\nAs a percentage of Export')
        with pytest.raises(ValueError):parse_apdmr_table(cover,modified)
    with pytest.raises(ValueError):parse_apdmr_table(cover.replace('2022/2023','2023/2024'),text)


def test_real_brop_printed_split_remains_separate_from_apdmr():
    from seeding.domains.fiscal_summary.actuals import read_brop
    split=read_brop(PDF.with_name('brop-2023.pdf'))
    assert split['ordinary_revenue_billion']==2041
    assert split['tax_revenue_billion']==1887
    assert split['non_tax_revenue_billion']==154
    assert split['aia_billion']==319
    assert split['total_revenue_incl_aia_billion']==2361
    assert split['precision_kes']==1e9


def test_actuals_capability_cannot_be_created_from_constants_or_serialization():
    import pickle
    from seeding.domains.fiscal_summary.actuals import ParsedAPDMR
    genuine=read_apdmr(PDF)
    forged=dict.__new__(ParsedAPDMR);dict.update(forged,dict(genuine))
    for bad in (dict(genuine),forged,pickle.loads(pickle.dumps(genuine))):
        payload={'fiscal_years':[{'fiscal_year':'FY 2022/23'}]}
        with pytest.raises(ValueError):apply_apdmr(payload,bad)
        assert payload=={'fiscal_years':[{'fiscal_year':'FY 2022/23'}]}


@pytest.mark.parametrize('contract',[{'version':'future-v2','measures':{}},{'version':'fiscal-measures-v1','measures':[]}])
def test_actuals_reject_prior_contract_corruption_atomically(contract):
    payload={'fiscal_years':[{'fiscal_year':'FY 2022/23','fiscal_measure_contract':contract}]}
    before=deepcopy(payload)
    with pytest.raises(ValueError):apply_apdmr(payload,read_apdmr(PDF))
    assert payload==before

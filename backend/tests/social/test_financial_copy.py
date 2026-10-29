"""Deterministic editorial copy from owned typed facts; no source acquisition."""
from copy import deepcopy

import pytest

from social.generation.contracts import SourceObservation
from social.generation.service import render, render_for_revision, generator_metadata
from social.service import SocialError
from test_generation import observation


def financial(domain='pending_bills', *, value='86899380000.00', notes=''):
    raw=observation().model_dump(mode='json')
    raw.update(source_key=f'cob:financial:{domain}:owned',ingestion_id='1',category='debt_update',
        title='Nairobi County pending bills data',financial=dict(native_domain=domain,record_id=1,
            report_record_id=1,authority_fingerprint='b'*64,period_start='2025-07-01',
            period_end='2026-06-30',published_on='2026-09-25'))
    fact=raw['facts'][0]
    fact.update(fact_id='owned:outstanding',entity='Nairobi County',metric='Reported pending bills: county',
        value=value,scale='units',period='FY 2025/26',publisher='Office of the Controller of Budget',
        published_on='2026-09-25',canonical_url='https://www.auditgava.com/debt',
        document_url='https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482',
        comparison_basis='publisher-reported Grand Total stock as at 2026-06-30; completeness is not assumed'+notes)
    if domain=='national_budget':
        raw.update(category='budget_update',title='Kenya national budget data')
        fact.update(entity='Kenya',metric='Actual expenditure: Health',value='1200000000.00',
            fact_id='owned:actual_spent',comparison_basis='actual expenditure, same sector and annual reporting period',
            document_url='https://cob.go.ke/download/national-government-budget-implementation-review-report-fy-2025-2026/?wpdmdl=16454',
            canonical_url='https://www.auditgava.com/budget')
        budget=deepcopy(fact);budget.update(metric='Revised gross budget: Health',value='1500000000.00',
            fact_id='owned:allocated_amount',comparison_basis='revised gross budget, same sector and annual reporting period')
        raw['facts']=[budget,fact]
    elif domain=='revenue_by_source':
        raw.update(source_type='kra',source_key='kra:financial:revenue_by_source:owned',category='budget_update',
            title='Kenya revenue by source data')
        fact.update(entity='Kenya',metric='Revenue collected: Customs departmental collections, including agency levies',
            value='800.25',scale='billions',publisher='Kenya Revenue Authority',
            document_url='https://www.kra.go.ke/news-center/press-release/2235-result',
            comparison_basis='published collections on the same revenue-head basis and annual reporting period',
            canonical_url='https://www.auditgava.com/revenue')
    return SourceObservation.model_validate(raw)


def test_nairobi_copy_leads_with_an_exact_readable_figure_and_retains_the_limit():
    source=financial();before=source.model_dump(mode='json')
    text=render(source)
    assert text == (
        'Nairobi County: KSh 86,899,380,000 in reported pending bills as at 30 June 2026.\n\n'
        'This is the report’s Grand Total. Completeness is not established by this figure.\n\n'
        'Source: Office of the Controller of Budget, FY 2025/26.\n\n'
        'Explore the figures and original source on AuditGava.')
    assert source.model_dump(mode='json')==before
    assert generator_metadata(source)['template_version']=='financial-v2'


def test_pending_bills_reader_notes_are_explicit_in_the_post():
    text=render(financial(notes='; assembly figure not reported; publisher marks this row inconsistent; chapter table differs from the Grand Total'))
    assert 'The assembly figure was not reported.' in text
    assert 'The publisher marks this row as inconsistent.' in text
    assert 'The chapter table differs from the Grand Total.' in text


def test_budget_copy_distinguishes_reported_spending_from_revised_budget():
    text=render(financial('national_budget'))
    assert 'Kenya: KSh 1,200,000,000 in actual expenditure for Health in FY 2025/26.' in text
    assert 'The revised gross budget for the same sector and reporting year was KSh 1,500,000,000.' in text
    assert '%' not in text and 'overspent' not in text.lower()


def test_revenue_copy_keeps_departmental_scope_and_source_scale():
    text=render(financial('revenue_by_source'))
    assert 'Kenya, FY 2025/26: KSh 800.25 billion reported for Customs departmental collections, including agency levies.' in text
    assert 'Source: Kenya Revenue Authority' in text
    assert 'tax revenue' not in text.lower()


def test_other_fact_templates_keep_their_existing_bytes_and_version():
    source=observation()
    assert render(source)==('County expenditure dataset is available on AuditGava.\n'
        'County fixture — Approved budget, FY2025/26: 123.45 millions KES (actual; County total).')
    assert generator_metadata(source)['template_version']=='factual-v1'


def test_saved_financial_v1_text_is_reproducible_after_the_new_template():
    source=financial()
    metadata=generator_metadata(source,template_version='factual-v1')
    expected=('Nairobi County pending bills data.\nNairobi County — Reported pending bills: county, '
        'FY 2025/26: 86899380000.00 units KES (actual; publisher-reported Grand Total stock as at '
        '2026-06-30; completeness is not assumed).')
    assert render_for_revision(source,metadata)==expected
    assert render(source)!=expected


@pytest.mark.parametrize('value,expected',[
    ('0.00','KSh 0'),('1.00','KSh 1'),('1000.0100','KSh 1,000.01'),
    ('0.00000001','KSh 0.00000001'),
    ('999999999999999999.99999999','KSh 999,999,999,999,999,999.99999999'),
])
def test_copy_formats_exact_decimals_without_float_or_rounding(value,expected):
    assert expected+' in reported pending bills' in render(financial(value=value))


@pytest.mark.parametrize('scale,suffix',[('units',''),('thousands',' thousand'),('millions',' million'),('billions',' billion')])
def test_copy_retains_the_supplied_scale_exactly(scale,suffix):
    raw=financial(value='12.50').model_dump(mode='json');raw['facts'][0]['scale']=scale
    assert 'KSh 12.5'+suffix+' in reported pending bills' in render(SourceObservation.model_validate(raw))


@pytest.mark.parametrize('field,value',[
    ('comparison_basis','An unreviewed reporting basis'),('unit','USD'),('classification','projected'),
])
@pytest.mark.parametrize('domain',['pending_bills','national_budget','revenue_by_source'])
def test_unrecognized_financial_meaning_cannot_use_the_actual_kes_template(domain,field,value):
    raw=financial(domain).model_dump(mode='json');raw['facts'][0][field]=value
    with pytest.raises(SocialError,match='UNRESOLVED_TEMPLATE'):
        render(SourceObservation.model_validate(raw))


@pytest.mark.parametrize('metadata',[None,{}, {'template_version':'financial-v999'},
    {'template_version':True}, {'template_version':'financial-v2','detector_version':1,'fact_ids':[]}])
def test_revision_rendering_never_guesses_an_unknown_or_missing_version(metadata):
    with pytest.raises(SocialError):render_for_revision(financial(),metadata)


def test_unknown_reader_note_is_kept_verbatim_and_correction_stays_visible():
    source=financial(notes='; reconciliation remains outstanding')
    raw=source.model_dump(mode='json');raw['correction_pending']=True
    text=render(SourceObservation.model_validate(raw))
    assert text.startswith('Correction awaiting human review.')
    assert 'reconciliation remains outstanding' in text


def test_pending_bill_subscope_cannot_be_lost_in_a_county_headline():
    raw=financial().model_dump(mode='json')
    raw['facts'][0]['metric']='Reported pending bills: County Assembly'
    assert 'Nairobi County (County Assembly):' in render(SourceObservation.model_validate(raw))


@pytest.mark.parametrize('version',[True,1.0])
def test_revision_metadata_preserves_json_scalar_types(version):
    source=financial();metadata=generator_metadata(source);metadata['detector_version']=version
    with pytest.raises(SocialError,match='EVIDENCE_INTEGRITY_FAILED'):
        render_for_revision(source,metadata)


def test_unvalidated_model_copy_cannot_turn_a_boolean_into_money():
    from pydantic import ValidationError
    source=financial();bad=source.model_copy(update={'facts':(source.facts[0].model_copy(update={'value':True}),)})
    with pytest.raises(ValidationError):render(bad)


def test_pinned_legacy_rendering_also_refuses_an_unvalidated_boolean_amount():
    from pydantic import ValidationError
    source=financial();bad=source.model_copy(update={'facts':(source.facts[0].model_copy(update={'value':True}),)})
    metadata=generator_metadata(source,template_version='factual-v1')
    with pytest.raises(ValidationError):render_for_revision(bad,metadata)


def test_unsupported_source_schema_cannot_be_rendered_as_a_known_template():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):render(observation().model_copy(update={'schema_version':99}))


def test_json_serialization_cannot_certify_an_unvalidated_decimal_type():
    from decimal import Decimal
    from pydantic import ValidationError
    source=financial();bad=source.model_copy(update={'facts':(source.facts[0].model_copy(update={'value':Decimal('1')}),)})
    with pytest.raises(ValidationError):render(bad)

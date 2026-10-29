"""Cross-entity/category coverage of the shared evidence-to-copy engine."""
from copy import deepcopy
from decimal import localcontext

import pytest
from pydantic import ValidationError
from social.contracts import canonical_hash
from social.generation.contracts import SourceObservation
from social.generation.service import render, generator_metadata, render_for_revision, semantic_fingerprint
from social.automation.service import source_scope
from social.service import SocialError
from test_generation import observation
from test_financial_copy import financial
from test_report_generation import report_observation


@pytest.mark.parametrize('entity', ['Mombasa County', 'Kisumu County', 'Garissa County', 'Kenya national government'])
@pytest.mark.parametrize('category', ['dataset_availability', 'new_report', 'debt_update', 'budget_update', 'audit_finding', 'correction'])
@pytest.mark.parametrize('source', ['treasury', 'cob', 'oag', 'knbs', 'cra', 'kra'])
def test_every_existing_fact_family_uses_the_same_rules_without_a_nairobi_dependency(entity,category,source):
    raw=observation().model_dump(mode='json')
    raw.update(source_type=source,category=category,title='Public finance figures to explore')
    raw['facts'][0].update(entity=entity,value='36000000.00',scale='units',metric='Reported amount')
    typed=SourceObservation.model_validate(raw);before=typed.model_dump(mode='json');fingerprint=semantic_fingerprint(typed)
    text=render(typed)
    assert entity in text and 'KSh 36 million' in text and '36000000' not in text
    assert 'Nairobi' not in text and 'units KES' not in text
    assert 'County total' in text and 'Controller of Budget' in text
    assert typed.model_dump(mode='json')==before and semantic_fingerprint(typed)==fingerprint
    assert generator_metadata(typed)['template_version']=='factual-v2'
    if category=='correction':assert text.startswith('Correction awaiting human review.')


@pytest.mark.parametrize('classification,label',[('actual','Reported figure'),('modelled','Modelled estimate'),('projected','Projection')])
@pytest.mark.parametrize('value,scale,unit,expected',[
    ('86899380000.00','units','KES','about KSh 86.9 billion'),
    ('36','millions','USD','36 million USD'),('74.25','units','%','74.25%'),
    ('0.125','units','ratio','0.125 ratio'),('1500000','units','people','1.5 million people'),
    ('0.00000001','units','tonnes','0.00000001 tonnes'),
])
def test_units_and_nonactual_classification_cannot_be_rewritten_as_actual_kes(classification,label,value,scale,unit,expected):
    raw=observation().model_dump(mode='json');raw['facts'][0].update(value=value,scale=scale,unit=unit,classification=classification)
    with localcontext() as ctx:
        ctx.prec=2
        text=render(SourceObservation.model_validate(raw))
    assert expected in text and label in text
    if unit!='KES':assert 'KSh' not in text


def test_multiple_entities_and_sources_keep_each_figure_scope_and_basis():
    raw=observation().model_dump(mode='json');other=deepcopy(raw['facts'][0])
    other.update(fact_id='second',entity='Kisumu County',publisher='National Treasury',period='FY2024/25',comparison_basis='Distinct reporting scope',value='7',scale='billions')
    raw['facts'].append(other);text=render(SourceObservation.model_validate(raw))
    assert 'County fixture, FY2025/26' in text and 'Kisumu County, FY2024/25' in text
    assert 'KSh 7 billion' in text and 'Distinct reporting scope' in text and 'National Treasury' in text
    assert 'total of' not in text.lower() and '%' not in text


@pytest.mark.parametrize('domain',['national_budget','revenue_by_source','audits','pending_bills'])
def test_every_native_report_family_has_a_neutral_plain_announcement(domain):
    from seeding.native_report_authority import DOMAINS
    source,hosts,publisher,path=DOMAINS[domain]
    raw=report_observation();raw.update(source_type=source,source_key=f'{source}:native:{domain}:1:owned')
    raw['report'].update(native_domain=domain,scope_key='owned',entity='Kenya' if domain!='audits' else 'Mombasa County',publisher=publisher,document_url=f'https://{hosts[0]}/owned-report.pdf',canonical_url='https://www.auditgava.com'+path)
    typed=SourceObservation.model_validate(raw);text=render(typed)
    assert typed.report.entity in text and 'explore' in text and '1 July 2026' in text
    assert publisher in text and 'KSh' not in text and 'Verified reporting scope' not in text
    assert render_for_revision(typed,generator_metadata(typed,template_version='report-availability-v1')).startswith('Report available from ')


def test_county_report_replays_saved_v1_without_claiming_new_publication():
    source=SourceObservation.model_validate(report_observation())
    old=render_for_revision(source,generator_metadata(source,template_version='report-availability-v1'))
    assert 'Publisher publication date: 2026-07-01.' in old
    assert 'budget implementation report for FY2025/26' in render(source)
    assert 'newly published' not in render(source).lower()


def test_catalogue_is_not_a_publication_or_a_figure_claim(tmp_path):
    from test_kra_catalogue import capture,report,observation as catalogue_observation
    source=SourceObservation.model_validate(catalogue_observation(report(capture(tmp_path)[0])))
    text=render(source)
    assert 'catalogue' in text and '8 July 2026' in text and 'publication date is not stated' in text
    assert '2.8' not in text and 'KSh' not in text
    old=render_for_revision(source,generator_metadata(source,template_version='catalogue-availability-v1'))
    assert 'Official KRA catalogue entry dated 2026-07-08.' in old


def test_new_words_do_not_inherit_an_old_automatic_copy_scope():
    source=observation();fact=source.facts[0]
    legacy_scope={'source_type':source.source_type,'source_key':source.source_key,'category':source.category,'title':source.title,
        'fact':fact.model_dump(mode='json',exclude={'value','published_on','retrieved_at','verified_at','document_checksum'})}
    assert source_scope(source,template_version='factual-v1')==canonical_hash(legacy_scope)
    assert source_scope(source)!=source_scope(source,template_version='factual-v1')
    report=SourceObservation.model_validate(report_observation())
    assert source_scope(report)!=source_scope(report,template_version='report-availability-v1')


def test_saved_generic_v1_text_remains_exact():
    source=observation()
    assert render_for_revision(source,generator_metadata(source,template_version='factual-v1'))==(
        'County expenditure dataset is available on AuditGava.\nCounty fixture — Approved budget, FY2025/26: 123.45 millions KES (actual; County total).')


@pytest.mark.parametrize('bad',[True,1.5,None,b'1'])
def test_unvalidated_values_and_unknown_versions_cannot_enter_any_new_template(bad):
    source=observation();bad_source=source.model_copy(update={'facts':(source.facts[0].model_copy(update={'value':bad}),)})
    with pytest.raises(ValidationError):render(bad_source)
    with pytest.raises(SocialError,match='UNRESOLVED_TEMPLATE'):render_for_revision(source,{'template_version':'invented-v2'})

"""Report links select qualified evidence, preserving each saved copy contract."""
import pytest
from decimal import Decimal
from pydantic import ValidationError
from social.service import SocialError
from social.generation.contracts import SourceObservation
from social.generation.destination import draft_destination
from social.generation.service import generator_metadata, render_for_revision, semantic_fingerprint
from social.automation.service import source_scope
from test_report_generation import report_observation


@pytest.mark.parametrize('domain',['national_budget','revenue_by_source','audits','pending_bills'])
def test_new_report_goes_to_its_original_document_and_old_reviewed_links_replay(domain):
    from seeding.native_report_authority import DOMAINS
    source,hosts,publisher,path=DOMAINS[domain]
    raw=report_observation();raw.update(source_type=source,source_key=f'{source}:native:{domain}:1:owned')
    raw['report'].update(native_domain=domain,scope_key='owned',entity='Kenya',publisher=publisher,
        document_url=f'https://{hosts[0]}/owned-FY2025-26-report.pdf',canonical_url='https://www.auditgava.com'+path)
    observation=SourceObservation.model_validate(raw);before=observation.model_dump(mode='json');fingerprint=semantic_fingerprint(observation)
    assert draft_destination(None,observation)==observation.report.document_url
    metadata=generator_metadata(observation)
    assert metadata['template_version']=='report-availability-v3'
    assert 'Read the original report on the publisher’s website.' in render_for_revision(observation,metadata)
    for old in ('report-availability-v1','report-availability-v2'):
        assert draft_destination(None,observation,template_version=old)==observation.report.canonical_url
        assert source_scope(observation,template_version=old)!=source_scope(observation)
    assert render_for_revision(observation,generator_metadata(observation,template_version='report-availability-v2')).endswith('Read the report and follow its source on AuditGava.')
    assert before==observation.model_dump(mode='json') and fingerprint==semantic_fingerprint(observation)


def test_catalogue_goes_to_exact_entry_without_inventing_a_publication_date(tmp_path):
    from test_kra_catalogue import capture,report,observation
    source=SourceObservation.model_validate(observation(report(capture(tmp_path)[0])))
    assert draft_destination(None,source)==source.report.document_url
    assert generator_metadata(source)['template_version']=='catalogue-availability-v3'
    assert 'publication date is not stated' in render_for_revision(source,generator_metadata(source))
    assert render_for_revision(source,generator_metadata(source)).endswith('Read the original report entry on the publisher’s website.')
    for old in ('catalogue-availability-v1','catalogue-availability-v2'):
        assert draft_destination(None,source,template_version=old)==source.report.canonical_url


@pytest.mark.parametrize('mutation',['report-url','financial-url','schema','boolean-amount','decimal-amount'])
def test_direct_destination_refuses_unvalidated_models(mutation):
    from test_financial_copy import financial
    source=SourceObservation.model_validate(report_observation()) if mutation in ('report-url','schema') else financial('national_budget')
    if mutation=='report-url':
        source=source.model_copy(update={'report':source.report.model_copy(update={'document_url':'javascript:alert(1)'})})
    elif mutation=='schema':
        source=source.model_copy(update={'schema_version':99})
    else:
        change={'document_url':'javascript:alert(1)'} if mutation=='financial-url' else {'value':True if mutation=='boolean-amount' else Decimal('1')}
        source=source.model_copy(update={'facts':(source.facts[0].model_copy(update=change),*source.facts[1:])})
    with pytest.raises((ValidationError,SocialError)):
        draft_destination(None,source)


@pytest.mark.parametrize('version',['invented-v99',None,True,1,'financial-v4','catalogue-availability-v3','factual-v2'])
def test_direct_report_renderer_refuses_unknown_and_foreign_versions(version):
    from social.generation.social_copy import render_social
    with pytest.raises(SocialError,match='UNRESOLVED_TEMPLATE'):
        render_social(SourceObservation.model_validate(report_observation()),version=version)


def test_financial_source_cannot_use_the_general_fact_helper():
    from social.generation.social_copy import render_social
    from test_financial_copy import financial
    with pytest.raises(SocialError,match='UNRESOLVED_TEMPLATE'):
        render_social(financial('national_budget'),version='factual-v2')

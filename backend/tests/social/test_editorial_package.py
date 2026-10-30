"""Context, exact scope and site-first publication contracts."""
from copy import deepcopy
from decimal import localcontext
from urllib.parse import urlsplit, parse_qs

import pytest
from social.destinations import on_site, publication_destination_problem
from social.generation.contracts import SourceObservation
from social.generation.service import generator_metadata, render, render_for_revision
from social.generation.editorial import hashtags, document_for_revision, account_caption, policy
from services.public_report_view import report_view_url, view_snapshot
from test_financial_copy import financial
from test_financial_destination import reader
from test_report_generation import report_observation


@pytest.mark.parametrize('entity,expected',[('Mombasa County','#MombasaCounty'),('Garissa County','#GarissaCounty'),("Murang’a County",'#MurangaCounty')])
def test_county_topic_and_location_come_from_the_actual_post(entity,expected):
    raw=financial().model_dump(mode='json');raw['facts'][0]['entity']=entity
    source=SourceObservation.model_validate(raw)
    assert hashtags(source,'facebook')==('#PendingBills',expected)
    assert hashtags(source,'instagram')==('#PendingBills',expected,'#AuditGava')
    assert hashtags(source,'threads')==('#PendingBills',)


@pytest.mark.parametrize('metric,tag',[('Revenue collected: PAYE','#PAYE'),('Revenue collected: Customs','#CustomsRevenue'),
    ('Revenue collected: VAT','#VAT'),('Revenue collected: Corporation Tax','#CorporationTax')])
def test_revenue_heads_are_not_given_the_same_generic_tags(metric,tag):
    raw=financial('revenue_by_source').model_dump(mode='json');raw['facts'][0]['metric']=metric
    source=SourceObservation.model_validate(raw)
    assert hashtags(source,'instagram')==(tag,'#Kenya','#AuditGava')


def test_sector_tags_require_budget_context_and_do_not_turn_health_data_into_spending():
    assert hashtags(financial('national_budget'),'facebook')==('#HealthBudget','#Kenya')
    from test_generation import observation
    raw=observation().model_dump(mode='json');raw['category']='audit_finding';raw['facts'][0]['metric']='Health service observations'
    assert '#HealthBudget' not in hashtags(SourceObservation.model_validate(raw))


@pytest.mark.parametrize('domain',['national_budget','revenue_by_source'])
def test_new_national_package_stays_on_site_and_preserves_exact_evidence(domain):
    source=financial(domain);before=source.model_dump(mode='json');metadata=generator_metadata(source)
    document=document_for_revision(None,source,metadata)
    assert metadata['template_version']=='financial-v5'
    assert metadata['editorial_policy']=='auditgava-editorial-v1'
    assert urlsplit(document.master.link).path.startswith('/reports/'+domain+'/')
    assert on_site(document.master.link) and document.master.hashtags
    assert 'publisher’s website' not in document.master.text and 'on AuditGava' in document.master.text
    assert source.model_dump(mode='json')==before
    for old in ('factual-v1','financial-v2','financial-v3','financial-v4'):
        assert render_for_revision(source,generator_metadata(source,template_version=old))==render(source,template_version=old)


def test_public_snapshot_is_stable_for_reacquisition_but_changes_with_reported_meaning():
    source=financial('national_budget');raw=source.model_dump(mode='json')
    raw['evidence_version']+=1;raw['ingestion_id']='2';raw['financial']['authority_fingerprint']='c'*64
    raw['facts'][0]['verified_at']=raw['facts'][0]['retrieved_at']
    assert view_snapshot(SourceObservation.model_validate(raw))==view_snapshot(source)
    with localcontext() as context:
        context.prec=2
        assert view_snapshot(source)==parse_qs(urlsplit(report_view_url(source)).query)['snapshot'][0]
    for key,value in [('period','FY2024/25'),('value','12'),('entity','Another entity'),('document_checksum','f'*64)]:
        changed=deepcopy(raw);changed['facts'][0][key]=value
        assert view_snapshot(SourceObservation.model_validate(changed))!=view_snapshot(source)


@pytest.mark.parametrize('link',[None,'https://cob.go.ke/report.pdf','http://www.auditgava.com','https://www.auditgava.com.evil.test/',
    'https://www.auditgava.com@evil.test/','https://www.auditgava.com:444/','https://auditgava.com./'])
def test_publishing_requires_a_real_auditgava_destination(link):
    assert publication_destination_problem(link,'A factual post')=='AUDITGAVA_DESTINATION_REQUIRED'


@pytest.mark.parametrize('text',['Read https://cob.go.ke/report.pdf','See www.example.test/source','See cob.go.ke/report'])
def test_publisher_urls_cannot_hide_in_the_resolved_caption(text):
    assert publication_destination_problem('https://www.auditgava.com/budget',text)=='EXTERNAL_CAPTION_LINK'


def test_secondary_sources_are_not_restricted_by_the_primary_destination_rule():
    from social.contracts import Reference
    assert Reference(url='https://cob.go.ke/report.pdf').url=='https://cob.go.ke/report.pdf'
    assert publication_destination_problem('https://www.auditgava.com/budget','A factual post') is None


def test_editorial_metadata_and_topic_selection_cannot_be_edited_into_automatic_authority():
    source=financial('national_budget');metadata=generator_metadata(source)
    altered=deepcopy(metadata);altered['editorial_policy_hash']='0'*64
    from social.service import SocialError
    with pytest.raises(SocialError,match='EVIDENCE_INTEGRITY_FAILED'):render_for_revision(source,altered)
    assert policy().platforms[0].tag_limit==2



def test_new_draft_preparation_stops_when_editorial_policy_needs_review():
    from datetime import datetime, timezone, timedelta
    from social.generation.editorial import capture_profiles
    from social.service import SocialError
    with pytest.raises(SocialError,match='EDITORIAL_POLICY_REVIEW_REQUIRED'):
        capture_profiles(None,[],datetime.combine(policy().review_due+timedelta(days=1),datetime.min.time(),tzinfo=timezone.utc))


def test_account_defaults_cannot_attest_tiktok_post_consent_or_unseen_media():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from uuid import uuid4
    from social.generation.editorial import capture_profiles
    account_id=uuid4()
    class Reader:
        def get(self,*_args,**_kwargs):return SimpleNamespace(platform='tiktok')
    target={'account_id':str(account_id),'format':'text','tiktok_options':dict(mode='direct',privacy_level='PUBLIC_TO_EVERYONE',upload_consent=True,music_usage_confirmed=True,branded_content_policy_confirmed=True,creator_settings_checked_at='2026-10-29T12:00:00Z',creator_settings_hash='a'*64,photo_title='Old post title')}
    profile=capture_profiles(Reader(),[target],datetime(2026,10,29,tzinfo=timezone.utc))[0]
    assert profile['target']['format']=='video' and 'tiktok_options' not in profile['target']


@pytest.mark.parametrize('separator',[',',';',')','',',www.'])
def test_adjacent_external_urls_cannot_hide_inside_an_onsite_caption_path(separator):
    target='evil.test/source' if separator==',www.' else 'https://evil.test/source'
    assert publication_destination_problem('https://www.auditgava.com/budget','Read https://www.auditgava.com/budget'+separator+target)=='EXTERNAL_CAPTION_LINK'


def test_saved_profile_platform_cannot_be_changed_without_its_frozen_profile_receipt():
    from uuid import uuid4
    from social.service import SocialError
    source=financial('national_budget')
    metadata=generator_metadata(source,editorial_profiles=[{'platform':'facebook','target':{'account_id':str(uuid4()),'format':'text','overrides':{}}}])
    metadata['editorial_profiles'][0]['platform']='x'
    with pytest.raises(SocialError,match='EVIDENCE_INTEGRITY_FAILED'):render_for_revision(source,metadata)


@pytest.mark.parametrize('platform',['x','threads'])
def test_short_numeric_copy_keeps_all_pending_caveats_or_uses_non_numeric_scope(platform):
    source=financial(notes='; assembly figure not reported; publisher marks this row inconsistent; chapter table differs from the Grand Total')
    full=render(source);tags=hashtags(source,platform)
    text=account_caption(source,full,'https://www.auditgava.com/counties/nairobi-county?tab=budget&as_at=2026-06-30#pending-bills',tags,platform)
    assert source.facts[0].publisher in text
    if 'KSh ' in text:
        assert all(note in text.lower() for note in ('assembly figure was not reported','publisher marks this row as inconsistent','chapter table differs'))
    else: assert source.facts[0].entity in text and source.facts[0].period in text

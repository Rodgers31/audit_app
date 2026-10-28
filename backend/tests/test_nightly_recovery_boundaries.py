"""Explicit repair and transfer phases cannot widen ordinary nightly admission."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from seeding.config import SeedingSettings
from seeding import cob_cbirr, freshness, source_plan
from seeding.domains.counties_budget import fetcher
from seeding.extractors import reviewed_proposals as rp
from seeding.extractors.reconciliation import _digest, IncompleteExtraction
from seeding.http_client import PdfDownloadIncomplete

REVIEW='oag-2542-20261026'


def plan(**overrides):
    fields=dict(event='workflow_dispatch',schedule='',domain='',dry_run='false',
                cra='false',opendata='false',discovery='false',audits_review=REVIEW)
    return source_plan.build_plan(**(fields | overrides))


def test_only_explicit_live_audits_plan_forwards_review():
    assert plan(domain='audits').argv[-3:]==['--audits-reconciliation-review',REVIEW,'--no-dry-run']
    ordinary=plan(audits_review='')
    assert '--audits-reconciliation-review' not in ordinary.argv


@pytest.mark.parametrize('overrides',[
    {'event':'schedule','schedule':source_plan.DAILY},
    {'event':'schedule','schedule':source_plan.WEEKLY},
    {'domain':'counties_budget'}, {'dry_run':'true'},
    {'audits_review':'../../different'}, {'audits_review':True},
])
def test_review_never_becomes_scheduled_or_unrelated_authority(overrides):
    with pytest.raises(ValueError):plan(**overrides)


@pytest.mark.parametrize('domain,override,expected',[(600,None,300),(600,420,420),
    (400,420,220),(100,420,1),(600,120,120)])
def test_cob_transfer_leaves_parse_reserve(monkeypatch,tmp_path,domain,override,expected):
    settings=SeedingSettings(total_timeout_seconds=1320,domain_timeout_seconds=domain,cob_pdf_download_timeout_seconds=override)
    seen={}
    monkeypatch.setattr(cob_cbirr,'server_fingerprint',lambda *a:'synthetic')
    from seeding import pdf_download
    def download(*args,**kwargs):seen.update(kwargs);return tmp_path/'source.pdf'
    monkeypatch.setattr(pdf_download,'get_or_download_pdf',download)
    monkeypatch.setattr(pdf_download,'cached_pdf_meta',lambda *a:{})
    cob_cbirr.download_cbirr(object(),'https://example.test/source.pdf',settings)
    assert seen['max_seconds']==expected
    assert settings.total_timeout_seconds==1320 and settings.domain_timeout_seconds==domain


def test_incomplete_live_download_never_loads_fixture(monkeypatch):
    error=PdfDownloadIncomplete('owned bounded transfer',bytes_downloaded=4096)
    def incomplete(*a):raise error
    monkeypatch.setattr(fetcher,'_fetch_from_cob_county_pdf',incomplete)
    monkeypatch.setattr(fetcher,'load_json_resource',lambda **k:pytest.fail('fixture must not reach writer'))
    freshness.reset('counties_budget')
    with pytest.raises(PdfDownloadIncomplete) as caught:
        fetcher.fetch_budget_payload(object(),SeedingSettings(live_pdf_fetch_enabled=True))
    assert caught.value is error
    assert freshness.get('counties_budget')['mode']=='refused'
    assert freshness.get('counties_budget')['reason']=='pdf_download_incomplete'


@pytest.fixture()
def exact_review(monkeypatch,tmp_path):
    # An owned synthetic receipt tests the review boundary. The production
    # receipt is separately qualified against all 1,269 actual PDF candidates.
    monkeypatch.setattr(rp,'__file__',str(tmp_path/'reviewed_proposals.py'))
    rows=[SimpleNamespace(extracted_json={'finding_text':'corrected','amounts':[42],
          'pdf_page':3,'pdf_artifact_binding_v1':{'schema_version':1,'extractor':'oag_county_volume','text_visibility':'visible_only','pdf_pages':8,'artifact':{'schema_version':1,'sha256':'a'*64,'md5':'b'*32,'size_bytes':100,'source_document_id':2542,'source_url':'https://example.test/source.pdf','report_title':'Owned test source','publisher':'Owned test publisher','validation':'pdf_magic_and_final_eof','verification_time':'2026-10-26T00:00:00+00:00','verification_time_reason':None}}},
          page_number=3,confidence=0.9)]
    proposal={'document_id':2542,'source_sha256':'a'*64,'source_md5':'b'*32,'source_url':'https://example.test/source.pdf','previous_sha256':'owned-before',
       'candidate_sha256':'full-with-first-binding','audit_ids':[7], 'retire_ids':[],
       'update_ids':[9],'revised_rows':[{'id':9,'before':{'payload':{'finding_text':'old'},
        'page':3,'confidence':0.9},'after':{'payload':rows[0].extracted_json,'page':3,'confidence':0.9}}]}
    snapshot={k:v for k,v in proposal.items() if k!='candidate_sha256'}
    snapshot['revised_rows']=[{**r,'after':rp.without_binding(r['after'])} for r in proposal['revised_rows']]
    manifest={'proposal_content_sha256':_digest(snapshot),
        'candidate_content_sha256':_digest([rp.without_binding(rp._row(r)) for r in rows]),
        'reason':'Owned synthetic correction checked.'}
    directory=tmp_path/'reviews';directory.mkdir()
    (directory/(REVIEW+'.json')).write_text(json.dumps(manifest))
    return proposal,rows


def test_exact_review_keeps_full_actual_proposal(exact_review):
    proposal,rows=exact_review
    approved=rp.approve(proposal,rows,REVIEW)
    assert approved['proposal'] is proposal and approved['source_complete'] is True
    assert approved['review_id']==REVIEW and approved['reason']


@pytest.mark.parametrize('field',['source_sha256','previous_sha256','audit_ids','retire_ids','update_ids'])
def test_changed_source_history_or_links_refuse(exact_review,field):
    proposal,rows=exact_review
    altered=deepcopy(proposal);altered[field]=None
    with pytest.raises(IncompleteExtraction):rp.approve(altered,rows,REVIEW)


@pytest.mark.parametrize('field',['finding_text','amounts','pdf_page','county_name','fiscal_year'])
def test_changed_full_candidate_refuses(exact_review,field):
    proposal,rows=exact_review
    rows[0].extracted_json={**rows[0].extracted_json,field:None}
    with pytest.raises(IncompleteExtraction):rp.approve(proposal,rows,REVIEW)


def test_empty_partial_candidate_and_unknown_review_refuse(exact_review):
    proposal,rows=exact_review
    with pytest.raises(IncompleteExtraction):rp.approve(proposal,[],REVIEW)
    with pytest.raises(IncompleteExtraction):rp.approve(proposal,rows,'unreviewed')


def test_review_requires_actual_binding_for_every_candidate(exact_review):
    proposal,rows=exact_review
    rows[0].extracted_json.pop('pdf_artifact_binding_v1')
    with pytest.raises(IncompleteExtraction,match='every actual PDF binding'):
        rp.approve(proposal,rows,REVIEW)


@pytest.mark.parametrize('review',[None,REVIEW])
def test_explicit_review_reads_even_when_ordinary_extraction_cache_is_current(tmp_path,monkeypatch,review):
    from seeding.extractors import oag_county_volume as volume
    from seeding import pdf_artifact
    path=tmp_path/'owned.pdf';path.write_bytes(b'%PDF-1.7\nowned fixture\n%%EOF\n')
    document=SimpleNamespace(file_path=str(path))
    monkeypatch.setattr(volume,'already_extracted',lambda *a:9)
    monkeypatch.setattr(pdf_artifact,'extraction_artifact',lambda *a:None)
    class FreshRead(RuntimeError):pass
    def read(*args,**kwargs):raise FreshRead('entered actual source read')
    monkeypatch.setattr(volume,'read_pages',read)
    if review is None:
        assert volume.extract_county_volume(object(),document,SeedingSettings(),known_counties={'mombasa':'Mombasa'})['reason']=='already_extracted'
    else:
        with pytest.raises(FreshRead):
            volume.extract_county_volume(object(),document,SeedingSettings(),known_counties={'mombasa':'Mombasa'},review=review)


def test_explicit_review_cannot_take_a_legacy_delegate_shortcut(tmp_path,monkeypatch):
    from seeding.extractors import oag_county_audit as county
    path=tmp_path/'owned.pdf';path.write_bytes(b'%PDF-1.7\nowned fixture\n%%EOF\n')
    class Session:
        def query(self,*args):pytest.fail('explicit review must enter its volume before legacy shortcuts')
    expected={'created':0,'skipped':0,'reviewed':True}
    seen=[]
    def volume(*args,**kwargs):seen.append(kwargs['review']);return expected
    monkeypatch.setattr(county,'_county_volume_dispatch',volume)
    assert county.extract_county_audit(Session(),SimpleNamespace(file_path=str(path)),SeedingSettings(),review=REVIEW) is expected
    assert seen==[REVIEW]

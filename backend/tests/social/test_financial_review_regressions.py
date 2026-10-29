"""Permanent executed independent review regressions; no live operations."""

from copy import deepcopy
from uuid import UUID
import json
import pytest
from sqlalchemy import select, func, text

import test_native_financial_changes_postgres as producer_fixture
from test_b83_generation_postgres import pg, no_publication
from native_worker_fixture import restricted
from test_native_financial_changes_postgres import enable
from models import RevenueBySource
from social.models import SocialPost, SocialPostRevision
from social.generation.service import consume_observation, verify_generated_revision
from social.generation.preview import preview
from social.generation.models import SourceCursor
from social.service import SocialService, SocialError
from seeding.generation_dispatch import dispatch_committed_generation


@pytest.fixture(autouse=True)
def native_financial_ceiling(monkeypatch):
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED','true')


def ingest(factory, tmp_path, monkeypatch, *, year=2024, paye='560', extra=b'', published=None):
    with monkeypatch.context() as patch:
        article = producer_fixture.HTML.replace(b'2024/2025',f'{year}/{year+1}'.encode()).replace(
            b'10/07/2025',(published or f'10/07/{year+1}').encode())
        patch.setattr(producer_fixture,'HTML',article)
        job,_=producer_fixture.ingest_revenue(factory,tmp_path,patch,paye=paye,extra=extra)
        with factory() as db:
            record=db.execute(select(RevenueBySource.id).where(
                RevenueBySource.revenue_type=='PAYE',
                RevenueBySource.meta['ingestion_job_id'].astext==str(job))).scalar_one()
        return job,record


def read(factory, job, record):
    from seeding.source_observations import read_revenue_financial_observation
    return read_revenue_financial_observation(factory,record_id=record,ingestion_id=job)


def dispatch(factory, job):
    return dispatch_committed_generation(factory,domain='revenue_by_source',ingestion_id=job,dry_run=False,include_reports=False)


def test_newer_native_job_cannot_turn_older_financial_year_into_a_change(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path,monkeypatch,year=2024)
    first=dispatch(factory,job)
    assert first['baselines']>=5,first
    older_job,older_record=ingest(factory,tmp_path,monkeypatch,year=2023,paye='561')
    result=preview(factory,producer_fixture.request(older_job,older_record))
    assert result['results'][0]['status']=='refused',result
    result=dispatch(factory,older_job)
    assert result['drafts_created']==0 and result['refused']>=1,result
    no_publication(factory)


@pytest.mark.parametrize('quarantine',['source evidence changed','operator withheld'])
def test_explicit_quarantined_financial_row_cannot_be_promoted(pg,tmp_path,monkeypatch,quarantine):
    from seeding.source_observations import SourceObservationUnavailable
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path,monkeypatch)
    read(factory,job,record)
    with factory.begin() as db:
        row=db.get(RevenueBySource,record)
        row.quarantine_reason=quarantine
        row.publishable=False
    with pytest.raises(SourceObservationUnavailable):
        read(factory,job,record)
    no_publication(factory)


def test_same_value_evidence_refresh_has_explicit_recovery_for_existing_draft(restricted,tmp_path,monkeypatch):
    factory,_,_,_=restricted;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path,monkeypatch)
    assert dispatch(factory,job)['drafts_created']==0
    job,record=ingest(factory,tmp_path,monkeypatch,paye='561')
    assert dispatch(factory,job)['drafts_created']==1
    same,record=ingest(factory,tmp_path,monkeypatch,paye='561',extra=b'<!-- layout -->')
    result=dispatch(factory,same)
    assert result['drafts_created']==0,result
    with factory.begin() as db:
        post=db.scalar(select(SocialPost))
        revision=db.get(SocialPostRevision,post.current_revision_id)
        try:
            verify_generated_revision(db,post,revision)
        except SocialError:
            pass
        else:
            return  # Original immutable proof still qualifies the same business facts.
    value=read(factory,same,record)
    with factory.begin() as db:
        recovered=consume_observation(SocialService(db),value,backfill=True)
    assert recovered['status']=='draft_created',recovered
    with factory.begin() as db:
        post=db.get(SocialPost,UUID(recovered['post_id']))
        revision=db.get(SocialPostRevision,post.current_revision_id)
        verify_generated_revision(db,post,revision)
    no_publication(factory)


def test_financial_source_marker_requires_exact_json_scalar_types(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path,monkeypatch)
    assert dispatch(factory,job)['baselines']>=5
    with factory.begin() as db:
        marker=db.scalar(select(SourceCursor).where(SourceCursor.source_key.endswith(':baseline')))
        state=deepcopy(marker.report_state)
        state['financial_baseline']=True
        db.execute(text('UPDATE social_source_cursors SET report_state=CAST(:state AS jsonb) WHERE id=:id'),
            {'id':marker.id,'state':json.dumps(state)})
    same,record=ingest(factory,tmp_path,monkeypatch,paye='561')
    result=dispatch(factory,same)
    assert result['drafts_created']==0 and result['state']!='completed',result
    no_publication(factory)


@pytest.mark.parametrize('sentence',[
    b'July PAYE collection stood at Kshs. 560 Billion.',
    b'First quarter PAYE collection stood at Kshs. 560 Billion.',
    b'Prior year PAYE collection stood at Kshs. 560 Billion.',
])
def test_annual_article_does_not_make_explicit_subperiod_or_prior_head_an_annual_fact(pg,tmp_path,monkeypatch,sentence):
    from seeding.source_observations import SourceObservationUnavailable
    factory,_=pg;enable(factory,monkeypatch)
    article=producer_fixture.HTML.replace(b'PAYE collection stood at Kshs. 560 Billion.',sentence)
    with monkeypatch.context() as patch:
        patch.setattr(producer_fixture,'HTML',article)
        job,record=producer_fixture.ingest_revenue(factory,tmp_path,patch)
    with pytest.raises(SourceObservationUnavailable):
        read(factory,job,record)
    no_publication(factory)


def test_newly_qualified_head_cannot_bypass_source_chronology(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    article=producer_fixture.HTML.replace(b'<p>PAYE collection stood at Kshs. 560 Billion.</p>',
        b'<p>Corporation Tax collected Kshs. 300 Billion.</p><p>Domestic VAT collected Kshs. 320 Billion.</p>'
        b'<p>Domestic Excise collection stood at Kshs. 70 Billion.</p><p>Customs collection stood at Kshs. 800 Billion.</p>'
        b'<p>PAYE revenue stood at Kshs. 560 Billion.</p>').replace(b'</div>\n<div',b'</div><div')
    with monkeypatch.context() as patch:
        patch.setattr(producer_fixture,'HTML',article)
        job,_=producer_fixture.ingest_revenue(factory,tmp_path,patch)
    first=dispatch(factory,job)
    assert first['baselines']==4 and first['refused']==1,first
    older,record=ingest(factory,tmp_path,monkeypatch,year=2023,paye='561')
    result=preview(factory,producer_fixture.request(older,record))
    assert result['results'][0]['status']=='refused',result
    result=dispatch(factory,older)
    assert result['drafts_created']==0,result
    no_publication(factory)


@pytest.mark.parametrize('sentence',[
    b'PAYE collection is projected at Kshs. 560 Billion.',
    b'PAYE collection is forecast at Kshs. 560 Billion.',
    b'PAYE collection is estimated at Kshs. 560 Billion.',
])
def test_forward_looking_head_is_not_actual_collections(pg,tmp_path,monkeypatch,sentence):
    from seeding.source_observations import SourceObservationUnavailable
    factory,_=pg;enable(factory,monkeypatch)
    article=producer_fixture.HTML.replace(b'PAYE collection stood at Kshs. 560 Billion.',sentence)
    with monkeypatch.context() as patch:
        patch.setattr(producer_fixture,'HTML',article)
        job,record=producer_fixture.ingest_revenue(factory,tmp_path,patch)
    with pytest.raises(SourceObservationUnavailable):
        read(factory,job,record)
    no_publication(factory)


def test_unchanged_values_advance_source_chronology_before_new_head(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    article=producer_fixture.HTML.replace(b'<p>PAYE collection stood at Kshs. 560 Billion.</p>',
        b'<p>Corporation Tax collected Kshs. 300 Billion.</p><p>Domestic VAT collected Kshs. 320 Billion.</p>'
        b'<p>Domestic Excise collection stood at Kshs. 70 Billion.</p><p>Customs collection stood at Kshs. 800 Billion.</p>'
        b'<p>PAYE revenue stood at Kshs. 560 Billion.</p>').replace(b'</div>\n<div',b'</div><div')
    with monkeypatch.context() as patch:
        patch.setattr(producer_fixture,'HTML',article)
        job,_=ingest(factory,tmp_path,patch)
        assert dispatch(factory,job)['baselines']==4
        same,_=ingest(factory,tmp_path,patch,published='11/07/2025')
        result=dispatch(factory,same)
        assert result['unchanged']==4 and result['drafts_created']==0,result
    later,record=ingest(factory,tmp_path,monkeypatch,published='10/07/2025')
    result=preview(factory,producer_fixture.request(later,record))
    assert result['results'][0]['status']=='refused',result
    result=dispatch(factory,later)
    assert result['drafts_created']==0,result
    no_publication(factory)


@pytest.mark.parametrize('style',['display:none','visibility:hidden'])
def test_hidden_collection_paragraph_is_not_published_financial_authority(pg,tmp_path,monkeypatch,style):
    from seeding.source_observations import SourceObservationUnavailable
    factory,_=pg;enable(factory,monkeypatch)
    article=producer_fixture.HTML.replace(b'<p>PAYE collection',
        f'<p style="{style}">PAYE collection'.encode())
    with monkeypatch.context() as patch:
        patch.setattr(producer_fixture,'HTML',article)
        job,record=producer_fixture.ingest_revenue(factory,tmp_path,patch)
    with pytest.raises(SourceObservationUnavailable):
        read(factory,job,record)
    no_publication(factory)


@pytest.mark.parametrize('paragraph',[
    b'<h2>First quarter performance</h2><p>PAYE collection stood at Kshs. 560 Billion.</p>',
    b'<p style="display:none">PAYE collection stood at Kshs. 560 Billion.</p>',
    b'<p style="visibility:hidden">PAYE collection stood at Kshs. 560 Billion.</p>',
    b'<p>PAYE collection stood at Kshs. 5,60 Billion.</p>',
    b'<p>PAYE collection stood at Kshs. ,560 Billion.</p>',
    b'<p>PAYE collection stood at Kshs. 560, Billion.</p>',
    b'<p>PAYE collection stood at Kshs. 5,,60 Billion.</p>',
])
def test_unknown_article_context_visibility_and_number_syntax_cannot_grant_financial_authority(pg,tmp_path,monkeypatch,paragraph):
    from seeding.source_observations import SourceObservationUnavailable
    factory,_=pg;enable(factory,monkeypatch)
    article=producer_fixture.HTML.replace(b'<p>PAYE collection stood at Kshs. 560 Billion.</p>',paragraph)
    with monkeypatch.context() as patch:
        patch.setattr(producer_fixture,'HTML',article)
        job,record=producer_fixture.ingest_revenue(factory,tmp_path,patch)
    with pytest.raises(SourceObservationUnavailable):read(factory,job,record)

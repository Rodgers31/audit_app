"""Owned current-source drafts keep copy versions and human approval boundaries."""
from uuid import uuid4

import pytest
from sqlalchemy import select

from social.contracts import ApproveCommand
from social.models import SocialPost, SocialPostRevision
from social.service import SocialService, SocialError
from social.generation.models import GenerationControls
from social.generation.contracts import SourceObservation, RuleCommand, EvaluateCommand
from social.generation.service import GenerationService, render, render_for_revision, verify_generated_revision
from seeding.generation_dispatch import dispatch_committed_generation
from test_b83_generation_postgres import pg, no_publication
from native_worker_fixture import restricted
from test_native_financial_changes_postgres import enable, ingest_revenue


def test_real_pending_writer_creates_a_county_and_date_specific_destination(restricted,tmp_path,monkeypatch):
    from test_automatic_cohort_timeout_postgres import ingest_cohort, enabled
    from models import Entity
    factory,_,_,_=restricted
    enabled(factory,monkeypatch)
    first=ingest_cohort(factory,tmp_path)
    result=dispatch_committed_generation(factory,domain='pending_bills',ingestion_id=first,dry_run=False,include_reports=False)
    assert result['baselines']==46 and result['drafts_created']==0,result
    newer=ingest_cohort(factory,tmp_path,correction='Nairobi',retained=True)
    result=dispatch_committed_generation(factory,domain='pending_bills',ingestion_id=newer,dry_run=False,include_reports=False)
    assert result['drafts_created']==1,result
    with factory() as db:
        post=db.scalar(select(SocialPost));revision=db.get(SocialPostRevision,post.current_revision_id)
        entity=db.scalar(select(Entity).where(Entity.canonical_name=='Nairobi County'))
        assert revision.document['master']['link']==f'https://www.auditgava.com/counties/{entity.slug}?tab=budget&as_at=2026-06-30#pending-bills'
        assert 'KSh 12 million in reported pending bills' in revision.document['master']['text']
        assert revision.evidence_snapshot['source']['facts'][0]['value']=='12000000.00'
        assert revision.evidence_snapshot['source']['facts'][0]['canonical_url']=='https://www.auditgava.com/debt'
        verify_generated_revision(db,post,revision)
    no_publication(factory)


def prepare(factory,tmp_path,monkeypatch,*,legacy=False):
    import social.generation.service as generation
    enable(factory,monkeypatch)
    first,_=ingest_revenue(factory,tmp_path,monkeypatch)
    assert dispatch_committed_generation(factory,domain='revenue_by_source',ingestion_id=first,
        dry_run=False,include_reports=False)['drafts_created']==0
    newer,_=ingest_revenue(factory,tmp_path,monkeypatch,paye='561')
    with monkeypatch.context() as patch:
        if legacy:
            original_render,original_metadata=generation.render,generation.generator_metadata
            patch.setattr(generation,'generator_metadata',lambda source,**kw:original_metadata(source,template_version='factual-v1'))
            patch.setattr(generation,'render',lambda source,**kw:original_render(source,template_version='factual-v1'))
        result=dispatch_committed_generation(factory,domain='revenue_by_source',ingestion_id=newer,
            dry_run=False,include_reports=False)
    assert result['drafts_created']==1,result
    with factory() as db:return db.scalar(select(SocialPost.id))


def test_current_financial_draft_has_current_witness_and_still_requires_human_review(restricted,tmp_path,monkeypatch):
    from social.automation.service import candidate_gates
    factory,_,_,_=restricted
    post_id=prepare(factory,tmp_path,monkeypatch)
    with factory.begin() as db:
        post=db.get(SocialPost,post_id);revision=db.get(SocialPostRevision,post.current_revision_id)
        source=SourceObservation.model_validate(revision.evidence_snapshot['source'])
        assert revision.generator_metadata['template_version']=='financial-v4'
        assert revision.document['master']['text']==render(source)
        assert 'KSh 561 billion reported for PAYE.' in revision.document['master']['text']
        verify_generated_revision(db,post,revision)  # Alive current-source control.
        body=ApproveCommand(expected_version=post.row_version,revision_id=revision.id)
        with pytest.raises(SocialError,match='REVIEW_ATTESTATION_REQUIRED'):
            SocialService(db).approve(post.id,body)
        with pytest.raises(SocialError,match='HUMAN_REVIEW_REQUIRED'):
            candidate_gates(SocialService(db),post,revision,None,None,SocialService(db).now())
    no_publication(factory)


def test_historical_v1_financial_revision_keeps_its_text_and_shadow_interpretation(restricted,tmp_path,monkeypatch):
    factory,_,_,_=restricted
    post_id=prepare(factory,tmp_path,monkeypatch,legacy=True)
    with factory.begin() as db:
        post=db.get(SocialPost,post_id);revision=db.get(SocialPostRevision,post.current_revision_id)
        source=SourceObservation.model_validate(revision.evidence_snapshot['source'])
        before=revision.document['master']['text']
        assert revision.generator_metadata['template_version']=='factual-v1'
        assert before==render_for_revision(source,revision.generator_metadata) and before!=render(source)
        verify_generated_revision(db,post,revision)
        db.get(GenerationControls,1).shadow_enabled=True
        service=SocialService(db);service.actor=uuid4();service.request_id=uuid4()
        svc=GenerationService(service);rule_id=uuid4()
        rule=svc.save_rule(rule_id,RuleCommand(expected_version=0,name='Owned versioned shadow',mode='shadow',
            categories=['dataset_availability'],source_allowlist=['kra'],account_allowlist=[uuid4()],
            reason='Owned legacy-copy advisory control'))
        result=svc.evaluate(post.id,EvaluateCommand(expected_version=post.row_version,revision_id=revision.id,
            rule_id=rule_id,rule_version=rule['version']))
        assert result['outcome']=='human_review'
        assert 'GENERATED_COPY_EDITED' not in result['reasons']
        assert revision.document['master']['text']==before
    no_publication(factory)


def national_ingestion(factory,tmp_path,*,actual='1200000000.00'):
    from datetime import date, datetime, timezone
    from decimal import Decimal
    from unittest.mock import patch
    from models import IngestionJob, IngestionStatus
    from seeding.config import SeedingSettings
    from seeding.types import DomainRunContext
    from seeding.domains.national_budget.parser import NationalBudgetRecord
    from seeding.domains.national_budget.writer import persist_national_budget_records
    from seeding.native_report_authority import capture_pdf_report
    from seeding.parse_cache import parse_with_cache
    from seeding.pdf_evidence import bind_parse_receipt, cell_evidence, seal_pdf_observations
    from services.response_receipts import capture_response
    from test_native_publisher_metadata import inputs
    with factory.begin() as db:
        job=IngestionJob(domain='national_budget',status=IngestionStatus.RUNNING,dry_run=False,
            started_at=datetime.now(timezone.utc),errors=[],meta={'source_mode':'live'})
        db.add(job);db.flush();job_id=job.id
        def capture(response,store):
            return capture_response(response,store,source_kind='pdf' if response.headers.get('content-type')=='application/pdf' else 'api')
        with patch('test_native_publisher_metadata.capture_response',capture):path,pdf,publisher=inputs(tmp_path,'national_budget')
        authority,reason=capture_pdf_report(path,pdf,domain='national_budget',publisher_receipt=publisher)
        assert authority is not None,reason
        parsed=parse_with_cache(path,cache_dir=tmp_path/'parse',kind='owned-national-financial',
            parse_fn=lambda:[{'sector':'Health','revised':'1500','actual':actual}],enabled=False)
        receipt=bind_parse_receipt(pdf,parsed)
        cells=[]
        for measure,value in [('allocated_amount',Decimal('1500000000.00')),('actual_spent',Decimal(actual))]:
            cells.append(cell_evidence(receipt=receipt,identity=dict(measure=measure,entity_id=None,
                geography='KEN',period='FY2025/26',unit='KES',basis='actual',
                dimensions={'category':'Health','subcategory':None,'line_type':None}),
                raw_value=str(value/Decimal(1000000)),value=str(value),raw_unit='KES million',factor='1000000',
                locator={'page':1,'table':'Owned national financial cells','cell':f'Health / {measure}'}))
        seal_pdf_observations(cells)
        record=NationalBudgetRecord(entity_slug='kenya',entity_name='Kenya',period_label='FY2025/26',
            start_date=date(2025,7,1),end_date=date(2026,6,30),category='Health',subcategory=None,
            allocated_amount=Decimal('1500000000.00'),actual_spent=Decimal(actual),committed_amount=None,
            currency='KES',source='CoB NG-BIRR',source_url=authority.value['document_url'],data_quality='official',notes=None,
            provenance_extra={'measure':'expenditure','source_evidence':cells,'_native_report_authority':authority})
        stats=persist_national_budget_records(db,[record],SeedingSettings(),DomainRunContext(None,False,job_id))
        assert not stats.errors,stats.errors
        job.status=IngestionStatus.COMPLETED;job.finished_at=datetime.now(timezone.utc)
    return job_id


def test_real_national_writer_qualified_two_measure_change_links_original_report(pg,tmp_path,monkeypatch):
    factory,_=pg;enable(factory,monkeypatch)
    first=national_ingestion(factory,tmp_path)
    result=dispatch_committed_generation(factory,domain='national_budget',ingestion_id=first,dry_run=False,include_reports=False)
    assert result['baselines']==1 and result['drafts_created']==0,result
    newer=national_ingestion(factory,tmp_path,actual='1250000000.00')
    result=dispatch_committed_generation(factory,domain='national_budget',ingestion_id=newer,dry_run=False,include_reports=False)
    assert result['drafts_created']==1,result
    with factory() as db:
        post=db.scalar(select(SocialPost));revision=db.get(SocialPostRevision,post.current_revision_id)
        assert post.editorial_state=='pending_review' and revision.generator_metadata['template_version']=='financial-v4'
        assert revision.document['master']['link']==revision.evidence_snapshot['source']['facts'][0]['document_url']
        assert revision.document['master']['text'].endswith('Read the original source on the publisher’s website.')
        assert len(revision.evidence_snapshot['source']['facts'])==2
        assert 'about KSh 1.3 billion in actual expenditure for Health' in revision.document['master']['text']
        assert 'revised gross budget for the same sector and reporting year was KSh 1.5 billion' in revision.document['master']['text']
    no_publication(factory)

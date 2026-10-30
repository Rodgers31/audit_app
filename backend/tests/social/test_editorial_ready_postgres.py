"""Owned current-source writers -> prepared drafts -> public source-only HTTP."""
from urllib.parse import urlsplit, parse_qs
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, event

from test_b83_generation_postgres import pg, no_publication
from native_worker_fixture import restricted
from test_native_financial_changes_postgres import enable, ingest_revenue
from test_domain_support import account, call
from social.models import SocialPost, SocialPostRevision, SocialControls
from social.generation.models import GenerationControls
from social.generation.contracts import SourceObservation
from social.generation.service import consume_observation, verify_generated_revision
from seeding.generation_dispatch import dispatch_committed_generation
from routers.public_reports import router, get_db
from services.public_report_view import report_view_url


def public_client(factory):
    app=FastAPI();app.include_router(router)
    def session():
        with factory() as db:yield db
    app.dependency_overrides[get_db]=session
    return TestClient(app)


def get_view(client,url):
    parsed=urlsplit(url)
    return client.get('/api/v1'+parsed.path,params={k:v[0] for k,v in parse_qs(parsed.query).items()})


def configure_accounts(factory):
    with factory() as db:
        accounts=[account(db,p) for p in ('facebook','instagram','threads','x','tiktok')]
        for item in accounts:item.publishing_enabled=False
        controls=db.get(GenerationControls,1)
        controls.targets=[dict(account_id=str(item.id),format='text',overrides={}) for item in accounts]
        db.commit()


def test_actual_revenue_post_has_contextual_per_account_tags_and_stable_public_view(restricted,tmp_path,monkeypatch):
    factory,engine,_,_=restricted;enable(factory,monkeypatch);configure_accounts(factory)
    first,_=ingest_revenue(factory,tmp_path,monkeypatch)
    assert dispatch_committed_generation(factory,domain='revenue_by_source',ingestion_id=first,dry_run=False,include_reports=False)['baselines']>0
    newer,_=ingest_revenue(factory,tmp_path,monkeypatch,paye='561')
    result=dispatch_committed_generation(factory,domain='revenue_by_source',ingestion_id=newer,dry_run=False,include_reports=False)
    assert result['drafts_created']==1,result
    with factory() as db:
        post=db.scalar(select(SocialPost));revision=db.get(SocialPostRevision,post.current_revision_id)
        source=SourceObservation.model_validate(revision.evidence_snapshot['source'])
        assert post.editorial_state=='pending_review' and revision.generator_metadata['template_version']=='financial-v5'
        assert revision.document['master']['hashtags']==['#PAYE','#Kenya','#AuditGava']
        profiles=revision.generator_metadata['editorial_profiles'];assert len(profiles)==5
        by_platform={p['platform']:next(t for t in revision.document['targets'] if t['account_id']==p['target']['account_id']) for p in profiles}
        assert by_platform['instagram']['format']=='image' and by_platform['tiktok']['format']=='video'
        assert by_platform['facebook']['overrides']['hashtags']['value']==['#PAYE','#Kenya']
        assert by_platform['threads']['overrides']['hashtags']['value']==['#PAYE']
        verify_generated_revision(db,post,revision)
        url=revision.document['master']['link']
        controls=db.get(SocialControls,1)
        assert controls is None or controls.publishing_enabled is False
    client=public_client(factory);statements=[]
    def trace(_conn,_cursor,sql,*_args):statements.append(sql)
    event.listen(engine,'before_cursor_execute',trace)
    try:response=get_view(client,url)
    finally:event.remove(engine,'before_cursor_execute',trace)
    assert response.status_code==200,response.text
    body=response.json();assert body['figures'][0]['value']=='561.00' and body['period']=='FY 2024/25'
    assert body['sources'][0]['url']==source.facts[0].document_url
    assert response.headers['cache-control']=='no-store'
    assert any('REPEATABLE READ READ ONLY' in sql for sql in statements)
    assert not any(any(table in sql.lower() for table in ('social_posts','social_source_events','social_accounts','social_post_revisions')) for sql in statements)
    assert not any(sql.lstrip().upper().startswith(('INSERT','UPDATE','DELETE','CREATE','ALTER')) for sql in statements)
    assert not any(key in str(body) for key in ('editorial_state','generator_metadata','ingestion_id','worker_authority','account_id'))
    ingest_revenue(factory,tmp_path,monkeypatch,paye='561')
    assert get_view(client,url).status_code==200
    ingest_revenue(factory,tmp_path,monkeypatch,paye='562')
    assert get_view(client,url).status_code==410
    no_publication(factory)


def test_actual_national_report_and_figures_have_exact_on_site_readers(restricted,tmp_path,monkeypatch):
    from test_financial_copy_postgres import national_ingestion
    from seeding.source_observations import read_native_report_record_ids,read_national_report_observation,read_native_financial_record_ids,read_national_financial_observation
    factory,_,_,_=restricted;enable(factory,monkeypatch);job=national_ingestion(factory,tmp_path)
    report_id=read_native_report_record_ids(factory,ingestion_id=job,domain='national_budget')[0]
    fact_id=read_native_financial_record_ids(factory,ingestion_id=job,domain='national_budget')[0]
    client=public_client(factory)
    for reader,record,kind in ((read_national_report_observation,report_id,'report'),(read_national_financial_observation,fact_id,'financial')):
        source=SourceObservation.model_validate(reader(factory,record_id=record,ingestion_id=job))
        with factory() as db:
            created=call(db,source,lambda svc:consume_observation(svc,source,backfill=True))[1]
            post=db.get(SocialPost,UUID(created['post_id']));revision=db.get(SocialPostRevision,post.current_revision_id)
            url=revision.document['master']['link'];verify_generated_revision(db,post,revision)
        response=get_view(client,url);assert response.status_code==200,response.text
        data=response.json();assert data['view']==kind and data['period']=='FY 2025/26'
        assert data['period_start']=='2025-07-01' and data['period_end']=='2026-06-30'
        if kind=='financial':assert {f['value'] for f in data['figures']}=={'1500000000.00','1200000000.00'}
        bad=url.replace('snapshot=','snapshot=0')
        assert get_view(client,bad).status_code==422
    no_publication(factory)


def test_existing_current_generated_draft_can_be_prepared_without_rewriting_history(restricted,tmp_path,monkeypatch):
    from test_financial_copy_postgres import prepare
    from social.generation.service import GenerationService
    from social.generation.contracts import PrepareDraftCommand
    from copy import deepcopy
    factory,_,_,_=restricted
    post_id=prepare(factory,tmp_path,monkeypatch,legacy=True)
    with factory() as db:
        old_post=db.get(SocialPost,post_id);old_id=old_post.current_revision_id
        old_revision=db.get(SocialPostRevision,old_id);before=deepcopy(old_revision.document)
        body=PrepareDraftCommand(expected_version=old_post.row_version,revision_id=old_id,reason='Owner explicitly refreshes this current source draft')
        result=call(db,body,lambda svc:GenerationService(svc).prepare(post_id,body))[1]
        assert result['editorial_state']=='draft' and result['revision_id']!=str(old_id)
        current=db.get(SocialPostRevision,UUID(result['revision_id']))
        assert current.generator_metadata['template_version']=='financial-v5'
        assert current.document['master']['hashtags']==['#PAYE','#Kenya','#AuditGava']
        assert '/reports/revenue_by_source/' in current.document['master']['link']
        assert db.get(SocialPostRevision,old_id).document==before
        assert current.evidence_snapshot['source']==old_revision.evidence_snapshot['source']
        verify_generated_revision(db,db.get(SocialPost,post_id),current)
    no_publication(factory)



def assert_prepared_view(factory,source,client):
    with factory() as db:
        created=call(db,source,lambda svc:consume_observation(svc,source,backfill=True))[1]
        post=db.get(SocialPost,UUID(created['post_id']));revision=db.get(SocialPostRevision,post.current_revision_id)
        verify_generated_revision(db,post,revision)
        assert revision.document['master']['hashtags']
        url=revision.document['master']['link']
    response=get_view(client,url);assert response.status_code==200,response.text
    data=response.json();first=source.report or source.facts[0]
    assert data['entity']==first.entity and data['period']==first.period
    assert data['publisher']==first.publisher and data['sources'][0]['url']==first.document_url
    return url,data


def test_county_report_and_figures_link_exact_entity_rows_and_preserve_reacquisition(restricted,tmp_path,monkeypatch):
    from test_report_postgres import ingest
    from seeding.source_observations import read_county_budget_record_ids,read_county_budget_observation,read_county_report_observation
    factory,_,_,_=restricted;enable(factory,monkeypatch)
    job=ingest(factory,tmp_path,year=2025,published='2026-07-01',amount='0')
    records=read_county_budget_record_ids(factory,ingestion_id=job)
    client=public_client(factory);views=[];entities=set()
    for record in records:
        for reader in (read_county_budget_observation,read_county_report_observation):
            source=SourceObservation.model_validate(reader(factory,record_id=record,ingestion_id=job))
            url,data=assert_prepared_view(factory,source,client);views.append(url);entities.add(data['entity'])
            assert '/reports/counties_budget/' in url
            if not source.report:assert data['figures'][0]['value']==source.facts[0].value
            parsed=urlsplit(url);params={k:v[0] for k,v in parse_qs(parsed.query).items()}
            if source.report:
                params['entity']='2147483647'
                assert client.get('/api/v1'+parsed.path,params=params).status_code==410
    assert len(entities)==3 and {'Mombasa County','Kisumu County'}<=entities
    ingest(factory,tmp_path,year=2025,published='2026-07-01',amount='0')
    for url in views:assert get_view(client,url).status_code==200
    no_publication(factory)


def test_pending_bills_and_audit_reports_link_to_exact_on_site_source_views(restricted,tmp_path,monkeypatch):
    from test_native_publisher_postgres import ingest as pending
    from test_b86_native_postgres import ingest as audit
    from seeding.source_observations import read_pending_bills_report_observation,read_audit_report_observation
    factory,_,_,_=restricted;enable(factory,monkeypatch);client=public_client(factory)
    job,record=pending(factory,tmp_path)
    source=SourceObservation.model_validate(read_pending_bills_report_observation(factory,record_id=record,ingestion_id=job))
    url,data=assert_prepared_view(factory,source,client)
    assert '/reports/pending_bills/' in url and '#PendingBills' in __import__('social.generation.editorial',fromlist=['hashtags']).hashtags(source)
    job,record=audit(factory,tmp_path,domain='audits',url='https://www.oagkenya.go.ke/native-audit.pdf',published='2025-07-10')
    source=SourceObservation.model_validate(read_audit_report_observation(factory,record_id=record,ingestion_id=job))
    url,data=assert_prepared_view(factory,source,client)
    assert '/reports/audits/' in url and data['figures']==[]
    no_publication(factory)


def test_catalogue_view_keeps_unknown_publication_and_withdrawal_never_selects_another_report(restricted,tmp_path,monkeypatch):
    from test_kra_catalogue_postgres import ingest
    from seeding.source_observations import read_revenue_report_observation
    factory,_,_,_=restricted;enable(factory,monkeypatch)
    job,record=ingest(factory,tmp_path)
    source=SourceObservation.model_validate(read_revenue_report_observation(factory,record_id=record,ingestion_id=job))
    client=public_client(factory);url,data=assert_prepared_view(factory,source,client)
    assert data['availability']=='catalogued' and data['published_on'] is None and data['catalogued_on']=='2026-07-08'
    ingest(factory,tmp_path,invalid=True)
    assert get_view(client,url).status_code==410
    no_publication(factory)



def test_prepare_http_returns_detail_and_same_key_replays_the_committed_revision(restricted,tmp_path,monkeypatch):
    from test_financial_copy_postgres import prepare
    from test_api_admin import make_client,key
    factory,engine,_,_=restricted;post_id=prepare(factory,tmp_path,monkeypatch,legacy=True)
    with factory() as db:
        before=db.get(SocialPost,post_id);old_revision=before.current_revision_id
        body=dict(expected_version=before.row_version,revision_id=str(old_revision),reason='Owner reviews refreshed copy and tags')
    client=make_client(engine);headers=key();path='/api/v1/admin/social/posts/'+str(post_id)+'/prepare'
    response=client.post(path,json=body,headers=headers)
    assert response.status_code==200,response.text
    data=response.json();assert data['revision_id']!=str(old_revision) and data['version']==body['expected_version']+1
    assert data['document']['master']['hashtags']==['#PAYE','#Kenya','#AuditGava']
    assert client.post(path,json=body,headers=headers).json()==data
    assert client.post(path,json=body,headers=key()).status_code==409
    no_publication(factory)

from datetime import datetime,timedelta,timezone
from uuid import uuid4
from types import SimpleNamespace
import json,httpx,pytest
from sqlalchemy import select
from models import Country,SourceDocument,DocumentStatus,DocumentType,RevenueBySource,IngestionJob,IngestionStatus
from services.receipt_store import LocalReceiptStore
from services.response_receipts import receipt_is_sealed
from seeding.domains.revenue_by_source.fetcher import _read_release
from seeding.types import DomainRunContext
from test_b86_native_authority import HTML,KRA_URL
from test_b83_generation_postgres import pg
from native_worker_fixture import restricted

def test_qualifying_press_comprehension_does_not_raise_nameerror_and_retains_cells(tmp_path):
 class Client:
  receipt_store=LocalReceiptStore(tmp_path/'receipts')
  def get(self,url,**kw):return httpx.Response(200,content=HTML,headers={'content-type':'text/html'},request=httpx.Request('GET',url))
 release=_read_release(Client(),KRA_URL,None)
 assert release is not None and release.heads['PAYE'].raw_amount is not None
 assert release.response_receipt and receipt_is_sealed(release.response_receipt)
 assert release.response_receipt['observations'][0]['raw_value']=='560000000000'

@pytest.mark.parametrize('reason',['missing','quarantined','changed'])
def test_committed_reader_valueerror_maps_to_review_required(monkeypatch,reason):
 import seeding.native_financial_observations as readers
 from seeding.source_observations import SourceObservationUnavailable
 from social.generation.authority import verify_financial_authority
 from social.service import SocialError
 def fail(*a,**kw):raise SourceObservationUnavailable(reason)
 monkeypatch.setattr(readers,'current_native_financial',fail)
 with pytest.raises(SocialError,match='SOURCE_REVIEW_REQUIRED'):
  verify_financial_authority(None,{'financial':{'record_id':1,'native_domain':'revenue_by_source'},'ingestion_id':'1'})

@pytest.mark.parametrize("eligible", [True, False])
def test_non_native_worldbank_row_eligibility_is_not_changed_by_native_gate(pg,monkeypatch,eligible):
 from seeding.native_financial_gate import qualify_native_financial_rows
 factory,engine=pg;monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED','true')
 with factory.begin()as db:
  country=db.scalar(select(Country).where(Country.iso_code=='KEN'))
  job=IngestionJob(domain='revenue_by_source',status=IngestionStatus.RUNNING,dry_run=False,started_at=datetime.now(timezone.utc),errors=[],meta={'source_mode':'live'});db.add(job);db.flush()
  source=SourceDocument(country_id=country.id,publisher='World Bank',title='World Bank non-native series',url='https://api.worldbank.org/example',status=DocumentStatus.AVAILABLE,doc_type=DocumentType.REPORT,fetch_date=datetime.now(timezone.utc),meta={});db.add(source);db.flush()
  row=RevenueBySource(fiscal_year='FY2025/26',revenue_type='World Bank headline',category='tax',amount_billion_kes=1,source_document_id=source.id,publishable=eligible,quarantine_reason=None,meta={'ingestion_job_id':job.id,'source_evidence':[{'unsupported':'foreign cell'}]});db.add(row);db.flush()
  qualify_native_financial_rows(db,[row],domain='revenue_by_source',context=DomainRunContext(None,False,job.id))
  assert row.publishable is eligible and row.quarantine_reason is None,'Native KRA gate altered unrelated World Bank numeric eligibility'

def test_qualification_policy_requires_new_native_financial_flag_off(monkeypatch):
 import admin_etl_qualification as q
 now=datetime.now(timezone.utc);generation=str(uuid4())
 raw=dict(version=1,generation=generation,issued_at=now.isoformat().replace('+00:00','Z'),expires_at=(now+timedelta(seconds=3600)).isoformat().replace('+00:00','Z'))
 monkeypatch.setenv(q.POLICY_ENV,json.dumps(raw))
 for key in q.DISABLED_FLAGS:monkeypatch.setenv(key,'false')
 for key,value in {'ADMIN_ETL_DISPATCH_SOURCES':'opendata','SEED_OPENDATA_INGESTION_ENABLED':'true','AUTO_SEEDER_ENABLED':'false','SEED_KNBS_RELEASE_DISCOVERY_ENABLED':'false','SOCIAL_GENERATION_HOOK_ENABLED':'false','SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED':'true'}.items():monkeypatch.setenv(key,value)
 with pytest.raises(q.QualificationRefused):q.qualification(now)


from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from threading import Event
from uuid import UUID
from pathlib import Path
import json,time
import pytest
from sqlalchemy import select,text
from models import RevenueBySource
from social.models import SocialAccount,SocialControls,SocialPost,SocialPostRevision,SocialPublication
from social.generation.models import GenerationControls,SourceCursor
from social.generation.service import consume_observation,verify_generated_revision
from social.service import SocialService,SocialError
from social.contracts import ApproveCommand
from test_b83_generation_postgres import pg
from test_native_financial_changes_postgres import enable,ingest_revenue,read
from test_domain_support import account,call
from test_policy_hook_registry import validation_environment
from test_report_postgres import repository_gate


def test_actual_human_approved_financial_worker_gate_refuses_changed_source(restricted,tmp_path,monkeypatch):
 factory,engine,_,_=restricted;enable(factory,monkeypatch);validation_environment(monkeypatch)
 from social.adapters.validation_registry import load_native_validation_registry
 registry=load_native_validation_registry();adapter=registry.adapters[('facebook','facebook_pages')]
 with factory() as db:
  a=account(db);a.api_product=adapter.product;a.external_account_id='123456';a.granted_scopes=list(adapter.scopes)
  a.capability_snapshot=adapter.capabilities(dict(platform=a.platform,api_product=a.api_product,external_account_id=a.external_account_id,connection_state=a.connection_state,granted_scopes=a.granted_scopes,capability_snapshot=a.capability_snapshot)).model_dump(mode='json')
  a.capabilities_checked_at=datetime.now(timezone.utc)-timedelta(seconds=5)
  cfg=db.get(GenerationControls,1);cfg.targets=[dict(account_id=str(a.id),format='text')];account_id=a.id;db.commit()
 job,record=ingest_revenue(factory,tmp_path,monkeypatch);value=read(factory,job,record)
 with factory.begin() as db:created=consume_observation(SocialService(db),value,backfill=True)
 post_id=UUID(created['post_id'])
 with factory() as db:
  post=db.get(SocialPost,post_id);revision_id=post.current_revision_id
  body=ApproveCommand(expected_version=post.row_version,revision_id=revision_id,review_attestation={'facts_checked':True,'sources_checked':True})
  call(db,body,lambda svc:svc.approve(post_id,body),adapters=registry.adapters)
  publication=db.scalar(select(SocialPublication).where(SocialPublication.post_id==post_id));pub_id=publication.id
  db.get(SocialControls,1).publishing_enabled=True;db.commit() # synthetic owned fixture only, never a live account
 with factory() as db:before=repository_gate(db,engine,pub_id,account_id)
 with factory.begin() as db:db.get(RevenueBySource,record).amount_billion_kes+=1
 with factory.begin() as db:
  with pytest.raises(SocialError,match='SOURCE_REVIEW_REQUIRED'):
   verify_generated_revision(db,db.get(SocialPost,post_id),db.get(SocialPostRevision,revision_id))
 with factory() as db:after=repository_gate(db,engine,pub_id,account_id)
 Path('/output/worker-gate.json').write_text(json.dumps({'before':before,'after_changed_business_value':after,'source_record':record,'synthetic_fixture_only':True},indent=2))
 assert before is None and after == 'SOURCE_REVIEW_REQUIRED', 'An installed current witness admits only unchanged reviewed evidence'

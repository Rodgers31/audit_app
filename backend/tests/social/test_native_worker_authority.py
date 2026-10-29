"""Actual restricted-login delivery authority; provider actions are never sent."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import UUID,uuid4
import json,pytest
from sqlalchemy import create_engine,select,text
from models import BudgetLine,RevenueBySource,SourceDocument
from social.models import SocialControls,SocialPost,SocialPostRevision,SocialPublication
from social.generation.models import GenerationControls
from social.generation.service import consume_observation
from social.generation.authority import verify_report_authority,verify_financial_authority
from social.worker.role_contract import install_worker_role,verify_worker_role,WorkerRoleError
from social.worker.repository import QueueRepository
from social.worker.config import WorkerConfig
from social.contracts import ApproveCommand
from social.service import SocialService,SocialError
from test_b83_generation_postgres import pg
from social.worker.native_authority_schema import install_native_authority
from social.generation.worker_authority import verify_worker_authority
from social.generation.contracts import SourceObservation
from test_domain_support import account,call
from test_policy_hook_registry import validation_environment
from test_b86_native_postgres import enable as enable_reports
from test_native_financial_changes_postgres import enable as enable_financial,ingest_revenue,read as financial_read
from test_report_postgres import ingest as county_ingest
from test_kra_catalogue_postgres import ingest as catalogue_ingest
from seeding.source_observations import read_county_budget_observation,read_county_report_observation,read_revenue_report_observation

@pytest.fixture
def restricted(pg):
 factory,owner=pg;role='b118_worker_'+uuid4().hex
 with factory.begin()as db:db.add(SocialControls(id=1,publishing_enabled=False))
 with owner.begin()as conn:conn.execute(text('CREATE ROLE '+role+" LOGIN PASSWORD 'inert-local-only' NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2"))
 worker=create_engine(owner.url.set(username=role,password='inert-local-only'),pool_size=2,max_overflow=0)
 try:
  install_worker_role(owner,role)
  install_native_authority(owner,role)
  install_native_authority(owner,role) # complete installation is idempotent
  verify_worker_role(worker,role)
  yield factory,owner,worker,role
 finally:
  worker.dispose()
  with owner.begin()as conn:
   conn.execute(text('DROP VIEW IF EXISTS social_native_source_authority,social_native_source_authority_snapshot'))
   conn.execute(text('DROP OWNED BY '+role));conn.execute(text('DROP ROLE '+role))

def capture(fn):
 try:return {'result':fn(),'error_class':None}
 except Exception as exc:return {'result':None,'error_class':type(exc).__name__,'code':getattr(exc,'code',None),'sqlstate':getattr(getattr(exc,'orig',None),'pgcode',None)}



def configure(factory,monkeypatch,*,financial=False):
 (enable_financial if financial else enable_reports)(factory,monkeypatch)
 validation_environment(monkeypatch)
 from social.adapters.validation_registry import load_native_validation_registry
 registry=load_native_validation_registry();adapter=registry.adapters[('facebook','facebook_pages')]
 with factory()as db:
  a=account(db);a.api_product=adapter.product;a.external_account_id='123456';a.granted_scopes=list(adapter.scopes)
  a.capability_snapshot=adapter.capabilities(dict(platform=a.platform,api_product=a.api_product,external_account_id=a.external_account_id,connection_state=a.connection_state,granted_scopes=a.granted_scopes,capability_snapshot=a.capability_snapshot)).model_dump(mode='json')
  a.capabilities_checked_at=datetime.now(timezone.utc)-timedelta(seconds=5)
  db.get(GenerationControls,1).targets=[dict(account_id=str(a.id),format='text')];aid=a.id;db.commit()
 return registry,aid

def queue(factory,registry,value):
 with factory.begin()as db:created=consume_observation(SocialService(db),value,backfill=True)
 post_id=UUID(created['post_id'])
 with factory()as db:
  post=db.get(SocialPost,post_id);body=ApproveCommand(expected_version=post.row_version,revision_id=post.current_revision_id,review_attestation={'facts_checked':True,'sources_checked':True})
  call(db,body,lambda svc:svc.approve(post_id,body),adapters=registry.adapters)
  pub=db.scalar(select(SocialPublication).where(SocialPublication.post_id==post_id));pid=pub.id
  db.get(SocialControls,1).publishing_enabled=True;db.commit()
 return pid

def gate(worker,pub_id,aid):
 with worker.begin()as conn:
  controls=conn.execute(text('SELECT * FROM social_controls WHERE id=1')).mappings().one()
  acc=conn.execute(text('SELECT * FROM social_accounts WHERE id=:id'),{'id':aid}).mappings().one()
  pub=conn.execute(text('SELECT * FROM social_publications WHERE id=:id'),{'id':pub_id}).mappings().one()
  target=conn.execute(text('SELECT * FROM social_post_targets WHERE publication_id=:id'),{'id':pub_id}).mappings().one()
  return QueueRepository(worker,WorkerConfig(database_url=worker.url.render_as_string(hide_password=False)),uuid4())._gate(conn,controls,acc,pub,target,datetime.now(timezone.utc),True)

def test_current_native_catalogue_core_worker_must_not_crash(restricted,tmp_path,monkeypatch):
 factory,owner,worker,role=restricted;registry,aid=configure(factory,monkeypatch)
 job,record=catalogue_ingest(factory,tmp_path)
 value=SourceObservation.model_validate(read_revenue_report_observation(factory,record_id=record,ingestion_id=job)).model_dump(mode='json')
 with factory()as db:assert verify_report_authority(db,value)is None
 pid=queue(factory,registry,value)
 with worker.begin()as conn:port=capture(lambda:verify_report_authority(conn,value))
 admission=capture(lambda:gate(worker,pid,aid))
 assert port.get('code')=='SOURCE_REVIEW_REQUIRED'
 assert admission['error_class']is None,'Current native catalogue worker path raises instead of returning a bounded authority decision'
 assert admission['result']is None,'A legitimate accepted current native report needs the restricted digest witness'

def test_legacy_financial_fact_mutation_must_not_remain_worker_authorized(restricted,tmp_path,monkeypatch):
 factory,owner,worker,role=restricted;registry,aid=configure(factory,monkeypatch)
 job=county_ingest(factory,tmp_path)
 with factory()as db:record=db.scalar(select(BudgetLine.id).order_by(BudgetLine.id))
 value=read_county_budget_observation(factory,record_id=record,ingestion_id=job)
 assert value.get('report')is None and value.get('financial')is None and value['facts']
 pid=queue(factory,registry,value);before=capture(lambda:gate(worker,pid,aid))
 with factory.begin()as db:db.get(BudgetLine,record).actual_spent+=1
 after=capture(lambda:gate(worker,pid,aid))
 assert before['error_class']is None and before['result']is None
 assert after['error_class']is None and after['result']=='SOURCE_REVIEW_REQUIRED','Changed legacy financial facts stayed worker-authorized without a current witness'


def test_native_financial_current_and_changed(restricted,tmp_path,monkeypatch):
 factory,owner,worker,role=restricted;registry,aid=configure(factory,monkeypatch,financial=True)
 job,record=ingest_revenue(factory,tmp_path,monkeypatch);value=financial_read(factory,job,record)
 pid=queue(factory,registry,value)
 assert gate(worker,pid,aid)is None
 with factory.begin()as db:db.get(RevenueBySource,record).amount_billion_kes+=1
 assert gate(worker,pid,aid)=='SOURCE_REVIEW_REQUIRED'
 verify_worker_role(worker,role)


def test_digest_only_worker_port_keeps_business_tables_private(restricted):
 factory,owner,worker,role=restricted
 for relation in ('budget_lines','revenue_by_source','loans','source_documents','extractions','ingestion_jobs','social_report_source_authority_snapshot','social_native_source_authority_snapshot'):
  with pytest.raises(Exception)as exc:
   with worker.begin()as conn:conn.execute(text('SELECT * FROM '+relation+' LIMIT 1'))
  assert exc.value.orig.pgcode=='42501'
 with worker.begin()as conn:
  rows=conn.execute(text('SELECT * FROM social_native_source_authority LIMIT 1'))
  assert list(rows.keys())==['source_kind','native_domain','record_id','ingestion_id','authority_fingerprint']
  assert rows.all()==[]


@pytest.mark.parametrize('changed',['job','country','receipt'])
def test_cached_owner_cannot_mint_changed_source_witness(restricted,tmp_path,monkeypatch,changed):
 from models import IngestionJob,IngestionStatus,Country,Extraction
 from seeding.source_observations import SourceObservationUnavailable
 factory,owner,worker,role=restricted;configure(factory,monkeypatch)
 job,record=catalogue_ingest(factory,tmp_path)
 value=SourceObservation.model_validate(read_revenue_report_observation(factory,record_id=record,ingestion_id=job)).model_dump(mode='json')
 model,pk=(IngestionJob,job) if changed=='job' else (Country,value['report']['entity_id']) if changed=='country' else (Extraction,record)
 with factory()as db:
  held=db.get(model,pk)
  with factory.begin()as other:
   row=other.get(model,pk)
   if changed=='job':row.status=IngestionStatus.FAILED
   elif changed=='country':row.iso_code='UGA'
   else:row.extracted_json={}
  with pytest.raises(SourceObservationUnavailable):read_revenue_report_observation(factory,record_id=record,ingestion_id=job)
  with pytest.raises(SocialError,match='SOURCE_REVIEW_REQUIRED'):
   consume_observation(SocialService(db),value,backfill=True)

def bound_witness(factory,pid):
 with factory()as db:
  pub=db.get(SocialPublication,pid);revision=db.get(SocialPostRevision,pub.revision_id)
  return deepcopy(revision.evidence_snapshot['source']),deepcopy(revision.evidence_snapshot.get('worker_authority'))

@pytest.mark.parametrize('broken',['missing','empty','bool_version','extra','bool_record','bool_ingestion','unknown_kind','unknown_domain','wrong_record','wrong_job','uppercase_hash','short_hash','None_hash','NaN_hash','wrong_hash','source_bool_record','source_unknown','source_bad_job','source_nested_report','foreign_country_kind'])
def test_witness_shapes_reject_cleanly(restricted,tmp_path,monkeypatch,broken):
 factory,owner,worker,role=restricted;registry,aid=configure(factory,monkeypatch)
 job,record=catalogue_ingest(factory,tmp_path);value=SourceObservation.model_validate(read_revenue_report_observation(factory,record_id=record,ingestion_id=job)).model_dump(mode='json')
 pid=queue(factory,registry,value);source,witness=bound_witness(factory,pid)
 assert witness and gate(worker,pid,aid)is None
 if broken=='missing':witness=None
 elif broken=='empty':witness={}
 elif broken=='bool_version':witness['version']=True
 elif broken=='extra':witness['unexpected']=None
 elif broken=='bool_record':witness['record_id']=True
 elif broken=='bool_ingestion':witness['ingestion_id']=True
 elif broken=='unknown_kind':witness['kind']='other'
 elif broken=='unknown_domain':witness['domain']='other'
 elif broken=='wrong_record':witness['record_id']+=1
 elif broken=='wrong_job':witness['ingestion_id']+=1
 elif broken=='uppercase_hash':witness['fingerprint']=witness['fingerprint'].upper()
 elif broken=='short_hash':witness['fingerprint']='a'*63
 elif broken=='None_hash':witness['fingerprint']=None
 elif broken=='NaN_hash':witness['fingerprint']=float('nan')
 elif broken=='wrong_hash':witness['fingerprint']='f'*64
 elif broken=='source_bool_record':source['report']['source_record_id']=True
 elif broken=='source_unknown':source['report']['native_domain']='unknown'
 elif broken=='source_bad_job':source['ingestion_id']='01'
 elif broken=='source_nested_report':source['report']={'native_domain':[]}
 elif broken=='foreign_country_kind':source['financial']={'native_domain':'revenue_by_source','record_id':record}
 with worker.begin()as conn:out=capture(lambda:verify_worker_authority(conn,source,witness))
 assert out.get('code')=='SOURCE_REVIEW_REQUIRED',out

@pytest.mark.parametrize('broken',['source_publisher','source_country','source_state','source_binding','receipt','job_status','job_errors','job_mode','job_finished','newer_job'])
def test_native_catalogue_changed_inputs_refuse(restricted,tmp_path,monkeypatch,broken):
 from models import IngestionJob,IngestionStatus,Extraction,DocumentStatus,Country
 factory,owner,worker,role=restricted;registry,aid=configure(factory,monkeypatch)
 job,record=catalogue_ingest(factory,tmp_path);value=SourceObservation.model_validate(read_revenue_report_observation(factory,record_id=record,ingestion_id=job)).model_dump(mode='json')
 pid=queue(factory,registry,value);assert gate(worker,pid,aid)is None
 with factory.begin()as db:
  source=db.get(SourceDocument,value['report']['source_document_id']);j=db.get(IngestionJob,job)
  if broken=='source_publisher':source.publisher='Foreign publisher'
  elif broken=='source_country':db.get(Country,source.country_id).iso_code='USA'
  elif broken=='source_state':source.status=DocumentStatus.FAILED
  elif broken=='source_binding':source.meta={}
  elif broken=='receipt':db.get(Extraction,record).extracted_json={}
  elif broken=='job_status':j.status=IngestionStatus.RUNNING
  elif broken=='job_errors':j.errors=['unexpected']
  elif broken=='job_mode':j.meta={**j.meta,'source_mode':'fixture'}
  elif broken=='job_finished':j.finished_at=datetime(2099,1,1)
  elif broken=='newer_job':db.add(IngestionJob(domain='revenue_by_source',status=IngestionStatus.COMPLETED_WITH_ERRORS,dry_run=False,started_at=datetime.now(timezone.utc),finished_at=datetime.now(timezone.utc),errors=['later'],meta={'source_mode':'partial'}))
 out=capture(lambda:gate(worker,pid,aid));assert out=={'result':'SOURCE_REVIEW_REQUIRED','error_class':None},out


def test_only_additional_digest_select_and_no_hidden_view_grants(restricted):
 factory,owner,worker,role=restricted
 with worker.begin()as conn:
  cols=conn.execute(text('SELECT * FROM social_native_source_authority LIMIT 1')).keys()
  assert list(cols)==['source_kind','native_domain','record_id','ingestion_id','authority_fingerprint']
 for relation in('budget_lines','revenue_by_source','loans','source_documents','extractions','ingestion_jobs','countries','entities','fiscal_periods','social_report_source_authority_snapshot','social_native_source_authority_snapshot'):
  with pytest.raises(Exception)as exc:
   with worker.begin()as conn:conn.execute(text('SELECT * FROM '+relation+' LIMIT 1'))
  assert exc.value.orig.pgcode=='42501'
 verify_worker_role(worker,role)
 install_native_authority(owner,role);verify_worker_role(worker,role)


def test_unknown_native_digest_definition_rejected(restricted):
 factory,owner,worker,role=restricted
 with owner.begin()as conn:original=conn.scalar(text("SELECT pg_get_viewdef('social_native_source_authority'::regclass,true)"))
 try:
  with owner.begin()as conn:conn.execute(text("CREATE OR REPLACE VIEW social_native_source_authority WITH (security_barrier=true) AS SELECT 'report'::text AS source_kind,'revenue_by_source'::text AS native_domain,1 AS record_id,1 AS ingestion_id,repeat('a',64) AS authority_fingerprint"))
  with pytest.raises(WorkerRoleError):verify_worker_role(worker,role)
  with pytest.raises(WorkerRoleError):install_native_authority(owner,role)
 finally:
  with owner.begin()as conn:conn.execute(text('CREATE OR REPLACE VIEW social_native_source_authority WITH (security_barrier=true) AS '+original))
 verify_worker_role(worker,role)


def test_financial_receipt_change_before_capture_requires_new_review(restricted,tmp_path,monkeypatch):
 from models import Extraction
 from social.generation import worker_authority
 factory,owner,worker,role=restricted;configure(factory,monkeypatch,financial=True)
 job,record=ingest_revenue(factory,tmp_path,monkeypatch);value=financial_read(factory,job,record)
 with factory()as db:
  row=db.get(RevenueBySource,record)
  receipt_id=row.meta['source_evidence'][0]['receipt']['extraction_id']
  held=db.get(Extraction,receipt_id)
  original=worker_authority._fingerprint
  changed=[]
  def between_qualification_and_capture(*args,**kwargs):
   if not changed:
    with factory.begin()as other:
     receipt=other.get(Extraction,receipt_id)
     raw=deepcopy(receipt.extracted_json)
     raw['response_receipt']['byte_check']['sha256']='b'*64
     receipt.extracted_json=raw
    changed.append(True)
   return original(*args,**kwargs)
  monkeypatch.setattr(worker_authority,'_fingerprint',between_qualification_and_capture)
  with pytest.raises(SocialError,match='SOURCE_REVIEW_REQUIRED'):
   consume_observation(SocialService(db),value,backfill=True)
  assert changed

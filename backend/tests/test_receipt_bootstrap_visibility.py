"""New no-run and bootstrap jobs retain explicit, isolated receipt outcomes."""
import pytest
from sqlalchemy import select
from models import IngestionJob,IngestionStatus
from seeding import cli,freshness
from seeding.config import SeedingSettings
from seeding.types import DomainRunResult
from services.receipt_retention import RetentionScope,safe_retention_summary
from services.response_receipts import capture_response
from test_receipt_upload_recovery import source_response
from test_seeding_cli_budget import clock,sessionmaker_factory,_FakeRegistry,_args,_jobs_by_domain

EMPTY=dict(state='not_observed',observed=0,retained=0,missing=0,recovered=0,retry_requests=0)
MISSING=dict(state='missing_bytes',observed=1,retained=0,missing=1,recovered=0,retry_requests=0)

@pytest.mark.parametrize('cause',['budget','ownership','history'])
def test_actual_no_run_paths_explicitly_record_zero_captures(clock,sessionmaker_factory,monkeypatch,cause):
 calls=[]
 def handler(*,context,**kwargs):
  calls.append(context.job_id)
  clock.advance(100)
  return DomainRunResult(domain='a')
 monkeypatch.setattr(cli,'REGISTRY',_FakeRegistry({'a':handler,'b':lambda **kwargs:pytest.fail('Unadmitted handler ran')}))
 args=_args()
 if cause=='ownership':
  from seeding import exclusion
  def refuse(*args,**kwargs):raise exclusion.DomainBusyError('inert retained owner')
  monkeypatch.setattr(exclusion,'enter_domain',refuse)
 if cause=='history':
  from seeding import fair_progress
  def refuse(*args,**kwargs):raise RuntimeError('inert unavailable history')
  monkeypatch.setattr(fair_progress,'admission_order',refuse);args.fair_progress=True
 assert cli.run_seed_command(args,SeedingSettings(total_timeout_seconds=100,domain_timeout_seconds=600))==1
 jobs=_jobs_by_domain(sessionmaker_factory)
 unrun=jobs['b'];assert unrun.status==IngestionStatus.FAILED
 assert unrun.items_processed==unrun.items_created==unrun.items_updated==0
 if cause!='budget':assert not calls
 assert unrun.meta.get('receipt_retention')==EMPTY,'The new job is known not to have entered any handler, rather than historical/unknown'

@pytest.mark.parametrize('capture,raises',[(False,False),(True,False),(True,True)])
def test_actual_bootstrap_budget_caller_accounts_captures(sessionmaker_factory,monkeypatch,capture,raises):
 import bootstrap
 from seeding.registries import REGISTRY,load_builtin_domains
 load_builtin_domains()
 monkeypatch.setattr(bootstrap,'SessionLocal',sessionmaker_factory)
 monkeypatch.setattr(bootstrap,'_seed_national_data',lambda *args,**kwargs:None)
 calls=[]
 def handler(**kwargs):
  calls.append(True)
  if capture:capture_response(source_response(),None)
  if raises:raise RuntimeError('inert handler failed after source capture')
  return DomainRunResult(domain='national_budget',items_processed=1)
 monkeypatch.setitem(REGISTRY._handlers,'national_budget',handler)
 bootstrap.initialize_reference_data(force=True)
 jobs=_jobs_by_domain(sessionmaker_factory)
 assert calls==[True] and set(jobs)=={'national_budget',bootstrap.BOOTSTRAP_DOMAIN}
 budget=jobs['national_budget'];assert budget.status==(IngestionStatus.FAILED if raises else IngestionStatus.COMPLETED)
 reference=jobs[bootstrap.BOOTSTRAP_DOMAIN];assert reference.status==IngestionStatus.COMPLETED
 # These actual new executions can report their own bounded evidence; missing historical summaries remain unknown.
 assert budget.meta.get('receipt_retention')==(MISSING if capture else EMPTY)
 assert reference.meta.get('receipt_retention')==EMPTY,'Nested budget validation must not be attributed to reference-data writes'
 next_job=RetentionScope()
 try:assert next_job.summary()==EMPTY
 finally:next_job.close()

@pytest.mark.parametrize('raises',[False,True])
def test_bootstrap_reference_scope_does_not_lose_or_inherit_budget_captures(sessionmaker_factory,monkeypatch,tmp_path,raises):
 import bootstrap
 from services.receipt_store import LocalReceiptStore
 from seeding.registries import REGISTRY,load_builtin_domains
 load_builtin_domains();calls=[]
 monkeypatch.setattr(bootstrap,'SessionLocal',sessionmaker_factory)
 def reference(*args,**kwargs):
  capture_response(source_response(),None)
  if raises:raise RuntimeError('inert reference capture failure')
 monkeypatch.setattr(bootstrap,'_seed_national_data',reference)
 def budget(**kwargs):
  calls.append(True);capture_response(source_response(),LocalReceiptStore(tmp_path/'receipts'))
  return DomainRunResult(domain='national_budget',items_processed=1)
 monkeypatch.setitem(REGISTRY._handlers,'national_budget',budget)
 if raises:
  with pytest.raises(RuntimeError,match='inert reference capture failure'):bootstrap.initialize_reference_data(force=True)
 else:bootstrap.initialize_reference_data(force=True)
 jobs=_jobs_by_domain(sessionmaker_factory)
 reference_job=jobs[bootstrap.BOOTSTRAP_DOMAIN]
 assert reference_job.status==(IngestionStatus.FAILED if raises else IngestionStatus.COMPLETED)
 assert calls==([] if raises else [True])
 assert reference_job.meta.get('receipt_retention')==MISSING
 if not raises:assert jobs['national_budget'].meta.get('receipt_retention')==dict(state='confirmed',observed=1,retained=1,missing=0,recovered=0,retry_requests=0)
 scope=RetentionScope()
 try:assert scope.summary()==EMPTY
 finally:scope.close()

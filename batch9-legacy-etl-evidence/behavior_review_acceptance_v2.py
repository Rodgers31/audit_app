"""Read back final independent execution receipts and assert scoped expectations."""
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];FOLDER=Path(__file__).resolve().parent
names=['recheck-minimum','recheck-current','recheck-cancellation-minimum','recheck-cancellation-current','recheck-dynamic-binds-minimum','recheck-dynamic-binds-current','recheck-refusal-storage-minimum','recheck-refusal-storage-current']
examined=[]
for name in names:
 path=FOLDER/f'behavior-review-{name}.json';receipt=json.loads(path.read_text())
 assert receipt['start_source_sha256']==receipt['source_sha256'],name
 for source,digest in receipt['source_sha256'].items():assert hashlib.sha256((ROOT/source).read_bytes()).hexdigest()==digest,(name,source)
 assert hashlib.sha256((ROOT/receipt['generated_by']).read_bytes()).hexdigest()==receipt['generator_sha256'],name
 if name in ('recheck-minimum','recheck-current'):
  results={r['control']:r for r in receipt['results']}
  assert results['normal_manual_session']['outcome']==dict(effects=1,active=0,released=13)
  assert not results['closed_session_reuse']['outcome']['returned']
  for transfer in ['cross_task_session_transfer','cross_thread_session_transfer']:
   assert all(not c['outcome']['returned'] and c['outcome']['error']=='DomainOwnershipError' for c in results[transfer]['calls'])
   assert results[transfer]['state']['effects']==0
  assert results['connection_commit_uncertainty']['commit']['error']=='DomainOwnershipError'
  assert results['connection_commit_uncertainty']['before_next']['effects']==0
  for control in ['session_begin_commit_uncertainty','baseexception_interrupt']:
   assert results[control]['final']==dict(effects=1,active=13,released=0)
  assert not results['missing_schema_startup']['outcome']['returned']
  for control in ['direct_pipeline_ownership_refusal','optional_loader_direct_pipeline']:
   assert not results[control]['returned'] and results[control]['error']=='DomainOwnershipError'
  for control in ['full_pipeline_monitor_ownership_refusal','optional_loader_full_pipeline','missing_dispatch_seam_full_pipeline']:
   assert not results[control]['returned'] and results[control]['error']=='DomainOwnershipError' and results[control]['monitor_success'] is False
  for control in ['scheduler_ownership_refusal','optional_loader_scheduler','missing_dispatch_seam_scheduler']:
   assert not results[control]['returned'] and results[control]['error']=='SystemExit'
  assert not results['missing_dispatch_seam_startup']['outcome']['returned']
 elif name.startswith('recheck-cancellation-'):
  for control in receipt['results']:
   assert not control['outcome']['returned'] and not control['next_owner']['returned']
   assert control['state']['active']==13
  assert receipt['results'][0]['state']['effects']==1 and receipt['results'][1]['state']['effects']==0
 elif name.startswith('recheck-refusal-storage-'):
  assert receipt['verdict']=='PASSED'
  for control in receipt['results']:
   assert not control['outcome']['returned'] and control['outcome']['error']=='DomainOwnershipError'
   assert control['outcome']['diagnostic']=='Domain ownership unavailable; reconcile retained execution'
  assert receipt['results'][1]['outcome']['monitor_success'] is False
  assert receipt['state']==dict(countries=0,documents=0,audits=0,retained=1,jobs=0)
 else:
  for control in receipt['results']:
   assert not control['outcome']['returned'] and control['outcome']['error']=='DomainOwnershipError'
   assert control['other_database_effects']==0 and control['other_database_retained']==1 and control['default_database_retained']==0
 examined.append(dict(path=str(path.relative_to(ROOT)),receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),python=receipt['python'],sqlalchemy=receipt['sqlalchemy'],source_sha256=receipt['source_sha256']))
result=dict(generated_by=str(Path(__file__).relative_to(ROOT)),generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),generated_at=datetime.now(timezone.utc).isoformat(),target_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),command=sys.argv,verdict='PASSED',failures=0,skips=0,examined=examined,limitation='Only owned SQLite independent behavioral controls; PostgreSQL process exclusion and deployed state are separate author/coordinator gates.')
output=FOLDER/'behavior-review-recheck-acceptance.json';output.write_text(json.dumps(result,indent=2));readback=json.loads(output.read_text());assert readback['generator_sha256']==result['generator_sha256'];assert readback['verdict']=='PASSED';print('PASSED: eight recheck execution receipts; zero failures/skips; source and generator hashes verified.')

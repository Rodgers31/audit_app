"""Independent refusal-recording storage-failure propagation; owned SQLite."""
import asyncio,hashlib,json,os,platform,socket,subprocess,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
os.environ['PYTHON_DOTENV_DISABLED']='1';os.environ['DATABASE_URL']='sqlite:////tmp/batch9-legacy-behavior-bootstrap.sqlite';os.environ['AWS_BUCKET_NAME']='';os.environ['AWS_ACCESS_KEY_ID']=''
sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
def no_network(*args,**kwargs):raise RuntimeError('External transport forbidden')
socket.socket.connect=no_network
import sqlalchemy
from sqlalchemy import event,text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from models import Base
from etl.database_loader import DatabaseLoader
from etl.kenya_pipeline import KenyaDataPipeline
from etl.monitored_runner import ETLMonitor
from seeding.exclusion import DomainOwnershipError,enter_domain
@compiles(JSONB,'sqlite')
def sqlite_json(*args,**kwargs):return 'TEXT'
sources=['etl/writer_ownership.py','etl/database_loader.py','etl/kenya_pipeline.py','etl/monitored_runner.py']
start={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources}
results=[]
with tempfile.TemporaryDirectory(prefix='batch9-legacy-refusal-review-') as scratch:
 loader=DatabaseLoader(f'sqlite:///{scratch}/owned.sqlite');Base.metadata.create_all(loader.engine)
 owner=enter_domain(sessionmaker(bind=loader.engine),'audits',False);owner.close()
 def observation_failure(conn,cursor,statement,parameters,context,executemany):
  if statement.startswith('INSERT INTO ingestion_jobs'):raise OperationalError('owned refusal observation',{},RuntimeError('owned unavailable recording storage'))
 event.listen(loader.engine,'before_cursor_execute',observation_failure)
 async def direct_loader():
  try:await loader.ensure_country_exists();return dict(returned=True)
  except BaseException as exc:return dict(returned=False,error=type(exc).__name__,diagnostic=str(exc))
 results.append(dict(control='direct_loader_refusal_recording_failure',outcome=asyncio.run(direct_loader())))
 os.environ['DATABASE_URL']=str(loader.engine.url)
 pipe=KenyaDataPipeline(storage_path=str(Path(scratch)/'storage'));pipe.db_loader=loader
 doc=dict(url='https://fixture.invalid/inert.pdf',source_key='oag',title='Owned inert audit',source='Inert fixture',doc_type='audit')
 finding=dict(finding_text='owned inert finding',severity='info',entity=dict(canonical_name='Inert entity',type='agency'))
 pipe.discover_budget_documents=lambda source:[dict(doc)] if source=='oag' else []
 pipe.http.get=lambda *a,**kw:SimpleNamespace(content=b'%PDF-owned-independent-refusal-storage',headers={'content-type':'application/pdf'},raise_for_status=lambda:None)
 pipe.extractor.extract_with_fallback=lambda path:{'confidence':1.,'tables':[]}
 pipe.audit_parser.parse=lambda *a:[dict(finding)]
 pipe.data_validator.validate_audit_data=lambda item:SimpleNamespace(is_valid=True,confidence=1.,warnings=[])
 pipe._maybe_upload_to_s3=lambda *a:None
 pipe.scheduler=SimpleNamespace(get_schedule_summary=lambda:{'efficiency':{'skip_percentage':0}},should_run=lambda source:(True,'Owned fixture'))
 monitor=ETLMonitor()
 async def full_pipeline():
  try:await monitor.run_with_monitoring(pipe.run_full_pipeline);return dict(returned=True,monitor_success=monitor.success)
  except BaseException as exc:return dict(returned=False,error=type(exc).__name__,diagnostic=str(exc),monitor_success=monitor.success)
 results.append(dict(control='full_pipeline_refusal_recording_failure',outcome=asyncio.run(full_pipeline())))
 event.remove(loader.engine,'before_cursor_execute',observation_failure)
 with loader.engine.connect() as conn:
  state=dict(countries=conn.scalar(text('SELECT count(*) FROM countries')),documents=conn.scalar(text('SELECT count(*) FROM source_documents')),audits=conn.scalar(text('SELECT count(*) FROM audits')),retained=conn.scalar(text('SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL')),jobs=conn.scalar(text('SELECT count(*) FROM ingestion_jobs')))
 loader.engine.dispose();pipe.http.close()
 for result in results:assert result['outcome']['error']=='DomainOwnershipError' and result['outcome']['diagnostic']=='Domain ownership unavailable; reconcile retained execution'
 assert results[1]['outcome']['monitor_success'] is False
 assert state==dict(countries=0,documents=0,audits=0,retained=1,jobs=0)
receipt=dict(generated_by=str(Path(__file__).relative_to(ROOT)),generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),generated_at=datetime.now(timezone.utc).isoformat(),target_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),start_source_sha256=start,source_sha256={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources},command=sys.argv,executable=sys.executable,python=sys.version,sqlalchemy=sqlalchemy.__version__,platform=platform.platform(),results=results,state=state,verdict='PASSED',limitation='Owned SQLite storage fault only; PostgreSQL transaction/process and production acceptance remain separate gates.')
output=Path(sys.argv[1]);output.write_text(json.dumps(receipt,indent=2));readback=json.loads(output.read_text());assert readback['generator_sha256']==receipt['generator_sha256'];assert readback['verdict']=='PASSED';print(json.dumps(receipt,indent=2))

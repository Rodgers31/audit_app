"""Actual task cancellation and Session-close interruption on owned SQLite."""
import asyncio,hashlib,json,os,platform,socket,subprocess,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ['PYTHON_DOTENV_DISABLED']='1';os.environ['DATABASE_URL']='sqlite:////tmp/batch9-legacy-behavior-bootstrap.sqlite'
sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
def no_network(*args,**kwargs):raise RuntimeError('External transport forbidden')
socket.socket.connect=no_network
import sqlalchemy
from sqlalchemy import event,text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from models import Base
from etl.database_loader import DatabaseLoader
@compiles(JSONB,'sqlite')
def sqlite_json(*args,**kwargs):return 'TEXT'
def attempt(call):
 try:call();return {'returned':True}
 except BaseException as exc:return {'returned':False,'error':type(exc).__name__,'diagnostic':str(exc)}
def state(loader):
 with loader.engine.connect() as conn:
  return dict(effects=conn.scalar(text('SELECT count(*) FROM inert_effects')),active=conn.scalar(text('SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL')))
sources=['etl/writer_ownership.py','etl/database_loader.py']
start={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources}
results=[]
with tempfile.TemporaryDirectory(prefix='batch9-legacy-cancellation-') as scratch:
 def loader_for(name):
  loader=DatabaseLoader(f'sqlite:///{scratch}/{name}.sqlite');Base.metadata.create_all(loader.engine)
  with loader.engine.begin() as conn:conn.execute(text('CREATE TABLE inert_effects(value INTEGER)'))
  return loader
 loader=loader_for('cancel')
 async def cancel_after_commit():
  alive=asyncio.Event();hold=asyncio.Event()
  async def runner():
   with loader.get_db_session() as db:
    db.execute(text('INSERT INTO inert_effects VALUES(1)'));db.commit();alive.set();await hold.wait()
  task=asyncio.create_task(runner());await alive.wait();task.cancel()
  try:await task;outcome={'returned':True}
  except BaseException as exc:outcome={'returned':False,'error':type(exc).__name__,'diagnostic':str(exc)}
  return outcome
 outcome=asyncio.run(cancel_after_commit());next_owner=attempt(loader.get_db_session)
 results.append(dict(control='cancel_after_committed_effect',outcome=outcome,next_owner=next_owner,state=state(loader)));loader.engine.dispose()
 loader=loader_for('close_interrupt');db=loader.get_db_session();db.execute(text('INSERT INTO inert_effects VALUES(1)'))
 @event.listens_for(db,'after_transaction_end')
 def interrupt_close(session,transaction):raise KeyboardInterrupt('owned actual transaction-end event interruption')
 outcome=attempt(db.close);next_owner=attempt(loader.get_db_session)
 results.append(dict(control='baseexception_during_session_close',outcome=outcome,next_owner=next_owner,state=state(loader)));loader.engine.dispose()
receipt=dict(generated_by=str(Path(__file__).relative_to(ROOT)),generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),generated_at=datetime.now(timezone.utc).isoformat(),target_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),start_source_sha256=start,source_sha256={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources},command=sys.argv,executable=sys.executable,python=sys.version,sqlalchemy=sqlalchemy.__version__,platform=platform.platform(),results=results,limitation='Owned SQLite cancellation only; no PostgreSQL/race acceptance claim.')
output=Path(sys.argv[1]);output.write_text(json.dumps(receipt,indent=2));readback=json.loads(output.read_text());assert readback['generator_sha256']==receipt['generator_sha256'];assert readback['results']==receipt['results'];print(json.dumps(receipt,indent=2))

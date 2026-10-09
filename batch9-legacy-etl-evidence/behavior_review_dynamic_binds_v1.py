"""Independent supported Session routing probes, owned SQLite only."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,os,platform,socket,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
os.environ['PYTHON_DOTENV_DISABLED']='1'
os.environ['DATABASE_URL']='sqlite:////tmp/batch9-legacy-behavior-bootstrap.sqlite'
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT))
def no_network(*args,**kwargs): raise RuntimeError('External transports forbidden')
socket.socket.connect=no_network
import sqlalchemy
from sqlalchemy import create_engine,text,Table,MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from models import Base,Country
from etl.database_loader import DatabaseLoader
from seeding.exclusion import reserve
from uuid import uuid4
@compiles(JSONB,'sqlite')
def sqlite_json(*args,**kwargs):return 'TEXT'
def attempt(call):
 try:call();return {'returned':True}
 except BaseException as exc:return {'returned':False,'error':type(exc).__name__,'diagnostic':str(exc)}
sources=['etl/writer_ownership.py','etl/database_loader.py']
start={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources}
results=[]
with tempfile.TemporaryDirectory(prefix='batch9-legacy-dynamic-') as scratch:
 for route in ['execute-bind-engine','execute-bind-connection','dynamic-bind-table','dynamic-bind-mapper']:
  a=DatabaseLoader(f'sqlite:///{scratch}/{route}-a.sqlite')
  b=create_engine(f'sqlite:///{scratch}/{route}-b.sqlite')
  for engine in [a.engine,b]:
   Base.metadata.create_all(engine)
   with engine.begin() as conn:conn.execute(text('CREATE TABLE inert_effects(value INTEGER)'))
  with sessionmaker(bind=b).begin() as db:assert reserve(db,'audits',uuid4())
  db=a.get_db_session()
  conn=b.connect();outer=conn.begin()
  def perform():
   if route=='execute-bind-engine':db.execute(text('INSERT INTO inert_effects VALUES(1)'),bind_arguments={'bind':b})
   elif route=='execute-bind-connection':db.execute(text('INSERT INTO inert_effects VALUES(1)'),bind_arguments={'bind':conn})
   elif route=='dynamic-bind-table':
    table=Table('inert_effects',MetaData(),autoload_with=b)
    db.bind_table(table,b)
    db.execute(table.insert().values(value=1))
   else:
    db.bind_mapper(Country,b)
    db.add(Country(iso_code='ZZZ',name='Inert',currency='ZZZ',timezone='UTC',default_locale='en'))
   db.commit()
  outcome=attempt(perform)
  close=attempt(db.close)
  if route=='execute-bind-connection':outer.commit()
  else:outer.rollback()
  with b.connect() as read:
   effects=read.scalar(text('SELECT count(*) FROM inert_effects'))+read.scalar(text('SELECT count(*) FROM countries'))
   active=read.scalar(text('SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL'))
  with a.engine.connect() as read:other_active=read.scalar(text('SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL'))
  results.append(dict(route=route,outcome=outcome,close=close,other_database_effects=effects,other_database_retained=active,default_database_retained=other_active))
  conn.close();a.engine.dispose();b.dispose()
receipt=dict(generated_by=str(Path(__file__).relative_to(ROOT)),generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),generated_at=datetime.now(timezone.utc).isoformat(),target_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),start_source_sha256=start,source_sha256={s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources},command=sys.argv,executable=sys.executable,python=sys.version,sqlalchemy=sqlalchemy.__version__,platform=platform.platform(),results=results,limitation='Owned SQLite routing controls only; no provider/storage or PostgreSQL race verification.')
output=Path(sys.argv[1]);output.write_text(json.dumps(receipt,indent=2));readback=json.loads(output.read_text());assert readback['generator_sha256']==receipt['generator_sha256'];assert readback['results']==receipt['results'];print(json.dumps(receipt,indent=2))

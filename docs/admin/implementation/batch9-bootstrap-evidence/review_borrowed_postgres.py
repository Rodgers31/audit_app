"""Actual PostgreSQL caller-transaction boundary on original and repaired bootstrap."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.orm import Session

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'backend/tests/batch9_bootstrap_fixture'))
from owned_database import owned_engine,schema_url
from models import Base
from seeding.registries import REGISTRY,load_builtin_domains
from seeding.types import DomainRunResult

URL=os.environ['BATCH9_BOOTSTRAP_POSTGRES_URL']
admin=owned_engine(URL)
subject_file=ROOT/'backend/bootstrap.py'
archive=None
if '--baseline' in sys.argv:
 archive=tempfile.TemporaryDirectory(prefix='pr590-pinned-bootstrap-')
 subject_file=Path(archive.name)/'bootstrap.py'
 subject_file.write_bytes(subprocess.check_output(['git','show','813acb0b75c6eccadf514dbbaffbc6439fd7fb63:backend/bootstrap.py'],cwd=ROOT))
spec=importlib.util.spec_from_file_location('bootstrap_transaction_subject',subject_file)
subject=importlib.util.module_from_spec(spec);spec.loader.exec_module(subject)
subject.PACKAGED_DATA_DIR = ROOT / "backend/data/reference"
subject.COUNTY_DATA_PATH = subject.PACKAGED_DATA_DIR / "enhanced_county_data.json"
load_builtin_domains()
results=[]
try:
 for force in (False,True):
  schema='bootstrap_'+uuid4().hex
  with admin.begin() as db:db.execute(text(f'CREATE SCHEMA "{schema}"'))
  engine=owned_engine(schema_url(URL,schema),allow_schema=True)
  Base.metadata.create_all(engine)
  with engine.begin() as db:db.execute(text('CREATE TABLE caller_effect(value text)'))
  caller=Session(engine);caller.execute(text("INSERT INTO caller_effect VALUES ('caller')"))
  outer=caller.get_transaction()
  subject.SessionLocal=lambda:caller
  subject._seed_national_data=lambda *a,**k:None
  def inert(session,settings,context):
   session.execute(text("INSERT INTO caller_effect VALUES ('budget')"))
   return DomainRunResult(domain='national_budget',items_processed=1,items_created=1)
  REGISTRY._handlers['national_budget']=inert
  error=None
  try:
   subject.initialize_reference_data(force=force)
   with engine.connect() as db:
    visible_effects=db.scalar(text('SELECT count(*) FROM caller_effect'))
    active_claims=db.scalar(text('SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL'))
    released_claims=db.scalar(text('SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NOT NULL'))
   outer_active=outer.is_active
   caller.rollback()
   with engine.connect() as db:
    remaining=db.scalar(text('SELECT count(*) FROM caller_effect'))
    retained=db.scalar(text('SELECT count(*) FROM seeding_domain_claims WHERE released_at IS NULL'))
   case={'force':force,'outer_active':outer_active,'visible_effects_before_caller_commit':visible_effects,'active_claims':active_claims,'released_claims':released_claims,'effects_after_caller_rollback':remaining,'claims_after_caller_rollback':retained}
   case['passed']=outer_active and visible_effects==0 and active_claims==1 and released_claims==0 and remaining==0 and retained==1
   results.append(case)
  finally:
   caller.close();engine.dispose()
   with admin.begin() as db:db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
finally:
 admin.dispose()
 if archive:archive.cleanup()
print(json.dumps(results,indent=2))
raise SystemExit(0 if all(c['passed'] for c in results) else 1)

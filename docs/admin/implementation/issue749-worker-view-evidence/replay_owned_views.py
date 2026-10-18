"""Portable, offline, disposable PostgreSQL replay for issue749.

No remote DSN, download, image pull, production mode or existing output reuse.
Historical producers and receipts remain immutable alongside this file.
"""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,subprocess,sys,time
import xml.etree.ElementTree as ET

CHECKOUT=Path(__file__).resolve().parents[4]
BACKEND=CHECKOUT/'backend'
IMAGE='public.ecr.aws/docker/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3'
EXPECTED={
 'clean':{'social_report_source_authority':'f140c09463d68b7878d4f7b199d04f15ef3b95e109cfbb5820572c9d5e0a84f0',
          'social_report_source_authority_snapshot':'60d9f03c6a0586c236e51f25fba05bc3659c72101bc3021fb0f7b887152f78ed'},
 'historical':{'social_report_source_authority':'a10869d91f9d43eb6713a33089592336a204650b25752c8c26065ec610c18de0',
               'social_report_source_authority_snapshot':'60d9f03c6a0586c236e51f25fba05bc3659c72101bc3021fb0f7b887152f78ed'}}

def parse(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--output',type=Path,required=True,help='New output directory outside the checkout')
 p.add_argument('--heavy-lock',type=Path,required=True,help='Existing external shared heavy-test lock')
 p.add_argument('--check-inputs',action='store_true',help='Validate paths and committed hashes only; no Docker or connections')
 p.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
 args=p.parse_args(argv)
 if args.check_inputs and args.child:p.error('--check-inputs and --child cannot be combined')
 return args

def validate(args):
 output=args.output.expanduser().resolve()
 lock=args.heavy_lock.expanduser().resolve()
 if output==CHECKOUT or CHECKOUT in output.parents or output in CHECKOUT.parents:
  raise ValueError('OUTPUT_MUST_BE_OUTSIDE_CHECKOUT')
 if not output.parent.is_dir() or (output.exists() and not args.child):
  raise ValueError('OUTPUT_MUST_BE_NEW_WITH_EXISTING_PARENT')
 if not lock.is_file() or lock==output or CHECKOUT in lock.parents:
  raise ValueError('EXISTING_EXTERNAL_HEAVY_LOCK_REQUIRED')
 semantic=json.loads((Path(__file__).parent/'semantic-review.json').read_text())
 if (EXPECTED['clean']['social_report_source_authority']!=semantic['clean_locked_sha256']
     or EXPECTED['historical']['social_report_source_authority']!=semantic['historical_locked_sha256']
     or semantic['sql_skeleton_exact_equal'] is not True):
  raise ValueError('CHECKED_IN_SEMANTIC_INPUT_MISMATCH')
 if not (BACKEND/'tests/social/test_report_authority_historical_schema.py').is_file():
  raise ValueError('FORMAL_TEST_MISSING')
 return output,lock

def source_snapshot():
 # Includes tracked and newly authored Python files; neither imports nor installs.
 files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','backend'],cwd=CHECKOUT,text=True).splitlines()
 return {name:hashlib.sha256((CHECKOUT/name).read_bytes()).hexdigest() for name in sorted(set(files)) if name.endswith('.py') and (CHECKOUT/name).is_file()}

def child_authority():
 value=os.environ.get('B17_PORTABLE_OWNED_CONTAINER','')
 if not value.startswith('b17-portable-view-'):
  raise RuntimeError('CHILD_REQUIRES_OWNED_CONTAINER')
 owner=json.loads((OUT/'owner.json').read_text())
 info=json.loads(subprocess.check_output(['docker','inspect',value],text=True,timeout=10))[0]
 if (hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=owner['controller_sha256']
     or info['Id']!=owner['container_id'] or info['Config']['Labels'].get('auditgava.issue749')!=owner['nonce']
     or info['HostConfig']['PortBindings']!={'5432/tcp':[{'HostIp':'127.0.0.1','HostPort':'55439'}]}
     or '/var/lib/postgresql/data' not in info['HostConfig']['Tmpfs']):
  raise RuntimeError('CHILD_CONTAINER_OWNERSHIP_MISMATCH')

args=parse()
OUT,LOCK=validate(args)
if args.check_inputs:
 print(json.dumps({'status':'INPUTS_VALID_NO_EXECUTION','image':IMAGE,'expected':EXPECTED,'output':str(OUT),'heavy_lock':str(LOCK)}))
 raise SystemExit(0)
if args.child:
 child_authority()
 from sqlalchemy import create_engine,text
 from sqlalchemy.orm import Session
 sys.path[:0]=[str(BACKEND)]
 from social.worker import role_contract as rc
 from social.models import SocialControls
 record={}

 for kind in ('clean','historical'):
  url='postgresql+psycopg2://postgres@127.0.0.1:55439/b17_view_'+kind
  env={'PATH':os.environ['PATH'],'PYTHONPATH':str(BACKEND),'DATABASE_URL':url}
  def upgrade(target):
   p=subprocess.run([sys.executable,'-m','alembic','upgrade',target],cwd=BACKEND,env=env,capture_output=True,text=True,timeout=90)
   (OUT/(kind+'-'+target+'.log')).write_text(p.stdout+p.stderr)
   if p.returncode:raise RuntimeError('MIGRATION_FAILED:'+kind+':'+target)
  upgrade('21d0394c1d6b')
  e=create_engine(url,pool_size=2,max_overflow=0)
  if kind=='historical':
   with e.begin() as c:
    if c.scalar(text('SELECT count(*) FROM budget_lines'))!=0:raise RuntimeError('NONEMPTY_REORDER_REFUSED')
    c.execute(text('ALTER TABLE budget_lines DROP COLUMN source_hash'))
    c.execute(text('ALTER TABLE budget_lines ADD COLUMN validation_warnings jsonb'))
    c.execute(text('ALTER TABLE budget_lines ADD COLUMN source_hash varchar(64)'))
    c.execute(text('ALTER TABLE budget_lines ADD COLUMN confidence_score numeric(3,2)'))
  upgrade('e621b17a0001')
  with Session(e) as db:db.add(SocialControls(id=1,publishing_enabled=False));db.commit()
  observed={}
  with e.begin() as c:
   observed['server_version']=c.scalar(text('SHOW server_version'))
   observed['columns']=list(c.scalars(text("SELECT attname FROM pg_attribute WHERE attrelid='budget_lines'::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum")))
   observed['views']=[]
   for name in rc.REPORT_VIEW_SHA256:
    definition=c.scalar(text('SELECT pg_get_viewdef(to_regclass(:name),true)'),{'name':name})
    for clause in ('FROM ','JOIN '):definition=definition.replace(clause+'"public".',clause).replace(clause+'public.',clause)
    digest=hashlib.sha256(definition.encode()).hexdigest()
    observed['views'].append(dict(name=name,definition=definition,digest=digest,expected=rc.REPORT_VIEW_SHA256[name]))
   try:rc._views(c,'public');observed['views_guard']='PASS'
   except rc.WorkerRoleError:observed['views_guard']='REFUSED'
  role='b17_view_'+kind
  with e.begin() as c:c.execute(text('CREATE ROLE '+role+' LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2'))
  try:rc.install_worker_role(e,role);observed['install']='PASS'
  except rc.WorkerRoleError:observed['install']='REFUSED'
  worker=create_engine(e.url.set(username=role),pool_size=1,max_overflow=0)
  frames=[]
  def trace(frame,event,arg):
   if event=='exception' and frame.f_code.co_filename.endswith('role_contract.py') and isinstance(arg[1],rc.WorkerRoleError):frames.append({'function':frame.f_code.co_name,'line':frame.f_lineno})
   return trace
  sys.settrace(trace)
  try:rc.verify_worker_role(worker,role);observed['verify']='PASS'
  except rc.WorkerRoleError:observed['verify']='REFUSED'
  finally:sys.settrace(None)
  observed['failure_frames']=frames
  worker.dispose();e.dispose();record[kind]=observed
  (OUT/'partial.json').write_text(json.dumps(record,indent=2)+'\n')
 if any(record[k][gate]!='PASS' for k in ('clean','historical') for gate in ('views_guard','install','verify')):raise RuntimeError('GREEN_CONTROL_FAILED')
 wanted=EXPECTED['historical']
 if {x['name']:x['digest'] for x in record['historical']['views']}!=wanted:raise RuntimeError('PRODUCTION_HASH_NOT_REPRODUCED')
 record['result']='ACCEPTS_EXACT_REVIEWED_CLEAN_AND_HISTORICAL_SCHEMAS'
 for kind in ('clean','historical'):
  if {x['name']:x['digest'] for x in record[kind]['views']}!=EXPECTED[kind]:raise RuntimeError('EXACT_REVIEWED_HASH_MISMATCH')
 record['formal_tests']=[]
 for optimize in (False,True):
  for kind in ('clean','historical'):
   env={'PATH':os.environ['PATH'],'PYTHONPATH':str(BACKEND)+':'+str(BACKEND/'tests/social'),'B17_REPORT_ROLE_TEST_DB_URL':'postgresql+psycopg2://postgres@127.0.0.1:55439/b17_view_'+kind}
   argv=[sys.executable]+(['-O'] if optimize else [])+['-m','pytest','-p','no:cacheprovider','--confcutdir=backend/tests','backend/tests/social/test_report_authority_historical_schema.py','-q','--tb=short','--junitxml='+str(OUT/(kind+('-optimized' if optimize else '-normal')+'.xml'))]
   p=subprocess.run(argv,cwd=CHECKOUT,env=env,capture_output=True,text=True,timeout=100)
   log=OUT/(kind+('-optimized' if optimize else '-normal')+'.log');log.write_text(p.stdout+p.stderr)
   record['formal_tests'].append({'argv':argv,'exit_code':p.returncode,'log':str(log)})
   if p.returncode:raise RuntimeError('FORMAL_TEST_FAILED:'+kind+':'+str(optimize))
 (OUT/'child-result.json').write_text(json.dumps(record,indent=2)+'\n')
 print(json.dumps({'result':record['result'],'clean':{k:v for k,v in record['clean'].items() if k not in ('views','columns')},'historical':{k:v for k,v in record['historical'].items() if k not in ('views','columns')}}));raise SystemExit
# The only database controller path owns a newly created loopback fixture.
try:
 prerequisite=subprocess.run(['docker','image','inspect',IMAGE],capture_output=True,text=True,timeout=15)
except (FileNotFoundError,subprocess.TimeoutExpired):
 print('SKIP_PREREQUISITE: Docker and the exact cached PG17 image are required; no pull attempted.')
 raise SystemExit(77)
if prerequisite.returncode:
 print('SKIP_PREREQUISITE: Docker or exact cached PG17 image unavailable; no pull attempted.')
 raise SystemExit(77)
with LOCK.open('r+') as lock:
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise RuntimeError('HEAVY_SLOT_BUSY_NO_START')
 OUT.mkdir()  # Exclusive: never overwrite archived or prior replay evidence.
 before=source_snapshot()
 (OUT/'source-before.json').write_text(json.dumps(before,indent=2)+'\n')
 name='b17-portable-view-'+str(os.getpid())
 nonce=os.urandom(12).hex()
 owned=False
 run=lambda argv,**kw:subprocess.run(argv,check=True,timeout=30,**kw)
 try:
  argv=['docker','create','--pull=never','--name',name,'--label','auditgava.issue749='+nonce,
        '--memory=256m','--cpus=1','--pids-limit=100','-p','127.0.0.1:55439:5432',
        '--tmpfs','/var/lib/postgresql/data','-e','POSTGRES_USER=postgres','-e','POSTGRES_HOST_AUTH_METHOD=trust',IMAGE]
  child=run(argv,capture_output=True,text=True);owned=True
  (OUT/'owner.json').write_text(json.dumps({'argv':argv,'container_id':child.stdout.strip(),'nonce':nonce,
    'pid':os.getpid(),'controller_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n')
  run(['docker','start',name],capture_output=True,text=True)
  for _ in range(80):
   if subprocess.run(['docker','exec',name,'pg_isready','-h','127.0.0.1','-U','postgres'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode==0:break
   time.sleep(.2)
  else:raise RuntimeError('PG_NOT_READY')
  for kind in ('clean','historical'):run(['docker','exec',name,'createdb','-U','postgres','b17_view_'+kind],capture_output=True,text=True)
  child=subprocess.run([sys.executable,str(Path(__file__)),'--output',str(OUT),'--heavy-lock',str(LOCK),'--child'],
    env={'PATH':os.environ['PATH'],'B17_PORTABLE_OWNED_CONTAINER':name},capture_output=True,text=True,timeout=480)
  (OUT/'child.log').write_text(child.stdout+child.stderr)
  if child.returncode:raise RuntimeError('CHILD_FAILED_SEE_RETAINED_LOG')
  result=json.loads((OUT/'child-result.json').read_text())
  counts={}
  case_ids={}
  for kind in ('clean','historical'):
   for mode in ('normal','optimized'):
    tree=ET.parse(OUT/(kind+'-'+mode+'.xml'))
    cases=list(tree.iter('testcase'))
    if len(cases)<11 or any(c.find(tag) is not None for c in cases for tag in ('failure','error','skipped')):
     raise RuntimeError('FORMAL_CASE_INVENTORY_REFUSED')
    counts[kind+'-'+mode]=len(cases)
    case_ids[kind+'-'+mode]=[{'class':c.get('classname'),'name':c.get('name')} for c in cases]
    raw=(OUT/(kind+'-'+mode+'.log')).read_text().lower()
    if 'xpassed' in raw or 'xfailed' in raw:raise RuntimeError('FORMAL_EXPECTED_FAILURE_STATUS_REFUSED')
  after=source_snapshot()
  (OUT/'source-after.json').write_text(json.dumps(after,indent=2)+'\n')
  if before!=after:raise RuntimeError('SOURCE_CHANGED_DURING_REPLAY')
  owner=json.loads((OUT/'owner.json').read_text())
  if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=owner['controller_sha256']:
   raise RuntimeError('CONTROLLER_CHANGED_DURING_REPLAY')
  result.update({'formal_case_counts':counts,'formal_case_ids':case_ids,'source_unchanged':True,'runtime':sys.version,'image':IMAGE,
    'controller_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'scope':'Owned isolated PostgreSQL replay only; no production, activation, live grants, provider or publishing acceptance.'})
 finally:
  if owned:
   try:
    run(['docker','rm','-fv',name],capture_output=True,text=True)
    owner=json.loads((OUT/'owner.json').read_text())
    listing=run(['docker','ps','-a','--no-trunc','--filter','id='+owner['container_id'],'--format','{{.ID}}'],capture_output=True,text=True)
    absent=listing.stdout.strip()==''
    if not absent:raise RuntimeError('OWNED_CONTAINER_STILL_PRESENT')
   except Exception:
    (OUT/'cleanup.json').write_text(json.dumps({'status':'UNVERIFIED','container_absent':None,'tmpfs_removed':None},indent=2)+'\n')
    raise
   (OUT/'cleanup.json').write_text(json.dumps({'status':'VERIFIED','container_absent':True,'tmpfs_removed':True,'successful_exact_id_listing_empty':True},indent=2)+'\n')
 result['cleanup_verified']=True
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['result'],'formal_case_counts':counts,'source_unchanged':True,'cleanup_verified':True}))

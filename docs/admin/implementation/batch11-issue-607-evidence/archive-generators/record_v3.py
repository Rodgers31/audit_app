import datetime,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
OUT=Path(__file__).resolve().parent
name=sys.argv[1]; limit=int(sys.argv[2]); command=sys.argv[3:]
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def measured(paths): return {p:digest(ROOT/p) if (ROOT/p).is_file() else None for p in paths}
paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().strip('\0').split('\0')
helper_paths=sorted({p for p in OUT.iterdir() if p.is_file() and p.suffix in ['.py','.js','.mjs','.ts']} | {p for name in ['probe-tests','probe-tests-v2','gated-tests','boundary-tests'] for p in (OUT/name).rglob('*') if p.is_file() and p.suffix in ['.py','.js','.mjs','.ts']})
helpers={str(p.relative_to(OUT)):digest(p) for p in helper_paths}
source=measured(paths); generator=digest(Path(__file__)); start=time.time()
head=subprocess.check_output(['git','rev-parse','HEAD','HEAD^{tree}'],cwd=ROOT).decode().splitlines()
status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).decode()
env={'PATH':'/Users/roger/.nvm/versions/node/v22.19.0/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','HOME':str(OUT/'home'),'TMPDIR':str(OUT/'tmp'),'DOCKER_HOST':'unix:///Users/roger/.docker/run/docker.sock'}
(OUT/'home').mkdir(exist_ok=True);(OUT/'tmp').mkdir(exist_ok=True)
with (OUT/(name+'.log')).open('x') as log:
 p=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 timed=False
 try: rc=p.wait(timeout=limit)
 except subprocess.TimeoutExpired:
  timed=True;os.killpg(p.pid,signal.SIGTERM)
  try:rc=p.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);rc=p.wait()
end_source=measured(paths)
r={'generated_by':Path(__file__).name,'generator_sha256':generator,'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'target_commit':head[0],'target_tree':head[1],'starting_status':status,'command':command,'timeout_seconds':limit,'timed_out':timed,'child_exit':rc,'source_hashes':source,'source_changed':[p for p in paths if source[p]!=end_source[p]],'generator_unchanged':generator==digest(Path(__file__)),'started_at':start,'ended_at':time.time(),'log':name+'.log','log_sha256':digest(OUT/(name+'.log'))}
r['helper_hashes']=helpers
r['helpers_changed']=[p for p,h in helpers.items() if not (OUT/p).is_file() or digest(OUT/p)!=h]
r['verification_exit']=rc if not r['source_changed'] and not r['helpers_changed'] and r['generator_unchanged'] and not timed else 1
with (OUT/(name+'.json')).open('x') as f:json.dump(r,f,indent=2)
if json.loads((OUT/(name+'.json')).read_text())!=r:raise RuntimeError('receipt readback mismatch')
print(json.dumps({k:v for k,v in r.items() if k not in ['source_hashes','helper_hashes','starting_status']},indent=2))
sys.exit(0 if r['verification_exit']==0 else 1)

import hashlib,json,os,platform,subprocess,sys,time
from pathlib import Path
ROOT=Path('/Users/roger/.codex/worktrees/batch10-etl-mappings/audit_app')
OUT=Path(__file__).resolve().parent
PYTHON=OUT/'venv/bin/python'
def inventory(root):
 names=set(subprocess.check_output(['git','ls-files'],cwd=root,text=True).splitlines())
 names.update(str(p.relative_to(root)) for folder in ('backend','etl') for p in (root/folder).rglob('*.py') if p.is_file() and '__pycache__' not in p.parts)
 return {n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in sorted(names) if (root/n).is_file()}
def run(name,args,root=ROOT,extra=None):
 if not name.replace('-','').replace('_','').isalnum(): raise ValueError('unsafe output')
 rec=OUT/(name+'.json'); log=OUT/(name+'.log')
 if rec.exists() or log.exists(): raise ValueError('existing output')
 before=inventory(root)
 env={'PATH':'/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','PYTHON_DOTENV_DISABLED':'1','PYTHONPATH':str(root/'backend'),'DATABASE_URL':'postgresql+psycopg2://batch10_mappings:batch10-inert-local@127.0.0.1:55522/batch10_mappings','BATCH10_MAPPINGS_DATABASE_URL':'postgresql+psycopg2://batch10_mappings:batch10-inert-local@127.0.0.1:55522/batch10_mappings','SUPABASE_URL':'http://127.0.0.1:9','SUPABASE_KEY':'batch10-inert','JWT_SECRET':'batch10-inert','TMPDIR':str(OUT/'tmp')}
 env.update(extra or {}); (OUT/'tmp').mkdir(exist_ok=True)
 cmd=[str(PYTHON),*args]; started=time.time()
 with log.open('xb') as f:
  try: code=subprocess.run(cmd,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=900).returncode
  except subprocess.TimeoutExpired: code=124
 discovered=inventory(root)
 after={n:hashlib.sha256((root/n).read_bytes()).hexdigest() if (root/n).is_file() else None for n in before}
 after.update({n:h for n,h in discovered.items() if n not in before})
 data={'generated_by':str(Path(__file__).resolve()),'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'command':cmd,'cwd':str(root),'environment':env,'runtime':platform.platform(),'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'source_tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=root,text=True).strip(),'source_before':before,'source_after':after,'source_stable':before==after,'started_at':started,'ended_at':time.time(),'child_exit':code,'verification_exit':code if before==after else 99,'log':str(log),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
 with rec.open('x') as f: json.dump(data,f,indent=2)
 if json.loads(rec.read_text())!=data: raise RuntimeError('readback mismatch')
 print(name,'exit',code,'stable',before==after); print(log.read_text()[-6500:]); return code
if __name__=='__main__': sys.exit(run(sys.argv[1],sys.argv[2:]))

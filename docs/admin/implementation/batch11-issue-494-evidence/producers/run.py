import hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def identity(root):
 def git(*a):return subprocess.check_output(['/usr/bin/git',*a],cwd=root,env={'PATH':os.defpath,'HOME':'/dev/null'},text=True).strip()
 need(Path(git('rev-parse','--show-toplevel')).resolve()==root,'exact git root required')
 paths=sorted(set(git('ls-files','-z').split('\0')+git('ls-files','--others','--exclude-standard','-z').split('\0'))-{''})
 return {'head':git('rev-parse','HEAD'),'tree':git('rev-parse','HEAD^{tree}'),'status':git('status','--porcelain=v1'),'files':{p:sha(root/p) if (root/p).is_file() else None for p in paths}}
def main():
 root,out,name,cwd,mode,*cmd=sys.argv[1:]; root=Path(root).resolve(); out=Path(out)
 need(not out.is_symlink(),'output symlink');out=out.resolve()
 need(out.is_dir() and not out.is_relative_to(root) and not root.is_relative_to(out),'external output required')
 need(name and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in name),'invalid name')
 need(mode in ('unit','build','native','plain'),'invalid mode');need(cmd and Path(cmd[0]).is_absolute(),'absolute executable')
 for d in (root,root/'frontend',Path(cwd)):
  for p in d.glob('.env*'):need(p.name.endswith(('.example','.sample','.template')),'dotenv runtime refused')
 dest=[out/(name+s) for s in ('.json','.stdout','.stderr')]
 for p in dest:need(not p.exists() and not p.is_symlink(),'inherited output')
 before=identity(root); gen=sha(__file__); work=out/(name+'-runtime');work.mkdir();(work/'home').mkdir();(work/'tmp').mkdir()
 base=Path(__file__).resolve().parent
 user=work/'npm-user';glob=work/'npm-global';user.write_text('');glob.write_text('')
 env={'PATH':str(Path(cmd[0]).parent)+os.pathsep+os.defpath,'HOME':str(work/'home'),'TMPDIR':str(work/'tmp'),'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','PYTHON_DOTENV_DISABLED':'1','NEXT_TELEMETRY_DISABLED':'1','ONNXRUNTIME_NODE_INSTALL':'skip','npm_config_cache':str(base/'npm-cache'),'npm_config_userconfig':str(user),'npm_config_globalconfig':str(glob),'npm_config_engine_strict':'true','PLAYWRIGHT_BROWSERS_PATH':str(base/'browsers'),'NATIVE_VERIFY_CACHE_DIR':str(base/'model-cache')}
 if mode=='build':env.update({'NEXT_PUBLIC_API_URL':'http://127.0.0.1:18033','INTERNAL_API_URL':'http://127.0.0.1:18033','NEXT_PUBLIC_SUPABASE_URL':'http://127.0.0.1:18033','NEXT_PUBLIC_SUPABASE_ANON_KEY':'batch11-inert-anon-key'})
 start=time.time();err=None;child=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
 try:stdout,stderr=child.communicate(timeout=1200)
 except subprocess.TimeoutExpired:
  os.killpg(child.pid,signal.SIGTERM)
  try:stdout,stderr=child.communicate(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);stdout,stderr=child.communicate(timeout=10)
  err='timeout; owned group terminated'
 after=identity(root);stable=before==after
 rec={'schema':1,'generated_by':'run.py','generator_sha256':gen,'started_at':start,'ended_at':time.time(),'source_before':before,'source_after':after,'source_stable':stable,'command':cmd,'cwd':cwd,'mode':mode,'resolved_environment':env,'exit':child.returncode,'error':err,'stdout_sha256':hashlib.sha256(stdout).hexdigest(),'stderr_sha256':hashlib.sha256(stderr).hexdigest(),'runtime':{'python':sys.version,'platform':sys.platform,'machine':os.uname().machine},'classification':'CURRENT_COMMAND_CAPTURE','current_checkout_acceptance':False}
 for p,data in zip(dest,[json.dumps(rec,indent=2).encode()+b'\n',stdout,stderr]):
  with p.open('xb') as f:f.write(data)
 need(json.loads(dest[0].read_bytes())==rec,'readback failure')
 print(json.dumps({'name':name,'exit':child.returncode,'stable':stable,'error':err,'seconds':round(time.time()-start,2)}))
 return 0 if child.returncode==0 and stable and err is None else 1
if __name__=='__main__':sys.exit(main())

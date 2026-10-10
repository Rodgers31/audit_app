import subprocess,pathlib,json,hashlib,time,sys
ROOT=pathlib.Path('/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app')
OWN=pathlib.Path(__file__).parent
PKG=ROOT/'docs/admin/implementation/batch10-scroll-evidence'
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*a):return subprocess.check_output(['git','-C',str(ROOT),*a],text=True).strip()
files=[ROOT/p for p in git('diff','--name-only','f6c31e271297eece52f34102dc40a1e2ed7069a8...HEAD').splitlines()]
files.extend([ROOT/'frontend/scripts/ci-browser-cohorts.mjs',ROOT/'frontend/scripts/legacy-e2e-env.mjs',OWN/'direct_controls.mjs',pathlib.Path(__file__)])
before={str(p):sha(p.read_bytes()) for p in files}
start=time.time()
commands=[('package-cli',['node',str(PKG/'verify.mjs')]),('package-tests',['node','--test',str(PKG/'verify.test.mjs')]),('direct-controls',['node',str(OWN/'direct_controls.mjs')]),('live-601',['gh','issue','view','601','--repo','Rodgers31/audit_app','--json','number,title,state,body,comments,url']),('live-607',['gh','issue','view','607','--repo','Rodgers31/audit_app','--json','number,title,state,body,comments,url'])]
results=[]
for name,command in commands:
 output=OWN/(name+'.log')
 with output.open('xb') as stream:
  c=subprocess.run(command,cwd=ROOT/'frontend',stdout=stream,stderr=subprocess.STDOUT,timeout=60)
 raw=output.read_bytes()
 results.append(dict(name=name,command=command,child_exit=c.returncode,log=str(output),log_sha256=sha(raw)))
 print(name,c.returncode,len(raw),flush=True)
after={str(p):sha(p.read_bytes()) for p in files}
receipt=dict(review='independent Spec',target_commit=git('rev-parse','HEAD'),target_tree=git('rev-parse','HEAD^{tree}'),started_at=start,ended_at=time.time(),generator_sha256=sha(pathlib.Path(__file__).read_bytes()),source_hashes=before,source_changed_during_run=[p for p,h in before.items() if after.get(p)!=h],commands=results)
with (OWN/'execution.json').open('x')as f:json.dump(receipt,f,indent=2)
if json.loads((OWN/'execution.json').read_text())!=receipt:raise RuntimeError('Receipt readback mismatch')
sys.exit(0 if all(r['child_exit']==0 for r in results)and not receipt['source_changed_during_run']else 1)

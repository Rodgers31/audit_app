import json, subprocess, pathlib, shutil, hashlib, os
out=pathlib.Path(__file__).parent
source=pathlib.Path('/Users/roger/.codex/worktrees/compatible-dependencies/audit_app')
base=source/'frontend'
cand=out.parent/'argparse2-candidate/frontend'
probe=source/'docs/admin/implementation/batch14-dependencies-evidence/probe-argparse.cjs'
def run(name,cmd,cwd=None):
 r=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True,timeout=120)
 (out/(name+'.stdout')).write_text(r.stdout); (out/(name+'.stderr')).write_text(r.stderr)
 result={'cmd':cmd,'cwd':str(cwd),'returncode':r.returncode}
 (out/(name+'.receipt.json')).write_text(json.dumps(result,indent=2)); return r
b=json.loads((base/'package-lock.json').read_text()); c=json.loads((cand/'package-lock.json').read_text())
prod=lambda x:{k:v for k,v in x['packages'].items() if k and not v.get('dev',False)}
delta={k:{'baseline':b['packages'].get(k),'candidate':c['packages'].get(k)} for k in b['packages'].keys()|c['packages'].keys() if b['packages'].get(k)!=c['packages'].get(k)}
(out/'lock-delta.json').write_text(json.dumps({'production_identical':prod(b)==prod(c),'production_counts':[len(prod(b)),len(prod(c))],'delta':delta},indent=2))
for name,root in [('baseline',base),('candidate',cand)]:
 run(name+'-probe',['node',str(probe),str(root)])
run('probe-absent',['node',str(probe),str(out/'missing')])
run('probe-noargs',['node',str(probe)])
for name,root in [('baseline',base),('candidate',cand)]:
 fixture=out/(name+'-repair-fixture'); fixture.mkdir(exist_ok=True)
 shutil.copytree(base/'scripts',fixture/'scripts',dirs_exist_ok=True)
 shutil.copy2(root/'package-lock.json',fixture/'package-lock.json')
 (fixture/'node_modules').mkdir(exist_ok=True)
 lock=json.loads((root/'package-lock.json').read_text())
 for key in lock['packages']:
  if key.endswith('/braces') or key.endswith('/sprintf-js'):
   if (root/key).is_dir(): shutil.copytree(root/key,fixture/key,dirs_exist_ok=True)
 run(name+'-repair',['node',str(fixture/'scripts/apply-tooling-repairs.cjs'),'--check'],fixture)
 shutil.rmtree(fixture)
fixture=out/'candidate-clean-install';fixture.mkdir(exist_ok=True)
for filename in ['package.json','package-lock.json']:shutil.copy2(cand/filename,fixture/filename)
for folder in ['scripts','eslint-rules']:shutil.copytree(base/folder,fixture/folder,dirs_exist_ok=True)
run('candidate-clean-install',['npm','ci','--no-audit','--no-fund','--cache',str(out.parent/'npm-cache')],fixture)
shutil.rmtree(fixture)
print((out/'lock-delta.json').read_text())
for f in sorted(out.glob('*.receipt.json')): print(f.name,f.read_text())

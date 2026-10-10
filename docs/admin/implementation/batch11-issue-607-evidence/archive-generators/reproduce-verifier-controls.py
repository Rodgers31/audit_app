import importlib.util,json,hashlib,subprocess,shutil
from pathlib import Path
root=Path(__file__).resolve().parent
old=root/'review-adversarial/verify_packet-d6e821070089e0149585331febb4a89358a95fc9a1d18224b44c27370b0a794e.py'
new=Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app/docs/admin/implementation/batch11-issue-607-evidence/tools/verify_packet.py')
def module(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
before=module(old,'before');after=module(new,'after')
source=root/'review-adversarial/attack-v1-20261010T095356/base'
owned=root/'verifier-controls-reproduction';shutil.copytree(source,owned)
packet=owned/'packet'; checkout=owned/'checkout'
data=json.loads((packet/'packet-v1.json').read_text());r=json.loads((packet/'green-report.json').read_text());(packet/'red-report.json').write_text(json.dumps(r));data['runs'][0]['counts']={'expected':1,'unexpected':0,'skipped':0,'flaky':0}
data['files']={p.relative_to(packet).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in packet.rglob('*') if p.is_file() and p.name!='packet-v1.json'};(packet/'packet-v1.json').write_text(json.dumps(data))
real=subprocess.check_output
subprocess.check_output=lambda args,*a,**kw: 'source.ts\n' if args==['git','ls-tree','-r','--name-only',before.BASE] else real(args,*a,**kw)
rows=[]
for name,v in [('before',before),('after',after)]:
 for kind in ['false-red','boolean-duration']:
  try:
   if kind=='false-red':v.verify(packet,checkout)
   else:
    q=json.loads((root/'focused-green-report.json').read_text());q['stats']['duration']=True;v.cases(q)
   accepted=True;error=None
  except Exception as e:accepted=False;error=str(e)
  rows.append({'version':name,'verifier_sha256':hashlib.sha256((old if name=='before' else new).read_bytes()).hexdigest(),'control':kind,'accepted':accepted,'error':error})
with (root/'verifier-controls-reproduction.json').open('x') as f:json.dump(rows,f,indent=2)
print(json.dumps(rows,indent=2))
assert [r['accepted'] for r in rows]==[True,True,False,False]

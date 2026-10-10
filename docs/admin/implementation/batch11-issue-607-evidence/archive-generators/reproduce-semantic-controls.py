"""Author execution of independently discovered schema-boundary hypotheses.
Dependencies are explicit controlled stubs, not browser acceptance.
"""
from pathlib import Path
import copy,hashlib,importlib.util,json,shutil,subprocess,sys
sys.dont_write_bytecode=True
out=Path(__file__).resolve().parent
fixture=out/'review-adversarial/attack-v5-20261010T101222/base'
owned=out/'semantic-controls-reproduction';owned.mkdir()
old1=out/'review-adversarial/verify_packet-34fb310503e51b0051e902dc929fd76b67c5714e31a92b0a693df0b7dbf65710.py'
old2=out/'review-adversarial/verify_packet-5731fc916703935a8ba49c28663cb29a7ae2749d6bdeed2985df6e2f58e50825.py'
current=Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app/docs/admin/implementation/batch11-issue-607-evidence/tools/verify_packet.py')
def mod(p):
 s=importlib.util.spec_from_file_location('verifier_'+hashlib.sha256(p.read_bytes()).hexdigest(),p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
modules={'before1':mod(old1),'before2':mod(old2),'after':mod(current)}
real=subprocess.check_output
subprocess.check_output=lambda args,*a,**kw: 'source.ts\n' if args==['git','ls-tree','-r','--name-only',modules['after'].BASE] else real(args,*a,**kw)
results=[]
for kind in ['focused-substitution','failed-diagnostic','empty-diagnostic','helper-drift-diagnostic']:
 root=owned/kind;shutil.copytree(fixture,root);packet=root/'packet';source=root/'checkout';data=json.loads((packet/'packet-v1.json').read_text());diag=next(r for r in data['runs'] if r['name']=='fixture-diagnostic-positive')
 if kind=='focused-substitution':
  focus=next(r for r in data['runs'] if r['name']=='focused-green');operations=next(r for r in data['runs'] if r['name']=='full-operations');focus.update(report=operations['report'],case_ids=operations['case_ids'],counts=operations['counts'])
 elif kind=='failed-diagnostic':
  red=next(r for r in data['runs'] if r['name']=='fixture-red');diag.update(report=red['report'],receipt=red['receipt'],case_ids=red['case_ids'],counts=red['counts'])
 elif kind=='empty-diagnostic':
  r=json.loads((packet/diag['report']).read_text())
  def skip(s):
   for spec in s['specs']:
    t=spec['tests'][0];t.update(status='skipped',expectedStatus='skipped');t['results'][0].update(status='skipped')
   for c in s.get('suites',[]):skip(c)
  for s in r['suites']:skip(s)
  r['stats'].update(expected=0,skipped=6);diag['counts'].update(expected=0,skipped=6);(packet/diag['report']).write_text(json.dumps(r))
 else:
  r=json.loads((packet/diag['receipt']).read_text());r['helpers_changed']=['producer.py'];(packet/diag['receipt']).write_text(json.dumps(r))
 data['files']={p.relative_to(packet).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in packet.rglob('*') if p.is_file() and p.name!='packet-v1.json'};(packet/'packet-v1.json').write_text(json.dumps(data))
 for version in [('before1' if kind in ['focused-substitution','failed-diagnostic'] else 'before2'),'after']:
  try:modules[version].verify(packet,source);accepted=True;error=None
  except Exception as e:accepted=False;error=str(e)
  results.append({'control':kind,'version':version,'accepted':accepted,'error':error})
with (out/'semantic-controls-reproduction.json').open('x') as f:json.dump(results,f,indent=2)
print(json.dumps(results,indent=2))
assert all(r['accepted']==(r['version']!='after') for r in results)

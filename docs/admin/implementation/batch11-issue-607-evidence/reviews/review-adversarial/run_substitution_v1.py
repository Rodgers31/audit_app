import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parent
CHECKOUT=Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
path=CHECKOUT/'docs/admin/implementation/batch11-issue-607-evidence/tools/verify_packet.py'
digest=hashlib.sha256(path.read_bytes()).hexdigest()
snapshot=ROOT/('verify_packet-'+digest+'.py')
if not snapshot.exists():snapshot.write_bytes(path.read_bytes())
assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==digest
spec=importlib.util.spec_from_file_location('verify_substitution',snapshot)
V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)
run=ROOT/('substitution-v1-'+time.strftime('%Y%m%dT%H%M%S'));run.mkdir()
template=ROOT/'attack-v3-20261010T095920/base'
real=subprocess.check_output
def git(args,**kwargs):
    if args==['git','ls-tree','-r','--name-only',V.BASE]:return 'source.ts\n'
    return real(args,**kwargs)
subprocess.check_output=git
results=[]
def case(name,mutation):
    folder=run/name;shutil.copytree(template,folder)
    packet=folder/'packet';source=folder/'checkout'
    data=json.loads((packet/'packet-v1.json').read_text())
    if mutation:mutation(data)
    data['files']={p.relative_to(packet).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in packet.rglob('*') if p.is_file() and p.name!='packet-v1.json'}
    (packet/'packet-v1.json').write_text(json.dumps(data,indent=2)+'\n')
    try:
        value=V.verify(packet,source)
        result={'name':name,'rejected':False,'value':value}
    except Exception as e:result={'name':name,'rejected':True,'error':type(e).__name__+': '+str(e)}
    results.append(result);print(json.dumps(result))
case('valid-control',None)
def focused_substitution(data):
    substitute=next(r for r in data['runs'] if r['name']=='full-operations')
    target=next(r for r in data['runs'] if r['name']=='focused-green')
    target.update(report=substitute['report'],case_ids=substitute['case_ids'],counts=substitute['counts'])
case('focused-replaced-by-six-operations-cases',focused_substitution)
def diagnostic_failure(data):
    red=next(r for r in data['runs'] if r['category']=='historical-red')
    data['runs'].append(dict(red,name='diagnostic-positive-but-failed',category='diagnostic-positive'))
case('diagnostic-positive-has-failed-case',diagnostic_failure)
subprocess.check_output=real
(run/'results.json').write_text(json.dumps({'verifier_sha256':digest,'python_version':sys.version,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                         'controlled_git_dependency':True,'real_browser_docker_database_calls':False,'results':results},indent=2)+'\n')
print(json.dumps({'results':str(run/'results.json'),'verifier_sha256':digest}))

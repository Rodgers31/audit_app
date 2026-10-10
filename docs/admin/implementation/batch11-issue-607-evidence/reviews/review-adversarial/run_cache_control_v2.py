import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

root=Path(__file__).resolve().parent
checkout=Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
tools=checkout/'docs/admin/implementation/batch11-issue-607-evidence/tools'
run=root/('cache-v2-'+time.strftime('%Y%m%dT%H%M%S'));run.mkdir()
shutil.copytree(root/'attack-v4-20261010T100704/base',run/'fixture')
packet=run/'fixture/packet';source=run/'fixture/checkout'
(packet/'tools').mkdir()
for name in ['verify_packet.py','replay.py']:(packet/'tools'/name).write_bytes((tools/name).read_bytes())
(packet/'tools/replay.py').write_bytes((root/'replay-46175fd698f5d55bb74eefbbbe0d167bb1c7c1f371dcf0df49c7d6f9a85bbe82.py').read_bytes())
manifest=json.loads((packet/'packet-v1.json').read_text())
manifest['files']={p.relative_to(packet).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in packet.rglob('*') if p.is_file() and p.name!='packet-v1.json'}
(packet/'packet-v1.json').write_text(json.dumps(manifest,indent=2)+'\n')
# Import a separate immutable verifier snapshot, avoiding cache writes in the controlled packet.
digest=hashlib.sha256((tools/'verify_packet.py').read_bytes()).hexdigest()
snapshot=root/('verify_packet-'+digest+'.py')
if not snapshot.exists():snapshot.write_bytes((tools/'verify_packet.py').read_bytes())
spec=importlib.util.spec_from_file_location('cache_verifier',snapshot)
V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)
real=subprocess.check_output
def fake_git(args,**kwargs):
    if args==['git','ls-tree','-r','--name-only',V.BASE]:return 'source.ts\n'
    return real(args,**kwargs)
subprocess.check_output=fake_git
results=[]
def verify(name):
    try:results.append({'name':name,'value':V.verify(packet,source),'rejected':False})
    except Exception as e:results.append({'name':name,'rejected':True,'exception':type(e).__name__+': '+str(e)})
verify('valid-packet-before-help')
command=[sys.executable,str(packet/'tools/replay.py'),'--help']
child=subprocess.run(command,capture_output=True,text=True)
(run/'help.stdout.log').write_text(child.stdout)
(run/'help.stderr.log').write_text(child.stderr)
verify('same-packet-after-help')
subprocess.check_output=real
result={'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'verifier_sha256':digest,'replay_sha256':hashlib.sha256((packet/'tools/replay.py').read_bytes()).hexdigest(),
        'python_version':sys.version,'command':command,'child_exit':child.returncode,'new_files':sorted(set(p.relative_to(packet).as_posix() for p in packet.rglob('*') if p.is_file())-set(manifest['files'])-{'packet-v1.json'}),
        'controlled_git_dependency':True,'no_docker_browser_database_calls':True,'results':results}
(run/'results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result));print(run/'results.json')

import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
sys.dont_write_bytecode = True
checkout=Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
root=Path('/Users/roger/.codex/visualizations/2026/10/10/01a12626-6d17-7a30-a5ea-1462a6883004/batch11-navigation/review-standards')
output=root/'focused-review'
assert not output.exists()
output.mkdir()
(output/'home').mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
started=time.time()
packet=checkout/'docs/admin/implementation/batch11-issue-607-evidence'
replay=packet/'tools/replay.py'
checker=packet/'tools/verify_packet.py'
inputs={str(p):sha(p) for p in [Path(__file__),root/'runtime-review.js',replay,checker,packet/'packet-v1.json']}
head=subprocess.check_output(['git','rev-parse','HEAD','HEAD^{tree}'],cwd=checkout,text=True).splitlines()
assert head==['6fcaed18327d4ebdb91b475c016d81ca624deda8','958d72062130267d0916ad14f9ab7ab6afb0af71']
assert subprocess.check_output(['git','status','--porcelain'],cwd=checkout,text=True)==''
paths=subprocess.check_output(['git','ls-files','-z'],cwd=checkout).decode().strip('\0').split('\0')
source={p:sha(checkout/p) for p in paths}
env={'PATH':'/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin','HOME':str(output/'home'),'PYTHONDONTWRITEBYTECODE':'1','DOCKER_HOST':'unix:///Users/roger/.docker/run/docker.sock'}
docker=shutil.which('docker',path=env['PATH'])
assert docker
container='batch11-navigation-linux'
inspect_command=[docker,'inspect',container]
meta=json.loads(subprocess.check_output(inspect_command,env=env,timeout=30))[0]
assert meta['Id']=='3f947fe7ad040d6cb7c99d9bdacce56ce7aec11510a0a31a17a6fe663ccb14f1'
assert meta['Config']['Labels']['audit_app.owner']=='batch11-navigation'
assert meta['State']['Running'] is True and meta['HostConfig']['PortBindings'] in [None,{}]
metadata={'Id':meta['Id'],'Image':meta['Image'],'image_reference':meta['Config']['Image'],'labels':meta['Config']['Labels'],'state_running':meta['State']['Running'],'port_bindings':meta['HostConfig']['PortBindings'],'mounts':meta['Mounts'],'command':inspect_command}
with (output/'container.json').open('x') as f:json.dump(metadata,f,indent=2);f.write('\n')
commands=[]
def run(name,argv,timeout):
    with (output/(name+'.log')).open('x') as log:
        child=subprocess.run(argv,env=env,cwd=checkout,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
    commands.append({'argv':argv,'child_exit':child.returncode,'log_sha256':sha(output/(name+'.log'))})
    return child.returncode
runtime_command=[docker,'exec',container,'env','-i','PATH=/opt/b11/node-v22.23.3-linux-x64/bin:/opt/b11/python/bin:/usr/local/bin:/usr/bin:/bin','HOME=/evidence/home','PLAYWRIGHT_BROWSERS_PATH=/ms-playwright','node','/evidence/review-standards/runtime-review.js']
assert run('runtime',runtime_command,60)==0
runtime=json.loads((output/'runtime.log').read_text())
assert runtime['nodeVersion']=='v22.23.3' and runtime['playwrightVersion']=='1.58.2' and runtime['browserVersion']=='145.0.7632.6'
command=[sys.executable,str(replay),'--checkout',str(checkout),'--output',str(output/'replay'),'--container',container,'--docker-host',env['DOCKER_HOST'],'--mode','focused']
assert run('replay-launch',command,1500)==0
receipt=json.loads((output/'replay/receipt.json').read_text())
assert receipt['head']==head[0] and receipt['tree']==head[1] and receipt['source_changed']==[] and receipt['source_hashes']==source
assert receipt['child_exit']==0 and receipt['timed_out'] is False
module_spec=importlib.util.spec_from_file_location('standards_fresh_verify',checker)
module=importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(module)
report=module.load(output/'replay/report.json')
measured,counts=module.cases(report)
assert len(measured)==6 and counts=={'expected':6,'unexpected':0,'skipped':0,'flaky':0}
project=report['config']['projects'][0]
assert project['use']['viewport']=={'width':1280,'height':720} and project['retries']==0 and report['config']['workers']==2
changed=[p for p,h in source.items() if sha(checkout/p)!=h]
assert not changed and all(sha(Path(p))==h for p,h in inputs.items())
assert subprocess.check_output(['git','status','--porcelain'],cwd=checkout,text=True)==''
result={'head':head[0],'tree':head[1],'started':started,'ended':time.time(),'source_hashes':source,'source_changed':changed,'inputs_before':inputs,'inputs_after':{p:sha(Path(p)) for p in inputs},'producer_argv':sys.argv,'commands':commands,'container_metadata_sha256':sha(output/'container.json'),'runtime':runtime,'runtime_file_sha256':sha(output/'runtime.log'),'portable_receipt_sha256':sha(output/'replay/receipt.json'),'report_sha256':sha(output/'replay/report.json'),'focused_counts':counts,'viewport':project['use']['viewport'],'configured_workers':report['config']['workers'],'retries':project['retries'],'child_exit':0,'scope':'Independent fresh six-case focused execution; current full acceptance remains false; no hosted or production acceptance','host_runtime':{'executable':sys.executable,'executable_sha256':sha(sys.executable),'version':sys.version,'platform':platform.platform()}}
with (output/'review-receipt.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
assert json.loads((output/'review-receipt.json').read_text())==result
print(json.dumps({k:result[k] for k in ['head','tree','source_changed','focused_counts','viewport','configured_workers','retries','child_exit','scope']}))

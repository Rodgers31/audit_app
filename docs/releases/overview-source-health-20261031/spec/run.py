import json,subprocess,time,sys
from pathlib import Path
p=Path(__file__).resolve().parent
label=sys.argv[1]
old=json.loads((p/'run-1.command.json').read_text())['argv']
cmd=[x.replace('overview-spec-retry-1','overview-spec-'+label).replace('/evidence/run-1.json','/evidence/'+label+'.json')for x in old]
(p/(label+'.command.json')).write_text(json.dumps({'argv':cmd,'network':'none','owned_container_only':True},indent=2))
start=time.time()
with (p/(label+'.txt')).open('w')as out:r=subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT)
(p/(label+'.exit.json')).write_text(json.dumps({'exit_code':r.returncode,'seconds':time.time()-start}))
print((p/(label+'.txt')).read_text()[-15000:])

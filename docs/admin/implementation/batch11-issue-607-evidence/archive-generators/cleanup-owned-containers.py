"""Remove only this lane's exact label-verified disposable containers."""
import datetime,hashlib,json,subprocess
from pathlib import Path
OUT=Path(__file__).resolve().parent
owned=[('batch11-navigation-postgres','1b078b7391980bcac8018c65b8556a426875c42667c6c4705d0db253bddb1e11'),('batch11-navigation-linux','3f947fe7ad040d6cb7c99d9bdacce56ce7aec11510a0a31a17a6fe663ccb14f1')]
rows=[]
for name,identity in owned:
 command=['docker','inspect',name];raw=subprocess.check_output(command);d=json.loads(raw)[0]
 assert d['Id']==identity and d['Config']['Labels'].get('audit_app.owner')=='batch11-navigation' and not d['HostConfig'].get('PortBindings')
 if name.endswith('postgres'):assert d['HostConfig']['NetworkMode']=='container:'+owned[1][1]
 rows.append({'name':name,'id':identity,'label':d['Config']['Labels']['audit_app.owner'],'image':d['Image'],'host_ports':d['HostConfig'].get('PortBindings'),'running_before':d['State']['Running'],'inspect_sha256':hashlib.sha256(raw).hexdigest()})
for row in rows:
 actions=[]
 for command in [['docker','stop','--time','10',row['id']],['docker','rm',row['id']]]:
  r=subprocess.run(command,capture_output=True,text=True,timeout=40);actions.append({'command':command,'child_exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr});assert r.returncode==0
 row['actions']=actions
 r=subprocess.run(['docker','inspect',row['id']],capture_output=True,text=True);assert r.returncode==1 and 'No such object' in r.stderr;row['absent_after']=True;row['readback_stderr']=r.stderr
data={'generated_by':Path(__file__).name,'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'containers':rows,'worktree_retained':True,'raw_external_artifacts_retained':True,'no_shared_images_removed':True}
with (OUT/'owned-container-cleanup.json').open('x') as f:json.dump(data,f,indent=2)
assert json.loads((OUT/'owned-container-cleanup.json').read_text())==data
print(json.dumps({'removed':[r['name'] for r in rows],'worktree_retained':True}))

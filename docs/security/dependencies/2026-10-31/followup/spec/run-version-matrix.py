#!/usr/bin/env python3
"""Bounded isolated registry-version controls; never imports candidate application code."""
import hashlib,json,os,pathlib,resource,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parent
NODE=pathlib.Path(os.environ.get('SPEC_NODE',str(ROOT.parents[1]/'runtime/node-v24.22.1-darwin-arm64/bin/node')))
OUT=ROOT/'runs';OUT.mkdir(exist_ok=True)
def limits():
 resource.setrlimit(resource.RLIMIT_CPU,(3,3))
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
cases=[]
for module in ['mm3','mm6','mm7','mm71','mm9','mm1024','mm10','mm1100','mm1101','mm11']:
 for level in ['default',0,1,2]:cases.append(dict(module=module,parts=8,level=level,instrument=True))
for module in ['mm10','mm11','mm3']:
 for n in [4,6,10]:cases.append(dict(module=module,parts=n,level=2,instrument=False))
cases.append(dict(module='mm10',parts=8,level=2,instrument=True,family='previous'))
records=[]
for index,config in enumerate(cases):
 argv=[str(NODE),'--max-old-space-size=96',str(ROOT/'probe-version.cjs'),json.dumps(config,separators=(',',':'))]
 start=time.monotonic()
 try:
  p=subprocess.run(argv,cwd=ROOT,env={'PATH':str(NODE.parent)+':/usr/bin:/bin','HOME':str(ROOT/'home')},capture_output=True,text=True,timeout=4,preexec_fn=limits)
  rec={'index':index,'argv':argv,'config':config,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'wall_seconds':time.monotonic()-start,'timed_out':False}
  if p.returncode==0:rec['measurement']=json.loads(p.stdout)
 except subprocess.TimeoutExpired as e:
  rec={'index':index,'argv':argv,'config':config,'timed_out':True,'stdout':str(e.stdout),'stderr':str(e.stderr),'wall_seconds':time.monotonic()-start}
 records.append(rec)
 (OUT/f'matrix-{index:02}.json').write_text(json.dumps(rec,indent=2)+'\n')
summary={'harness_sha256':hashlib.sha256((ROOT/'probe-version.cjs').read_bytes()).hexdigest(),'node':str(NODE),'timeout_seconds':4,'cpu_seconds':3,'max_old_space_mb':96,'records':records}
(OUT/'version-matrix.json').write_text(json.dumps(summary,indent=2)+'\n')
for r in records:
 m=r.get('measurement',{});print(json.dumps({'module':r['config']['module'],'level':r['config']['level'],'parts':r['config']['parts'],'family':r['config'].get('family','advisory'),'exit':r.get('returncode'),'timeout':r['timed_out'],'set':m.get('setLength'),'phases':m.get('observations'),'ms':round(m.get('elapsed_ms',0),3)}))
if any(r.get('returncode')!=0 or r['timed_out'] for r in records):raise SystemExit(1)

#!/usr/bin/env python3
import json,os,pathlib,resource,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parent
NODE=pathlib.Path(os.environ.get('SPEC_NODE',str(ROOT.parents[1]/'runtime/node-v24.22.1-darwin-arm64/bin/node')))
def limits():resource.setrlimit(resource.RLIMIT_CPU,(1,1));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
records=[]
for module in ['mm3','mm11']:
 for n in [4,8,12]:
  argv=[str(NODE),'--max-old-space-size=64',str(ROOT/'legacy-other-pattern.cjs'),module,str(n)];start=time.monotonic()
  try:
   p=subprocess.run(argv,cwd=ROOT,env={'PATH':str(NODE.parent)+':/usr/bin:/bin'},capture_output=True,text=True,timeout=.75,preexec_fn=limits)
   r={'module':module,'parts':n,'argv':argv,'timed_out':False,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'wall_seconds':time.monotonic()-start}
  except subprocess.TimeoutExpired as e:r={'module':module,'parts':n,'argv':argv,'timed_out':True,'stdout':e.stdout.decode() if isinstance(e.stdout,bytes) else e.stdout,'stderr':e.stderr.decode() if isinstance(e.stderr,bytes) else e.stderr,'wall_seconds':time.monotonic()-start}
  records.append(r);print(module,n,r.get('returncode'),'timeout',r['timed_out'],round(r['wall_seconds'],3),flush=True)
(ROOT/'runs/other-pattern.json').write_text(json.dumps(records,indent=2)+'\n')

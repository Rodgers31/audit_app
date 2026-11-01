#!/usr/bin/env python3
import hashlib,json,os,pathlib,resource,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parent
NODE=pathlib.Path(os.environ.get('SPEC_NODE',str(ROOT.parents[1]/'runtime/node-v24.22.1-darwin-arm64/bin/node')))
SOURCE=pathlib.Path(os.environ.get('SPEC_SOURCE_ROOT','/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app'))
FRONTEND=SOURCE/'frontend'
def limits():
 resource.setrlimit(resource.RLIMIT_CPU,(30,30));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
records=[]
cases=[
 ('candidate-permanent-regressions',[str(NODE),'--test','scripts/deepmerge-boundary.test.cjs','scripts/tooling-repair-install.test.cjs','scripts/modern-glob-boundary.test.cjs'],FRONTEND,0),
 ('candidate-check',[str(NODE),'scripts/apply-tooling-repairs.cjs','--check'],FRONTEND,0),
 ('exact-permanent-minimatch-red',[str(NODE),'--require',str(ROOT/'minimatch-red-preload.cjs'),'--test','--test-name-pattern','modern minimatch bounds','scripts/modern-glob-boundary.test.cjs'],FRONTEND,1),
 ('legacy-callers',[str(NODE),'--max-old-space-size=256',str(ROOT/'legacy-callers.cjs'),str(FRONTEND)],FRONTEND,0),
 ('minimatch-applicability',[str(NODE),'--test',str(ROOT/'minimatch-applicability.test.cjs')],FRONTEND,0),
 ('guard-exemption-control',[str(NODE),'--max-old-space-size=256',str(ROOT/'guard-exemption-control.cjs'),str(FRONTEND)],FRONTEND,0),
 ('legacy-api-major-control',[str(NODE),'--max-old-space-size=256',str(ROOT/'legacy-api-major-control.cjs'),str(FRONTEND)],FRONTEND,0),
 ('deepmerge-installer-adversarial',[str(NODE),'--max-old-space-size=256',str(ROOT/'deepmerge-installer-adversarial.cjs'),str(FRONTEND)],FRONTEND,0),
]
for name,argv,cwd,expected in cases:
 start=time.monotonic()
 try:
  p=subprocess.run(argv,cwd=cwd,env={'PATH':str(NODE.parent)+':/usr/bin:/bin','HOME':str(ROOT/'home'),'NODE_ENV':'test','SPEC_FRONTEND_ROOT':str(FRONTEND)},text=True,capture_output=True,timeout=45,preexec_fn=limits)
  r={'name':name,'argv':argv,'cwd':str(cwd),'returncode':p.returncode,'expected_returncode':expected,'timed_out':False,'stdout':p.stdout,'stderr':p.stderr,'wall_seconds':time.monotonic()-start}
 except subprocess.TimeoutExpired as e:r={'name':name,'argv':argv,'cwd':str(cwd),'timed_out':True,'stdout':str(e.stdout),'stderr':str(e.stderr),'expected_returncode':expected,'wall_seconds':time.monotonic()-start}
 if name=='exact-permanent-minimatch-red':r['red_failure_observed']=('256 !== 8' in r['stdout']+r['stderr'] and 'review-minimatch-red-interceptions=1' in r['stdout']+r['stderr'])
 records.append(r);(ROOT/'runs'/f'{name}.receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(name,r.get('returncode'),'expected',expected,'seconds',round(r['wall_seconds'],2),flush=True)
(ROOT/'runs/candidate-controls.json').write_text(json.dumps(records,indent=2)+'\n')
if any(r.get('returncode')!=r['expected_returncode'] or r['timed_out'] or r.get('red_failure_observed') is False for r in records):raise SystemExit(1)

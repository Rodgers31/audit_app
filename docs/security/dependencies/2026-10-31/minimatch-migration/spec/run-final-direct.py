#!/usr/bin/env python3
"""Run only after the author's final repaired installation is ready; never overwrites baseline."""
import datetime,hashlib,json,os,pathlib,resource,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parent;SOURCE=pathlib.Path(os.environ.get('SPEC_SOURCE_ROOT','/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app'));NODE=pathlib.Path(os.environ.get('SPEC_NODE',str(ROOT.parents[1]/'runtime/node-v24.22.1-darwin-arm64/bin/node')))
def limits():resource.setrlimit(resource.RLIMIT_CPU,(40,40));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
argv=[str(NODE),'--max-old-space-size=1024',str(ROOT/'probe-core-lint.cjs'),str(SOURCE/'frontend'),'direct'];start=time.monotonic();p=subprocess.run(argv,cwd=SOURCE/'frontend',env={'PATH':str(NODE.parent)+':/usr/bin:/bin','HOME':str(ROOT/'home'),'NODE_ENV':'test'},text=True,capture_output=True,timeout=55,preexec_fn=limits)
rec={'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':argv,'returncode':p.returncode,'stdout_sha256':hashlib.sha256(p.stdout.encode()).hexdigest(),'stderr':p.stderr,'wall_seconds':time.monotonic()-start};(ROOT/'runs/final-direct.stdout.json').write_text(p.stdout);(ROOT/'runs/final-direct.receipt.json').write_text(json.dumps(rec,indent=2)+'\n');assert p.returncode==0,rec
before=json.loads((ROOT/'baseline-pre-migration/effective-configs-and-diagnostics.json').read_text());after=json.loads(p.stdout)
assert after['interceptions']==[];assert after['minimatchUsed']=='11.0.3';comparisons={}
for key in ['sourceFileCount','lintedFileCount','configurations','mappings','configArrayCases','diagnostic']:comparisons[key]=before[key]==after[key]
assert all(comparisons.values()),comparisons
summary={'source_files':after['sourceFileCount'],'linted_files':after['lintedFileCount'],'unique_configs':len(after['configurations']),'baseline_payload_sha256':hashlib.sha256((ROOT/'baseline-pre-migration/effective-configs-and-diagnostics.json').read_bytes()).hexdigest(),'installed_minimatch':after['minimatchUsed'],'runtime_redirection_used':False,'comparisons':comparisons,'identical':True};(ROOT/'runs/final-direct-parity-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))

# Independent catalog and public-path checks use the actual installed packages.
for name,script,arguments in [
 ('final-rule-catalog','capture-rule-catalog.cjs',[]),
 ('final-flat-api','probe-flat-api.cjs',['baseline']),
 ('final-public-api','probe-final-public.cjs',[]),
]:
 argv=[str(NODE),'--max-old-space-size=384',str(ROOT/script),str(SOURCE/'frontend'),*arguments];start=time.monotonic();p=subprocess.run(argv,cwd=SOURCE/'frontend',env={'PATH':str(NODE.parent)+':/usr/bin:/bin'},capture_output=True,text=True,timeout=15,preexec_fn=limits)
 rec={'argv':argv,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'wall_seconds':time.monotonic()-start};(ROOT/'runs'/f'{name}.receipt.json').write_text(json.dumps(rec,indent=2)+'\n');assert p.returncode==0,rec
 current=json.loads(p.stdout)
 if name=='final-rule-catalog':assert current==json.loads((ROOT/'baseline-pre-migration/declared-rule-catalog.json').read_text())
 if name=='final-flat-api':
  old=json.loads(json.loads((ROOT/'runs/flat-api.receipts.json').read_text())[0]['stdout']);assert current['interceptions']==0;assert current['cases']==old['cases'];assert current['noMatchError']==old['noMatchError']
 print(name,'exact comparison complete')

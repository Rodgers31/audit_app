#!/usr/bin/env python3
import datetime,hashlib,json,os,pathlib,resource,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parent;SOURCE=pathlib.Path(os.environ.get('SPEC_SOURCE_ROOT','/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app'));NODE=pathlib.Path(os.environ.get('SPEC_NODE',str(ROOT.parents[1]/'runtime/node-v24.22.1-darwin-arm64/bin/node')))
def limits():resource.setrlimit(resource.RLIMIT_CPU,(40,40));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
records=[];data={}
for mode in ['baseline','modern-core']:
 argv=[str(NODE),'--max-old-space-size=1024',str(ROOT/'probe-core-lint.cjs'),str(SOURCE/'frontend'),mode];start=time.monotonic();p=subprocess.run(argv,cwd=SOURCE/'frontend',env={'PATH':str(NODE.parent)+':/usr/bin:/bin','HOME':str(ROOT/'home'),'NODE_ENV':'test'},text=True,capture_output=True,timeout=55,preexec_fn=limits)
 rec={'mode':mode,'argv':argv,'returncode':p.returncode,'stdout_sha256':hashlib.sha256(p.stdout.encode()).hexdigest(),'stderr':p.stderr,'wall_seconds':time.monotonic()-start};records.append(rec);(ROOT/'runs'/f'{mode}.stdout.json').write_text(p.stdout);print(mode,p.returncode,round(rec['wall_seconds'],2),flush=True)
 if p.returncode==0:data[mode]=json.loads(p.stdout)
(ROOT/'runs/core-lint-receipts.json').write_text(json.dumps(records,indent=2)+'\n')
assert len(data)==2,records
for key in ['sourceFileCount','lintedFileCount','configurations','mappings','configArrayCases','diagnostic']:assert data['baseline'][key]==data['modern-core'][key],key
first=next(iter(data['baseline']['configurations'].values()));rules=first['rules'];summary={'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'comparison':'exact full effective config/options, every source file diagnostic and direct ConfigArray behavior','linted':data['baseline']['lintedFileCount'],'unique_configs':len(data['baseline']['configurations']),'rules_in_first_config':len(rules),'enabled_rules_in_first_config':sum(v[0] not in [0,'off'] for v in rules.values()),'rule_namespaces':{},'interceptions':data['modern-core']['interceptions'],'equal':True}
for name,v in rules.items():prefix=name.split('/')[0]if'/'in name else 'core';summary['rule_namespaces'].setdefault(prefix,{'configured':0,'enabled':0});summary['rule_namespaces'][prefix]['configured']+=1;summary['rule_namespaces'][prefix]['enabled']+=v[0]not in[0,'off']
(ROOT/'runs/core-parity-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))

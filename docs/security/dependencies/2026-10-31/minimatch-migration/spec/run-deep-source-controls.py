#!/usr/bin/env python3
import concurrent.futures,json,os,pathlib,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parent;NODE=pathlib.Path(os.environ.get('SPEC_NODE',str(ROOT.parents[1]/'runtime/node-v24.22.1-darwin-arm64/bin/node')));FRONTEND=str(pathlib.Path(os.environ.get('SPEC_SOURCE_ROOT','/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app'))/'frontend')
origins=['eslint/lib/cli-engine/file-enumerator.js','eslint/lib/eslint/eslint-helpers.js','@humanwhocodes/config-array/api.js','flat-cache/src/del.js','rimraf/dist/commonjs/index.js']
def run(origin):
 argv=[str(NODE),'--max-old-space-size=384',str(ROOT/'probe-source-caller-shadow.cjs'),FRONTEND,origin];start=time.monotonic();p=subprocess.run(argv,env={'PATH':str(NODE.parent)+':/usr/bin:/bin'},text=True,capture_output=True,timeout=15);return{'origin':origin,'argv':argv,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'wall_seconds':time.monotonic()-start}
with concurrent.futures.ThreadPoolExecutor(max_workers=2)as pool:records=list(pool.map(run,origins))
(ROOT/'runs/deep-source-controls-green.json').write_text(json.dumps(records,indent=2)+'\n')
for r in records:print(r['origin'],r['returncode'],round(r['wall_seconds'],2),r['stderr'][-100:])
assert all(r['returncode']==0 for r in records),records

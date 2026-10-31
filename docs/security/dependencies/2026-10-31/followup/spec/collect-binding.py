#!/usr/bin/env python3
import datetime,hashlib,json,os,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parent
SOURCE=pathlib.Path(os.environ.get('SPEC_SOURCE_ROOT','/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app'))
NODE=pathlib.Path(os.environ.get('SPEC_NODE',str(ROOT.parents[1]/'runtime/node-v24.22.1-darwin-arm64/bin/node')))
def sh(*argv):return subprocess.check_output(argv,cwd=SOURCE,text=True).strip()
def record(p):return{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
files=['frontend/package.json','frontend/package-lock.json','frontend/scripts/apply-tooling-repairs.cjs','frontend/scripts/tooling-repairs.json','frontend/scripts/tooling-repair-install.test.cjs','frontend/scripts/deepmerge-boundary.test.cjs','frontend/scripts/modern-glob-boundary.test.cjs','frontend/.eslintrc.json','docs/security/DEPENDENCY_FOLLOWUP_2026_10_31.md']
versions=json.load(open(ROOT/'runs/version-matrix.json'))
installed={}
for rel,alias in [('frontend/node_modules/minimatch/minimatch.js','mm3'),('frontend/node_modules/@typescript-eslint/typescript-estree/node_modules/minimatch/dist/commonjs/index.js','mm11')]:
 p=SOURCE/rel
 if not p.exists():continue
 measurements=[r['measurement'] for r in versions['records'] if r['config']['module']==alias]
 fixture=pathlib.Path(measurements[0]['entry'])
 installed[rel]={**record(p),'fixture':str(fixture),'fixture_sha256':record(fixture)['sha256'],'same_fixture_bytes':p.read_bytes()==fixture.read_bytes()}
lock=json.loads((SOURCE/'frontend/package-lock.json').read_text());legacy=[];modern=[];callers=[]
for entry,data in lock['packages'].items():
 if entry.endswith('/node_modules/minimatch') or entry=='node_modules/minimatch':
  (legacy if data['version']=='3.1.5' else modern).append({'entry':entry,'version':data['version'],'dev':data.get('dev',False),'resolved':data.get('resolved'),'integrity':data.get('integrity')})
 if 'minimatch' in data.get('dependencies',{}) and not('node_modules/@types/' in entry):callers.append({'entry':entry,'version':data.get('version'),'minimatch':data['dependencies']['minimatch'],'dev':data.get('dev',False)})
manifest=json.loads((SOURCE/'frontend/scripts/tooling-repairs.json').read_text());deep=next(p for p in manifest['packages'] if p['name']=='deepmerge')
for file,identity in deep['files'].items():
 actual=SOURCE/'frontend/node_modules/deepmerge'/file
 assert record(actual)['sha256']==identity['repaired_sha256'],file
out={'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'head':sh('git','rev-parse','HEAD'),'branch':sh('git','branch','--show-current'),'status':sh('git','status','--short'),'node_version':subprocess.check_output([str(NODE),'--version'],text=True).strip(),'node_binary':record(NODE),'candidate_files':{f:record(SOURCE/f) for f in files},'installed_minimatch':installed,'legacy_minimatch_lock':legacy,'modern_minimatch_lock':modern,'minimatch_declared_callers':callers,'deepmerge_inventory_matches':deep}
(ROOT/'source-binding.json').write_text(json.dumps(out,indent=2)+'\n')
print('HEAD',out['head'],'branch',out['branch'])
for k,v in out['candidate_files'].items():print(v['sha256'],k)
print('installed fixture identity',[(k,v['same_fixture_bytes'])for k,v in installed.items()])

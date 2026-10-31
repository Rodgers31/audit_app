from pathlib import Path
import json,hashlib
p=Path(__file__).resolve().parent
root=Path('/Users/roger/.codex/worktrees/admin-social-release-check/audit_app')
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
x=json.loads((p/'final-2.json').read_text());exit=json.loads((p/'final-2.exit.json').read_text())
if exit['exit_code']!=0 or not x['success'] or x['numPassedTests']!=105 or x['numFailedTests']!=0 or x['numPendingTests']!=0:raise RuntimeError('Final run not exact all-green105')
cases=[];suite_counts={}
for suite in x['testResults']:
 if suite['status']!='passed':raise RuntimeError('Suite did not pass')
 suite_counts[suite['name']]=len(suite['assertionResults'])
 for c in suite['assertionResults']:
  if c['status']!='passed':raise RuntimeError('Non-passing case')
  cases.append({'suite':suite['name'],'title':c['fullName'],'outcome':c['status'],'duration_ms':c.get('duration')})
if len(cases)!=105 or len({(c['suite'],c['title'])for c in cases})!=105:raise RuntimeError('Missing or duplicate case identity')
independent=[c for c in cases if c['suite']=='/evidence/retry-adversarial.test.tsx']
if len(independent)!=60:raise RuntimeError('Wrong independent count')
integration=[c for c in independent if c['title'].startswith('actual Overview + QueryClient + actual Axios adapter')]
if len(integration)!=5:raise RuntimeError('Wrong actual overview count')
manifest=json.loads((p/'final-2-source-manifest.json').read_text());source_bad=[];checkout_bad=[]
for name,d in manifest.items():
 if sha(p/'source-final-2'/name)!=d:source_bad.append(name)
 if sha(root/name)!=d:checkout_bad.append(name)
if source_bad or checkout_bad:raise RuntimeError('Source drift: '+repr([source_bad,checkout_bad]))
(p/'CASE-LEDGER.json').write_text(json.dumps(cases,indent=2));(p/'SOURCE-AFTER.json').write_text(json.dumps({'files_verified':len(manifest),'frozen_mismatches':source_bad,'checkout_mismatches':checkout_bad,'axios_sha256':manifest['frontend/lib/api/axios.ts'],'test_sha256':manifest['frontend/__tests__/lib/api/retryAfter.test.ts']},indent=2))
cleanup=json.loads((p/'cleanup.json').read_text());runtime=json.loads((p/'runtime.json').read_text())
if cleanup['query_exit_code']!=0 or cleanup['remaining_owned_container_names']:raise RuntimeError('Owned cleanup incomplete')
if runtime['exit_code']!=0:raise RuntimeError('Runtime check failed')
versions=json.loads(runtime['stdout'])
if versions!={'node':'v24.22.1','arch':'x64','platform':'linux','axios':'1.20.0'}:raise RuntimeError('Unexpected runtime')
findings={'S1':{'final_classification':'REFUTED as an application strict-input defect under locked Axios1.20.0','initial_observation':'Raw LF/CRLF adapter response objects caused bounded retries, contradicting an incorrect raw-byte refusal expectation','executed_causal_result':'Axios sanitizes response headers before the application interceptor; both raw object and mutated AxiosHeaders variants normalize to valid numeric1','preserved_rejected_hypotheses':['run-3:2failed/98passed','final:4failed/98passed','sanitizer-probe:2failed/2passed (class-instance raw refusal expectation also wrong)'],'final_contract':'Normalized-valid1 recovers in2bounded attempts; values remaining malformed after normalization are refused. Defensive CR/LF check retained without raw-byte acceptance claim.'}}
(p/'FINDINGS.json').write_text(json.dumps(findings,indent=2))
files=['CASE-LEDGER.json','SOURCE-AFTER.json','FINDINGS.json','final-2-source-identity.json','final-2-source-manifest.json','final-2.command.json','final-2.exit.json','final-2.json','final-2.txt','retry-adversarial.test.tsx','jest.config.cjs','axios-runtime-identity.json','runtime.json','cleanup.json','run-1.command.json','run-1.exit.json','run-1.txt','run-2.json','run-2.txt','run-3.json','run-3.txt','initial-findings.json','header-probes.jsonl','final.json','final.txt','final-header-probes.jsonl','sanitizer-probe.test.ts','sanitizer-probe.json','sanitizer-probe-values.json','final-2-header-probes.jsonl','retry-adversarial.raw-refusal-hypothesis.tsx.bytes']
receipt={'verdict':'SCOPED FRONTEND ACCEPTANCE; no remaining confirmed finding','source':json.loads((p/'final-2-source-identity.json').read_text()),'execution':{'total':105,'independent':60,'repository':45,'passed':105,'failed':0,'skipped':0,'exit_code':exit['exit_code'],'wall_seconds':exit['seconds'],'suite_counts':suite_counts,'overview_integration_cases':integration},'runtime':versions,'docker_image':'sha256:e1582112fb9f152ed38eefcd712efc93fee1becb519fdfa57574d5e07eaa5e7d','caps':{'cpus':1,'memory':'1g','pids':256,'network':'none','source':'readonly','dependencies':'readonly'},'findings':findings,'source_after':{'files':len(manifest),'frozen_mismatches':source_bad,'checkout_mismatches':checkout_bad},'cleanup':cleanup,'scope_limits':['Actual Axios custom adapter and controlled Supabase session ports; no real HTTP transport/provider','Actual Overview, QueryClient and decoders in JSDOM; no browser layout claim','Backend fixes, source-monitor results and production recovery not certified','No project source/test edits, shared-container changes, provider/prod calls or activation'],'artifact_sha256':{name:sha(p/name)for name in files}}
(p/'FINAL-RECEIPT.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({'verdict':receipt['verdict'],'total':len(cases),'independent':len(independent),'integration':len(integration),'source_files_verified':len(manifest),'checkout_mismatches':checkout_bad,'remaining_owned':cleanup['remaining_owned_container_names']},indent=2))

from pathlib import Path
import json,hashlib,subprocess,xml.etree.ElementTree as ET,shutil
P=Path(__file__).resolve().parent;ROOT=P.parent;PROJECT=Path('/Users/roger/.codex/worktrees/admin-social-release-check/audit_app');sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
pins=json.loads((P/'input-pins.json').read_text());after={}
for name,h in pins['files'].items():
 if sha(P/name)!=h or sha(ROOT/name)!=h:raise RuntimeError('Input changed '+name)
 after[name]=h
old=ROOT.parent/'pr861-pr862-review-deploy-20261031/merge_guard.py'
expected=old.read_text().replace('pr not in (861, 862)','pr not in (863,)').replace('choices=(861, 862)','choices=(863,)')
if expected!=(P/'merge_guard.py').read_text():raise RuntimeError('Unexpected helper delta')
allcases=[]
for label,opt in [('merge-normal',0),('merge-optimized',1)]:
 r=json.loads((P/(label+'-result.json')).read_text());e=json.loads((P/(label+'.exit.json')).read_text());traces=json.loads((P/(label+'-traces.json')).read_text())
 if r!={'mode':opt,'tests':50,'failures':0,'errors':0,'skipped':0,'external_calls':0}or e['exit_code']!=0 or len(traces)!=50:raise RuntimeError('Unexpected matrix result '+label)
 if len({t['case']for t in traces})!=50 or any(t['actual_external_calls']!=0 for t in traces):raise RuntimeError('Bad matrix trace')
 allcases.extend([dict(t,mode=label)for t in traces])
proof=json.loads((P/'assertion-runner-results.json').read_text());counts=[]
for name in ['run_review.py','run_final_review.py','run_canonical_affected.py']:
 tree=ET.parse(P/(name+'-assertions.xml'));nodes=tree.findall('.//testcase');failed=[n for n in nodes if n.find('failure')is not None];errors=[n for n in nodes if n.find('error')is not None]
 if len(nodes)!=3 or len(failed)!=2 or errors or any(n.find('skipped')is not None for n in nodes):raise RuntimeError('Unexpected assertion canary result')
 if not all('assert' in n.find('failure').text.lower() for n in failed):raise RuntimeError('Failure was not intended assertion')
 counts.append({'runner':name,'actual_cases':3,'expected_failed_assertions':2,'runtime_canary_passed':1,'child_exit':1})
if len(proof['records'])!=3 or any(r['propagated_exit']!=1 or r['actual_docker_or_gh_calls']!=0 for r in proof['records']):raise RuntimeError('Runner did not propagate canary failure')
plain=ET.parse(P/'plain-negative-calibration.xml').findall('.//testcase')
if len(plain)!=3 or any(n.find('failure')is not None or n.find('error')is not None for n in plain):raise RuntimeError('Plain negative calibration not observed')
runnerpins=json.loads((P/'historical-runner-pins.json').read_text());runner_after={}
for name,h in runnerpins.items():
 rel='docs/releases/overview-source-health-20261031/standards/'+name
 committed=subprocess.check_output(['git','show','253ab29978fdb546b001381861eb767fe84b633f:'+rel],cwd=PROJECT)
 if hashlib.sha256(committed).hexdigest()!=h or sha(PROJECT/rel)!=h or sha(P/'historical-runners'/name)!=h:raise RuntimeError('Historical runner source changed '+name)
 runner_after[name]=h
disposition=PROJECT/'docs/releases/overview-source-health-20261031/review-20261031/REVIEW.md';shutil.copyfile(disposition,P/'REVIEWED-DISPOSITION.md')
(P/'CASE-LEDGER.json').write_text(json.dumps(allcases,indent=2));(P/'SOURCE-AFTER.json').write_text(json.dumps({'merge_helper_and_census':after,'historical_runners':runner_after,'historical_runners_match_committed_head':'253ab29978fdb546b001381861eb767fe84b633f','allowlist_is_only_helper_delta':True,'reviewed_disposition_sha256':sha(P/'REVIEWED-DISPOSITION.md')},indent=2))
cmd=['docker','ps','-a','--filter','name=pr863-spec-','--format','{{.Names}}'];r=subprocess.run(cmd,capture_output=True,text=True)
if r.returncode!=0 or r.stdout.splitlines():raise RuntimeError('Owned cleanup incomplete')
(P/'CLEANUP.json').write_text(json.dumps({'command':cmd,'exit_code':r.returncode,'remaining_owned':r.stdout.splitlines(),'external_gh_calls':0,'shared_resources_touched':False,'credential_files_created':0},indent=2))
files=[x for x in P.rglob('*')if x.is_file()and x.name not in ['FINAL-RECEIPT.json','REPORT.md']and '__pycache__'not in x.parts]
receipt={'verdict':'SCOPED PASS:merge coordinator controls accepted;optimized assertion hypothesis refuted','review_head':'253ab29978fdb546b001381861eb767fe84b633f','merge_helper_sha256':pins['files']['merge_guard.py'],'helper_delta':'Only PR allowlist861/862→863 at validation and argparse','merge_controls':{'normal':50,'true_optimized':50,'passed':100,'failed':0,'skipped':0,'actual_GitHub_calls':0,'initial_vs_late_bad_states':19},'assertion_disposition':{'classification':'REFUTED for exact default pytest collected-module command shapes and same-module helpers','independent_exact_argv_builders':3,'actual_expected_canary_outcomes':counts,'deliberate_plain_negative_calibration':{'passed_false_green_cases':3,'credited_validation_pass':False},'peer_evidence':'Standards70outcomes read/parsed only; not counted as own execution','limits':'No guarantee for ordinary unrewritten imported-module assertions; no full backend suites rerun here'},'live_verification_disposition':'Valid upcoming deployment gate; offline artifacts do not certify live provider/cold-cache transitions','source_after':'SOURCE-AFTER.json','cleanup':'CLEANUP.json','preserved_attempt':'attempt-1-draft-fixture:captured actual draft state correctly refused; synthetic ready baseline corrected, no product defect','artifact_sha256':{str(f.relative_to(P)):sha(f)for f in files}}
(P/'FINAL-RECEIPT.json').write_text(json.dumps(receipt,indent=2));print(json.dumps({'verdict':receipt['verdict'],'helper_sha256':receipt['merge_helper_sha256'],'matrix_controls':receipt['merge_controls'],'assertion_shapes':3,'cleanup':r.stdout.splitlines()},indent=2))

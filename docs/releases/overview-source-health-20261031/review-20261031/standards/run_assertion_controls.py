"""Execute retained Docker/Python shapes with isolated negative selections/output."""
from pathlib import Path
import json,subprocess,time
E=Path(__file__).resolve().parent;OLD=E.parent.parent/'overview-source-health-20261031/standards'
shapes={'run_review.py':'candidate-1-normal-command.json','run_final_review.py':'candidate-2-optimized-command.json','run_canonical_affected.py':'canonical-affected-optimized-command.json'}
plans=[('c1-canary','run_review.py',['/evidence/test_optimization_canary.py'],1),('c2-canary','run_final_review.py',['/evidence/test_optimization_canary.py'],1),('canonical-canary','run_canonical_affected.py',['/evidence/test_optimization_canary.py'],1),('original31','run_final_review.py',['/evidence/test_optimization_canary.py::test_runtime_is_optimized_and_test_module_is_rewritten','/evidence/baseline/test_backend_independent.py'],0),('wrong27','run_final_review.py',['/evidence/test_optimization_canary.py::test_runtime_is_optimized_and_test_module_is_rewritten','/evidence/mutant/test_backend_independent.py'],1)]
for label,runner,selection,want in plans:
 cmd=json.loads((OLD/shapes[runner]).read_text());cmd[cmd.index('--name')+1]='pr863-standards-'+label
 for i,value in enumerate(cmd):
  if value==str(OLD)+':/evidence':cmd[i]=str(E)+':/evidence'
 py=cmd.index('python')
 if cmd[py+1]!='-O':cmd.insert(py+1,'-O')
 if cmd[py+1:py+4]!=['-O','-m','pytest']:raise RuntimeError('Unexpected retained Python shape')
 cmd=cmd[:py+4]+['-q','-p','no:cacheprovider',*selection,'--junitxml=/evidence/'+label+'.xml']
 cmd[cmd.index('-v'):cmd.index('-v')]=['-e','ASSERTION_PROBE_LABEL='+label]
 (E/(label+'-command.json')).write_text(json.dumps({'argv':cmd,'retained_runner':runner,'retained_command_receipt':shapes[runner],'expected_exit':want,'changes':'Container name/output directory/test selection plus inert metadata-label environment; -O added exactly as run_review --optimized does for its recorded normal command.'},indent=2)+'\n');started=time.monotonic()
 with (E/(label+'.txt')).open('wb') as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
 (E/(label+'-execution.json')).write_text(json.dumps({'exit':r.returncode,'expected_exit':want,'seconds':time.monotonic()-started},indent=2)+'\n');print(label,r.returncode,'expected',want,flush=True)
 if r.returncode!=want:raise SystemExit('Unexpected assertion-control verdict')

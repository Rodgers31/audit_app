import hashlib
import importlib.util
import json
import platform
import subprocess
import sys
from pathlib import Path
sys.dont_write_bytecode=True
root=Path('/Users/roger/.codex/visualizations/2026/10/10/01a12626-6d17-7a30-a5ea-1462a6883004/batch11-navigation/review-standards')
output=root/'focused-review'
checkout=Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
checker=checkout/'docs/admin/implementation/batch11-issue-607-evidence/tools/verify_packet.py'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
inputs=[Path(__file__),root/'browser_replay_review.py',root/'runtime-review.js',root/'config-readback.js',output/'runtime.log',output/'container.json',output/'config-readback.log',output/'replay/receipt.json',output/'replay/report.json',output/'replay/console.log',checker]
before={str(p):sha(p) for p in inputs}
receipt=json.loads((output/'replay/receipt.json').read_text())
assert receipt['head']=='6fcaed18327d4ebdb91b475c016d81ca624deda8' and receipt['tree']=='958d72062130267d0916ad14f9ab7ab6afb0af71'
assert receipt['child_exit']==0 and receipt['timed_out'] is False and receipt['source_changed']==[]
assert subprocess.check_output(['git','rev-parse','HEAD','HEAD^{tree}'],cwd=checkout,text=True).splitlines()==[receipt['head'],receipt['tree']]
assert subprocess.check_output(['git','status','--porcelain'],cwd=checkout,text=True)==''
paths=subprocess.check_output(['git','ls-files','-z'],cwd=checkout).decode().strip('\0').split('\0')
assert set(paths)==set(receipt['source_hashes'])
assert all(sha(checkout/p)==h for p,h in receipt['source_hashes'].items())
module_spec=importlib.util.spec_from_file_location('standards_focused_postprocess',checker)
module=importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(module)
report=module.load(output/'replay/report.json')
measured,counts=module.cases(report)
assert len(measured)==6 and counts=={'expected':6,'unexpected':0,'skipped':0,'flaky':0}
config=json.loads((output/'config-readback.log').read_text())
assert config['workers']==2 and config['retries']==0 and config['viewport']=={'width':1280,'height':720}
assert config['configSha256']==receipt['source_hashes']['frontend/playwright.ci-cohorts.config.ts']
assert report['config']['metadata']['actualWorkers']==2
runtime=json.loads((output/'runtime.log').read_text())
assert runtime['nodeVersion']=='v22.23.3' and runtime['playwrightVersion']=='1.58.2' and runtime['browserVersion']=='145.0.7632.6'
assert all(sha(Path(p))==h for p,h in before.items())
result={'head':receipt['head'],'tree':receipt['tree'],'source_hashes':receipt['source_hashes'],'source_changed':[],'producer_argv':sys.argv,'inputs_before':before,'inputs_after':{p:sha(Path(p)) for p in before},'portable_child_exit':receipt['child_exit'],'portable_command':receipt['command'],'portable_generator_sha256':receipt['generator_sha256'],'runtime':runtime,'resolved_config':config,'focused_counts':counts,'actual_workers':report['config']['metadata']['actualWorkers'],'retry_indices':[result['retry'] for spec,_ in measured for test in spec['tests'] for result in test['results']],'postprocessor_child_exit':0,'original_outer_wrapper_exit':1,'outer_wrapper_error_classification':'Post-run metadata KeyError: the Playwright JSON reporter omits project.use. Six real cases and the supported portable helper completed successfully; this consumes their preserved bytes without rerunning them.','scope':'Independent fresh focused6 passes; full behavioral acceptance remains false316/2/11; #601 unresolved; no hosted or production acceptance','host_runtime':{'executable':sys.executable,'executable_sha256':sha(sys.executable),'version':sys.version,'platform':platform.platform()}}
with (output/'review-receipt.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
assert json.loads((output/'review-receipt.json').read_text())==result
print(json.dumps({k:result[k] for k in ['head','tree','source_changed','focused_counts','actual_workers','retry_indices','portable_child_exit','postprocessor_child_exit','original_outer_wrapper_exit','scope']}))

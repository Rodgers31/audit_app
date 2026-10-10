"""Execute unmodified production-config cohorts in this lane's owned namespace.
The original runner's fixture/config/env is retained; only Docker ownership and
report destinations are adapted. This generator is an archival invocation.
"""
import json, subprocess, sys
from pathlib import Path
OUT=Path(__file__).resolve().parent/'full-current'
OUT.mkdir()
root=Path('/Users/roger/.codex/worktrees/batch11-county-navigation/audit_app')
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
inv=json.loads((OUT.parent/'current-inventory.json').read_text())
rows=[]
for cohort in inv['cohorts']:
 name=cohort['name']
 command=['docker','exec','batch11-navigation-linux','env','-i','PATH=/opt/b11/node-v22.23.3-linux-x64/bin:/opt/b11/python/bin:/usr/local/bin:/usr/bin:/bin','HOME=/evidence/home','PLAYWRIGHT_BROWSERS_PATH=/ms-playwright','BROWSER_TEST_PYTHON=/opt/b11/python/bin/python','BROWSER_TEST_COHORT='+name,'BROWSER_TARGET_SHA='+head,'CI=true','PLAYWRIGHT_JSON_OUTPUT_FILE=/evidence/full-current/'+name+'-report.json','node','node_modules/@playwright/test/cli.js','test','--config','playwright.ci-cohorts.config.ts','--project=chromium','--output','/evidence/full-current/'+name+'-output','--reporter=list,json']
 print('START '+name,flush=True)
 with (OUT/(name+'.log')).open('x') as log:
  p=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=1000)
 validator="import fs from 'node:fs';import {executionPassed} from './scripts/ci-browser-cohorts.mjs';const inv=JSON.parse(fs.readFileSync('/evidence/current-inventory.json'));const c=inv.cohorts.find(c=>c.name===process.argv[1]);const r=JSON.parse(fs.readFileSync('/evidence/full-current/'+c.name+'-report.json'));const ok=executionPassed(r,c.cases,Number(process.argv[2]));console.log(JSON.stringify({passed:ok,stats:r.stats}));process.exitCode=ok?0:1;"
 check=subprocess.run(['docker','exec','batch11-navigation-linux','env','-i','PATH=/opt/b11/node-v22.23.3-linux-x64/bin:/usr/bin:/bin','HOME=/evidence/home','node','--input-type=module','-e',validator,name,str(p.returncode)],capture_output=True,text=True,timeout=60)
 row={'cohort':name,'command':command,'child_exit':p.returncode,'verification_exit':check.returncode,'stdout':check.stdout,'stderr':check.stderr}
 rows.append(row)
 (OUT/(name+'-receipt.json')).write_text(json.dumps(row,indent=2)+'\n')
 print('END '+name+' '+check.stdout.strip(),flush=True)
 if check.returncode:break
passed=len(rows)==6 and all(r['verification_exit']==0 for r in rows)
(OUT/'summary.json').write_text(json.dumps({'scope':'local Linux AMD64 Docker Desktop emulation; no hosted/production acceptance','total':inv['total'],'original':inv['originalTotal'],'cohorts':rows,'passed':passed},indent=2)+'\n')
sys.exit(0 if passed else 1)

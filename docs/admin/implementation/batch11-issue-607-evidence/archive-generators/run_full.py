"""Run the six unchanged production-config cohorts against this lane's owned DB.

Only resource ownership differs from run-legacy-e2e.mjs: PostgreSQL was started
by the host in the browser container's network namespace, using internal 55494.
This adapter does not edit or replace any application, fixture, test or config.
"""
import json
from pathlib import Path
import subprocess
import shutil
import sys

ROOT = Path(__file__).resolve().parent
FRONTEND = Path('/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app/frontend')
OUT = ROOT / 'full-original'
OUT.mkdir()
inventory = json.loads((FRONTEND / 'legacy-results/inventory.json').read_text())
(OUT / 'inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
results = []
for cohort in inventory['cohorts']:
    name = cohort['name']
    output = FRONTEND / 'legacy-results' / name
    if output.exists():
        shutil.copytree(output, OUT / (name + '-inherited'))
        shutil.rmtree(output)
    command = ['docker', 'exec', '-e', 'BROWSER_TEST_PYTHON=/opt/batch10-scroll-python/bin/python',
               '-e', 'BROWSER_TEST_COHORT=' + name,
               '-e', 'BROWSER_TARGET_SHA=' + inventory['target_commit'], 'batch10-scroll-linux',
               'node', 'node_modules/@playwright/test/cli.js', 'test',
               '--config', 'playwright.ci-cohorts.config.ts', '--project=chromium']
    print('START ' + name, flush=True)
    with (OUT / (name + '.log')).open('x') as log:
        child = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=1200)
    shutil.copytree(output, OUT / name)
    validator = "import fs from 'node:fs';import {executionPassed} from './scripts/ci-browser-cohorts.mjs';const inventory=JSON.parse(fs.readFileSync('/evidence/full-original/inventory.json'));const cohort=inventory.cohorts.find(c=>c.name===process.argv[1]);const report=JSON.parse(fs.readFileSync('legacy-results/'+cohort.name+'/results.json'));const passed=executionPassed(report,cohort.cases,Number(process.argv[2]));console.log(JSON.stringify({passed,stats:report.stats}));process.exitCode=passed?0:1;"
    check = subprocess.run(['docker', 'exec', 'batch10-scroll-linux', 'node', '--input-type=module',
                            '-e', validator, name, str(child.returncode)], capture_output=True, text=True)
    record = {'cohort': name, 'command': command, 'child_exit': child.returncode,
              'verification_exit': check.returncode, 'readback': check.stdout, 'error': check.stderr}
    results.append(record)
    with (OUT / (name + '-receipt.json')).open('x') as receipt:
        json.dump(record, receipt, indent=2)
    print('END ' + name + ' ' + check.stdout.strip(), flush=True)
    if check.returncode:
        break
with (OUT / 'summary.json').open('x') as summary:
    json.dump({'scope': 'local original Chromium cohorts; no hosted/deployed acceptance',
               'inventory_total': inventory['total'], 'cohorts': results,
               'passed': len(results) == len(inventory['cohorts']) and all(x['verification_exit'] == 0 for x in results)}, summary, indent=2)
sys.exit(0 if len(results) == len(inventory['cohorts']) and all(x['verification_exit'] == 0 for x in results) else 1)

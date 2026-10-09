"""Bind local executions to frozen source hashes; privately load owned fixture URL."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path('/Users/roger/.codex/worktrees/batch9-pr592-review/audit_app')
OUT=Path(__file__).parent
RUNTIMES={'current':'/Users/roger/Documents/projects/audit_app/venv/bin/python',
          'minimum':'/Users/roger/.codex/worktrees/a46a/audit_app/.batch9-min/bin/python'}
sys.path.insert(0,str(ROOT/'batch9-reconciliation-evidence'))
from receipt_safety import redact,public_environment,safety_hash


def main():
    label, runtime_name, *args=sys.argv[1:]
    runtime=RUNTIMES[runtime_name]
    private=json.loads((OUT/'private-fixture-env.json').read_text())
    env={'PATH':'/usr/bin:/bin:/usr/local/bin','PYTHON_DOTENV_DISABLED':'1','PYTHONDONTWRITEBYTECODE':'1',
         'PYTHONPATH':str(ROOT/'backend'), 'DATABASE_URL':private['BATCH9_RECONCILIATION_DATABASE_URL'], **private,
         'BATCH9_RECEIPT_RUNTIMES':json.dumps(list(RUNTIMES.values())),
         'BATCH9_SPEC_RECEIPT_PATH':str(OUT/(label+'-spec.md')),
         'BATCH9_STANDARDS_RECEIPT_PATH':str(OUT/(label+'-standards.md'))}
    names=subprocess.check_output(['git','diff','--name-only','b0ec603ccbf29d5ae7f6540faa3d484964334fb1'],cwd=ROOT,text=True).splitlines()
    names += ['backend/tests/test_batch9_reconciliation_receipts.py','batch9-reconciliation-evidence/receipt_safety.py']
    def hashes():return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in set(names) if (ROOT/name).is_file()}
    before=hashes()
    result=subprocess.run([runtime,*args],cwd=ROOT,env=env,capture_output=True,text=True)
    after=hashes()
    receipt={'generated_by':str(Path(__file__)), 'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'generated_at':datetime.now(timezone.utc).isoformat(),'target_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             'runtime':subprocess.check_output([runtime,'-c','import sys,sqlalchemy;print(sys.version);print(sqlalchemy.__version__)'],env=env,text=True),
             'command':[runtime,*args],'environment':public_environment(env),'receipt_safety_sha256':safety_hash(),
             'source_sha256_before':before,'source_sha256_after':after,'source_changed_during_run':before!=after,
             'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    receipt=redact(receipt,env)
    output=OUT/(label+'.json');assert not output.exists();output.write_text(json.dumps(receipt,indent=2)+'\n')
    assert json.loads(output.read_text())==receipt
    print(json.dumps({'receipt':str(output),'exit_code':result.returncode,'source_changed':before!=after,'stdout_tail':receipt['stdout'][-1500:],'stderr_tail':receipt['stderr'][-1000:]}))
    return result.returncode if before==after else 90


if __name__=='__main__':sys.exit(main())

import hashlib
import json
from pathlib import Path
import subprocess

REPO = Path('/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app')
OUT = Path(__file__).resolve().parent
EV = OUT.parent
docs = ['docs/admin/implementation/BATCH_10_SCROLL_HANDOFF.md', 'docs/admin/implementation/batch10-scroll-evidence/LESSONS.md', 'docs/admin/implementation/batch10-scroll-evidence/RUNTIME_CORRECTION.md']
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
before = {p:sha(REPO / p) for p in docs}
observations = []
for command in [ ['git','diff','--',*docs], ['file',str(EV / 'node22.bin'),str(EV / 'node22-amd64.bin')], ['node','docs/admin/implementation/batch10-scroll-evidence/verify.mjs'] ]:
    child = subprocess.run(command, cwd=REPO, text=True, capture_output=True, timeout=30)
    observations.append({'command':command,'child_exit':child.returncode,'stdout':child.stdout,'stderr':child.stderr})
    if child.returncode: raise RuntimeError('Failed correction control')
expected = 'fde6a4bf8d0562f7751d1a2d6cb9b417c4cfe107bbcb0aa3e9a24e125e348f48'
binaries = {n:sha(EV / n) for n in ['node22.bin','node22-amd64.bin']}
assert all(d == expected for d in binaries.values())
assert observations[1]['stdout'].count('ELF 64-bit LSB executable, x86-64,') == 2
after = {p:sha(REPO / p) for p in docs}
assert before == after
record = {'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),'scope':'Runtime correction docs pending follow-up commit, no modified archive/checker', 'source_before':before,'source_after':after,'source_changed':[], 'generator':str(Path(__file__)),'generator_sha256':sha(Path(__file__)),'retained_binary_sha256':binaries,'correction_receipt_sha256':sha(EV / 'node22-runtime-correction.json'),'observations':observations,'verification_exit':0,'not_executed':['container runtime checks (author receipt read only)', 'browser replay', 'build', 'publisher regeneration']}
destination=OUT / 'correction-review-v2-receipt.json'
with destination.open('x') as stream: json.dump(record,stream,indent=2)
assert json.loads(destination.read_text()) == record
print(json.dumps({'receipt':str(destination),'verification_exit':0,'readback_verified':True}))

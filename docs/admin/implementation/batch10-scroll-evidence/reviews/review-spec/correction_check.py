from pathlib import Path
import subprocess,json,hashlib
ROOT=Path('/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app')
OWN=Path(__file__).parent
SOURCE=ROOT/'docs/admin/implementation/batch10-scroll-evidence/RUNTIME_CORRECTION.md'
def sha(b):return hashlib.sha256(b).hexdigest()
before=sha(SOURCE.read_bytes())
checks=[['docker','image','inspect','sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392','--format','{{.Architecture}}'],['docker','exec','batch10-scroll-linux','/opt/batch10-scroll-node22/node','-p','JSON.stringify({node:process.version,platform:process.platform,arch:process.arch})'],['docker','exec','batch10-scroll-linux','/opt/batch10-scroll-node22-amd/node','-p','JSON.stringify({node:process.version,platform:process.platform,arch:process.arch})'],['docker','exec','batch10-scroll-linux','sha256sum','/opt/batch10-scroll-node22/node','/opt/batch10-scroll-node22-amd/node']]
outputs=[]
for command in checks:
 r=subprocess.run(command,capture_output=True,text=True,timeout=15)
 if r.returncode:raise RuntimeError(r.stderr)
 outputs.append(dict(command=command,child_exit=r.returncode,stdout=r.stdout,stderr=r.stderr))
assert outputs[0]['stdout'].strip()=='arm64'
for r in outputs[1:3]:
 v=json.loads(r['stdout']);assert v==dict(node='v22.23.3',platform='linux',arch='x64')
assert all(line.split()[0]=='fde6a4bf8d0562f7751d1a2d6cb9b417c4cfe107bbcb0aa3e9a24e125e348f48'for line in outputs[3]['stdout'].splitlines())
result=dict(generator_sha256=sha(Path(__file__).read_bytes()),correction_sha256=before,correction_changed_during_execution=before!=sha(SOURCE.read_bytes()),observations=outputs,conclusion='Correction is supported; original archived annotation remains historical and withdrawn.')
p=OWN/'correction-check.json'
with p.open('x')as f:json.dump(result,f,indent=2)
assert json.loads(p.read_text())==result
print(json.dumps({'correction_changed_during_execution':result['correction_changed_during_execution'],'checks':len(outputs),'conclusion':result['conclusion']}))

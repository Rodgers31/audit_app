import hashlib,json,os,subprocess,sys,time
from pathlib import Path
script,archive,manifest=sys.argv[1:]
inputs=[Path(script),Path(script).with_name('verify_bundle.py'),Path(archive),Path(manifest)]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before={str(p):sha(p) for p in inputs}
command=[sys.executable,*(['-O'] if sys.flags.optimize else []),script,archive,manifest]
print(json.dumps({'check':'actual-publication-inputs','producer_sha256':sha(Path(__file__)),'inputs':before,'command':command,'runtime':sys.version,'platform':sys.platform,'environment':dict(os.environ)}),flush=True)
result=subprocess.run(command,timeout=240)
after={str(p):sha(p) for p in inputs}
if before!=after:raise ValueError('publication inputs mutated')
print(json.dumps({'check':'actual-publication-readback','exit':result.returncode,'inputs':after,'sourceStable':True}),flush=True)
raise SystemExit(result.returncode)

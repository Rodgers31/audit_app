import hashlib,json,subprocess,sys,tarfile
from pathlib import Path
root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();sha=lambda b:hashlib.sha256(b).hexdigest()
extra=['.github/workflows/seed.yml','docs/admin/implementation/batch9-dependencies-evidence/control_contract.cjs','docs/admin/implementation/batch9-dependencies-evidence/run.cjs']
manifest=json.loads((out/'distribution-export/linux-final-source-manifest.json').read_bytes())
with tarfile.open(out/'linux-readonly-prerequisites.tar','x') as t:
 for p in extra:
  b=(root/p).read_bytes();assert b==subprocess.check_output(['git','show','bcb5ff99854de595bbe3f7d60cc8796b7ada5a20:'+p],cwd=root)
  t.add(root/p,arcname=p,recursive=False);manifest['files'][p]=sha(b)
manifest['previous_import_manifest_sha256']=sha((out/'distribution-export/linux-final-source-manifest.json').read_bytes())
manifest['prerequisite_archive_sha256']=sha((out/'linux-readonly-prerequisites.tar').read_bytes());manifest['prerequisite_producer_sha256']=sha(Path(__file__).read_bytes())
with (out/'linux-complete-source-manifest.json').open('x') as f:json.dump(manifest,f,indent=2)
print(json.dumps({'added_readonly_inputs':extra,'total_files':len(manifest['files'])}))

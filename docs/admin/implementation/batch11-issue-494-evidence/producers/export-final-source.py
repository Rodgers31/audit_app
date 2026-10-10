import hashlib,json,subprocess,sys,tarfile
from pathlib import Path
root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve()
sha=lambda b:hashlib.sha256(b).hexdigest()
paths=set(subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0'))|set(subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=root).decode().split('\0'))
selected=sorted(p for p in paths if p.startswith('frontend/') or p in ['docs/admin/implementation/batch10-dependencies-evidence/native-controls.mjs','docs/admin/implementation/batch10-dependencies-evidence/builder-init.mjs'])
files={p:sha((root/p).read_bytes()) for p in selected}
archive=out/'linux-final-source.tar'
with tarfile.open(archive,'x') as t:
 for p in selected:t.add(root/p,arcname=p,recursive=False)
if files!={p:sha((root/p).read_bytes()) for p in selected}:raise ValueError('source mutation')
manifest={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=root,text=True).strip(),'files':files,'archive_sha256':sha(archive.read_bytes()),'producer_sha256':sha(Path(__file__).read_bytes()),'classification':'UNCOMMITTED_CANDIDATE_SOURCE_IMPORT'}
with (out/'linux-final-source-manifest.json').open('x') as f:json.dump(manifest,f,indent=2)
baseline=out/'baseline-final/frontend';baseline.mkdir(parents=True)
for p in ['package.json','package-lock.json']:
 (baseline/p).write_bytes(subprocess.check_output(['git','show','bcb5ff99854de595bbe3f7d60cc8796b7ada5a20:frontend/'+p],cwd=root))
import shutil
shutil.copytree(root/'frontend/eslint-rules',baseline/'eslint-rules')
(baseline/'scripts').mkdir();shutil.copyfile(root/'frontend/scripts/tooling-repair-behavior.test.cjs',baseline/'scripts/tooling-repair-behavior.test.cjs')
with (out/'baseline-final/source.json').open('x') as f:json.dump({'pinned_head':'bcb5ff99854de595bbe3f7d60cc8796b7ada5a20','pinned_tree':'9d0061928c16d173859f98cb6daa5f2f591b257c','files':{p.relative_to(baseline).as_posix():sha(p.read_bytes()) for p in baseline.rglob('*') if p.is_file()},'behavior_fixture_sha256':sha((baseline/'scripts/tooling-repair-behavior.test.cjs').read_bytes())},f,indent=2)
print(json.dumps({'files':len(files),'archive_sha256':manifest['archive_sha256']}))

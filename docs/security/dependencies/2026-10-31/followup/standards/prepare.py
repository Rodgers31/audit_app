from pathlib import Path
import json,hashlib,urllib.request,tarfile,base64,shutil,datetime
r=Path('/Users/roger/.codex/worktrees/dependency-security-weekly/audit_app');o=Path(__file__).parent
lock=json.loads((r/'frontend/package-lock.json').read_text());manifest=json.loads((r/'frontend/scripts/tooling-repairs.json').read_text());inventory=next(x for x in manifest['packages'] if x['name']=='deepmerge');meta=lock['packages']['node_modules/deepmerge']
raw=urllib.request.urlopen(meta['resolved'],timeout=30).read();algorithm,b64=meta['integrity'].split('-',1)
if base64.b64encode(hashlib.new(algorithm,raw).digest()).decode()!=b64:raise RuntimeError('npm tar integrity mismatch')
(o/'deepmerge-4.3.1.tgz').write_bytes(raw)
original=o/'original';original.mkdir(exist_ok=False)
with tarfile.open(o/'deepmerge-4.3.1.tgz') as t:t.extractall(original,filter='data')
original=original/'package';files={str(p.relative_to(original)):hashlib.sha256(p.read_bytes()).hexdigest() for p in original.rglob('*') if p.is_file()}
if set(files)!=set(inventory['files']):raise RuntimeError('Incomplete original package inventory')
for name,h in files.items():
 if h!=inventory['files'][name]['original_sha256']:raise RuntimeError('Wrong original package hash '+name)
patched=o/'patched';shutil.copytree(original,patched)
for patch in (p for p in manifest['patches'] if p['package']=='deepmerge'):
 p=patched/patch['file'];s=p.read_text()
 for edit in patch['edits']:
  if s.count(edit['before'])!=1:raise RuntimeError('Ambiguous edit '+patch['file'])
  s=s.replace(edit['before'],edit['after'])
 p.write_text(s)
 if hashlib.sha256(p.read_bytes()).hexdigest()!=patch['repaired_sha256']:raise RuntimeError('Wrong generated patch hash')
pkg=json.loads((original/'package.json').read_text());helper_version=pkg['devDependencies']['is-mergeable-object'];print('main',pkg['main'],'module',pkg.get('module'),'helper',helper_version)
# The source index requires this genuine build helper; bundles contain its code.
helper_meta=json.load(urllib.request.urlopen('https://registry.npmjs.org/is-mergeable-object/'+helper_version,timeout=30));dist=helper_meta['dist'];raw=urllib.request.urlopen(dist['tarball'],timeout=30).read();alg,b64=dist['integrity'].split('-',1)
if base64.b64encode(hashlib.new(alg,raw).digest()).decode()!=b64:raise RuntimeError('Helper tar integrity mismatch')
(o/'is-mergeable-object.tgz').write_bytes(raw)
(o/'helper-metadata.json').write_text(json.dumps(helper_meta,indent=2)+'\n');helper_unpack=o/'helper-unpack';helper_unpack.mkdir()
with tarfile.open(o/'is-mergeable-object.tgz') as t:t.extractall(helper_unpack,filter='data')
for package in [original,patched]:
 dest=package/'node_modules/is-mergeable-object';dest.parent.mkdir();shutil.copytree(helper_unpack/'package',dest)
record={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'lock_integrity':meta['integrity'],'archive_sha256':hashlib.sha256((o/'deepmerge-4.3.1.tgz').read_bytes()).hexdigest(),'original_hashes':files,'helper_version':helper_version,'helper_integrity':dist['integrity'],'source_hashes':{p:hashlib.sha256((r/p).read_bytes()).hexdigest() for p in ['frontend/scripts/tooling-repairs.json','frontend/scripts/apply-tooling-repairs.cjs','frontend/scripts/deepmerge-boundary.test.cjs','frontend/scripts/tooling-repair-install.test.cjs','frontend/package.json','frontend/package-lock.json']}}
(o/'preparation.json').write_text(json.dumps(record,indent=2)+'\n');print('Exact npm tarball, all 11 package members, 3 repaired code entries and genuine helper verified')

"""Create one immutable retained-evidence packet from explicitly selected files."""
import hashlib,json,sys,zipfile
from pathlib import Path
root=Path(sys.argv[1]).resolve();destination=Path(sys.argv[2]).resolve()
sha=lambda b:hashlib.sha256(b).hexdigest()
if not destination.is_dir() or any(destination.iterdir()):raise ValueError('empty packet staging directory required')
selected={};receipts={}
def add(p,name):
 if p.is_symlink() or not p.is_file() or name in selected:raise ValueError('unsafe/duplicate member')
 selected[name]=p.read_bytes()
# Exactly the recorder's fresh root triples: other JSON observations are data.
for p in sorted(root.glob('*.json')):
 try:record=json.loads(p.read_bytes())
 except (ValueError,UnicodeError):continue
 if isinstance(record,dict) and record.get('generated_by')=='run.py' and record.get('schema')==1:
  name='commands/'+p.name;add(p,name)
  for suffix in ('.stdout','.stderr'):add(p.with_suffix(suffix),'commands/'+p.with_suffix(suffix).name)
  receipts[name]={k:record.get(k) for k in ('exit','source_stable','error')}
for name in ['run.py','linux-run.cjs','native-builder.cjs','baseline-child.cjs','preview.cjs','prepare-patches.py','revise-patches.py','repair-distribution.cjs','export-final-source.py','export-linux-prerequisites.py']:
 add(root/name,'producers/'+name)
add(Path(__file__),'producers/pack.py')
for p in sorted(root.iterdir()):
 if p.is_file() and p.suffix in ('.json','.css','.bin','.cjs','.py') and p.name not in [Path(n).name for n in selected]:add(p,'observations/'+p.name)
for directory in ['canonical-upstream','adversarial-review','adversarial-final','adversarial-distribution','standards-review','spec-review']:
 for p in sorted((root/directory).rglob('*')):
  if p.is_file():add(p,'reviews-and-upstream/'+p.relative_to(root).as_posix())
for directory in ['host-builder-distribution','distribution-export']:
 base=root/directory
 for p in sorted(base.rglob('*')):
  relative=p.relative_to(base).as_posix()
  if p.is_file() and not p.is_symlink() and 'node_modules/' not in relative and not relative.startswith('baseline-final/frontend/') and not relative.startswith('models/') and p.suffix in ('.json','.bin'):
   add(p,'observations/'+directory+'/'+relative)
for directory in ['baseline-install','baseline-install2']:
 for p in sorted((root/directory).glob('*')):
  if p.is_file() and p.suffix in ('.json','.stdout','.stderr'):add(p,'early-setup/'+directory+'/'+p.name)
for p in sorted((root/'packet-initial').iterdir()):
 if p.is_file():add(p,'early-publication/'+p.name)
archive=destination/'evidence-v1.zip'
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for name,data in sorted(selected.items()):z.writestr(name,data)
manifest={'schema':2,'classification':'HISTORICAL_PACKET_INTEGRITY','current_checkout_acceptance':False,'archive_sha256':sha(archive.read_bytes()),'members':{n:sha(b) for n,b in sorted(selected.items())},'receipts':receipts,'producer_sha256':sha(Path(__file__).read_bytes())}
with (destination/'evidence-v1.manifest.json').open('x') as f:json.dump(manifest,f,indent=2);f.write('\n')
print(json.dumps({'members':len(selected),'receipts':len(receipts),'bytes':archive.stat().st_size}))

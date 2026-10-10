"""Copy immutable producer bytes into the owned packet; never rebind history."""
import argparse,gzip,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--artifacts',type=Path,required=True);p.add_argument('--packet',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
def sha(raw):return hashlib.sha256(raw).hexdigest()
rows=[]
def copy(source,target,compress=False):
 if target.exists():return
 raw=source.read_bytes();target.parent.mkdir(parents=True,exist_ok=True)
 encoded=gzip.compress(raw,mtime=0) if compress else raw
 with target.open('xb') as f:f.write(encoded)
 assert (gzip.decompress(target.read_bytes()) if compress else target.read_bytes())==raw
 assert source.read_bytes()==raw
 rows.append({'input':source.relative_to(a.artifacts).as_posix(),'input_sha256':sha(raw),'output':target.relative_to(a.packet).as_posix(),'output_sha256':sha(encoded)})
for source in a.artifacts.iterdir():
 if not source.is_file() or source.is_symlink():continue
 if source.suffix in ['.json','.jsonl','.log','.txt','.diff','.md']:
  copy(source,a.packet/'archives'/(source.name+'.gz'),True)
 elif source.suffix in ['.py','.mjs','.js','.ts','.tsx']:
  copy(source,a.packet/'archive-generators'/source.name)
for name in ['probe-tests','probe-tests-v2','gated-tests','boundary-tests','pending-original-tests','controls-tests']:
 for source in (a.artifacts/name).rglob('*'):
  if source.is_file() and not source.is_symlink() and source.suffix in ['.ts','.js','.py','.mjs']:
   copy(source,a.packet/'archive-generators'/source.relative_to(a.artifacts))
for name in ['boundary-red-attempt2-output','contracts-before-fix-output','contracts-corrected-before-fix-output','pending-original-red-output','gated-original-40-output','full-current','full-current-attempt2','full-current-attempt3','full-current-attempt3-remaining','full-current-attempt3-remaining-attempt2','initial-render-launch-control-output','focused-green-rechecked-output','pending-original-green-rechecked-output','prior-coordinator-fixture']:
 for source in (a.artifacts/name).rglob('*'):
  if source.is_file() and not source.is_symlink():copy(source,a.packet/'archives'/(source.relative_to(a.artifacts).as_posix()+'.gz'),True)
with a.receipt.open('x') as f:json.dump({'generator_sha256':sha(Path(__file__).read_bytes()),'copies':rows},f,indent=2)
print(json.dumps({'copied':len(rows),'receipt':str(a.receipt)}))

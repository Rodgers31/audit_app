"""Append publication history and regenerate only the current manifest index."""
import gzip,hashlib,json,time
from pathlib import Path
ROOT=Path('/Users/roger/.codex/worktrees/batch10-etl-mappings/audit_app')
PACK=ROOT/'docs/admin/implementation/batch10-mappings-evidence'
OUT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(b)
 if p.read_bytes()!=b:raise RuntimeError('readback mismatch')
def gz(p,target):write(target,gzip.compress(p.read_bytes(),mtime=0))
original=gzip.decompress((PACK/'history/initial-publication-manifest.json.gz').read_bytes())
if (PACK/'manifest.json').read_bytes()!=original:raise RuntimeError('current index no longer initial')
manifest=json.loads(original)
write(PACK/'revise_package.py',Path(__file__).read_bytes())
review=OUT/'review-adversarial'
write(PACK/'history/packet_adversarial.py', (review/'packet_adversarial.py').read_bytes())
reds=[]
for directory in sorted(review.glob('packet-review-*')):
 if not (directory/'manifest.json').exists():continue
 data=json.loads((directory/'manifest.json').read_text())
 if data['verdict']!='FAIL':continue
 for p in directory.iterdir():
  if p.is_file():gz(p,PACK/'history/packet-review-red'/directory.name/(p.name+'.gz'))
 reds.append({'receipt':'history/packet-review-red/'+directory.name+'/manifest.json.gz','status':'HISTORICAL_SUPERSEDED','reason':'Actual bool-schema, duplicate/pruned-cohort and hidden JUnit failure false-green reproduced; current verifier repairs these guards.'})
if not reds:raise RuntimeError('missing actual red execution')
publication={'generated_by':'revise_package.py','generator_sha256':sha(Path(__file__)),'generated_at':time.time(),'initial_manifest_sha256':hashlib.sha256(original).hexdigest(),'initial_verifier_sha256':hashlib.sha256(gzip.decompress((PACK/'history/initial-publication-verifier.py.gz').read_bytes())).hexdigest(),'initial_status':'HISTORICAL_SUPERSEDED','reason':'Verifier guard repair only. Original four execution receipts, raw logs, original sources and failed diagnostics remain byte-for-byte preserved. Canonical manifest.json is the current publication index.','red_controls':reds}
write(PACK/'publication-history.json',(json.dumps(publication,indent=2)+'\n').encode())
name='backend/tests/test_batch10_etl_mappings_package_guards.py'
manifest['source_sha256'][name]=sha(ROOT/name)
manifest['source_sha256']['docs/admin/implementation/batch10-mappings-evidence/verify_package.py']=sha(PACK/'verify_package.py')
for name,expected in manifest['source_sha256'].items():
 if sha(ROOT/name)!=expected:raise RuntimeError('substantive source drift '+name)
manifest.update({'generated_by':'revise_package.py','generator_sha256':sha(Path(__file__)),'generated_at':time.time(),'previous_publication_sha256':hashlib.sha256(original).hexdigest(),'publication_history':'publication-history.json'})
manifest['assets_sha256']={str(p.relative_to(PACK)):sha(p) for p in PACK.rglob('*') if p.is_file() and p.name!='manifest.json'}
body=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
(PACK/'manifest.json').write_bytes(body)
if (PACK/'manifest.json').read_bytes()!=body:raise RuntimeError('current index readback mismatch')
print(json.dumps({'sources':len(manifest['source_sha256']),'assets':len(manifest['assets_sha256']),'preserved_red_runs':len(reds)}))

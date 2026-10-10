"""Publish immutable actual executions; refuse an existing published package."""
import gzip,hashlib,json,shutil,tarfile,time
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path('/Users/roger/.codex/worktrees/batch10-etl-mappings/audit_app')
OUT=Path(__file__).resolve().parent
PACK=ROOT/'docs/admin/implementation/batch10-mappings-evidence'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(b)
 if p.read_bytes()!=b:raise RuntimeError('readback mismatch')
def encode(v):return (json.dumps(v,indent=2,sort_keys=True)+'\n').encode()
def gz(p,target):write(target,gzip.compress(p.read_bytes(),mtime=0))
if (PACK/'manifest.json').exists():raise RuntimeError('published package exists')
active=['cohort-current-repaired','cohort-minimum-final','legacy-current-repaired','legacy-minimum-repaired']
records={n:json.loads((OUT/(n+'.json')).read_text()) for n in active}
# Original measured identities are retained unchanged; portable records bind the
# exact executable inventory consumed by the cohorts, excluding unrelated assets.
source={str(p.relative_to(ROOT)):sha(p) for folder in ('backend','etl') for p in (ROOT/folder).rglob('*.py') if '__pycache__' not in p.parts}
source.update({n:sha(ROOT/n) for n in next(iter(records.values()))['source_before'] if n.endswith('.py') and not n.startswith('docs/admin/implementation/batch10-mappings-evidence/')})
source.update({n:sha(ROOT/n) for n in ('backend/alembic.ini','backend/pytest.ini','backend/requirements.txt','backend/requirements-dev.txt') if (ROOT/n).is_file()})
source['docs/admin/implementation/batch10-mappings-evidence/verify_package.py']=sha(PACK/'verify_package.py')
checks=[]
for n,r in records.items():
 if r['child_exit']!=0 or not r['source_stable']:raise RuntimeError('failed current execution '+n)
 names={k:v for k,v in r['source_before'].items() if k in source}
 if not names or any(source[k]!=h for k,h in names.items()):raise RuntimeError('current source drift '+n)
 if any(k not in names for k in source if k != 'docs/admin/implementation/batch10-mappings-evidence/verify_package.py'):raise RuntimeError('missing measured source '+n)
 raw=Path(r['log']);gen=Path(r['generated_by'])
 if sha(raw)!=r['log_sha256'] or sha(gen)!=r['generator_sha256']:raise RuntimeError('execution asset drift '+n)
 log='runs/'+n+'.log.gz'; generator='generators/'+gen.name
 gz(raw,PACK/log)
 if not (PACK/generator).exists():write(PACK/generator,gen.read_bytes())
 driver=OUT/('run_cohort_v2.py' if n.startswith('cohort') else 'run_legacy_v2.py')
 if not (PACK/'generators'/driver.name).exists():write(PACK/'generators'/driver.name,driver.read_bytes())
 junit='runs/'+n+'-junit.xml';xml=OUT/(n+'-junit.xml')
 write(PACK/junit,xml.read_bytes())
 suites=list(ET.parse(xml).getroot().iter('testsuite'))
 counts={key:sum(int(s.attrib.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
 if counts['tests']<=0 or any(counts[k] for k in ('failures','errors','skipped')):raise RuntimeError('non-green junit '+n)
 receipt={**r,'generated_by':generator,'generator':generator,'generator_sha256':sha(PACK/generator),'log':log,'log_sha256':sha(PACK/log),'raw_log_sha256':r['log_sha256'],'junit':junit,'junit_sha256':sha(PACK/junit),'counts':counts,'source_before':names,'source_after':{k:r['source_after'][k] for k in names},'original_receipt':'history/'+n+'.json.gz','publication_generator':'build_package.py','publication_generator_sha256':sha(Path(__file__))}
 target='receipts/'+n+'.json';write(PACK/target,encode(receipt)); checks.append({'receipt':target,'expected_exit':0})
# Preserve every root execution receipt and its exact raw output, including setup
# failures and intermediate greens; historical status is a separate index.
history=[]
for p in sorted(OUT.glob('*.json')):
 try:r=json.loads(p.read_text())
 except ValueError:continue
 if not isinstance(r,dict) or 'child_exit' not in r:continue
 gz(p,PACK/'history'/(p.name+'.gz'))
 entry={'receipt':'history/'+p.name+'.gz','original_sha256':sha(p),'status':'CURRENT_EXECUTION_ORIGINAL' if p.stem in active else 'HISTORICAL_SUPERSEDED','reason':'Portable current record verifies executable sources; raw receipt is unchanged.' if p.stem in active else 'Retained actual baseline/red/setup/intermediate execution; no final acceptance inferred.'}
 log=p.with_suffix('.log')
 if log.exists():gz(log,PACK/'history'/(log.name+'.gz'));entry['log']='history/'+log.name+'.gz';entry['raw_log_sha256']=sha(log)
 history.append(entry)
write(PACK/'history-index.json',encode(history))
for name in ('record.py','record_v2.py','replay_baseline.py','replay_baseline_final.py','replay_baseline_mappings.py','run_cohort.py','run_cohort_v2.py','run_legacy.py','run_legacy_v2.py'):
 p=OUT/name
 if p.exists() and not (PACK/'generators'/name).exists():write(PACK/'generators'/name,p.read_bytes())
for name in ('issue-census-pages.json','issues-all.json','prs-all.json','issue-602-readback.json'):
 p=OUT/name
 if p.exists():gz(p,PACK/'routing'/(name+'.gz'))
p=OUT/'prerequisite-issue.md'
if p.exists():write(PACK/'routing'/p.name,p.read_bytes())
# Reviewer archives retain independent generators, controls, receipts and raw
# results; ephemeral caches/log storage are not evidence and are excluded.
for review in sorted(p for p in OUT.glob('review-*') if p.is_dir()):
 target=PACK/'review'/ (review.name+'.tar.gz');target.parent.mkdir(exist_ok=True)
 with target.open('xb') as f:
  with tarfile.open(fileobj=f,mode='w:gz') as archive:
   for p in sorted(review.rglob('*')):
    if p.is_file() and not any(part in ('tmp','pytest-temp','__pycache__','storage','cache','.pytest_cache') for part in p.relative_to(review).parts):archive.add(p,arcname=str(p.relative_to(OUT)))
write(PACK/'build_package.py',Path(__file__).read_bytes())
assets={str(p.relative_to(PACK)):sha(p) for p in PACK.rglob('*') if p.is_file() and p.name!='manifest.json'}
manifest={'schema':1,'generated_by':'build_package.py','generator_sha256':sha(Path(__file__)),'generated_at':time.time(),'source_sha256':source,'assets_sha256':assets,'checks':checks,'history_index':'history-index.json','limitations':'Local inert dispatch ownership acceptance only. Financial handlers, deployed role/UI acceptance, production reconciliation and activation remain pending.'}
write(PACK/'manifest.json',encode(manifest))
print(json.dumps({'checks':len(checks),'source_files':len(source),'assets':len(assets),'counts':{n:json.loads((PACK/('receipts/'+n+'.json')).read_text())['counts'] for n in active}}))

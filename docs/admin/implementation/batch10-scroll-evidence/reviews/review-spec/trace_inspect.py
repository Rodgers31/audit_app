import pathlib,gzip,json,zipfile,io,hashlib,subprocess,time
REPO=pathlib.Path('/Users/roger/.codex/worktrees/batch10-county-scroll/audit_app')
OWN=pathlib.Path(__file__).parent
DATA=REPO/'docs/admin/implementation/batch10-scroll-evidence/data'
def sha(b):return hashlib.sha256(b).hexdigest()
inputs=['historical-trace.zip.gz','node22-precondition-trace.zip.gz','node22-runtime.json.gz']
source={str(DATA/n):sha((DATA/n).read_bytes())for n in inputs}
records=[]
for n in inputs[:2]:
 raw=gzip.decompress((DATA/n).read_bytes());z=zipfile.ZipFile(io.BytesIO(raw))
 rows=[json.loads(x)for name in z.namelist()if name.endswith('.trace')for x in z.read(name).decode().splitlines()]
 failures=[r for r in rows if r.get('type')=='after'and r.get('error')and r['error'].get('stack')]
 scrolls=[r for r in rows if r.get('type')=='before'and'window.scrollTo'in str(r.get('params'))]
 numeric=[r for r in rows if r.get('type')=='after'and'n'in r.get('result',{}).get('value',{})]
 contexts=[r for r in rows if r.get('type')=='context-options'and r.get('origin')=='library']
 records.append(dict(archive=n,raw_sha256=sha(raw),contexts=contexts,assertion_failures=failures,scroll_calls=len(scrolls),numeric_evaluations=numeric))
runtime=json.loads(gzip.decompress((DATA/inputs[2]).read_bytes()))
binaries=OWN.parent
binary_checks=[]
for n in ['node22.bin','node22-amd64.bin']:
 p=binaries/n;b=p.read_bytes()
 diagnostic=subprocess.check_output(['file',str(p)],text=True)
 binary_checks.append(dict(path=str(p),sha256=sha(b),file_diagnostic=diagnostic))
source[str(pathlib.Path(__file__))]=sha(pathlib.Path(__file__).read_bytes())
result=dict(inspected_commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),source_hashes=source,traces=records,archived_runtime=runtime,retained_binary_checks=binary_checks,source_changed_during_read=[p for p,h in source.items()if sha(pathlib.Path(p).read_bytes())!=h])
print(json.dumps(result,indent=2))

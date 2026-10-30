"""Check COPY-MANIFEST archive bytes; this never reruns acceptance."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(root):
    manifest=json.loads((root/'COPY-MANIFEST.json').read_text())['files']
    mapping=json.loads((root/'logical-paths.json').read_text())
    index=json.loads((root/'index.json').read_text())
    if index['generator_sha256']!=sha(Path(__file__)):raise ValueError('Verifier/index provenance differs')
    if not manifest or set(manifest)!=set(mapping):raise ValueError('Incomplete logical inventory')
    actual=set()
    for p in root.rglob('*'):
        if p.is_symlink() or not(p.is_file() or p.is_dir()):raise ValueError('Nonregular member')
        if p.is_file() and p!=root/'index.json':actual.add(p.relative_to(root).as_posix())
    if actual!=set(index['files']):raise ValueError('Physical inventory differs')
    if {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_dir()}!=set(index['directories']):raise ValueError('Directory inventory differs')
    for name,entry in index['files'].items():
        p=root/name
        if p.stat().st_size!=entry['bytes'] or sha(p)!=entry['sha256']:raise ValueError('Packet member differs: '+name)
    for logical,digest in manifest.items():
        entry=mapping[logical];name=entry['path']
        if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('Unsafe path')
        if entry['sha256']!=digest or sha(root/name)!=digest:raise ValueError('Declared artifact differs: '+logical)
    counts={}
    for name in ['candidate8/final-phase-and-cli.xml','candidate8/final-prefix-exhaustion.xml','candidate8/final-optimized.xml']:
        cases=list(ET.parse(root/mapping[name]['path']).getroot().iter('testcase'))
        if not cases or any(any(c.find(k) is not None for k in ('failure','error','skipped')) for c in cases):raise ValueError('Nonpass final XML')
        counts[name]=len(cases)
    if counts['candidate8/final-phase-and-cli.xml']+counts['candidate8/final-prefix-exhaustion.xml']!=29 or counts['candidate8/final-optimized.xml']!=29:raise ValueError('Final29 identities incomplete')
    return dict(status='verified_archive',tests_rerun=False,listed_files=len(manifest),original_normal_cases=29,original_optimized_cases=29,generated_by='verify.py',generator_sha256=sha(Path(__file__)))
if __name__=='__main__':
    try:
        root=Path(__file__).resolve().parent
        if len(sys.argv)>1 and sys.argv[1]=='--publish':
            if (root/'index.json').exists():raise ValueError('Fresh index required')
            files={p.relative_to(root).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in root.rglob('*') if p.is_file()}
            value=dict(kind='copied_spec_originals',tests_rerun=False,generated_at=datetime.now(timezone.utc).isoformat(),generated_by='verify.py',generator_sha256=sha(Path(__file__)),files=files,directories=sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_dir()))
            (root/'index.json').write_text(json.dumps(value,indent=2)+'\n')
            if json.loads((root/'index.json').read_text())['generator_sha256']!=sha(Path(__file__)):raise ValueError('Index readback differs')
        print(json.dumps(verify(Path(sys.argv[1]).resolve() if len(sys.argv)>1 and sys.argv[1]!='--publish' else root),indent=2))
    except (ValueError,KeyError,OSError,ET.ParseError) as error:print(json.dumps(dict(status='refused',tests_rerun=False,reason=str(error))));sys.exit(1)

"""One-time archive index producer; copies have already been hash checked.

Refuses an existing index. Does not run acceptance tests or modify originals.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text())


def main(root, repo):
    if (root / 'index.json').exists(): raise ValueError('Fresh index required')
    receipt = load(root / 'original/FINAL7-RECEIPT.json')
    prior = load(root / 'original/RECEIPT.json')
    manifest = load(root / 'source/original-manifest.json')
    script = Path(__file__).resolve()
    bridge = dict(scope='Historical backend/seed workflow equality; not full-tree identity or a new acceptance run',
                  commit='d0da4996327213049614cd8f09b373bcaa856a23',
                  original_manifest_mapping_sha256=receipt['manifest_mapping_sha256'],
                  original_manifest_file_sha256=receipt['manifest_file_sha256'],
                  generated_by='tools/publish_index.py', generator_sha256=sha(script), source_files={})
    process = subprocess.Popen(['git','-c','safe.directory='+str(repo),'cat-file','--batch'], cwd=repo, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for name in sorted(n for n in manifest if n.startswith('backend/') or n == '.github/workflows/seed.yml'):
            process.stdin.write((bridge['commit']+':'+name+'\n').encode()); process.stdin.flush()
            head = process.stdout.readline().decode().strip().split()
            if len(head)!=3 or head[1]!='blob': raise ValueError('Historical Git source missing: '+name)
            size=int(head[2]); body=process.stdout.read(size)
            if process.stdout.read(1)!=b'\n' or hashlib.sha256(body).hexdigest()!=manifest[name]:
                raise ValueError('Historical Git source differs: '+name)
            bridge['source_files'][name]=dict(sha256=manifest[name],git_blob=head[0],bytes=size)
    finally:
        process.stdin.close(); process.wait()
    if process.returncode: raise ValueError('Git source read failed')
    bridge['source_file_count']=len(bridge['source_files'])
    bridge['source_bytes']=sum(v['bytes'] for v in bridge['source_files'].values())
    (root/'source/source-bridge.json').write_text(json.dumps(bridge,indent=2)+'\n')
    if load(root/'source/source-bridge.json')['generator_sha256']!=sha(script): raise ValueError('Bridge readback differs')
    declarations=[]
    def declare(owner,name,digest,role,folder='original'):
        path=folder+'/'+name+('.bytes' if name.endswith('.py') else '')
        if sha(root/path)!=digest: raise ValueError('Original bytes differ: '+path)
        declarations.append(dict(declared_by=owner+name,path=path,sha256=digest,role=role))
    for name,digest in receipt['artifacts_sha256'].items():
        role='original_harness_failure_not_acceptance' if '-initial' in name else 'original_final7_acceptance'
        declare('FINAL7.artifacts.',name,digest,role)
    for name,digest in receipt['imported_independent_fixtures_sha256'].items():
        declare('FINAL7.fixtures.',name,digest,'original_imported_fixture','fixtures')
    for name,digest in prior['artifacts_sha256'].items():
        declare('diagnostic.artifacts.',name,digest,'historical_diagnostic_not_final7_acceptance')
    declare('diagnostic.fixture.','test_cohort_guard.py',prior['imported_fixture_sha256'],'historical_fixture','fixtures')
    declare('FINAL7.reference.','RECEIPT.json',sha(root/'original/RECEIPT.json'),'prior_diagnostic_receipt')
    reference=[dict(declared_by='diagnostic.parent_production_read_only_receipt_sha256',
        sha256=prior['parent_production_read_only_receipt_sha256'],
        disposition='reference_only_not_bundled_not_a_FINAL7_test_input',
        reason='Historical parent production read-only context; this packet contains no production data dump.')]
    inventory={}
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or not(path.is_dir() or path.is_file()): raise ValueError('Nonregular publisher input')
        if path.is_file(): inventory[path.relative_to(root).as_posix()]=dict(sha256=sha(path),bytes=path.stat().st_size)
    index=dict(schema_version=1,kind='portable_original_evidence',tests_rerun=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
        generated_by=dict(path='tools/publish_index.py',sha256=sha(script)),
        verifier=dict(path='tools/verify_packet.py',sha256=sha(root/'tools/verify_packet.py')),
        original_receipt=dict(path='original/FINAL7-RECEIPT.json',sha256=sha(root/'original/FINAL7-RECEIPT.json')),
        original_scope='Frozen candidate7 / d0 backend: 74 tests; not current phase-repair acceptance',
        declarations=declarations,reference_only=reference,
        packet_files=inventory,packet_directories=sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_dir()))
    target=root/'index.json';target.write_text(json.dumps(index,indent=2)+'\n')
    again=load(target)
    if again['generated_by']['sha256']!=sha(script) or again['tests_rerun'] is not False: raise ValueError('Index provenance readback differs')
    print(json.dumps(dict(status='published_archive_index',tests_rerun=False,files=len(inventory),declarations=len(declarations))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--repo',type=Path,required=True)
    args=parser.parse_args();main(args.packet.resolve(),args.repo.resolve())

"""Relocated positive and hostile archive-verifier controls; no acceptance replay."""
import hashlib,json
from pathlib import Path
import shutil,subprocess,sys,tempfile
sys.dont_write_bytecode=True

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')

def recatalog(root,names):
    index=read(root/'index.json');receipt=read(root/'original/FINAL7-RECEIPT.json')
    for name in names:
        original_name=Path(name).name.removesuffix('.bytes')
        if original_name in receipt['artifacts_sha256']:
            digest=sha(root/name);receipt['artifacts_sha256'][original_name]=digest
            for entry in index['declarations']:
                if entry['declared_by']=='FINAL7.artifacts.'+original_name:entry['sha256']=digest
    write(root/'original/FINAL7-RECEIPT.json',receipt)
    for name in [*names,'original/FINAL7-RECEIPT.json']:
        path=root/name;index['packet_files'][name]=dict(sha256=sha(path),bytes=path.stat().st_size)
    index['original_receipt']['sha256']=sha(root/'original/FINAL7-RECEIPT.json');write(root/'index.json',index)

def mutate(root,kind):
    xml='original/candidate7-bounds.xml'
    if kind=='missing_xml':(root/xml).unlink()
    elif kind=='missing_fixture':(root/'fixtures/test_cohort_guard.py.bytes').unlink()
    elif kind=='corrupt_script':(root/'original/test_final7_bounds.py.bytes').write_text('changed')
    elif kind=='symlink':
        (root/xml).unlink();(root/xml).symlink_to(root/'original/candidate7-storage.xml')
    elif kind=='extra_file':(root/'unknown').write_text('unknown')
    elif kind=='empty_directory':(root/'unknown-directory').mkdir()
    elif kind=='omitted_declaration':
        index=read(root/'index.json');index['declarations']=[d for d in index['declarations'] if d['declared_by']!='FINAL7.artifacts.candidate7-bounds.xml'];write(root/'index.json',index)
    elif kind=='boolean_exit_coherent_recatalog':
        name='original/FINAL7-commands.json';commands=read(root/name);commands['runs'][0]['child_exit_code']=False;write(root/name,commands);recatalog(root,[name])
    elif kind=='missing_source_pin_coherent_recatalog':
        name='source/source-bridge.json';bridge=read(root/name);bridge['source_files'].pop(next(iter(bridge['source_files'])));bridge['source_file_count']-=1;write(root/name,bridge);recatalog(root,[name])
    elif kind=='missing_case_coherent_recatalog':
        name='original/FINAL7-case-ledger.json';ledger=read(root/name);ledger['cases'].pop();write(root/name,ledger);recatalog(root,[name])

def main():
    results=[]
    cases=['positive','missing_xml','missing_fixture','corrupt_script','symlink','extra_file','empty_directory','omitted_declaration','boolean_exit_coherent_recatalog','missing_source_pin_coherent_recatalog','missing_case_coherent_recatalog']
    with tempfile.TemporaryDirectory(prefix='relocated-packet-') as temporary:
        for optimized in (False,True):
            for kind in cases:
                root=Path(temporary)/(kind+('-O' if optimized else '-normal'));shutil.copytree(ROOT,root)
                if kind!='positive':mutate(root,kind)
                command=[sys.executable,*(['-O'] if optimized else []),str(root/'tools/verify_packet.py'),'--packet',str(root)]
                child=subprocess.run(command,text=True,capture_output=True)
                outcome=json.loads(child.stdout)
                wanted=0 if kind=='positive' else 1
                if child.returncode!=wanted or outcome.get('tests_rerun') is not False:
                    raise RuntimeError('Wrong verifier result: '+repr((kind,optimized,child.returncode,outcome)))
                results.append(dict(case=kind,optimized=optimized,exit_code=child.returncode,status=outcome['status'],reason=outcome.get('reason')))
    print(json.dumps(dict(status='passed_archive_controls',tests_rerun=False,controls=len(results),
        generated_by='tools/packet_controls.py',generator_sha256=sha(Path(__file__)),results=results),indent=2))

if __name__=='__main__':main()

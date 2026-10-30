"""Portable original FINAL7 replay. Default prints a plan; --execute runs it.

Requires a source worktree matching the pinned d0 backend and cached images.
Never downloads, builds, forwards provider environment, or uses existing PG.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
import xml.etree.ElementTree as ET
sys.dont_write_bytecode=True
from verify_packet import verify,load,sha


def main(packet,repo,out,execute):
    verify(packet)
    if out.exists() or out==repo or repo in out.parents or packet in out.parents:
        raise ValueError('Fresh output outside packet and source required')
    bridge=load(packet/'source/source-bridge.json')
    expected=bridge['source_files']
    actual={p.relative_to(repo).as_posix() for p in (repo/'backend').rglob('*') if p.is_file()}
    if any(p.is_symlink() for p in (repo/'backend').rglob('*')) or actual!={n for n in expected if n.startswith('backend/')}:
        raise ValueError('Use a clean historical source tree; backend inventory differs')
    for name,entry in expected.items():
        if sha(repo/name)!=entry['sha256']:raise ValueError('Source differs from original d0: '+name)
    receipt=load(packet/'original/FINAL7-RECEIPT.json');name='standards-portable-'+uuid4().hex[:10]
    db='postgresql://postgres@127.0.0.1:55492/standards_pending_source_test'
    pg=['docker','run','--pull','never','--rm','-d','--name',name,'--label','codex.review=portable-final7','--network','none','--cpus','1','--memory','512m','--pids-limit','128','--tmpfs','/var/lib/postgresql/data:rw,size=268435456','-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB=standards_pending_source_test',receipt['postgres_image'],'postgres','-c','listen_addresses=127.0.0.1','-c','port=55492','-c','max_connections=12','-c','shared_buffers=32MB']
    base=['docker','run','--pull','never','--rm','--network','container:'+name,'--cpus','1','--memory','2g','--pids-limit','256','-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTHON_DOTENV_DISABLED=1','-e','PYTHONPATH=/work/backend:/work/backend/tests:/work/backend/tests/social:/review:/prior','-e','DATABASE_URL='+db,'-e','STANDARDS_PG_URL='+db,'-v',str(repo/'backend')+':/work/backend:ro','-v',str(repo/'.github/workflows/seed.yml')+':/work/.github/workflows/seed.yml:ro','-v',str(out/'review')+':/review','-v',str(out/'fixtures')+':/prior:ro','-v',str(out/'results')+':/results','-w','/work/backend',receipt['python_image']]
    runs=[('latency',['/review/test_candidate7_facebook_150ms.py']),('bounds',['/review/test_final7_bounds.py']),('storage',['/review/test_final7_storage.py']),('source',['/review/test_final7_source_guards.py','/review/test_final7_global_prefix.py','/prior/test_completion_witness.py','/prior/test_witness_contexts.py::test_shared_witness_actual_source_context_baseline_change_and_replay'])]
    commands=[(label,base+['python','-m','pytest','-p','no:cacheprovider','-v','-s',*targets,'--junitxml=/results/'+label+'.xml']) for label,targets in runs]
    plan=dict(scope='Fresh ORIGINAL d0/FINAL7 replay only, not phase-repair acceptance',postgres=pg,prepare=base+['python','/review/prepare_current_pg.py'],tests=commands)
    if not execute:
        print(json.dumps(dict(status='plan_only',tests_rerun=False,**plan),indent=2));return
    out.mkdir(parents=True,exist_ok=False)
    for sub in ('review','fixtures','results'):(out/sub).mkdir()
    # Materialize code inputs only. Historical XML/log/output bytes are never overwritten.
    for folder,target in [('original','review'),('fixtures','fixtures')]:
        for path in (packet/folder).glob('*.py.bytes'):
            (out/target/path.name.removesuffix('.bytes')).write_bytes(path.read_bytes())
    result=dict(status='failed',scope=plan['scope'],source_commit=bridge['commit'],tests_rerun=False,
        generated_by='tools/replay.py',generator_sha256=sha(Path(__file__)),child_exit_codes={})
    owned=None
    try:
        owned=subprocess.check_output(pg,text=True).strip()
        if len(owned)!=64:raise ValueError('Owned container ID missing')
        for _ in range(100):
            probe=subprocess.run(['docker','exec',owned,'pg_isready','-h','127.0.0.1','-p','55492','-U','postgres'],capture_output=True)
            if probe.returncode==0:break
            time.sleep(.1)
        else:raise ValueError('Owned PG not ready')
        for label,command in [('prepare',plan['prepare']),*commands]:
            if label!='prepare':result['tests_rerun']=True
            with (out/'results'/(label+'.txt')).open('w') as stream:
                child=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
            result['child_exit_codes'][label]=child.returncode
            if child.returncode:raise ValueError('Replay child failed: '+label)
        cases=[]
        for label,_ in commands:
            for case in ET.parse(out/'results'/(label+'.xml')).getroot().iter('testcase'):
                if any(case.find(k) is not None for k in ('failure','error','skipped')):raise ValueError('Nonpass replay')
                cases.append(case.attrib['classname']+'::'+case.attrib['name'])
        original=load(packet/'original/FINAL7-case-ledger.json')['cases']
        if len(cases)!=74 or set(cases)!={c['id'] for c in original}:raise ValueError('Replay identities differ')
        verify(packet)
        for name,entry in expected.items():
            if sha(repo/name)!=entry['sha256']:raise ValueError('Source drift during replay: '+name)
        for folder,target in [('original','review'),('fixtures','fixtures')]:
            for path in (packet/folder).glob('*.py.bytes'):
                if sha(out/target/path.name.removesuffix('.bytes'))!=sha(path):raise ValueError('Replay helper drift')
        result.update(status='passed_original_scope',cases=74)
    finally:
        if owned:
            info=json.loads(subprocess.check_output(['docker','inspect',owned],text=True))[0]
            if info['Id']!=owned or info['Config']['Labels'].get('codex.review')!='portable-final7':raise ValueError('Owned cleanup identity differs')
            subprocess.run(['docker','rm','-f',owned],check=True,capture_output=True)
            left=subprocess.check_output(['docker','ps','-a','--filter','name=^/'+name+'$','--format','{{.ID}}'],text=True)
            if left:raise ValueError('Owned PG survived cleanup')
            result['owned_pg_absent']=True
        (out/'results/replay-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    a=parser.parse_args();main(a.packet.resolve(),a.repo.resolve(),a.out.resolve(),a.execute)

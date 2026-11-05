"""Inert document-envelope controls, never official acquisitions or native proof."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from common import Refusal, identity, sha256
import operational
import runtime
from test_controls import make_repo
import record


@pytest.fixture
def envelope(tmp_path):
    repo, _ = make_repo(tmp_path, 'def test_probe(): pass\n')
    root = tmp_path / 'packet'; root.mkdir()
    def put(name, value):
        path = root / name
        path.write_text(json.dumps(value))
        return {'path': name, 'size': path.stat().st_size, 'sha256': sha256(path)}
    inert = put('INERT-RAW.json', {'scope':'document fixture, no official authority'})
    source = put('source.json', record.source_snapshot(repo, ()))
    lock = runtime.load_lock()
    native = {name: {'path':'/inert/'+name, 'sha256':'a'*64, 'version':'inert document'}
              for name in ('tesseract','pdftoppm','pdftotext','pdfinfo','java')}
    native.update(dpkg=['inert\t1'], dpkg_sha256=identity(['inert\t1']), os_release_sha256='b'*64,
                  traineddata={'/inert/eng':'c'*64}, languages=['eng'], linked_libraries={'/inert/lib':'d'*64})
    rt = put('runtime.json', dict(qualification='PYTHON_AND_REVIEWED_NATIVE',native_profile_sha256='e'*64,
                 lock_sha256=sha256(runtime.LOCK),python='3.12.16',executable_sha256='f'*64,stdlib_sha256='e'*64,
                 soabi='inert-document', system='Linux', machine='x86_64',
                 packages={r['name']:{'version':r['version'],'files_sha256':'a'*64} for r in lock['packages']},
                 native=native))
    domains = runtime.read_json(operational.CONTRACT)['domains']
    plan = dict(domains=domains,bootstrap=False,dry_run=False,audits_review='',
                reacquire_pending_pdf=False,audits_source_acceptance='')
    plan_ref = put('plan.json',plan)
    pg_rows = [dict(domain=d,job_id=i+1,run_id=100,attempt=1,processed=1,created=0,updated=0)
               for i,d in enumerate(domains)]
    pg = put('pg.json',pg_rows)
    source_data = runtime.read_json(root / source['path'])
    value = dict(schema='nightly-operational-envelope-v1', generated_at=datetime.now(timezone.utc).isoformat(),
                 binding=dict(commit=source_data['commit'],tree=source_data['tree'],admitted_sha=source_data['commit'],
                              schema_revision='a756b20a0001',run_id=100,attempt=1),
                 source=source,runtime=rt,plan=dict(sha256=identity(plan),original=plan_ref),
                 cli=dict(exit_code=0,executed=True,run_id=100,attempt=1,original=inert),
                 pg=dict(schema_revision='a756b20a0001',run_id=100,attempt=1,inventory=pg),
                 domains=[dict(domain=d,job_id=i+1,status='curated' if d=='learning_hub' else 'accepted',
                               components=[dict(id='inert',period='inert',basis='inert',units='inert',
                                                source_bytes=inert,authority=inert,acquisition=inert,readback=inert)])
                          for i,d in enumerate(domains)],
                 refresh=dict(worker_pids=[7], paths=['/'],events=[dict(kind=k,sequence=i,pid=7 if k=='backend_worker' else None,
                              request=inert,signature='a'*64,response=inert) for i,k in enumerate(
                                  ['backend_invalidate','backend_worker','frontend'])]),
                 originals={k:inert for k in ('run','jobs','full_log','acquisition_inventory','source_authority_review',
                                             'hmac_verification','cleanup')})
    path = root / 'envelope.json'
    def save(data=value): path.write_text(json.dumps(data)); return path
    save()
    return path, value, put, save


def test_inert_envelope_is_only_structural_and_never_acceptance(envelope):
    path, value, _, _ = envelope
    assert operational.validate(path) == value
    with pytest.raises(Refusal): operational.replay(path,path)


@pytest.mark.parametrize('field,value', [('run_id',True),('run_id',0),('attempt',False),('attempt',-1),
                                       ('commit','bad'),('admitted_sha','b'*40),('tree',None),('schema_revision','unknown')])
def test_binding_adversaries_refuse(envelope, field, value):
    path, original, _, save = envelope
    data=copy.deepcopy(original);data['binding'][field]=value
    with pytest.raises(Refusal): operational.validate(save(data))


@pytest.mark.parametrize('mutation', ['empty','duplicate','unknown','partial','bool-job','missing-components',
                                     'wrong-readback','frontend-first','duplicate-worker','bool-cli','stale','malformed'])
def test_operational_boundary_adversaries_refuse(envelope, mutation):
    path,data,put,save=envelope;data=copy.deepcopy(data)
    if mutation=='empty': data['domains']=[]
    if mutation=='duplicate': data['domains'][1]=data['domains'][0]
    if mutation=='unknown': data['domains'][0]['domain']='unknown'
    if mutation=='partial': data['domains'][0]['status']='partial'
    if mutation=='bool-job': data['domains'][0]['job_id']=True
    if mutation=='missing-components': data['domains'][0]['components']=[]
    if mutation=='wrong-readback': data['domains'][0]['components'][0]['readback']=put('wrong.json',{'changed':True})
    if mutation=='frontend-first': data['refresh']['events'][0]['kind']='frontend'
    if mutation=='duplicate-worker': data['refresh']['worker_pids']=[7,7]
    if mutation=='bool-cli': data['cli']['exit_code']=False
    if mutation=='stale': data['generated_at']='2020-01-01T00:00:00+00:00'
    if mutation=='malformed': data['runtime']=None
    with pytest.raises((Refusal,ValueError)): operational.validate(save(data))


def test_same_source_replay_compares_actual_retained_source_bytes(envelope):
    path,first,put,save=envelope
    second=copy.deepcopy(first);second['binding']['run_id']=101;second['cli']['run_id']=101;second['pg']['run_id']=101
    pg=runtime.read_json(path.parent/first['pg']['inventory']['path'])
    for row in pg:row['run_id']=101
    second['pg']['inventory']=put('pg-replay.json',pg)
    second_path=path.parent/'replay.json';second_path.write_text(json.dumps(second))
    assert operational.replay(path,second_path)['production_accepted'] is False
    changed=put('different-source.json',{'inert':'different bytes'})
    second['domains'][0]['components'][0].update(source_bytes=changed,readback=changed)
    second_path.write_text(json.dumps(second))
    with pytest.raises(Refusal): operational.replay(path,second_path)


def test_missing_empty_tampered_originals_refuse(envelope):
    path,data,_,save=envelope
    original=path.parent/data['originals']['run']['path']
    original.write_text('')
    with pytest.raises(Refusal): operational.validate(path)
    original.unlink()
    with pytest.raises(Refusal): operational.validate(path)


@pytest.mark.parametrize('languages',[[],['eng','eng']])
def test_native_language_evidence_refuses(envelope,languages):
    path,value,put,save=envelope
    rt=runtime.read_json(path.parent/value['runtime']['path']);rt['native']['languages']=languages
    value['runtime']=put('bad-native.json',rt)
    with pytest.raises(Refusal): operational.validate(save(value))


def test_symlink_envelope_entry_refuses(envelope):
    path,_,_,_=envelope
    link=path.parent/'alias.json';link.symlink_to(path)
    with pytest.raises(Refusal): operational.validate(link)

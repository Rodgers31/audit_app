"""Independent direct-call and executed-main manual source-scope controls."""
from dataclasses import replace
import json,os,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from seeding import source_plan as p
from seeding.domains.audits import scope

CHOICE='oag-combined-catalogue-20261101'
ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/'docs/operations/2026-11-01-oag-catalogue-acceptance/manifest.json'

@pytest.mark.parametrize('bad',[None,False,True,0,1,[],{},'true','OAG-combined-catalogue-20261101','../manifest.json','oag-combined-catalogue-20261101\n'])
def test_noncanonical_acceptance_choice_refused_at_direct_builder(bad):
    with pytest.raises(ValueError):p.build_plan(event='workflow_dispatch',schedule='',domain='audits',dry_run='false',cra='false',opendata='false',discovery='false',audits_source_acceptance=bad)

@pytest.mark.parametrize('overrides',[
    {'domains':()}, {'domains':('audits','audits')}, {'domains':('audits','national_budget')},
    {'domains':('national_budget',)}, {'domains':['audits']},
    {'dry_run':True}, {'bootstrap':True}, {'reacquire_pending_pdf':True}, {'audits_review':'oag-2542-20261026'},
    {'audits_source_acceptance':True}, {'bootstrap':1}, {'dry_run':0},
])
def test_direct_plan_cannot_bypass_builder(overrides):
    value=p.SourcePlan(('audits',),False,False,audits_source_acceptance=CHOICE)
    with pytest.raises(ValueError):replace(value,**overrides).argv


def test_execute_writes_no_actions_output_and_clamps_only_child(monkeypatch,tmp_path,capsys):
    for key in list(os.environ):
        if key.startswith(('SEED_PLAN_','SEED_CRA_','SEED_OPENDATA_','SEED_KNBS_','SEED_COUNTY_BORROWING_')):monkeypatch.delenv(key)
    for name,value in dict(SEED_PLAN_EVENT='workflow_dispatch',SEED_PLAN_DOMAIN='audits',SEED_PLAN_AUDITS_SOURCE_ACCEPTANCE=CHOICE,SEED_PDF_CACHE_TTL_SECONDS='86400',SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED='false',SOCIAL_NATIVE_ENABLED='false',SOCIAL_MEDIA_ENABLED='false',SOCIAL_WORKER_SUPERVISOR_ENABLED='false').items():monkeypatch.setenv(name,value)
    output=tmp_path/'output';output.write_text('sentinel\n');monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    seen=[]
    monkeypatch.setattr(p.subprocess,'run',lambda argv,**kw:seen.append((argv,kw)) or SimpleNamespace(returncode=17))
    monkeypatch.setattr(sys,'argv',['source_plan','--execute'])
    assert p.main()==17
    assert len(seen)==1
    argv,options=seen[0]
    assert argv==[sys.executable,'-m','seeding.cli','seed','--domain','audits','--audits-source-manifest',str(MANIFEST),'--no-dry-run']
    assert options['env']['SEED_PDF_CACHE_TTL_SECONDS']=='0'
    for flag in ('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED','SOCIAL_NATIVE_ENABLED','SOCIAL_MEDIA_ENABLED','SOCIAL_WORKER_SUPERVISOR_ENABLED'):assert options['env'][flag]=='false'
    assert os.environ['SEED_PDF_CACHE_TTL_SECONDS']=='86400'
    assert output.read_text()=='sentinel\n'
    receipt=json.loads(capsys.readouterr().out)
    assert receipt['evidence']=='selection_plan_only'
    assert receipt['domains']==['audits']


def test_manifest_exact_four_sources_previously_reviewed():
    entries=scope.parse_manifest(MANIFEST.read_bytes())
    assert len(entries)==4 and len({e['source_url'] for e in entries})==4
    prior=json.loads((ROOT/'docs/verification/2026-09-27-oag-coverage/accepted-source-manifest.json').read_text())
    # Canonical source identity comes from the existing retained packet, not arbitrary URLs.
    known={r['url']:r for r in prior}
    for entry in entries:
        old=known[entry['source_url']]
        assert entry['sha256']==old['sha256']
        assert entry['md5']==old['md5']
        assert entry['fiscal_year']==old['fiscal_year']
        assert entry['institution']==old['institution']
    receipt=scope.receipt_for(entries,raw=MANIFEST.read_bytes())
    import hashlib
    assert receipt['manifest_sha256']==hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    assert receipt['whole_world_coverage'] is False
    assert receipt['inventory_basis']=='reviewed_retained_manifest_not_live_discovery'


def test_receipt_cannot_mislabel_new_four_source_packet_as_legacy_five():
    entries=scope.parse_manifest(MANIFEST.read_bytes())
    with pytest.raises(scope.AuditSourceScopeError):scope.receipt_for(entries)


def test_legacy_raw_omission_allows_only_exact_unchanged_adopted_inventory():
    from seeding.domains.audits.observation import accepted_editions
    legacy=list(accepted_editions().values())[3:]
    receipt=scope.receipt_for(legacy)
    assert receipt['manifest_sha256']==scope.MANIFEST_SHA256
    assert len(receipt['selected'])==5
    assert receipt['whole_world_coverage'] is False
    assert receipt['attempted']==receipt['processed']==receipt['refused']==[]
    import copy
    changed=copy.deepcopy(legacy);changed[0]['sha256']='0'*64
    with pytest.raises(scope.AuditSourceScopeError):scope.receipt_for(changed)
    with pytest.raises(scope.AuditSourceScopeError):scope.receipt_for(legacy[::-1])
    with pytest.raises(scope.AuditSourceScopeError):scope.receipt_for(legacy[:-1])


def test_one_shot_iterable_cannot_emit_empty_legacy_selected_receipt():
    from seeding.domains.audits.observation import accepted_editions
    legacy=list(accepted_editions().values())[3:]
    with pytest.raises(scope.AuditSourceScopeError):scope.receipt_for(iter(legacy))

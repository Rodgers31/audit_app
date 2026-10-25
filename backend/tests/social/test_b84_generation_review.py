"""Review regressions for launch identity, refusal custody and preview budgets."""
import importlib
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy.orm import sessionmaker

from test_domain_support import db
from test_generation import configure, observation

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize('package', [False, True])
@pytest.mark.parametrize('entry', ['skipped', 'dispatch', 'preview', 'refusal'])
def test_generation_launch_identity_without_root_shim(tmp_path, package, entry):
    prefix = 'backend.' if package else ''
    env = {k:v for k,v in os.environ.items() if not k.startswith(('PG','SOCIAL_')) and k not in {'PYTHONPATH','DATABASE_URL'}}
    env.update(PYTHONPATH=str(ROOT if package else ROOT/'backend'), PYTHON_DOTENV_DISABLED='1',
               DATABASE_URL='postgresql+psycopg2://inert:inert@127.0.0.1:1/unused')
    script = f"""import importlib, socket, sys
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network'))
prefix={prefix!r}
entry={entry!r}
if entry=='skipped':
    subject=importlib.import_module(prefix+'seeding.generation_capabilities')
    result=subject.skipped_generation('opendata',dry_run=False,source_mode='live',completed=True)
    assert result['post_commit_generation']['reason']=='environment_disabled'
elif entry=='dispatch':
    subject=importlib.import_module(prefix+'seeding.generation_dispatch')
    model=importlib.import_module(prefix+'models')
    assert subject.IngestionJob is model.IngestionJob
    assert subject.dispatch_committed_generation(lambda:None,domain='counties_budget',ingestion_id=1,dry_run=False) is None
elif entry=='preview':
    subject=importlib.import_module(prefix+'social.generation.preview')
    result=subject.preview(lambda: (_ for _ in ()).throw(AssertionError('reader')),dict(domain='opendata',record_ids=[1],ingestion_id=1))
    assert result['results'][0]['status']=='unsupported_source'
    models=importlib.import_module(prefix+'models')
    social=importlib.import_module(prefix+'social.models')
    assert models.Base is social.Base
else:
    subject=importlib.import_module(prefix+'social.generation.integration')
    adapter=importlib.import_module(prefix+'seeding.source_observations')
    adapter.read_county_budget_observation=lambda *a,**k: (_ for _ in ()).throw(adapter.SourceObservationUnavailable('Retained publisher date authority required'))
    counts=dict(processed=0,drafts_created=0,baselines=0,unchanged=0,refused=0,refusal_reasons={{}})
    result=subject._consume_records(None,[1],1,__import__('time').monotonic()+30,counts,{{}},{{'uncertain':False}})
    assert result['refusal_reasons']=={{'publisher_date_receipt_unavailable':1}},result
if prefix:
    assert 'seeding' not in sys.modules, 'root seeding shim polluted the package launch'
    if 'models' in sys.modules:
        assert sys.modules['models'] is sys.modules['backend.models'], 'duplicate model identity'
print('executed',prefix,entry)
"""
    result=subprocess.run([sys.executable,'-c',script],cwd=tmp_path,env=env,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stderr


def test_county_borrowing_capability_is_explicit_but_not_eligible():
    from seeding.generation_capabilities import capability
    entry=capability('county_borrowing')
    assert not entry.financial and not entry.reports
    assert entry.reason=='report_date_authority_unavailable'


@pytest.mark.parametrize('message,code', [('Fresh committed-reader session required','FRESH_SESSION_REQUIRED'), ('PostgreSQL committed snapshot required','SOURCE_ADAPTER_UNAVAILABLE')])
def test_operational_source_problem_is_not_counted_as_evidence_refusal(db,monkeypatch,message,code):
    from seeding import source_observations as adapter
    import social.generation.integration as integration
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED','true')
    configure(db)
    monkeypatch.setattr(adapter,'read_county_budget_observation',lambda *a,**kw: (_ for _ in ()).throw(adapter.SourceObservationUnavailable(message)))
    result=integration.maybe_generate_committed(sessionmaker(bind=db.bind,expire_on_commit=False),record_ids=[1],ingestion_id=1)
    assert result['state']=='failed' and result['reason']==code,result
    assert result['refused']==0 and result['processed']==0,result


def test_preview_deadline_after_factory_acquisition_prevents_queries(monkeypatch):
    import social.generation.integration as integration
    preview=importlib.import_module('social.generation.preview')
    adapter=importlib.import_module('seeding.source_observations')
    clock=[0.0]
    monkeypatch.setattr(integration.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(adapter,'read_county_budget_observation',lambda *a,**kw: (_ for _ in ()).throw(adapter.SourceObservationUnavailable('Retained publisher date authority required')))
    class EmptySession:
        new=dirty=deleted=identity_map=()
        def in_transaction(self): return False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get_bind(self):pytest.fail('Expired preview queried its database')
    def factory():clock[0]=31;return EmptySession()
    with pytest.raises(integration.GenerationDeadlineExceeded):
        preview.preview(factory,dict(domain='counties_budget',record_ids=[1],ingestion_id=1,reports=False))


@pytest.mark.parametrize('message,code', [('Fresh committed-reader session required','FRESH_SESSION_REQUIRED'), ('PostgreSQL committed snapshot required','SOURCE_ADAPTER_UNAVAILABLE')])
def test_preview_operational_source_problem_returns_service_unavailable(db,monkeypatch,message,code):
    from seeding import source_observations as adapter
    from social.generation.preview import preview
    from social.service import SocialError
    monkeypatch.setattr(adapter,'read_county_budget_observation',lambda *a,**kw: (_ for _ in ()).throw(adapter.SourceObservationUnavailable(message)))
    with pytest.raises(SocialError) as caught:
        preview(sessionmaker(bind=db.bind),dict(domain='counties_budget',record_ids=[1],ingestion_id=1,reports=False))
    assert caught.value.code==code and caught.value.status==503


def test_confirmed_refusal_reason_survives_later_commit_uncertainty(db,monkeypatch):
    from sqlalchemy import event
    from sqlalchemy.exc import DBAPIError
    from seeding import source_observations as adapter
    import social.generation.integration as integration
    from seeding.generation_dispatch import _validate_result
    from services.generation_outcome import safe_generation_outcome
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED','true')
    configure(db)
    def read(*a,record_id,**kw):
        if record_id==1:raise adapter.SourceObservationUnavailable('Retained publisher date authority required')
        return observation(source_key='county:2').model_dump(mode='json')
    monkeypatch.setattr(adapter,'read_county_budget_observation',read)
    factory=sessionmaker(bind=db.bind,expire_on_commit=False)
    def lost(session):raise DBAPIError('COMMIT',{},RuntimeError('inert lost ack'),connection_invalidated=True)
    event.listen(factory.class_,'after_commit',lost)
    try:result=integration.maybe_generate_committed(factory,record_ids=[1,2],ingestion_id=1)
    finally:event.remove(factory.class_,'after_commit',lost)
    assert result['execution_unverified'] is True
    assert result['confirmed']['refused']==1
    assert result.get('refusal_reasons')=={'publisher_date_receipt_unavailable':1},result
    assert _validate_result(result,2)==result
    projected=safe_generation_outcome(result)
    assert projected['refusal_reasons']==result['refusal_reasons']
    assert projected['refused'] is None


@pytest.mark.parametrize('reports', [False, True])
def test_dispatch_operational_source_error_is_not_a_lineage_refusal(monkeypatch, reports):
    from seeding import generation_dispatch as bridge
    from seeding.source_observations import SourceObservationUnavailable
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'true')
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED', 'true')
    monkeypatch.setattr(bridge, 'read_county_budget_record_ids', lambda *a, **kw: (_ for _ in ()).throw(SourceObservationUnavailable('Fresh committed-reader session required')))
    monkeypatch.setattr(bridge, '_record_outcome', lambda *a, **kw: None)
    dispatch = bridge.dispatch_committed_report_generation if reports else bridge.dispatch_committed_generation
    result = dispatch(None, domain='counties_budget', ingestion_id=1, dry_run=False)
    assert result['state'] == 'failed' and result['reason'] == 'fresh_session_required'
    assert result['processed'] == 0 and result['refused'] == 0


@pytest.mark.parametrize('change', [
    {'confirmed': None}, {'confirmed': {'processed': 1}},
    {'refusal_reasons': {'publisher_date_receipt_unavailable': 2}},
    {'refusal_reasons': {'environment_disabled': 1}},
    {'refusal_reasons': {'publisher_date_receipt_unavailable': True}},
    {'refusal_reasons': {'publisher_date_receipt_unavailable': float('nan')}},
])
def test_uncertain_refusal_breakdown_cannot_invent_confirmed_progress(change):
    from seeding.generation_dispatch import _validate_result
    from services.generation_outcome import safe_generation_outcome
    result = dict(state='failed', reason='generation_database_unavailable', execution_unverified=True,
        processed=None, drafts_created=None, baselines=None, unchanged=None, refused=None,
        confirmed=dict(processed=1, drafts_created=0, baselines=0, unchanged=0, refused=1),
        refusal_reasons={'publisher_date_receipt_unavailable': 1})
    result.update(change)
    with pytest.raises(ValueError):
        _validate_result(result, 2)
    assert 'refusal_reasons' not in safe_generation_outcome(result)


def test_workflow_generation_flags_are_explicitly_default_off(monkeypatch):
    import yaml
    from seeding.generation_capabilities import skipped_generation
    from seeding import generation_dispatch as bridge
    workflow = yaml.safe_load((ROOT/'.github/workflows/seed.yml').read_text())
    for key in ('SOCIAL_GENERATION_HOOK_ENABLED', 'SOCIAL_REPORT_GENERATION_ENABLED'):
        assert workflow['env'][key] == "${{ vars."+key+" || 'false' }}"
        monkeypatch.delenv(key, raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail('Default-off generation touched its factory')
    assert bridge.dispatch_committed_generation(forbidden, domain='counties_budget', ingestion_id=1, dry_run=False) is None
    receipt = skipped_generation('counties_budget', dry_run=False, source_mode='live', completed=True)
    assert all(value['state'] == 'disabled' for value in receipt.values())

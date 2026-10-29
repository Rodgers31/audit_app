"""Explicit one-source cache refresh on the existing runner; no live download."""
import os
import sys
from types import SimpleNamespace

import pytest


def execute(monkeypatch, *, enabled='true', domain='pending_bills'):
    from seeding import source_plan as p
    for key in list(os.environ):
        if key.startswith(('SEED_PLAN_','SEED_CRA_','SEED_OPENDATA_','SEED_COUNTY_BORROWING_','SEED_KNBS_')):
            monkeypatch.delenv(key)
    for key,value in dict(SEED_PLAN_EVENT='workflow_dispatch',SEED_PLAN_DOMAIN=domain,
            SEED_PLAN_DRY_RUN='true',SEED_PLAN_REACQUIRE_PENDING_BILLS_PDF=enabled).items():
        monkeypatch.setenv(key,value)
    monkeypatch.setattr(sys,'argv',['source_plan','--execute'])
    seen=[]
    def run(argv,**kwargs):
        seen.append((argv,kwargs));return SimpleNamespace(returncode=0)
    monkeypatch.setattr(p.subprocess,'run',run)
    return p.main(),seen


def test_explicit_pending_reacquisition_disables_only_child_pdf_cache(monkeypatch):
    monkeypatch.setenv('SEED_PDF_CACHE_TTL_SECONDS','4321')
    result,seen=execute(monkeypatch)
    assert result==0 and len(seen)==1
    argv,options=seen[0]
    assert argv[-3:]==['--domain','pending_bills','--dry-run']
    assert options['env']['SEED_PDF_CACHE_TTL_SECONDS']=='0'
    assert os.environ['SEED_PDF_CACHE_TTL_SECONDS']=='4321'


def test_default_refresh_keeps_existing_execution_environment(monkeypatch):
    result,seen=execute(monkeypatch,enabled='false')
    assert result==0 and seen[0][1]=={'check':False}


@pytest.mark.parametrize('domain',['','audits','national_budget','opendata'])
def test_reacquisition_does_not_expand_to_other_selections(monkeypatch,domain):
    result,seen=execute(monkeypatch,domain=domain)
    assert result==2 and seen==[]


@pytest.mark.parametrize('value',[True,None,'TRUE','1','yes',' true '])
def test_direct_plan_reacquisition_requires_a_literal_flag(value):
    from seeding.source_plan import build_plan
    with pytest.raises(ValueError):
        build_plan(event='workflow_dispatch',schedule='',domain='pending_bills',dry_run='true',
            cra='false',opendata='false',discovery='false',reacquire_pending_pdf=value)


def test_schedules_and_bootstrap_cannot_select_forced_reacquisition():
    from seeding.source_plan import build_plan,DAILY
    common=dict(domain='',dry_run='false',cra='false',opendata='false',discovery='false',reacquire_pending_pdf='true')
    with pytest.raises(ValueError):build_plan(event='schedule',schedule=DAILY,**common)
    with pytest.raises(ValueError):build_plan(event='workflow_dispatch',schedule='',**(common|dict(domain='pending_bills',bootstrap='true')))


def test_direct_plan_cannot_skip_refresh_scope_validation():
    from seeding.source_plan import SourcePlan
    with pytest.raises(ValueError):SourcePlan(('national_budget',),False,True,reacquire_pending_pdf=True).argv
    with pytest.raises(ValueError):SourcePlan(('pending_bills',),False,True,reacquire_pending_pdf=1).argv

"""A bounded run's recorded drops must receive a later admission opportunity."""
import argparse

from seeding import cli
from seeding.config import SeedingSettings
from seeding.source_plan import SourcePlan
from seeding.types import DomainRunResult
from test_seeding_cli_budget import clock, sessionmaker_factory, _FakeRegistry


def args(**changes):
    return argparse.Namespace(domain=None, all=True, dry_run=False, since=None,
        fair_progress=True, **changes)


def test_later_domain_starts_first_after_real_budget_drop(clock, sessionmaker_factory, monkeypatch):
    calls=[]
    def handler(name):
        def run(**kwargs):
            calls.append(name)
            clock.advance(60)
            return DomainRunResult(domain=name)
        return run
    monkeypatch.setattr(cli,'REGISTRY',_FakeRegistry({n:handler(n) for n in ('a','b','c')}))
    settings=SeedingSettings(total_timeout_seconds=100,domain_timeout_seconds=600)
    assert cli.run_seed_command(args(),settings)==1
    assert calls==['a','b']
    calls.clear();clock.now=0
    assert cli.run_seed_command(args(),settings)==1
    assert calls[0]=='c'  # a durable not-run observation is not an admission
    assert len(calls)==2  # no new budget or hidden second pass
    calls.clear();clock.now=0
    cli.run_seed_command(args(),settings)
    assert calls[0]=='b'  # previous admissions remain authoritative across runs


def test_workflow_multi_domain_plan_requests_fair_progress():
    assert '--fair-progress' in SourcePlan(('audits','counties_budget'),False,False).argv
    assert '--fair-progress' not in SourcePlan(('audits',),False,False).argv


def test_explicit_single_domain_is_not_replaced(clock,monkeypatch):
    calls=[]
    def run(**kwargs):
        calls.append('a');return DomainRunResult(domain='a')
    monkeypatch.setattr(cli,'REGISTRY',_FakeRegistry({'a':run}))
    selected=argparse.Namespace(domain=['a'],all=False,dry_run=False,since=None,fair_progress=True)
    assert cli.run_seed_command(selected,SeedingSettings(total_timeout_seconds=100))==0
    assert calls==['a']


def test_running_owner_shape_precedes_terminal_scheduling_telemetry(clock,sessionmaker_factory,monkeypatch):
    from models import IngestionJob
    from sqlalchemy import select
    calls=[]
    def handler(*,session,settings,context):
        job=session.get(IngestionJob,context.job_id)
        assert set(job.meta)=={'since','seeding_claim_id'}
        assert job.meta['seeding_claim_id']==str(context.ownership.identity)
        calls.append(job.domain)
        return DomainRunResult(domain=job.domain)
    monkeypatch.setattr(cli,'REGISTRY',_FakeRegistry({n:handler for n in ('cra','opendata','county_borrowing')}))
    assert cli.run_seed_command(args(),SeedingSettings(total_timeout_seconds=1320))==0
    assert calls==['cra','opendata','county_borrowing']
    with cli.SessionLocal() as session:
        jobs=session.scalars(select(IngestionJob).order_by(IngestionJob.id)).all()
        assert len(jobs)==3
        for job in jobs:
            assert job.meta['execution_plan']['execution_order']==calls
            assert job.meta['execution_plan']['total_budget_seconds']==1320


def test_explicit_recovery_admits_both_sources_before_ordinary_rotation(clock,sessionmaker_factory,monkeypatch):
    calls=[]
    def handler(*,session,settings,context):
        from models import IngestionJob
        name=session.get(IngestionJob,context.job_id).domain
        calls.append(name);return DomainRunResult(domain=name)
    monkeypatch.setattr(cli,'REGISTRY',_FakeRegistry({n:handler for n in ('imf_weo','counties_budget','audits','opendata')}))
    selected=args(audits_reconciliation_review='oag-2542-20261026')
    assert cli.run_seed_command(selected,SeedingSettings(total_timeout_seconds=1320))==0
    assert calls==['audits','counties_budget','opendata','imf_weo']

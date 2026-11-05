"""Operational regressions execute the workflow shell and real ORM queries."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models import Base, PopulationData
from seeding.source_plan import build_plan
from tests.test_hollow_run_gate import HEALTHY_NIGHT, _run_step, _write_db

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/seed.yml'


def population_check(tmp_path, rows):
    url = os.environ.get('REFRESH_FIXTURE_PG_URL')
    if url:
        parsed = urlsplit(url)
        if (os.environ.get('REFRESH_FIXTURE_OWNED') != 'true' or parsed.hostname != '127.0.0.1'
                or parsed.path != '/auditgava_refresh_fixture' or parsed.username != 'postgres'):
            raise RuntimeError('Unowned population PostgreSQL fixture refused')
    engine = create_engine(url or 'sqlite:///'+str(tmp_path/'population.sqlite'))
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add_all(PopulationData(id=i, entity_id=None, year=y, total_population=n) for i,y,n in rows)
            session.commit()
            doc = yaml.safe_load(WORKFLOW.read_text())
            step = next(s for s in doc['jobs']['validate']['steps'] if 'Sanity checks: values' in s.get('run',''))
            body = step['run'].split('# ── Sanity checks: values in reasonable ranges ──')[1].split('latest_gdp =')[0]
            scope = {'session':session, 'PopulationData':PopulationData, 'errors':[]}
            class FixedTime(datetime):
                @classmethod
                def now(cls, tz=None): return cls(2026,11,5,tzinfo=timezone.utc)
            with patch('seeding.staleness.datetime', FixedTime):
                exec(compile(body, '<actual workflow population validation>', 'exec'), scope)
            return scope['errors']
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.parametrize('rows', [
    [(1,2010,41_598_567),(99,2025,80_000_000)],
    [(99,2010,41_598_567),(1,2025,80_000_000)],
])
def test_population_sanity_checks_newest_period_regardless_of_ids(tmp_path, rows, capsys):
    errors = population_check(tmp_path, rows)
    assert errors and '2025' in str(errors), errors
    assert '2025' in capsys.readouterr().out


def test_population_valid_newest_and_bad_old_are_distinguished(tmp_path, capsys):
    assert population_check(tmp_path, [(1,2010,1),(2,2025,57_532_493)]) == []
    assert '2025' in capsys.readouterr().out


@pytest.mark.parametrize('rows', [[], [(1,2010,41_598_567)],
    [(1,2025,57_532_493),(2,2025,57_532_494)]])
def test_population_missing_stale_or_duplicate_newest_is_not_healthy(tmp_path, rows):
    assert population_check(tmp_path, rows)


@pytest.mark.parametrize('status,outcome,conclusion', [
    ('failure','failure','failure'), ('success','failure','success'),
    ('cancelled','cancelled','cancelled'), ('success','skipped','skipped'),
])
def test_actual_result_shell_refuses_prior_cache_failure_even_if_continued(tmp_path, monkeypatch, status, outcome, conclusion):
    monkeypatch.setenv('SEED_PRIOR_JOB_STATUS', status)
    names = ('checkout','python','ocr','dependencies','writer_tls','database','pdf_cache_period',
             'restore_pdfs','native_boundary','cli','pdf_cache_state','save_pdfs')
    steps = {name:{'outcome':'success','conclusion':'success','outputs':{}} for name in names}
    steps['pdf_cache_state'].update(outcome=outcome,conclusion=conclusion)
    monkeypatch.setenv('SEED_PRIOR_STEPS', json.dumps(steps))
    result = _run_step(_write_db(tmp_path, HEALTHY_NIGHT))
    assert result.returncode == 1, result.stdout+result.stderr
    report = json.loads(next(x.removeprefix('CURRENT_RUN_REPORT_V1 ') for x in result.stdout.splitlines() if x.startswith('CURRENT_RUN_REPORT_V1 ')))
    assert report['cache_eligible'] is False


@pytest.mark.parametrize('domain,review,acceptance', [('all','none','none'),('','','')])
def test_manual_default_and_legacy_empty_plan_remain_equivalent(domain, review, acceptance):
    args = dict(event='workflow_dispatch', schedule='', domain=domain, dry_run='false',
                cra='false', opendata='false', discovery='false', audits_review=review,
                audits_source_acceptance=acceptance)
    plan = build_plan(**args)
    expected = build_plan(**dict(args, domain='', audits_review='', audits_source_acceptance=''))
    assert plan == expected


def test_cog_no_write_is_unavailable_with_last_good_not_a_served_fixture():
    from types import SimpleNamespace
    from seeding.staleness import hollow_run_findings
    job = SimpleNamespace(id=1,domain='county_officials',status='completed_with_errors',
        meta={'source_mode':'fixture','source_fallback_reason':'source_unreachable'},
        items_processed=0,items_created=0,items_updated=0)
    findings = hollow_run_findings([job])
    assert len(findings) == 1 and findings[0].level == 'FAIL'
    assert 'unavailable' in findings[0].message.lower()
    assert 'previous' in findings[0].message.lower()
    assert 'served a FIXTURE' not in findings[0].message


def test_cog_partial_governor_writes_are_not_reported_as_unchanged(tmp_path):
    from models import IngestionJob, IngestionStatus
    from seeding.staleness import check_ingestion_freshness
    engine = create_engine('sqlite:///'+str(tmp_path/'cog.sqlite'))
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            now = datetime.now(timezone.utc)
            session.add(IngestionJob(domain='county_officials',status=IngestionStatus.COMPLETED_WITH_ERRORS,
                started_at=now,finished_at=now,items_processed=47,items_created=0,items_updated=47,
                errors=['deputies unavailable'],meta={'source_mode':'partial','source_fallback_reason':'deputies_unavailable'}))
            session.commit()
            findings = check_ingestion_freshness(session)
            text = str(next(f for f in findings if f.label == 'county_officials ingestion'))
            assert 'remain unchanged' not in text and 'partial' in text.lower(),text
    finally:
        engine.dispose()


@pytest.mark.parametrize('domain,field,value', [
    ('county_officials','source_status',{'state':'unknown'}),
    ('county_officials','source_status',{'state':'live','fixture_used':0,'governors_observed':47,'deputies_state':'live'}),
    ('debt_timeline','year_coverage',{'contract':'debt-calendar-observation-coverage-v1','years':[],'note':'inert'}),
])
def test_present_malformed_native_diagnostics_cannot_certify_refresh(tmp_path,domain,field,value):
    from models import IngestionJob
    url=_write_db(tmp_path,HEALTHY_NIGHT);engine=create_engine(url)
    try:
        with Session(engine) as session:
            job=session.query(IngestionJob).filter_by(domain=domain).one()
            job.meta=dict(job.meta,**{field:value});session.commit()
        result=_run_step(url)
        assert result.returncode==1,result.stdout+result.stderr
        report=json.loads(next(x.removeprefix('CURRENT_RUN_REPORT_V1 ') for x in result.stdout.splitlines() if x.startswith('CURRENT_RUN_REPORT_V1 ')))
        assert report['cache_eligible'] is False and 'source_diagnostic_refused' in report['refusals']
    finally:engine.dispose()


def test_cog_last_good_age_has_a_bounded_current_run_frame(tmp_path):
    from models import IngestionJob
    rows=[(d,s,c,u,p,m,r) if d!='county_officials' else (d,'completed_with_errors',0,0,0,'fixture','source_unreachable')
          for d,s,c,u,p,m,r in HEALTHY_NIGHT]
    url=_write_db(tmp_path,rows);engine=create_engine(url)
    try:
        with Session(engine) as session:
            job=session.query(IngestionJob).filter_by(domain='county_officials').one()
            job.meta=dict(job.meta,source_status={'state':'unavailable','fixture_used':False,
                'stored_governors_retained':47,'dated_stored_governors':47,'newest_age_seconds':3600.0,'oldest_age_seconds':7200.0})
            session.commit()
        result=_run_step(url)
        assert result.returncode==1
        frames=[json.loads(x.removeprefix('SOURCE_DIAGNOSTICS_V1 ')) for x in result.stdout.splitlines() if x.startswith('SOURCE_DIAGNOSTICS_V1 ')]
        cog=next(x for x in frames if x['domain']=='county_officials')
        assert cog['validation']=='valid' and cog['source_status']['oldest_age_seconds']==7200.0
        assert cog['source_status']['fixture_used'] is False
    finally:engine.dispose()


def coverage_fixture():
    years=[]
    for year in range(2013,2027):
        measures={}
        for name in ('external','domestic','total','gdp'):
            state=('unqualified' if name=='gdp' and year==2026 else
                   'observed_this_run' if name=='gdp' or year>=2023 else 'retained_qualified')
            measures[name]={'state':state,'absence_reason':'annual_period_not_ended' if state=='unqualified' else None,
                'period':str(year),'period_kind':'calendar_year' if name=='gdp' else 'latest_observed_month_in_calendar_year',
                'stock_as_of_month':None if name=='gdp' else f'{year}-12','unit':'KES',
                'basis':'current_prices' if name=='gdp' else 'actual','source_url':'https://example.invalid/owned-fixture',
                'source_digest':'a'*64,'acquired_at':'2026-11-05T01:00:00+00:00',
                'locator':{'page':1,'cell':'owned inert diagnostic'},'publication_date':None,'vintage_date':None}
        ratio={'state':'unavailable' if year==2026 else 'qualified_derived_pair','stock_as_of_month':f'{year}-12',
               'gdp_calendar_year':year,'year_end_stock':True,'reason':'stock_denominator_pair_unqualified' if year==2026 else None}
        years.append({'year':year,'measures':measures,'ratio':ratio})
    return {'contract':'debt-calendar-observation-coverage-v1','years':years,'note':'inert typed diagnostic contract; no financial authority'}


def test_year_diagnostics_preserve_fresh_retained_unpublished_distinctions():
    from types import SimpleNamespace
    from seeding.current_run import source_diagnostics
    frame,valid=source_diagnostics(SimpleNamespace(id=31,domain='debt_timeline',meta={'year_coverage':coverage_fixture()}))
    assert valid and frame['validation']=='valid'
    rows=frame['year_coverage']['years']
    assert sum(r['measures']['total']['state']=='observed_this_run' for r in rows)==4
    assert sum(r['measures']['gdp']['state']=='observed_this_run' for r in rows)==13
    assert rows[0]['measures']['total']['state']=='retained_qualified' and rows[0]['ratio']['state']=='qualified_derived_pair'
    assert rows[-1]['measures']['gdp']['absence_reason']=='annual_period_not_ended'
    assert 'example.invalid' not in json.dumps(frame)


@pytest.mark.parametrize('field,value', [('state',[]),('state','unknown'),('unit','USD'),('period',2025),
    ('source_digest',True),('acquired_at',None),('locator',{}),('publication_date','2026-11-05')])
def test_year_diagnostic_wrong_schema_never_becomes_a_valid_frame(field,value):
    from types import SimpleNamespace
    from seeding.current_run import source_diagnostics
    coverage=coverage_fixture();coverage['years'][0]['measures']['total'][field]=value
    frame,valid=source_diagnostics(SimpleNamespace(id=31,domain='debt_timeline',meta={'year_coverage':coverage}))
    assert valid is False and frame['validation']=='refused'


@pytest.mark.parametrize('field', ['source_url','acquired_at','locator'])
@pytest.mark.parametrize('value', [True, [], float('nan')],ids=['boolean','array','nonfinite'])
def test_unqualified_year_data_still_requires_primitive_null_schema(field,value):
    from types import SimpleNamespace
    from seeding.current_run import source_diagnostics
    coverage=coverage_fixture();coverage['years'][-1]['measures']['gdp'][field]=value
    frame,valid=source_diagnostics(SimpleNamespace(id=31,domain='debt_timeline',meta={'year_coverage':coverage}))
    assert valid is False and frame['validation']=='refused'


@pytest.mark.parametrize('job', ['migrate','bootstrap','seed','validate'])
@pytest.mark.parametrize('profile_kind', ['missing','linked_parent'])
def test_writer_runtime_refuses_missing_reviewed_native_profile_before_acquisition(tmp_path,job,profile_kind):
    import subprocess
    doc=yaml.safe_load(WORKFLOW.read_text())
    step=next(s for s in doc['jobs'][job]['steps'] if 'runtime.py install' in s.get('run',''))
    if profile_kind=='linked_parent':
        native=tmp_path/'elsewhere';native.mkdir();(native/f'{job}.json').write_text('{}')
        parent=tmp_path/'docs/operations/nightly-acceptance-20261105';parent.mkdir(parents=True)
        (parent/'native').symlink_to(native,target_is_directory=True)
    output=tmp_path/'path';output.touch()
    result=subprocess.run(['bash','-eo','pipefail','-c',step['run']],cwd=tmp_path,text=True,capture_output=True,timeout=10,
        env={'PATH':os.environ['PATH'],'RUNNER_TEMP':str(tmp_path/'scratch'),'GITHUB_JOB':job,'GITHUB_PATH':str(output)})
    assert result.returncode==1 and 'Reviewed native ingestion profile missing' in result.stderr,result.stdout+result.stderr
    assert not (tmp_path/'scratch').exists() and output.read_text()==''

"""Diagnostic continuity must never grant source or cache acceptance."""
import copy
import json

import pytest

from test_refresh_eligibility import execution_fixture
from seeding.current_run import classify, plan_identity, publish_diagnostics
from seeding.source_plan import SourcePlan


def unavailable():
    jobs,_,context=execution_fixture();job=jobs[0]
    plan=SourcePlan(('county_officials',),False,False)
    context['planned_identity']=plan_identity(plan)
    job.domain='county_officials';job.items_processed=job.items_created=job.items_updated=0
    job.status='completed_with_errors';job.errors=['source unavailable']
    job.meta={'source_mode':'fixture','source_fallback_reason':'source_unreachable',
        'execution_plan':{'planned_domains':['county_officials'],'execution_order':['county_officials']},
        'source_status':{'state':'unavailable','fixture_used':False,'stored_governors_retained':47,
                        'dated_stored_governors':47,'oldest_age_seconds':86400,'newest_age_seconds':3600}}
    return [job],plan,context


def test_current_unavailable_cog_keeps_age_diagnostics_while_cache_stays_refused(tmp_path,monkeypatch):
    jobs,plan,context=unavailable();report=classify(jobs,plan,context)
    assert report['classification']=='unsafe' and report['cache_eligible'] is False
    output=tmp_path/'output';monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    packet=publish_diagnostics(jobs,report,context)
    assert packet['scope']=='diagnostics_only_not_source_acceptance'
    assert packet['rows'][0]['source_status']['oldest_age_seconds']==86400
    stored=json.loads(output.read_text().strip().split('=',1)[1]);assert stored==packet
    assert report['cache_eligible'] is False


@pytest.mark.parametrize('bad',['old_job','outside_window','wrong_run','missing','duplicate','unexecuted'])
def test_unbound_source_diagnostics_are_not_published(tmp_path,monkeypatch,bad):
    jobs,plan,context=unavailable()
    if bad=='old_job':jobs[0].id=30
    if bad=='outside_window':context['cli_started']='2026-11-05T02:00:00Z'
    if bad=='wrong_run':context['cli_run_id']='9999'
    if bad=='missing':jobs=[]
    if bad=='duplicate':jobs.append(copy.deepcopy(jobs[0]))
    if bad=='unexecuted':context['cli_executed']='false'
    report=classify(jobs,plan,context)
    output=tmp_path/'output';monkeypatch.setenv('GITHUB_OUTPUT',str(output))
    assert publish_diagnostics(jobs,report,context) is None
    assert not output.exists()

"""Proposed combined-lane regression; root may adopt after reviewing the delta.

The actual source producer and current-run consumer execute. db_session is the
ordinary backend fixture; final PostgreSQL/native identity is a separate gate.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from seeding.domains.debt_timeline.coverage import coverage_report
from seeding.current_run import classify, plan_identity, source_diagnostics
from seeding.source_plan import SourcePlan
from test_refresh_eligibility import execution_fixture


def actual_producer_packet(db_session):
    now = datetime.now(timezone.utc)
    rows = [SimpleNamespace(year=y, external=None, domestic=None, total=None, gdp=None, source_evidence=[])
            for y in (now.year - 1, now.year)]
    return coverage_report(db_session, rows, now=now)


def job_from_producer(db_session):
    jobs, _, context = execution_fixture()
    job = jobs[0]
    job.domain = 'debt_timeline'
    plan = SourcePlan(('debt_timeline',), False, False)
    context['planned_identity'] = plan_identity(plan)
    job.meta = {'source_mode': 'partial',
                'source_fallback_reason': 'debt_stock_refresh_incomplete',
                'execution_plan': {'planned_domains': ['debt_timeline'], 'execution_order': ['debt_timeline']},
                'year_coverage': actual_producer_packet(db_session)}
    return job, plan, context


def test_real_debt_producer_contract_is_not_malformed_current_run(db_session):
    job, plan, context = job_from_producer(db_session)
    projected, valid = source_diagnostics(job)
    assert valid is True and projected['validation'] == 'valid'
    report = classify([job], plan, context)
    assert 'source_diagnostic_refused' not in report['refusals']
    assert report['classification'] != 'unsafe' and report['cache_eligible'] is True


def test_retained_legacy_debt_contract_remains_readable(db_session):
    job, _, _ = job_from_producer(db_session)
    packet = job.meta['year_coverage']
    for key in ('required_stock_years', 'required_gdp_years', 'unpublished_gdp_years'):
        packet.pop(key)
    for row in packet['years']:
        for measure in row['measures'].values():
            measure.pop('required')
            measure.pop('publication_requirement')
    projection, valid = source_diagnostics(job)
    assert valid is True and projection['validation'] == 'valid'


@pytest.mark.parametrize('bad', ['required_bool', 'wrong_required_stock', 'wrong_required_gdp',
                                'missing_new_measure_field', 'unknown_measure_field', 'unknown_top_field',
                                'duplicate_stock_year', 'unsorted_stock_years', 'boolean_year',
                                'string_year', 'partial_extension', 'false_required_stock',
                                'wrong_unpublished_requirement'])
def test_debt_requirement_extensions_are_closed_and_consistent(db_session, bad):
    job, _, _ = job_from_producer(db_session)
    packet = job.meta['year_coverage']
    if bad == 'required_bool': packet['years'][0]['measures']['total']['required'] = 1
    if bad == 'wrong_required_stock': packet['required_stock_years'] = packet['required_stock_years'][:1]
    if bad == 'wrong_required_gdp': packet['required_gdp_years'] = packet['unpublished_gdp_years']
    if bad == 'missing_new_measure_field': packet['years'][0]['measures']['total'].pop('publication_requirement')
    if bad == 'unknown_measure_field': packet['years'][0]['measures']['total']['unreviewed'] = True
    if bad == 'unknown_top_field': packet['unreviewed'] = True
    if bad == 'duplicate_stock_year': packet['required_stock_years'].append(packet['required_stock_years'][0])
    if bad == 'unsorted_stock_years': packet['required_stock_years'].reverse()
    if bad == 'boolean_year': packet['required_stock_years'][0] = True
    if bad == 'string_year': packet['required_stock_years'][0] = str(packet['required_stock_years'][0])
    if bad == 'partial_extension': packet.pop('unpublished_gdp_years')
    if bad == 'false_required_stock': packet['years'][0]['measures']['total']['required'] = False
    if bad == 'wrong_unpublished_requirement':
        packet['years'][-1]['measures']['gdp']['publication_requirement'] = 'required_published_period'
    projected, valid = source_diagnostics(job)
    assert valid is False and projected['validation'] == 'refused'

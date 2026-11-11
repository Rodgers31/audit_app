"""Independent reproduction; inert decoder/transport, real ORM and qualifier."""
from test_refresh_review_debt import db, freshness, run_source, document, URL
from test_refresh_review_debt_boundary import capture
from seeding.domains.debt_timeline import writer
from seeding.domains.debt_timeline.coverage import coverage_report
from services.response_receipts import persist_evidence
from models import DebtTimeline
from sqlalchemy import select


def test_rejected_current_receipt_must_not_claim_observed_this_run(db, tmp_path, monkeypatch):
    run_source(db, tmp_path/'first', monkeypatch)
    before = db.scalar(select(DebtTimeline).where(DebtTimeline.year == 2025)).total
    record = capture(tmp_path/'new', monkeypatch)
    other = document(db, url=URL, publisher='Central Bank of Kenya')
    other.title = 'Different observation binding'
    db.flush()
    persist_evidence(db, other, [record.source_evidence[0]])
    writer.write_debt_timeline_records(db, [record], {})
    db.commit()
    assert db.scalar(select(DebtTimeline).where(DebtTimeline.year == 2025)).total == before
    result = coverage_report(db, [record])
    print(result)
    assert result['years'][0]['measures']['total']['state'] == 'retained_qualified'


def test_current_then_retained_years_have_distinct_observation_states(db,tmp_path,monkeypatch):
    result,rows,_,_=run_source(db,tmp_path/'first',monkeypatch)
    coverage=result.metadata['year_coverage']
    assert coverage['contract']=='debt-calendar-observation-coverage-v1'
    for year in coverage['years']:
        assert year['measures']['total']['state']=='observed_this_run'
        assert year['measures']['total']['stock_as_of_month']==f"{year['year']}-12"
        assert year['measures']['gdp']['period_kind']=='calendar_year'
        assert year['measures']['gdp']['publication_date'] is None
    result,_,_,_=run_source(db,tmp_path/'gdp-only',monkeypatch,cbk=False)
    for year in result.metadata['year_coverage']['years']:
        assert year['measures']['total']['state']=='retained_qualified'
        assert year['measures']['gdp']['state']=='observed_this_run'
    assert result.metadata['refresh_components']['debt']['state']=='unavailable'


def test_absent_current_year_gdp_is_not_projected_or_zeroed(db,tmp_path,monkeypatch):
    from datetime import datetime,timezone
    from seeding.domains.debt_timeline.parser import DebtTimelineRecord
    year=datetime.now(timezone.utc).year
    record=DebtTimelineRecord(year=year,external=400,domestic=600,total=1000,gdp=None,gdp_ratio=None)
    report=coverage_report(db,[record])['years'][0]
    assert report['measures']['gdp']['state']=='unqualified'
    assert report['measures']['gdp']['absence_reason']=='annual_period_not_ended'
    assert report['ratio']['state']=='unavailable'
    assert report['measures']['total']['stock_as_of_month'] is None

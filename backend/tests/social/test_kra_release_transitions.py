"""PR833: evidence-kind changes cannot masquerade as another annual release."""
from copy import deepcopy
from datetime import datetime, timezone
import pytest
from sqlalchemy import select, func
from social.generation.service import report_release_state, report_release_regresses, valid_report_release_state, consume_observation
from social.generation.contracts import SourceObservation
from social.generation.preview import preview
from social.generation.models import SourceCursor
from social.models import SocialPost
from social.service import SocialService, SocialError
from seeding.source_observations import read_revenue_report_observation
from test_b83_generation_postgres import pg, no_publication
from test_b86_native_postgres import enable, ingest as publication_ingest
from test_kra_catalogue_postgres import ingest as catalogue_ingest, request
from test_kra_catalogue import capture, report, observation, WRAPPER, ENTRY, acquired, URL, CATALOGUE


def state(day='2026-07-08', *, kind='publisher_catalogue', start='2025-07-01', end='2026-06-30'):
    value=dict(release_hash='a'*64,period_start=start,period_end=end)
    value['catalogued_on' if kind=='publisher_catalogue' else 'published_on']=day
    if kind=='publisher_catalogue':value['evidence_kind']=kind
    return value


def test_catalogue_state_persists_explicit_kind_without_altering_legacy_state(tmp_path):
    parsed=SourceObservation.model_validate(observation(report(capture(tmp_path)[0])))
    assert report_release_state(parsed)['evidence_kind']=='publisher_catalogue'
    assert valid_report_release_state(state())
    assert valid_report_release_state(state(kind='publisher_publication'))
    for changed in [dict(evidence_kind='publisher_publication'),dict(evidence_kind=None),dict(evidence_kind=True),dict(evidence_kind='unknown')]:
        assert not valid_report_release_state(state()|changed)


@pytest.mark.parametrize('before,after',[
    (state(),state(kind='publisher_publication')),
    (state(kind='publisher_publication'),state()),
    (state(kind='publisher_publication',start='2024-07-01',end='2025-06-30',day='2025-07-08'),state()),
])
def test_cross_kind_same_release_and_unknown_date_downgrade_refuse(before,after):
    assert report_release_regresses(after,before)


def test_later_completed_published_release_has_a_separate_admission_path():
    old=state(start='2024-07-01',end='2025-06-30',day='2025-07-08')
    assert not report_release_regresses(state(kind='publisher_publication'),old)
    assert report_release_regresses(state(kind='publisher_publication'),old|{'catalogued_on':'2026-07-09'})


def test_later_publication_transition_requires_completed_period_at_direct_guard():
    old=state(start='2024-07-01',end='2025-06-30',day='2025-07-08')
    premature=state(kind='publisher_publication',day='2025-07-09')
    assert report_release_regresses(premature,old)


@pytest.mark.parametrize('first_kind',['publisher_catalogue','publisher_publication'])
@pytest.mark.parametrize('backfill',[False,True])
def test_actual_pg_same_period_kind_switch_cannot_create_a_second_draft(pg,tmp_path,monkeypatch,first_kind,backfill):
    factory,_=pg;enable(factory,monkeypatch)
    def publication():return publication_ingest(factory,tmp_path,year=2025,published='10/07/2026')
    def catalogue():return catalogue_ingest(factory,tmp_path)
    first,second=(catalogue,publication) if first_kind=='publisher_catalogue' else (publication,catalogue)
    job,record=first()
    value=read_revenue_report_observation(factory,record_id=record,ingestion_id=job)
    with factory.begin() as db:
        assert consume_observation(SocialService(db),value,backfill=True)['status']=='draft_created'
    with factory() as db:before=deepcopy(db.scalar(select(SourceCursor)).report_state)
    job,record=second()
    value=read_revenue_report_observation(factory,record_id=record,ingestion_id=job)
    result=preview(factory,request(job,record,backfill=backfill))['results'][0]
    assert result['status']=='refused' and result['reason']=='report_release_regression',result
    with pytest.raises(SocialError,match='REPORT_RELEASE_REGRESSION'):
        with factory.begin() as db:consume_observation(SocialService(db),value,backfill=backfill)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost))==1
        assert db.scalar(select(SourceCursor)).report_state==before
    no_publication(factory)


def test_real_pg_catalogue_to_genuinely_later_published_release(pg,tmp_path,monkeypatch):
    from models import IngestionJob, IngestionStatus, SourceDocument, Country, DocumentType
    from seeding.kra_report_catalogue import capture_catalogue_report
    from seeding.native_report_authority import persist_native_report
    from seeding.types import DomainRunContext
    factory,_=pg;enable(factory,monkeypatch)
    old_url=URL.replace('2025-2026','2024-2025')
    with factory.begin() as db:
        job=IngestionJob(domain='revenue_by_source',status=IngestionStatus.RUNNING,dry_run=False,
            started_at=datetime.now(timezone.utc),errors=[],meta={'source_mode':'live'})
        db.add(job);db.flush()
        wrapper=acquired(tmp_path,WRAPPER.replace(b'2025/2026',b'2024/2025'),old_url)
        entry=acquired(tmp_path,ENTRY.replace(b'2025-2026',b'2024-2025').replace(b'08/07/2026',b'08/07/2025'),CATALOGUE)
        proof,reason=capture_catalogue_report(wrapper,entry,fiscal_year='FY 2024/25')
        assert proof is not None,reason
        source=SourceDocument(country_id=db.scalar(select(Country.id)),publisher='Kenya Revenue Authority',
            title='Owned prior annual fixture',url=old_url,fetch_date=datetime.now(timezone.utc),doc_type=DocumentType.REPORT,meta={})
        db.add(source);db.flush()
        record=persist_native_report(db,source,proof,context=DomainRunContext(None,False,job.id),domain='revenue_by_source')
        job.status=IngestionStatus.COMPLETED;job.finished_at=datetime.now(timezone.utc);job_id=job.id
    value=read_revenue_report_observation(factory,record_id=record,ingestion_id=job_id)
    with factory.begin() as db:assert consume_observation(SocialService(db),value)['status']=='baseline'
    job_id,record=publication_ingest(factory,tmp_path,year=2025,published='10/07/2026')
    value=read_revenue_report_observation(factory,record_id=record,ingestion_id=job_id)
    assert preview(factory,request(job_id,record))['results'][0]['status']=='eligible_change'
    with factory.begin() as db:assert consume_observation(SocialService(db),value)['status']=='draft_created'
    with factory.begin() as db:assert consume_observation(SocialService(db),value)['status']=='unchanged'
    no_publication(factory)

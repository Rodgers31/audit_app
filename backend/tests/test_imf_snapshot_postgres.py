"""Actual PostgreSQL contract for observation revisions, not fetch snapshots."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from uuid import uuid4
import asyncio

import httpx
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from models import ImfWeoObservation as Observation
from seeding.domains.imf_weo.writer import persist_imf_weo
from seeding.types import DomainRunContext

AT = datetime(2026, 10, 26, tzinfo=timezone.utc)
LIVE = DomainRunContext(since=None, dry_run=False)


@pytest.fixture
def pg():
    url = os.getenv('AUDIT_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Requires isolated AUDIT_TEST_POSTGRES_URL')
    admin = create_engine(url)
    schema = 'imf_' + uuid4().hex
    with admin.begin() as c:
        c.exec_driver_sql('CREATE SCHEMA ' + schema)
    engine = create_engine(url, connect_args={'options': '-csearch_path=' + schema})
    Observation.__table__.create(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as c:
            c.exec_driver_sql('DROP SCHEMA ' + schema + ' CASCADE')
        admin.dispose()


def row(value='67.3000', at=AT, year=2024, projection=False):
    return dict(country_code='KEN', indicator='GGXWDG_NGDP', year=year,
                value=value, is_projection=projection, vintage=at, source='imf_datamapper')


def write(pg, records):
    with Session(pg) as db, db.begin():
        return persist_imf_weo(db, records, LIVE)


def stored(pg):
    with Session(pg) as db:
        return [(r.value, r.vintage, r.is_projection) for r in
                db.scalars(select(Observation).order_by(Observation.vintage))]


def test_different_fetch_times_identical_values_do_not_insert(pg):
    assert write(pg, [row()]).created == 1
    result = write(pg, [row(at=AT + timedelta(days=1))])
    assert (result.created, result.skipped) == (0, 1)
    assert stored(pg) == [(Decimal('67.3000'), AT, False)]


def test_actual_revisions_and_return_to_original_value_are_preserved(pg):
    for day, value in enumerate(('67.3', '68.1', '67.3')):
        result = write(pg, [row(value, at=AT + timedelta(days=day))])
        assert (result.created, result.updated) == ((1, 0) if day == 0 else (0, 1))
    assert [r[0] for r in stored(pg)] == [Decimal('67.3'), Decimal('68.1'), Decimal('67.3')]


@pytest.mark.parametrize('first,second', [(None, '0'), ('0', None), ('1', '0')])
def test_null_zero_and_changed_amount_are_distinct(pg, first, second):
    write(pg, [row(first)])
    assert write(pg, [row(second, at=AT + timedelta(days=1))]).updated == 1
    assert len(stored(pg)) == 2


def test_projection_change_is_preserved(pg):
    write(pg, [row()])
    assert write(pg, [row(at=AT + timedelta(days=1), projection=True)]).updated == 1


def test_precision_compares_the_actual_numeric_storage_contract(pg):
    write(pg, [row('67.30001')])
    assert write(pg, [row('67.30002', at=AT + timedelta(days=1))]).created == 0
    assert write(pg, [row('67.30005', at=AT + timedelta(days=2))]).updated == 1


def test_historical_duplicate_snapshots_are_retained(pg):
    with Session(pg) as db, db.begin():
        db.add_all([Observation(**row(at=AT + timedelta(days=i))) for i in range(3)])
    assert write(pg, [row(at=AT + timedelta(days=3))]).created == 0
    assert len(stored(pg)) == 3


@pytest.mark.parametrize('day', [0, -1])
def test_conflicting_or_out_of_order_capture_refuses_whole_batch(pg, day):
    write(pg, [row()])
    with pytest.raises(ValueError):
        write(pg, [row('50', year=2023, at=AT + timedelta(days=day)), row('68', at=AT + timedelta(days=day))])
    assert len(stored(pg)) == 1


def test_outer_transaction_retains_commit_and_rollback_control(pg):
    with Session(pg) as db:
        assert persist_imf_weo(db, [row()], LIVE).created == 1
        with Session(pg) as other:
            assert list(other.scalars(select(Observation))) == []
        db.rollback()
    assert stored(pg) == []


def test_direct_concurrent_writer_cannot_acknowledge_duplicate(pg):
    with Session(pg) as db:
        assert persist_imf_weo(db, [row()], LIVE).created == 1
        with pytest.raises(OperationalError) as exc:
            write(pg, [row(at=AT + timedelta(days=1))])
        assert exc.value.orig.pgcode == '55P03'
        db.commit()
    assert write(pg, [row(at=AT + timedelta(days=1))]).created == 0
    assert len(stored(pg)) == 1


def test_duplicate_input_identity_is_not_silently_dropped(pg):
    with pytest.raises(ValueError):
        write(pg, [row(), row()])
    assert stored(pg) == []


@pytest.mark.parametrize('value', [True, 'NaN', 'Infinity', '-Infinity'])
def test_invalid_numbers_refuse_before_any_insert(pg, value):
    with pytest.raises(ValueError):
        write(pg, [row('5', year=2023), row(value)])
    assert stored(pg) == []


def test_changed_cohort_retains_companion_rows_and_honest_counts(pg):
    original = [row(), row('50', year=2023)]
    assert write(pg, original).created == 2
    changed = [row('68', at=AT + timedelta(days=1)), row('50', year=2023, at=AT + timedelta(days=1))]
    result = write(pg, changed)
    assert (result.created, result.updated, result.skipped, result.snapshot_rows_inserted) == (0, 1, 1, 2)
    with Session(pg) as db:
        latest = db.scalars(select(Observation).where(Observation.vintage == AT + timedelta(days=1))).all()
        assert {r.year for r in latest} == {2023, 2024}
    assert write(pg, [dict(r, vintage=AT + timedelta(days=2)) for r in changed]).snapshot_rows_inserted == 0


def test_incomplete_response_cannot_hide_a_companion_indicator(pg):
    write(pg, [row(), row('50', year=2023)])
    with pytest.raises(ValueError, match='Incomplete'):
        write(pg, [row('68', at=AT + timedelta(days=1))])
    assert len(stored(pg)) == 2


def test_stale_repeatable_read_snapshot_refuses_without_resetting_caller(pg):
    with Session(pg.execution_options(isolation_level='REPEATABLE READ')) as stale:
        stale.scalar(text('SELECT count(*) FROM pg_class'))
        write(pg, [row()])
        with pytest.raises(ValueError, match='READ COMMITTED'):
            persist_imf_weo(stale, [row(at=AT + timedelta(days=1))], LIVE)
        assert stale.scalar(text('SHOW transaction_isolation')) == 'repeatable read'
        stale.rollback()
    assert len(stored(pg)) == 1


@pytest.mark.parametrize('raw', [True, 'not-a-number', 'NaN', 'Infinity', '-Infinity'])
def test_parser_cannot_disguise_invalid_source_as_null_or_numeric_revision(pg, raw):
    from seeding.domains.imf_weo.parser import parse_imf_weo
    write(pg, [row()])
    payload = {'GGXWDG_NGDP': {'values': {'GGXWDG_NGDP': {'KEN': {'2024': raw}}}}}
    with pytest.raises(ValueError):
        records = parse_imf_weo(payload, vintage=AT + timedelta(days=1))
        write(pg, records)
    assert stored(pg) == [(Decimal('67.3000'), AT, False)]


def test_accepted_188_observation_input_replays_without_duplicate_facts(pg):
    fixture = Path(__file__).parent / 'fixtures/imf/accepted-2026-10-27.json'
    records = json.loads(fixture.read_text())['rows']
    for r in records:
        r['vintage'] = datetime.fromisoformat(r['vintage'])
    first = write(pg, records)
    assert (first.created, first.updated, first.snapshot_rows_inserted) == (188, 0, 188)
    repeat = [dict(r, vintage=r['vintage'] + timedelta(days=1)) for r in records]
    second = write(pg, repeat)
    assert (second.created, second.updated, second.skipped, second.snapshot_rows_inserted) == (0, 0, 188, 0)
    assert len(stored(pg)) == 188
    changed = [dict(r) for r in repeat]
    changed[0]['value'] = Decimal(changed[0]['value']) + Decimal('.1')
    revision = write(pg, changed)
    assert (revision.created, revision.updated, revision.skipped, revision.snapshot_rows_inserted) == (0, 1, 187, 188)
    assert len(stored(pg)) == 376


def test_real_fetcher_parser_keeps_full_retained_coverage(pg, monkeypatch, tmp_path):
    import seeding.domains.imf_weo as domain
    from seeding.config import SeedingSettings
    from seeding.http_client import SeedingHttpClient

    records = json.loads((Path(__file__).parent / 'fixtures/imf/accepted-2026-10-27.json').read_text())['rows']
    for r in records:
        r['vintage'] = datetime.fromisoformat(r['vintage'])
    write(pg, records)
    payload = {}
    for r in records:
        payload.setdefault(r['indicator'], {})[str(r['year'])] = r['value']
    requests = []

    def respond(request):
        requests.append(request)
        indicator = request.url.path.split('/')[-2]
        values = dict(payload[indicator])
        # An upstream that honors the caller's query must not truncate history.
        if request.url.params.get('periods'):
            allowed = request.url.params['periods'].split(',')
            values = {k: v for k, v in values.items() if k in allowed}
        return httpx.Response(200, json={'values': {indicator: {'KEN': values}}}, request=request)

    def client(settings):
        return SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(respond)))

    monkeypatch.setattr(domain, 'create_http_client', client)
    settings = SeedingSettings(storage_path=tmp_path/'store', cache_path=tmp_path/'cache', log_path=tmp_path/'logs/seed.log')
    with Session(pg) as db, db.begin():
        result = domain.run(db, settings, LIVE)
        assert (result.items_created, result.items_updated) == (0, 0)
        assert result.metadata['imf_retained_vintages'] == {'KEN': records[0]['vintage'].isoformat()}
    assert len(requests) == 4 and all('periods' not in r.url.params for r in requests)
    payload['GGXCNL_NGDP']['1982'] = '-3.2'
    with Session(pg) as db, db.begin():
        revised = domain.run(db, settings, LIVE)
        assert (revised.items_created, revised.items_updated) == (0, 1)
    assert len(stored(pg)) == 376


def checked_cohort(pg):
    from models import IngestionJob, IngestionStatus, SeedingDomainClaim

    now = datetime.now(timezone.utc)
    cohort = now - timedelta(days=90)
    write(pg, [row(at=cohort)])
    IngestionJob.__table__.create(pg)
    with pg.begin() as c:
        # This unused FK target supplies fixture schema only, not dispatch authority.
        c.exec_driver_sql('CREATE TABLE etl_dispatch_commands (id uuid PRIMARY KEY)')
    SeedingDomainClaim.__table__.create(pg)
    claim = uuid4()
    start, finish = now - timedelta(hours=1, minutes=1), now - timedelta(hours=1)
    with Session(pg) as db, db.begin():
        job = IngestionJob(domain='imf_weo', status=IngestionStatus.COMPLETED,
            dry_run=False, started_at=start.replace(tzinfo=None), finished_at=finish.replace(tzinfo=None),
            meta={'source_mode': 'live', 'seeding_claim_id': str(claim),
                  'imf_retained_vintages': {'KEN': cohort.isoformat()}})
        db.add(job)
        db.flush()
        db.add(SeedingDomainClaim(id=claim, domain='imf_weo', kind='native', job_id=job.id,
            acquired_at=start-timedelta(seconds=1), entered_at=start-timedelta(seconds=1),
            entry_id=uuid4(), returned_at=finish+timedelta(seconds=1), released_at=finish+timedelta(seconds=2)))
    return cohort, finish


def test_public_broader_debt_uses_successful_unchanged_check(pg, monkeypatch):
    import main

    cohort, finish = checked_cohort(pg)
    payload = {'status': 'success', 'stale': True, 'vintage': cohort.isoformat(), 'vintage_age_days': 90}

    async def cached(**kwargs):
        return payload

    monkeypatch.setattr(main, 'DATABASE_AVAILABLE', True)
    monkeypatch.setattr(main, '_get_debt_broader_cached', cached)
    with Session(pg) as db:
        actual = asyncio.run(main.get_debt_broader(db=db))
    assert actual['stale'] is False
    assert actual['last_successful_check_at'] == finish.isoformat()
    assert actual['vintage_age_days'] == 90
    assert payload['stale'] is True  # Shared numerical cache must not be mutated.


@pytest.mark.parametrize('invalid', [
    'dry_run', 'fixture', 'running', 'failed', 'wrong_cohort', 'wrong_claim',
    'reconciled', 'not_returned', 'not_released', 'future', 'before_cohort',
    'before_entry', 'errors', 'missing_pointer', 'no_job',
])
def test_unqualified_receipts_cannot_freshen_old_observations(pg, invalid):
    from models import IngestionJob, IngestionStatus, SeedingDomainClaim
    from services.imf_freshness import with_imf_check_freshness

    cohort, finish = checked_cohort(pg)
    with Session(pg) as db, db.begin():
        job = db.scalars(select(IngestionJob)).one()
        claim = db.scalars(select(SeedingDomainClaim)).one()
        meta = dict(job.meta)
        if invalid == 'dry_run': job.dry_run = True
        elif invalid == 'fixture': meta['source_mode'] = 'fixture'
        elif invalid == 'running': job.status = IngestionStatus.RUNNING
        elif invalid == 'failed': job.status = IngestionStatus.FAILED
        elif invalid == 'wrong_cohort': meta['imf_retained_vintages'] = {'KEN': finish.isoformat()}
        elif invalid == 'wrong_claim': meta['seeding_claim_id'] = str(uuid4())
        elif invalid == 'reconciled':
            claim.reconciled_by, claim.reconciliation = 'fixture_operator', 'isolated test'
        elif invalid == 'not_returned':
            claim.returned_at, claim.released_at, claim.job_id = None, None, None
        elif invalid == 'not_released': claim.released_at = None
        elif invalid == 'future':
            job.finished_at = (finish + timedelta(days=2)).replace(tzinfo=None)
            claim.returned_at = finish + timedelta(days=2, seconds=1)
            claim.released_at = finish + timedelta(days=2, seconds=2)
        elif invalid == 'before_cohort':
            job.started_at = (cohort - timedelta(minutes=1)).replace(tzinfo=None)
            job.finished_at = (cohort - timedelta(seconds=1)).replace(tzinfo=None)
            claim.acquired_at = claim.entered_at = cohort - timedelta(minutes=2)
        elif invalid == 'before_entry':
            job.started_at = (finish - timedelta(days=1)).replace(tzinfo=None)
        elif invalid == 'errors': job.errors = ['refused source']
        elif invalid == 'missing_pointer': meta.pop('imf_retained_vintages')
        elif invalid == 'no_job':
            db.delete(claim)
            db.flush()
            db.delete(job)
        job.meta = meta
    with Session(pg) as db:
        result = with_imf_check_freshness(db, {'status': 'success'}, cohort)
        assert result['stale'] is True
        assert result['last_successful_check_at'] is None
        assert result['freshness_basis'] == 'retained_acquisition'
        assert db.scalar(text('SELECT 1')) == 1


@pytest.mark.parametrize('present', ['neither', 'jobs_only'])
def test_missing_optional_receipts_keep_transaction_usable(pg, present):
    from models import IngestionJob
    from services.imf_freshness import with_imf_check_freshness

    if present == 'jobs_only': IngestionJob.__table__.create(pg)
    with Session(pg) as db:
        result = with_imf_check_freshness(db, {}, datetime.now(timezone.utc) - timedelta(days=90))
        assert result['stale'] is True and result['last_successful_check_at'] is None
        assert db.scalar(text('SELECT 1')) == 1


def test_future_cohort_is_not_fresh(pg):
    from services.imf_freshness import with_imf_check_freshness

    with Session(pg) as db:
        result = with_imf_check_freshness(db, {}, datetime.now(timezone.utc) + timedelta(days=1))
        assert result['stale'] is True


def test_old_check_does_not_hide_old_data(pg):
    from models import IngestionJob, SeedingDomainClaim
    from services.imf_freshness import with_imf_check_freshness

    cohort, finish = checked_cohort(pg)
    with Session(pg) as db, db.begin():
        job = db.scalars(select(IngestionJob)).one()
        claim = db.scalars(select(SeedingDomainClaim)).one()
        job.started_at -= timedelta(days=61)
        job.finished_at -= timedelta(days=61)
        for column in ('acquired_at', 'entered_at', 'returned_at', 'released_at'):
            setattr(claim, column, getattr(claim, column) - timedelta(days=61))
    with Session(pg) as db:
        result = with_imf_check_freshness(db, {}, cohort)
        assert result['stale'] is True
        assert result['freshness_basis'] == 'qualified_live_check'
        assert result['check_age_days'] == 61


@pytest.mark.parametrize('zone', ['UTC', 'America/Chicago'])
@pytest.mark.parametrize('skew', [-2, 0, 2])
def test_actual_native_clock_contract_qualifies_without_redating(pg, zone, skew):
    import time
    from sqlalchemy import event
    from sqlalchemy.orm import sessionmaker
    from models import EtlDispatchDomain, IngestionJob, IngestionStatus, SeedingDomainClaim
    from seeding.exclusion import enter_domain
    from services.imf_freshness import with_imf_check_freshness

    def set_zone(connection):
        connection.execute(text("SELECT set_config('TimeZone', :zone, false)"), {'zone': zone})
        connection.commit()

    event.listen(pg, 'engine_connect', set_zone)
    cohort = datetime.now(timezone.utc) - timedelta(days=90)
    write(pg, [row(at=cohort)])
    IngestionJob.__table__.create(pg)
    with pg.begin() as c:
        c.exec_driver_sql('CREATE TABLE etl_dispatch_commands (id uuid PRIMARY KEY)')
    SeedingDomainClaim.__table__.create(pg)
    EtlDispatchDomain.__table__.create(pg)
    factory = sessionmaker(pg)
    execution = enter_domain(factory, 'imf_weo', False)
    try:
        start = datetime.now(timezone.utc) + timedelta(seconds=skew)
        finish = start + timedelta(microseconds=10)
        with factory() as db, db.begin():
            job = IngestionJob(domain='imf_weo', status=IngestionStatus.COMPLETED,
                dry_run=False, started_at=start, finished_at=finish, errors=[],
                items_processed=1, items_created=0, items_updated=0,
                meta={'source_mode': 'live', 'seeding_claim_id': str(execution.identity),
                      'imf_retained_vintages': {'KEN': cohort.isoformat()}})
            db.add(job)
            db.flush()
            job_id = job.id
        execution.acknowledge(job_id)
    finally:
        execution.close()
    if skew > 0:
        with factory() as db:
            assert with_imf_check_freshness(db, {}, cohort)['last_successful_check_at'] is None
        time.sleep(skew + .2)
    with factory() as db:
        result = with_imf_check_freshness(db, {}, cohort)
        assert result['stale'] is False
        assert result['last_successful_check_at'] == finish.isoformat()
        assert result['vintage_age_days'] == 90

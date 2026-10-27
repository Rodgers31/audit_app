"""Actual PostgreSQL contract for observation revisions, not fetch snapshots."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from uuid import uuid4

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

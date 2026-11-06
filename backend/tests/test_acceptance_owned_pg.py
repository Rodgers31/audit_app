"""Regression controls for the two supported nightly PostgreSQL consumers."""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from models import IngestionJob, IngestionStatus
from tests import test_nightly_workflow_validation as population
from tests import test_refresh_current_run_postgres as current


BASE = 'postgresql+psycopg2://postgres@127.0.0.1:55432/auditgava_refresh_fixture'
HOSTILE = [
    BASE + '?host=elsewhere.invalid', BASE + '?hostaddr=192.0.2.1',
    BASE + '?host=%2Ftmp', BASE + '?%68ost=elsewhere.invalid',
    BASE + '?port=5432', BASE + '?dbname=postgres', BASE + '?user=another',
    BASE + '?password=inert', BASE + '?service=inert',
    BASE + '?options=-csearch_path%3Dpublic', BASE + '?connect_timeout=0',
    BASE + '#inert', BASE.replace('127.0.0.1', '%31%32%37.0.0.1'),
    BASE.replace('55432', '5432'), BASE.replace('postgres@', 'postgres:inert@'),
    BASE.replace('postgresql+psycopg2', 'postgresql+psycopg'),
    BASE.replace('/auditgava_refresh_fixture', '/%61uditgava_refresh_fixture'),
]


@pytest.mark.parametrize('entry', ['population', 'current'])
@pytest.mark.parametrize('url', HOSTILE)
def test_redirects_refuse_before_engine_or_ddl(tmp_path, monkeypatch, entry, url):
    monkeypatch.setenv('REFRESH_FIXTURE_PG_URL', url)
    monkeypatch.setenv('REFRESH_FIXTURE_OWNED', 'true')
    monkeypatch.setenv('REFRESH_FIXTURE_TOKEN', 'a' * 32)
    touched = []
    def forbidden(*args, **kwargs):
        touched.append(True)
        raise AssertionError('engine creation reached for hostile target')
    # Patch the genuine SQLAlchemy entry and both historical imported aliases.
    monkeypatch.setattr('sqlalchemy.create_engine', forbidden)
    monkeypatch.setattr(population, 'create_engine', forbidden)
    monkeypatch.setattr(current, 'create_engine', forbidden)
    with pytest.raises(RuntimeError, match='[Oo]wned|[Ff]ixture|[Pp]ostgreSQL'):
        if entry == 'population':
            population.population_check(tmp_path, [])
        else:
            next(current.fixture_db.__wrapped__(tmp_path))
    assert touched == []


@pytest.mark.parametrize('entry', ['population', 'current'])
@pytest.mark.parametrize('key', ['PGHOST', 'PGHOSTADDR', 'PGPORT', 'PGDATABASE',
                                 'PGUSER', 'PGPASSWORD', 'PGSERVICE', 'PGSERVICEFILE',
                                 'PGOPTIONS', 'PGPASSFILE', 'PGCONNECT_TIMEOUT'])
def test_libpq_environment_refuses_before_engine(tmp_path, monkeypatch, entry, key):
    monkeypatch.setenv('REFRESH_FIXTURE_PG_URL', BASE)
    monkeypatch.setenv('REFRESH_FIXTURE_OWNED', 'true')
    monkeypatch.setenv('REFRESH_FIXTURE_TOKEN', 'a' * 32)
    monkeypatch.setenv(key, 'inert')
    touched = []
    def forbidden(*args, **kwargs):
        touched.append(True)
        raise AssertionError('engine creation reached for ambient override')
    monkeypatch.setattr('sqlalchemy.create_engine', forbidden)
    monkeypatch.setattr(population, 'create_engine', forbidden)
    monkeypatch.setattr(current, 'create_engine', forbidden)
    with pytest.raises(RuntimeError, match='[Oo]wned|[Ff]ixture|[Pp]ostgreSQL'):
        if entry == 'population': population.population_check(tmp_path, [])
        else: next(current.fixture_db.__wrapped__(tmp_path))
    assert touched == []


def test_population_cleanup_preserves_unrelated_ingestion_jobs(tmp_path):
    url = os.environ.get('REFRESH_FIXTURE_PG_URL')
    if not url: pytest.fail('actual owned PostgreSQL is required for isolation control')
    engine = create_engine(url)
    IngestionJob.__table__.create(engine)
    try:
        with Session(engine) as db:
            job = IngestionJob(domain='inert-unrelated', status=IngestionStatus.COMPLETED,
                               items_processed=1, items_created=0, items_updated=0)
            db.add(job); db.commit(); original_id = job.id
        before = inspect(engine).get_table_names()
        assert population.population_check(tmp_path, [(1, 2025, 57_532_493)]) == []
        assert inspect(engine).get_table_names() == before
        with Session(engine) as db:
            assert db.scalar(select(IngestionJob.id)) == original_id
    finally:
        IngestionJob.__table__.drop(engine, checkfirst=True)
        engine.dispose()


def test_population_and_current_run_overlap_and_subsequent_fixtures_survive(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    first = current.fixture_db.__wrapped__(tmp_path / 'first')
    (tmp_path / 'first').mkdir()
    engine, _ = next(first)
    try:
        with Session(engine) as db: before = list(db.scalars(select(IngestionJob.id)))
        assert len(before) == 15
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(population.population_check, tmp_path,
                               [(1, 2025, 57_532_493)]).result(timeout=15) == []
        with Session(engine) as db: assert list(db.scalars(select(IngestionJob.id))) == before
    finally:
        first.close()
    (tmp_path / 'next').mkdir()
    second = current.fixture_db.__wrapped__(tmp_path / 'next')
    next_engine, _ = next(second)
    try:
        with Session(next_engine) as db: assert len(list(db.scalars(select(IngestionJob.id)))) == 15
    finally:
        second.close()

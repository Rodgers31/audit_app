"""Replay existing aggregate controls in Operations' dedicated PostgreSQL lane."""
from contextlib import contextmanager
import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from harness import Probe, recording_cursor
from models import IngestionJob
from test_compact_ingestion_stats import (
    seed_jobs,
    test_stats_output_is_equivalent_while_selected_rows_and_bytes_are_bounded,
    test_empty_and_future_only_stats_preserve_zero_semantics,
    test_summary_selected_byte_estimate_excludes_diagnostic_bodies,
)


@pytest.fixture
def pg_fixture():
    raw = os.environ.get('OPERATIONS_TEST_DATABASE_URL')
    if not raw:
        pytest.skip('Set explicit Operations loopback database URL')
    url = make_url(raw)
    assert url.drivername == 'postgresql+psycopg2' and url.host == '127.0.0.1'
    assert url.port == 55472 and url.database == 'operations_batch6' and not url.query
    url = url.set(query={'hostaddr':'127.0.0.1'})
    schema = 'operations_batch6_' + uuid4().hex
    admin = create_engine(url, hide_parameters=True)
    with admin.begin() as conn:
        conn.execute(text('CREATE SCHEMA ' + schema))
    probe = Probe()
    engine = create_engine(url, hide_parameters=True,
        connect_args={'options':'-csearch_path='+schema, 'cursor_factory':recording_cursor(probe)})
    IngestionJob.__table__.create(engine)
    try:
        yield engine, probe
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
        admin.dispose()


def test_list_projects_counts_without_large_diagnostic_transfer(pg_fixture):
    from routers.admin import list_ingestion_jobs
    engine, probe = pg_fixture
    seed_jobs(engine)
    with Session(engine) as db:
        with probe.capture():
            result = asyncio.run(list_ingestion_jobs(domain=None,status=None,days=30,page=1,page_size=20,db=db))
    assert result.total == 80 and len(result.jobs) == 20 and result.has_more
    assert all(job.error_count == 1 and job.diagnostics_redacted and job.metadata == {} for job in result.jobs)
    samples = probe.selected('ingestion_jobs')
    print('OPERATIONS_LIST_TRANSFER', probe.summary(samples))
    assert len(samples) == 2 and sum(s.rows for s in samples) == 21
    assert sum(s.selected_value_bytes for s in samples) < 8192
    assert not any('errors' in s.columns or 'metadata' in s.columns for s in samples)


@pytest.mark.parametrize('diagnostic', [None, {}, 'private scalar', True, []])
def test_pg_diagnostic_shapes_do_not_crash_or_expose_bodies(pg_fixture, diagnostic):
    from models import IngestionStatus
    from routers.admin import list_ingestion_jobs
    engine,_=pg_fixture
    with Session(engine) as db:
        db.add(IngestionJob(domain='audits',status=IngestionStatus.FAILED,errors=diagnostic,meta={'private':'must not leak'}))
        db.commit()
        result=asyncio.run(list_ingestion_jobs(domain=None,status=None,days=30,page=1,page_size=20,db=db))
        assert len(result.jobs)==1
        assert 'private' not in result.model_dump_json()

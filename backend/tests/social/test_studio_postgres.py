"""Owned Batch15 PostgreSQL fixture on reserved port55402; no production DSN."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path
from uuid import UUID

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from social.service import SocialError
from social.studio.analytics import collect
from social.studio.models import MetricCollection, MetricObservation, RenderJob
from social.studio.runner import run_job
from social.studio.service import StudioService
from test_domain_support import call
from test_studio import FixtureMetrics, composition, published, runtime, source


@pytest.fixture(scope='module')
def pg():
    value = os.environ.get('B15_RENDERING_TEST_DATABASE_URL')
    if value is None:
        pytest.skip('Owned rendering PostgreSQL fixture was not configured')
    url = make_url(value)
    if '?' in value or url.drivername != 'postgresql+psycopg2' or url.host != '127.0.0.1' or url.port != 55402 or url.database != 'b15_rendering_final' or url.query:
        raise ValueError('Use only owned rendering PostgreSQL database on port55402')
    engine = create_engine(url.set(query={'hostaddr': '127.0.0.1'}), pool_size=4, max_overflow=0)
    with engine.connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == 'a705b15a0001'
    yield engine
    engine.dispose()


def test_owned_full_chain_schema_rls_no_grants_and_guards(pg):
    names = ('social_render_jobs', 'social_metric_collections', 'social_metric_observations')
    with pg.connect() as conn:
        for name in names:
            assert conn.execute(text('SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:name AS regclass)'), {'name': name}).scalar_one()
            assert not conn.execute(text("SELECT EXISTS(SELECT 1 FROM pg_class c, LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a WHERE c.oid=CAST(:name AS regclass) AND a.grantee=0)"), {'name': name}).scalar_one()
        assert {c['name'] for c in inspect(conn).get_columns('social_render_jobs')} >= {'attempt', 'retry_of_id', 'approved_sha256'}


def test_real_pg_render_chain_idempotency_checksum_and_sql_immutability(pg, runtime):
    with Session(pg, expire_on_commit=False) as db:
        post = source(db)
    body = composition(post['revision_id'])
    def enqueue(_):
        with Session(pg) as db:
            return call(db, body, lambda svc: StudioService(svc, runtime).create(body))[1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(enqueue, range(2)))
    assert values[0]['id'] == values[1]['id']
    job_id = UUID(values[0]['id'])
    assert run_job(sessionmaker(bind=pg), runtime, job_id) == 'ready'
    with Session(pg) as db:
        row = db.get(RenderJob, job_id)
        from social.studio.contracts import Approval
        body = Approval(expected_version=row.version, sha256=row.sha256, review_attestation={'facts_checked': True, 'sources_checked': True})
        result = call(db, body, lambda svc: StudioService(svc, runtime).approve(job_id, body))[1]
        assert result['sha256'] == result['approved_sha256']
    for sql in ("UPDATE social_render_jobs SET composition=jsonb_set(composition,'{title}','\"altered\"') WHERE id=:id", "UPDATE social_render_jobs SET sha256=repeat('0',64) WHERE id=:id", 'DELETE FROM social_render_jobs WHERE id=:id'):
        with pytest.raises(IntegrityError), pg.begin() as conn:
            conn.execute(text(sql), {'id': job_id})


def test_real_pg_collection_quota_and_immutable_observations(pg):
    with Session(pg, expire_on_commit=False) as db:
        target_id = published(db).id
    factory = sessionmaker(bind=pg)
    def execute(_):
        try:
            collect(factory, target_id, {'facebook': FixtureMetrics()}, enabled=True)
            return 'collected'
        except SocialError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(execute, range(2))) == ['METRICS_QUOTA', 'collected']
    with Session(pg) as db:
        assert db.scalar(select(func.count()).select_from(MetricCollection).where(MetricCollection.target_id == target_id)) == 1
        collection = db.scalar(select(MetricCollection).where(MetricCollection.target_id == target_id))
        observation = db.scalar(select(MetricObservation).where(MetricObservation.collection_id == collection.id))
        observation_id = observation.id
    with pytest.raises(IntegrityError), pg.begin() as conn:
        conn.execute(text("UPDATE social_metric_observations SET metric='{}'::jsonb WHERE id=:id"), {'id': observation_id})
    path = Path(__file__).resolve().parents[2] / 'alembic/versions/a705b15a0001_social_studio.py'
    spec = importlib.util.spec_from_file_location('studio_candidate_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(RuntimeError, match='history'), pg.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            module.downgrade()

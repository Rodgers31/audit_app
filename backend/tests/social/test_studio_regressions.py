from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from social.models import Base, SOCIAL_TABLES
from social.service import SocialError
from social.studio.analytics import collect
from social.studio.contracts import Approval, Composition
from social.studio.models import MetricCollection, RenderJob
from social.studio.runner import run_job
from social.studio.service import StudioService
from test_domain_support import call, db
from test_studio import FixtureMetrics, composition, enqueue, published, runtime, source


def test_durable_input_corruption_refuses_render_and_approval(db, runtime):
    queued = enqueue(db, runtime, source(db))
    job_id = UUID(queued['id'])
    corrupt = {**queued['composition'], 'title': 'Corrupted persisted composition'}
    db.execute(update(RenderJob).where(RenderJob.id == job_id).values(composition=corrupt))
    db.commit()
    with pytest.raises(SocialError, match='RENDER_INTEGRITY'):
        run_job(sessionmaker(bind=db.bind), runtime, job_id)
    db.expire_all()
    assert db.get(RenderJob, job_id).state == 'queued'
    # Restore fixture bytes, execute, then corrupt only after actual inspection.
    db.execute(update(RenderJob).where(RenderJob.id == job_id).values(composition=queued['composition']))
    db.commit()
    assert run_job(sessionmaker(bind=db.bind), runtime, job_id) == 'ready'
    db.execute(update(RenderJob).where(RenderJob.id == job_id).values(composition=corrupt))
    db.commit()
    row = db.get(RenderJob, job_id, populate_existing=True)
    approval = Approval(expected_version=row.version, sha256=row.sha256, review_attestation={'facts_checked': True, 'sources_checked': True})
    with pytest.raises(SocialError, match='RENDER_INTEGRITY'):
        call(db, approval, lambda svc: StudioService(svc, runtime).approve(job_id, approval))
    db.expire_all()
    assert db.get(RenderJob, job_id).approved_sha256 is None


def test_sqlite_concurrent_collection_reserves_once(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'quota.sqlite'), connect_args={'check_same_thread': False, 'timeout': 3})
    Base.metadata.create_all(engine, tables=SOCIAL_TABLES)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        target_id = published(db).id
    inserting, release, second_entered = threading.Event(), threading.Event(), threading.Event()
    first_thread = None
    @event.listens_for(engine, 'before_cursor_execute')
    def gate(conn, cursor, statement, params, context, many):
        nonlocal first_thread
        if statement == 'BEGIN IMMEDIATE' and inserting.is_set():
            second_entered.set()
        if statement.startswith('INSERT INTO social_metric_collections') and not inserting.is_set():
            first_thread = threading.get_ident()
            inserting.set()
            if not release.wait(3):
                raise RuntimeError('Fixture failed to release owned writer')
    def execute():
        try:
            collect(factory, target_id, {'facebook': FixtureMetrics()}, enabled=True)
            return 'collected'
        except SocialError as error:
            return error.code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(execute)
            assert inserting.wait(2)
            second = pool.submit(execute)
            assert second_entered.wait(2)
            assert not second.done()
            release.set()
            assert sorted([first.result(timeout=15), second.result(timeout=15)]) == ['METRICS_QUOTA', 'collected']
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(MetricCollection)) == 1
    finally:
        release.set()
        engine.dispose()


class OrphanMetrics(FixtureMetrics):
    def __init__(self, path):
        self.path = path

    def collect(self, request):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        Path(self.path).write_text(json.dumps({'pid': child.pid, 'pgid': os.getpgrp()}))
        return super().collect(request)


def test_provider_success_with_surviving_descendant_is_failure_and_reaped(db, tmp_path):
    target = published(db)
    record = tmp_path / 'owned-process.json'
    with pytest.raises(SocialError, match='METRICS_COLLECTION_FAILED'):
        collect(sessionmaker(bind=db.bind), target.id, {'facebook': OrphanMetrics(str(record))}, enabled=True)
    owned = json.loads(record.read_text())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = subprocess.run(['/bin/ps', '-p', str(owned['pid']), '-o', 'stat='], capture_output=True, text=True, check=False)
        if not result.stdout.strip() or result.stdout.strip().startswith('Z'):
            break
        time.sleep(0.05)
    else:
        pytest.fail('Owned provider descendant remains running')
    db.expire_all()
    assert db.scalar(select(MetricCollection).where(MetricCollection.target_id == target.id)).state == 'failed'


def test_explicit_retry_is_new_bounded_attempt_without_inherited_approval(db, runtime):
    from social.contracts import VersionCommand
    queued = enqueue(db, runtime, source(db))
    original_id = UUID(queued['id'])
    command = VersionCommand(expected_version=1)
    cancelled = call(db, command, lambda svc: StudioService(svc, runtime).cancel(original_id, 1))[1]
    retry_command = VersionCommand(expected_version=cancelled['version'])
    retry = call(db, retry_command, lambda svc: StudioService(svc, runtime).retry(original_id, retry_command.expected_version))[1]
    assert retry['id'] != queued['id'] and retry['attempt'] == 2 and retry['retry_of_id'] == queued['id']
    assert retry['approved_sha256'] is None and retry['sha256'] is None
    assert retry['input_hash'] == queued['input_hash']
    assert call(db, retry_command, lambda svc: StudioService(svc, runtime).retry(original_id, retry_command.expected_version))[1]['id'] == retry['id']
    retry_id = UUID(retry['id'])
    assert run_job(sessionmaker(bind=db.bind), runtime, retry_id) == 'ready'
    with pytest.raises(SocialError, match='RENDER_RETRY_REFUSED'):
        call(db, VersionCommand(expected_version=3), lambda svc: StudioService(svc, runtime).retry(retry_id, 3))
    db.expire_all()
    assert db.get(RenderJob, original_id).state == 'cancelled'


@pytest.mark.parametrize('value', [True, -1, float('nan'), float('inf'), '0'])
def test_metric_numeric_shapes_are_strict(value):
    from datetime import timedelta
    from pydantic import ValidationError
    from social.studio.contracts import Metric
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        Metric(name='views', api_version='fixture', unit='count', period='day', window_start=now-timedelta(days=1), window_end=now-timedelta(seconds=1), collected_at=now, available_until=now+timedelta(hours=1), status='available', value=value, reason=None)


@pytest.mark.parametrize('template', ['debt_update', 'audit_finding', 'budget_update', 'new_report', 'did_you_know', 'educational'])
def test_templates_require_roles_and_resolved_placeholders(template):
    from social.studio.contracts import TEMPLATE_DEFINITIONS
    from uuid import uuid4
    from pydantic import ValidationError
    roles = TEMPLATE_DEFINITIONS[template]['required_facts']
    facts = [{'id': r, 'text': 'Reviewed factual text', 'source_url': 'https://example.org/report'} for r in roles]
    body = composition(uuid4(), template=template, facts=facts, scenes=[{'fact_id': roles[0], 'seconds': 15}])
    assert body.template == template
    for invalid in ('{{amount}}', '[amount]', '<value>'):
        with pytest.raises(ValidationError):
            Composition.model_validate({**body.model_dump(mode='json'), 'title': invalid})
    with pytest.raises(ValidationError):
        Composition.model_validate({**body.model_dump(mode='json'), 'facts': facts[:-1]})

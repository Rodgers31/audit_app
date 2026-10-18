"""Run with PYTHONPATH=backend pytest --confcutdir=backend/tests/social."""
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import shutil
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from social.contracts import PatchPost
from social.models import SocialMediaAsset, SocialPost, SocialPostTarget, SocialPublication
from social.service import SocialError, SocialService
from social.studio.analytics import collect, observations
from social.studio.contracts import Approval, Composition, Metric
from social.studio.models import MetricCollection, RenderJob
from social.studio.runner import recover_interrupted, run_job
from social.studio.runtime import StudioRuntime, configure_studio, verified_bytes
from social.studio.service import StudioService, calendar
from test_domain_support import ACTOR, account, call, db, draft_body


def composition(revision_id, kind='graphic', **updates):
    value = {'template': 'new_report', 'kind': kind, 'revision_id': str(revision_id), 'title': 'Reviewed report', 'facts': [{'id': role, 'text': 'The reviewed report is available.', 'source_url': 'https://example.org/report'} for role in ('report', 'publisher', 'publication_date')], 'scenes': [{'fact_id': role, 'seconds': 5} for role in ('report', 'publisher', 'publication_date')] if kind == 'video' else [{'fact_id': 'report', 'seconds': 15}]}
    value.update(updates)
    return Composition.model_validate(value)


@pytest.fixture
def runtime(tmp_path):
    root = tmp_path / 'render'
    root.mkdir(mode=0o700)
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        pytest.fail('Real local FFmpeg/ffprobe are required for studio acceptance')
    return StudioRuntime(True, root.resolve(), ffmpeg, ffprobe).validate()


def source(db):
    body = draft_body(references=[{'url': 'https://example.org/report', 'label': 'Report'}])
    return call(db, body, lambda svc: svc.create(body))[1]


def enqueue(db, runtime, post, kind='graphic'):
    body = composition(post['revision_id'], kind)
    return call(db, body, lambda svc: StudioService(svc, runtime).create(body))[1]


def test_render_real_graphic_deterministic_restart_approval_and_attach(db, runtime):
    post = source(db)
    queued = enqueue(db, runtime, post)
    factory = sessionmaker(bind=db.bind, expire_on_commit=False)
    assert run_job(factory, runtime, UUID(queued['id'])) == 'ready'
    db.expire_all()
    row = db.get(RenderJob, UUID(queued['id']))
    data = verified_bytes(runtime, row)
    assert data.startswith(b'\x89PNG') and row.inspection['width'] == 720 and row.inspection['height'] == 1280
    assert hashlib.sha256(data).hexdigest() == row.sha256
    expected_sha, version = row.sha256, row.version
    approval = Approval(expected_version=version, sha256=expected_sha, review_attestation={'facts_checked': True, 'sources_checked': True})
    approved = call(db, approval, lambda svc: StudioService(svc, runtime).approve(row.id, approval))[1]
    assert approved['approved_sha256'] == expected_sha
    # Existing ready intake is the only bridge: this test supplies inspected fixture bytes.
    asset_id = uuid4()
    db.add(SocialMediaAsset(id=asset_id, storage_provider='fixture', bucket='private', storage_key=str(asset_id), original_filename='card.png', mime_type='image/png', byte_size=len(data), sha256=expected_sha, width=720, height=1280, codec_metadata={}, state='ready', created_by=ACTOR))
    db.commit()
    body = PatchPost(expected_version=post['version'])
    attached = call(db, body, lambda svc: StudioService(svc, runtime).attach(row.id, asset_id, body.expected_version))[1]
    assert attached['editorial_state'] == 'draft'
    assert attached['revision_id'] != post['revision_id']
    assert attached['document']['master']['media'][0]['asset_id'] == str(asset_id)
    assert attached['document']['master']['media'][0]['alt_text'] == ' '.join(f['text'] for f in row.composition['facts'])
    # Same template/source produces the same actual graphics bytes across jobs.
    another = source(db)
    second = enqueue(db, runtime, another)
    assert run_job(factory, runtime, UUID(second['id'])) == 'ready'
    db.expire_all()
    assert db.get(RenderJob, UUID(second['id'])).sha256 == expected_sha


def test_real_video_decodes_and_has_timed_caption_sidecar(db, runtime):
    post = source(db)
    queued = enqueue(db, runtime, post, 'video')
    assert run_job(sessionmaker(bind=db.bind), runtime, UUID(queued['id'])) == 'ready'
    db.expire_all()
    row = db.get(RenderJob, UUID(queued['id']))
    assert row.inspection['duration_ms'] == 15000
    assert row.inspection['mime_type'] == 'video/mp4'
    assert row.inspection['codec_metadata']['video_codec'] == 'h264'
    assert '00:00:00,000 --> 00:00:05,000' in (runtime.directory(row.id) / 'captions.srt').read_text()
    assert row.sha256 == hashlib.sha256(verified_bytes(runtime, row)).hexdigest()


def test_missing_tool_failed_render_not_ready_and_cancel(db, runtime):
    post = source(db)
    queued = enqueue(db, runtime, post, 'video')
    # /usr/bin/false is executable but does not render: actual execution fails closed.
    broken = StudioRuntime(True, runtime.root, '/usr/bin/false', runtime.ffprobe)
    assert run_job(sessionmaker(bind=db.bind), broken, UUID(queued['id'])) == 'failed'
    db.expire_all()
    failed = db.get(RenderJob, UUID(queued['id']))
    assert failed.sha256 is None and failed.safe_error
    other = source(db)
    second = enqueue(db, runtime, other)
    from social.contracts import VersionCommand
    body = VersionCommand(expected_version=1)
    cancelled = call(db, body, lambda svc: StudioService(svc, runtime).cancel(UUID(second['id']), 1))[1]
    assert cancelled['state'] == 'cancelled'
    with pytest.raises(SocialError, match='RENDER_NOT_QUEUED'):
        run_job(sessionmaker(bind=db.bind), runtime, UUID(second['id']))


def test_wrong_checksum_missing_bytes_changed_revision_and_duplicate_input(db, runtime):
    post = source(db)
    queued = enqueue(db, runtime, post)
    assert enqueue(db, runtime, post)['id'] == queued['id']
    assert run_job(sessionmaker(bind=db.bind), runtime, UUID(queued['id'])) == 'ready'
    db.expire_all()
    row = db.get(RenderJob, UUID(queued['id']))
    wrong = Approval(expected_version=row.version, sha256='0' * 64, review_attestation={'facts_checked': True, 'sources_checked': True})
    with pytest.raises(SocialError):
        call(db, wrong, lambda svc: StudioService(svc, runtime).approve(row.id, wrong))
    good = Approval(expected_version=row.version, sha256=row.sha256, review_attestation={'facts_checked': True, 'sources_checked': True})
    path = runtime.directory(row.id) / 'card-0.png'
    original = path.read_bytes()
    path.write_bytes(b'changed')
    with pytest.raises(SocialError, match='RENDER_INTEGRITY'):
        call(db, good, lambda svc: StudioService(svc, runtime).approve(row.id, good))
    path.write_bytes(original)
    patch = PatchPost(expected_version=post['version'], title='Revised title')
    call(db, patch, lambda svc: svc.patch(UUID(post['id']), patch))
    with pytest.raises(SocialError, match='VERSION_CONFLICT'):
        call(db, good, lambda svc: StudioService(svc, runtime).approve(row.id, good))


@pytest.mark.parametrize('bad', [True, 0, -1, float('nan'), float('inf'), None])
def test_hostile_composition_duration(bad):
    with pytest.raises(ValidationError):
        composition(uuid4(), scenes=[{'fact_id': 'fact-1', 'seconds': bad}])


def test_evidence_and_local_enablement_guards(db, runtime, tmp_path):
    post = source(db)
    body = composition(post['revision_id'], facts=[{'id': role, 'text': 'Unverified', 'source_url': 'https://other.example/report'} for role in ('report', 'publisher', 'publication_date')])
    with pytest.raises(SocialError, match='RENDER_EVIDENCE_REQUIRED'):
        call(db, body, lambda svc: StudioService(svc, runtime).create(body))
    with pytest.raises(SocialError, match='RENDER_UNAVAILABLE'):
        StudioRuntime().require()
    with pytest.raises(ValueError):
        StudioRuntime(True, tmp_path / 'absent', runtime.ffmpeg, runtime.ffprobe).validate()
    app = SimpleNamespace(state=SimpleNamespace())
    configure_studio(app, {})
    assert app.state.social_studio_runtime.enabled is False
    with pytest.raises(ValueError):
        configure_studio(app, {'SOCIAL_STUDIO_ENABLED': 'yes'})


def test_restart_recovery_retains_failed_history(db, runtime):
    job = enqueue(db, runtime, source(db))
    row = db.get(RenderJob, UUID(job['id']))
    row.state, row.started_at, row.token = 'running', datetime.now(timezone.utc), uuid4()
    token = row.token
    db.commit()
    factory = sessionmaker(bind=db.bind)
    with pytest.raises(SocialError, match='RENDER_RECOVERY_REFUSED'):
        recover_interrupted(factory, row.id)
    recover_interrupted(factory, row.id, datetime.now(timezone.utc) + timedelta(seconds=181))
    db.expire_all()
    assert db.get(RenderJob, row.id).state == 'failed' and row.token == token


def published(db, platform='facebook'):
    acc = account(db, platform)
    post = source(db)
    pub = SocialPublication(id=uuid4(), post_id=UUID(post['id']), revision_id=UUID(post['revision_id']), authorization_kind='human', approved_by=ACTOR, approved_at=datetime.now(timezone.utc), approved_hash='a' * 64)
    db.add(pub)
    db.flush()
    target = SocialPostTarget(id=uuid4(), publication_id=pub.id, account_id=acc.id, resolved_payload={}, payload_hash='b' * 64, capability_version='fixture', state='published', primary_remote_id='remote-fixture', visibility_state='public', published_at=datetime.now(timezone.utc), confirmation_kind='fixture')
    db.add(target)
    db.commit()
    return target


class FixtureMetrics:
    platform = 'facebook'
    zero_cost = True

    def collect(self, request):
        now = datetime.now(timezone.utc)
        return (Metric(name='post_impressions', api_version='fixture-v1', unit='count', period='day', window_start=now-timedelta(days=1), window_end=now-timedelta(seconds=1), collected_at=now, available_until=now+timedelta(hours=1), status='available', value=0, reason=None), Metric(name='post_reach', api_version='fixture-v1', unit='unique_accounts', period='lifetime', window_start=now-timedelta(days=1), window_end=now-timedelta(seconds=1), collected_at=now, available_until=now+timedelta(hours=1), status='unavailable', value=None, reason='permission_missing'))


def test_provider_metrics_zero_unavailable_stale_quota_and_default_off(db):
    target = published(db)
    factory = sessionmaker(bind=db.bind)
    with pytest.raises(SocialError, match='ANALYTICS_DISABLED'):
        collect(factory, target.id, {'facebook': FixtureMetrics()})
    with pytest.raises(SocialError, match='METRICS_UNAVAILABLE'):
        collect(factory, target.id, {}, enabled=True)
    collect(factory, target.id, {'facebook': FixtureMetrics()}, enabled=True)
    result = observations(db, target.id)
    metrics = result['collections'][0]['metrics']
    assert sorted((m['name'], m['value'], m['status']) for m in metrics) == [('post_impressions', 0, 'available'), ('post_reach', None, 'unavailable')]
    assert all(m['freshness'] == 'fresh' for m in metrics)
    stale = observations(db, target.id, now=datetime.now(timezone.utc) + timedelta(hours=2))
    assert all(m['freshness'] == 'stale' for m in stale['collections'][0]['metrics'])
    with pytest.raises(SocialError, match='METRICS_QUOTA'):
        collect(factory, target.id, {'facebook': FixtureMetrics()}, enabled=True)


class EmptyMetrics(FixtureMetrics):
    def collect(self, request):
        return ()


def test_empty_provider_result_consumes_quota_and_x_always_blocked(db):
    target = published(db)
    factory = sessionmaker(bind=db.bind)
    with pytest.raises(SocialError, match='METRICS_COLLECTION_FAILED'):
        collect(factory, target.id, {'facebook': EmptyMetrics()}, enabled=True)
    row = db.scalar(select(MetricCollection).where(MetricCollection.target_id == target.id))
    assert row.state == 'failed'
    x = published(db, 'x')
    with pytest.raises(SocialError, match='METRICS_UNAVAILABLE'):
        collect(factory, x.id, {'x': SimpleNamespace(platform='x', zero_cost=True)}, enabled=True)


def test_calendar_window_guards_and_actual_schedule(db):
    target = published(db)
    publication = db.get(SocialPublication, target.publication_id)
    now = datetime.now(timezone.utc)
    publication.scheduled_for, publication.schedule_timezone = now, 'Africa/Nairobi'
    db.commit()
    rows = calendar(db, now - timedelta(hours=1), now + timedelta(hours=1), 1)
    assert rows['items'][0]['publication_id'] == str(publication.id)
    assert rows['items'][0]['timezone'] == 'Africa/Nairobi'
    with pytest.raises(SocialError):
        calendar(db, now, now + timedelta(days=32), 1)
    with pytest.raises(SocialError):
        calendar(db, now.replace(tzinfo=None), now, 1)

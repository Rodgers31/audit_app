"""Mounted API + actual signer/R2 port; inert SDK transport, nonempty cold restore.

SQLite here measures capsule feasibility, not PostgreSQL DDL/ACL acceptance.
The separate PG case exercises the same capsule against real migrated tables.
"""
from dataclasses import replace
import hashlib
from io import BytesIO
import json
from uuid import UUID, uuid4

from PIL import Image
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session

from social.media.config import MediaConfig
from social.media.inspection import LocalInspector
from social.media.models import SocialMediaBudget, SocialMediaUpload
from social.media.recovery import capture_stage_a_rows, capture_stage_a_payloads, encode_rows, restore_stage_a_rows, verify_stage_a_payloads, MODELS, RecoveryScopeError
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.models import Base, SocialAuditEvent, SocialPost, SocialPostRevision
from social.studio.models import RenderJob
from social.privacy.models import SocialPrivacyReceipt
from test_manual_media_workflow import mounted_client, BASE, headers
from test_media_owned_writes import concrete_runtime
from test_media_support import ACTOR, media, media_db


def jpeg():
    out = BytesIO()
    Image.new('RGB', (1080, 1080), 'green').save(out, format='JPEG', quality=80)
    return out.getvalue()


def intake(media, monkeypatch):
    svc, _ = media
    io = concrete_runtime(svc, monkeypatch)
    cfg = replace(svc.config, owned_quiescence_enabled=False, retained_writes_enabled=True)
    svc.config, svc.runtime = cfg, replace(svc.runtime, config=cfg)
    api = mounted_client((svc, io))
    data = jpeg()
    assert 0 < len(data) <= 262144
    response = api.post(BASE + '/media/uploads', json={'filename': 'stage-a.jpg',
        'declared_size': len(data), 'declared_mime_type': 'image/jpeg',
        'alt_text': 'Synthetic recovery square'}, headers=headers())
    assert response.status_code == 201, response.text
    grant = response.json()
    # The real botocore signer signs all guards. SDK I/O is an explicit inert
    # transport double; this does not qualify browser CORS or real signed PUT.
    from urllib.parse import parse_qs, unquote, urlsplit
    access = grant
    signed = parse_qs(urlsplit(access['url']).query)
    assert set(signed['X-Amz-SignedHeaders'][0].split(';')) == {
        'host', 'content-length', 'content-type', 'if-none-match'}
    key = unquote(urlsplit(access['url']).path).removeprefix('/media-test/')
    assert access['headers'] == {'Content-Type': 'image/jpeg', 'If-None-Match': '*'}
    io.objects[key] = (data, 'image/jpeg', {})
    identity = grant['asset']['id']
    complete = api.post(BASE + '/media/uploads/' + identity + '/complete',
        json={'expected_version': 1}, headers=headers())
    assert complete.status_code == 200, complete.text
    assert (complete.json()['width'], complete.json()['height']) == (1080, 1080)
    preview = api.get(BASE + '/media/assets/' + identity + '/preview')
    assert preview.status_code == 200, preview.text
    created = api.post(BASE + '/posts', json={'title': 'Synthetic storage recovery',
        'content_type': 'announcement', 'document': {'master': {
            'text': 'Synthetic storage recovery only', 'media': [{'asset_id': identity}]},
            'targets': []}, 'references': []}, headers=headers())
    assert created.status_code == 201, created.text
    return io, data, UUID(identity), UUID(created.json()['id'])


def reconstruct(engine, raw):
    """Test-only typed row insertion into an independently created inert target."""
    with engine.begin() as conn:
        restore_stage_a_rows(conn, raw)


@pytest.mark.parametrize('damage', [None, 'missing_original', 'corrupt_original', 'missing_quarantine'])
def test_nonempty_retained_cold_restore_through_mounted_api(media, monkeypatch, tmp_path, damage):
    svc, _ = media
    io, data, identity, post = intake(media, monkeypatch)
    with svc.db.begin():
        rows = capture_stage_a_rows(svc.db, ACTOR, identity, post)
        raw = encode_rows(rows)
    captured, snapshots = capture_stage_a_payloads(rows, svc.runtime.storage)
    assert len(snapshots) == 2 and all(v['version'] is None for v in snapshots.values())
    assert captured == {k: v[0] for k, v in io.objects.items()}
    (tmp_path / 'rows.json').write_bytes(raw)
    # Capture independent bytes; destroy the primary DB and store before restore.
    saved = {}
    for index, (key, (payload, mime, metadata)) in enumerate(sorted(io.objects.items())):
        path = tmp_path / f'object-{index}.bin'; path.write_bytes(payload)
        saved[key] = (path, mime, metadata.copy())
    assert len(saved) == 2 and sum(p.stat().st_size for p, _, _ in saved.values()) == 2 * len(data)
    verify_stage_a_payloads(rows, {k: p.read_bytes() for k, (p, _, _) in saved.items()})
    assert len(raw) + 2 * len(data) < 655360  # Proposed rows+payload+manifest cap is 1 MiB.
    source_engine = svc.db.get_bind()
    svc.db.close(); source_engine.dispose(); io.objects.clear()
    engine = create_engine('sqlite:///' + str(tmp_path / 'restored.sqlite'))
    @event.listens_for(engine, 'connect')
    def foreign_keys(conn, record): conn.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name.startswith('social_')])
    reconstruct(engine, (tmp_path / 'rows.json').read_bytes())
    for key, (path, mime, metadata) in saved.items():
        io.objects[key] = (path.read_bytes(), mime, metadata)
    original = f'ready/{identity}/original'
    quarantine = f'quarantine/{ACTOR}/{identity}/source'
    if damage == 'missing_original': del io.objects[original]
    if damage == 'missing_quarantine': del io.objects[quarantine]
    if damage == 'corrupt_original':
        payload, mime, metadata = io.objects[original]
        io.objects[original] = (b'x' * len(payload), mime, metadata)
    try:
        with Session(engine, expire_on_commit=False) as db:
            restored = MediaService(db, replace(svc.runtime, storage=io.runtime.storage))
            api = mounted_client((restored, io))
            assert api.get(BASE + '/posts/' + str(post)).status_code == 200
            assert api.get(BASE + '/media/assets').json()['assets'][0]['sha256'] == hashlib.sha256(data).hexdigest()
            response = api.get(BASE + '/media/assets/' + str(identity) + '/preview')
            assert response.status_code == (503 if damage in {'missing_original', 'corrupt_original'} else 200)
            # Capsule validates ledger closure, not object integrity. Independent
            # custody verification must read/hash BOTH captured payloads.
            restored_payloads = {k: value[0] for k, value in io.objects.items()}
            if damage:
                with pytest.raises(RecoveryScopeError):
                    verify_stage_a_payloads(json.loads((tmp_path / 'rows.json').read_bytes()), restored_payloads)
            else:
                verify_stage_a_payloads(json.loads((tmp_path / 'rows.json').read_bytes()), restored_payloads)
            with db.begin():
                upload = db.get(SocialMediaUpload, identity)
                assert upload.retained_write_fence and upload.pending_released == 1
                assert (upload.grant_epoch, upload.grant_settled_epoch) == (1, 0)
                assert upload.reserved_bytes == 2 * len(data) and upload.reservation_released == 0
                assert {(b.bytes_used, b.pending_count) for b in db.scalars(select(SocialMediaBudget))} == {(2 * len(data), 0)}
            off = MediaService(db, MediaRuntime(MediaConfig(), None, None))
            assert off.capabilities().upload_available is False
            assert off.backlog().unknown_browser_writes == 1
            assert off.backlog().reserved_bytes == 2 * len(data)
            assert all(op != 'delete' for op, _ in io.calls)
    finally:
        engine.dispose(); io.sdk.close()


@pytest.mark.parametrize('damage', ['lost_budget', 'lost_fence', 'extra_revision'])
def test_capture_refuses_incomplete_or_broader_scope(media, monkeypatch, damage):
    svc, _ = media
    io, _, identity, post = intake(media, monkeypatch)
    try:
        with svc.db.begin():
            if damage == 'lost_budget': svc.db.get(SocialMediaBudget, 'global').bytes_used = 0
            if damage == 'lost_fence':
                from sqlalchemy import update
                svc.db.execute(update(SocialMediaUpload).where(SocialMediaUpload.asset_id == identity).values(retained_write_fence=None))
            if damage == 'extra_revision':
                revision = svc.db.scalar(select(SocialPostRevision))
                svc.db.add(SocialPostRevision(post_id=post, revision_no=2, document=revision.document,
                    content_hash=revision.content_hash, evidence_snapshot=revision.evidence_snapshot, created_by=ACTOR))
        with svc.db.begin(), pytest.raises(RecoveryScopeError):
            capture_stage_a_rows(svc.db, ACTOR, identity, post)
    finally:
        io.sdk.close()


@pytest.mark.parametrize('history', ['foreign_audit_parent', 'render_job', 'dependent_post', 'privacy_receipt'])
def test_capsule_never_omits_existing_reference_history(media, monkeypatch, history):
    svc, _ = media
    io, _, asset, post = intake(media, monkeypatch)
    try:
        with svc.db.begin():
            if history == 'foreign_audit_parent':
                other = SocialPost(title='Other retained post', content_type='announcement', created_by=ACTOR)
                svc.db.add(other); svc.db.flush()
                from sqlalchemy import update
                svc.db.execute(update(SocialAuditEvent).where(
                    SocialAuditEvent.action == 'media.inspection_started').values(post_id=other.id))
            elif history == 'render_job':
                revision = svc.db.scalar(select(SocialPostRevision.id).where(SocialPostRevision.post_id == post))
                svc.db.add(RenderJob(revision_id=revision, actor_id=ACTOR, composition={}, input_hash='a' * 64, state='queued'))
            elif history == 'dependent_post':
                svc.db.add(SocialPost(title='Dependent retained post', content_type='announcement',
                    created_by=ACTOR, duplicated_from_id=post, creation_method='duplicate'))
            else:
                audit = svc.db.scalar(select(SocialAuditEvent.id).where(SocialAuditEvent.action == 'media.upload_initiated'))
                svc.db.add(SocialPrivacyReceipt(app_id='inert-app', kind='deauthorization',
                    digest_version='v1', subject_digest='a' * 64, event_key='b' * 64,
                    request_fingerprint='c' * 64, affected={}, resolution='Inert fixture',
                    state='blocked_future_mutations', audit_id=audit))
        with svc.db.begin(), pytest.raises(RecoveryScopeError):
            capture_stage_a_rows(svc.db, ACTOR, asset, post)
    finally:
        io.sdk.close()


@pytest.mark.parametrize('side', ['quarantine', 'original'])
def test_payload_capture_refuses_recorded_identity_drift(media, monkeypatch, side):
    svc, _ = media
    io, _, asset, post = intake(media, monkeypatch)
    try:
        with svc.db.begin(): rows = capture_stage_a_rows(svc.db, ACTOR, asset, post)
        head = io.sdk.head_object
        def changed(**kw):
            value = head(**kw)
            if kw['Key'].startswith('quarantine/' if side == 'quarantine' else 'ready/'):
                value['ETag'] = '"unaccounted-writer"'
            return value
        monkeypatch.setattr(io.sdk, 'head_object', changed)
        with pytest.raises(RecoveryScopeError): capture_stage_a_payloads(rows, svc.runtime.storage)
        assert not any(op == 'delete' for op, _ in io.calls)
    finally:
        io.sdk.close()


@pytest.mark.parametrize('damage', ['asset_only', 'lost_history', 'lost_inspection_event',
    'lost_completion_key', 'lost_completion_hash', 'wrong_completion_hash', 'wrong_initial_hash',
    'wrong_receipt_response', 'lost_grant_expiry', 'wrong_bytes'])
def test_rejected_restore_cannot_commit_a_usable_partial_asset(media, monkeypatch, damage):
    svc, _ = media
    io, _, asset, post = intake(media, monkeypatch)
    engine = create_engine('sqlite://')
    try:
        with svc.db.begin(): rows = json.loads(encode_rows(capture_stage_a_rows(svc.db, ACTOR, asset, post)))
        if damage == 'asset_only':
            rows = {name: values if name == 'social_media_assets' else [] for name, values in rows.items()}
        elif damage == 'lost_history': rows['social_audit_events'] = []
        elif damage == 'lost_inspection_event':
            rows['social_audit_events'] = [r for r in rows['social_audit_events'] if r['action'] != 'media.inspection_started']
        elif damage == 'lost_completion_key': rows['social_media_uploads'][0]['completion_key'] = None
        elif damage == 'lost_completion_hash': rows['social_media_uploads'][0]['completion_hash'] = None
        elif damage == 'wrong_completion_hash': rows['social_media_uploads'][0]['completion_hash'] = '0' * 64
        elif damage == 'wrong_initial_hash': rows['social_media_uploads'][0]['request_hash'] = '0' * 64
        elif damage == 'wrong_receipt_response': rows['social_command_receipts'][0]['response']['id'] = str(uuid4())
        elif damage == 'lost_grant_expiry': rows['social_media_uploads'][0]['grant_expires_at'] = None
        else: rows['social_media_budgets'][0]['bytes_used'] = 0
        Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name.startswith('social_')])
        with engine.begin() as connection:
            with pytest.raises(RecoveryScopeError): restore_stage_a_rows(connection, encode_rows(rows))
            # Deliberately catch then commit caller transaction: failure must
            # have rolled back its own partial inserts, not rely on this caller.
            for model in MODELS:
                assert connection.scalar(select(func.count()).select_from(model.__table__)) == 0
    finally:
        engine.dispose(); io.sdk.close()

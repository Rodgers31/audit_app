"""Synthetic cold restore: logical SQLite export and private fixture objects only.

This is not a PostgreSQL/R2 restore tool or production custody acceptance.
"""
import hashlib
import json
import sqlite3
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from social.media.config import MediaConfig
from social.media.inspection import LocalInspector
from social.media.models import SocialMediaBudget
from social.media.runtime import MediaRuntime
from social.media.service import MediaService
from social.models import SocialMediaAsset, SocialRevisionAsset
from social.service import SocialError, SocialService
from test_domain_support import call, draft_body
from test_media_api import BASE, client, header
from test_media_support import ACTOR, FakeStorage, intent, media, media_db, png


@pytest.mark.parametrize('damage', [None, 'missing_original', 'corrupt_original'])
def test_cold_reconstruction_preserves_media_ledger_and_historical_reference(media, tmp_path, damage):
    source, primary_store = media
    original_bytes = png()
    # Independent input evidence is captured before any service output exists.
    original_digest = hashlib.sha256(original_bytes).hexdigest()
    api = client(media)
    grant = api.post(BASE + '/uploads', json=intent(original_bytes), headers=header())
    assert grant.status_code == 201, grant.text
    identity = UUID(grant.json()['asset']['id'])
    primary_store.objects[primary_store.last_key] = (original_bytes, 'image/png', None)
    ready = api.post(BASE + f'/uploads/{identity}/complete', json={'expected_version': 1}, headers=header())
    assert ready.status_code == 200, ready.text
    assert ready.json()['sha256'] == original_digest
    body = draft_body(document={'master': {'text': 'Retained local evidence',
        'media': [{'asset_id': str(identity)}]}, 'targets': []})
    call(source.db, body, lambda svc: svc.create(body), adapters=())
    source_engine = source.db.bind

    # Export actual persisted rows as SQL, then rebuild a different database.
    # No original DB file is reopened or copied into the restored engine.
    with source_engine.connect() as connection:
        logical_sql = '\n'.join(connection.connection.driver_connection.iterdump())
    backup_sql = tmp_path / 'inert-social.sql'
    backup_sql.write_text(logical_sql, encoding='utf-8')
    object_manifest = []
    for number, (key, (data, mime, digest)) in enumerate(sorted(primary_store.objects.items())):
        filename = f'object-{number}.bin'
        (tmp_path / filename).write_bytes(data)
        object_manifest.append({'key': key, 'file': filename, 'mime': mime, 'sha256_metadata': digest})
    manifest = tmp_path / 'inert-object-manifest.json'
    manifest.write_text(json.dumps(object_manifest), encoding='utf-8')
    source.db.close()
    source_engine.dispose()  # The primary in-memory DB ceases to exist.
    primary_store.objects.clear()
    del logical_sql, object_manifest

    restored_path = tmp_path / 'independently-rebuilt.sqlite'
    with sqlite3.connect(restored_path) as connection:
        connection.executescript(backup_sql.read_text(encoding='utf-8'))
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
    restored_store = FakeStorage()
    for item in json.loads(manifest.read_text(encoding='utf-8')):
        restored_store.objects[item['key']] = ((tmp_path / item['file']).read_bytes(),
            item['mime'], item['sha256_metadata'])
    restored_engine = create_engine(f'sqlite:///{restored_path}')
    try:
        with Session(restored_engine, expire_on_commit=False) as db:
            restored_inspector = LocalInspector(source.config)
            restored = MediaService(db, MediaRuntime(source.config, restored_store, restored_inspector))
            off_runtime = MediaRuntime(MediaConfig(), None, None)
            offline = MediaService(db, off_runtime)
            assert not offline.capabilities().upload_available
            assert offline.library().assets[0].sha256 == original_digest
            usage = offline.asset_usage(identity)
            assert usage.total == 1 and not usage.archive_eligible
            with pytest.raises(SocialError, match='MEDIA_ARCHIVE_BLOCKED'):
                offline.archive_asset(ACTOR, identity, uuid4(),
                    {'expected_version': 2, 'reason': 'Must retain historical evidence'}, uuid4())
            with db.begin():
                assert list(db.scalars(select(SocialRevisionAsset.asset_id))) == [identity]
                assert {(b.scope, b.bytes_used, b.pending_count) for b in db.scalars(select(SocialMediaBudget))} == {
                    ('global', 2 * len(original_bytes), 1),
                    (f'actor:{ACTOR}', 2 * len(original_bytes), 1)}
                asset = db.get(SocialMediaAsset, identity)
                key = asset.storage_key
                assert asset.sha256 == original_digest
                assert asset.width == 64 and asset.height == 32
            data, mime, digest = restored_store.objects[key]
            assert data == original_bytes and hashlib.sha256(data).hexdigest() == original_digest
            restored_original = tmp_path / 'reconstructed-original.png'
            restored_original.write_bytes(data)
            inspected = restored_inspector.inspect(restored_original, 'image/png', len(original_bytes))
            assert inspected.sha256 == original_digest and (inspected.width, inspected.height) == (64, 32)
            if damage == 'missing_original':
                del restored_store.objects[key]
            elif damage == 'corrupt_original':
                restored_store.objects[key] = (b'x' * len(data), mime, digest)
            if damage:
                with pytest.raises(SocialError, match='MEDIA_STORAGE_UNAVAILABLE'):
                    restored.preview(identity)
                assert 'preview' not in restored_store.operations
            else:
                assert restored.preview(identity).asset.sha256 == original_digest
            # A restored unknown grant stays held; restore is not quiescence.
            assert offline.backlog().reserved_bytes == 2 * len(original_bytes)
            assert offline.backlog().pending_uploads == 1
            assert offline.backlog().unknown_browser_writes == 1
            with db.begin():
                status = SocialService(db, available_adapters=(), media_runtime=off_runtime).status()
                assert status['publishing_enabled'] is False and status['generation_enabled'] is False
                assert not any(status[name] for name in ('media_upload_available', 'auto_approve_enabled',
                    'auto_schedule_enabled', 'auto_publish_enabled'))
            assert primary_store.objects == {}
            assert 'delete' not in restored_store.operations and 'finalize' not in restored_store.operations
    finally:
        restored_engine.dispose()

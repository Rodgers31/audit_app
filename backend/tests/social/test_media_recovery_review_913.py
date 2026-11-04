"""Malformed recovery input and isolated-target refusals; inert inspection only."""
from copy import deepcopy
import hashlib
import json
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select, text

from social.contracts import canonical_hash
from social.media.inspection import InspectedMedia, LocalInspector
from social.media.recovery import (MODELS, RecoveryScopeError, capture_stage_a_rows,
    capture_stage_a_payloads, encode_rows, restore_stage_a_rows, verify_stage_a_payloads)
from social.media.recovery_packet import (MAX_MANIFEST, _canonical, _load,
    publish_stage_a_packet, read_stage_a_packet)
from social.models import Base, SocialAccount, SocialMediaAsset, SocialPostRevision
from test_media_recovery_packet import CONTEXT
from test_media_stage_a_recovery import intake
from test_media_support import ACTOR, media, media_db


@pytest.fixture
def retained(media, monkeypatch):
    def inspect(self, path, mime, size):
        return InspectedMedia(mime, size, hashlib.sha256(path.read_bytes()).hexdigest(),
            1080, 1080, None, None, {})
    monkeypatch.setattr(LocalInspector, 'inspect', inspect)
    svc, _ = media
    io, data, asset, post = intake(media, monkeypatch)
    try:
        with svc.db.begin():
            rows = json.loads(encode_rows(capture_stage_a_rows(svc.db, ACTOR, asset, post)))
        yield svc, io, data, asset, post, rows
    finally:
        io.sdk.close()


def empty_target():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine,
        tables=[t for t in Base.metadata.sorted_tables if t.name.startswith('social_')])
    return engine


@pytest.mark.parametrize('preexisting', ['account', 'unknown_table', 'unknown_empty_table'])
def test_restore_refuses_rows_outside_capsule_models_without_changing_target(retained, preexisting):
    rows = retained[-1]
    engine = empty_target()
    try:
        with engine.begin() as connection:
            if preexisting == 'account':
                connection.execute(SocialAccount.__table__.insert().values(
                    id=uuid4(), platform='facebook', api_product='facebook_pages',
                    connection_method='manual', external_account_id='913',
                    display_name='Inert existing account', publishing_enabled=False))
            else:
                connection.exec_driver_sql('CREATE TABLE unknown_history(value TEXT)')
                if preexisting != 'unknown_empty_table':
                    connection.exec_driver_sql("INSERT INTO unknown_history VALUES ('must remain')")
        with engine.begin() as connection:
            with pytest.raises(RecoveryScopeError):
                restore_stage_a_rows(connection, encode_rows(rows))
            for model in MODELS:
                assert connection.scalar(select(func.count()).select_from(model.__table__)) == 0
        with engine.connect() as connection:
            if preexisting == 'account':
                assert connection.scalar(select(func.count()).select_from(SocialAccount)) == 1
            elif preexisting == 'unknown_table':
                assert connection.exec_driver_sql('SELECT value FROM unknown_history').scalar_one() == 'must remain'
            else:
                assert connection.exec_driver_sql('SELECT count(*) FROM unknown_history').scalar_one() == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize('version', ['a756b20a0001', 'historical', 'ambiguous'])
def test_restore_allows_only_the_explicit_single_current_migration_record(retained, version):
    engine = empty_target()
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE alembic_version(version_num VARCHAR(32) PRIMARY KEY)')
            connection.execute(text('INSERT INTO alembic_version VALUES (:version)'),
                {'version': 'a756b20a0001' if version != 'historical' else 'a611b12a0001'})
            if version == 'ambiguous':
                connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('a611b12a0001')")
        with engine.begin() as connection:
            if version == 'a756b20a0001':
                restore_stage_a_rows(connection, encode_rows(retained[-1]))
                assert connection.scalar(select(func.count()).select_from(MODELS[0])) == 1
            else:
                with pytest.raises(RecoveryScopeError):
                    restore_stage_a_rows(connection, encode_rows(retained[-1]))
                assert connection.scalar(select(func.count()).select_from(MODELS[0])) == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize('kind', ['deep', 'cycle', 'nonfinite'])
def test_row_encoder_normalizes_bad_json_to_scope_refusal(kind):
    rows = {m.__tablename__: [] for m in MODELS}
    node = {}
    if kind == 'deep':
        for _ in range(10000):
            node = {'next': node}
    elif kind == 'cycle':
        node['next'] = node
    else:
        node['number'] = float('nan')
    rows['social_posts'] = [node]
    with pytest.raises(RecoveryScopeError):
        encode_rows(rows)


@pytest.mark.parametrize('operation', ['load', 'canonical', 'restore'])
def test_deep_raw_rows_and_manifest_json_refuse_with_typed_error(operation):
    raw = b'[' * 10000 + b'0' + b']' * 10000
    assert len(raw) < MAX_MANIFEST
    if operation == 'load':
        with pytest.raises(RecoveryScopeError):
            _load(raw)
        return
    value = {}
    for _ in range(10000):
        value = {'next': value}
    if operation == 'canonical':
        with pytest.raises(RecoveryScopeError):
            _canonical(value)
        return
    engine = empty_target()
    try:
        with engine.begin() as connection:
            with pytest.raises(RecoveryScopeError):
                restore_stage_a_rows(connection, raw)
            for model in MODELS:
                assert connection.scalar(select(func.count()).select_from(model.__table__)) == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize('damage', ['document_list', 'master_list', 'media_scalar', 'codec_list'])
def test_malformed_historical_document_rolls_back_caught_restore(retained, damage):
    rows = deepcopy(retained[-1])
    revision = rows['social_post_revisions'][0]
    if damage == 'document_list':
        revision['document'] = []
    elif damage == 'master_list':
        revision['document']['master'] = []
    elif damage == 'media_scalar':
        revision['document']['master']['media'] = [False]
    else:
        rows['social_media_assets'][0]['codec_metadata'] = []
    revision['content_hash'] = canonical_hash({'document': revision['document'],
        'evidence_snapshot': revision['evidence_snapshot']})
    engine = empty_target()
    try:
        with engine.begin() as connection:
            with pytest.raises(RecoveryScopeError):
                restore_stage_a_rows(connection, encode_rows(rows))
            for model in MODELS:
                assert connection.scalar(select(func.count()).select_from(model.__table__)) == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize('damage', ['asset_missing_key', 'asset_list', 'post_list',
    'upload_list', 'codec_list', 'fence_missing_key'])
def test_self_consistent_packet_with_malformed_inner_shape_is_typed_refusal(retained, tmp_path, damage):
    svc, _, _, asset, post, _ = retained
    root = tmp_path / 'custody'
    root.mkdir(mode=0o700)
    custody = uuid4()
    with svc.db.begin():
        digest = publish_stage_a_packet(svc.db, svc.runtime.storage, ACTOR,
            asset, post, root, custody, CONTEXT)
    original, _, _ = read_stage_a_packet(root, custody, digest)
    rows = json.loads(original)
    if damage == 'asset_missing_key':
        del rows['social_media_assets'][0]['id']
    elif damage == 'asset_list':
        rows['social_media_assets'][0] = []
    elif damage == 'post_list':
        rows['social_posts'][0] = []
    elif damage == 'upload_list':
        rows['social_media_uploads'][0] = []
    elif damage == 'codec_list':
        rows['social_media_assets'][0]['codec_metadata'] = []
    else:
        rows['social_media_uploads'][0]['retained_write_fence'] = '{}'
    contents = encode_rows(rows)
    directory = root / str(custody)
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    (directory / 'rows.json').write_bytes(contents)
    manifest['files']['rows.json'] = {'size': len(contents),
        'sha256': hashlib.sha256(contents).hexdigest()}
    raw = _canonical(manifest)
    (directory / 'manifest.json').write_bytes(raw)
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    from unittest.mock import patch
    opened = []
    original_open = os.open
    def opened_directory(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        if flags & os.O_DIRECTORY:
            opened.append(fd)
        return fd
    with patch('social.media.recovery_packet.os.open', opened_directory):
        with pytest.raises(RecoveryScopeError):
            read_stage_a_packet(root, custody, hashlib.sha256(raw).hexdigest())
    assert len(opened) == 2
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)
    assert {path.name: path.read_bytes() for path in directory.iterdir()} == before


@pytest.mark.parametrize('damage', ['document', 'codec', 'fence', 'duplicate_fence'])
def test_capture_refusal_publishes_no_custody_and_performs_no_storage_read(retained, tmp_path, damage):
    svc, io, _, asset, post, rows = retained
    with svc.db.begin():
        # Deliberately model corrupt imported storage via Core; ordinary ORM
        # edits correctly refuse immutable history before capture is reached.
        if damage == 'document':
            svc.db.execute(SocialPostRevision.__table__.update().where(
                SocialPostRevision.id == UUID(rows['social_post_revisions'][0]['id']))
                .values(document=[]))
        elif damage == 'codec':
            svc.db.execute(SocialMediaAsset.__table__.update().where(
                SocialMediaAsset.id == asset).values(codec_metadata=[]))
        else:
            from social.media.models import SocialMediaUpload
            fence = ('{' + rows['social_media_uploads'][0]['retained_write_fence'][1:-1]
                + ',"version":1}') if damage == 'duplicate_fence' else '[]'
            svc.db.execute(SocialMediaUpload.__table__.update().where(
                SocialMediaUpload.asset_id == asset).values(
                    retained_write_fence=fence))
    svc.db.expire_all()
    root = tmp_path / 'custody'
    root.mkdir(mode=0o700)
    previous_calls = list(io.calls)
    with svc.db.begin(), pytest.raises(RecoveryScopeError):
        publish_stage_a_packet(svc.db, svc.runtime.storage, ACTOR,
            asset, post, root, uuid4(), CONTEXT)
    assert list(root.iterdir()) == []
    assert io.calls == previous_calls


def test_deep_fence_input_refuses_before_storage_capture(retained):
    svc, io, _, _, _, original = retained
    rows = deepcopy(original)
    rows['social_media_uploads'][0]['retained_write_fence'] = '[' * 10000 + '0' + ']' * 10000
    previous_calls = list(io.calls)
    with pytest.raises(RecoveryScopeError):
        capture_stage_a_payloads(rows, svc.runtime.storage)
    assert io.calls == previous_calls


@pytest.mark.parametrize('damage', ['codec_list', 'missing_etag', 'empty_etag',
    'version_list', 'missing_original', 'empty_original', 'duplicate_keys', 'nonfinite_size',
    'boolean_size', 'bad_mime', 'missing_sha', 'missing_quarantine', 'duplicate_fence'])
def test_invalid_capture_metadata_refuses_before_any_storage_call(retained, monkeypatch, damage):
    svc, _, _, _, _, original = retained
    rows = deepcopy(original)
    asset, upload = rows['social_media_assets'][0], rows['social_media_uploads'][0]
    if damage == 'codec_list':
        asset['codec_metadata'] = []
    elif damage == 'missing_etag':
        del asset['codec_metadata']['storage_etag']
    elif damage == 'empty_etag':
        asset['codec_metadata']['storage_etag'] = ''
    elif damage == 'version_list':
        asset['codec_metadata']['storage_version'] = []
    elif damage == 'missing_original':
        del asset['storage_key']
    elif damage == 'empty_original':
        asset['storage_key'] = ''
    elif damage == 'duplicate_keys':
        asset['storage_key'] = upload['quarantine_key']
    elif damage == 'boolean_size':
        asset['byte_size'] = True
    elif damage == 'bad_mime':
        asset['mime_type'] = 'video/mp4'
    elif damage == 'missing_sha':
        del asset['sha256']
    elif damage == 'missing_quarantine':
        del upload['quarantine_key']
    elif damage == 'duplicate_fence':
        upload['retained_write_fence'] = ('{' + upload['retained_write_fence'][1:-1] + ',"version":1}')
    else:
        asset['byte_size'] = float('nan')
    storage = svc.runtime.storage
    calls = []
    old_head, old_download = storage.head, storage.download
    def head(*args, **kwargs):
        calls.append('head')
        return old_head(*args, **kwargs)
    def download(*args, **kwargs):
        calls.append('download')
        return old_download(*args, **kwargs)
    monkeypatch.setattr(storage, 'head', head)
    monkeypatch.setattr(storage, 'download', download)
    with pytest.raises(RecoveryScopeError):
        capture_stage_a_payloads(rows, storage)
    assert calls == []


def test_restore_refuses_unknown_sqlite_view_without_inserts(retained):
    engine = empty_target()
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE VIEW private_view AS SELECT 1 AS value')
        with engine.begin() as connection:
            with pytest.raises(RecoveryScopeError):
                restore_stage_a_rows(connection, encode_rows(retained[-1]))
            assert connection.exec_driver_sql('SELECT count(*) FROM social_media_assets').scalar_one() == 0
            assert connection.exec_driver_sql('SELECT value FROM private_view').scalar_one() == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize('side', ['quarantine', 'original'])
def test_payload_refusal_changes_actual_same_size_original_bytes(retained, side):
    _, _, data, _, _, rows = retained
    asset, upload = rows['social_media_assets'][0], rows['social_media_uploads'][0]
    changed = bytes([data[0] ^ 1]) + data[1:]
    assert changed != data and len(changed) == len(data)
    payloads = {asset['storage_key']: data, upload['quarantine_key']: data}
    payloads[asset['storage_key'] if side == 'original' else upload['quarantine_key']] = changed
    with pytest.raises(RecoveryScopeError):
        verify_stage_a_payloads(rows, payloads)


@pytest.mark.parametrize('internal_state', [False, True],
                         ids=['ordinary-empty-target', 'populated-internal-sequence'])
def test_restore_censuses_internal_sqlite_tables(retained, internal_state):
    engine = empty_target()
    try:
        with engine.begin() as connection:
            if internal_state:
                connection.exec_driver_sql('CREATE TABLE retired_probe(id INTEGER PRIMARY KEY AUTOINCREMENT)')
                connection.exec_driver_sql('DROP TABLE retired_probe')
                connection.exec_driver_sql("INSERT INTO sqlite_sequence(name,seq) VALUES('imported_history',7)")
            refused = False
            try:
                restore_stage_a_rows(connection, encode_rows(retained[-1]))
            except RecoveryScopeError:
                refused = True
            assets = connection.exec_driver_sql('SELECT count(*) FROM social_media_assets').scalar_one()
            metadata = connection.exec_driver_sql('SELECT count(*) FROM sqlite_sequence').scalar_one() if internal_state else 0
        with engine.connect() as connection:
            committed = connection.exec_driver_sql('SELECT count(*) FROM social_media_assets').scalar_one()
        assert refused is internal_state
        assert assets == committed == (0 if internal_state else 1)
        if internal_state:
            assert metadata == 1
    finally:
        engine.dispose()

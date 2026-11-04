"""Actual local publication/fsync/readback; only inert mounted API/storage."""
import hashlib
import json
import os
from uuid import uuid4

import pytest

from social.media.recovery import RecoveryScopeError
from social.media.recovery_packet import publish_stage_a_packet, read_stage_a_packet
from test_media_stage_a_recovery import intake
from test_media_support import ACTOR, media, media_db


CONTEXT = {**{k: 'a' * 64 for k in ('runtime_sha256', 'policy_sha256', 'decision_sha256',
    'writer_inventory_sha256', 'appointments_sha256', 'dependencies_sha256')},
    'source_commit': 'b' * 40, 'source_tree': 'c' * 40, 'schema_revision': 'a756b20a0001'}


@pytest.fixture
def packet(media, monkeypatch, tmp_path):
    svc, _ = media
    io, _, asset, post = intake(media, monkeypatch)
    root = tmp_path / 'approved-existing'; root.mkdir(mode=0o700)
    custody = uuid4()
    try: yield svc, io, asset, post, root, custody
    finally: io.sdk.close()


def publish(packet):
    svc, io, asset, post, root, custody = packet
    with svc.db.begin():
        return publish_stage_a_packet(svc.db, svc.runtime.storage, ACTOR, asset, post, root, custody, CONTEXT)


def test_complete_packet_is_private_bounded_and_independently_read_back(packet):
    digest = publish(packet)
    _, _, asset, post, root, custody = packet
    rows, payloads, manifest = read_stage_a_packet(root, custody, digest)
    assert hashlib.sha256((root / str(custody) / 'manifest.json').read_bytes()).hexdigest() == digest
    assert set(json.loads(rows)['social_posts'][0]) and len(payloads) == 2
    assert manifest['asset_id'] == str(asset) and manifest['post_id'] == str(post)
    assert manifest['execution_identity_authenticated'] is False
    assert manifest['source_snapshot']['dialect'] == 'sqlite_fixture'
    assert manifest['source_snapshot']['consistency_proven'] is False
    files = list((root / str(custody)).iterdir())
    assert len(files) == 4 and sum(p.stat().st_size for p in files) <= 720896
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in files)


@pytest.mark.parametrize('damage', ['missing_original', 'corrupt_quarantine', 'symlink_original', 'hardlink_original', 'extra_file', 'wrong_manifest', 'boolean_schema'])
def test_custody_damage_never_becomes_success(packet, damage):
    digest = publish(packet)
    *_, root, custody = packet
    directory = root / str(custody)
    if damage == 'missing_original': (directory / 'original.bin').unlink()
    elif damage == 'corrupt_quarantine': (directory / 'quarantine.bin').write_bytes(b'bad')
    elif damage == 'symlink_original':
        original = directory / 'original.bin'; original.rename(directory.parent / 'retained-original.bin')
        original.symlink_to(directory.parent / 'retained-original.bin')
    elif damage == 'hardlink_original': os.link(directory / 'original.bin', directory.parent / 'retained-original.bin')
    elif damage == 'extra_file': (directory / 'unaccounted.bin').write_bytes(b'unknown')
    elif damage == 'wrong_manifest': digest = '0' * 64
    else:
        path = directory / 'manifest.json'; value = json.loads(path.read_bytes()); value['schema_version'] = True
        raw = json.dumps(value).encode(); path.write_bytes(raw); digest = hashlib.sha256(raw).hexdigest()
    with pytest.raises((RecoveryScopeError, OSError)):
        read_stage_a_packet(root, custody, digest)


@pytest.mark.parametrize('damage', ['root_mode', 'existing_directory', 'bad_context'])
def test_invalid_destination_and_context_refuse_before_any_capture_io(packet, damage):
    svc, io, asset, post, root, custody = packet
    context = dict(CONTEXT)
    if damage == 'root_mode': root.chmod(0o755)
    elif damage == 'existing_directory':
        (root / str(custody)).mkdir(mode=0o700)
        (root / str(custody) / 'preserve.bin').write_bytes(b'existing')
    else: context['decision_sha256'] = True
    before = list(io.calls)
    with svc.db.begin(), pytest.raises(RecoveryScopeError):
        publish_stage_a_packet(svc.db, svc.runtime.storage, ACTOR, asset, post, root, custody, context)
    assert io.calls == before
    if damage == 'existing_directory': assert (root / str(custody) / 'preserve.bin').read_bytes() == b'existing'


def test_failed_fsync_preserves_partial_packet_and_never_returns_a_manifest(packet, monkeypatch):
    def fail(fd): raise OSError('Inert fsync failure')
    monkeypatch.setattr('social.media.recovery_packet.os.fsync', fail)
    with pytest.raises(OSError): publish(packet)
    *_, root, custody = packet
    assert (root / str(custody) / 'rows.json').is_file()
    assert not (root / str(custody) / 'manifest.json').exists()
    with pytest.raises(RecoveryScopeError): publish(packet)


def test_readback_refuses_inventory_drift_during_payload_reads(packet, monkeypatch):
    digest = publish(packet)
    *_, root, custody = packet
    from social.media import recovery_packet
    original = recovery_packet._read
    changed = False
    def drift(directory, name, maximum):
        nonlocal changed
        data = original(directory, name, maximum)
        if not changed:
            changed = True
            fd = os.open('unaccounted.bin', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
            with os.fdopen(fd, 'wb') as stream: stream.write(b'unknown')
        return data
    monkeypatch.setattr(recovery_packet, '_read', drift)
    with pytest.raises(RecoveryScopeError): read_stage_a_packet(root, custody, digest)
    assert changed and (root / str(custody) / 'unaccounted.bin').is_file()

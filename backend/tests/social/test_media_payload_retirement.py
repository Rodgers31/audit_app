"""Actual service/R2-port controls. No bucket/network/credentials are used."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
from threading import Event, Lock
from types import SimpleNamespace
from uuid import uuid4

from botocore.exceptions import ClientError
import pytest
from sqlalchemy import select

from social.media.deletion import (MediaDeletionAuthority, PrivacyMediaDeletionCommand,
    execute_deletion)
from social.media.fencing import FENCE_BODY, WRITE_PROTOCOL
from social.media.models import SocialMediaBudget, SocialMediaDeletion, SocialMediaUpload
from social.media.storage import R2Storage, StorageFailure
from social.models import SocialMediaAsset
from social.service import SocialError
from test_media_support import ACTOR, FakeStorage, intent, media, media_db, png


def response(code):
    return {'ResponseMetadata': {'HTTPStatusCode': code, 'RetryAttempts': 0}}


def failure(code, name):
    return ClientError({**response(code), 'Error': {'Code': name}}, 'fixture')


class ConditionalSDK:
    def __init__(self, objects):
        self.objects = objects
        self.metadata = {}
        self.lock = Lock()
        self.meta = SimpleNamespace(config=SimpleNamespace(retries={'total_max_attempts': 1}))
        self.before_put = None
        self.lose_response = False
        self.puts = []
        self.version = None

    def head_object(self, Bucket, Key):
        with self.lock:
            if Key not in self.objects:
                raise failure(404, 'NoSuchKey')
            data, mime, sha = self.objects[Key]
            result = {**response(200), 'ContentLength': len(data), 'ETag': hashlib.md5(data).hexdigest(),
                'ContentType': mime, 'Metadata': {'sha256': sha, **self.metadata.get(Key, {})}}
            if self.version is not None:
                result['VersionId'] = self.version
            return result

    def get_object(self, Bucket, Key, IfMatch, **kwargs):
        result = self.head_object(Bucket, Key)
        if result['ETag'] != IfMatch:
            raise failure(412, 'PreconditionFailed')
        return {**result, 'Body': BytesIO(self.objects[Key][0])}

    def put_object(self, **params):
        if self.before_put:
            self.before_put(params)
        with self.lock:
            self.puts.append({k: v for k, v in params.items() if k != 'Body'})
            key = params['Key']
            old = self.objects.get(key)
            if params.get('IfNoneMatch') == '*' and old is not None:
                raise failure(412, 'PreconditionFailed')
            if 'IfMatch' in params and (old is None or hashlib.md5(old[0]).hexdigest() != params['IfMatch']):
                raise failure(412, 'PreconditionFailed')
            data = params['Body']
            self.objects[key] = (data, params['ContentType'], params['Metadata']['sha256'])
            self.metadata[key] = params['Metadata']
        if self.lose_response:
            self.lose_response = False
            raise TimeoutError('private fixture response lost')
        return response(200)


class FenceStorage(FakeStorage):
    retained_create_only = permanent_payload_fence = True

    def __init__(self):
        super().__init__()
        self.sdk = ConditionalSDK(self.objects)
        self.port = R2Storage(self.sdk, self.bucket, 'https://fixture.invalid')

    def retire_payload(self, key, operation_id, maximum):
        self.operations.append('retire')
        return self.port.retire_payload(key, operation_id, maximum)


class Approved:
    def __init__(self):
        self.calls = []

    def verify(self, command, scope):
        self.calls.append((command, scope))
        return MediaDeletionAuthority(command=command, scope_hash=scope.scope_hash,
            policy_hash='b' * 64, verified_at=datetime.now(timezone.utc))


def configured(service):
    store = FenceStorage()
    service.config = replace(service.config, fenced_retirement_enabled=True)
    service.runtime = replace(service.runtime, config=service.config, storage=store, deletion_authority=Approved())
    return service, store


def command(identity, **updates):
    return PrivacyMediaDeletionCommand(authority_id=uuid4(), receipt_id=uuid4(), asset_id=identity,
        operation_id=uuid4(), **updates)


def granted(service, store, ready=False):
    grant = service.initiate(ACTOR, uuid4(), intent(), uuid4())
    store.objects[store.last_key] = (png(), 'image/png', None)
    if ready:
        service.complete(ACTOR, grant.asset.id, uuid4(), 1, uuid4())
    return grant.asset.id


def rows(service, identity):
    with service.db.begin():
        upload = service.db.get(SocialMediaUpload, identity)
        budget = service.db.get(SocialMediaBudget, 'global')
        return upload.reserved_bytes, upload.fenced_copies, budget.bytes_used, budget.pending_count


def test_lifetime_admission_is_bounded_even_after_payloads_shrink(media):
    service, store = configured(media[0])
    service.config = replace(service.config, max_actor_assets=1)
    identity = granted(service, store)
    assert execute_deletion(service, command(identity)).state == 'complete'
    with pytest.raises(SocialError, match='MEDIA_QUOTA_EXCEEDED'):
        service.initiate(ACTOR, uuid4(), intent(), uuid4())
    assert rows(service, identity) == (2, 2, 2, 0)


def test_permanent_fences_preserve_unknown_epochs_and_charge_marker_bytes(media):
    service, store = configured(media[0])
    identity = granted(service, store)
    operation = command(identity)
    result = execute_deletion(service, operation)
    assert result.state == 'complete' and result.verified_deleted
    assert result.write_quiescence_proven is False
    assert rows(service, identity) == (2, 2, 2, 0)
    with service.db.begin():
        upload = service.db.get(SocialMediaUpload, identity)
        asset = service.db.get(SocialMediaAsset, identity)
        assert upload.grant_epoch == 1 and upload.grant_settled_epoch == 0
        assert upload.write_protocol == WRITE_PROTOCOL and not upload.reservation_released
        assert asset.state == 'archived' and asset.deleted_at is not None
    assert [value[0] for value in store.objects.values()] == [FENCE_BODY, FENCE_BODY]
    before = list(store.sdk.puts)
    assert execute_deletion(service, operation) == result
    assert store.sdk.puts == before and service.cleanup() == 0


def test_late_put_wins_before_fence_then_is_replaced_without_gap(media):
    service, store = configured(media[0])
    identity = granted(service, store)
    with service.db.begin():
        key = service.db.get(SocialMediaUpload, identity).quarantine_key
    del store.objects[key]
    inserted = []
    def late(params):
        if params['Key'] == key and not inserted:
            inserted.append(True)
            # Already admitted browser PUT commits before fence IfNoneMatch.
            store.objects[key] = (png(), 'image/png', None)
    store.sdk.before_put = late
    assert execute_deletion(service, command(identity)).verified_deleted
    assert inserted == [True] and store.objects[key][0] == FENCE_BODY
    with pytest.raises(ClientError):
        store.sdk.put_object(Bucket=store.bucket, Key=key, Body=png(), ContentType='image/png',
            Metadata={}, IfNoneMatch='*')
    assert store.objects[key][0] == FENCE_BODY


def test_lost_response_retains_full_capacity_then_exact_retry_recovers(media):
    service, store = configured(media[0])
    identity = granted(service, store)
    operation = command(identity)
    store.sdk.lose_response = True
    first = execute_deletion(service, operation)
    assert first.state == 'uncertain' and first.verified_deleted is False
    assert rows(service, identity) == (2 * len(png()), 0, 2 * len(png()), 1)
    assert execute_deletion(service, command(identity)).state == 'blocked'
    second = execute_deletion(service, operation)
    assert second.verified_deleted and rows(service, identity) == (2, 2, 2, 0)


def test_default_authority_and_legacy_protocol_do_no_storage_effects(media):
    service, store = media
    identity = granted(service, store)
    assert execute_deletion(service, command(identity)).state == 'disabled'
    service, safe = configured(service)
    assert execute_deletion(service, command(identity)).state == 'blocked'
    assert safe.sdk.puts == [] and rows(service, identity)[0] == 2 * len(png())
    fresh = granted(service, safe)
    from social.media.deletion import UnsupportedMediaDeletionAuthority
    service.runtime = replace(service.runtime, deletion_authority=UnsupportedMediaDeletionAuthority())
    assert execute_deletion(service, command(fresh)).state == 'blocked' and safe.sdk.puts == []


def test_historical_reference_blocks_original_but_allows_quarantine_retirement(media):
    from social.contracts import CreatePost
    from social.service import SocialService
    service, store = configured(media[0])
    identity = granted(service, store, ready=True)
    domain = SocialService(service.db)
    body = CreatePost.model_validate({'title': 'Keep evidence', 'content_type': 'announcement',
        'document': {'master': {'media': [{'asset_id': str(identity)}]}, 'targets': []}})
    domain.command(actor=ACTOR, route='fixture.reference', key=uuid4(), body=body.model_dump(mode='json'),
        request_id=uuid4(), action=lambda: domain.create(body))
    assert execute_deletion(service, command(identity)).state == 'blocked'
    result = execute_deletion(service, command(identity, mode='quarantine'))
    assert result.state == 'complete' and result.verified_deleted is False
    assert rows(service, identity) == (len(png()) + 1, 1, len(png()) + 1, 0)
    with service.db.begin():
        asset = service.db.get(SocialMediaAsset, identity)
        assert asset.state == 'ready' and asset.deleted_at is None
        assert store.objects[asset.storage_key][0] == png()
    assert service.preview(identity).asset.id == identity
    assert execute_deletion(service, command(identity)).state == 'blocked'


def test_quarantine_then_all_credits_only_remaining_copy(media):
    service, store = configured(media[0])
    identity = granted(service, store, ready=True)
    assert execute_deletion(service, command(identity, mode='quarantine')).state == 'complete'
    assert execute_deletion(service, command(identity)).verified_deleted
    assert rows(service, identity) == (2, 2, 2, 0)


def test_wrong_scope_and_malformed_authority_are_refused(media):
    service, store = configured(media[0])
    identity = granted(service, store)
    class Wrong:
        def verify(self, cmd, scope):
            return MediaDeletionAuthority(command=cmd, scope_hash='f' * 64,
                policy_hash='b' * 64, verified_at=datetime.now(timezone.utc))
    service.runtime = replace(service.runtime, deletion_authority=Wrong())
    assert execute_deletion(service, command(identity)).state == 'blocked'
    assert store.sdk.puts == []


@pytest.mark.parametrize('bad', [None, {}, [], True, 'yes', 1, 0])
def test_truthy_failed_or_missing_authority_is_not_approval(media, bad):
    service, store = configured(media[0])
    identity = granted(service, store)
    class Bad:
        def verify(self, cmd, scope): return bad
    service.runtime = replace(service.runtime, deletion_authority=Bad())
    assert execute_deletion(service, command(identity)).state == 'blocked' and store.sdk.puts == []


def test_versioned_storage_and_forged_marker_bytes_preserve_uncertainty(media):
    service, store = configured(media[0])
    identity = granted(service, store)
    store.sdk.version = 'retained-version'
    operation = command(identity)
    assert execute_deletion(service, operation).state == 'uncertain'
    assert rows(service, identity)[2:] == (2 * len(png()), 1)
    store.sdk.version = None
    store.sdk.lose_response = True
    assert execute_deletion(service, operation).state == 'uncertain'
    key = next(key for key in store.sdk.metadata)
    data, mime, sha = store.objects[key]
    store.objects[key] = (b'x', mime, sha)
    assert execute_deletion(service, operation).state == 'uncertain'
    assert rows(service, identity)[2:] == (2 * len(png()), 1)


def test_retention_expiry_requires_age_and_policy(media):
    service, store = configured(media[0])
    identity = granted(service, store, ready=True)
    operation = command(identity, purpose='retention_expiry')
    assert execute_deletion(service, operation).state == 'blocked'
    with service.db.begin():
        service.db.get(SocialMediaAsset, identity).created_at = service.now() - timedelta(days=31)
    assert execute_deletion(service, operation).verified_deleted


def test_lifetime_limit_blocks_second_intent_before_signing(media):
    service, store = configured(media[0])
    service.config = replace(service.config, max_actor_assets=1)
    granted(service, store)
    operations = list(store.operations)
    with pytest.raises(SocialError, match='MEDIA_QUOTA_EXCEEDED'):
        service.initiate(ACTOR, uuid4(), intent(), uuid4())
    assert store.operations == operations


def test_admin_retirement_routes_enforce_authority_and_keep_private_headers(media):
    from test_media_api import client, BASE
    service, store = configured(media[0])
    identity = granted(service, store)
    api = client((service, store))
    body = command(identity).model_dump(mode='json')
    anonymous = client((service, store), None).post(BASE + f'/assets/{identity}/retire', json=body)
    assert anonymous.status_code in {401, 403}
    assert anonymous.headers['cache-control'] == 'private, no-store'
    invalid = api.post(BASE + f'/assets/{uuid4()}/retire', json=body)
    assert invalid.status_code == 422 and store.sdk.puts == []
    result = api.post(BASE + f'/assets/{identity}/retire', json=body)
    assert result.status_code == 200 and result.json()['verified_deleted'] is True
    assert result.headers['cache-control'] == 'private, no-store'
    observed = api.get(BASE + '/maintenance')
    assert observed.status_code == 200 and observed.json()['write_quiescence_proven'] is False


@pytest.mark.parametrize('metadata', [response(500)['ResponseMetadata'], {'HTTPStatusCode': True, 'RetryAttempts': 0},
    {'HTTPStatusCode': 200, 'RetryAttempts': True}, {'HTTPStatusCode': 200, 'RetryAttempts': 1}, {}, None])
def test_marker_get_must_confirm_single_success_before_byte_credit(media, metadata):
    service, store = configured(media[0])
    identity = granted(service, store)
    original = store.sdk.get_object
    def malformed(**params):
        return {**original(**params), 'ResponseMetadata': metadata}
    store.sdk.get_object = malformed
    assert execute_deletion(service, command(identity)).state == 'uncertain'
    assert rows(service, identity) == (2 * len(png()), 0, 2 * len(png()), 1)


def test_retained_pair_can_retire_without_rewriting_immutable_retained_history(media):
    service, store = configured(media[0])
    service.config = replace(service.config, retained_writes_enabled=True)
    service.runtime = replace(service.runtime, config=service.config)
    identity = granted(service, store, ready=True)
    with service.db.begin():
        marker = service.db.get(SocialMediaUpload, identity).retained_write_fence
        assert marker is not None
    assert execute_deletion(service, command(identity)).verified_deleted
    with service.db.begin():
        assert service.db.get(SocialMediaUpload, identity).retained_write_fence == marker
    assert rows(service, identity) == (2, 2, 2, 0)


def test_operator_reports_permanent_fences_and_raw_uncertainty_without_legacy_gap(media):
    from social.media.operator import prepare_reconciliation
    service, store = configured(media[0])
    identity = granted(service, store)
    assert execute_deletion(service, command(identity)).verified_deleted
    report = prepare_reconciliation(service)
    assert report.completed_retirements == 1 and report.uncertain_retirements == 0
    assert report.permanent_fence_bytes == 2 and report.lifetime_admitted_assets == 1
    assert report.legacy_released_write_hazards == 0 and report.reason_codes == ()
    assert report.uploads[0].payload_fenced_copies == 2
    assert report.write_quiescence_proven is False
    assert 'PAYLOAD_FENCED_NOT_WRITE_DRAINED' in report.uploads[0].reason_codes


def test_operator_command_reaches_service_and_replays_exact_original_scope(media, monkeypatch, tmp_path, capsys):
    from social.media.maintenance import main
    service, store = configured(media[0])
    identity = granted(service, store)
    original = command(identity)
    path = tmp_path / 'command.json'
    path.write_text(original.model_dump_json())
    monkeypatch.setattr('social.media.maintenance.create_worker_engine', lambda config: service.db.bind)
    monkeypatch.setattr('social.media.maintenance.media_runtime', lambda: service.runtime)
    monkeypatch.setattr(service.db.bind, 'dispose', lambda: None)
    argv = ['--database-url', 'postgresql+psycopg2://fixture@127.0.0.1:55394/fixture', '--retire-command', str(path)]
    assert main(argv) == 0
    assert '"verified_deleted":true' in capsys.readouterr().out
    before = list(store.sdk.puts)
    assert main(argv) == 0
    assert store.sdk.puts == before
    assert '"state":"complete"' in capsys.readouterr().out


def test_operator_disabled_retirement_exits_nonzero_with_honest_status(media, monkeypatch, tmp_path, capsys):
    from social.media.maintenance import main
    service, store = media
    identity = granted(service, store)
    path = tmp_path / 'command.json'
    path.write_text(command(identity).model_dump_json())
    monkeypatch.setattr('social.media.maintenance.create_worker_engine', lambda config: service.db.bind)
    monkeypatch.setattr('social.media.maintenance.media_runtime', lambda: service.runtime)
    monkeypatch.setattr(service.db.bind, 'dispose', lambda: None)
    assert main(['--database-url', 'postgresql+psycopg2://fixture@127.0.0.1:55394/fixture', '--retire-command', str(path)]) == 1
    assert '"state":"disabled"' in capsys.readouterr().out


@pytest.mark.parametrize('content', ['{}', 'not-json-private', 'x' * 4097])
def test_operator_refuses_invalid_retirement_file_before_engine(media, monkeypatch, tmp_path, capsys, content):
    from social.media.maintenance import main
    path = tmp_path / 'command.json'
    path.write_text(content)
    calls = []
    def forbidden(config):
        calls.append(True)
        raise AssertionError('must refuse before connection')
    monkeypatch.setattr('social.media.maintenance.create_worker_engine', forbidden)
    assert main(['--database-url', 'postgresql+psycopg2://fixture@127.0.0.1:55394/fixture', '--retire-command', str(path)]) == 1
    assert calls == [] and 'not-json-private' not in capsys.readouterr().out


@pytest.mark.parametrize('kind', ['fifo', 'symlink', 'directory'])
def test_operator_command_special_files_refuse_without_waiting_or_engine(media, monkeypatch, tmp_path, capsys, kind):
    import os
    from social.media.maintenance import main
    path = tmp_path / 'input'
    if kind == 'fifo':
        os.mkfifo(path)
    elif kind == 'symlink':
        target = tmp_path / 'regular'
        target.write_text(command(uuid4()).model_dump_json())
        path.symlink_to(target)
    else:
        path.mkdir()
    calls = []
    def forbidden(config):
        calls.append(True)
        raise AssertionError('must refuse before connection')
    monkeypatch.setattr('social.media.maintenance.create_worker_engine', forbidden)
    assert main(['--database-url', 'fixture-only', '--retire-command', str(path)]) == 1
    assert calls == [] and 'error_code' in capsys.readouterr().out

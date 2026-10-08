"""Execute the real R2 port with hostile SDK outputs; no network or credentials."""
import hashlib
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import pytest

from social.media.storage import ObjectSnapshot, R2Storage, StorageFailure


ORIGIN = 'fixture-r2.example.org'
KEY = 'finalized/fixture-asset.png'
BUCKET = 'fixture-private-media'
GOOD = b'good bytes'
BAD = b'evil bytes'
HASH = hashlib.sha256(GOOD).hexdigest()


def signed_url(headers='host;content-length;content-type;if-none-match', **changes):
    query = {
        'X-Amz-Algorithm': 'AWS4-HMAC-SHA256',
        'X-Amz-Credential': 'fixture/20261003/auto/s3/aws4_request',
        'X-Amz-Date': '20261003T120000Z',
        'X-Amz-Expires': '300',
        'X-Amz-SignedHeaders': headers,
        'X-Amz-Signature': 'a' * 64,
    }
    query.update(changes)
    return f'https://{ORIGIN}/{BUCKET}/{KEY}?{urlencode(query)}'


class Stream:
    def __init__(self, chunks, *, read_error=False, close_error=False):
        self.chunks = iter(chunks)
        self.read_error, self.close_error = read_error, close_error
        self.closed = False
        self.requests = []

    def read(self, amount):
        self.requests.append(amount)
        if self.read_error:
            raise RuntimeError('fixture-private-read-error')
        return next(self.chunks, b'')

    def close(self):
        self.closed = True
        if self.close_error:
            raise RuntimeError('fixture-private-close-error')


class SDK:
    def __init__(self, *, data=GOOD, size=None, etag='"fixture-etag"', version='v1', digest=HASH, mime='image/png', url=None, create_error=False, read_error=False, close_error=False, chunks=None):
        self.data = data
        self.size = len(data) if size is None else size
        self.etag, self.version = etag, version
        self.digest, self.mime = digest, mime
        self.url = signed_url() if url is None else url
        self.create_error = create_error
        self.fresh_object_stream = chunks is None and not read_error and not close_error
        self.stream = Stream([data] if chunks is None else chunks, read_error=read_error, close_error=close_error)
        self.calls = []
        self.response_changes = {}
        self.head_changes = {}
        self.meta = SimpleNamespace(config=SimpleNamespace(retries={'total_max_attempts': 1}))

    def delete_object(self, **params):
        self.calls.append(('delete_object', params))
        return {'ResponseMetadata': {'HTTPStatusCode': 204, 'RetryAttempts': 0}}

    def generate_presigned_url(self, operation, **params):
        self.calls.append((operation, params))
        return self.url

    def head_object(self, **params):
        self.calls.append(('head_object', params))
        return {'ContentLength': self.size, 'ETag': self.etag, 'VersionId': self.version, 'Metadata': {'sha256': self.digest}, 'ContentType': self.mime, **self.head_changes}

    def get_object(self, **params):
        self.calls.append(('get_object', params))
        if self.fresh_object_stream:
            self.stream = Stream([self.data])
        return {'ContentLength': self.size, 'ETag': self.etag, 'VersionId': self.version, 'Body': self.stream, **self.response_changes}

    def put_object(self, **params):
        self.calls.append(('put_object', {key: value for key, value in params.items() if key != 'Body'}))
        if self.create_error:
            from botocore.exceptions import ClientError
            raise ClientError({'Error': {'Code': 'PreconditionFailed'}, 'ResponseMetadata': {'HTTPStatusCode': 412, 'RetryAttempts': 0}}, 'PutObject')
        self.data = params['Body'].read()
        self.size = len(self.data)
        self.digest = params['Metadata']['sha256']
        self.mime = params['ContentType']
        return {'ResponseMetadata': {'HTTPStatusCode': 200, 'RetryAttempts': 0}}


def storage(sdk):
    return R2Storage(sdk, BUCKET, f'https://{ORIGIN}')


def snapshot(sdk, **overrides):
    return ObjectSnapshot(**{'size': sdk.size, 'etag': sdk.etag, 'version': sdk.version, 'sha256': sdk.digest, 'mime_type': sdk.mime, **overrides})


def test_finalize_must_not_accept_reused_key_whose_metadata_lies_about_actual_bytes(tmp_path):
    local = tmp_path / 'inspected.png'
    local.write_bytes(GOOD)
    sdk = SDK(data=BAD, digest=HASH, create_error=True)
    assert len(BAD) == len(GOOD)
    assert hashlib.sha256(sdk.data).hexdigest() != HASH
    with pytest.raises(StorageFailure):
        storage(sdk).finalize(local, KEY, len(GOOD), 'image/png', HASH)


def test_finalize_cannot_turn_local_read_failure_into_confirmation_of_a_wrong_existing_object(tmp_path):
    sdk = SDK(data=BAD, digest=HASH, create_error=True)
    with pytest.raises(StorageFailure):
        storage(sdk).finalize(tmp_path / 'missing-inspected-file', KEY, len(GOOD), 'image/png', HASH)


def test_identical_finalize_recovery_remains_supported(tmp_path):
    local = tmp_path / 'inspected.png'
    local.write_bytes(GOOD)
    sdk = SDK(create_error=True)
    result = storage(sdk).finalize(local, KEY, len(GOOD), 'image/png', HASH)
    assert result.size == len(GOOD) and result.sha256 == HASH
    assert sdk.data == GOOD


def test_create_only_finalize_uses_the_real_inspected_local_file(tmp_path):
    local = tmp_path / 'inspected.png'
    local.write_bytes(GOOD)
    sdk = SDK(data=b'')
    result = storage(sdk).finalize(local, KEY, len(GOOD), 'image/png', HASH)
    assert sdk.data == GOOD and result.sha256 == HASH
    assert next(params for operation, params in sdk.calls if operation == 'put_object')['IfNoneMatch'] == '*'


@pytest.mark.parametrize('url', [
    signed_url(headers='host;content-type;if-none-match'),
    signed_url(headers='host;content-length;content-type'),
    signed_url(headers='content-length;content-type;if-none-match'),
    signed_url().replace(ORIGIN, 'attacker.example.org'),
    signed_url().replace('https://', 'http://'),
    signed_url().replace(f'https://{ORIGIN}', f'https://fixture-user:fixture-password@{ORIGIN}'),
    f'https://{ORIGIN}/{BUCKET}/{KEY}',
])
def test_upload_signer_missing_guards_or_unsafe_origin_is_rejected(url):
    with pytest.raises(StorageFailure):
        storage(SDK(url=url)).authorize_upload(KEY, len(GOOD), 'image/png', 300)


@pytest.mark.parametrize('url', [
    f'https://{ORIGIN}/{BUCKET}/{KEY}?X-Amz-SignedHeaders=host%3Bcontent-length%3Bcontent-type%3Bif-none-match',
    signed_url() + '&X-Amz-SignedHeaders=host',
    signed_url(**{'X-Amz-Signature': ''}),
    signed_url().replace(f'/{BUCKET}/{KEY}', f'/{BUCKET}/different-asset.png'),
    signed_url().replace(f'https://{ORIGIN}', f'https://{ORIGIN}:9999'),
    signed_url().replace('/finalized/', '/finalized/\n'),
])
def test_upload_signer_cannot_certify_unsigned_ambiguous_or_differently_bound_url(url):
    with pytest.raises(StorageFailure):
        storage(SDK(url=url)).authorize_upload(KEY, len(GOOD), 'image/png', 300)


@pytest.mark.parametrize('size', [True, False, 0, -1, 1.5, float('nan'), float('inf')])
def test_upload_authorization_rejects_invalid_exact_body_lengths(size):
    with pytest.raises(StorageFailure):
        storage(SDK()).authorize_upload(KEY, size, 'image/png', 300)


@pytest.mark.parametrize('size', [True, False, 0, -1, 1.5, float('nan'), float('inf')])
def test_head_rejects_invalid_lengths(size):
    with pytest.raises(StorageFailure):
        storage(SDK(size=size)).head(KEY)


def test_bounded_download_reads_only_requested_chunks_and_closes_response(tmp_path):
    sdk = SDK(chunks=[GOOD[:3], GOOD[3:]])
    dest = tmp_path / 'download.png'
    storage(sdk).download(KEY, snapshot(sdk), dest, len(GOOD))
    assert dest.read_bytes() == GOOD and sdk.stream.closed
    assert sdk.stream.requests and max(sdk.stream.requests) <= 256 * 1024
    request = next(params for operation, params in sdk.calls if operation == 'get_object')
    assert request['IfMatch'] == sdk.etag and request['VersionId'] == sdk.version


@pytest.mark.parametrize('chunks', [[], [b''], [GOOD[:-1]], [GOOD + b'!'], [GOOD[:1], GOOD]])
def test_empty_truncated_and_oversized_downloads_fail_and_close(chunks, tmp_path):
    sdk = SDK(chunks=chunks)
    dest = tmp_path / 'download.png'
    with pytest.raises(StorageFailure):
        storage(sdk).download(KEY, snapshot(sdk), dest, len(GOOD))
    assert sdk.stream.closed
    if dest.exists():
        assert dest.stat().st_size <= len(GOOD)


@pytest.mark.parametrize('maximum', [True, 1.0, float('nan'), float('inf')])
def test_invalid_bounded_download_limits_do_not_become_permissive(maximum, tmp_path):
    sdk = SDK(data=b'1', digest=hashlib.sha256(b'1').hexdigest())
    with pytest.raises(StorageFailure):
        storage(sdk).download(KEY, snapshot(sdk), tmp_path / 'download.png', maximum)


@pytest.mark.parametrize('declared', [True, 1.0])
def test_snapshot_length_must_be_an_actual_integer_not_numerically_equal(declared, tmp_path):
    sdk = SDK(data=b'1', digest=hashlib.sha256(b'1').hexdigest())
    with pytest.raises(StorageFailure):
        storage(sdk).download(KEY, snapshot(sdk, size=declared), tmp_path / 'download.png', 1)


@pytest.mark.parametrize('declared', [True, 1.0])
def test_download_response_length_must_not_accept_bool_or_float_equality(declared, tmp_path):
    sdk = SDK(data=b'1', digest=hashlib.sha256(b'1').hexdigest())
    sdk.response_changes['ContentLength'] = declared
    with pytest.raises(StorageFailure):
        storage(sdk).download(KEY, snapshot(sdk), tmp_path / 'download.png', 1)


@pytest.mark.parametrize('metadata', [{'ETag': '"other-etag"'}, {'ContentLength': len(GOOD) + 1}])
def test_rejected_response_metadata_still_closes_its_stream(metadata, tmp_path):
    sdk = SDK()
    sdk.response_changes.update(metadata)
    with pytest.raises(StorageFailure):
        storage(sdk).download(KEY, snapshot(sdk), tmp_path / 'download.png', len(GOOD))
    assert sdk.stream.closed


def test_response_version_cannot_differ_from_the_snapshot_even_with_the_same_etag(tmp_path):
    sdk = SDK()
    sdk.response_changes['VersionId'] = 'other-version'
    with pytest.raises(StorageFailure):
        storage(sdk).download(KEY, snapshot(sdk), tmp_path / 'download.png', len(GOOD))


@pytest.mark.parametrize('metadata', [{'ETag': '"other-etag"'}, {'VersionId': 'other-version'}])
def test_post_download_identity_change_is_rejected(metadata, tmp_path):
    sdk = SDK()
    sdk.head_changes.update(metadata)
    with pytest.raises(StorageFailure):
        storage(sdk).download(KEY, snapshot(sdk), tmp_path / 'download.png', len(GOOD))
    assert sdk.stream.closed


def test_stream_read_failure_is_sanitized_and_closed(tmp_path):
    sdk = SDK(read_error=True)
    with pytest.raises(StorageFailure) as error:
        storage(sdk).download(KEY, snapshot(sdk), tmp_path / 'download.png', len(GOOD))
    assert 'fixture-private-read-error' not in str(error.value)
    assert sdk.stream.closed


@pytest.mark.parametrize('chunks', [[GOOD], []])
def test_stream_close_failure_cannot_escape_or_replace_a_sanitized_storage_failure(chunks, tmp_path):
    sdk = SDK(chunks=chunks, close_error=True)
    with pytest.raises(StorageFailure) as error:
        storage(sdk).download(KEY, snapshot(sdk), tmp_path / 'download.png', len(GOOD))
    assert 'fixture-private-close-error' not in str(error.value)


@pytest.mark.parametrize('url', [
    signed_url(headers=''),
    signed_url(headers='host').replace(ORIGIN, 'attacker.example.org'),
    signed_url(headers='host').replace(f'https://{ORIGIN}', f'https://fixture-user@{ORIGIN}'),
])
def test_preview_rejects_missing_host_binding_wrong_origin_and_credentials(url):
    sdk = SDK(url=url)
    with pytest.raises(StorageFailure):
        storage(sdk).preview(KEY, snapshot(sdk), 300)


def test_complete_signed_upload_and_private_preview_remain_usable():
    sdk = SDK()
    access = storage(sdk).authorize_upload(KEY, len(GOOD), 'image/png', 300)
    assert access.headers == {'Content-Type': 'image/png', 'If-None-Match': '*'}
    sdk.url = signed_url(headers='host')
    assert storage(sdk).preview(KEY, snapshot(sdk), 300).url == sdk.url


@pytest.mark.parametrize('field', ['X-Amz-Credential', 'X-Amz-Date'])
def test_signed_url_missing_required_authentication_query_field_is_not_certified(field):
    parts = urlsplit(signed_url())
    query = parse_qs(parts.query)
    del query[field]
    malformed = urlunsplit(parts._replace(query=urlencode(query, doseq=True)))
    with pytest.raises(StorageFailure):
        storage(SDK(url=malformed)).authorize_upload(KEY, len(GOOD), 'image/png', 300)


def test_bytes_subclass_cannot_lie_about_its_length_and_exceed_the_download_bound(tmp_path):
    class LyingBytes(bytes):
        def __len__(self):
            return 1

    sdk = SDK(data=b'1', chunks=[LyingBytes(b'x' * 300_000)])
    dest = tmp_path / 'download.png'
    with pytest.raises(StorageFailure):
        storage(sdk).download(KEY, snapshot(sdk), dest, 1)
    assert not dest.exists() or dest.stat().st_size <= 1


def test_ambiguous_put_cannot_be_settled_by_a_matching_head(tmp_path):
    local=tmp_path/'inspected.png'; local.write_bytes(GOOD)
    sdk=SDK()
    def ambiguous(**params): raise TimeoutError('unknown remote write; identical bytes already exist')
    sdk.put_object=ambiguous
    with pytest.raises(StorageFailure): storage(sdk).finalize(local,KEY,len(GOOD),'image/png',HASH)
    assert not any(operation=='head_object' for operation,_ in sdk.calls)


@pytest.mark.parametrize('response',[None,{}, {'ResponseMetadata':{'HTTPStatusCode':200,'RetryAttempts':1}}, {'ResponseMetadata':{'HTTPStatusCode':True,'RetryAttempts':0}}])
def test_finalize_requires_a_confirmed_single_wire_success_response(tmp_path,response):
    local=tmp_path/'inspected.png'; local.write_bytes(GOOD); sdk=SDK()
    sdk.put_object=lambda **params:response
    with pytest.raises(StorageFailure): storage(sdk).finalize(local,KEY,len(GOOD),'image/png',HASH)


@pytest.mark.parametrize('response', [None, [], {}, {'ResponseMetadata': None}, {'ResponseMetadata': {'HTTPStatusCode': 200, 'RetryAttempts': 0}}, {'ResponseMetadata': {'HTTPStatusCode': 204, 'RetryAttempts': 1}}, {'ResponseMetadata': {'HTTPStatusCode': 204, 'RetryAttempts': False}}, {'ResponseMetadata': {'HTTPStatusCode': 204.0, 'RetryAttempts': 0}}])
def test_delete_requires_an_actual_single_attempt_http204_ack(response):
    sdk = SDK()
    sdk.delete_object = lambda **params: response
    with pytest.raises(StorageFailure): storage(sdk).delete(KEY)


def test_delete_normal_ack_uses_exact_bucket_and_key():
    sdk = SDK()
    storage(sdk).delete(KEY)
    assert sdk.calls == [('delete_object', {'Bucket': BUCKET, 'Key': KEY})]


@pytest.mark.parametrize('retries', [None, {}, {'max_attempts': 1}, {'total_max_attempts': 2}, {'total_max_attempts': True}, {'total_max_attempts': 1.0}])
def test_mutations_reject_sdk_retry_configuration_before_any_remote_write(retries, tmp_path):
    sdk = SDK()
    sdk.meta.config.retries = retries
    local = tmp_path / 'source'; local.write_bytes(GOOD)
    with pytest.raises(StorageFailure): storage(sdk).delete(KEY)
    with pytest.raises(StorageFailure): storage(sdk).finalize(local, KEY, len(GOOD), 'image/png', HASH)
    assert sdk.calls == []


def test_signed_access_uses_signature_date_instead_of_a_caller_clock():
    from datetime import datetime, timezone
    access = storage(SDK()).authorize_upload(KEY, len(GOOD), 'image/png', 300)
    assert access.expires_at == datetime(2026, 10, 3, 12, 5, tzinfo=timezone.utc)


def test_invalid_calendar_signature_date_is_not_certified():
    with pytest.raises(StorageFailure):
        storage(SDK(url=signed_url(**{'X-Amz-Date': '20269999T999999Z'}))).authorize_upload(KEY, len(GOOD), 'image/png', 300)


@pytest.mark.parametrize('retained_version', [{'DeleteMarker': True}, {'DeleteMarker': False}, {'VersionId': 'retained-version'}])
def test_delete_marker_does_not_prove_physical_bytes_were_removed(retained_version):
    sdk = SDK()
    sdk.delete_object = lambda **params: {'ResponseMetadata': {'HTTPStatusCode': 204, 'RetryAttempts': 0}, **retained_version}
    with pytest.raises(StorageFailure): storage(sdk).delete(KEY)

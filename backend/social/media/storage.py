"""One private R2/S3 port. Object bytes stream to/from bounded local files."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
from typing import Protocol
from urllib.parse import parse_qs, quote, urlsplit

MAXIMUM = 50 * 1024 * 1024
MIMES = {'image/jpeg', 'image/png', 'video/mp4'}


class StorageFailure(Exception):
    """Sanitized failure: never includes an SDK response, URL or credential."""


@dataclass(frozen=True)
class ObjectSnapshot:
    size: int
    etag: str
    version: str | None = None
    sha256: str | None = None
    mime_type: str | None = None


@dataclass(frozen=True)
class SignedAccess:
    url: str = field(repr=False)
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    expires_at: datetime | None = None


class MediaStorage(Protocol):
    provider: str
    bucket: str
    def authorize_upload(self, key: str, size: int, mime: str, ttl: int) -> SignedAccess: ...
    def head(self, key: str) -> ObjectSnapshot: ...
    def download(self, key: str, snapshot: ObjectSnapshot, path: Path, maximum: int) -> None: ...
    def finalize(self, path: Path, key: str, size: int, mime: str, sha256: str) -> ObjectSnapshot: ...
    def preview(self, key: str, snapshot: ObjectSnapshot, ttl: int) -> SignedAccess: ...
    def delete(self, key: str) -> None: ...


def bounded(value, maximum=MAXIMUM):
    if type(value) is not int or not 1 <= value <= maximum:
        raise StorageFailure('Invalid bounded storage operation')


class R2Storage:
    provider = 'r2'

    def __init__(self, client, bucket: str, endpoint: str):
        self.client, self.bucket = client, bucket
        self.origin = urlsplit(endpoint).hostname

    def _signed(self, url, key, ttl, required=()):
        if not isinstance(url, str) or len(url) > 8000 or any(ord(c) < 32 or ord(c) == 127 for c in url):
            raise StorageFailure('Storage signing capabilities are unavailable')
        parsed = urlsplit(url); params = parse_qs(parsed.query, keep_blank_values=True)
        if not params.get('X-Amz-Credential', [''])[0] or not re.fullmatch('[0-9]{8}T[0-9]{6}Z', params.get('X-Amz-Date', [''])[0]):
            raise StorageFailure('Storage signing capabilities are unavailable')
        header_names = params.get('X-Amz-SignedHeaders', [''])[0].split(';')
        if len(header_names) > 16 or any(not re.fullmatch('[a-z][a-z0-9-]{0,63}', name) for name in header_names) or header_names != sorted(set(header_names)):
            raise StorageFailure('Storage signing capabilities are unavailable')
        headers = set(header_names)
        if parsed.scheme != 'https' or parsed.hostname != self.origin or parsed.port not in {None, 443} or parsed.username or parsed.password or parsed.fragment or parsed.path != '/' + quote(self.bucket, safe='') + '/' + quote(key, safe='/') or any(len(v) != 1 for v in params.values()) or not re.fullmatch('[0-9a-f]{64}', params.get('X-Amz-Signature', [''])[0]) or params.get('X-Amz-Algorithm') != ['AWS4-HMAC-SHA256'] or params.get('X-Amz-Expires') != [str(ttl)] or not set(required) <= headers:
            raise StorageFailure('Storage signing capabilities are unavailable')
        return url

    def authorize_upload(self, key, size, mime, ttl):
        bounded(size); bounded(ttl, 600)
        if mime not in MIMES: raise StorageFailure('Unsupported storage media type')
        try:
            url = self.client.generate_presigned_url('put_object', Params={'Bucket': self.bucket, 'Key': key, 'ContentLength': size, 'ContentType': mime, 'IfNoneMatch': '*'}, ExpiresIn=ttl, HttpMethod='PUT')
            # Browser File supplies Content-Length. Refuse SDKs that omit it.
            self._signed(url, key, ttl, ('host', 'content-length', 'content-type', 'if-none-match'))
            return SignedAccess(url, {'Content-Type': mime, 'If-None-Match': '*'}, self._expiration(url, ttl))
        except StorageFailure:
            raise
        except Exception:
            raise StorageFailure('Storage upload authorization is unavailable') from None

    def head(self, key):
        try:
            value = self.client.head_object(Bucket=self.bucket, Key=key)
            size, etag = value['ContentLength'], value['ETag']; bounded(size)
            version = value.get('VersionId')
            if not isinstance(etag, str) or not etag or version is not None and (not isinstance(version, str) or not version):
                raise StorageFailure('Object metadata is incomplete')
            return ObjectSnapshot(size, etag, version, value.get('Metadata', {}).get('sha256'), value.get('ContentType'))
        except StorageFailure:
            raise
        except Exception:
            raise StorageFailure('Object is unavailable') from None

    def _read(self, key, snapshot, maximum, consume):
        bounded(maximum); bounded(snapshot.size)
        if snapshot.size > maximum: raise StorageFailure('Object exceeds the bounded upload')
        body = None; failure = None
        try:
            params = {'Bucket': self.bucket, 'Key': key, 'IfMatch': snapshot.etag}
            if snapshot.version: params['VersionId'] = snapshot.version
            response = self.client.get_object(**params)
            body = response.get('Body')
            bounded(response.get('ContentLength'))
            if response.get('ETag') != snapshot.etag or response.get('ContentLength') != snapshot.size or response.get('VersionId') != snapshot.version:
                raise StorageFailure('Object changed before inspection')
            count = 0
            while chunk := body.read(256 * 1024):
                if type(chunk) is not bytes or len(chunk) > 256 * 1024:
                    raise StorageFailure('Object stream is invalid')
                count += len(chunk)
                if count > maximum or count > snapshot.size:
                    raise StorageFailure('Object exceeds the bounded upload')
                consume(chunk)
            if count != snapshot.size: raise StorageFailure('Object upload is incomplete')
            if self.head(key) != snapshot: raise StorageFailure('Object changed during inspection')
        except Exception:
            failure = StorageFailure('Object inspection download failed or changed')
        finally:
            if body is not None:
                try: body.close()
                except Exception: failure = StorageFailure('Object inspection stream did not close')
        if failure: raise failure from None

    def download(self, key, snapshot, path, maximum):
        try:
            with path.open('xb') as target: self._read(key, snapshot, maximum, target.write)
        except StorageFailure:
            raise
        except Exception:
            raise StorageFailure('Object inspection download failed') from None

    def finalize(self, path, key, size, mime, sha256):
        self._single_attempt()
        bounded(size)
        if mime not in MIMES or not isinstance(sha256, str) or not re.fullmatch('[0-9a-f]{64}', sha256):
            raise StorageFailure('Invalid inspected identity')
        try:
            # A local read failure cannot recover somebody else's object.
            with path.open('rb') as source:
                digest = hashlib.sha256(); count = 0
                for chunk in iter(lambda: source.read(256 * 1024), b''):
                    count += len(chunk)
                    if count > size: raise StorageFailure('Inspected file changed')
                    digest.update(chunk)
                if count != size or digest.hexdigest() != sha256: raise StorageFailure('Inspected file changed')
                source.seek(0)
                try:
                    response = self.client.put_object(Bucket=self.bucket, Key=key, Body=source, ContentLength=size, ContentType=mime, Metadata={'sha256': sha256}, IfNoneMatch='*')
                    metadata = response.get('ResponseMetadata', {}) if isinstance(response, dict) else {}
                    if type(metadata.get('HTTPStatusCode')) is not int or metadata['HTTPStatusCode'] != 200 or type(metadata.get('RetryAttempts')) is not int or metadata['RetryAttempts'] != 0:
                        raise StorageFailure('Storage creation completion is unknown')
                except Exception as error:
                    # A HEAD cannot settle a timed-out PUT that might still
                    # finish remotely. Recover only a confirmed rejected create.
                    from botocore.exceptions import ClientError
                    if not isinstance(error, ClientError) or error.response.get('ResponseMetadata', {}).get('HTTPStatusCode') != 412 or error.response.get('ResponseMetadata', {}).get('RetryAttempts') != 0 or error.response.get('Error', {}).get('Code') != 'PreconditionFailed':
                        raise StorageFailure('Storage creation completion is unknown') from None
            snapshot = self.head(key)
            if snapshot.size != size or snapshot.sha256 != sha256 or snapshot.mime_type != mime:
                raise StorageFailure('Finalized object did not confirm inspected identity')
            stored_digest = hashlib.sha256()
            self._read(key, snapshot, size, stored_digest.update)
            if stored_digest.hexdigest() != sha256:
                raise StorageFailure('Finalized bytes do not match inspected identity')
            return snapshot
        except StorageFailure:
            raise
        except Exception:
            raise StorageFailure('Finalized object identity is unconfirmed') from None

    def preview(self, key, snapshot, ttl):
        bounded(ttl, 300)
        try:
            params = {'Bucket': self.bucket, 'Key': key, 'ResponseContentType': snapshot.mime_type, 'ResponseContentDisposition': 'inline'}
            if snapshot.version: params['VersionId'] = snapshot.version
            url = self.client.generate_presigned_url('get_object', Params=params, ExpiresIn=ttl, HttpMethod='GET')
            return SignedAccess(self._signed(url, key, ttl, ('host',)), expires_at=self._expiration(url, ttl))
        except StorageFailure:
            raise
        except Exception:
            raise StorageFailure('Private preview is unavailable') from None

    def delete(self, key):
        self._single_attempt()
        try:
            response = self.client.delete_object(Bucket=self.bucket, Key=key)
            metadata = response.get('ResponseMetadata', {}) if isinstance(response, dict) else {}
            if type(metadata.get('HTTPStatusCode')) is not int or metadata['HTTPStatusCode'] != 204 or type(metadata.get('RetryAttempts')) is not int or metadata['RetryAttempts'] != 0:
                raise StorageFailure('Storage delete acknowledgement is unknown')
            # A versioned-store DELETE can create a marker while retaining the
            # bytes. This narrow R2 port has no version-removal contract.
            if 'DeleteMarker' in response or 'VersionId' in response:
                raise StorageFailure('Versioned storage cleanup is unsupported')
        except Exception: raise StorageFailure('Object cleanup failed') from None

    def _single_attempt(self):
        try:
            retries = self.client.meta.config.retries
            if type(retries.get('total_max_attempts')) is not int or retries['total_max_attempts'] != 1:
                raise StorageFailure('Storage wire retries must be disabled')
        except Exception:
            raise StorageFailure('Storage wire retries must be disabled') from None

    @staticmethod
    def _expiration(url, ttl):
        try:
            date = parse_qs(urlsplit(url).query)['X-Amz-Date'][0]
            return datetime.strptime(date, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc) + timedelta(seconds=ttl)
        except Exception:
            raise StorageFailure('Storage signature expiration is unavailable') from None

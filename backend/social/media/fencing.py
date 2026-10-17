"""R2 payload retirement without an absence window.

The one-byte object is permanent. This proves conditional creates are fenced,
not that admitted requests have drained. Never DELETE these keys, including on
rollback. External policy must establish an unversioned, exclusive-writer bucket
without lifecycle removal before this port may be enabled.
"""
import hashlib
from pathlib import Path
import tempfile
from uuid import UUID

from .storage import ObjectSnapshot, StorageFailure

FENCE_BODY = b'\x00'
FENCE_SHA256 = hashlib.sha256(FENCE_BODY).hexdigest()
FENCE_MIME = 'application/octet-stream'
WRITE_PROTOCOL = 'conditional_create_v1'


def _status(response, code):
    metadata = response.get('ResponseMetadata') if type(response) is dict else None
    return (type(metadata) is dict and type(metadata.get('HTTPStatusCode')) is int
            and metadata['HTTPStatusCode'] == code
            and type(metadata.get('RetryAttempts')) is int and metadata['RetryAttempts'] == 0)


def _client_error(error, code, name):
    from botocore.exceptions import ClientError
    return (isinstance(error, ClientError) and _status(error.response, code)
            and error.response.get('Error', {}).get('Code') == name)


def replace_with_fence(storage, key, operation_id, maximum):
    """Bounded CAS/create, then read the exact marker. Ambiguity raises.

    A late browser/server create can win before the first marker creation; the
    next bounded CAS replaces that payload. After installation it cannot win.
    A lost response is *not* retried in this invocation. The durable operation's
    next explicit retry uses the same marker identity and re-verifies it.
    """
    from .storage import bounded
    bounded(maximum)
    if type(operation_id) is not UUID or not operation_id.int:
        raise StorageFailure('Invalid fence identity')
    storage._single_attempt()
    try:
        for _ in range(3):
            snapshot = None
            try:
                raw = storage.client.head_object(Bucket=storage.bucket, Key=key)
            except Exception as error:
                if not _client_error(error, 404, '404') and not _client_error(error, 404, 'NoSuchKey'):
                    raise StorageFailure('Fence observation unavailable') from None
            else:
                if not _status(raw, 200) or raw.get('VersionId') is not None or raw.get('DeleteMarker') is not None:
                    raise StorageFailure('Versioned or unconfirmed fencing is unsupported')
                size, etag, metadata = raw.get('ContentLength'), raw.get('ETag'), raw.get('Metadata')
                bounded(size, maximum)
                if type(etag) is not str or not etag or type(metadata) is not dict:
                    raise StorageFailure('Fence observation invalid')
                snapshot = ObjectSnapshot(size, etag, None, metadata.get('sha256'), raw.get('ContentType'))
                if metadata.get('media-fence') == operation_id.hex:
                    if snapshot != ObjectSnapshot(1, etag, None, FENCE_SHA256, FENCE_MIME):
                        raise StorageFailure('Fence identity invalid')
                    with tempfile.TemporaryDirectory(prefix='media-fence-') as directory:
                        path = Path(directory) / 'marker'
                        storage.download(key, snapshot, path, 1, strict_ack=True)
                        if path.read_bytes() != FENCE_BODY:
                            raise StorageFailure('Fence bytes invalid')
                    return snapshot
                if 'media-fence' in metadata:
                    # Another operation owns this key. Its ledger must be
                    # reconciled; never overwrite another permanent marker.
                    raise StorageFailure('Fence ownership changed')
            params = {'Bucket': storage.bucket, 'Key': key, 'Body': FENCE_BODY,
                      'ContentLength': 1, 'ContentType': FENCE_MIME,
                      'Metadata': {'sha256': FENCE_SHA256, 'media-fence': operation_id.hex}}
            params.update({'IfMatch': snapshot.etag} if snapshot else {'IfNoneMatch': '*'})
            try:
                response = storage.client.put_object(**params)
                if not _status(response, 200) or response.get('VersionId') is not None:
                    raise StorageFailure('Fence creation completion unknown')
            except Exception as error:
                if not _client_error(error, 412, 'PreconditionFailed'):
                    raise StorageFailure('Fence creation completion unknown') from None
        raise StorageFailure('Fence contention or readback requires retry')
    except StorageFailure:
        raise
    except Exception:
        raise StorageFailure('Fence operation unavailable') from None

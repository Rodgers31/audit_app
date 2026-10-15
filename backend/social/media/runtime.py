"""Lazy optional runtime; absence never silently substitutes fake storage."""
from dataclasses import dataclass, field
from functools import lru_cache

from .config import MediaConfig, config_from_environment
from .inspection import LocalInspector
from .storage import MediaStorage, R2Storage
from .reconciliation import UnsupportedWriteQuiescenceVerifier, WriteQuiescenceVerifier


@dataclass(frozen=True)
class MediaRuntime:
    config: MediaConfig
    storage: MediaStorage | None
    inspector: LocalInspector | None
    unavailable_reason: str | None = None
    write_quiescence_verifier: WriteQuiescenceVerifier = field(default_factory=UnsupportedWriteQuiescenceVerifier)

    def available_mimes(self):
        if not self.config.enabled or self.storage is None or self.inspector is None:
            return ()
        return self.inspector.available_mimes()


def build_media_runtime(config):
    client = None
    transferred = False
    try:
        config.validate()
        if not config.enabled:
            return MediaRuntime(config, None, None, 'Media storage has not been enabled.')
        import boto3
        from botocore.config import Config
        client = boto3.client('s3', endpoint_url=config.endpoint, region_name='auto', aws_access_key_id=config.access_key, aws_secret_access_key=config.secret_key, config=Config(signature_version='s3v4', s3={'addressing_style': 'path'}, connect_timeout=5, read_timeout=10, retries={'total_max_attempts': 1, 'mode': 'standard'}))
        storage = R2Storage(client, config.bucket, config.endpoint)
        # No network request; reject SDK signing that drops the length/create guard.
        storage.authorize_upload('capability/probe', 1, 'image/png', config.upload_ttl)
        inspector = LocalInspector(config)
        if not inspector.available_mimes():
            return MediaRuntime(config, None, None, 'Required media inspectors are unavailable.')
        transferred = True
        return MediaRuntime(config, storage, inspector)
    except Exception:
        return MediaRuntime(MediaConfig(), None, None, 'Media storage or inspection configuration is unavailable.')
    finally:
        if client is not None and not transferred:
            try:
                client.close()
            except Exception:
                # This path already returns an unavailable runtime. Never turn
                # an SDK cleanup error into secret-bearing startup output.
                pass


@lru_cache(maxsize=1)
def media_runtime():
    try:
        config = config_from_environment()
    except Exception:
        return MediaRuntime(MediaConfig(), None, None, 'Media storage or inspection configuration is unavailable.')
    return build_media_runtime(config)


def request_media_runtime(request):
    """HTTP never constructs or borrows a process-global SDK client."""
    runtime = getattr(request.app.state, 'social_media_runtime', None)
    if runtime is None:
        return MediaRuntime(MediaConfig(), None, None, 'Media storage has not been enabled.')
    if not isinstance(runtime, MediaRuntime):
        from ..service import SocialError
        raise SocialError('MEDIA_STORAGE_UNAVAILABLE', 'The application media runtime is unavailable.', 503)
    return runtime

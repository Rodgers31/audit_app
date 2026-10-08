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


@lru_cache(maxsize=1)
def media_runtime():
    try:
        config = config_from_environment()
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
        return MediaRuntime(config, storage, inspector)
    except Exception:
        return MediaRuntime(MediaConfig(), None, None, 'Media storage or inspection configuration is unavailable.')

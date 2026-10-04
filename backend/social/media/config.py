"""Explicit runtime configuration. Never reads .env or provisions storage."""
from dataclasses import dataclass, field
import os
import re
from urllib.parse import urlsplit


@dataclass(frozen=True)
class MediaConfig:
    enabled: bool = False
    endpoint: str = ''
    bucket: str = ''
    access_key: str = field(default='', repr=False)
    secret_key: str = field(default='', repr=False)
    max_image_bytes: int = 10 * 1024 * 1024
    max_video_bytes: int = 50 * 1024 * 1024
    actor_quota_bytes: int = 200 * 1024 * 1024
    total_quota_bytes: int = 2 * 1024 * 1024 * 1024
    max_pending: int = 3
    upload_ttl: int = 300
    inspection_timeout: int = 20
    lease_seconds: int = 120
    preview_ttl: int = 120
    orphan_hours: int = 24
    ready_retention_days: int = 30
    ffprobe_path: str | None = ''

    def validate(self):
        if type(self.enabled) is not bool:
            raise ValueError('Media feature flag must be boolean')
        if self.ffprobe_path is not None and not isinstance(self.ffprobe_path, str):
            raise ValueError('Media inspection executable path must be a string or unset')
        for name, maximum in [('max_image_bytes', 10 * 1024 * 1024), ('max_video_bytes', 50 * 1024 * 1024), ('actor_quota_bytes', 1024 ** 3), ('total_quota_bytes', 10 * 1024 ** 3), ('max_pending', 10), ('upload_ttl', 600), ('inspection_timeout', 30), ('lease_seconds', 300), ('preview_ttl', 300), ('orphan_hours', 168), ('ready_retention_days', 90)]:
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError('Invalid media limit: ' + name)
        if self.actor_quota_bytes > self.total_quota_bytes or self.lease_seconds <= self.inspection_timeout + 30:
            raise ValueError('Invalid media budget or inspection lease')
        if not self.enabled:
            return self
        parsed = urlsplit(self.endpoint)
        if parsed.scheme != 'https' or not re.fullmatch(r'[a-f0-9]{32}\.r2\.cloudflarestorage\.com', parsed.hostname or '') or parsed.username or parsed.password or parsed.port not in {None, 443} or parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
            raise ValueError('Use the private R2 S3 API endpoint')
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', self.bucket) or not self.access_key or not self.secret_key:
            raise ValueError('Private media bucket and credentials are required')
        return self


def config_from_environment(environ=None):
    values = os.environ if environ is None else environ
    # Missing or invalid enablement never implicitly enables upload.
    enabled = values.get('SOCIAL_MEDIA_ENABLED', 'false').lower()
    if enabled not in {'true', 'false'}:
        raise ValueError('Invalid media enablement')
    return MediaConfig(enabled=enabled == 'true', endpoint=values.get('SOCIAL_MEDIA_R2_ENDPOINT', ''), bucket=values.get('SOCIAL_MEDIA_BUCKET', ''), access_key=values.get('SOCIAL_MEDIA_ACCESS_KEY', ''), secret_key=values.get('SOCIAL_MEDIA_SECRET_KEY', ''), ffprobe_path=values.get('SOCIAL_MEDIA_FFPROBE_PATH', '')).validate()

"""Explicit native read admission, independent of HTTP upload issuance."""
from ..media.config import MediaConfig


def read_config(values):
    flag = values.get('SOCIAL_WORKER_MEDIA_READS_ENABLED', 'false')
    if flag not in ('true', 'false'):
        raise ValueError('Invalid worker media read enablement')
    # Read admission validates the same endpoint, credentials and inspection
    # constraints. It never changes the HTTP runtime or its upload flag.
    return MediaConfig(enabled=flag == 'true',
        endpoint=values.get('SOCIAL_MEDIA_R2_ENDPOINT', ''),
        bucket=values.get('SOCIAL_MEDIA_BUCKET', ''),
        access_key=values.get('SOCIAL_MEDIA_ACCESS_KEY', ''),
        secret_key=values.get('SOCIAL_MEDIA_SECRET_KEY', ''),
        ffprobe_path=values.get('SOCIAL_MEDIA_FFPROBE_PATH', '')).validate()


class ReadStorage:
    """Narrow material port; no upload, finalization, deletion or SDK handle."""
    __slots__ = ('__storage', 'bucket', 'origin')
    provider = 'r2'

    def __init__(self, storage):
        self.__storage = storage
        self.bucket, self.origin = storage.bucket, storage.origin

    def head(self, key):
        return self.__storage.head(key)

    def download(self, key, snapshot, path, maximum):
        return self.__storage.download(key, snapshot, path, maximum)

    def preview(self, key, snapshot, ttl):
        return self.__storage.preview(key, snapshot, ttl)

"""No runtime is configured implicitly; no network/media URLs are accepted."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat

from ..service import SocialError

MAX_BYTES = 50 * 1024 * 1024
TIMEOUT = 120


@dataclass(frozen=True)
class StudioRuntime:
    enabled: bool = False
    root: Path | None = None
    ffmpeg: str = ''
    ffprobe: str = ''

    def validate(self):
        if type(self.enabled) is not bool:
            raise ValueError('Studio enablement must be boolean')
        if not self.enabled:
            return self
        if not isinstance(self.root, Path) or not self.root.is_absolute():
            raise ValueError('A private absolute render directory is required')
        try:
            resolved = self.root.resolve(strict=True)
            info = self.root.lstat()
        except OSError:
            raise ValueError('Private local render directory is unavailable') from None
        if resolved != self.root or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Render directory must be owned, private and free of symlinks')
        for executable in (self.ffmpeg, self.ffprobe):
            path = Path(executable)
            if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
                raise ValueError('Local FFmpeg and ffprobe are required')
        return self

    def require(self):
        self.validate()
        if not self.enabled:
            raise SocialError('RENDER_UNAVAILABLE', 'Local rendering has not been enabled.', 503)
        return self

    def directory(self, job_id):
        self.require()
        from uuid import UUID
        directory = self.root / str(UUID(str(job_id)))
        if directory.exists() and (directory.is_symlink() or directory.resolve() != directory):
            raise SocialError('RENDER_INTEGRITY', 'The local derivative path is unsafe.', 409)
        return directory

    def fingerprint(self):
        import PIL
        digest = hashlib.sha256(PIL.__version__.encode())
        for path in (Path(__file__), Path(__file__).with_name('render_child.py'), Path(self.ffmpeg), Path(self.ffprobe)):
            with path.open('rb') as source:
                for chunk in iter(lambda: source.read(256 * 1024), b''):
                    digest.update(chunk)
        return digest.hexdigest()


def request_runtime(request):
    runtime = getattr(request.app.state, 'social_studio_runtime', StudioRuntime())
    if not isinstance(runtime, StudioRuntime):
        raise SocialError('RENDER_UNAVAILABLE', 'Local rendering configuration is unavailable.', 503)
    return runtime.validate()


def configure_studio(app, environ=None):
    values = os.environ if environ is None else environ
    enabled = values.get('SOCIAL_STUDIO_ENABLED', 'false')
    if enabled not in {'true', 'false'}:
        raise ValueError('Invalid studio enablement')
    runtime = StudioRuntime() if enabled == 'false' else StudioRuntime(True, Path(values['SOCIAL_STUDIO_ROOT']), values['SOCIAL_STUDIO_FFMPEG'], values['SOCIAL_STUDIO_FFPROBE'])
    app.state.social_studio_runtime = runtime.validate()


def verified_bytes(runtime, job, *, graphic=False):
    """Read and hash one private regular file; return the exact verified bytes."""
    name = 'card-0.png' if graphic else ('output.mp4' if job.composition['kind'] == 'video' else 'card-0.png')
    path = runtime.directory(job.id) / name
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
                raise ValueError('Invalid derivative')
            data = source.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES or not graphic and hashlib.sha256(data).hexdigest() != job.sha256:
            raise ValueError('Changed derivative')
    except (OSError, ValueError):
        raise SocialError('RENDER_INTEGRITY', 'The derivative is missing or differs from its inspected checksum.', 409) from None
    return data

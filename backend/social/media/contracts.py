from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator

from ..contracts import Hash, PositiveVersion, StrictModel

Mime = Literal['image/jpeg', 'image/png', 'video/mp4']
Alt = Union[Annotated[str, StringConstraints(strict=True, max_length=2000)], None]


class UploadIntent(StrictModel):
    filename: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)]
    declared_mime_type: Mime
    declared_size: Annotated[int, Field(strict=True, gt=0, le=50 * 1024 * 1024)]
    alt_text: Alt = None

    @field_validator('filename')
    @classmethod
    def filename_only(cls, value):
        if not value.strip() or '/' in value or '\\' in value or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('Use a filename without paths or control characters')
        return value


class CompleteUpload(StrictModel):
    expected_version: PositiveVersion


class MediaAssetDTO(StrictModel):
    id: UUID
    version: PositiveVersion
    filename: str
    state: Literal['pending', 'inspecting', 'ready', 'failed', 'archived']
    mime_type: Union[Mime, None]
    byte_size: Union[int, None]
    sha256: Union[Hash, None]
    width: Union[int, None]
    height: Union[int, None]
    duration_ms: Union[int, None]
    default_alt_text: Alt
    safe_error: Union[str, None]
    created_at: datetime


class UploadAuthorization(StrictModel):
    asset: MediaAssetDTO
    method: Literal['PUT']
    url: str
    headers: dict[str, str]
    expires_at: datetime


class MediaLibrary(StrictModel):
    assets: tuple[MediaAssetDTO, ...]
    total: int
    page: int
    page_size: int
    has_more: bool


class MediaPreview(StrictModel):
    asset: MediaAssetDTO
    url: str
    expires_at: datetime


class ArchiveMedia(StrictModel):
    expected_version: PositiveVersion
    reason: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=500)]

    @field_validator('reason')
    @classmethod
    def reason_required(cls, value):
        if not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('A plain-text archive reason is required')
        return value.strip()


class MediaReference(StrictModel):
    post_id: UUID
    revision_id: UUID
    revision_no: PositiveVersion
    title: str


class MediaUsage(StrictModel):
    asset: MediaAssetDTO
    references: tuple[MediaReference, ...]
    total: Annotated[int, Field(strict=True, ge=0)]
    page: PositiveVersion
    page_size: Annotated[int, Field(strict=True, ge=1, le=50)]
    has_more: bool
    archive_eligible: bool
    archive_reason: str


class MediaCapabilities(StrictModel):
    upload_available: bool
    library_available: bool
    allowed_mime_types: tuple[Mime, ...]
    max_image_bytes: int
    max_video_bytes: int
    unavailable_reason: Union[str, None]


class MaintenanceBacklog(StrictModel):
    retained_fences: Annotated[int, Field(strict=True, ge=0)] = 0
    eligible_cleanup: Annotated[int, Field(strict=True, ge=0)]
    unknown_browser_writes: Annotated[int, Field(strict=True, ge=0)]
    unknown_finalizations: Annotated[int, Field(strict=True, ge=0)]
    active_leases: Annotated[int, Field(strict=True, ge=0)]
    protected_references: Annotated[int, Field(strict=True, ge=0)]
    reserved_bytes: Annotated[int, Field(strict=True, ge=0)]
    pending_uploads: Annotated[int, Field(strict=True, ge=0)]
    oldest_orphan_at: datetime | None


class MaintenanceResult(StrictModel):
    cleanup_enabled: bool
    cleaned: Annotated[int, Field(strict=True, ge=0, le=20)]
    backlog: MaintenanceBacklog

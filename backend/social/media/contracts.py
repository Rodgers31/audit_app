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
        if not value.strip() or '/' in value or '\\' in value or any(ord(c) < 32 for c in value):
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


class MediaCapabilities(StrictModel):
    upload_available: bool
    library_available: bool
    allowed_mime_types: tuple[Mime, ...]
    max_image_bytes: int
    max_video_bytes: int
    unavailable_reason: Union[str, None]

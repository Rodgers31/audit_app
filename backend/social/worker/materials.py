"""Ephemeral, server-only provider material; never persistent delivery data."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from ..contracts import InspectedAsset


@dataclass(frozen=True)
class WorkerCredentialMaterial:
    account_id: UUID
    credential_id: UUID
    credential_version: int
    platform: str
    api_product: str
    external_account_id: str
    page_id: str
    page_access_token: str = field(repr=False)
    granted_scopes: tuple[str, ...]
    access_expires_at: datetime | None
    data_access_expires_at: datetime | None


@dataclass(frozen=True)
class ProviderFetchURL:
    url: str = field(repr=False)
    expires_at: datetime
    asset_id: UUID
    sha256: str


class InspectedMediaAccess(Protocol):
    async def read_bytes(self, asset: InspectedAsset, maximum_bytes: int) -> bytes: ...
    async def provider_fetch_url(self, asset: InspectedAsset, minimum_ttl_seconds: int) -> ProviderFetchURL: ...

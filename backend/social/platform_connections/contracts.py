from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import StrictBool, StrictStr

from ..contracts import StrictModel, Reason
from ..connections.contracts import AccountDTO
from ..adapters.tiktok import TikTokCreatorSettings


class ConfirmCommand(StrictModel):
    external_account_id: StrictStr
    reason: Reason


class PlatformConnectionStatus(StrictModel):
    provider: Literal['threads', 'x', 'tiktok']
    available: StrictBool
    blockers: tuple[StrictStr, ...]
    scopes: tuple[StrictStr, ...]
    provider_api_version: StrictStr
    publishing_enabled: Literal[False] = False


class ConnectionChoice(StrictModel):
    flow_id: UUID
    external_account_id: StrictStr
    display_name: StrictStr
    handle: StrictStr | None
    granted_scopes: tuple[StrictStr, ...]
    expires_at: datetime


class ConnectedAccount(StrictModel):
    flow_id: UUID
    account: AccountDTO
    credential_id: UUID
    credential_version: int


class CredentialHealth(StrictModel):
    account_id: UUID
    platform: Literal['threads', 'x', 'tiktok']
    connection_state: StrictStr
    credential_id: UUID
    credential_version: int
    access_expires_at: datetime
    refresh_pending: StrictBool
    reconnect_required: StrictBool
    publishing_enabled: StrictBool


class CreatorSettingsResponse(StrictModel):
    account_id: UUID
    external_account_id: StrictStr
    display_name: StrictStr
    handle: StrictStr | None
    settings: TikTokCreatorSettings
    checked_at: datetime
    settings_hash: StrictStr
    credential_version: int

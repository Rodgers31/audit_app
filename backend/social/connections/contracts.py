"""Only short-lived authorization nonce/code crosses the browser boundary."""
from typing import Annotated, Literal
from datetime import datetime
from uuid import UUID
from pydantic import Field, StrictBool, StrictStr, StringConstraints
from ..contracts import StrictModel, PositiveVersion, Reason
from ..contracts import CapabilitySet, Platform

class AccountDTO(StrictModel):
    id: UUID
    platform: Platform
    display_name: StrictStr
    handle: StrictStr | None
    profile_url: StrictStr | None
    connection_state: StrictStr
    publishing_enabled: StrictBool
    capabilities: CapabilitySet

URL = Annotated[str, StringConstraints(strict=True, max_length=2048)]
Opaque = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=4096)]

class StartCommand(StrictModel):
    redirect_uri: URL
    reconnect_account_id: UUID | None = None
    reason: Reason

class CompleteCommand(StrictModel):
    code: Opaque
    state: Annotated[str, StringConstraints(strict=True, pattern=r'^[A-Za-z0-9_-]{43}$')]
    redirect_uri: URL

class SelectCommand(StrictModel):
    page_id: Annotated[str, StringConstraints(strict=True, pattern=r'^[0-9]{1,64}$')]
    instagram_id: Annotated[str, StringConstraints(strict=True, pattern=r'^[0-9]{1,64}$')] | None = None
    reason: Reason

class AccountCommand(StrictModel):
    expected_credential_id: UUID
    expected_credential_version: PositiveVersion
    reason: Reason

class ConnectionStatus(StrictModel):
    provider: Literal['meta'] = 'meta'
    available: StrictBool
    blockers: tuple[StrictStr, ...]
    access_mode: Literal['unverified','owned_standard','advanced']
    scopes: tuple[StrictStr, ...]
    publishing_adapter_available: Literal[False] = False

class StartedFlow(StrictModel):
    flow_id: UUID
    authorize_url: URL
    expires_at: datetime

class AssetChoice(StrictModel):
    page_id: StrictStr
    display_name: StrictStr
    tasks: tuple[StrictStr, ...]
    instagram_id: StrictStr | None
    instagram_name: StrictStr | None
    instagram_handle: StrictStr | None
    page_eligible: StrictBool
    instagram_eligible: StrictBool
    missing_page_scopes: tuple[StrictStr, ...]
    missing_instagram_scopes: tuple[StrictStr, ...]

class DiscoveredFlow(StrictModel):
    flow_id: UUID
    expires_at: datetime
    granted_scopes: tuple[StrictStr, ...]
    choices: tuple[AssetChoice, ...]

class SelectedAccounts(StrictModel):
    flow_id: UUID
    accounts: tuple[AccountDTO, ...]

class AccountHealth(StrictModel):
    account_id: UUID
    external_account_id: StrictStr
    api_product: StrictStr
    connection_method: Literal['facebook_login']
    connection_state: StrictStr
    credential_kind: Literal['facebook_page']
    credential_id: UUID
    credential_version: int
    key_version: StrictStr
    access_expires_at: datetime | None
    data_access_expires_at: datetime | None
    parent_access_expires_at: datetime | None
    parent_data_access_expires_at: datetime | None
    parent_grant_reconnect_required: StrictBool
    granted_scopes: tuple[StrictStr, ...]
    missing_scopes: tuple[StrictStr, ...]
    checked_at: datetime | None
    last_api_success_at: datetime | None
    reconnect_required: StrictBool
    publishing_enabled: StrictBool
    renewal_strategy: Literal['facebook_login_reconnect'] = 'facebook_login_reconnect'
    provider_revocation_confirmed: Literal[False] = False

"""Typed seam. Media owns storage authority, fencing and absence verification."""
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

@dataclass(frozen=True)
class PrivacyMediaDeletionCommand:
    operation_id: UUID
    authority_id: UUID
    asset_id: UUID
    plan_hash: str
    policy_hash: str

@dataclass(frozen=True)
class PrivacyMediaDeletionResult:
    operation_id: UUID
    asset_id: UUID
    state: Literal['verified_deleted', 'blocked', 'outcome_unknown']
    verified_deleted: bool = False

    def __post_init__(self):
        if (type(self.operation_id) is not UUID or type(self.asset_id) is not UUID
                or self.state not in ('verified_deleted', 'blocked', 'outcome_unknown')
                or type(self.verified_deleted) is not bool
                or self.verified_deleted != (self.state == 'verified_deleted')):
            raise ValueError('PRIVACY_MEDIA_RESULT_INVALID')

class PrivacyMediaDeletionPort(Protocol):
    def inspect_scope(self, asset_id: UUID) -> dict[str, str]: ...
    def execute(self, command: PrivacyMediaDeletionCommand) -> PrivacyMediaDeletionResult: ...
    def reconcile(self, command: PrivacyMediaDeletionCommand) -> PrivacyMediaDeletionResult: ...

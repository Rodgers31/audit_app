"""Bounded approval commands; receipts identify a request, never deletion permission."""
from dataclasses import dataclass
from typing import Literal
from uuid import UUID
from pydantic import Field, StrictInt, field_validator
from ..contracts import StrictModel


class PrivacyProposal(StrictModel):
    receipt_id: UUID
    policy_key: str = Field(min_length=1, max_length=128)
    policy_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    evidence: str = Field(min_length=10, max_length=2000)
    erase_credentials: tuple[UUID, ...] = Field(default=(), max_length=100)
    erase_flows: tuple[UUID, ...] = Field(default=(), max_length=100)
    media_assets: tuple[UUID, ...] = Field(default=(), max_length=100)

    @field_validator('erase_credentials', 'erase_flows', 'media_assets')
    @classmethod
    def unique_ids(cls, values):
        if len(set(values)) != len(values) or any(v.int == 0 for v in values):
            raise ValueError('Unique nonzero identities required')
        return values


class PrivacyApproval(StrictModel):
    plan_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    decision: Literal['approved', 'rejected']
    reason: str = Field(min_length=10, max_length=2000)


class PrivacyRun(StrictModel):
    expected_version: StrictInt = Field(gt=0)


@dataclass(frozen=True)
class PrivacyWorkflowConfig:
    enabled: bool = False
    execution_enabled: bool = False
    # Operator-installed policy digest and explicit eligible human approvers.
    # An HTTP request cannot add a policy or promote its own actor.
    policies: tuple[tuple[str, str], ...] = ()
    approvers: tuple[UUID, ...] = ()

    app_id: str = ''

    def validate(self):
        import re
        if (type(self.enabled) is not bool or type(self.execution_enabled) is not bool
                or (self.execution_enabled and not self.enabled)
                or type(self.policies) is not tuple or len(self.policies) > 32
                or any(type(p) is not tuple or len(p) != 2 or type(p[0]) is not str
                       or not 1 <= len(p[0]) <= 128 or type(p[1]) is not str
                       or re.fullmatch('[a-f0-9]{64}', p[1]) is None for p in self.policies)
                or len(dict(self.policies)) != len(self.policies)
                or type(self.approvers) is not tuple or len(self.approvers) > 100
                or any(type(a) is not UUID or a.int == 0 for a in self.approvers)
                or len(set(self.approvers)) != len(self.approvers)
                or type(self.app_id) is not str
                or (self.app_id != '' and re.fullmatch('[0-9]{1,64}', self.app_id) is None)
                or (self.enabled and (not self.policies or not self.approvers or not self.app_id))):
            raise ValueError('PRIVACY_WORKFLOW_CONFIGURATION_INVALID')

"""Explicit human operating acceptance and exact immutable authorization commands."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, StrictBool, StringConstraints, field_validator, model_validator
from ..contracts import StrictModel, PositiveVersion, Reason

Digest = Annotated[str, StringConstraints(strict=True, pattern=r'^[a-f0-9]{64}$')]


class OperatingEvidenceCommand(StrictModel):
    rule_id: UUID
    rule_version: PositiveVersion
    rule_hash: Digest
    shadow_decision_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=100)]
    evidence_url: Annotated[str, StringConstraints(strict=True, pattern=r'^https://', max_length=2000)]
    evidence_sha256: Digest
    accuracy_accepted: StrictBool
    reliability_accepted: StrictBool
    corrections_reviewed: StrictBool
    tiktok_unattended_product: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)] | None = None
    reason: Reason

    @model_validator(mode='after')
    def accepted(self):
        if not (self.accuracy_accepted and self.reliability_accepted and self.corrections_reviewed):
            raise ValueError('Human operating acceptance is required')
        if len(set(self.shadow_decision_ids)) != len(self.shadow_decision_ids):
            raise ValueError('Duplicate shadow decision')
        return self


class SnapshotCommand(StrictModel):
    operating_evidence_id: UUID
    rule_id: UUID
    rule_version: PositiveVersion
    rule_hash: Digest
    valid_until: datetime
    materiality_mode: Literal['numeric_change', 'new_reporting_release'] = 'numeric_change'
    minimum_absolute_change: Annotated[str, StringConstraints(strict=True, pattern=r'^(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,8})?$')] = '1'
    reason: Reason

    @field_validator('minimum_absolute_change')
    @classmethod
    def materiality(cls, value):
        if Decimal(value) <= 0:
            raise ValueError('Materiality must be a positive exact decimal in the approved fact scale')
        return value

    @field_validator('valid_until')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('An explicit timezone is required')
        return value


class PolicyControlsCommand(StrictModel):
    expected_version: PositiveVersion
    snapshot_id: UUID | None
    auto_approve_enabled: StrictBool
    auto_schedule_enabled: StrictBool
    auto_publish_enabled: StrictBool
    reason: Reason

    @model_validator(mode='after')
    def hierarchy(self):
        if self.auto_publish_enabled and not self.auto_schedule_enabled or self.auto_schedule_enabled and not self.auto_approve_enabled:
            raise ValueError('Publish requires schedule; schedule requires approval')
        if self.auto_approve_enabled and self.snapshot_id is None:
            raise ValueError('An authorized snapshot is required')
        return self


class AuthorizePolicyCommand(StrictModel):
    expected_version: PositiveVersion
    revision_id: UUID
    content_hash: Digest
    snapshot_id: UUID


class SchedulePolicyCommand(AuthorizePolicyCommand):
    publication_id: UUID
    expected_publication_version: PositiveVersion

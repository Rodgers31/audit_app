"""Versioned committed-evidence seam. No parser, network, or model-generated facts."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, StrictBool, StringConstraints, field_validator, model_validator
from ..contracts import StrictModel, Reference, DocumentTarget, Reason, PositiveVersion

Text = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=300)]
Key = Annotated[str, StringConstraints(strict=True, pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.:/-]{0,199}$')]


class FactEvidence(StrictModel):
    fact_id: Key
    entity: Text
    metric: Text
    period: Text
    comparison_basis: Text
    value: Annotated[str, StringConstraints(strict=True, pattern=r'^-?(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,8})?$')]
    unit: Text
    scale: Literal['units', 'thousands', 'millions', 'billions']
    classification: Literal['actual', 'modelled', 'projected']
    source_document_id: Annotated[int, Field(strict=True, gt=0)]
    document_url: str
    locator: Text
    document_checksum: Annotated[str, StringConstraints(strict=True, pattern=r'^(?:[a-f0-9]{32}|[a-f0-9]{64})$')]
    publisher: Text
    published_on: date
    retrieved_at: datetime
    verified_at: datetime
    canonical_url: str

    @field_validator('document_url', 'canonical_url')
    @classmethod
    def urls(cls, value):
        return Reference(url=value).url

    @field_validator('canonical_url')
    @classmethod
    def canonical(cls, value):
        if urlsplit(value).netloc != 'www.auditgava.com':
            raise ValueError('Canonical URL must use www.auditgava.com')
        return value

    @field_validator('retrieved_at', 'verified_at')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Evidence timestamps require an offset')
        return value

    @model_validator(mode='after')
    def chronology(self):
        if self.published_on > self.retrieved_at.date() or self.verified_at < self.retrieved_at:
            raise ValueError('Invalid evidence chronology')
        Decimal(self.value)  # bounded exact decimal syntax above; never a float
        return self


class SourceObservation(StrictModel):
    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    source_type: Literal['treasury', 'cob', 'oag', 'knbs', 'cra']
    source_key: Key
    evidence_version: PositiveVersion
    ingestion_id: Key
    category: Literal['dataset_availability', 'new_report', 'debt_update', 'budget_update', 'audit_finding', 'correction']
    title: Text
    committed: StrictBool
    fixture: StrictBool
    quarantined: StrictBool
    publishable: StrictBool
    correction_pending: StrictBool = False
    facts: Annotated[tuple[FactEvidence, ...], Field(min_length=1, max_length=10)]

    @model_validator(mode='after')
    def identities(self):
        if len({f.fact_id for f in self.facts}) != len(self.facts):
            raise ValueError('Duplicate fact identifiers')
        return self


class GenerationControlsCommand(StrictModel):
    expected_version: PositiveVersion
    drafts_enabled: StrictBool
    shadow_enabled: StrictBool
    source_allowlist: Annotated[tuple[Literal['treasury', 'cob', 'oag', 'knbs', 'cra'], ...], Field(max_length=5)]
    targets: Annotated[tuple[DocumentTarget, ...], Field(max_length=25)] = ()
    reason: Reason

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.source_allowlist)) != len(self.source_allowlist) or len({t.account_id for t in self.targets}) != len(self.targets):
            raise ValueError('Duplicate allowlist entry')
        return self


class DetectCommand(StrictModel):
    record_ids: Annotated[tuple[Annotated[int, Field(strict=True, gt=0)], ...], Field(min_length=1, max_length=25)]
    ingestion_id: Annotated[int, Field(strict=True, gt=0)]
    backfill: StrictBool = False
    reason: Reason


class RuleCommand(StrictModel):
    expected_version: Annotated[int, Field(strict=True, ge=0)]
    name: Text
    mode: Literal['disabled', 'shadow'] = 'disabled'
    categories: Annotated[tuple[Literal['dataset_availability', 'new_report'], ...], Field(min_length=1, max_length=2)]
    source_allowlist: Annotated[tuple[Literal['treasury', 'cob', 'oag', 'knbs', 'cra'], ...], Field(min_length=1, max_length=5)]
    account_allowlist: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=25)]
    max_per_day: Annotated[int, Field(strict=True, ge=1, le=3)] = 3
    min_interval_minutes: Annotated[int, Field(strict=True, ge=60, le=1440)] = 60
    freshness_hours: Annotated[int, Field(strict=True, ge=1, le=168)] = 24
    reason: Reason

    @model_validator(mode='after')
    def unique(self):
        for values in (self.categories, self.source_allowlist, self.account_allowlist):
            if len(values) != len(set(values)):
                raise ValueError('Allowlist entries must be unique')
        return self


class EvaluateCommand(StrictModel):
    expected_version: PositiveVersion
    revision_id: UUID
    rule_id: UUID
    rule_version: PositiveVersion

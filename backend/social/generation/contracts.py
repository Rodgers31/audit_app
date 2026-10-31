"""Versioned committed-evidence seam. No parser, network, or model-generated facts."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, StrictBool, StringConstraints, field_validator, model_validator, model_serializer
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


class ReportEvidence(StrictModel):
    """A retained publisher report and verified scope, without a monetary claim."""
    entity_id: Annotated[int, Field(strict=True, gt=0, le=2147483647)]
    source_record_id: Annotated[int, Field(strict=True, gt=0, le=2147483647)]
    authority_fingerprint: Annotated[str, StringConstraints(strict=True, pattern=r'^[a-f0-9]{64}$')]
    entity: Text
    period: Text
    period_start: date
    period_end: date
    source_document_id: Annotated[int, Field(strict=True, gt=0, le=2147483647)]
    document_url: str
    document_checksum: Annotated[str, StringConstraints(strict=True, pattern=r'^[a-f0-9]{64}$')]
    publisher: Text
    published_on: date
    retrieved_at: datetime
    verified_at: datetime
    canonical_url: str
    locator: Text
    publication_extraction_id: Annotated[int, Field(strict=True, gt=0, le=2147483647)]
    qualification_extraction_id: Annotated[int, Field(strict=True, gt=0, le=2147483647)]

    @field_validator('document_url', 'canonical_url')
    @classmethod
    def urls(cls, value):
        return FactEvidence.urls(value)

    @field_validator('retrieved_at', 'verified_at')
    @classmethod
    def aware(cls, value):
        return FactEvidence.aware(value)

    @model_validator(mode='after')
    def bound(self):
        if self.canonical_url != f'https://www.auditgava.com/counties/{self.entity_id}':
            raise ValueError('Report scope requires the exact canonical county destination')
        url = urlsplit(self.document_url)
        if url.hostname not in {'cob.go.ke', 'www.cob.go.ke'} or url.username or url.password or url.port not in (None, 443):
            raise ValueError('Official CoB report URL required')
        if self.period_start > self.period_end or self.published_on > self.retrieved_at.date() or self.verified_at < self.retrieved_at:
            raise ValueError('Invalid report chronology')
        return self


class NativeReportEvidence(ReportEvidence):
    native_domain: Literal['national_budget', 'revenue_by_source', 'audits', 'pending_bills']
    scope_key: Key

    @model_validator(mode='after')
    def bound(self):
        from importlib import import_module
        module = import_module('backend.seeding.native_report_authority' if __package__.startswith('backend.') else 'seeding.native_report_authority')
        if (not module.official_url(self.document_url, self.native_domain)
                or self.publisher != module.DOMAINS[self.native_domain][2]
                or self.canonical_url != 'https://www.auditgava.com'+module.DOMAINS[self.native_domain][3]
                or self.period_start > self.period_end or self.period_end > self.published_on or self.published_on > self.retrieved_at.date()
                or self.verified_at < self.retrieved_at):
            raise ValueError('Exact native report scope and chronology required')
        return self


class CataloguedNativeReportEvidence(NativeReportEvidence):
    """KRA availability with a catalogue day; no claim of report publication day."""
    native_domain: Literal['revenue_by_source']
    published_on: None
    evidence_kind: Literal['publisher_catalogue']
    catalogued_on: date
    catalogue_url: str

    @model_validator(mode='after')
    def bound(self):
        from importlib import import_module
        module = import_module('backend.seeding.kra_report_catalogue' if __package__.startswith('backend.') else 'seeding.kra_report_catalogue')
        period, start, end = module.annual_scope(self.document_url, self.period)
        if (self.catalogue_url != module.CATALOGUE_URL or self.publisher != 'Kenya Revenue Authority'
                or self.canonical_url != 'https://www.auditgava.com/budget'
                or self.entity != 'Kenya annual revenue performance' or self.scope_key != 'annual-revenue'
                or self.period_start.isoformat() != start or self.period_end.isoformat() != end
                or not self.period_end <= self.catalogued_on <= self.retrieved_at.date()
                or self.verified_at < self.retrieved_at):
            raise ValueError('Exact catalogue availability scope and chronology required')
        return self


class OagCataloguedReportEvidence(CataloguedNativeReportEvidence):
    """A combined volume's dated OAG entry, with no PDF publication claim."""
    native_domain: Literal['audits']
    institution: Literal['executives', 'assemblies']

    @model_validator(mode='after')
    def bound(self):
        from importlib import import_module
        module = import_module('backend.seeding.oag_report_catalogue' if __package__.startswith('backend.') else 'seeding.oag_report_catalogue')
        authority = import_module('backend.seeding.native_report_authority' if __package__.startswith('backend.') else 'seeding.native_report_authority')
        scope = module.scope_fields(self.period, self.institution)
        if (self.catalogue_url != module.catalogue_url(self.period)
                or not authority.official_url(self.document_url, 'audits')
                or self.publisher != authority.DOMAINS['audits'][2]
                or self.canonical_url != 'https://www.auditgava.com/audits'
                or self.entity != scope['entity'] or self.scope_key != scope['scope_key']
                or self.period_start.isoformat() != scope['start'] or self.period_end.isoformat() != scope['end']
                or not self.period_end <= self.catalogued_on <= self.retrieved_at.date()
                or self.verified_at < self.retrieved_at):
            raise ValueError('Exact OAG combined catalogue scope and chronology required')
        return self


class NativeFinancialEvidence(StrictModel):
    native_domain: Literal['national_budget', 'revenue_by_source', 'pending_bills']
    record_id: Annotated[int, Field(strict=True, gt=0, le=2147483647)]
    report_record_id: Annotated[int, Field(strict=True, gt=0, le=2147483647)]
    authority_fingerprint: Annotated[str, StringConstraints(strict=True, pattern=r'^[a-f0-9]{64}$')]
    period_start: date
    period_end: date
    published_on: date

    @model_validator(mode='after')
    def chronology(self):
        if self.period_start > self.period_end or self.period_end > self.published_on:
            raise ValueError('Completed financial reporting scope required')
        return self


class SourceObservation(StrictModel):
    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    source_type: Literal['treasury', 'cob', 'oag', 'knbs', 'cra', 'kra']
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
    facts: Annotated[tuple[FactEvidence, ...], Field(max_length=10)] = ()
    report: OagCataloguedReportEvidence | CataloguedNativeReportEvidence | NativeReportEvidence | ReportEvidence | None = None
    financial: NativeFinancialEvidence | None = None

    @model_serializer(mode='wrap')
    def preserve_legacy_evidence(self, handler):
        value = handler(self)
        if self.financial is None:
            value.pop('financial', None)
        return value

    @model_validator(mode='after')
    def identities(self):
        if self.financial is not None and self.report is not None:
            raise ValueError('Financial and neutral report observations are distinct')
        if self.report is not None:
            if isinstance(self.report, NativeReportEvidence):
                sources = {'national_budget':'cob', 'revenue_by_source':'kra', 'audits':'oag','pending_bills':'cob'}
                source = sources[self.report.native_domain]
                expected = f'{source}:native:{self.report.native_domain}:{self.report.entity_id}:{self.report.scope_key}'
            else:
                source, expected = 'cob', f'cob:county:{self.report.entity_id}:reports'
            if self.facts or self.category != 'dataset_availability' or self.source_type != source or self.source_key != expected:
                raise ValueError('Neutral report evidence requires its distinct report series and no financial facts')
        elif not self.facts:
            raise ValueError('Financial observations require at least one exact fact')
        if len({f.fact_id for f in self.facts}) != len(self.facts):
            raise ValueError('Duplicate fact identifiers')
        return self


class GenerationControlsCommand(StrictModel):
    expected_version: PositiveVersion
    drafts_enabled: StrictBool
    shadow_enabled: StrictBool
    source_allowlist: Annotated[tuple[Literal['treasury', 'cob', 'oag', 'knbs', 'cra', 'kra'], ...], Field(max_length=6)]
    targets: Annotated[tuple[DocumentTarget, ...], Field(max_length=25)] = ()
    reason: Reason

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.source_allowlist)) != len(self.source_allowlist) or len({t.account_id for t in self.targets}) != len(self.targets):
            raise ValueError('Duplicate allowlist entry')
        return self


class PreviewCommand(StrictModel):
    domain: Annotated[str, StringConstraints(strict=True, pattern=r'^[a-z_]{1,100}$')]
    record_ids: Annotated[tuple[Annotated[int, Field(strict=True, gt=0, le=2147483647)], ...], Field(min_length=1, max_length=25)]
    ingestion_id: Annotated[int, Field(strict=True, gt=0, le=2147483647)]
    reports: StrictBool = True
    backfill: StrictBool = False

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.record_ids)) != len(self.record_ids):
            raise ValueError('Unique record IDs required')
        return self


class DetectCommand(StrictModel):
    domain: Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z_]{1,100}$")] = "counties_budget"
    record_ids: Annotated[tuple[Annotated[int, Field(strict=True, gt=0, le=2147483647)], ...], Field(min_length=1, max_length=25)]
    ingestion_id: Annotated[int, Field(strict=True, gt=0, le=2147483647)]
    backfill: StrictBool = False
    reason: Reason


class RuleCommand(StrictModel):
    expected_version: Annotated[int, Field(strict=True, ge=0)]
    name: Text
    mode: Literal['disabled', 'shadow'] = 'disabled'
    categories: Annotated[tuple[Literal['dataset_availability', 'new_report'], ...], Field(min_length=1, max_length=2)]
    source_allowlist: Annotated[tuple[Literal['treasury', 'cob', 'oag', 'knbs', 'cra', 'kra'], ...], Field(min_length=1, max_length=6)]
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


class PrepareDraftCommand(StrictModel):
    expected_version: PositiveVersion
    revision_id: UUID
    reason: Reason

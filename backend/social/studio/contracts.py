from datetime import datetime
from typing import Annotated, Literal, Protocol
from uuid import UUID
import re

from pydantic import Field, StringConstraints, field_validator, model_validator

from ..contracts import Hash, Platform, ReviewAttestation, StrictModel

# A deliberately small card composition contract, not an executable template language.
Text = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=180, pattern=r'^[\x20-\x7e]+$')]
Identifier = Annotated[str, StringConstraints(strict=True, pattern=r'^[a-zA-Z0-9_.:-]{1,80}$')]
TEMPLATES = ('debt_update', 'audit_finding', 'budget_update', 'new_report', 'did_you_know', 'educational')
TEMPLATE_DEFINITIONS = {
    'debt_update': {'required_facts': ('metric', 'period', 'value'), 'default_formats': ('image', 'reel'), 'layout': 'source-cards-v1'},
    'audit_finding': {'required_facts': ('entity', 'finding', 'period'), 'default_formats': ('image', 'video'), 'layout': 'source-cards-v1'},
    'budget_update': {'required_facts': ('entity', 'period', 'value'), 'default_formats': ('image', 'reel'), 'layout': 'source-cards-v1'},
    'new_report': {'required_facts': ('report', 'publisher', 'publication_date'), 'default_formats': ('image', 'video'), 'layout': 'source-cards-v1'},
    'did_you_know': {'required_facts': ('fact', 'context'), 'default_formats': ('image', 'reel'), 'layout': 'source-cards-v1'},
    'educational': {'required_facts': ('term', 'definition'), 'default_formats': ('image', 'video'), 'layout': 'source-cards-v1'},
}


class Fact(StrictModel):
    id: Identifier
    text: Text
    source_url: Annotated[str, StringConstraints(strict=True, max_length=2048)]


class Scene(StrictModel):
    fact_id: Identifier
    seconds: Annotated[int, Field(strict=True, ge=3, le=15)]


class Composition(StrictModel):
    schema_version: Literal[1] = 1
    template: Literal['debt_update', 'audit_finding', 'budget_update', 'new_report', 'did_you_know', 'educational']
    template_version: Literal[1] = 1
    kind: Literal['graphic', 'video']
    revision_id: UUID
    title: Annotated[Text, Field(max_length=70)]
    facts: Annotated[tuple[Fact, ...], Field(min_length=1, max_length=6)]
    scenes: Annotated[tuple[Scene, ...], Field(min_length=1, max_length=6)]

    @field_validator('schema_version', 'template_version', mode='before')
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('Use integer template/schema version 1')
        return value

    @model_validator(mode='after')
    def complete(self):
        ids = [f.id for f in self.facts]
        if len(set(ids)) != len(ids) or any(s.fact_id not in ids for s in self.scenes):
            raise ValueError('Every scene must bind a unique supplied fact set')
        if set(ids) != set(TEMPLATE_DEFINITIONS[self.template]['required_facts']):
            raise ValueError('Supply the required factual roles for this template version')
        if self.kind == 'video' and set(ids) != {s.fact_id for s in self.scenes}:
            raise ValueError('Video scenes must cover every required fact')
        if any(re.search(r'\{|\}|\[[a-zA-Z_][^]]*\]|<[^>]+>', value) for value in [self.title, *(f.text for f in self.facts)]):
            raise ValueError('Resolve every template placeholder before rendering')
        if self.kind == 'video' and not 15 <= sum(s.seconds for s in self.scenes) <= 45:
            raise ValueError('Video duration must be 15–45 seconds')
        if self.kind == 'graphic' and len(self.scenes) != 1:
            raise ValueError('Graphics have exactly one scene')
        return self


class Approval(StrictModel):
    expected_version: Annotated[int, Field(strict=True, gt=0)]
    sha256: Hash
    review_attestation: ReviewAttestation

    @model_validator(mode='after')
    def reviewed(self):
        if not self.review_attestation.facts_checked or not self.review_attestation.sources_checked:
            raise ValueError('Fact and source review are required')
        return self


class Metric(StrictModel):
    name: Identifier
    api_version: Identifier
    unit: Identifier
    period: Identifier
    window_start: datetime
    window_end: datetime
    collected_at: datetime
    available_until: datetime
    status: Literal['available', 'unavailable']
    value: Annotated[int, Field(strict=True, ge=0, le=2**53-1)] | None
    reason: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=200)] | None

    @model_validator(mode='after')
    def semantics(self):
        if not self.window_start < self.window_end <= self.collected_at < self.available_until:
            raise ValueError('Invalid provider observation window or freshness')
        if (self.status == 'available') != (self.value is not None) or (self.status == 'unavailable') != (self.reason is not None):
            raise ValueError('Unavailable observations require a reason and null value')
        if (self.available_until - self.collected_at).total_seconds() > 86400:
            raise ValueError('Freshness cannot exceed one day')
        return self


class MetricRequest(StrictModel):
    platform: Platform
    account_id: UUID
    target_id: UUID
    remote_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=512)]
    deadline: datetime
    max_records: Literal[20] = 20
    max_response_bytes: Literal[32768] = 32768


class MetricsPort(Protocol):
    """Platform-owned transport must obey deadline/byte cap and perform no writes.

    Only explicitly installed zero-cost, authorized read adapters are admissible.
    No platform implementation is implicitly imported from another lane.
    """
    platform: Platform
    zero_cost: bool

    def collect(self, request: MetricRequest) -> tuple[Metric, ...]: ...

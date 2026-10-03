"""Version-one, bounded, immutable social documents and adapter contracts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Union
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, StringConstraints, field_validator, model_serializer

Platform = Literal["facebook", "instagram", "threads", "x", "tiktok"]
PostFormat = Literal["text", "image", "carousel", "video", "reel"]
EditorialState = Literal["draft", "pending_review", "approved", "rejected", "archived"]
TargetState = Literal["ready", "queued", "claimed", "dispatching", "processing", "retry_wait", "reconciling", "blocked", "published", "failed", "outcome_unknown", "cancelled"]
FeatureState = Literal["supported", "restricted", "requires_review", "paid", "unsupported", "unverified"]
PositiveVersion = Annotated[int, Field(strict=True, gt=0)]
BoundedText = Annotated[str, StringConstraints(strict=True, max_length=20000)]
Reason = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=1000)]
Hash = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @field_validator("*", mode="after")
    @classmethod
    def strict_time_and_json(cls, value):
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Timestamps must include a timezone")
            return value.astimezone(timezone.utc)
        if isinstance(value, dict):
            try:
                canonical_json(value)
            except (TypeError, ValueError):
                raise ValueError("Use JSON objects containing finite JSON values") from None
        return value


def canonical_json(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def https_url(value: Union[str, None]) -> Union[str, None]:
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in value):
        raise ValueError("Use an absolute HTTPS URL without embedded credentials")
    return value


class MediaReference(StrictModel):
    asset_id: UUID
    alt_text: Union[Annotated[str, StringConstraints(strict=True, max_length=2000)], None] = None
    caption_asset_id: Union[UUID, None] = None


Hashtags = Annotated[tuple[Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)], ...], Field(max_length=50)]
Media = Annotated[tuple[MediaReference, ...], Field(max_length=35)]


class MasterContent(StrictModel):
    text: BoundedText = ""
    link: Union[Annotated[str, StringConstraints(strict=True, max_length=2048)], None] = None
    hashtags: Hashtags = ()
    media: Media = ()

    _link = field_validator("link")(https_url)


class TextOverride(StrictModel):
    mode: Literal["replace"]
    value: BoundedText


class LinkOverride(StrictModel):
    mode: Literal["replace"]
    value: Union[Annotated[str, StringConstraints(strict=True, max_length=2048)], None]
    _link = field_validator("value")(https_url)


class HashtagOverride(StrictModel):
    mode: Literal["replace"]
    value: Hashtags


class MediaOverride(StrictModel):
    mode: Literal["replace"]
    value: Media


class SparseOverrides(StrictModel):
    text: Union[TextOverride, None] = None
    link: Union[LinkOverride, None] = None
    hashtags: Union[HashtagOverride, None] = None
    media: Union[MediaOverride, None] = None

    @field_validator("text", "link", "hashtags", "media", mode="before")
    @classmethod
    def forbid_explicit_null(cls, value):
        if value is None:
            raise ValueError("Remove the override key to inherit; explicit null overrides are invalid")
        return value


    @model_serializer(mode="wrap")
    def serialize_sparse(self, handler):
        return {key: value for key, value in handler(self).items() if key in self.model_fields_set}


class DocumentTarget(StrictModel):
    account_id: UUID
    format: PostFormat
    overrides: SparseOverrides = Field(default_factory=SparseOverrides)


class PostDocument(StrictModel):
    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    master: MasterContent
    targets: Annotated[tuple[DocumentTarget, ...], Field(max_length=25)] = ()

    @field_validator("targets")
    @classmethod
    def unique_accounts(cls, values):
        if len({v.account_id for v in values}) != len(values):
            raise ValueError("Select each account only once")
        return values


class Reference(StrictModel):
    url: Annotated[str, StringConstraints(strict=True, max_length=2048)]
    label: Union[Annotated[str, StringConstraints(strict=True, max_length=300)], None] = None
    _url = field_validator("url")(https_url)


class CreatePost(StrictModel):
    title: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=300)]
    content_type: Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]{0,63}$")] = "announcement"
    document: PostDocument
    references: Annotated[tuple[Reference, ...], Field(max_length=30)] = ()


class PatchPost(StrictModel):
    expected_version: PositiveVersion
    title: Union[Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=300)], None] = None
    content_type: Union[Annotated[str, StringConstraints(strict=True, pattern='^[a-z][a-z0-9_]{0,63}$')], None] = None
    document: Union[PostDocument, None] = None
    references: Union[Annotated[tuple[Reference, ...], Field(max_length=30)], None] = None

    @field_validator("title", "content_type", "document", "references", mode="before")
    @classmethod
    def no_null(cls, value):
        if value is None:
            raise ValueError("Editable fields cannot be null; omit fields to retain them")
        return value


class VersionCommand(StrictModel):
    expected_version: PositiveVersion


class ValidateCommand(StrictModel):
    expected_version: Union[PositiveVersion, None] = None


class ReviewAttestation(StrictModel):
    facts_checked: StrictBool
    sources_checked: StrictBool


class ApproveCommand(VersionCommand):
    revision_id: UUID
    review_attestation: Union[ReviewAttestation, None] = None


class RejectCommand(VersionCommand):
    reason: Reason


class PublishCommand(ApproveCommand):
    acknowledged_warning_codes: Annotated[tuple[StrictStr, ...], Field(max_length=50)] = ()


class ScheduleTime(StrictModel):
    local_time: Annotated[str, StringConstraints(strict=True, max_length=30)]
    timezone: Annotated[str, StringConstraints(strict=True, max_length=100)]
    utc_offset: Annotated[str, StringConstraints(strict=True, pattern=r"^[+-](?:0[0-9]|1[0-4]):[0-5][0-9]$")]


class ScheduleCommand(PublishCommand):
    schedule: ScheduleTime


class ResumeCommand(PublishCommand):
    reason: Reason


class RetryCommand(StrictModel):
    reason: Reason


class ControlsCommand(VersionCommand):
    publishing_enabled: StrictBool
    reason: Reason


class CapabilitySet(StrictModel):
    rules_version: StrictStr = "social-v1"
    provider_api_version: StrictStr = "unverified"
    eligible: StrictBool = False
    supported_formats: tuple[PostFormat, ...] = ()
    feature_states: dict[StrictStr, FeatureState] = Field(default_factory=lambda: {"publishing": "unverified", "media_upload": "unsupported"})
    limits: dict[StrictStr, Union[Annotated[int, Field(strict=True, ge=0)], None]] = Field(default_factory=dict)
    granted_scopes: tuple[StrictStr, ...] = ()
    required_scopes: tuple[StrictStr, ...] = ()
    price_class: Literal["free", "paid", "unverified"] = "unverified"
    source_links: tuple[StrictStr, ...] = ()
    verified_at: Union[datetime, None] = None
    adapter_available: StrictBool = False


class InspectedAsset(StrictModel):
    asset_id: UUID
    sha256: Hash
    mime_type: StrictStr
    byte_size: Annotated[int, Field(strict=True, gt=0)]
    width: Union[Annotated[int, Field(strict=True, gt=0)], None] = None
    height: Union[Annotated[int, Field(strict=True, gt=0)], None] = None
    duration_ms: Union[Annotated[int, Field(strict=True, gt=0)], None] = None
    alt_text: Union[StrictStr, None] = None
    caption_asset_id: Union[UUID, None] = None
    caption_sha256: Union[Hash, None] = None


class ResolvedPostPayload(StrictModel):
    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)] = 1
    account_id: UUID
    platform: Platform
    api_product: StrictStr
    external_account_id: StrictStr
    format: PostFormat
    text: BoundedText
    link: Union[StrictStr, None] = None
    hashtags: Hashtags = ()
    assets: tuple[InspectedAsset, ...] = ()
    visibility: Literal["public"] = "public"
    disclosures: tuple[StrictStr, ...] = ()
    capability_version: StrictStr = "social-v1"
    evidence_hash: Hash
    content_hash: Hash

    _link = field_validator("link")(https_url)

    @field_validator("external_account_id")
    @classmethod
    def nonblank_identity(cls, value):
        if not value.strip():
            raise ValueError("An external account identity cannot be blank")
        return value


class ValidationIssue(StrictModel):
    code: StrictStr
    field: StrictStr
    message: StrictStr


class TargetValidation(StrictModel):
    account_id: UUID
    platform: Union[Platform, None] = None
    valid: StrictBool
    errors: tuple[ValidationIssue, ...] = ()
    warnings: tuple[ValidationIssue, ...] = ()
    resolved_preview: Union[ResolvedPostPayload, None] = None


class ValidationResult(StrictModel):
    valid: StrictBool
    rules_version: Literal["social-v1"] = "social-v1"
    targets: tuple[TargetValidation, ...] = ()
    errors: tuple[ValidationIssue, ...] = ()
    warnings: tuple[ValidationIssue, ...] = ()


class OperationPlan(StrictModel):
    operation_id: UUID
    operation: Literal["upload", "create_container", "finalize", "publish", "poll", "reconcile", "delete"]
    publication_capable: StrictBool
    safe_replay_class: Literal["safe", "requires_reconciliation", "read_only"]
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: Annotated[int, Field(strict=True, gt=0, le=90)] = 30
    estimated_cost_microusd: Annotated[int, Field(strict=True, ge=0)] = 0


class OperationResult(StrictModel):
    outcome: Literal["confirmed_success", "processing", "definite_failure", "ambiguous"]
    remote_refs: dict[str, Any] = Field(default_factory=dict)
    primary_remote_id: Union[StrictStr, None] = None
    remote_url: Union[StrictStr, None] = None
    visibility_state: Literal["unknown", "public", "private", "manual_action"] = "unknown"
    confirmation_kind: Union[StrictStr, None] = None
    error_code: Union[StrictStr, None] = None
    safe_error_message: Union[StrictStr, None] = None
    provider_request_id: Union[StrictStr, None] = None
    http_status: Union[Annotated[int, Field(strict=True, ge=100, le=599)], None] = None
    provider_code: Union[StrictStr, None] = None
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    receipt: dict[str, Any] = Field(default_factory=dict)
    next_action_at: Union[datetime, None] = None
    retry_safe: StrictBool = False

    _remote_url = field_validator("remote_url")(https_url)

    @field_validator("primary_remote_id", "confirmation_kind")
    @classmethod
    def nonblank_public_proof(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Public identity and confirmation cannot be blank")
        return value


class DefinitiveAbsenceProof(StrictModel):
    """A provider-established absence, bound to the original mutation/account.

    A generic nonempty evidence object is audit context, never permission to
    resend. The worker verifies both identities against the frozen payload and
    original operation intent before a new public submission can be admitted.
    """

    kind: Literal["provider_definitive_status", "confirmed_not_sent"]
    verified: StrictBool
    coverage_complete: StrictBool
    account_id: UUID
    operation_id: UUID

    @field_validator("verified", "coverage_complete")
    @classmethod
    def positive_complete_proof(cls, value):
        if value is not True:
            raise ValueError("An absence proof must be verified and complete")
        return value


class ReconciliationResult(StrictModel):
    outcome: Literal["confirmed_published", "definitively_unpublished", "still_processing", "unknown"]
    evidence: dict[str, Any] = Field(default_factory=dict)
    absence_proof: Union[DefinitiveAbsenceProof, None] = None
    result: Union[OperationResult, None] = None
    next_action_at: Union[datetime, None] = None


class RetryDecision(StrictModel):
    action: Literal["retry", "block", "fail", "reconcile"]
    reason: StrictStr
    next_action_at: Union[datetime, None] = None


class CredentialUpdate(StrictModel):
    prior_version: PositiveVersion
    bundle: dict[str, Any]
    scopes: tuple[StrictStr, ...] = ()
    access_expires_at: Union[datetime, None] = None
    refresh_expires_at: Union[datetime, None] = None

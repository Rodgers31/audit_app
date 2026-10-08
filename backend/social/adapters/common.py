"""Typed, payload-bound state and local validation shared by Meta adapters."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Literal
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from ..contracts import (CapabilitySet, Hash, OperationPlan, OperationResult,
    ResolvedPostPayload, StrictModel, ValidationIssue, ValidationResult, canonical_hash)
from ..worker.materials import WorkerCredentialMaterial
from ..native_admission import NativeCapabilityAdmission, native_capability_matches
from .meta_http import MetaHTTP, MetaHTTPFailure, remote_id


class Checkpoint(StrictModel):
    schema_version: Literal[1]
    adapter: Literal["facebook_pages-v1", "instagram_facebook_login-v1"]
    account_id: UUID
    external_account_id: str
    content_hash: Hash
    phase: Literal["upload_uncertain", "photo_uploaded", "post_created", "creation_uncertain",
                   "quota_checked", "container_created", "container_ready", "publish_ready",
                   "publication_uncertain", "media_created"]
    photo_id: str | None = None
    photo_post_id: str | None = None
    post_id: str | None = None
    container_id: str | None = None
    media_id: str | None = None
    poll_count: int = Field(strict=True, ge=0, le=5)

    @field_validator("schema_version", mode="before")
    @classmethod
    def strict_schema(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Invalid checkpoint schema version")
        return value

    @field_validator("external_account_id", "photo_id", "container_id", "media_id")
    @classmethod
    def numeric_id(cls, value):
        return remote_id(value) if value is not None else None

    @field_validator("post_id", "photo_post_id")
    @classmethod
    def composite_id(cls, value):
        return remote_id(value, composite=True) if value is not None else None


def caption(payload, *, include_link=True):
    parts = [payload.text]
    if payload.hashtags:
        parts.append(" ".join(tag if tag.startswith("#") else "#" + tag for tag in payload.hashtags))
    if include_link and payload.link:
        parts.append(payload.link)
    return "\n\n".join(part for part in parts if part)


def issue(code, field, message):
    return ValidationIssue(code=code, field=field, message=message)


def public_url(value, platform):
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid public permalink")
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname not in {platform + ".com", "www." + platform + ".com"} or parsed.port not in {None, 443} or parsed.username or parsed.password or parsed.fragment or "\\" in value:
            raise ValueError("Invalid public permalink")
    except (ValueError, TypeError):
        raise ValueError("Invalid public permalink") from None
    if platform == "instagram" and parsed.query:
        raise ValueError("Invalid public permalink")
    if platform == "facebook" and parsed.query:
        query = parse_qs(parsed.query, keep_blank_values=True)
        if not query or set(query) - {"story_fbid", "id", "fbid", "set", "type"} or any(len(values) != 1 or not re.fullmatch(r"[0-9a.]{1,100}", values[0]) for values in query.values()):
            raise ValueError("Invalid public permalink")
    return value


class MetaAdapter:
    platform = ""
    product = ""
    checkpoint_name = ""
    formats = ()
    scopes = ()
    source_links = ()
    limits = {}
    phases = {}

    def __init__(self, config, *, transport, now=None):
        self.config = config
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.http = MetaHTTP(config, transport=transport, now=self.now)

    async def close(self):
        await self.http.close()

    def capabilities(self, account):
        granted = account.get("granted_scopes", ())
        if not isinstance(granted, (list, tuple)) or any(not isinstance(s, str) for s in granted):
            granted = ()
        prior = account.get("capability_snapshot", {})
        eligible = bool(isinstance(prior, dict) and prior.get("eligible") is True and
            account.get("platform") == self.platform and account.get("api_product") == self.product and
            account.get("connection_state") == "connected" and set(self.scopes) <= set(granted))
        return CapabilitySet(provider_api_version=self.config.graph_version,
            eligible=eligible, supported_formats=self.formats,
            feature_states={"publishing": "supported" if self.config.ready and eligible else "restricted",
                            "media_upload": "supported", "carousel": "unsupported", "video": "unsupported", "reel": "unsupported"},
            limits=self.limits, granted_scopes=tuple(sorted(set(granted))), required_scopes=self.scopes,
            price_class="free", source_links=self.source_links, verified_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
            adapter_available=self.config.ready)

    def validate(self, payload: ResolvedPostPayload, capabilities: CapabilitySet):
        errors = []
        if not self.config.ready or not capabilities.adapter_available or not capabilities.eligible:
            errors.append(issue("ADAPTER_NOT_AVAILABLE", "capabilities", "Native publishing requires explicit server construction and operational acceptance."))
        if payload.platform != self.platform or payload.api_product != self.product:
            errors.append(issue("ACCOUNT_PRODUCT_MISMATCH", "account_id", "Use the exact connected Meta API product."))
        if payload.format not in self.formats:
            errors.append(issue("UNSUPPORTED_FORMAT", "format", "This native adapter supports only its advertised formats."))
        if not set(self.scopes) <= set(capabilities.granted_scopes):
            errors.append(issue("PERMISSION_DENIED", "scopes", "The account lacks a required Meta permission."))
        if canonical_hash(payload.model_dump(mode="json", exclude={"content_hash"})) != payload.content_hash:
            errors.append(issue("PAYLOAD_HASH_MISMATCH", "content_hash", "The immutable publishing payload no longer matches its authorized hash."))
        try:
            remote_id(payload.external_account_id)
        except ValueError:
            errors.append(issue("ACCOUNT_ID_INVALID", "account_id", "The connected Meta identity is invalid."))
        if payload.disclosures:
            errors.append(issue("UNSUPPORTED_DISCLOSURE", "disclosures", "This publishing slice does not support provider disclosure settings."))
        if any(not re.fullmatch(r"#?\w+", tag) for tag in payload.hashtags):
            errors.append(issue("INVALID_HASHTAG", "hashtags", "Use individual hashtags containing letters, numbers or underscores."))
        if payload.format == "text" and payload.assets or payload.format == "image" and len(payload.assets) != 1:
            errors.append(issue("FORMAT_MEDIA_MISMATCH", "assets", "Select the advertised number of inspected assets."))
        if any(a.caption_asset_id is not None or a.caption_sha256 is not None for a in payload.assets):
            errors.append(issue("UNSUPPORTED_CAPTION_ASSET", "assets", "Caption assets are unsupported for static image publishing."))
        errors.extend(self._content_errors(payload))
        return ValidationResult(valid=not errors, errors=tuple(errors))

    def _material(self, payload, credential):
        if not self.config.ready:
            raise MetaHTTPFailure("AUTHORIZATION_REQUIRED", retry_safe=True)
        if not isinstance(credential, WorkerCredentialMaterial) or credential.account_id != payload.account_id or credential.platform != self.platform or credential.api_product != self.product or credential.external_account_id != payload.external_account_id or type(credential.credential_version) is not int or credential.credential_version < 1 or not isinstance(credential.credential_id, UUID):
            raise MetaHTTPFailure("AUTHORIZATION_REQUIRED", retry_safe=True)
        try:
            remote_id(credential.page_id)
        except ValueError:
            raise MetaHTTPFailure("AUTHORIZATION_REQUIRED", retry_safe=True) from None
        if self.platform == "facebook" and credential.page_id != payload.external_account_id:
            raise MetaHTTPFailure("AUTHORIZATION_REQUIRED", retry_safe=True)
        if not isinstance(credential.granted_scopes, tuple) or any(not isinstance(scope, str) for scope in credential.granted_scopes) or not set(self.scopes) <= set(credential.granted_scopes):
            raise MetaHTTPFailure("PERMISSION_DENIED", retry_safe=True)
        if not isinstance(credential.page_access_token, str) or not 0 < len(credential.page_access_token) <= 16384 or any(ord(c) < 32 or ord(c) == 127 for c in credential.page_access_token):
            raise MetaHTTPFailure("AUTHORIZATION_REQUIRED", retry_safe=True)
        for expiry in (credential.access_expires_at, credential.data_access_expires_at):
            if expiry is not None and (not isinstance(expiry, datetime) or expiry.tzinfo is None or expiry.utcoffset() is None or expiry <= self.now()):
                raise MetaHTTPFailure("TOKEN_EXPIRED", retry_safe=True)
        return credential

    def _checkpoint(self, payload, value):
        if value == {}:
            return None
        state = Checkpoint.model_validate(value)
        if state.adapter != self.checkpoint_name or state.account_id != payload.account_id or state.external_account_id != payload.external_account_id or state.content_hash != payload.content_hash or state.phase not in self.phases:
            raise ValueError("Checkpoint does not match immutable publishing identity")
        expected = self.phases[state.phase]
        if self.platform == "facebook" and payload.format == "text" and state.phase in {"post_created", "publication_uncertain"}:
            expected = expected - {"photo_id"}
        refs = {key for key in ("photo_id", "post_id", "container_id", "media_id") if getattr(state, key) is not None}
        if refs != expected or state.post_id and not state.post_id.startswith(payload.external_account_id + "_"):
            raise ValueError("Checkpoint has inconsistent remote identities")
        if state.photo_post_id and (not state.photo_id or not state.photo_post_id.startswith(payload.external_account_id + "_")):
            raise ValueError("Unpublished photo post belongs to another Page")
        if self.platform == "facebook" and payload.format == "text" and state.photo_id is not None:
            raise ValueError("Text checkpoint contains an image")
        return state

    def _state(self, payload, phase, *, previous=None, poll_count=0, **refs):
        if previous:
            refs = {key: getattr(previous, key) for key in ("photo_id", "photo_post_id", "post_id", "container_id", "media_id") if getattr(previous, key) is not None} | refs
        result = Checkpoint(schema_version=1, adapter=self.checkpoint_name,
            account_id=payload.account_id, external_account_id=payload.external_account_id,
            content_hash=payload.content_hash, phase=phase, poll_count=poll_count, **refs)
        return result.model_dump(mode="json", exclude_none=True)

    @staticmethod
    def _plan(operation, checkpoint):
        read = operation == "poll"
        return OperationPlan(operation_id=uuid4(), operation=operation,
            publication_capable=operation == "publish",
            safe_replay_class="read_only" if read else "requires_reconciliation",
            checkpoint=checkpoint, timeout_seconds=25)

    @staticmethod
    def _failure(error, checkpoint):
        return OperationResult(outcome="ambiguous" if error.ambiguous else "definite_failure",
            error_code=error.code, safe_error_message="Meta publishing requires review of the recorded safe outcome.",
            retry_safe=error.retry_safe, http_status=error.http_status,
            provider_code=error.provider_code, next_action_at=error.next_action_at, checkpoint=checkpoint)

    def _processing(self, checkpoint, *, code=None):
        return OperationResult(outcome="processing", checkpoint=checkpoint, error_code=code,
                               next_action_at=self.now() + timedelta(seconds=60))

    def _success(self, checkpoint, response):
        state = Checkpoint.model_validate(checkpoint)
        refs = {key: getattr(state, key) for key in ("photo_id", "photo_post_id", "post_id", "container_id", "media_id") if getattr(state, key) is not None}
        return OperationResult(outcome="confirmed_success", remote_refs=refs, checkpoint=checkpoint,
                               http_status=response.http_status, next_action_at=response.next_action_at,
                               receipt={"provider_api_version": self.config.graph_version})

    def _admission(self, payload, operation, credential):
        material = self._material(payload, credential)
        admission = material.capability_admission
        caps = self.capabilities({"platform": material.platform, "api_product": material.api_product,
            "granted_scopes": material.granted_scopes, "connection_state": "connected",
            "capability_snapshot": {"eligible": isinstance(admission, NativeCapabilityAdmission) and admission.eligible is True}})
        if operation.safe_replay_class != "read_only":
            if not native_capability_matches(admission, caps) or payload.capability_version != caps.rules_version:
                raise MetaHTTPFailure("ACCOUNT_INELIGIBLE", retry_safe=True)
        else:
            # Publishing restrictions do not erase readback of an accepted send.
            # Credentials, identity, payload integrity and read-only fencing stay
            # mandatory; this copy is used only for local payload validation.
            caps = caps.model_copy(update={"eligible": True})
        if not self.validate(payload, caps).valid:
            raise MetaHTTPFailure("INVALID_PUBLISHING_PAYLOAD", retry_safe=True)
        state = self._checkpoint(payload, operation.checkpoint)
        expected = self.next_operation(payload, operation.checkpoint)
        if operation.operation != expected.operation or operation.publication_capable != expected.publication_capable or operation.safe_replay_class != expected.safe_replay_class:
            raise ValueError("Operation does not match checkpoint")
        return material, state

    def validate_mutation_admission(self, payload, account):
        """Explicit worker hook, shared with API and final material admission."""
        caps = self.capabilities(account)
        if not native_capability_matches(account.get("capability_snapshot"), caps) or payload.capability_version != caps.rules_version:
            return ValidationResult(valid=False, errors=(issue("ACCOUNT_INELIGIBLE", "capabilities",
                "The persisted native publishing admission requires verification."),))
        return self.validate(payload, caps)


def verify_bytes(asset, value, maximum):
    if type(value) is not bytes or len(value) != asset.byte_size or not 0 < len(value) <= maximum or hashlib.sha256(value).hexdigest() != asset.sha256:
        raise MetaHTTPFailure("INSPECTED_MEDIA_CHANGED", retry_safe=True)
    return value

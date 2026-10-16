"""X API v2, one cost-reserved request per durable operation.

No endpoint retries or absence inference. Bounded own-post recovery requires
the original immutable dispatch intent. Construction,
verified application access, current credentials and an operation-bound budget
reservation are all required before any HTTP request, including status reads.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from pydantic import Field, field_validator

from ..contracts import (CapabilitySet, Hash, OperationPlan, OperationResult,
    ReconciliationResult, StrictModel, ValidationIssue, ValidationResult, canonical_hash)
from ..native_admission import NativeCapabilityAdmission
from ..worker.materials import WorkerCredentialMaterial
from .x_text import contains_url, count_text, render_text


CONTRACT = "x-v2-2026-10-16"
CHUNK_BYTES = 4_000_000
MAX_MEDIA_BYTES = 8_000_000  # Application ceiling, not a provider entitlement.
POST_READ_COST = 15_000  # One post + one expanded author (public visibility).
OWN_POST_LOOKUP_COST = 35_000  # At most five posts + one expanded author.
SOURCES = ("https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code",
    "https://docs.x.com/fundamentals/counting-characters",
    "https://docs.x.com/x-api/posts/create-post",
    "https://docs.x.com/x-api/users/get-posts",
    "https://docs.x.com/x-api/media/quickstart/media-upload-chunked",
    "https://docs.x.com/x-api/getting-started/pricing",
    "https://docs.x.com/openapi.json")


@dataclass(frozen=True)
class XAdapterConfig:
    enabled: bool = False
    operational_gates_verified: bool = False
    media_uploads_enabled: bool = False
    api_version: str = "2"
    contract_version: str = CONTRACT
    # No public upload tariff was established. Real construction must supply a
    # reviewed ceiling before media endpoints can reserve any spending.
    media_request_cost_microusd: int | None = None

    def __post_init__(self):
        if any(type(v) is not bool for v in (self.enabled, self.operational_gates_verified, self.media_uploads_enabled)):
            raise ValueError("X feature gates require explicit booleans")
        if self.api_version != "2" or self.contract_version != CONTRACT:
            raise ValueError("X contract version is pinned")
        if self.media_request_cost_microusd is not None and (type(self.media_request_cost_microusd) is not int
                or not 0 < self.media_request_cost_microusd <= 1_000_000):
            raise ValueError("A reviewed positive media request cost ceiling is required")

    @property
    def ready(self):
        return self.enabled and self.operational_gates_verified


class XCheckpoint(StrictModel):
    schema_version: Literal[1] = 1
    adapter: Literal["x-v2-2026-10-16"] = CONTRACT
    account_id: UUID
    external_account_id: str
    content_hash: Hash
    phase: Literal["initialized", "appended", "media_processing", "media_ready", "metadata_ready",
                   "publication_uncertain", "mutation_uncertain", "post_created"]
    asset_index: int = Field(strict=True, ge=0, le=4)
    media_ids: tuple[str, ...] = ()
    media_keys: tuple[str, ...] = ()
    next_segment: int = Field(default=0, strict=True, ge=0, le=2)
    poll_count: int = Field(default=0, strict=True, ge=0, le=10)
    expires_at: datetime | None = None
    post_id: str | None = None

    @field_validator("schema_version", mode="before")
    @classmethod
    def strict_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Invalid checkpoint version")
        return value

    @field_validator("external_account_id", "post_id")
    @classmethod
    def identity(cls, value):
        return _id(value) if value is not None else None

    @field_validator("media_ids")
    @classmethod
    def media_identity(cls, value):
        if len(value) > 4 or len(set(value)) != len(value):
            raise ValueError("Invalid media identity list")
        return tuple(_id(item) for item in value)

    @field_validator("media_keys")
    @classmethod
    def key_identity(cls, value):
        if len(value) > 4 or len(set(value)) != len(value) or any(not re.fullmatch(r"[0-9]{1,3}_[0-9]{1,19}", item) for item in value):
            raise ValueError("Invalid media key list")
        return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,19}", value):
        raise ValueError("Invalid X remote identity")
    return value


def _issue(code, field, message):
    return ValidationIssue(code=code, field=field, message=message)


class XFailure(Exception):
    def __init__(self, code, *, ambiguous=False, status=None, retry_safe=False, next_at=None):
        super().__init__(code)
        self.code, self.ambiguous, self.status = code, ambiguous, status
        self.retry_safe, self.next_at = retry_safe, next_at


def _no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate response field")
        value[key] = item
    return value


class XAdapter:
    platform = "x"
    product = "x_api_v2"
    scopes = ("tweet.read", "tweet.write", "users.read")
    formats = ("text", "image", "carousel", "video")

    def __init__(self, config: XAdapterConfig, *, transport, now=None):
        if not isinstance(config, XAdapterConfig) or not isinstance(transport, httpx.AsyncBaseTransport):
            raise ValueError("Explicit X settings and HTTP transport are required")
        self.config, self.now = config, now or (lambda: datetime.now(timezone.utc))
        self.client = httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False,
            timeout=httpx.Timeout(15, connect=5), limits=httpx.Limits(max_connections=2, max_keepalive_connections=2))

    async def close(self):
        await self.client.aclose()

    def capabilities(self, account):
        granted = account.get("granted_scopes", ())
        if not isinstance(granted, (tuple, list)) or any(not isinstance(item, str) for item in granted):
            granted = ()
        snapshot = account.get("capability_snapshot", {})
        access = account.get("x_access_verified", snapshot.get("x_access_verified", False) if isinstance(snapshot, dict) else False)
        budget = account.get("x_budget_remaining_microusd", 0)
        eligible = (account.get("platform") == self.platform and account.get("api_product") == self.product
            and account.get("connection_state") == "connected" and isinstance(snapshot, dict)
            and snapshot.get("eligible") is True and access is True and type(budget) is int and budget > 0
            and set(self.scopes) <= set(granted))
        media = self.config.media_uploads_enabled and self.config.media_request_cost_microusd is not None and "media.write" in granted
        return CapabilitySet(provider_api_version=CONTRACT, eligible=eligible,
            supported_formats=self.formats if media else ("text",), granted_scopes=tuple(sorted(set(granted))),
            required_scopes=self.scopes, adapter_available=self.config.ready, price_class="paid",
            feature_states={"publishing": "supported" if self.config.ready and eligible else "restricted",
                "media_upload": "supported" if media else "restricted", "replies": "unverified", "editing": "unsupported"},
            limits={"max_text_length": 280, "transformed_url_length": 23, "max_media_count": 4,
                "max_image_bytes": 5_000_000, "max_video_bytes": MAX_MEDIA_BYTES,
                "max_video_duration_ms": 60_000, "max_alt_text_length": 1000},
            source_links=SOURCES, verified_at=datetime(2026, 10, 16, tzinfo=timezone.utc))

    def validate(self, payload, capabilities):
        errors = []
        if not self.config.ready or not capabilities.adapter_available or not capabilities.eligible:
            errors.append(_issue("ADAPTER_NOT_AVAILABLE", "capabilities", "X requires verified access and an explicit positive spending policy."))
        if payload.platform != self.platform or payload.api_product != self.product:
            errors.append(_issue("ACCOUNT_PRODUCT_MISMATCH", "account_id", "Use the connected X API v2 account."))
        if payload.format not in capabilities.supported_formats:
            errors.append(_issue("UNSUPPORTED_FORMAT", "format", "The selected X format has not passed its access and upload gates."))
        if not set(self.scopes) <= set(capabilities.granted_scopes):
            errors.append(_issue("PERMISSION_DENIED", "scopes", "Required X user scopes are missing."))
        if payload.assets and "media.write" not in capabilities.granted_scopes:
            errors.append(_issue("PERMISSION_DENIED", "scopes", "X media upload requires media.write."))
        if payload.disclosures:
            errors.append(_issue("UNSUPPORTED_DISCLOSURE", "disclosures", "Unsupported X disclosures must be resolved explicitly."))
        if canonical_hash(payload.model_dump(mode="json", exclude={"content_hash"})) != payload.content_hash:
            errors.append(_issue("PAYLOAD_HASH_MISMATCH", "content_hash", "The immutable payload changed."))
        if payload.capability_version != capabilities.rules_version:
            errors.append(_issue("CAPABILITY_VERSION_CHANGED", "capabilities", "The X validation contract changed."))
        try:
            _id(payload.external_account_id)
            if count_text(render_text(payload)) > 280:
                errors.append(_issue("TEXT_TOO_LONG", "text", "The combined X text exceeds 280 weighted characters."))
        except ValueError:
            errors.append(_issue("X_TEXT_OR_ID_INVALID", "text", "Use valid Unicode and explicit ASCII HTTP(S) links."))
        if (payload.format == "text" and payload.assets or payload.format in {"image", "video"} and len(payload.assets) != 1
                or payload.format == "carousel" and not 2 <= len(payload.assets) <= 4):
            errors.append(_issue("FORMAT_MEDIA_MISMATCH", "assets", "Use one video or one to four inspected photos."))
        if not render_text(payload).strip() and not payload.assets:
            errors.append(_issue("CONTENT_REQUIRED", "text", "A post requires text or media."))
        for asset in payload.assets:
            video = payload.format == "video"
            valid = (asset.mime_type == "video/mp4" and asset.duration_ms is not None and 500 <= asset.duration_ms <= 60_000
                     and asset.byte_size <= MAX_MEDIA_BYTES) if video else (asset.mime_type in {"image/jpeg", "image/png"}
                     and asset.duration_ms is None and asset.byte_size <= 5_000_000)
            if not valid or asset.width is None or asset.height is None:
                errors.append(_issue("UNSUPPORTED_MEDIA", "assets", "Use inspected JPEG/PNG or an MP4 within the application media limits."))
            if asset.alt_text is not None and (not asset.alt_text.strip() or len(asset.alt_text) > 1000):
                errors.append(_issue("ALT_TEXT_INVALID", "assets.alt_text", "X image descriptions require 1–1000 characters."))
            if asset.caption_asset_id is not None or asset.caption_sha256 is not None:
                errors.append(_issue("CAPTION_TRACK_UNAVAILABLE", "assets", "External subtitle tracks require a separately accepted media contract."))
        return ValidationResult(valid=not errors, errors=tuple(errors))

    def validate_mutation_admission(self, payload, account):
        caps = self.capabilities(account)
        try:
            prior = NativeCapabilityAdmission.from_snapshot(account.get("capability_snapshot"))
            current = NativeCapabilityAdmission.from_snapshot(caps)
            matches = prior == current and prior.eligible and prior.adapter_available and prior.price_class == "paid" and prior.publishing_state == "supported"
        except (ValueError, TypeError):
            matches = False
        if not matches or payload.capability_version != caps.rules_version:
            return ValidationResult(valid=False, errors=(_issue("ACCOUNT_INELIGIBLE", "capabilities", "X admission must match the reviewed account contract."),))
        return self.validate(payload, caps)

    def _state(self, payload, phase, previous=None, **changes):
        data = previous.model_dump() if previous else dict(account_id=payload.account_id,
            external_account_id=payload.external_account_id, content_hash=payload.content_hash, asset_index=0)
        return XCheckpoint(**(data | changes | {"phase": phase})).model_dump(mode="json", exclude_none=True)

    def _checkpoint(self, payload, checkpoint):
        if checkpoint == {}:
            return None
        state = XCheckpoint.model_validate(checkpoint)
        if (state.account_id != payload.account_id or state.external_account_id != payload.external_account_id
                or state.content_hash != payload.content_hash or state.asset_index > len(payload.assets)
                or len(state.media_ids) != len(state.media_keys)
                or len(state.media_ids) not in {state.asset_index, min(state.asset_index+1, len(payload.assets))}
                or (state.post_id is not None) != (state.phase == "post_created")):
            raise ValueError("X checkpoint does not match the immutable target")
        if any(not key.endswith("_" + identity) for key, identity in zip(state.media_keys, state.media_ids)):
            raise ValueError("X media identity mismatch")
        if state.expires_at is not None and (state.expires_at.tzinfo is None or state.expires_at.utcoffset() is None):
            raise ValueError("X media expiry must be aware")
        active = {"initialized", "appended", "media_processing", "media_ready"}
        if state.phase in active:
            if (state.asset_index >= len(payload.assets) or len(state.media_ids) != state.asset_index+1
                    or state.expires_at is None):
                raise ValueError("Active X upload lacks its exact asset and media identity")
            segments = (payload.assets[state.asset_index].byte_size + CHUNK_BYTES - 1) // CHUNK_BYTES
            if (state.phase == "initialized" and state.next_segment != 0
                    or state.phase == "appended" and not 1 <= state.next_segment <= segments
                    or state.phase in {"media_processing", "media_ready"} and state.next_segment != segments):
                raise ValueError("X upload phase contradicts its chunk checkpoint")
        if state.phase == "metadata_ready" and (state.asset_index < 1 or len(state.media_ids) != state.asset_index
                or state.next_segment != 0 or state.expires_at is None):
            raise ValueError("X metadata checkpoint lacks a completed asset")
        if state.phase in {"post_created", "publication_uncertain"} and (
                state.asset_index != len(payload.assets) or len(state.media_ids) != len(payload.assets)
                or state.next_segment != 0 or bool(payload.assets) != (state.expires_at is not None)):
            raise ValueError("X publication checkpoint must bind every selected asset")
        return state

    def _cost(self, payload, operation, state):
        if operation == "publish":
            return 200_000 if contains_url(render_text(payload)) else 15_000
        if operation == "reconcile" or operation == "poll" and state and state.phase == "post_created":
            return POST_READ_COST
        if operation == "finalize" and state and state.phase == "media_ready":
            return 5_000  # Metadata write, not media upload finalize.
        if self.config.media_request_cost_microusd is None:
            raise XFailure("BUDGET_EXHAUSTED", retry_safe=True)
        return self.config.media_request_cost_microusd

    def next_operation(self, payload, checkpoint):
        state = self._checkpoint(payload, checkpoint)
        if state and state.phase in {"publication_uncertain", "mutation_uncertain"}:
            raise ValueError("An uncertain X mutation requires reconciliation")
        if state and state.phase == "post_created":
            operation = "poll"
        elif not payload.assets:
            operation = "publish"
        elif state is None or state.phase == "metadata_ready" and state.asset_index < len(payload.assets):
            operation = "create_container"
        elif state.phase in {"initialized", "appended"}:
            operation = "upload" if state.next_segment * CHUNK_BYTES < payload.assets[state.asset_index].byte_size else "finalize"
        elif state.phase == "media_processing":
            operation = "poll"
        elif state.phase == "media_ready":
            operation = "finalize"  # Separate metadata boundary after upload.
        elif state.phase == "metadata_ready":
            operation = "publish"
        else:
            raise ValueError("Unusable X checkpoint")
        return OperationPlan(operation_id=uuid4(), operation=operation, publication_capable=operation == "publish",
            safe_replay_class="read_only" if operation == "poll" else "requires_reconciliation", checkpoint=checkpoint,
            timeout_seconds=25, estimated_cost_microusd=self._cost(payload, operation, state))

    def reconciliation_operation(self, payload, checkpoint):
        state = self._checkpoint(payload, checkpoint)
        return OperationPlan(operation_id=uuid4(), operation="reconcile", publication_capable=False,
            safe_replay_class="read_only", checkpoint=checkpoint, timeout_seconds=25,
            estimated_cost_microusd=POST_READ_COST if state and state.post_id else OWN_POST_LOOKUP_COST)

    def _admit(self, payload, credential, operation=None, *, expected_cost=0, reservation_id=None):
        if not self.config.ready:
            raise XFailure("AUTHORIZATION_REQUIRED", retry_safe=True)
        if (not isinstance(credential, WorkerCredentialMaterial) or credential.account_id != payload.account_id
                or credential.platform != self.platform or credential.api_product != self.product
                or credential.external_account_id != payload.external_account_id or credential.page_id != payload.external_account_id
                or type(credential.credential_version) is not int or credential.credential_version < 1
                or not isinstance(credential.credential_id, UUID)):
            raise XFailure("AUTHORIZATION_REQUIRED", retry_safe=True)
        if getattr(credential, "x_access_verified", False) is not True:
            raise XFailure("ACCOUNT_INELIGIBLE", retry_safe=True)
        budget = getattr(credential, "x_budget_remaining_microusd", 0)
        reserved = getattr(credential, "x_reserved_cost_microusd", 0)
        if (type(budget) is not int or budget <= 0 or type(reserved) is not int or reserved < expected_cost
                or budget < expected_cost or expected_cost <= 0
                or getattr(credential, "x_reservation_operation_id", None) != reservation_id):
            raise XFailure("BUDGET_EXHAUSTED", retry_safe=True)
        scopes = credential.granted_scopes
        if not isinstance(scopes, tuple) or any(not isinstance(scope, str) for scope in scopes) or not set(self.scopes) <= set(scopes) or payload.assets and "media.write" not in scopes:
            raise XFailure("PERMISSION_DENIED", retry_safe=True)
        token = credential.page_access_token
        if not isinstance(token, str) or not 1 <= len(token) <= 16384 or any(not 33 <= ord(c) <= 126 for c in token):
            raise XFailure("AUTHORIZATION_REQUIRED", retry_safe=True)
        if credential.access_expires_at is None:
            raise XFailure('TOKEN_EXPIRED', retry_safe=True)
        for expiry in (credential.access_expires_at, credential.data_access_expires_at):
            if expiry is not None and (not isinstance(expiry, datetime) or expiry.tzinfo is None or expiry.utcoffset() is None or expiry <= self.now()):
                raise XFailure("TOKEN_EXPIRED", retry_safe=True)
        admission = credential.capability_admission
        caps = self.capabilities({"platform": self.platform, "api_product": self.product, "granted_scopes": scopes,
            "connection_state": "connected", "capability_snapshot": {"eligible": True},
            "x_access_verified": True, "x_budget_remaining_microusd": budget})
        if operation and operation.safe_replay_class != "read_only":
            if admission != NativeCapabilityAdmission.from_snapshot(caps):
                raise XFailure("ACCOUNT_INELIGIBLE", retry_safe=True)
        if not self.validate(payload, caps).valid:
            raise XFailure("INVALID_PUBLISHING_PAYLOAD", retry_safe=True)
        return token

    async def _request(self, method, path, token, *, params=None, body=None, files=None, data=None):
        if (method, path) not in {("POST", "/2/tweets"), ("POST", "/2/media/upload/initialize"),
                ("GET", "/2/media/upload"), ("POST", "/2/media/metadata")} and not (
                method == "GET" and re.fullmatch(r"/2/tweets/[0-9]{1,19}", path) or
                method == "GET" and re.fullmatch(r"/2/users/[0-9]{1,19}/tweets", path) or
                method == "POST" and re.fullmatch(r"/2/media/upload/[0-9]{1,19}/(?:append|finalize)", path)):
            raise ValueError("Unsupported X operation")
        response = None
        try:
            request = self.client.build_request(method, "https://api.x.com" + path, params=params,
                headers={"Authorization": "Bearer " + token, "Accept-Encoding": "identity"}, json=body, files=files, data=data)
            response = await self.client.send(request, stream=True)
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("Compressed provider response refused")
            chunks, size = [], 0
            async for chunk in response.aiter_bytes(chunk_size=16384):
                size += len(chunk)
                if size > 65536:
                    raise ValueError("Response exceeds bound")
                chunks.append(chunk)
            raw = b"".join(chunks)
            value = json.loads(raw, object_pairs_hook=_no_duplicates,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError())) if raw else {}
            if not isinstance(value, dict):
                raise ValueError("X response must be an object")
        except (httpx.HTTPError, ValueError, TypeError, RecursionError):
            raise XFailure("PROVIDER_OUTCOME_UNCERTAIN", ambiguous=True) from None
        finally:
            if response is not None:
                await response.aclose()
        status = response.status_code
        if not 200 <= status < 300 or value.get("errors"):
            ambiguous = status >= 500 or status < 400 or "data" in value
            code = {401: "TOKEN_REVOKED", 403: "PERMISSION_DENIED", 402: "BUDGET_EXHAUSTED", 429: "RATE_LIMITED"}.get(status, "PROVIDER_REJECTED")
            next_at = None
            delays = []
            reset = response.headers.get("x-rate-limit-reset", "")
            if status == 429 and re.fullmatch(r"[0-9]{1,12}", reset):
                try:
                    delays.append(datetime.fromtimestamp(int(reset), timezone.utc))
                except (ValueError, OverflowError, OSError):
                    pass
            if status == 429:
                retry = response.headers.get('retry-after','')
                try:
                    if re.fullmatch(r'[0-9]{1,9}', retry):
                        delays.append(self.now()+timedelta(seconds=int(retry)))
                    elif retry:
                        date=parsedate_to_datetime(retry)
                        if date.tzinfo is not None:
                            delays.append(date)
                except (ValueError, TypeError, OverflowError):
                    pass
                future=[date for date in delays if date>self.now()]
                next_at=max(future) if future else None
            raise XFailure("PROVIDER_OUTCOME_UNCERTAIN" if ambiguous else code, ambiguous=ambiguous,
                status=status, retry_safe=not ambiguous and (status != 429 or next_at is not None), next_at=next_at)
        return value, status

    def _result(self, checkpoint, *, outcome="confirmed_success", **fields):
        return OperationResult(outcome=outcome, checkpoint=checkpoint,
            receipt={"provider_api_version": CONTRACT}, **fields)

    def _failure(self, error, checkpoint):
        return self._result(checkpoint, outcome="ambiguous" if error.ambiguous else "definite_failure",
            error_code=error.code, safe_error_message="The recorded X operation requires review.",
            http_status=error.status, retry_safe=error.retry_safe, next_action_at=error.next_at)

    async def execute(self, payload, operation, credential, media_access):
        checkpoint, state = operation.checkpoint, self._checkpoint(payload, operation.checkpoint)
        try:
            expected = self.next_operation(payload, checkpoint)
            if (operation.operation, operation.publication_capable, operation.safe_replay_class, operation.estimated_cost_microusd) != (
                    expected.operation, expected.publication_capable, expected.safe_replay_class, expected.estimated_cost_microusd):
                raise ValueError("Operation does not match the X checkpoint and cost")
            token = self._admit(payload, credential, operation, expected_cost=expected.estimated_cost_microusd,
                reservation_id=operation.operation_id)
            if payload.assets and not (self.config.media_uploads_enabled and self.config.media_request_cost_microusd):
                raise XFailure("AUTHORIZATION_REQUIRED", retry_safe=True)
            if state and state.expires_at is not None and state.expires_at <= self.now() and state.phase != "post_created":
                raise XFailure("MEDIA_EXPIRED", retry_safe=True)
            if operation.operation == "publish":
                body = {"text": render_text(payload)}
                if payload.assets:
                    if state.asset_index != len(payload.assets) or len(state.media_ids) != len(payload.assets):
                        raise ValueError("All selected X media must be checkpointed")
                    body["media"] = {"media_ids": list(state.media_ids)}
                checkpoint = self._state(payload, "publication_uncertain", state)
                value, status = await self._request("POST", "/2/tweets", token, body=body)
                post_id = _id(value.get("data", {}).get("id"))
                checkpoint = self._state(payload, "post_created", state, post_id=post_id)
                return self._result(checkpoint, http_status=status, remote_refs={"post_id": post_id}, primary_remote_id=post_id,
                    remote_url=f"https://x.com/i/web/status/{post_id}", confirmation_kind="provider_create_ack",
                    visibility_state="unknown")
            if state and state.phase == "post_created":
                return await self._read_post(payload, state, token)
            asset = payload.assets[state.asset_index if state else 0]
            if operation.operation == "create_container":
                checkpoint = self._state(payload, "mutation_uncertain", state)
                value, status = await self._request("POST", "/2/media/upload/initialize", token,
                    body={"media_type": asset.mime_type, "total_bytes": asset.byte_size,
                        "media_category": "tweet_video" if payload.format == "video" else "tweet_image"})
                result = value.get("data", {})
                media_id = _id(result.get("id"))
                media_key = result.get("media_key")
                if not isinstance(media_key, str) or not re.fullmatch(r"[0-9]{1,3}_" + media_id, media_key):
                    raise ValueError("Missing media key")
                expiry = result.get("expires_after_secs")
                if type(expiry) is not int or not 1 <= expiry <= 86400:
                    raise ValueError("Missing media expiry")
                expires_at = self.now() + timedelta(seconds=expiry)
                if state and state.expires_at:
                    expires_at = min(expires_at, state.expires_at)
                checkpoint = self._state(payload, "initialized", state, media_ids=(*(state.media_ids if state else ()), media_id),
                    media_keys=(*(state.media_keys if state else ()), media_key), next_segment=0, expires_at=expires_at)
                return self._result(checkpoint, http_status=status)
            media_id = state.media_ids[state.asset_index]
            if operation.operation == "upload":
                if media_access is None:
                    raise XFailure("MEDIA_ACCESS_REQUIRED", retry_safe=True)
                content = await media_access.read_bytes(asset, MAX_MEDIA_BYTES)
                if (type(content) is not bytes or len(content) != asset.byte_size or len(content) > MAX_MEDIA_BYTES
                        or hashlib.sha256(content).hexdigest() != asset.sha256):
                    raise XFailure("MEDIA_BYTES_UNVERIFIED", retry_safe=True)
                segment = state.next_segment
                checkpoint = self._state(payload, "mutation_uncertain", state)
                _, status = await self._request("POST", f"/2/media/upload/{media_id}/append", token,
                    data={"segment_index": str(segment)}, files={"media": ("segment", content[segment*CHUNK_BYTES:(segment+1)*CHUNK_BYTES], "application/octet-stream")})
                return self._result(self._state(payload, "appended", state, next_segment=segment+1), http_status=status)
            if operation.operation == "finalize" and state.phase == "media_ready":
                if asset.alt_text:
                    checkpoint = self._state(payload, "mutation_uncertain", state)
                    value, status = await self._request("POST", "/2/media/metadata", token,
                        body={"id": media_id, "metadata": {"alt_text": {"text": asset.alt_text}}})
                    if value.get("data", {}).get("id") != media_id:
                        raise ValueError("Metadata acknowledgement identity missing")
                else:
                    status = None
                return self._result(self._state(payload, "metadata_ready", state, asset_index=state.asset_index+1, next_segment=0, poll_count=0), http_status=status)
            if operation.operation == "finalize":
                checkpoint = self._state(payload, "mutation_uncertain", state)
                value, status = await self._request("POST", f"/2/media/upload/{media_id}/finalize", token)
            elif operation.operation == "poll":
                if state.poll_count >= 10:
                    raise XFailure("PROCESSING_DEADLINE_EXCEEDED")
                value, status = await self._request("GET", "/2/media/upload", token, params={"command": "STATUS", "media_id": media_id})
            else:
                raise ValueError("Invalid X media operation")
            result = value.get("data", {})
            if result.get("id") != media_id:
                raise ValueError("Media status identity mismatch")
            processing = result.get("processing_info")
            if (processing is None and operation.operation == "finalize"
                    or isinstance(processing, dict) and processing.get("state") == "succeeded"):
                return self._result(self._state(payload, "media_ready", state), http_status=status)
            if not isinstance(processing, dict) or processing.get("state") not in {"pending", "in_progress", "failed"}:
                raise ValueError("Invalid processing status")
            if processing["state"] == "failed":
                raise XFailure("MEDIA_PROCESSING_FAILED", status=status)
            delay = processing.get("check_after_secs")
            if type(delay) is not int or not 1 <= delay <= 86400:
                raise ValueError("Invalid media retry delay")
            return self._result(self._state(payload, "media_processing", state, poll_count=state.poll_count+1),
                outcome="processing", http_status=status, next_action_at=self.now()+timedelta(seconds=delay))
        except XFailure as error:
            # A definitely rejected request retains its exact input; uncertain
            # responses retain the no-replay phase with every known remote ref.
            return self._failure(error, checkpoint if error.ambiguous else operation.checkpoint)
        except (ValueError, TypeError, KeyError, AttributeError, IndexError):
            return self._failure(XFailure("PROVIDER_OUTCOME_UNCERTAIN", ambiguous=True), checkpoint)

    async def _read_post(self, payload, state, token):
        value, status = await self._request("GET", "/2/tweets/" + state.post_id, token,
            params={"tweet.fields": "author_id,attachments,entities,withheld", "expansions": "author_id", "user.fields": "protected"})
        return self._confirm_post(payload, state, value.get("data", {}), value.get("includes", {}), status)

    def _confirm_post(self, payload, state, data, includes, status):
        """The same exact public proof is required for ID and bounded lookup."""
        text = data.get("text")
        if not isinstance(text, str):
            raise XFailure("PUBLICATION_NOT_CONFIRMED", ambiguous=True)
        # Provider t.co wrapping is reversible only using the response entities.
        urls = data.get("entities", {}).get("urls", [])
        keys = data.get("attachments", {}).get("media_keys", [])
        if not isinstance(urls, list) or len(urls) > 20:
            raise XFailure("PUBLICATION_NOT_CONFIRMED", ambiguous=True)
        for url in urls:
            if not isinstance(url, dict) or not isinstance(url.get("url"), str) or not isinstance(url.get("expanded_url"), str):
                raise XFailure("PUBLICATION_NOT_CONFIRMED", ambiguous=True)
            expanded = urlsplit(url["expanded_url"])
            # X appends a t.co attachment URL to response text. Only strip a
            # suffix whose entity points to this exact post's selected media;
            # the separately checked attachment keys bind the uploaded assets.
            attachment = (bool(state.media_keys) and keys == list(state.media_keys)
                and expanded.scheme == "https" and expanded.hostname in {"x.com", "twitter.com"}
                and expanded.port in {None, 443} and not expanded.username and not expanded.password
                and not expanded.query and not expanded.fragment and re.fullmatch(
                    r"/[A-Za-z0-9_]{1,15}/status/" + state.post_id + r"/(?:photo|video)/[1-4]", expanded.path)
                and re.fullmatch(r"https://t\.co/[A-Za-z0-9]+", url["url"])
                and text.endswith(" " + url["url"]))
            if attachment:
                text = text[:-(len(url["url"])+1)]
            else:
                text = text.replace(url["url"], url["expanded_url"])
        authors = includes.get("users", [])
        if (data.get("id") != state.post_id or data.get("author_id") != payload.external_account_id
                or text != render_text(payload) or keys != list(state.media_keys)
                or not isinstance(authors, list) or len(authors) != 1 or not isinstance(authors[0], dict)
                or authors[0].get("id") != payload.external_account_id or authors[0].get("protected") is not False
                or data.get("withheld") is not None):
            raise XFailure("PUBLICATION_NOT_CONFIRMED", ambiguous=True)
        return self._result(state.model_dump(mode="json", exclude_none=True), http_status=status,
            remote_refs={"post_id": state.post_id}, primary_remote_id=state.post_id,
            remote_url=f"https://x.com/i/web/status/{state.post_id}", confirmation_kind="provider_owned_post_read",
            visibility_state="public")

    def _lookup_dispatch_window(self, payload, state, attempt):
        if not isinstance(attempt, dict) or attempt.get("operation") != "publish":
            raise XFailure("X_ORIGINAL_DISPATCH_UNVERIFIED")
        intent = attempt.get("receipt", {}).get("intent", {})
        if (not isinstance(intent, dict) or intent.get("publication_capable") is not True
                or intent.get("mutating") is not True or intent.get("safe_replay_class") != "requires_reconciliation"):
            raise XFailure("X_ORIGINAL_DISPATCH_UNVERIFIED")
        original_id = attempt.get("operation_id")
        if not isinstance(original_id, UUID):
            try:
                if not isinstance(original_id, str) or str(UUID(original_id)) != original_id:
                    raise ValueError()
            except (ValueError, TypeError):
                raise XFailure("X_ORIGINAL_DISPATCH_UNVERIFIED") from None
        dispatched = attempt.get("dispatch_started_at")
        if (not isinstance(dispatched, datetime) or dispatched.tzinfo is None or dispatched.utcoffset() is None
                or dispatched < datetime(2010, 11, 6, tzinfo=timezone.utc)):
            raise XFailure("X_ORIGINAL_DISPATCH_UNVERIFIED")
        # Crash-before-save leaves the original input; a recorded uncertain
        # response changes only its phase. Reconstruct the exact authorized
        # publish input and compare the durable request fingerprint.
        if payload.assets:
            if not state or state.phase not in {"metadata_ready", "publication_uncertain"} or state.asset_index != len(payload.assets):
                raise XFailure("X_ORIGINAL_DISPATCH_UNVERIFIED")
            original_checkpoint = state.model_dump(mode="json", exclude_none=True) | {"phase": "metadata_ready"}
        else:
            if state is not None and state.phase != "publication_uncertain":
                raise XFailure("X_ORIGINAL_DISPATCH_UNVERIFIED")
            original_checkpoint = {}
        fingerprint = canonical_hash({"payload_hash": payload.content_hash, "operation": "publish", "checkpoint": original_checkpoint})
        if attempt.get("request_fingerprint") != fingerprint:
            raise XFailure("X_ORIGINAL_DISPATCH_UNVERIFIED")
        start, end = dispatched-timedelta(seconds=5), dispatched+timedelta(minutes=5)
        if start < datetime(2010, 11, 6, tzinfo=timezone.utc):
            raise XFailure("X_ORIGINAL_DISPATCH_UNVERIFIED")
        # Never truncate a future window to "now" and claim complete coverage.
        if end >= self.now():
            raise XFailure("X_LOOKUP_WINDOW_NOT_COVERED", next_at=end+timedelta(seconds=1))
        return start, end

    async def _lookup_own_post(self, payload, state, token, attempt):
        start, end = self._lookup_dispatch_window(payload, state, attempt)
        def stamp(value):
            return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        value, status = await self._request("GET", "/2/users/" + payload.external_account_id + "/tweets", token,
            params={"max_results": "5", "start_time": stamp(start), "end_time": stamp(end),
                "post.fields": "attachments,created_at,entities,withheld", "expansions": "author_id", "user.fields": "protected"})
        rows, meta = value.get("data", []), value.get("meta")
        if (not isinstance(rows, list) or not isinstance(meta, dict) or len(rows) > 5
                or type(meta.get("result_count")) is not int or meta["result_count"] != len(rows)
                or "next_token" in meta or "previous_token" in meta
                or "errors" in value and value["errors"] != []):
            raise XFailure("X_LOOKUP_INCOMPLETE")
        matches, seen = [], set()
        for data in rows:
            if not isinstance(data, dict) or not isinstance(data.get("text"), str) or data.get("author_id") != payload.external_account_id:
                raise XFailure("X_LOOKUP_INCOMPLETE")
            identity = _id(data.get("id"))
            if identity in seen:
                raise XFailure("X_LOOKUP_INCOMPLETE")
            seen.add(identity)
            timestamp = data.get("created_at")
            if not isinstance(timestamp, str) or len(timestamp) > 40:
                raise XFailure("X_LOOKUP_INCOMPLETE")
            created = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if created.tzinfo is None or created.utcoffset() is None or not start <= created < end:
                raise XFailure("X_LOOKUP_INCOMPLETE")
            candidate = XCheckpoint.model_validate(self._state(payload, "post_created", state, post_id=identity))
            try:
                matches.append(self._confirm_post(payload, candidate, data, value.get("includes", {}), status))
            except XFailure:
                # A well-shaped different post is not this dispatch. Only one
                # complete strong match can identify the lost acknowledgement.
                continue
        if len(matches) != 1:
            raise XFailure("X_LOOKUP_MATCH_NOT_UNIQUE")
        return matches[0], {"confidence": "unique_strong_match", "matching_rows": 1,
            "returned_rows": len(rows), "coverage": "complete_bounded_page",
            "window_start": stamp(start), "window_end": stamp(end),
            "original_operation_id": str(attempt["operation_id"]),
            "original_request_fingerprint": attempt["request_fingerprint"],
            "criteria": ["account", "created_at", "rendered_text", "selected_media_keys", "public_author", "not_withheld"]}

    async def reconcile(self, payload, checkpoint, attempt, credential=None, media_access=None):
        # The legacy interface cannot bind a reservation to the new paid read
        # intent. Refuse it instead of trusting a reservation's self-identity.
        return ReconciliationResult(outcome="unknown", evidence={"code": "BUDGET_EXHAUSTED", "charge_reservation": "held"})

    async def reconcile_operation(self, payload, operation, attempt, credential=None, media_access=None):
        checkpoint = operation.checkpoint
        state = self._checkpoint(payload, checkpoint)
        try:
            cost = POST_READ_COST if state and state.post_id else OWN_POST_LOOKUP_COST
            if (operation.operation != "reconcile" or operation.publication_capable
                    or operation.safe_replay_class != "read_only" or operation.estimated_cost_microusd != cost):
                raise XFailure("BUDGET_EXHAUSTED", retry_safe=True)
            token = self._admit(payload, credential, expected_cost=cost, reservation_id=operation.operation_id)
            if state is None or state.phase != "post_created":
                result, evidence = await self._lookup_own_post(payload, state, token, attempt)
                kind = "X_UNIQUE_BOUNDED_OWN_POST"
            else:
                result = await self._read_post(payload, state, token)
                evidence = {}
                kind = "X_EXACT_OWNED_POST"
            return ReconciliationResult(outcome="confirmed_published", result=result,
                evidence={"code": kind, "post_id": result.primary_remote_id, "provider_api_version": CONTRACT, **evidence})
        except XFailure as error:
            outcome = 'still_reconciling' if error.code == 'X_LOOKUP_WINDOW_NOT_COVERED' else 'unknown'
            return ReconciliationResult(outcome=outcome, evidence={"code": error.code, "charge_reservation": "held"}, next_action_at=error.next_at)
        except (ValueError, TypeError, KeyError, AttributeError):
            return ReconciliationResult(outcome="unknown", evidence={"code": "X_READBACK_UNVERIFIED", "charge_reservation": "held"})

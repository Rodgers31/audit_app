"""TikTok Accounts API v1.3, gated owned-account publication and recovery.

Standard Content Posting/Direct Post is deliberately not an alternate product.
Every network boundary fits an existing durable worker OperationPlan.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import Field, StrictBool, StrictStr, field_validator

from ..contracts import (CapabilitySet, Hash, OperationPlan, OperationResult,
    ReconciliationResult, StrictModel, ValidationResult, canonical_hash)
from ..native_admission import native_capability_matches
from ..worker.materials import ProviderFetchURL, WorkerCredentialMaterial
from .common import caption, issue
from .tiktok_http import TikTokHTTP, TikTokHTTPFailure, bounded_string, identity


SOURCES = (
    "https://business-api.tiktok.com/portal/docs/accounts-api-overview/v1.3",
    "https://business-api.tiktok.com/portal/docs/publish-a-public-video-post-to-an-owned-account/v1.3",
    "https://business-api.tiktok.com/portal/docs/publish-a-photo-post-to-an-owned-account/v1.3",
    "https://business-api.tiktok.com/portal/docs/get-the-post-privacy-settings-of-a-tiktok-account/v1.3",
    "https://business-api.tiktok.com/portal/docs/get-the-publishing-status-of-a-tiktok-post/v1.3",
    "https://developers.tiktok.com/docs/en/content-sharing-guidelines",
)


@dataclass(frozen=True)
class TikTokAdapterConfig:
    api_version: str = "v1.3"
    enabled: bool = False
    operational_gates_verified: bool = False
    product_access_verified: bool = False
    unattended_publication_verified: bool = False

    def __post_init__(self):
        if self.api_version != "v1.3":
            raise ValueError("TikTok Accounts API contract is pinned to v1.3")
        if any(type(value) is not bool for value in (self.enabled, self.operational_gates_verified, self.product_access_verified, self.unattended_publication_verified)):
            raise ValueError("TikTok gates require explicit booleans")

    @property
    def ready(self):
        return self.enabled and self.operational_gates_verified and self.product_access_verified


class TikTokCreatorSettings(StrictModel):
    privacy_level_options: tuple[Literal["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"], ...]
    comment_disabled: StrictBool
    duet_disabled: StrictBool
    stitch_disabled: StrictBool
    max_video_post_duration_sec: int = Field(strict=True, ge=3, le=600)

    @field_validator("privacy_level_options")
    @classmethod
    def valid_options(cls, value):
        if not value or len(value) != len(set(value)):
            raise ValueError("Creator privacy options must be nonempty and unique")
        return tuple(sorted(value))

    def bound_hash(self, external_account_id):
        return canonical_hash({"external_account_id": external_account_id, "settings": self.model_dump(mode="json")})


class TikTokCheckpoint(StrictModel):
    schema_version: Literal[1]
    adapter: Literal["tiktok_accounts_api-v1.3"]
    account_id: UUID
    external_account_id: StrictStr
    content_hash: Hash
    mode: Literal["direct", "draft"]
    phase: Literal["settings_checked", "submission_uncertain", "submitted", "public", "manual_action", "failed"]
    settings_hash: Hash
    checked_at: datetime
    share_id: StrictStr | None = None
    post_ids: tuple[StrictStr, ...] = ()
    poll_count: int = Field(strict=True, ge=0, le=20)

    @field_validator("schema_version", mode="before")
    @classmethod
    def strict_schema(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Invalid checkpoint version")
        return value

    @field_validator("external_account_id", "share_id")
    @classmethod
    def valid_identity(cls, value):
        return identity(value) if value is not None else None

    @field_validator("post_ids")
    @classmethod
    def public_identities(cls, value):
        if len(value) > 35 or len(set(value)) != len(value) or any(not re.fullmatch(r"[0-9]{1,64}", item) for item in value):
            raise ValueError("Invalid public post identities")
        return value


def verified_fetch_url(value, prefixes):
    """Only the approved origin/path; never follow a redirect or use suffix matching."""
    bounded_string(value, maximum=8000)
    if not value.isascii() or any(c.isspace() for c in value) or "\\" in value:
        raise ValueError("Invalid media URL")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in {None, 443} or parsed.fragment or "%" in parsed.path
            or any(segment in {".", ".."} for segment in parsed.path.split("/"))):
        raise ValueError("Invalid media URL")
    if not isinstance(prefixes, tuple) or not prefixes:
        raise ValueError("Provider-verified media URL property required")
    for prefix in prefixes:
        bounded_string(prefix, maximum=2000)
        owned = urlsplit(prefix)
        if (owned.scheme != "https" or not owned.hostname or owned.username or owned.password
                or owned.port not in {None, 443} or owned.query or owned.fragment or "\\" in prefix
                or "%" in owned.path or not owned.path.endswith("/")
                or any(segment in {".", ".."} for segment in owned.path.split("/"))):
            raise ValueError("Invalid provider-verified property")
        if parsed.hostname == owned.hostname and parsed.path.startswith(owned.path):
            return value
    raise ValueError("URL is outside provider-verified media properties")


class TikTokAccountsAdapter:
    platform = "tiktok"
    product = "tiktok_accounts_api"
    formats = ("image", "carousel", "video")
    scopes = ("video.publish",)
    limits = {"max_video_bytes": 100000000, "min_video_duration_ms": 3000,
        "max_video_duration_ms": 600000, "max_media_count": 35, "max_image_bytes": 8000000,
        "max_publications_24h": 15, "max_publications_minute": 6,
        "max_video_caption_utf16": 2200, "max_photo_caption_utf16": 4000, "max_photo_title_utf16": 90}

    def __init__(self, config, *, transport, now=None):
        if not isinstance(config, TikTokAdapterConfig):
            raise ValueError("Explicit TikTok configuration required")
        self.config = config
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.http = TikTokHTTP(transport=transport, now=self.now)

    async def close(self):
        await self.http.close()

    def capabilities(self, account):
        scopes = account.get("granted_scopes", ())
        if not isinstance(scopes, (list, tuple)) or any(not isinstance(value, str) for value in scopes):
            scopes = ()
        eligible = (account.get("platform") == self.platform and account.get("api_product") == self.product
            and account.get("connection_state") == "connected" and account.get("tiktok_product_approved") is True
            and self.config.ready and bool({"video.publish", "video.upload"} & set(scopes)))
        return CapabilitySet(provider_api_version="v1.3", eligible=eligible, supported_formats=self.formats,
            feature_states={"publishing": "supported" if eligible else "restricted", "media_upload": "restricted",
                "native_scheduling": "unsupported", "unattended_publication": "supported" if self.config.unattended_publication_verified else "requires_review", "delete": "unsupported", "edit": "unsupported"},
            limits=self.limits, granted_scopes=tuple(sorted(set(scopes))),
            required_scopes=("video.publish",) if "video.publish" in scopes else ("video.upload",),
            price_class="free", adapter_available=self.config.ready, source_links=SOURCES,
            verified_at=datetime(2026, 10, 16, tzinfo=timezone.utc))

    def validate(self, payload, capabilities):
        errors = []
        if not self.config.ready or not capabilities.eligible or not capabilities.adapter_available:
            errors.append(issue("ACCOUNT_INELIGIBLE", "capabilities", "TikTok requires genuine approved Accounts API product access and accepted operational gates."))
        if payload.platform != self.platform or payload.api_product != self.product:
            errors.append(issue("ACCOUNT_PRODUCT_MISMATCH", "account_id", "Use the approved TikTok Accounts API product."))
        if canonical_hash(payload.model_dump(mode="json", exclude={"content_hash"})) != payload.content_hash:
            errors.append(issue("PAYLOAD_HASH_MISMATCH", "content_hash", "The immutable payload differs from its authorized hash."))
        try:
            identity(payload.external_account_id)
        except (ValueError, TypeError):
            errors.append(issue("ACCOUNT_ID_INVALID", "account_id", "A valid approved account identity is required."))
        options = payload.tiktok_options
        if options is None:
            errors.append(issue("TIKTOK_CHOICES_REQUIRED", "tiktok_options", "Review current creator settings, choose privacy and consent to upload."))
        else:
            required_scope = "video.upload" if options.mode == "draft" else "video.publish"
            if required_scope not in capabilities.granted_scopes:
                errors.append(issue("PERMISSION_DENIED", "scopes", "The approved workflow's token permission is missing."))
            if not options.upload_consent or not options.music_usage_confirmed:
                errors.append(issue("UPLOAD_CONSENT_REQUIRED", "tiktok_options", "Explicit upload consent and Music Usage Confirmation are required."))
            if options.mode == "direct" and options.privacy_level != "PUBLIC_TO_EVERYONE":
                errors.append(issue("PUBLIC_VISIBILITY_REQUIRED", "tiktok_options.privacy_level", "The owned-account direct video endpoint publishes publicly; choose public explicitly."))
            if options.commercial_content != (options.is_brand_organic or options.is_branded_content):
                errors.append(issue("DISCLOSURE_SELECTION_REQUIRED", "tiktok_options", "Commercial content must select your brand, branded content, or both."))
            if options.is_branded_content and (not options.branded_content_policy_confirmed or options.privacy_level == "SELF_ONLY"):
                errors.append(issue("BRANDED_CONTENT_POLICY_REQUIRED", "tiktok_options", "Branded content requires policy confirmation and non-private visibility."))
            if len(options.photo_title.encode("utf-16-le")) // 2 > 90:
                errors.append(issue("TITLE_TOO_LONG", "tiktok_options.photo_title", "TikTok photo titles allow 90 UTF-16 code units."))
            if payload.format != "video" and (not options.disable_duet or not options.disable_stitch):
                errors.append(issue("PHOTO_INTERACTIONS_UNSUPPORTED", "tiktok_options", "Photo posts do not support Duet or Stitch."))
            if payload.format == "video" and options.photo_title:
                errors.append(issue("PHOTO_TITLE_UNSUPPORTED", "tiktok_options.photo_title", "Photo titles apply only to photo posts."))
            if payload.format != "video" and options.is_ai_generated:
                errors.append(issue("PHOTO_AI_DISCLOSURE_UNSUPPORTED", "tiktok_options", "This verified photo API contract does not expose an AI disclosure field."))
            # A draft drops these provider metadata fields. Never pretend that
            # these controls will survive the inbox handoff.
            if options.mode == "draft" and (options.commercial_content or options.is_ai_generated or not options.disable_comment or not options.disable_duet or not options.disable_stitch):
                errors.append(issue("DRAFT_METADATA_IGNORED", "tiktok_options", "TikTok ignores these draft settings; complete them in the TikTok app."))
        if payload.format not in self.formats:
            errors.append(issue("UNSUPPORTED_FORMAT", "format", "Use an inspected video or JPEG/WebP photo post."))
        count = len(payload.assets)
        if (payload.format in {"image", "video"} and count != 1) or (payload.format == "carousel" and not 2 <= count <= 35):
            errors.append(issue("FORMAT_MEDIA_MISMATCH", "assets", "Select one video/image or two to 35 carousel images."))
        if payload.link or payload.disclosures:
            errors.append(issue("UNSUPPORTED_METADATA", "link", "Use caption text and explicit TikTok disclosure controls; caption links are not advertised."))
        maximum = 2200 if payload.format == "video" else 4000
        try:
            too_long = len(caption(payload, include_link=False).encode("utf-16-le")) // 2 > maximum
        except UnicodeEncodeError:
            too_long = True
        if too_long:
            errors.append(issue("CAPTION_TOO_LONG", "text", "TikTok's rendered caption exceeds its UTF-16 limit."))
        if len(re.findall(r"(?<![\w@])@[A-Za-z0-9_.]+", caption(payload, include_link=False))) > 30:
            errors.append(issue("TOO_MANY_MENTIONS", "text", "TikTok allows at most 30 caption mentions."))
        for asset in payload.assets:
            if asset.caption_asset_id or asset.caption_sha256 or asset.alt_text:
                errors.append(issue("UNSUPPORTED_ACCESSIBILITY_METADATA", "assets", "TikTok's inspected contract does not support these separate accessibility fields; burn captions into video."))
            if payload.format == "video":
                if asset.mime_type not in {"video/mp4", "video/quicktime", "video/webm"} or asset.byte_size > 100000000 or asset.duration_ms is None or not 3000 <= asset.duration_ms <= 600000:
                    errors.append(issue("INVALID_VIDEO", "assets", "Use an inspected MP4/MOV/WebM video, 3–600 seconds, at most the 100 MB application ceiling."))
                if asset.frame_rate_milli_fps is None or not 23000 <= asset.frame_rate_milli_fps <= 60000:
                    errors.append(issue("INVALID_VIDEO_FRAME_RATE", "assets", "TikTok requires an inspected video frame rate of 23–60 FPS."))
                if asset.width is None or asset.height is None or min(asset.width, asset.height) < 360:
                    errors.append(issue("INVALID_VIDEO_DIMENSIONS", "assets", "TikTok video dimensions must be at least 360 pixels."))
            elif (asset.mime_type not in {"image/jpeg", "image/webp"} or asset.byte_size > 8000000
                    or asset.duration_ms is not None or asset.width is None or asset.height is None
                    or min(asset.width, asset.height) > 1080 or max(asset.width, asset.height) > 1920):
                errors.append(issue("INVALID_PHOTO", "assets", "Use inspected JPEG/WebP photos at most the 8 MB application ceiling, within 1080 by 1920 or 1920 by 1080."))
        return ValidationResult(valid=not errors, errors=tuple(errors))

    def validate_mutation_admission(self, payload, account):
        due,requested=account.get('scheduled_for'),account.get('dispatch_requested_at')
        if due is not None and requested is not None and due>requested and not self.config.unattended_publication_verified:
            return ValidationResult(valid=False,errors=(issue('UNATTENDED_WORKFLOW_UNVERIFIED','schedule','TikTok future delivery requires separate accepted workflow evidence.'),))
        caps = self.capabilities(account)
        if not native_capability_matches(account.get("capability_snapshot"), caps) or payload.capability_version != caps.rules_version:
            return ValidationResult(valid=False, errors=(issue("ACCOUNT_INELIGIBLE", "capabilities", "The current approved TikTok capability differs from the persisted admission."),))
        return self.validate(payload, caps)

    def _checkpoint(self, payload, value):
        if value == {}:
            return None
        state = TikTokCheckpoint.model_validate(value)
        if (state.account_id != payload.account_id or state.external_account_id != payload.external_account_id
                or state.content_hash != payload.content_hash or payload.tiktok_options is None
                or state.mode != payload.tiktok_options.mode):
            raise ValueError("TikTok checkpoint identity differs from immutable target")
        if bool(state.share_id) != (state.phase in {"submitted", "public", "manual_action", "failed"}):
            raise ValueError("TikTok checkpoint remote identity does not match its phase")
        if bool(state.post_ids) != (state.phase == "public") or (state.phase == "public" and state.mode != "direct"):
            raise ValueError("TikTok public proof does not match its workflow")
        return state

    def _state(self, payload, phase, *, previous=None, **changes):
        values = previous.model_dump() if previous else dict(schema_version=1, adapter="tiktok_accounts_api-v1.3",
            account_id=payload.account_id, external_account_id=payload.external_account_id,
            content_hash=payload.content_hash, mode=payload.tiktok_options.mode, poll_count=0)
        values.update(changes, phase=phase)
        return TikTokCheckpoint(**values).model_dump(mode="json", exclude_none=True)

    def next_operation(self, payload, checkpoint):
        state = self._checkpoint(payload, checkpoint)
        operation = "poll"
        if state and state.phase == "settings_checked":
            operation = "upload" if state.mode == "draft" else "publish"
        return OperationPlan(operation_id=uuid4(), operation=operation, checkpoint=checkpoint,
            publication_capable=operation == "publish",
            safe_replay_class="read_only" if operation == "poll" else "requires_reconciliation", timeout_seconds=25)

    def _material(self, payload, material, *, mutating=False):
        if not self.config.ready or getattr(material, 'tiktok_product_approved', False) is not True:
            raise TikTokHTTPFailure('ACCOUNT_INELIGIBLE')
        if (not isinstance(material, WorkerCredentialMaterial) or material.account_id != payload.account_id
                or material.platform != self.platform or material.api_product != self.product
                or material.external_account_id != payload.external_account_id or material.page_id != payload.external_account_id
                or type(material.credential_version) is not int or material.credential_version < 1
                or not isinstance(material.credential_id, UUID)):
            raise TikTokHTTPFailure("AUTHORIZATION_REQUIRED")
        try:
            bounded_string(material.page_access_token)
            identity(material.external_account_id)
        except ValueError:
            raise TikTokHTTPFailure("AUTHORIZATION_REQUIRED") from None
        if material.access_expires_at is None:
            raise TikTokHTTPFailure("AUTHORIZATION_REQUIRED")
        for expiry in (material.access_expires_at, material.data_access_expires_at):
            if expiry is not None and (not isinstance(expiry, datetime) or expiry.tzinfo is None or expiry.utcoffset() is None or expiry <= self.now()):
                raise TikTokHTTPFailure("TOKEN_EXPIRED")
        if not isinstance(material.granted_scopes, tuple) or any(not isinstance(s, str) for s in material.granted_scopes):
            raise TikTokHTTPFailure("PERMISSION_DENIED")
        if canonical_hash(payload.model_dump(mode="json", exclude={"content_hash"})) != payload.content_hash:
            raise TikTokHTTPFailure("INVALID_PUBLISHING_PAYLOAD")
        if mutating:
            if not self.config.ready or getattr(material, "tiktok_product_approved", False) is not True:
                raise TikTokHTTPFailure("ACCOUNT_INELIGIBLE")
            caps = self.capabilities({"platform": material.platform, "api_product": material.api_product,
                "connection_state": "connected", "granted_scopes": material.granted_scopes, "tiktok_product_approved": True})
            if (not native_capability_matches(material.capability_admission, caps)
                    or payload.capability_version != caps.rules_version or not self.validate(payload, caps).valid):
                raise TikTokHTTPFailure("ACCOUNT_INELIGIBLE")
        return material

    def _future_retry_at(self, error):
        value = error.next_action_at
        if (not isinstance(value, datetime) or value.tzinfo is None
                or value.utcoffset() is None or value <= self.now()):
            return None
        return value

    def _failure(self, error, checkpoint):
        retry_at = self._future_retry_at(error)
        return OperationResult(outcome="ambiguous" if error.ambiguous else "definite_failure", checkpoint=checkpoint,
            error_code=error.code, safe_error_message="TikTok requires review of the recorded provider outcome.",
            http_status=error.http_status, provider_code=error.provider_code, next_action_at=retry_at,
            retry_safe=not error.ambiguous and error.code == "RATE_LIMITED" and retry_at is not None)

    def _processing(self, checkpoint, *, code=None):
        return OperationResult(outcome="processing", checkpoint=checkpoint, error_code=code,
            next_action_at=self.now() + timedelta(seconds=180))

    async def creator_settings(self, external_account_id, token):
        response = await self.http.request("GET", "business/video/settings/", token=token,
            params={"business_id": identity(external_account_id)})
        # Restrict to documented semantic fields, not provider prose/metadata.
        fields = set(TikTokCreatorSettings.model_fields)
        settings = TikTokCreatorSettings.model_validate({key: value for key, value in response.data.items() if key in fields})
        return settings

    def _settings_match(self, payload, settings):
        options = payload.tiktok_options
        if options is None or settings.bound_hash(payload.external_account_id) != options.creator_settings_hash:
            raise TikTokHTTPFailure("CREATOR_SETTINGS_CHANGED")
        age = (self.now() - options.creator_settings_checked_at).total_seconds()
        if age < 0 or options.privacy_level not in settings.privacy_level_options:
            raise TikTokHTTPFailure("CREATOR_SETTINGS_CHANGED")
        if any(getattr(settings, name + "_disabled") and not getattr(options, "disable_" + name) for name in ("comment", "duet", "stitch")):
            raise TikTokHTTPFailure("CREATOR_SETTINGS_CHANGED")
        if payload.format == "video" and (payload.assets[0].duration_ms or 0) > settings.max_video_post_duration_sec * 1000:
            raise TikTokHTTPFailure("CREATOR_DURATION_EXCEEDED")

    async def execute(self, payload, operation, credential, media_access):
        checkpoint = operation.checkpoint
        try:
            state = self._checkpoint(payload, checkpoint)
            expected = self.next_operation(payload, checkpoint)
            if (operation.operation, operation.publication_capable, operation.safe_replay_class) != (expected.operation, expected.publication_capable, expected.safe_replay_class):
                raise ValueError("TikTok operation differs from its durable checkpoint")
            material = self._material(payload, credential, mutating=operation.operation != "poll")
            if state is None:
                if not self.config.ready or getattr(material, "tiktok_product_approved", False) is not True:
                    raise TikTokHTTPFailure("ACCOUNT_INELIGIBLE")
                caps = self.capabilities({"platform": material.platform, "api_product": material.api_product,
                    "connection_state": "connected", "granted_scopes": material.granted_scopes, "tiktok_product_approved": True})
                if not self.validate(payload, caps).valid:
                    raise TikTokHTTPFailure("INVALID_PUBLISHING_PAYLOAD")
                settings = await self.creator_settings(payload.external_account_id, material.page_access_token)
                self._settings_match(payload, settings)
                checkpoint = self._state(payload, "settings_checked", settings_hash=settings.bound_hash(payload.external_account_id), checked_at=self.now())
                return OperationResult(outcome="confirmed_success", checkpoint=checkpoint,
                    receipt={"provider_api_version": "v1.3", "creator_settings_hash": settings.bound_hash(payload.external_account_id)})
            if operation.operation == "poll":
                return await self._status(payload, state, material)
            options = payload.tiktok_options
            if (state.settings_hash != options.creator_settings_hash or not 0 <= (self.now() - state.checked_at).total_seconds() <= 300
                    or (self.now() - options.creator_settings_checked_at).total_seconds() < 0):
                raise TikTokHTTPFailure("CREATOR_SETTINGS_CHANGED")
            if media_access is None:
                raise TikTokHTTPFailure("MEDIA_ACCESS_UNAVAILABLE")
            urls = []
            try:
                for asset in payload.assets:
                    access = await media_access.provider_fetch_url(asset, 1800)
                    if (not isinstance(access, ProviderFetchURL) or access.asset_id != asset.asset_id or access.sha256 != asset.sha256
                            or not isinstance(access.expires_at, datetime) or access.expires_at.tzinfo is None
                            or access.expires_at.utcoffset() is None or access.expires_at < self.now() + timedelta(seconds=1800)):
                        raise ValueError("Inspected media URL binding or lifetime invalid")
                    urls.append(verified_fetch_url(access.url, getattr(material, "tiktok_verified_origins", ())))
            except Exception:
                # No provider mutation has been attempted. Raw media URL errors
                # can contain signed material and never cross this boundary.
                raise TikTokHTTPFailure("MEDIA_ACCESS_UNAVAILABLE") from None
            post_info = {"caption": caption(payload, include_link=False), "is_brand_organic": options.is_brand_organic,
                "is_branded_content": options.is_branded_content, "disable_comment": options.disable_comment}
            body = {"business_id": payload.external_account_id, "post_info": post_info}
            if payload.format == "video":
                path = "business/video/publish/"
                body["video_url"] = urls[0]
                post_info.update(disable_duet=options.disable_duet, disable_stitch=options.disable_stitch,
                    is_ai_generated=options.is_ai_generated, upload_to_draft=options.mode == "draft", is_ads_only=False)
            else:
                path = "business/photo/publish/"
                body.update(photo_images=urls, photo_cover_index=0)
                post_info.update(title=options.photo_title, privacy_level=options.privacy_level,
                    is_draft=options.mode == "draft", auto_add_music=False)
            uncertain = self._state(payload, "submission_uncertain", previous=state)
            try:
                response = await self.http.request("POST", path, token=material.page_access_token, data=body)
                share_id = identity(response.data.get("share_id"))
                checkpoint = self._state(payload, "submitted", previous=state, share_id=share_id)
                return self._processing(checkpoint).model_copy(update={"provider_request_id": response.request_id,
                    "remote_refs": {"share_id": share_id}, "receipt": {"provider_api_version": "v1.3", "mode": options.mode}})
            except TikTokHTTPFailure as error:
                return self._failure(error, uncertain if error.ambiguous else checkpoint)
            except (ValueError, TypeError):
                return self._failure(TikTokHTTPFailure("PROVIDER_OUTCOME_UNCERTAIN", ambiguous=True), uncertain)
        except TikTokHTTPFailure as error:
            return self._failure(error, checkpoint)

    async def _status(self, payload, state, material):
        checkpoint = state.model_dump(mode="json", exclude_none=True)
        if state.share_id is None:
            return self._failure(TikTokHTTPFailure("PUBLICATION_VERIFICATION_REQUIRED", ambiguous=True), checkpoint)
        if state.poll_count >= 20:
            return self._failure(TikTokHTTPFailure("PUBLICATION_VERIFICATION_REQUIRED", ambiguous=True), checkpoint)
        checkpoint = self._state(payload, state.phase, previous=state, poll_count=state.poll_count + 1)
        try:
            response = await self.http.request("GET", "business/publish/status/", token=material.page_access_token,
                params={"business_id": payload.external_account_id, "publish_id": state.share_id})
            status = response.data.get("status")
            post_ids = response.data.get("post_ids")
            if post_ids is not None and not isinstance(post_ids, list):
                raise ValueError("Invalid public post ID shape")
            if status == "PUBLISH_COMPLETE" and isinstance(post_ids, list) and post_ids and state.mode == "direct":
                checkpoint = self._state(payload, "public", previous=state, post_ids=tuple(post_ids), poll_count=state.poll_count + 1)
                return OperationResult(outcome="confirmed_success", checkpoint=checkpoint, primary_remote_id=post_ids[0],
                    remote_refs={"share_id": state.share_id, "post_ids": post_ids}, visibility_state="public",
                    confirmation_kind="tiktok_accounts_public_status_post_ids", provider_request_id=response.request_id,
                    receipt={"provider_api_version": "v1.3", "content_hash": payload.content_hash, "status": status})
            if status == "SEND_TO_USER_INBOX" or (status == "PUBLISH_COMPLETE" and state.mode == "draft"):
                checkpoint = self._state(payload, "manual_action", previous=state, poll_count=state.poll_count + 1)
                return OperationResult(outcome="definite_failure", checkpoint=checkpoint, visibility_state="manual_action",
                    remote_refs={"share_id": state.share_id}, error_code="MANUAL_ACTION_REQUIRED",
                    safe_error_message="Finish this draft in the TikTok app. Inbox delivery is not public publication.",
                    provider_request_id=response.request_id)
            if status == "FAILED":
                checkpoint = self._state(payload, "failed", previous=state, poll_count=state.poll_count + 1)
                return OperationResult(outcome="definite_failure", checkpoint=checkpoint, remote_refs={"share_id": state.share_id},
                    error_code="PROVIDER_PUBLISH_FAILED", provider_request_id=response.request_id,
                    safe_error_message="TikTok reports that this publishing task failed; review before retrying.")
            if status in {"PROCESSING_DOWNLOAD", "PUBLISH_COMPLETE"} and not post_ids:
                return self._processing(checkpoint)
            return self._failure(TikTokHTTPFailure("PUBLICATION_PROOF_INVALID", ambiguous=True), checkpoint)
        except TikTokHTTPFailure as error:
            if error.code == "RATE_LIMITED":
                retry_at = self._future_retry_at(error)
                if retry_at is None:
                    return OperationResult(outcome="definite_failure", checkpoint=checkpoint,
                        remote_refs={"share_id": state.share_id}, error_code="STATUS_RETRY_DELAY_UNVERIFIED",
                        http_status=error.http_status, provider_code=error.provider_code,
                        safe_error_message="TikTok status is rate limited without a usable future retry time. Review the retained task.")
                return self._processing(checkpoint, code="RATE_LIMITED").model_copy(update={
                    "next_action_at": max(self.now() + timedelta(seconds=180), retry_at),
                    "remote_refs": {"share_id": state.share_id}})
            if error.code in {"AUTHORIZATION_REQUIRED", "PERMISSION_DENIED"}:
                return self._failure(error, checkpoint)
            return self._processing(checkpoint, code="PUBLICATION_LOOKUP_UNAVAILABLE")
        except (ValueError, TypeError):
            return self._failure(TikTokHTTPFailure("PUBLICATION_PROOF_INVALID", ambiguous=True), checkpoint)

    async def reconcile(self, payload, checkpoint, attempt, credential, media_access):
        try:
            state = self._checkpoint(payload, checkpoint)
            material = self._material(payload, credential)
        except (ValueError, TypeError, TikTokHTTPFailure):
            return ReconciliationResult(outcome="unknown", evidence={"code": "RECONCILIATION_MATERIAL_UNAVAILABLE"})
        if state is None or state.share_id is None:
            # An acknowledgement lost before share_id is durable cannot be
            # recovered by caption searches or another submission.
            return ReconciliationResult(outcome="unknown", evidence={"code": "NO_DURABLE_TIKTOK_TASK_ID"})
        result = await self._status(payload, state, material)
        if result.visibility_state == "public":
            return ReconciliationResult(outcome="confirmed_published", result=result,
                evidence={"share_id": state.share_id, "public_post_ids": result.remote_refs["post_ids"]})
        if result.outcome == "processing":
            return ReconciliationResult(outcome="still_processing", result=result, next_action_at=result.next_action_at,
                evidence={"share_id": state.share_id, "code": "REMOTE_TASK_PENDING"})
        # FAILED is terminal for this task. It does not authorize an automatic
        # resubmission of the original intent or clear its durable history.
        return ReconciliationResult(outcome="unknown", result=result,
            evidence={"share_id": state.share_id, "code": result.error_code or "PUBLICATION_NOT_PROVEN"})

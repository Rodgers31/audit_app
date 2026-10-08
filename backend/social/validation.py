"""Resolve the exact selected accounts and inspected assets; no network fetches."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from collections.abc import Mapping

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .contracts import (CapabilitySet, InspectedAsset, PostDocument, ResolvedPostPayload, ScheduleTime, TargetValidation, ValidationIssue, ValidationResult, canonical_hash)
from .models import SocialAccount, SocialMediaAsset


def issue(code, field, message):
    return ValidationIssue(code=code, field=field, message=message)


def registered_capability(account: SocialAccount, available_adapters) -> CapabilitySet:
    if isinstance(available_adapters, Mapping):
        adapter = available_adapters.get((account.platform, account.api_product))
        if adapter is None:
            return CapabilitySet()
        try:
            return CapabilitySet.model_validate(adapter.capabilities({
                'platform': account.platform, 'api_product': account.api_product,
                'external_account_id': account.external_account_id, 'connection_state': account.connection_state,
                'granted_scopes': account.granted_scopes, 'capability_snapshot': account.capability_snapshot,
            }))
        except (ValueError, TypeError):
            return CapabilitySet()
    return CapabilitySet()


def capability_for(account: SocialAccount, available_adapters=frozenset()) -> CapabilitySet:
    if isinstance(available_adapters, Mapping):
        caps = registered_capability(account, available_adapters)
        try:
            stored = CapabilitySet.model_validate(account.capability_snapshot)
        except (ValueError, TypeError):
            return CapabilitySet()
        # Registry presence cannot silently upgrade a legacy connected account.
        # A provider-verified reconnect persists the native capability snapshot.
        if (not stored.eligible or not stored.adapter_available
                or stored.provider_api_version != caps.provider_api_version
                or stored.rules_version != caps.rules_version
                or stored.supported_formats != caps.supported_formats
                or stored.required_scopes != caps.required_scopes
                or stored.granted_scopes != caps.granted_scopes
                or stored.limits != caps.limits
                or stored.feature_states.get('publishing') != 'supported'
                or stored.price_class != 'free'):
            return caps.model_copy(update={'eligible':False,'adapter_available':False,
                'feature_states':{**caps.feature_states,'publishing':'requires_review'}})
        return caps
    try:
        caps = CapabilitySet.model_validate(account.capability_snapshot)
    except (ValidationError, TypeError):
        return CapabilitySet()
    return caps.model_copy(update={"adapter_available": account.platform in available_adapters and caps.adapter_available})


def resolve_fields(document, target):
    result = document.master.model_dump(mode="json")
    for key in ("text", "link", "hashtags", "media"):
        override = getattr(target.overrides, key)
        if override is not None:
            result[key] = override.model_dump(mode="json")["value"]
    return result


def all_asset_ids(document):
    ids = set()
    for media in [document.master.media, *(t.overrides.media.value for t in document.targets if t.overrides.media is not None)]:
        for ref in media:
            ids.add(ref.asset_id)
            if ref.caption_asset_id:
                ids.add(ref.caption_asset_id)
    return ids


def validate_document(db: Session, document: PostDocument, evidence, available_adapters=frozenset()):
    account_ids = [t.account_id for t in document.targets]
    accounts = {a.id: a for a in db.scalars(select(SocialAccount).where(SocialAccount.id.in_(account_ids)))} if account_ids else {}
    asset_ids = all_asset_ids(document)
    assets = {a.id: a for a in db.scalars(select(SocialMediaAsset).where(SocialMediaAsset.id.in_(asset_ids)))} if asset_ids else {}
    results = []
    for target in document.targets:
        errors, warnings = [], []
        account = accounts.get(target.account_id)
        if account is None:
            results.append(TargetValidation(account_id=target.account_id, valid=False, errors=(issue("ACCOUNT_UNAVAILABLE", "account_id", "This selected account is not connected. Remove it or connect an eligible account."),)))
            continue
        caps = capability_for(account, available_adapters)
        if account.connection_state != "connected" or not account.publishing_enabled or account.hold_reason:
            errors.append(issue("ACCOUNT_UNAVAILABLE", "account_id", "Reconnect or enable this account before publishing."))
        if not caps.eligible or caps.feature_states.get("publishing") not in {"supported", "paid"}:
            errors.append(issue("ACCOUNT_UNAVAILABLE", "capabilities", "Publishing eligibility has not been verified for this account."))
        if not set(caps.required_scopes).issubset(set(account.granted_scopes or [])):
            errors.append(issue("ACCOUNT_UNAVAILABLE", "scopes", "The connected account is missing a required publishing permission."))
        if not caps.adapter_available:
            errors.append(issue("ADAPTER_NOT_AVAILABLE", "platform", "This platform adapter is not enabled in this batch."))
        if target.format not in caps.supported_formats:
            errors.append(issue("UNSUPPORTED_FORMAT", "format", "Choose a format explicitly supported by this account."))
        fields = resolve_fields(document, target)
        media = fields["media"]
        if not fields["text"].strip() and not fields["link"] and not media:
            errors.append(issue("EMPTY_CONTENT", "text", "Add text, a link or ready media before publishing."))
        if target.format == "text" and media:
            errors.append(issue("FORMAT_MEDIA_MISMATCH", "media", "Text format cannot contain media."))
        if target.format == "image" and len(media) != 1:
            errors.append(issue("FORMAT_MEDIA_MISMATCH", "media", "Image format requires exactly one ready image."))
        if target.format == "carousel" and len(media) < 2:
            errors.append(issue("FORMAT_MEDIA_MISMATCH", "media", "Carousel format requires at least two ready assets."))
        if target.format in {"video", "reel"} and len(media) != 1:
            errors.append(issue("FORMAT_MEDIA_MISMATCH", "media", "Video format requires exactly one ready video."))
        for limit, value, field in (("max_text_length", len(fields["text"]), "text"), ("max_hashtags", len(fields["hashtags"]), "hashtags"), ("max_media_count", len(media), "media")):
            maximum = caps.limits.get(limit)
            if maximum is not None and value > maximum:
                errors.append(issue("LIMIT_EXCEEDED", field, f"This value exceeds the verified account limit of {maximum}."))
        inspected = []
        for index, reference in enumerate(media):
            from uuid import UUID
            asset = assets.get(UUID(reference["asset_id"]))
            path = f"media.{index}"
            if not asset or asset.state != "ready" or asset.deleted_at is not None:
                errors.append(issue("MEDIA_NOT_READY", path, "This asset has not completed server inspection."))
                continue
            if target.format == "image" and not (asset.mime_type or "").startswith("image/"):
                errors.append(issue("FORMAT_MEDIA_MISMATCH", path, "Image format requires an inspected image."))
            if target.format in {"video", "reel"} and not (asset.mime_type or "").startswith("video/"):
                errors.append(issue("FORMAT_MEDIA_MISMATCH", path, "Video format requires an inspected video."))
            caption_id = UUID(reference["caption_asset_id"]) if reference.get("caption_asset_id") else None
            caption = assets.get(caption_id) if caption_id else None
            if caption_id and (not caption or caption.state != "ready" or caption.deleted_at is not None):
                errors.append(issue("MEDIA_NOT_READY", path + ".caption_asset_id", "The caption asset is not ready."))
                continue
            try:
                inspected.append(InspectedAsset(asset_id=asset.id, sha256=asset.sha256, mime_type=asset.mime_type, byte_size=asset.byte_size, width=asset.width, height=asset.height, duration_ms=asset.duration_ms, alt_text=reference.get("alt_text") if reference.get("alt_text") is not None else asset.default_alt_text, caption_asset_id=caption_id, caption_sha256=caption.sha256 if caption else None))
            except ValidationError:
                errors.append(issue("MEDIA_NOT_READY", path, "The inspected asset metadata is incomplete."))
                continue
            if (asset.mime_type or "").startswith("image/") and not inspected[-1].alt_text:
                warnings.append(issue("ALT_TEXT_MISSING", path + ".alt_text", "Add an image description for accessibility."))
        payload = dict(schema_version=1, account_id=str(account.id), platform=account.platform, api_product=account.api_product, external_account_id=account.external_account_id, format=target.format, text=fields["text"], link=fields["link"], hashtags=fields["hashtags"], assets=[a.model_dump(mode="json") for a in inspected], visibility="public", disclosures=[], capability_version=caps.rules_version, evidence_hash=canonical_hash(evidence))
        try:
            preview = ResolvedPostPayload(**payload, content_hash=canonical_hash(payload))
        except ValidationError:
            preview = None
            errors.append(issue("ACCOUNT_UNAVAILABLE", "account_id", "The stored account metadata needs repair."))
        if preview is not None and isinstance(available_adapters, Mapping):
            adapter = available_adapters.get((account.platform, account.api_product))
            if adapter is not None:
                try:
                    native = ValidationResult.model_validate(adapter.validate(preview, caps))
                    native_errors = [*native.errors, *(error for result in native.targets for error in result.errors)]
                    if (not native.valid or any(not result.valid for result in native.targets)) and not native_errors:
                        native_errors.append(issue('TARGET_VALIDATION_FAILED', 'format', 'This provider could not validate the selected content.'))
                    errors.extend(native_errors)
                    warnings.extend(native.warnings)
                    warnings.extend(warning for result in native.targets for warning in result.warnings)
                except (ValueError, TypeError):
                    errors.append(issue('TARGET_VALIDATION_FAILED', 'format', 'This provider could not validate the selected content.'))
        results.append(TargetValidation(account_id=account.id, platform=account.platform, valid=not errors, errors=tuple(errors), warnings=tuple(warnings), resolved_preview=preview))
    errors = () if account_ids else (issue("NO_TARGETS", "targets", "Select at least one connected account before publication."),)
    return ValidationResult(valid=bool(account_ids) and all(r.valid for r in results), targets=tuple(results), errors=errors)


def resolve_schedule(schedule: ScheduleTime, now: datetime) -> datetime:
    """Round trips both folds; chosen offset is required, including ambiguous time."""
    try:
        civil = datetime.fromisoformat(schedule.local_time)
        if civil.tzinfo is not None:
            raise ValueError("local_time must be a civil time without an offset")
        zone = ZoneInfo(schedule.timezone)
        candidates = []
        for fold in (0, 1):
            localized = civil.replace(tzinfo=zone, fold=fold)
            utc = localized.astimezone(timezone.utc)
            if utc.astimezone(zone).replace(tzinfo=None) == civil:
                offset = localized.strftime("%z")
                if offset[:3] + ":" + offset[3:] == schedule.utc_offset:
                    candidates.append(utc)
        if not candidates:
            raise ValueError("The civil time does not exist or the selected UTC offset is incorrect")
        value = candidates[0]
        if value <= now:
            raise ValueError("Choose a future schedule time")
        return value
    except (ValueError, ZoneInfoNotFoundError, OverflowError) as exc:
        raise ValueError("Choose a valid future civil time, IANA timezone and matching UTC offset") from exc

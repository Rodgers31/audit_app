"""Pure native Meta capability/content rules shared with delivery adapters.

These validators construct no HTTP client, transport, storage or worker material.
Account admission still compares these current rules with persisted native proof.
"""
from datetime import datetime, timezone
import re

from ..contracts import CapabilitySet, ResolvedPostPayload, ValidationIssue, ValidationResult, canonical_hash
from .meta_http import remote_id


def caption(payload, *, include_link=True):
    parts = [payload.text]
    if payload.hashtags:
        parts.append(" ".join(tag if tag.startswith("#") else "#" + tag for tag in payload.hashtags))
    if include_link and payload.link:
        parts.append(payload.link)
    return "\n\n".join(part for part in parts if part)


def issue(code, field, message):
    return ValidationIssue(code=code, field=field, message=message)


class MetaValidation:
    platform = ""
    product = ""
    checkpoint_name = ""
    formats = ()
    scopes = ()
    source_links = ()
    limits = {}
    phases = {}

    def __init__(self, config):
        self.config = config

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


class FacebookPageValidation(MetaValidation):
    platform = "facebook"
    product = "facebook_pages"
    checkpoint_name = "facebook_pages-v1"
    formats = ("text", "image")
    scopes = ("pages_manage_posts", "pages_read_engagement", "pages_show_list")
    source_links = ("https://developers.facebook.com/docs/graph-api/reference/v26.0/page/feed",
                    "https://developers.facebook.com/docs/graph-api/reference/photo/",
                    "https://developers.facebook.com/documentation/pages-api/posts")
    limits = {"max_text_length": 20000, "max_hashtags": 50, "max_media_count": 1,
              "max_image_bytes": 8000000, "max_alt_text_length": 2000}
    phases = {"upload_uncertain": set(), "photo_uploaded": {"photo_id"},
              "publication_uncertain": {"photo_id"}, "post_created": {"photo_id", "post_id"}}

    def _content_errors(self, payload):
        errors = []
        rendered = caption(payload, include_link=payload.format == "image")
        if not rendered.strip() and not payload.link:
            errors.append(issue("FACEBOOK_MESSAGE_REQUIRED", "text", "Add a nonblank caption or link for this Page feed publishing slice."))
        if len(rendered) > 20000:
            errors.append(issue("CAPTION_TOO_LONG", "text", "The full Page message exceeds the application's 20000 character ceiling."))
        if len(payload.hashtags) > 50:
            errors.append(issue("TOO_MANY_HASHTAGS", "hashtags", "The separate Page hashtag list exceeds the application's 50-tag ceiling."))
        for asset in payload.assets:
            if asset.mime_type not in {"image/jpeg", "image/png"} or asset.duration_ms is not None:
                errors.append(issue("UNSUPPORTED_IMAGE_TYPE", "assets", "Select one inspected static JPEG or PNG."))
            if asset.byte_size > 8000000:
                errors.append(issue("IMAGE_TOO_LARGE", "assets", "The image exceeds the application's 8000000 byte ceiling."))
            if asset.width is None or asset.height is None:
                errors.append(issue("MEDIA_DIMENSIONS_REQUIRED", "assets", "The image needs inspected dimensions."))
            if asset.alt_text is not None and len(asset.alt_text) > 2000:
                errors.append(issue("ALT_TEXT_TOO_LONG", "assets", "The image description exceeds the application's 2000 character ceiling."))
        return errors


class InstagramFacebookLoginValidation(MetaValidation):
    platform = "instagram"
    product = "instagram_graph_facebook_login"
    checkpoint_name = "instagram_facebook_login-v1"
    formats = ("image",)
    scopes = ("instagram_basic", "instagram_content_publish", "pages_read_engagement", "pages_show_list")
    source_links = ("https://developers.facebook.com/documentation/instagram-platform/content-publishing",
        "https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user/media",
        "https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-container")
    limits = {"max_text_length": 2200, "max_hashtags": 30, "max_media_count": 1,
        "max_image_bytes": 8000000, "min_image_width": 320, "max_image_width": 1440,
        "max_alt_text_length": 1000, "max_mentions": 20, "max_publications_24h": 100,
        "max_containers_24h": 400}
    phases = {"creation_uncertain": set(), "quota_checked": set(), "container_created": {"container_id"},
        "container_ready": {"container_id"}, "publish_ready": {"container_id"},
        "publication_uncertain": {"container_id"}, "media_created": {"container_id", "media_id"}}

    def _content_errors(self, payload):
        errors = []
        rendered = caption(payload)
        if len(rendered) > 2200:
            errors.append(issue("CAPTION_TOO_LONG", "text", "The full Instagram caption exceeds 2200 characters."))
        if len(re.findall(r"(?<!\w)#\w+", rendered)) > 30:
            errors.append(issue("TOO_MANY_HASHTAGS", "hashtags", "The full caption exceeds 30 hashtags."))
        if len(re.findall(r"(?<![\w@])@[A-Za-z0-9_.]+", rendered)) > 20:
            errors.append(issue("TOO_MANY_MENTIONS", "text", "The full caption exceeds 20 mentions."))
        for asset in payload.assets:
            if asset.mime_type != "image/jpeg" or asset.duration_ms is not None:
                errors.append(issue("UNSUPPORTED_IMAGE_TYPE", "assets", "Instagram requires one inspected static JPEG."))
            if asset.byte_size > 8000000:
                errors.append(issue("IMAGE_TOO_LARGE", "assets", "The JPEG exceeds the 8000000 byte application ceiling."))
            if asset.width is None or asset.height is None:
                errors.append(issue("MEDIA_DIMENSIONS_REQUIRED", "assets", "The JPEG needs inspected dimensions."))
            elif not (320 <= asset.width <= 1440 and 5 * asset.width >= 4 * asset.height and 100 * asset.width <= 191 * asset.height):
                errors.append(issue("INSTAGRAM_IMAGE_DIMENSIONS", "assets", "Use width 320–1440 and aspect ratio 4:5–1.91:1 for this slice."))
            if asset.alt_text is not None and len(asset.alt_text) > 1000:
                errors.append(issue("ALT_TEXT_TOO_LONG", "assets", "Instagram image descriptions are limited to 1000 characters."))
        return errors

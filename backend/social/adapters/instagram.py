"""Instagram Facebook Login single JPEG flow; no ambiguous publish replay."""
from __future__ import annotations

from datetime import timedelta
import re
from urllib.parse import urlsplit

from ..contracts import OperationResult, ReconciliationResult, canonical_hash
from ..worker.materials import ProviderFetchURL
from .common import MetaAdapter, caption, issue, public_url
from .meta_http import MetaHTTPFailure, remote_id


class InstagramFacebookLoginAdapter(MetaAdapter):
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

    def next_operation(self, payload, checkpoint):
        state = self._checkpoint(payload, checkpoint)
        if state is None or state.phase in {"container_created", "container_ready", "media_created", "creation_uncertain", "publication_uncertain"}:
            return self._plan("poll", checkpoint)
        if state.phase == "quota_checked":
            return self._plan("create_container", checkpoint)
        if state.phase == "publish_ready":
            return self._plan("publish", checkpoint)
        raise ValueError("Unsupported Instagram checkpoint phase")

    async def execute(self, payload, operation, credential, media_access):
        try:
            material, state = self._admission(payload, operation, credential)
        except MetaHTTPFailure as error:
            return self._failure(error, operation.checkpoint)
        if operation.operation == "poll":
            if state is None or state.phase == "container_ready":
                return await self._quota(payload, state, material)
            if state.phase == "media_created":
                return await self._media(payload, state, material)
            if state.phase in {"container_created", "publication_uncertain"}:
                return await self._container(payload, state, material)
            return self._failure(MetaHTTPFailure("CONTAINER_IDENTITY_REQUIRED", ambiguous=True), operation.checkpoint)
        checkpoint = operation.checkpoint
        if operation.operation == "create_container":
            try:
                if media_access is None:
                    raise MetaHTTPFailure("MEDIA_ACCESS_UNAVAILABLE", retry_safe=True)
                asset = payload.assets[0]
                access = await media_access.provider_fetch_url(asset, 120)
                if not isinstance(access, ProviderFetchURL) or access.asset_id != asset.asset_id or access.sha256 != asset.sha256 or access.expires_at.tzinfo is None or access.expires_at.utcoffset() is None or access.expires_at < self.now() + timedelta(seconds=120):
                    raise MetaHTTPFailure("INSPECTED_MEDIA_CHANGED", retry_safe=True)
                parsed = urlsplit(access.url)
                if not isinstance(access.url, str) or len(access.url) > 8000 or not access.url.isascii() or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in access.url) or parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or "\\" in access.url:
                    raise MetaHTTPFailure("MEDIA_ACCESS_UNAVAILABLE", retry_safe=True)
            except MetaHTTPFailure as error:
                return self._failure(error, checkpoint)
            except Exception:
                return self._failure(MetaHTTPFailure("MEDIA_ACCESS_UNAVAILABLE", retry_safe=True), checkpoint)
            uncertain = self._state(payload, "creation_uncertain")
            try:
                response = await self.http.request("POST", payload.external_account_id, token=material.page_access_token,
                    edge="media", data={"image_url": access.url, "caption": caption(payload), "alt_text": asset.alt_text or ""})
                container_id = remote_id(response.value.get("id"))
                checkpoint = self._state(payload, "container_created", container_id=container_id)
                return self._success(checkpoint, response)
            except MetaHTTPFailure as error:
                return self._failure(error, uncertain if error.ambiguous else checkpoint)
            except (ValueError, TypeError):
                return self._failure(MetaHTTPFailure("PROVIDER_OUTCOME_UNCERTAIN", ambiguous=True), uncertain)
        if operation.operation == "publish":
            uncertain = self._state(payload, "publication_uncertain", previous=state)
            try:
                response = await self.http.request("POST", payload.external_account_id, token=material.page_access_token,
                    edge="media_publish", data={"creation_id": state.container_id})
                media_id = remote_id(response.value.get("id"))
                if media_id == state.container_id:
                    raise ValueError("A container identity is not a published media identity")
                checkpoint = self._state(payload, "media_created", previous=state, media_id=media_id)
                return self._success(checkpoint, response)
            except MetaHTTPFailure as error:
                return self._failure(error, uncertain if error.ambiguous else checkpoint)
            except (ValueError, TypeError):
                return self._failure(MetaHTTPFailure("PROVIDER_OUTCOME_UNCERTAIN", ambiguous=True), uncertain)
        raise ValueError("Unsupported Instagram operation")

    async def _quota(self, payload, state, material):
        checkpoint = state.model_dump(mode="json", exclude_none=True) if state else {}
        try:
            response = await self.http.request("GET", payload.external_account_id, token=material.page_access_token,
                edge="content_publishing_limit", fields="quota_usage,config")
            rows = response.value.get("data")
            if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or "paging" in response.value:
                raise ValueError("Invalid quota response")
            usage = rows[0].get("quota_usage")
            total = 100
            if "config" in rows[0]:
                config = rows[0]["config"]
                if not isinstance(config, dict) or type(config.get("quota_total")) is not int or not 1 <= config["quota_total"] <= 100 or type(config.get("quota_duration")) is not int or config["quota_duration"] != 86400:
                    raise ValueError("Invalid quota configuration")
                total = config["quota_total"]
            if type(usage) is not int or not 0 <= usage <= 1000000:
                raise ValueError("Invalid quota count")
            if usage >= total:
                return OperationResult(outcome="definite_failure", error_code="RATE_LIMITED", retry_safe=True,
                    checkpoint=checkpoint, next_action_at=self.now() + timedelta(hours=1), http_status=response.http_status)
            checkpoint = self._state(payload, "publish_ready" if state else "quota_checked", previous=state)
            return self._success(checkpoint, response)
        except MetaHTTPFailure as error:
            if not error.ambiguous:
                return self._failure(error, checkpoint)
            return self._processing(checkpoint, code="QUOTA_LOOKUP_UNAVAILABLE")
        except (ValueError, TypeError):
            return self._processing(checkpoint, code="QUOTA_PROOF_INVALID")

    async def _container(self, payload, state, material):
        checkpoint = state.model_dump(mode="json", exclude_none=True)
        if state.poll_count >= 5:
            return self._failure(MetaHTTPFailure("CONTAINER_READ_LIMIT", ambiguous=True), checkpoint)
        checkpoint = self._state(payload, state.phase, previous=state, poll_count=state.poll_count + 1)
        try:
            response = await self.http.request("GET", state.container_id, token=material.page_access_token, fields="id,status_code")
            status = response.value.get("status_code")
            if response.value.get("id") != state.container_id or status not in {"EXPIRED", "ERROR", "FINISHED", "IN_PROGRESS", "PUBLISHED"}:
                raise ValueError("Container status identity was not verified")
            if status == "IN_PROGRESS":
                return self._processing(checkpoint)
            if state.phase == "publication_uncertain" or status == "PUBLISHED":
                checkpoint = self._state(payload, "publication_uncertain", previous=state, poll_count=state.poll_count + 1)
                return OperationResult(outcome="ambiguous", checkpoint=checkpoint, remote_refs={"container_id": state.container_id},
                    http_status=response.http_status, error_code="FINAL_MEDIA_IDENTITY_UNAVAILABLE" if status == "PUBLISHED" else "NO_PROVIDER_COMPLETE_ABSENCE_PROOF",
                    receipt={"container_status": status})
            if status == "FINISHED":
                checkpoint = self._state(payload, "container_ready", previous=state)
                return self._success(checkpoint, response)
            return OperationResult(outcome="definite_failure", checkpoint=checkpoint, error_code="CONTAINER_PROCESSING_FAILED",
                                   http_status=response.http_status, remote_refs={"container_id": state.container_id})
        except MetaHTTPFailure as error:
            if not error.ambiguous and error.code in {"TOKEN_REVOKED", "PERMISSION_DENIED"}:
                return self._failure(error, checkpoint)
            return self._processing(checkpoint, code="CONTAINER_LOOKUP_UNAVAILABLE")
        except (ValueError, TypeError):
            return self._failure(MetaHTTPFailure("CONTAINER_PROOF_INVALID", ambiguous=True), checkpoint)

    async def _media(self, payload, state, material):
        checkpoint = state.model_dump(mode="json", exclude_none=True)
        if state.poll_count >= 5:
            return self._failure(MetaHTTPFailure("PUBLICATION_VERIFICATION_REQUIRED", ambiguous=True), checkpoint)
        checkpoint = self._state(payload, state.phase, previous=state, poll_count=state.poll_count + 1)
        try:
            response = await self.http.request("GET", state.media_id, token=material.page_access_token,
                fields="id,owner{id},media_type,media_product_type,permalink,shortcode,caption")
            value = response.value
            if value.get("id") != state.media_id or not isinstance(value.get("owner"), dict) or value["owner"].get("id") != payload.external_account_id or value.get("media_type") != "IMAGE" or value.get("media_product_type") != "FEED" or value.get("caption", "") != caption(payload):
                raise ValueError("Published media ownership or content was not verified")
            url = public_url(value.get("permalink"), "instagram")
            shortcode = value.get("shortcode")
            if not isinstance(shortcode, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", shortcode) or urlsplit(url).path != "/p/" + shortcode + "/":
                raise ValueError("Permalink does not identify the media")
            return OperationResult(outcome="confirmed_success", primary_remote_id=state.media_id, remote_url=url,
                visibility_state="public", confirmation_kind="instagram_owned_feed_image_read",
                checkpoint=checkpoint, remote_refs={"container_id": state.container_id, "media_id": state.media_id},
                http_status=response.http_status, receipt={"provider_api_version": self.config.graph_version,
                    "owner_verified": True, "content_hash": payload.content_hash})
        except MetaHTTPFailure as error:
            if not error.ambiguous and error.code in {"TOKEN_REVOKED", "PERMISSION_DENIED"}:
                return self._failure(error, checkpoint)
            return self._processing(checkpoint, code="PUBLICATION_LOOKUP_UNAVAILABLE")
        except (ValueError, TypeError):
            return self._failure(MetaHTTPFailure("PUBLICATION_PROOF_INVALID", ambiguous=True), checkpoint)

    async def reconcile(self, payload, checkpoint, attempt, credential, media_access):
        try:
            material = self._material(payload, credential)
            state = self._checkpoint(payload, checkpoint)
            if canonical_hash(payload.model_dump(mode="json", exclude={"content_hash"})) != payload.content_hash:
                raise ValueError("Invalid immutable payload")
        except (MetaHTTPFailure, ValueError, TypeError):
            return ReconciliationResult(outcome="unknown", evidence={"code": "RECONCILIATION_MATERIAL_UNAVAILABLE"})
        if state and state.phase == "media_created":
            result = await self._media(payload, state, material)
            if result.visibility_state == "public":
                return ReconciliationResult(outcome="confirmed_published", result=result,
                    evidence={"container_id": state.container_id, "media_id": state.media_id, "owner_verified": True})
        elif state and state.container_id and attempt and attempt.get("operation") in {"publish", "create_container"}:
            if attempt.get("operation") == "publish":
                uncertain = self._state(payload, "publication_uncertain", previous=state, poll_count=state.poll_count)
                state = self._checkpoint(payload, uncertain)
            result = await self._container(payload, state, material)
        else:
            return ReconciliationResult(outcome="unknown", evidence={"code": "NO_PROVIDER_COMPLETE_PUBLICATION_PROOF"})
        if result.outcome in {"processing", "confirmed_success"}:
            return ReconciliationResult(outcome="still_processing", result=result, next_action_at=result.next_action_at,
                evidence={"code": "KNOWN_REMOTE_OPERATION_PENDING"})
        return ReconciliationResult(outcome="unknown", result=result, evidence={"code": result.error_code or "PUBLICATION_PROOF_UNAVAILABLE"})

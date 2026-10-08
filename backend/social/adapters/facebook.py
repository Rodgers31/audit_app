"""Facebook Page text and single static image publishing with durable IDs."""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from ..contracts import OperationResult, ReconciliationResult, canonical_hash
from .common import MetaAdapter, caption, issue, public_url, verify_bytes
from .meta_http import MetaHTTPFailure, remote_id


class FacebookPageAdapter(MetaAdapter):
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

    def next_operation(self, payload, checkpoint):
        state = self._checkpoint(payload, checkpoint)
        if state is None:
            return self._plan("upload" if payload.format == "image" else "publish", checkpoint)
        if state.phase == "photo_uploaded":
            return self._plan("publish", checkpoint)
        if state.phase in {"post_created", "publication_uncertain", "upload_uncertain"}:
            return self._plan("poll", checkpoint)
        raise ValueError("Unsupported Facebook checkpoint phase")

    async def execute(self, payload, operation, credential, media_access):
        try:
            material, state = self._admission(payload, operation, credential)
        except MetaHTTPFailure as error:
            return self._failure(error, operation.checkpoint)
        if operation.operation == "poll":
            return await self._poll(payload, state, material)
        checkpoint = operation.checkpoint
        if operation.operation == "upload":
            try:
                if media_access is None:
                    raise MetaHTTPFailure("MEDIA_ACCESS_UNAVAILABLE", retry_safe=True)
                asset = payload.assets[0]
                value = verify_bytes(asset, await media_access.read_bytes(asset, 8000000), 8000000)
            except MetaHTTPFailure as error:
                return self._failure(error, checkpoint)
            except Exception:
                return self._failure(MetaHTTPFailure("MEDIA_ACCESS_UNAVAILABLE", retry_safe=True), checkpoint)
            uncertain = self._state(payload, "upload_uncertain")
            try:
                response = await self.http.request("POST", material.page_id, token=material.page_access_token,
                    edge="photos", data={"published": "false", "alt_text_custom": asset.alt_text or ""},
                    files={"source": ("inspected.jpg" if asset.mime_type == "image/jpeg" else "inspected.png", value, asset.mime_type)})
                photo_id = remote_id(response.value.get("id"))
                photo_post_id = None
                if "post_id" in response.value:
                    photo_post_id = remote_id(response.value["post_id"], composite=True)
                    if not photo_post_id.startswith(material.page_id + "_"):
                        raise ValueError("Photo belongs to another Page")
                checkpoint = self._state(payload, "photo_uploaded", photo_id=photo_id,
                                         **({"photo_post_id": photo_post_id} if photo_post_id else {}))
                return self._success(checkpoint, response)
            except MetaHTTPFailure as error:
                return self._failure(error, uncertain if error.ambiguous else checkpoint)
            except (ValueError, TypeError):
                return self._failure(MetaHTTPFailure("PROVIDER_OUTCOME_UNCERTAIN", ambiguous=True), uncertain)
        if operation.operation == "publish":
            data = {"message": caption(payload, include_link=payload.format == "image"), "published": "true"}
            if payload.format == "image":
                data["attached_media"] = json.dumps([{"media_fbid": state.photo_id}], separators=(",", ":"))
            elif payload.link:
                data["link"] = payload.link
            uncertain = self._state(payload, "publication_uncertain", previous=state)
            try:
                response = await self.http.request("POST", material.page_id, token=material.page_access_token, edge="feed", data=data)
                post_id = remote_id(response.value.get("id"), composite=True)
                if not post_id.startswith(material.page_id + "_"):
                    raise ValueError("Post belongs to another Page")
                checkpoint = self._state(payload, "post_created", previous=state, post_id=post_id)
                return self._success(checkpoint, response)
            except MetaHTTPFailure as error:
                return self._failure(error, uncertain if error.ambiguous else checkpoint)
            except (ValueError, TypeError):
                return self._failure(MetaHTTPFailure("PROVIDER_OUTCOME_UNCERTAIN", ambiguous=True), uncertain)
        raise ValueError("Unsupported Facebook operation")

    async def _poll(self, payload, state, material):
        checkpoint = state.model_dump(mode="json", exclude_none=True) if state else {}
        if state is None or state.phase != "post_created" or state.poll_count >= 5:
            return self._failure(MetaHTTPFailure("PUBLICATION_VERIFICATION_REQUIRED", ambiguous=True), checkpoint)
        checkpoint = self._state(payload, state.phase, previous=state, poll_count=state.poll_count + 1)
        try:
            response = await self.http.request("GET", state.post_id, token=material.page_access_token,
                fields="id,from{id},is_published,is_hidden,privacy,permalink_url,message,link,attachments{target{id}}")
            value = response.value
            if value.get("id") != state.post_id or not isinstance(value.get("from"), dict) or value["from"].get("id") != material.page_id:
                raise ValueError("Post identity was not verified")
            if value.get("is_published") is not True or value.get("is_hidden") is not False or not isinstance(value.get("privacy"), dict) or value["privacy"].get("value") != "EVERYONE":
                return self._processing(checkpoint, code="PUBLIC_VISIBILITY_UNCONFIRMED")
            if value.get("message", "") != caption(payload, include_link=payload.format == "image"):
                raise ValueError("Published message differs from authorized content")
            if payload.format == "text" and payload.link and value.get("link") != payload.link:
                raise ValueError("Published link differs from authorized content")
            if state.photo_id:
                attachments = value.get("attachments")
                if not isinstance(attachments, dict) or not isinstance(attachments.get("data"), list) or len(attachments["data"]) != 1 or not isinstance(attachments["data"][0], dict) or attachments["data"][0].get("target", {}).get("id") != state.photo_id:
                    raise ValueError("Uploaded photo was not verified in the post")
            url = public_url(value.get("permalink_url"), "facebook")
            parsed = urlsplit(url)
            post_part = state.post_id.split("_")[1]
            query = parse_qs(parsed.query)
            segments = parsed.path.strip("/").split("/")
            canonical_path = (segments == [state.post_id] or
                segments in ([material.page_id, "posts", post_part],
                             [material.page_id, "posts", state.post_id]))
            canonical_query = (parsed.path in {"/permalink.php", "/story.php"} and
                set(query) == {"story_fbid", "id"} and
                query.get("story_fbid") == [post_part] and query.get("id") == [material.page_id])
            if not ((canonical_path and not query) or canonical_query):
                raise ValueError("Permalink does not identify the post")
            return OperationResult(outcome="confirmed_success", primary_remote_id=state.post_id, remote_url=url,
                visibility_state="public", confirmation_kind="facebook_owned_public_post_read",
                checkpoint=checkpoint, remote_refs={"post_id": state.post_id, **({"photo_id": state.photo_id} if state.photo_id else {})},
                http_status=response.http_status, receipt={"provider_api_version": self.config.graph_version,
                    "owner_verified": True, "content_hash": payload.content_hash})
        except MetaHTTPFailure as error:
            if error.code in {"TOKEN_REVOKED", "TOKEN_EXPIRED", "PERMISSION_DENIED", "AUTHORIZATION_REQUIRED"}:
                return self._failure(error, checkpoint)
            return self._processing(checkpoint, code="PUBLICATION_LOOKUP_UNAVAILABLE")
        except (ValueError, TypeError, AttributeError):
            return self._failure(MetaHTTPFailure("PUBLICATION_PROOF_INVALID", ambiguous=True), checkpoint)

    async def reconcile(self, payload, checkpoint, attempt, credential, media_access):
        try:
            material = self._material(payload, credential)
            state = self._checkpoint(payload, checkpoint)
            if canonical_hash(payload.model_dump(mode="json", exclude={"content_hash"})) != payload.content_hash:
                raise ValueError("Invalid immutable payload")
        except (MetaHTTPFailure, ValueError, TypeError):
            return ReconciliationResult(outcome="unknown", evidence={"code": "RECONCILIATION_MATERIAL_UNAVAILABLE"})
        if state and state.phase == "post_created":
            result = await self._poll(payload, state, material)
            if result.visibility_state == "public":
                return ReconciliationResult(outcome="confirmed_published", result=result,
                    evidence={"post_id": state.post_id, "owner_verified": True})
            if result.outcome == "processing":
                return ReconciliationResult(outcome="still_processing", result=result, next_action_at=result.next_action_at,
                                            evidence={"post_id": state.post_id, "code": "PUBLICATION_READ_PENDING"})
            return ReconciliationResult(outcome="unknown", result=result, evidence={"code": "PUBLICATION_PROOF_UNAVAILABLE"})
        if state and state.phase == "photo_uploaded" and attempt and attempt.get("operation") == "upload" and state.poll_count < 5:
            saved = self._state(payload, state.phase, previous=state, poll_count=state.poll_count + 1)
            try:
                response = await self.http.request("GET", state.photo_id, token=material.page_access_token, fields="id,from{id}")
                value = response.value
                if value.get("id") != state.photo_id or not isinstance(value.get("from"), dict) or value["from"].get("id") != material.page_id:
                    raise ValueError("Uploaded photo ownership was not verified")
                result = self._success(saved, response)
                return ReconciliationResult(outcome="still_processing", result=result,
                    evidence={"photo_id": state.photo_id, "upload_verified": True})
            except (MetaHTTPFailure, ValueError, TypeError):
                return ReconciliationResult(outcome="unknown", evidence={"code": "UPLOAD_PROOF_UNAVAILABLE"})
        # A bounded/ranked feed or unknown photo upload has no complete absence
        # guarantee. Missing post identity never authorizes another publication.
        return ReconciliationResult(outcome="unknown", evidence={"code": "NO_PROVIDER_COMPLETE_PUBLICATION_PROOF"})

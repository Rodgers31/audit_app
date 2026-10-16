"""Sanitized Accounts API v1.3 fixtures; no real provider requests."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import pytest

from social.adapters.tiktok import (TikTokAccountsAdapter, TikTokAdapterConfig,
    TikTokCreatorSettings, verified_fetch_url)
from social.adapters.tiktok_http import TikTokHTTPFailure
from social.adapters.tiktok_oauth import TikTokAccountsOAuth, TikTokOAuthConfig
from social.contracts import InspectedAsset, ResolvedPostPayload, TikTokPostOptions, canonical_hash
from social.native_admission import NativeCapabilityAdmission
from social.worker.materials import ProviderFetchURL, WorkerCredentialMaterial

NOW = datetime(2026, 10, 16, 20, tzinfo=timezone.utc)
TOKEN = "private-tiktok-fixture-token"
ORIGIN = "https://owned.example/tiktok/"
FETCH = ORIGIN + "video.mp4?signature=private-fetch-fixture"
SETTINGS = dict(privacy_level_options=["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"],
    comment_disabled=False, duet_disabled=False, stitch_disabled=False, max_video_post_duration_sec=600)


def run(awaitable):
    return asyncio.run(awaitable)


def rehash(payload):
    return payload.model_copy(update={"content_hash": canonical_hash(payload.model_dump(mode="json", exclude={"content_hash"}))})


def payload(format="video", mode="direct", **option_changes):
    settings = TikTokCreatorSettings(**SETTINGS)
    options = dict(mode=mode, privacy_level="PUBLIC_TO_EVERYONE", upload_consent=True, music_usage_confirmed=True,
        creator_settings_checked_at=NOW, creator_settings_hash=settings.bound_hash("owned-account-fixture"))
    options.update(option_changes)
    asset = InspectedAsset(asset_id=uuid4(), sha256="a" * 64, mime_type="video/mp4" if format == "video" else "image/jpeg",
        byte_size=15000, width=1080, height=1920, duration_ms=10000 if format == "video" else None,
        frame_rate_milli_fps=30000 if format == "video" else None)
    return rehash(ResolvedPostPayload(account_id=uuid4(), platform="tiktok", api_product="tiktok_accounts_api",
        external_account_id="owned-account-fixture", format=format, text="A reviewed caption", hashtags=("AuditGava",),
        assets=(asset, asset.model_copy(update={"asset_id": uuid4()})) if format == "carousel" else (asset,),
        tiktok_options=TikTokPostOptions(**options), evidence_hash="b" * 64, content_hash="0" * 64))


class Provider:
    def __init__(self):
        self.calls = []
        self.settings = dict(SETTINGS)
        self.status = "PUBLISH_COMPLETE"
        self.post_ids = ["7123456789012345678"]
        self.timeout_mutation = False
        self.override = None

    async def __call__(self, request):
        body = await request.aread()
        self.calls.append((request.method, request.url.path, json.loads(body) if body else parse_qs(request.url.query.decode())))
        assert request.url.host == "business-api.tiktok.com"
        assert request.headers["Access-Token"] == TOKEN
        if self.override is not None:
            return self.override(request)
        if request.url.path.endswith("/business/video/settings/"):
            data = self.settings
        elif request.url.path.endswith(("/business/video/publish/", "/business/photo/publish/")):
            if self.timeout_mutation:
                raise httpx.ReadTimeout(TOKEN + " " + FETCH, request=request)
            data = {"share_id": "v_pub_url~v1.123456789"}
        elif request.url.path.endswith("/business/publish/status/"):
            data = {"status": self.status}
            if self.post_ids is not None:
                data["post_ids"] = self.post_ids
        else:
            raise AssertionError("Unexpected provider request")
        return httpx.Response(200, json={"code": 0, "message": "OK", "request_id": "fixture-request-1", "data": data})


class Media:
    def __init__(self):
        self.calls = []
        self.changes = {}

    async def provider_fetch_url(self, asset, minimum_ttl_seconds):
        self.calls.append((asset.asset_id, minimum_ttl_seconds))
        return replace(ProviderFetchURL(FETCH, NOW + timedelta(seconds=1800), asset.asset_id, asset.sha256), **self.changes)


def adapter(provider, **config):
    values = dict(enabled=True, operational_gates_verified=True, product_access_verified=True)
    values.update(config)
    return TikTokAccountsAdapter(TikTokAdapterConfig(**values), transport=httpx.MockTransport(provider), now=lambda: NOW)


def account(value, *, scopes=("video.publish", "video.upload")):
    return {"platform": "tiktok", "api_product": value.api_product, "connection_state": "connected",
        "granted_scopes": scopes, "tiktok_product_approved": True}


def material(value, provider, **changes):
    scopes = changes.pop("granted_scopes", ("video.publish", "video.upload"))
    caps = provider.capabilities(account(value, scopes=scopes))
    return replace(WorkerCredentialMaterial(value.account_id, uuid4(), 1, "tiktok", value.api_product,
        value.external_account_id, value.external_account_id, TOKEN, scopes, NOW + timedelta(hours=1), None,
        NativeCapabilityAdmission.from_snapshot(caps), tiktok_product_approved=True,
        tiktok_verified_origins=(ORIGIN,)), **changes)


async def checked(provider, value, graph):
    operation = provider.next_operation(value, {})
    result = await provider.execute(value, operation, material(value, provider), Media())
    assert result.outcome == "confirmed_success"
    return result.checkpoint


async def submitted(provider, value, graph, media=None):
    checkpoint = await checked(provider, value, graph)
    operation = provider.next_operation(value, checkpoint)
    result = await provider.execute(value, operation, material(value, provider), media or Media())
    assert result.outcome == "processing"
    return result.checkpoint


def test_default_closed_tiktok_product_gate():
    assert TikTokAdapterConfig().ready is False
    for config in ({"enabled": True}, {"operational_gates_verified": True}, {"product_access_verified": True}):
        assert not TikTokAdapterConfig(**config).ready
    for config in ({"enabled": "true"}, {"product_access_verified": 1}, {"api_version": "v2"}):
        with pytest.raises(ValueError):
            TikTokAdapterConfig(**config)


@pytest.mark.parametrize("format,mode,operation", [("video", "direct", "publish"), ("video", "draft", "upload"),
    ("image", "direct", "publish"), ("carousel", "direct", "publish"), ("image", "draft", "upload")])
def test_full_chain_survives_restart_after_every_boundary(format, mode, operation):
    async def exercise():
        value, graph, media = payload(format, mode), Provider(), Media()
        checkpoint = {}
        if mode == "draft":
            graph.status, graph.post_ids = "SEND_TO_USER_INBOX", None
        for expected in ("poll", operation, "poll"):
            provider = adapter(graph)
            assert provider.validate(value, provider.capabilities(account(value))).valid
            plan = provider.next_operation(value, checkpoint)
            assert plan.operation == expected
            assert plan.publication_capable is (expected == "publish")
            assert plan.safe_replay_class == ("read_only" if expected == "poll" else "requires_reconciliation")
            result = await provider.execute(value, plan, material(value, provider), media)
            checkpoint = json.loads(json.dumps(result.checkpoint))
            await provider.close()
        mutations = [call for call in graph.calls if call[0] == "POST"]
        assert len(mutations) == 1
        body = mutations[0][2]
        assert body["business_id"] == value.external_account_id
        assert body["post_info"]["disable_comment"] is True
        if format == "video":
            assert body["post_info"]["upload_to_draft"] is (mode == "draft")
            assert body["post_info"]["disable_duet"] is True
        else:
            assert body["post_info"]["is_draft"] is (mode == "draft")
            assert body["post_info"]["privacy_level"] == "PUBLIC_TO_EVERYONE"
            assert body["post_info"]["auto_add_music"] is False
        if mode == "draft":
            assert result.visibility_state == "manual_action" and result.error_code == "MANUAL_ACTION_REQUIRED"
            assert result.primary_remote_id is None
        else:
            assert result.visibility_state == "public" and result.primary_remote_id == graph.post_ids[0]
            assert result.confirmation_kind == "tiktok_accounts_public_status_post_ids"
            assert result.remote_url is None  # No fabricated permalink.
        assert all(ttl == 1800 for _, ttl in media.calls)
        encoded = json.dumps(checkpoint)
        assert TOKEN not in encoded and FETCH not in encoded and "signature" not in encoded
    run(exercise())


@pytest.mark.parametrize("options,code", [({"upload_consent": False}, "UPLOAD_CONSENT_REQUIRED"),
    ({"music_usage_confirmed": False}, "UPLOAD_CONSENT_REQUIRED"),
    ({"privacy_level": "SELF_ONLY"}, "PUBLIC_VISIBILITY_REQUIRED"),
    ({"commercial_content": True}, "DISCLOSURE_SELECTION_REQUIRED"),
    ({"is_brand_organic": True}, "DISCLOSURE_SELECTION_REQUIRED"),
    ({"commercial_content": True, "is_branded_content": True}, "BRANDED_CONTENT_POLICY_REQUIRED")])
def test_explicit_privacy_consent_and_disclosure_validation(options, code):
    value, graph = payload(**options), Provider()
    provider = adapter(graph)
    validation = provider.validate(value, provider.capabilities(account(value)))
    assert not validation.valid and code in {error.code for error in validation.errors}
    assert not graph.calls
    run(provider.close())


@pytest.mark.parametrize("asset_change,code", [({"frame_rate_milli_fps": None}, "INVALID_VIDEO_FRAME_RATE"),
    ({"frame_rate_milli_fps": 22999}, "INVALID_VIDEO_FRAME_RATE"), ({"frame_rate_milli_fps": 60001}, "INVALID_VIDEO_FRAME_RATE"),
    ({"duration_ms": 600001}, "INVALID_VIDEO"), ({"width": 359}, "INVALID_VIDEO_DIMENSIONS"),
    ({"alt_text": "silently discarded alt text"}, "UNSUPPORTED_ACCESSIBILITY_METADATA")])
def test_actual_inspected_video_limits(asset_change, code):
    value, graph = payload(), Provider()
    value = rehash(value.model_copy(update={"assets": (value.assets[0].model_copy(update=asset_change),)}))
    provider = adapter(graph)
    validation = provider.validate(value, provider.capabilities(account(value)))
    assert code in {error.code for error in validation.errors}
    run(provider.close())


def test_utf16_limits_and_draft_metadata_are_not_silently_dropped():
    graph = Provider()
    provider = adapter(graph)
    value = rehash(payload().model_copy(update={"text": "😀" * 1101, "hashtags": ()}))
    assert "CAPTION_TOO_LONG" in {e.code for e in provider.validate(value, provider.capabilities(account(value))).errors}
    value = payload("image", photo_title="😀" * 46)
    assert "TITLE_TOO_LONG" in {e.code for e in provider.validate(value, provider.capabilities(account(value))).errors}
    value = payload(mode="draft", is_ai_generated=True)
    assert "DRAFT_METADATA_IGNORED" in {e.code for e in provider.validate(value, provider.capabilities(account(value))).errors}
    run(provider.close())


@pytest.mark.parametrize("changes", [{"tiktok_product_approved": False}, {"tiktok_verified_origins": ()},
    {"account_id": uuid4()}, {"page_id": "other-owner"}, {"credential_version": True},
    {"access_expires_at": NOW}, {"access_expires_at": None}, {"access_expires_at": NOW.replace(tzinfo=None)},
    {"capability_admission": None}, {"granted_scopes": ("video.upload",)}])
def test_every_mutation_rechecks_material_and_approval(changes):
    async def exercise():
        value, graph = payload(), Provider()
        provider = adapter(graph)
        checkpoint = await checked(provider, value, graph)
        plan = provider.next_operation(value, checkpoint)
        result = await provider.execute(value, plan, material(value, provider, **changes), Media())
        assert result.outcome == "definite_failure"
        assert not any(call[0] == "POST" for call in graph.calls)
        await provider.close()
    run(exercise())


@pytest.mark.parametrize("changes", [{"asset_id": uuid4()}, {"sha256": "b" * 64},
    {"expires_at": NOW + timedelta(seconds=1799)}, {"expires_at": NOW.replace(tzinfo=None)},
    {"url": "https://owned.example.evil/tiktok/video.mp4"}, {"url": "https://owned.example/elsewhere/video.mp4"},
    {"url": "https://owned.example/tiktok/%2e%2e/private.mp4"}, {"url": "https://owned.example/tiktok/../private.mp4"},
    {"url": "https://owned.example:8443/tiktok/video.mp4"}, {"url": "https://private@owned.example/tiktok/video.mp4"}])
def test_inspected_media_must_match_provider_verified_origin_and_binding(changes):
    async def exercise():
        value, graph, media = payload(), Provider(), Media()
        provider = adapter(graph)
        checkpoint = await checked(provider, value, graph)
        media.changes = changes
        result = await provider.execute(value, provider.next_operation(value, checkpoint), material(value, provider), media)
        assert result.error_code == "MEDIA_ACCESS_UNAVAILABLE"
        assert not any(call[0] == "POST" for call in graph.calls)
        await provider.close()
    run(exercise())


@pytest.mark.parametrize("setting,choice", [({"comment_disabled": True}, {"disable_comment": False}),
    ({"max_video_post_duration_sec": 3}, {}),
    ({}, {"creator_settings_checked_at": NOW + timedelta(seconds=1)})])
def test_current_settings_and_account_duration_restrict_before_mutation(setting, choice):
    async def exercise():
        value, graph = payload(**choice), Provider()
        graph.settings.update(setting)
        provider = adapter(graph)
        result = await provider.execute(value, provider.next_operation(value, {}), material(value, provider), Media())
        assert result.outcome == "definite_failure"
        assert result.error_code in {"CREATOR_SETTINGS_CHANGED", "CREATOR_DURATION_EXCEEDED"}
        assert not any(call[0] == "POST" for call in graph.calls)
        await provider.close()
    run(exercise())


def test_approved_draft_only_permission_cannot_direct_publish():
    value, graph = payload(mode="draft"), Provider()
    provider = adapter(graph)
    caps = provider.capabilities(account(value, scopes=("video.upload",)))
    assert caps.eligible and provider.validate(value, caps).valid
    direct = rehash(value.model_copy(update={"tiktok_options": value.tiktok_options.model_copy(update={"mode": "direct"})}))
    assert "PERMISSION_DENIED" in {e.code for e in provider.validate(direct, caps).errors}
    run(provider.close())


def test_lost_ack_never_resubmits_or_invents_absence_proof():
    async def exercise():
        value, graph = payload(), Provider()
        provider = adapter(graph)
        checkpoint = await checked(provider, value, graph)
        graph.timeout_mutation = True
        result = await provider.execute(value, provider.next_operation(value, checkpoint), material(value, provider), Media())
        assert result.outcome == "ambiguous" and result.checkpoint["phase"] == "submission_uncertain"
        assert TOKEN not in str(result.model_dump()) and FETCH not in str(result.model_dump())
        recovered = adapter(graph)
        reconciliation = await recovered.reconcile(value, result.checkpoint, {"operation": "publish"}, material(value, recovered), None)
        assert reconciliation.outcome == "unknown" and reconciliation.absence_proof is None
        again = await recovered.execute(value, recovered.next_operation(value, result.checkpoint), material(value, recovered), None)
        assert again.outcome == "ambiguous"
        assert len([call for call in graph.calls if call[0] == "POST"]) == 1
        await provider.close()
        await recovered.close()
    run(exercise())


@pytest.mark.parametrize("status,post_ids,expected", [("PUBLISH_COMPLETE", None, "still_processing"),
    ("PUBLISH_COMPLETE", [], "still_processing"), ("PROCESSING_DOWNLOAD", None, "still_processing"),
    ("FAILED", None, "unknown"), ("made-up-success", ["123"], "unknown"),
    ("PUBLISH_COMPLETE", {"id": "123"}, "unknown"), ("PUBLISH_COMPLETE", [True], "unknown")])
def test_processing_without_public_post_ids_is_not_public(status, post_ids, expected):
    async def exercise():
        value, graph = payload(), Provider()
        provider = adapter(graph)
        checkpoint = await submitted(provider, value, graph)
        graph.status, graph.post_ids = status, post_ids
        result = await provider.reconcile(value, checkpoint, {"operation": "publish"}, material(value, provider), None)
        assert result.outcome == expected and result.absence_proof is None
        if result.result:
            assert result.result.visibility_state != "public"
        await provider.close()
    run(exercise())


def test_unapproved_product_blocks_recovery_and_retains_exact_task():
    async def exercise():
        value, graph = payload(), Provider()
        provider = adapter(graph)
        checkpoint = await submitted(provider, value, graph)
        recovery = adapter(graph, enabled=False, product_access_verified=False)
        credential = material(value, provider, tiktok_product_approved=False, capability_admission=None)
        result = await recovery.reconcile(value, checkpoint, {"operation": "publish"}, credential, None)
        assert result.outcome == "unknown"
        assert not any(call[1].endswith('/business/publish/status/') for call in graph.calls)
        other = payload()
        bad = await recovery.reconcile(other, checkpoint, None, credential, None)
        assert bad.outcome == "unknown"
        assert len([call for call in graph.calls if call[0] == "POST"]) == 1
        await recovery.close()
        await provider.close()
    run(exercise())


def test_default_gate_refuses_every_initial_entry_without_network():
    async def exercise():
        value, graph = payload(), Provider()
        provider = adapter(graph, enabled=False)
        assert not provider.validate(value, provider.capabilities(account(value))).valid
        assert not provider.validate_mutation_admission(value, account(value)).valid
        result = await provider.execute(value, provider.next_operation(value, {}), material(value, provider), Media())
        assert result.error_code == "ACCOUNT_INELIGIBLE" and graph.calls == []
        await provider.close()
    run(exercise())


def oauth_config(**changes):
    values = dict(client_id="fixture-app", client_secret="fixture-client-secret", redirect_uri="https://app.example/callback/",
        authorization_url="https://www.tiktok.com/v2/auth/authorize?client_key=fixture-app&scope=video.publish&redirect_uri=https%3A%2F%2Fapp.example%2Fcallback%2F",
        product_access_verified=True)
    values.update(changes)
    return TikTokOAuthConfig(**values)


def test_oauth_uses_console_url_and_requires_opaque_durable_state():
    config = oauth_config()
    parsed = parse_qs(config.begin_url("a" * 43).split("?", 1)[1])
    assert parsed["state"] == ["a" * 43] and parsed["disable_auto_auth"] == ["1"]
    assert parsed["scope"] == ["video.publish"]
    with pytest.raises(ValueError):
        oauth_config(product_access_verified=False).begin_url("a" * 43)
    for value in ("short", "http://state.invalid/", "\n" * 40):
        with pytest.raises(ValueError):
            config.begin_url(value)
    for redirect in ("https://app.example/callback", "http://app.example/callback/", "https://app.example:443/callback/", "https://app.example/callback/?a=1"):
        with pytest.raises(ValueError):
            oauth_config(redirect_uri=redirect)


def test_oauth_exact_exchange_refresh_and_returned_rotation_are_not_logged():
    async def exercise():
        calls = []
        async def transport(request):
            body = json.loads(await request.aread())
            calls.append((request.url.path, body))
            return httpx.Response(200, json={"code": 0, "request_id": "oauth-request-1", "data": {
                "open_id": "owned-account-fixture", "access_token": "new-fixture-access", "refresh_token": "rotated-fixture-refresh",
                "scope": "video.publish,video.upload", "token_type": "Bearer", "expires_in": 3400, "refresh_token_expires_in": 20000}})
        oauth = TikTokAccountsOAuth(oauth_config(), transport=httpx.MockTransport(transport), now=lambda: NOW)
        grant = await oauth.exchange("one-use-fixture-code")
        assert calls[0][0].endswith("/tt_user/oauth2/token/")
        assert calls[0][1]["auth_code"] == "one-use-fixture-code" and calls[0][1]["redirect_uri"].endswith("/callback/")
        assert grant.access_expires_at == NOW + timedelta(seconds=3400)
        rotated = await oauth.refresh("prior-fixture-refresh", expected_open_id=grant.open_id)
        assert calls[1][0].endswith("/tt_user/oauth2/refresh_token/")
        assert calls[1][1]["grant_type"] == "refresh_token"
        assert rotated.credential_bundle()["refresh_token"] == "rotated-fixture-refresh"
        assert "new-fixture-access" not in repr(grant) and "rotated-fixture-refresh" not in repr(grant)
        with pytest.raises(TikTokHTTPFailure, match="TOKEN_GRANT_UNCERTAIN"):
            await oauth.refresh("prior-fixture-refresh", expected_open_id="different-owner")
        await oauth.close()
    run(exercise())


@pytest.mark.parametrize("data", [
    {"code": 0, "data": {"share_id": "bad\nsecret"}},
    {"code": True, "data": {"share_id": "123"}},
    {"code": 1234, "data": {"share_id": "v_pub_url~v1.123"}},
])
def test_malformed_mutation_ack_remains_ambiguous(data):
    async def exercise():
        value, graph = payload(), Provider()
        provider = adapter(graph)
        checkpoint = await checked(provider, value, graph)
        graph.override = lambda request: httpx.Response(200, json=data)
        result = await provider.execute(value, provider.next_operation(value, checkpoint), material(value, provider), Media())
        assert result.outcome == "ambiguous" and result.checkpoint["phase"] == "submission_uncertain"
        assert "bad\nsecret" not in str(result.model_dump())
        await provider.close()
    run(exercise())


@pytest.mark.parametrize("kind", ["redirect", "duplicate", "oversize", "server_error", "compressed"])
def test_http_boundary_does_not_replay_or_accept_ambiguous_mutation(kind):
    async def exercise():
        value, graph = payload(), Provider()
        provider = adapter(graph)
        checkpoint = await checked(provider, value, graph)
        def override(request):
            if kind == "redirect":
                return httpx.Response(307, headers={"Location": "https://other.invalid/"}, json={"code": 0, "data": {}})
            if kind == "duplicate":
                return httpx.Response(200, content=b'{"code":0,"code":0,"data":{"share_id":"123"}}')
            if kind == "oversize":
                return httpx.Response(200, content=b'{"code":0,"data":{"padding":"' + b'x' * 66000 + b'"}}')
            if kind == "compressed":
                return httpx.Response(200, headers={"content-encoding": "gzip"}, content=b'not-a-compressed-provider-response')
            return httpx.Response(500, json={"code": 50000, "message": TOKEN, "data": {}})
        graph.override = override
        result = await provider.execute(value, provider.next_operation(value, checkpoint), material(value, provider), Media())
        assert result.outcome == "ambiguous"
        assert len([call for call in graph.calls if call[0] == "POST"]) == 1
        assert TOKEN not in str(result.model_dump())
        await provider.close()
    run(exercise())


def test_explicit_rate_rejection_preserves_exact_retry_after_without_wire_retry():
    async def exercise():
        value, graph = payload(), Provider()
        provider = adapter(graph)
        checkpoint = await checked(provider, value, graph)
        graph.override = lambda request: httpx.Response(429, headers={"retry-after": "4000"}, json={"code": 42900, "data": {}})
        result = await provider.execute(value, provider.next_operation(value, checkpoint), material(value, provider), Media())
        assert result.outcome == "definite_failure" and result.error_code == "RATE_LIMITED" and result.retry_safe
        assert result.next_action_at == NOW + timedelta(seconds=4000)
        assert result.checkpoint == checkpoint
        assert len([call for call in graph.calls if call[0] == "POST"]) == 1
        await provider.close()
    run(exercise())


def test_cross_payload_checkpoint_and_forged_operation_cannot_dispatch():
    async def exercise():
        value, graph = payload(), Provider()
        provider = adapter(graph)
        checkpoint = await checked(provider, value, graph)
        changed = rehash(value.model_copy(update={"text": "Unapproved changed caption"}))
        with pytest.raises(ValueError):
            provider.next_operation(changed, checkpoint)
        plan = provider.next_operation(value, checkpoint)
        for changes in ({"operation": "upload"}, {"publication_capable": False}, {"safe_replay_class": "safe"}):
            with pytest.raises(ValueError):
                await provider.execute(value, plan.model_copy(update=changes), material(value, provider), Media())
        assert not any(call[0] == "POST" for call in graph.calls)
        await provider.close()
    run(exercise())


def test_bounded_status_polls_exhaust_to_unknown_without_mutation():
    async def exercise():
        value, graph = payload(), Provider()
        provider = adapter(graph)
        checkpoint = await submitted(provider, value, graph)
        checkpoint["poll_count"] = 20
        result = await provider.reconcile(value, checkpoint, None, material(value, provider), None)
        assert result.outcome == "unknown"
        assert len(graph.calls) == 2  # Settings + one mutation only.
        await provider.close()
    run(exercise())


@pytest.mark.parametrize("field,value", [("expires_in", True), ("expires_in", 0), ("expires_in", 86401),
    ("refresh_token_expires_in", 31536001), ("token_type", "MAC"), ("scope", "video.publish,video.publish"),
    ("scope", "video.publish secret"), ("refresh_token", "bad\nmaterial")])
def test_unusable_rotated_grant_is_never_a_safe_retry(field, value):
    async def exercise():
        calls = []
        async def transport(request):
            calls.append(request.url.path)
            data = dict(open_id="owned-account-fixture", access_token="new-fixture-access", refresh_token="new-fixture-refresh",
                token_type="Bearer", scope="video.publish", expires_in=86400, refresh_token_expires_in=31536000)
            data[field] = value
            return httpx.Response(200, json={"code": 0, "data": data})
        oauth = TikTokAccountsOAuth(oauth_config(), transport=httpx.MockTransport(transport), now=lambda: NOW)
        with pytest.raises(TikTokHTTPFailure) as caught:
            await oauth.refresh("old-fixture-refresh", expected_open_id="owned-account-fixture")
        assert caught.value.ambiguous and caught.value.code == "TOKEN_GRANT_UNCERTAIN"
        assert len(calls) == 1
        await oauth.close()
    run(exercise())


def test_mutation_rejects_an_old_capability_rule_even_with_valid_payload_hash():
    async def exercise():
        value, graph = payload(), Provider()
        value = rehash(value.model_copy(update={"capability_version": "retired-rules"}))
        provider = adapter(graph)
        checkpoint = await checked(provider, value, graph)
        result = await provider.execute(value, provider.next_operation(value, checkpoint), material(value, provider), Media())
        assert result.error_code == "ACCOUNT_INELIGIBLE"
        assert not any(call[0] == "POST" for call in graph.calls)
        await provider.close()
    run(exercise())


def test_delayed_authorized_choices_revalidate_current_settings_before_dispatch():
    async def exercise():
        value, graph = payload(creator_settings_checked_at=NOW - timedelta(hours=3)), Provider()
        provider = adapter(graph)
        checkpoint = await checked(provider, value, graph)
        assert checkpoint['checked_at'] == NOW.isoformat().replace('+00:00', 'Z')
        result = await provider.execute(value, provider.next_operation(value, checkpoint), material(value, provider), Media())
        assert result.outcome == 'processing'
        assert [method for method, _, _ in graph.calls] == ['GET', 'POST']
        await provider.close()
    run(exercise())


def test_stale_dispatch_settings_checkpoint_still_blocks_media_send():
    async def exercise():
        value, graph = payload(creator_settings_checked_at=NOW - timedelta(hours=3)), Provider()
        provider = adapter(graph)
        checkpoint = await checked(provider, value, graph)
        checkpoint['checked_at'] = (NOW - timedelta(seconds=301)).isoformat()
        result = await provider.execute(value, provider.next_operation(value, checkpoint), material(value, provider), Media())
        assert result.error_code == 'CREATOR_SETTINGS_CHANGED'
        assert not any(method == 'POST' for method, _, _ in graph.calls)
        await provider.close()
    run(exercise())


def test_oauth_console_url_requires_exact_static_callback_for_ui_launch():
    with pytest.raises(ValueError,match='redirect mismatch'):
        oauth_config(authorization_url='https://www.tiktok.com/v2/auth/authorize?client_key=fixture-app&scope=video.publish')


@pytest.mark.parametrize('header,expected', [
    ('1000000', NOW + timedelta(seconds=1000000)),
    ('Wed, 21 Oct 2026 20:00:00 GMT', NOW + timedelta(days=5)),
    (None, None), ('', None), ('invalid', None), ('-10', None), ('0', None),
    ('9999999999999999999', None), ('Fri, 16 Oct 2026 19:59:00 GMT', None),
    ('Wed, 21 Oct 2026 20:00:00', None),
])
def test_tiktok_retry_after_never_authorizes_earlier_retry(header, expected):
    async def exercise():
        from social.worker.policy import retry_decision
        value, graph = payload(), Provider()
        provider = adapter(graph)
        checkpoint = await checked(provider, value, graph)
        headers = {} if header is None else {'retry-after': header}
        graph.override = lambda request: httpx.Response(429, headers=headers, json={'code': 42900, 'data': {}})
        result = await provider.execute(value, provider.next_operation(value, checkpoint), material(value, provider), Media())
        assert result.next_action_at == expected
        assert result.retry_safe is (expected is not None)
        assert result.checkpoint == checkpoint
        decision = retry_decision(result, now=NOW, submit_count=1, first_started_at=NOW,
            retry_deadline=NOW + timedelta(hours=24), content_valid_until=None, random_fraction=0)
        if expected is None:
            assert decision.action == 'reconcile'
        else:
            # The provider's actual long delay exceeds the delivery lifetime;
            # worker policy blocks it rather than shortening it to an early send.
            assert decision.action == 'block' and decision.reason == 'RETRY_DEADLINE_EXCEEDED'
        assert sum(method == 'POST' for method, _, _ in graph.calls) == 1
        await provider.close()
    run(exercise())


@pytest.mark.parametrize('header,expected', [
    ('1000000', NOW + timedelta(seconds=1000000)),
    ('Wed, 21 Oct 2026 20:00:00 GMT', NOW + timedelta(days=5)),
    ('1', NOW + timedelta(seconds=180)), (None, None), ('invalid', None), ('0', None),
])
def test_tiktok_status_rate_limit_preserves_delay_and_stops_unknown_delay(header, expected):
    async def exercise():
        value, graph = payload(), Provider()
        provider = adapter(graph)
        checkpoint = await submitted(provider, value, graph)
        headers = {} if header is None else {'retry-after': header}
        graph.override = lambda request: httpx.Response(429, headers=headers, json={'code': 42900, 'data': {}})
        result = await provider.execute(value, provider.next_operation(value, checkpoint), material(value, provider), None)
        assert result.checkpoint['share_id'] == checkpoint['share_id']
        assert result.checkpoint['content_hash'] == checkpoint['content_hash']
        if expected is None:
            assert result.outcome == 'definite_failure' and result.error_code == 'STATUS_RETRY_DELAY_UNVERIFIED'
            assert result.retry_safe is False and result.next_action_at is None
        else:
            assert result.outcome == 'processing' and result.next_action_at == expected
            assert result.error_code == 'RATE_LIMITED'
        recovered = await provider.reconcile(value, checkpoint, None, material(value, provider), None)
        assert recovered.outcome == ('unknown' if expected is None else 'still_processing')
        assert recovered.next_action_at == expected
        assert sum(method == 'POST' for method, _, _ in graph.calls) == 1
        await provider.close()
    run(exercise())

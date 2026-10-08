"""Native adapter integration against injected HTTP; no real publishing calls."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import pytest

from social.adapters import FacebookPageAdapter, InstagramFacebookLoginAdapter, MetaAdapterConfig
from social.contracts import InspectedAsset, ResolvedPostPayload, canonical_hash
from social.worker.materials import ProviderFetchURL, WorkerCredentialMaterial


NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
TOKEN = "private-page-token-native-fixture"
FETCH_URL = "https://private.example/inspected.jpg?signature=private-fetch-native-fixture"
IMAGE = b"inspected-image-bytes-fixture"
SCOPES = ("pages_manage_posts", "pages_read_engagement", "pages_show_list", "instagram_basic", "instagram_content_publish")


def payload(platform="facebook", format="text", **changes):
    asset = InspectedAsset(asset_id=uuid4(), sha256=hashlib.sha256(IMAGE).hexdigest(), mime_type="image/jpeg",
                           byte_size=len(IMAGE), width=1080, height=1080, alt_text="A chart description")
    value = dict(account_id=uuid4(), platform=platform,
        api_product="facebook_pages" if platform == "facebook" else "instagram_graph_facebook_login",
        external_account_id="901" if platform == "facebook" else "801", format=format,
        text="Approved caption", hashtags=("AuditGava",), assets=(asset,) if format == "image" else (),
        evidence_hash="1" * 64, content_hash="0" * 64)
    value.update(changes)
    result = ResolvedPostPayload(**value)
    return rehash(result)


def rehash(value):
    return value.model_copy(update={"content_hash": canonical_hash(value.model_dump(mode="json", exclude={"content_hash"}))})


def credential(value):
    return WorkerCredentialMaterial(value.account_id, uuid4(), 1, value.platform, value.api_product,
        value.external_account_id, "901", TOKEN, SCOPES, NOW + timedelta(days=1), NOW + timedelta(days=1))


class Media:
    def __init__(self):
        self.calls = []
        self.body = IMAGE
        self.access_changes = {}

    async def read_bytes(self, asset, maximum_bytes):
        self.calls.append(("bytes", asset.asset_id, maximum_bytes))
        return self.body

    async def provider_fetch_url(self, asset, minimum_ttl_seconds):
        self.calls.append(("url", asset.asset_id, minimum_ttl_seconds))
        result = ProviderFetchURL(FETCH_URL, NOW + timedelta(seconds=300), asset.asset_id, asset.sha256)
        return replace(result, **self.access_changes)


class Graph:
    """Fake provider retains its state while adapter processes are replaced."""
    def __init__(self):
        self.calls = []
        self.caption = ""
        self.link = None
        self.container_status = "FINISHED"
        self.quota_usage = 0
        self.overrides = {}
        self.timeout_path = None

    async def __call__(self, request):
        body = await request.aread()
        self.calls.append((request.method, request.url.path, body))
        key = (request.method, request.url.path)
        if key in self.overrides:
            override = self.overrides[key]
            return override(request) if callable(override) else httpx.Response(200, json=override)
        assert request.url.host == "graph.facebook.com"
        assert request.headers["authorization"] == "Bearer " + TOKEN
        form = parse_qs(body.decode()) if "multipart" not in request.headers.get("content-type", "") else {}
        if key == ("POST", "/v26.0/901/photos"):
            assert b'name="published"' in body and b"false" in body and IMAGE in body
            value = {"id": "401", "post_id": "901_402"}
        elif key == ("POST", "/v26.0/901/feed"):
            self.caption = form.get("message", [""])[0]
            self.link = form.get("link", [None])[0]
            value = {"id": "901_777"}
        elif key == ("GET", "/v26.0/901_777"):
            value = {"id": "901_777", "from": {"id": "901"}, "is_published": True, "is_hidden": False,
                "privacy": {"value": "EVERYONE"}, "message": self.caption, "link": self.link,
                "permalink_url": "https://www.facebook.com/901/posts/777/", "attachments": {"data": [{"target": {"id": "401"}}]}}
        elif key == ("GET", "/v26.0/401"):
            value = {"id": "401", "from": {"id": "901"}}
        elif key == ("GET", "/v26.0/801/content_publishing_limit"):
            value = {"data": [{"quota_usage": self.quota_usage, "config": {"quota_total": 100, "quota_duration": 86400}}]}
        elif key == ("POST", "/v26.0/801/media"):
            assert form["image_url"] == [FETCH_URL]
            self.caption = form["caption"][0]
            value = {"id": "501"}
        elif key == ("GET", "/v26.0/501"):
            value = {"id": "501", "status_code": self.container_status}
        elif key == ("POST", "/v26.0/801/media_publish"):
            assert form["creation_id"] == ["501"]
            self.container_status = "PUBLISHED"
            value = {"id": "601"}
        elif key == ("GET", "/v26.0/601"):
            value = {"id": "601", "owner": {"id": "801"}, "media_type": "IMAGE", "media_product_type": "FEED",
                     "permalink": "https://www.instagram.com/p/fixture/", "shortcode": "fixture", "caption": self.caption}
        else:
            raise AssertionError("Unexpected fake Graph operation")
        if request.url.path == self.timeout_path:
            raise httpx.ReadTimeout("Private provider exception " + TOKEN + " " + FETCH_URL, request=request)
        return httpx.Response(200, json=value)


def adapter(value, graph, **config_changes):
    config = MetaAdapterConfig(graph_version="v26.0", enabled=True, operational_gates_verified=True, **config_changes)
    kind = FacebookPageAdapter if value.platform == "facebook" else InstagramFacebookLoginAdapter
    return kind(config, transport=httpx.MockTransport(graph), now=lambda: NOW)


def capabilities(provider, value):
    return provider.capabilities({"platform": value.platform, "api_product": value.api_product,
        "connection_state": "connected", "granted_scopes": SCOPES, "capability_snapshot": {"eligible": True}})


async def until_operation(provider, value, graph, media, wanted):
    checkpoint = {}
    for _ in range(12):
        plan = provider.next_operation(value, checkpoint)
        if plan.operation == wanted:
            return plan
        result = await provider.execute(value, plan, credential(value), media)
        assert result.outcome in {"confirmed_success", "processing"}
        checkpoint = json.loads(json.dumps(result.checkpoint))
    raise AssertionError("Fake flow did not reach requested operation")


@pytest.mark.asyncio
@pytest.mark.parametrize("platform,format,operations", [
    ("facebook", "text", ["publish", "poll"]),
    ("facebook", "image", ["upload", "publish", "poll"]),
    ("instagram", "image", ["poll", "create_container", "poll", "poll", "publish", "poll"]),
])
async def test_positive_baseline_survives_restart_after_every_durable_step(platform, format, operations):
    value, graph, media = payload(platform, format), Graph(), Media()
    checkpoint, observed = {}, []
    for expected in operations:
        provider = adapter(value, graph)
        assert provider.validate(value, capabilities(provider, value)).valid
        plan = provider.next_operation(value, checkpoint)
        assert plan.operation == expected
        assert plan.checkpoint == checkpoint
        assert plan.publication_capable is (expected == "publish")
        assert plan.safe_replay_class == ("read_only" if expected == "poll" else "requires_reconciliation")
        result = await provider.execute(value, plan, credential(value), media)
        if expected != operations[-1] or len(observed) != len(operations) - 1:
            assert result.visibility_state == "unknown"
            assert result.primary_remote_id is None
        checkpoint = json.loads(json.dumps(result.checkpoint))
        observed.append(expected)
        await provider.close()
    assert result.visibility_state == "public" and result.primary_remote_id and result.remote_url
    assert observed == operations
    assert sum(method == "POST" for method, _, _ in graph.calls) == (2 if format == "image" else 1)
    assert TOKEN not in json.dumps(checkpoint) and "https://" not in json.dumps(checkpoint)
    if platform == "facebook" and format == "image":
        assert checkpoint["photo_post_id"] == "901_402"
    if platform == "instagram":
        assert media.calls == [("url", value.assets[0].asset_id, 120)]


def test_default_gates_and_version_pin_cannot_enable_publication():
    value, graph = payload(), Graph()
    provider = FacebookPageAdapter(MetaAdapterConfig("v26.0"), transport=httpx.MockTransport(graph))
    assert not capabilities(provider, value).adapter_available
    assert not provider.validate(value, capabilities(provider, value)).valid
    with pytest.raises(TypeError):
        FacebookPageAdapter(MetaAdapterConfig("v26.0", True, True))
    with pytest.raises(ValueError):
        MetaAdapterConfig("v27.0", True, True)
    with pytest.raises(ValueError):
        MetaAdapterConfig("v26.0", "true", True)


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"account_id": uuid4()}, {"external_account_id": "999"}, {"page_id": "999"},
    {"credential_version": True}, {"granted_scopes": ()}, {"granted_scopes": None},
    {"granted_scopes": SCOPES + (None,)}, {"access_expires_at": NOW},
    {"data_access_expires_at": datetime(2026, 10, 9)}, {"page_access_token": "bad\nmaterial"},
])
async def test_material_mismatch_and_expiry_never_reach_http(changes):
    value, graph = payload(), Graph()
    provider = adapter(value, graph)
    result = await provider.execute(value, provider.next_operation(value, {}), replace(credential(value), **changes), Media())
    assert result.outcome == "definite_failure" and not graph.calls
    await provider.close()


@pytest.mark.parametrize("platform,format,changes,expected", [
    ("facebook", "reel", {}, "UNSUPPORTED_FORMAT"),
    ("instagram", "text", {}, "UNSUPPORTED_FORMAT"),
    ("facebook", "image", {"text": "", "hashtags": ()}, "FACEBOOK_MESSAGE_REQUIRED"),
    ("instagram", "image", {"text": "a" * 2200}, "CAPTION_TOO_LONG"),
    ("instagram", "image", {"text": " ".join("#inline" for _ in range(31))}, "TOO_MANY_HASHTAGS"),
    ("instagram", "image", {"text": " ".join("@someone" for _ in range(21))}, "TOO_MANY_MENTIONS"),
    ("facebook", "text", {"api_product": "pages_graph"}, "ACCOUNT_PRODUCT_MISMATCH"),
    ("instagram", "image", {"disclosures": ("paid_partnership",)}, "UNSUPPORTED_DISCLOSURE"),
])
def test_supported_slice_is_explicit(platform, format, changes, expected):
    value, graph = payload(platform, format, **changes), Graph()
    provider = adapter(value, graph)
    assert expected in {error.code for error in provider.validate(value, capabilities(provider, value)).errors}


def test_facebook_direct_validator_enforces_hashtag_ceiling():
    value = rehash(payload().model_copy(update={"hashtags": tuple("tag" + str(index) for index in range(51))}))
    provider = adapter(value, Graph())
    result = provider.validate(value, capabilities(provider, value))
    assert not result.valid and "TOO_MANY_HASHTAGS" in {item.code for item in result.errors}


@pytest.mark.parametrize("changes,expected", [
    ({"mime_type": "image/png"}, "UNSUPPORTED_IMAGE_TYPE"),
    ({"byte_size": 8000001}, "IMAGE_TOO_LARGE"),
    ({"width": 319}, "INSTAGRAM_IMAGE_DIMENSIONS"),
    ({"width": 1441}, "INSTAGRAM_IMAGE_DIMENSIONS"),
    ({"width": 799, "height": 1000}, "INSTAGRAM_IMAGE_DIMENSIONS"),
    ({"width": 1911, "height": 1000}, "INSTAGRAM_IMAGE_DIMENSIONS"),
    ({"width": None}, "MEDIA_DIMENSIONS_REQUIRED"),
    ({"alt_text": "a" * 1001}, "ALT_TEXT_TOO_LONG"),
    ({"caption_asset_id": uuid4()}, "UNSUPPORTED_CAPTION_ASSET"),
])
def test_instagram_media_limits_use_inspected_evidence(changes, expected):
    value = payload("instagram", "image")
    value = rehash(value.model_copy(update={"assets": (value.assets[0].model_copy(update=changes),)}))
    provider = adapter(value, Graph())
    assert expected in {error.code for error in provider.validate(value, capabilities(provider, value)).errors}


@pytest.mark.parametrize("width,height", [(800, 1000), (955, 500), (1080, 1080)])
def test_instagram_exact_ratio_boundaries_pass(width, height):
    value = payload("instagram", "image")
    value = rehash(value.model_copy(update={"assets": (value.assets[0].model_copy(update={"width": width, "height": height}),)}))
    provider = adapter(value, Graph())
    assert provider.validate(value, capabilities(provider, value)).valid


@pytest.mark.asyncio
async def test_bytes_are_rechecked_before_facebook_upload():
    value, graph, media = payload("facebook", "image"), Graph(), Media()
    media.body = b"changed"
    provider = adapter(value, graph)
    result = await provider.execute(value, provider.next_operation(value, {}), credential(value), media)
    assert result.error_code == "INSPECTED_MEDIA_CHANGED" and not graph.calls
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"sha256": "0" * 64}, {"asset_id": uuid4()}, {"expires_at": NOW + timedelta(seconds=119)},
                                     {"url": "http://private.example/image"}, {"url": "https://user:password@private.example/image"}])
async def test_scoped_instagram_url_is_fresh_bound_and_server_only(changes):
    value, graph, media = payload("instagram", "image"), Graph(), Media()
    media.access_changes = changes
    provider = adapter(value, graph)
    plan = await until_operation(provider, value, graph, media, "create_container")
    result = await provider.execute(value, plan, credential(value), media)
    assert result.outcome == "definite_failure"
    assert all(method == "GET" for method, _, _ in graph.calls)
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("platform,format,operation,path", [
    ("facebook", "text", "publish", "/v26.0/901/feed"),
    ("facebook", "image", "upload", "/v26.0/901/photos"),
    ("instagram", "image", "create_container", "/v26.0/801/media"),
    ("instagram", "image", "publish", "/v26.0/801/media_publish"),
])
async def test_accepted_mutation_timeout_never_resends(platform, format, operation, path):
    value, graph, media = payload(platform, format), Graph(), Media()
    provider = adapter(value, graph)
    plan = await until_operation(provider, value, graph, media, operation)
    graph.timeout_path = path
    result = await provider.execute(value, plan, credential(value), media)
    assert result.outcome == "ambiguous" and not result.retry_safe
    assert provider.next_operation(value, result.checkpoint).operation == "poll"
    count = sum(method == "POST" for method, _, _ in graph.calls)
    await provider.close()
    restarted = adapter(value, graph)
    reconciled = await restarted.reconcile(value, json.loads(json.dumps(result.checkpoint)), {"operation": operation}, credential(value), media)
    assert reconciled.outcome == "unknown" and reconciled.absence_proof is None
    assert sum(method == "POST" for method, _, _ in graph.calls) == count
    assert TOKEN not in repr(result) and FETCH_URL not in repr(result)
    await restarted.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["FINISHED", "PUBLISHED", "ERROR", "EXPIRED", "IN_PROGRESS"])
async def test_ambiguous_instagram_publish_status_never_authorizes_replay(status):
    value, graph, media = payload("instagram", "image"), Graph(), Media()
    provider = adapter(value, graph)
    plan = await until_operation(provider, value, graph, media, "publish")
    graph.container_status = status
    reconciliation = await provider.reconcile(value, plan.checkpoint, {"operation": "publish"}, credential(value), media)
    assert reconciliation.absence_proof is None
    if status == "IN_PROGRESS":
        assert reconciliation.outcome == "still_processing"
        assert provider.next_operation(value, reconciliation.result.checkpoint).operation == "poll"
        graph.container_status = "FINISHED"
        result = await provider.execute(value, provider.next_operation(value, reconciliation.result.checkpoint), credential(value), media)
        assert result.outcome == "ambiguous"
    else:
        assert reconciliation.outcome == "unknown"
    assert not any(path.endswith("media_publish") for _, path, _ in graph.calls)
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("platform,format", [("facebook", "text"), ("instagram", "image")])
async def test_known_final_id_reconciles_with_read_only_positive_proof(platform, format):
    value, graph, media = payload(platform, format), Graph(), Media()
    provider = adapter(value, graph)
    plan = await until_operation(provider, value, graph, media, "publish")
    submitted = await provider.execute(value, plan, credential(value), media)
    await provider.close()
    restarted = adapter(value, graph)
    count = len(graph.calls)
    recovered = await restarted.reconcile(value, json.loads(json.dumps(submitted.checkpoint)), {"operation": "publish"}, credential(value), media)
    assert recovered.outcome == "confirmed_published" and recovered.result.remote_url
    assert all(method == "GET" for method, _, _ in graph.calls[count:])
    await restarted.close()


@pytest.mark.asyncio
async def test_known_facebook_upload_reconciles_before_new_publication_step():
    value, graph, media = payload("facebook", "image"), Graph(), Media()
    provider = adapter(value, graph)
    uploaded = await provider.execute(value, provider.next_operation(value, {}), credential(value), media)
    recovered = await provider.reconcile(value, uploaded.checkpoint, {"operation": "upload"}, credential(value), media)
    assert recovered.outcome == "still_processing"
    assert provider.next_operation(value, recovered.result.checkpoint).operation == "publish"
    unsafe = await provider.reconcile(value, uploaded.checkpoint, {"operation": "publish"}, credential(value), media)
    assert unsafe.outcome == "unknown"
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code,expected,retry_safe", [(400, 190, "TOKEN_REVOKED", True), (400, 200, "PERMISSION_DENIED", True),
    (400, 324, "INVALID_MEDIA_OR_PARAMETER", True), (429, 4, "RATE_LIMITED", True),
    (500, 2, "PROVIDER_OUTCOME_UNCERTAIN", False), (400, True, "PROVIDER_OUTCOME_UNCERTAIN", False),
    (400, 10 ** 40, "PROVIDER_OUTCOME_UNCERTAIN", False)])
async def test_explicit_rejection_and_uncertain_response_are_distinct(status, code, expected, retry_safe, caplog):
    value, graph = payload(), Graph()
    graph.overrides[("POST", "/v26.0/901/feed")] = lambda request: httpx.Response(status, json={"error": {"code": code, "message": TOKEN + FETCH_URL}}, headers={"retry-after": "120"})
    provider = adapter(value, graph)
    caplog.set_level(logging.DEBUG)
    result = await provider.execute(value, provider.next_operation(value, {}), credential(value), Media())
    assert result.error_code == expected and result.retry_safe is retry_safe
    assert result.outcome == ("ambiguous" if not retry_safe else "definite_failure")
    assert TOKEN not in caplog.text and FETCH_URL not in caplog.text and TOKEN not in repr(result)
    if expected == "RATE_LIMITED":
        assert result.next_action_at == NOW + timedelta(seconds=120)
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"id": "901_777", "error": {"code": 100}}, {"id": "901_777", "error": None},
    {"id": "attacker/path"}, [], {"id": "999_777"}])
async def test_hostile_mutation_success_shape_is_uncertain(body):
    value, graph = payload(), Graph()
    graph.overrides[("POST", "/v26.0/901/feed")] = lambda request: httpx.Response(200, json=body)
    provider = adapter(value, graph)
    result = await provider.execute(value, provider.next_operation(value, {}), credential(value), Media())
    assert result.outcome == "ambiguous" and not result.retry_safe
    assert result.primary_remote_id is None
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"from": {"id": "999"}}, {"privacy": {"value": "SELF"}}, {"is_published": False},
    {"is_hidden": True}, {"message": "changed"}, {"permalink_url": "https://attacker.example/901_777"},
    {"permalink_url": "https://www.facebook.com/901/posts/999/"},
    {"permalink_url": "https://www.facebook.com/999/posts/777/"},
    {"permalink_url": "https://www.facebook.com/901/posts/prefix901_777suffix/"},
    {"permalink_url": "https://www.facebook.com/901/posts/777/?access_token=secret"}])
async def test_facebook_id_does_not_replace_publication_proof(changes):
    value, graph = payload(), Graph()
    provider = adapter(value, graph)
    submitted = await provider.execute(value, provider.next_operation(value, {}), credential(value), Media())
    graph.overrides[("GET", "/v26.0/901_777")] = {"id": "901_777", "from": {"id": "901"}, "is_published": True,
        "is_hidden": False, "privacy": {"value": "EVERYONE"}, "message": graph.caption,
        "permalink_url": "https://www.facebook.com/901/posts/777/", **changes}
    result = await provider.execute(value, provider.next_operation(value, submitted.checkpoint), credential(value), Media())
    assert result.visibility_state != "public" and result.primary_remote_id is None
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/901/posts/777/", "/901/posts/901_777/", "/901_777/",
    "/permalink.php?story_fbid=777&id=901", "/story.php?id=901&story_fbid=777"])
async def test_facebook_permalink_binds_exact_page_and_post(path):
    value, graph = payload(), Graph()
    provider = adapter(value, graph)
    submitted = await provider.execute(value, provider.next_operation(value, {}), credential(value), Media())
    graph.overrides[("GET", "/v26.0/901_777")] = {"id": "901_777", "from": {"id": "901"}, "is_published": True,
        "is_hidden": False, "privacy": {"value": "EVERYONE"}, "message": graph.caption,
        "permalink_url": "https://www.facebook.com" + path}
    result = await provider.execute(value, provider.next_operation(value, submitted.checkpoint), credential(value), Media())
    assert result.visibility_state == "public" and result.primary_remote_id == "901_777"
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"owner": {"id": "999"}}, {"media_type": "VIDEO"}, {"media_product_type": "STORY"},
    {"caption": "different"}, {"permalink": "https://attacker.example/p/fixture/"}, {"shortcode": "different"}])
async def test_instagram_requires_owned_feed_image_and_permalink(changes):
    value, graph, media = payload("instagram", "image"), Graph(), Media()
    provider = adapter(value, graph)
    plan = await until_operation(provider, value, graph, media, "publish")
    submitted = await provider.execute(value, plan, credential(value), media)
    graph.overrides[("GET", "/v26.0/601")] = {"id": "601", "owner": {"id": "801"}, "media_type": "IMAGE",
        "media_product_type": "FEED", "caption": graph.caption, "permalink": "https://www.instagram.com/p/fixture/", "shortcode": "fixture", **changes}
    result = await provider.execute(value, provider.next_operation(value, submitted.checkpoint), credential(value), media)
    assert result.outcome == "ambiguous" and result.visibility_state == "unknown"
    await provider.close()


@pytest.mark.asyncio
async def test_quota_gate_prevents_container_and_publish_without_hiding_a_read():
    value, graph, media = payload("instagram", "image"), Graph(), Media()
    graph.quota_usage = 100
    provider = adapter(value, graph)
    plan = provider.next_operation(value, {})
    assert plan.operation == "poll" and not plan.publication_capable
    result = await provider.execute(value, plan, credential(value), media)
    assert result.error_code == "RATE_LIMITED" and result.retry_safe
    assert len(graph.calls) == 1 and graph.calls[0][0] == "GET" and not media.calls
    graph.quota_usage = 0
    plan = await until_operation(provider, value, graph, media, "publish")
    state = dict(plan.checkpoint, phase="container_ready")
    graph.quota_usage = 100
    result = await provider.execute(value, provider.next_operation(value, state), credential(value), media)
    assert result.error_code == "RATE_LIMITED"
    assert not any(path.endswith("media_publish") for _, path, _ in graph.calls)
    await provider.close()


@pytest.mark.asyncio
async def test_container_reads_are_bounded_and_no_poll_is_hidden_in_a_mutation():
    value, graph, media = payload("instagram", "image"), Graph(), Media()
    provider = adapter(value, graph)
    create = await until_operation(provider, value, graph, media, "create_container")
    created = await provider.execute(value, create, credential(value), media)
    graph.container_status = "IN_PROGRESS"
    checkpoint = created.checkpoint
    for _ in range(5):
        result = await provider.execute(value, provider.next_operation(value, checkpoint), credential(value), media)
        assert result.outcome == "processing" and result.next_action_at == NOW + timedelta(seconds=60)
        checkpoint = result.checkpoint
    count = len(graph.calls)
    result = await provider.execute(value, provider.next_operation(value, checkpoint), credential(value), media)
    assert result.outcome == "ambiguous" and len(graph.calls) == count
    await provider.close()


@pytest.mark.asyncio
async def test_checkpoint_whitelist_identity_hash_and_operation_fencing():
    value, graph = payload(), Graph()
    provider = adapter(value, graph)
    plan = provider.next_operation(value, {})
    submitted = await provider.execute(value, plan, credential(value), Media())
    for changes in ({"content_hash": "2" * 64}, {"account_id": str(uuid4())}, {"access_token": TOKEN},
                    {"remote_url": FETCH_URL}, {"post_id": "../bad"}, {"poll_count": True}, {"photo_id": "401"}, {"schema_version": True}):
        with pytest.raises(ValueError):
            provider.next_operation(value, submitted.checkpoint | changes)
    changed = value.model_copy(update={"text": "not authorized"})
    result = await provider.execute(changed, plan, credential(value), Media())
    assert result.error_code == "INVALID_PUBLISHING_PAYLOAD"
    with pytest.raises(ValueError):
        await provider.execute(value, plan.model_copy(update={"publication_capable": False}), credential(value), Media())
    assert sum(method == "POST" for method, _, _ in graph.calls) == 1
    await provider.close()


@pytest.mark.asyncio
async def test_facebook_link_is_verified_and_targets_are_independent():
    graph, media = Graph(), Media()
    facebook = payload(link="https://auditgava.example/evidence")
    provider = adapter(facebook, graph)
    submitted = await provider.execute(facebook, provider.next_operation(facebook, {}), credential(facebook), media)
    verified = await provider.execute(facebook, provider.next_operation(facebook, submitted.checkpoint), credential(facebook), media)
    assert verified.visibility_state == "public"
    instagram = payload("instagram", "image")
    graph.quota_usage = 100
    ig = adapter(instagram, graph)
    failed = await ig.execute(instagram, ig.next_operation(instagram, {}), credential(instagram), media)
    assert failed.outcome == "definite_failure" and failed.error_code == "RATE_LIMITED"
    assert verified.visibility_state == "public" and verified.primary_remote_id == "901_777"
    await provider.close()
    await ig.close()


@pytest.mark.asyncio
async def test_missing_checkpoint_after_remote_acceptance_is_quarantined():
    value, graph, media = payload("instagram", "image"), Graph(), Media()
    provider = adapter(value, graph)
    plan = await until_operation(provider, value, graph, media, "publish")
    accepted = await provider.execute(value, plan, credential(value), media)
    assert accepted.checkpoint["media_id"] == "601"
    # Simulate a DB crash before persisting the mutation result. Only its
    # committed checkpoint input and original durable publish intent survive.
    recovered = await provider.reconcile(value, plan.checkpoint, {"operation": "publish"}, credential(value), media)
    assert recovered.outcome == "unknown" and recovered.absence_proof is None
    assert recovered.result.error_code == "FINAL_MEDIA_IDENTITY_UNAVAILABLE"
    assert sum(path.endswith("media_publish") for _, path, _ in graph.calls) == 1
    await provider.close()


class OversizedStream(httpx.AsyncByteStream):
    def __init__(self):
        self.yields = 0
        self.closed = False

    async def __aiter__(self):
        for _ in range(200):
            self.yields += 1
            yield b"a" * 16384

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_http_response_allocation_is_bounded_and_stream_closed():
    value, graph, stream = payload(), Graph(), OversizedStream()
    graph.overrides[("POST", "/v26.0/901/feed")] = lambda request: httpx.Response(200, stream=stream)
    provider = adapter(value, graph)
    result = await provider.execute(value, provider.next_operation(value, {}), credential(value), Media())
    assert result.outcome == "ambiguous" and stream.closed and stream.yields == 5
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("body,headers", [(b'{"id":"901_777","id":"901_888"}', {}),
    (b'{"id":"901_777","other":NaN}', {}), (b'{}', {"content-encoding": "gzip"})])
async def test_duplicate_json_nonfinite_or_compression_never_establish_success(body, headers):
    value, graph = payload(), Graph()
    graph.overrides[("POST", "/v26.0/901/feed")] = lambda request: httpx.Response(200, content=body, headers=headers)
    provider = adapter(value, graph)
    result = await provider.execute(value, provider.next_operation(value, {}), credential(value), Media())
    assert result.outcome == "ambiguous"
    await provider.close()


@pytest.mark.asyncio
async def test_server_material_repr_and_http_hooks_exclude_secret_query_values(caplog):
    value, graph = payload(), Graph()
    material = credential(value)
    provider = adapter(value, graph, app_secret="private-app-secret-native-fixture")
    urls = []
    async def hook(request):
        urls.append(str(request.url))
    provider.http.client.event_hooks["request"] = [hook]
    caplog.set_level(logging.DEBUG)
    result = await provider.execute(value, provider.next_operation(value, {}), material, Media())
    assert result.outcome == "confirmed_success"
    assert TOKEN not in repr(material)
    assert FETCH_URL not in repr(ProviderFetchURL(FETCH_URL, NOW, uuid4(), "0" * 64))
    assert "private-app-secret" not in repr(provider.config)
    assert all("appsecret_proof" not in url and TOKEN not in url for url in urls)
    assert TOKEN not in caplog.text and "private-app-secret" not in caplog.text
    await provider.close()

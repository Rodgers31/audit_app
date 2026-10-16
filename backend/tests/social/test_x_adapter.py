"""Sanitized X contracts with an explicit mock transport; no provider traffic."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid4

import httpx
import pytest

from social.adapters.x import CONTRACT, XAdapter, XAdapterConfig
from social.adapters.x_text import count_text
from social.contracts import InspectedAsset, ResolvedPostPayload, canonical_hash
from social.native_admission import NativeCapabilityAdmission
from social.worker.materials import WorkerCredentialMaterial


NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
BODY = b"sanitized-inspected-media"
SCOPES = ("tweet.read", "tweet.write", "users.read", "media.write")


def payload(format="text", **changes):
    count = 2 if format == "carousel" else 0 if format == "text" else 1
    assets = tuple(InspectedAsset(asset_id=uuid4(), sha256=hashlib.sha256(BODY).hexdigest(),
        mime_type="video/mp4" if format == "video" else "image/jpeg", byte_size=len(BODY),
        width=1080, height=1080, duration_ms=1000 if format == "video" else None,
        alt_text="County chart") for _ in range(count))
    fields = dict(account_id=uuid4(), platform="x", api_product="x_api_v2", external_account_id="901",
        format=format, text="Verified budget summary", assets=assets, evidence_hash="1" * 64, content_hash="0" * 64)
    fields.update(changes)
    value = ResolvedPostPayload(**fields)
    return value.model_copy(update={"content_hash": canonical_hash(value.model_dump(mode="json", exclude={"content_hash"}))})


def account(value):
    return dict(platform="x", api_product="x_api_v2", external_account_id=value.external_account_id,
        granted_scopes=SCOPES, connection_state="connected", capability_snapshot={"eligible": True},
        x_access_verified=True, x_budget_remaining_microusd=1_000_000)


def credential(provider, value, operation, **changes):
    caps = provider.capabilities(account(value))
    fields = dict(account_id=value.account_id, credential_id=uuid4(), credential_version=1,
        platform="x", api_product="x_api_v2", external_account_id=value.external_account_id,
        page_id=value.external_account_id, page_access_token="sanitized-fixture-user-token",
        granted_scopes=SCOPES, access_expires_at=NOW+timedelta(days=1), data_access_expires_at=None,
        capability_admission=NativeCapabilityAdmission.from_snapshot(caps), x_access_verified=True,
        x_budget_remaining_microusd=1_000_000, x_reserved_cost_microusd=operation.estimated_cost_microusd,
        x_reservation_operation_id=operation.operation_id)
    fields.update(changes)
    return WorkerCredentialMaterial(**fields)


class Media:
    def __init__(self):
        self.calls = []
        self.body = BODY

    async def read_bytes(self, asset, maximum_bytes):
        self.calls.append((asset.asset_id, maximum_bytes))
        return self.body


class Provider:
    def __init__(self):
        self.calls, self.media_ids, self.media_keys = [], [], []
        self.post_body = None
        self.timeout = None
        self.overrides = {}
        self.processing = False

    async def __call__(self, request):
        raw = await request.aread()
        self.calls.append((request.method, request.url.path, request.url.query, raw))
        key = (request.method, request.url.path)
        assert request.url.host == "api.x.com"
        assert request.headers["authorization"] == "Bearer sanitized-fixture-user-token"
        if key in self.overrides:
            response = self.overrides[key]
            return response(request) if callable(response) else httpx.Response(200, json=response)
        if key == ("POST", "/2/media/upload/initialize"):
            fields = json.loads(raw)
            assert set(fields) == {"media_type", "media_category", "total_bytes"}
            assert "command" not in fields
            media_id = str(500 + len(self.media_ids))
            media_key = "3_" + media_id
            self.media_ids.append(media_id)
            self.media_keys.append(media_key)
            value = {"data": {"id": media_id, "media_key": media_key, "expires_after_secs": 86400}}
        elif request.url.path.endswith("/append"):
            assert b'name="segment_index"' in raw and BODY in raw
            if request.url.path == self.timeout:
                raise httpx.ReadTimeout("fixture-secret-no-error-propagation", request=request)
            return httpx.Response(204)
        elif request.url.path.endswith("/finalize"):
            value = {"data": {"id": request.url.path.split("/")[-2]}}
            if self.processing:
                value["data"]["processing_info"] = {"state": "pending", "check_after_secs": 3}
        elif key == ("GET", "/2/media/upload"):
            assert request.url.params["command"] == "STATUS"
            value = {"data": {"id": request.url.params["media_id"], "processing_info": {"state": "succeeded"}}}
        elif key == ("POST", "/2/media/metadata"):
            fields = json.loads(raw)
            assert fields["metadata"] == {"alt_text": {"text": "County chart"}}
            value = {"data": {"id": fields["id"]}}
        elif key == ("POST", "/2/tweets"):
            self.post_body = json.loads(raw)
            value = {"data": {"id": "777", "text": self.post_body["text"]}}
        elif key == ("GET", "/2/tweets/777"):
            value = {"data": {"id": "777", "author_id": "901", "text": self.post_body["text"]}}
            value["includes"] = {"users": [{"id": "901", "protected": False}]}
            if self.media_keys:
                value["data"]["attachments"] = {"media_keys": self.media_keys}
        else:
            raise AssertionError("Unexpected fixture endpoint")
        if request.url.path == self.timeout:
            raise httpx.ReadTimeout("fixture-secret-no-error-propagation", request=request)
        return httpx.Response(200, json=value)


def adapter(provider, **changes):
    fields = dict(enabled=True, operational_gates_verified=True, media_uploads_enabled=True,
        media_request_cost_microusd=5_000)
    fields.update(changes)
    return XAdapter(XAdapterConfig(**fields), transport=httpx.MockTransport(provider), now=lambda: NOW)


def original_publish_attempt(value, input_checkpoint, *, when=None):
    return {"operation_id": uuid4(), "operation": "publish", "dispatch_started_at": when or NOW-timedelta(minutes=10),
        "request_fingerprint": canonical_hash({"payload_hash": value.content_hash, "operation": "publish", "checkpoint": input_checkpoint}),
        "receipt": {"intent": {"publication_capable": True, "mutating": True, "safe_replay_class": "requires_reconciliation"}}}


def own_posts(value, *, posts=None, meta=None):
    data = posts if posts is not None else [{"id": "777", "author_id": value.external_account_id,
        "text": value.text, "created_at": (NOW-timedelta(minutes=10)+timedelta(seconds=1)).isoformat().replace("+00:00", "Z")}]
    return {"data": data, "includes": {"users": [{"id": value.external_account_id, "protected": False}]},
        "meta": meta if meta is not None else {"result_count": len(data)}}


@pytest.mark.parametrize("text,expected", [
    ("a"*280, 280), ("漢"*140, 280), ("cafe\u0301", 4), ("👨‍👩‍👧‍👦", 2), ("🙋🏽", 2),
    ("🇰🇪", 2), ("1️⃣", 2), ("©", 1), ("©️", 2), ("https://example.com/a/very/long/link", 23),
    ("(https://example.com/a)", 25), ("a https://example.com", 25), ("👨‍🎤"*140, 280),
])
def test_weighted_counting(text, expected):
    assert count_text(text) == expected


@pytest.mark.parametrize("text", ["example.com", "https://user:pass@example.com", "https://☃.com", "\ud800", "\uffff",
    "https://example.com:abc", "https://example.com:0", "https://example.com\\foo", "https://%65xample.com", "https://example_.com"])
def test_unsupported_counting_is_explicit(text):
    with pytest.raises(ValueError):
        count_text(text)


def test_default_off_and_unknown_media_tariff_blocked():
    value = payload("image")
    provider = XAdapter(XAdapterConfig(), transport=httpx.MockTransport(Provider()), now=lambda: NOW)
    assert not provider.validate(value, provider.capabilities(account(value))).valid
    assert provider.capabilities(account(value)).feature_states["publishing"] == "restricted"
    assert provider.capabilities(account(value)).supported_formats == ("text",)


@pytest.mark.asyncio
@pytest.mark.parametrize("format", ["text", "image", "carousel", "video"])
async def test_full_chain_survives_restart_after_every_checkpoint(format):
    value, graph, media = payload(format), Provider(), Media()
    graph.processing = True
    checkpoint, operations = {}, []
    for _ in range(25):
        provider = adapter(graph)
        caps = provider.capabilities(account(value))
        assert provider.validate(value, caps).valid
        plan = provider.next_operation(value, checkpoint)
        operations.append(plan.operation)
        assert plan.estimated_cost_microusd > 0
        result = await provider.execute(value, plan, credential(provider, value, plan), media)
        assert result.outcome in {"confirmed_success", "processing"}, result
        checkpoint = json.loads(json.dumps(result.checkpoint))
        await provider.close()
        if result.confirmation_kind == "provider_owned_post_read":
            assert result.primary_remote_id == "777"
            break
    else:
        pytest.fail("fixture did not finish")
    assert operations.count("publish") == 1
    assert len([call for call in graph.calls if call[:2] == ("POST", "/2/tweets")]) == 1
    if value.assets:
        assert len(media.calls) == len(value.assets)
        assert graph.post_body["media"]["media_ids"] == graph.media_ids
        assert operations.count("create_container") == len(value.assets)
    assert checkpoint["content_hash"] == value.content_hash


@pytest.mark.asyncio
@pytest.mark.parametrize("changes,code", [
    ({"x_budget_remaining_microusd": 0}, "BUDGET_EXHAUSTED"),
    ({"x_budget_remaining_microusd": True}, "BUDGET_EXHAUSTED"),
    ({"x_reserved_cost_microusd": 0}, "BUDGET_EXHAUSTED"),
    ({"x_reservation_operation_id": uuid4()}, "BUDGET_EXHAUSTED"),
    ({"x_access_verified": False}, "ACCOUNT_INELIGIBLE"),
    ({"x_access_verified": 1}, "ACCOUNT_INELIGIBLE"),
    ({"access_expires_at": NOW}, "TOKEN_EXPIRED"),
    ({"external_account_id": "902"}, "AUTHORIZATION_REQUIRED"),
    ({"granted_scopes": ("tweet.read",)}, "PERMISSION_DENIED"),
])
async def test_every_entry_blocks_without_access_and_positive_current_reservation(changes, code):
    value, graph = payload(), Provider()
    provider = adapter(graph)
    plan = provider.next_operation(value, {})
    material = credential(provider, value, plan, **changes)
    result = await provider.execute(value, plan, material, None)
    assert result.outcome == "definite_failure" and result.error_code == code
    reconciliation = provider.reconciliation_operation(value, {})
    material = credential(provider, value, reconciliation, **changes)
    result = await provider.reconcile_operation(value, reconciliation, {}, material)
    assert result.outcome == "unknown" and result.evidence["code"] == code
    assert graph.calls == []
    await provider.close()


@pytest.mark.asyncio
async def test_exact_budget_reservation_is_sufficient_and_url_tariff_covers_text_links():
    value, graph = payload(text="See https://example.com/report"), Provider()
    provider = adapter(graph)
    plan = provider.next_operation(value, {})
    assert plan.estimated_cost_microusd == 200_000
    result = await provider.execute(value, plan, credential(provider, value, plan,
        x_budget_remaining_microusd=200_000), None)
    assert result.outcome == "confirmed_success"
    assert len(graph.calls) == 1
    await provider.close()


@pytest.mark.asyncio
async def test_lost_publish_response_retains_uncertainty_and_never_uses_timeline_absence():
    value, graph = payload(), Provider()
    provider = adapter(graph)
    graph.timeout = "/2/tweets"
    plan = provider.next_operation(value, {})
    result = await provider.execute(value, plan, credential(provider, value, plan), None)
    assert result.outcome == "ambiguous"
    assert result.checkpoint["phase"] == "publication_uncertain"
    assert "fixture-secret" not in result.model_dump_json()
    with pytest.raises(ValueError):
        provider.next_operation(value, result.checkpoint)
    read_plan = provider.reconciliation_operation(value, result.checkpoint)
    recovered = await provider.reconcile_operation(value, read_plan, {}, credential(provider, value, read_plan))
    assert recovered.outcome == "unknown" and recovered.absence_proof is None
    assert recovered.evidence["charge_reservation"] == "held"
    assert len(graph.calls) == 1
    await provider.close()


@pytest.mark.asyncio
async def test_readback_is_target_bound_and_cannot_infer_absence():
    value, graph = payload(), Provider()
    provider = adapter(graph)
    plan = provider.next_operation(value, {})
    ack = await provider.execute(value, plan, credential(provider, value, plan), None)
    read = provider.reconciliation_operation(value, ack.checkpoint)
    material = credential(provider, value, read)
    result = await provider.reconcile_operation(value, read, {}, material)
    assert result.outcome == "confirmed_published"
    graph.overrides[("GET", "/2/tweets/777")] = {"data": {"id": "777", "author_id": "999", "text": value.text}}
    result = await provider.reconcile_operation(value, read, {}, material)
    assert result.outcome == "unknown" and result.absence_proof is None
    graph.overrides[("GET", "/2/tweets/777")] = lambda request: httpx.Response(404, json={"title": "Not Found"})
    result = await provider.reconcile_operation(value, read, {}, material)
    assert result.outcome == "unknown" and result.absence_proof is None
    other = payload()
    with pytest.raises(ValueError):
        provider.next_operation(other, ack.checkpoint)
    assert not any(b"/users/" in call[1].encode() for call in graph.calls)
    await provider.close()


@pytest.mark.asyncio
async def test_media_bytes_verified_before_upload_and_no_reinit_after_lost_append():
    value, graph, media = payload("image"), Provider(), Media()
    provider = adapter(graph)
    plan = provider.next_operation(value, {})
    initialized = await provider.execute(value, plan, credential(provider, value, plan), media)
    plan = provider.next_operation(value, initialized.checkpoint)
    media.body = b"modified"
    result = await provider.execute(value, plan, credential(provider, value, plan), media)
    assert result.error_code == "MEDIA_BYTES_UNVERIFIED" and len(graph.calls) == 1
    media.body = BODY
    graph.timeout = "/2/media/upload/500/append"
    result = await provider.execute(value, plan, credential(provider, value, plan), media)
    assert result.outcome == "ambiguous" and result.checkpoint["media_ids"] == ["500"]
    with pytest.raises(ValueError):
        provider.next_operation(value, result.checkpoint)
    assert len(graph.calls) == 2
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    lambda req: httpx.Response(302, headers={"location": "https://untrusted.example"}),
    lambda req: httpx.Response(500, json={"title": "private-error-value"}),
    lambda req: httpx.Response(200, content=b'{"data":{"id":"777"},"data":{"id":"888"}}'),
    lambda req: httpx.Response(200, json={"data": {"id": True}}),
])
async def test_malformed_publish_never_creates_retry_proof(response):
    value, graph = payload(), Provider()
    graph.overrides[("POST", "/2/tweets")] = response
    provider = adapter(graph)
    plan = provider.next_operation(value, {})
    result = await provider.execute(value, plan, credential(provider, value, plan), None)
    assert result.outcome == "ambiguous"
    assert result.checkpoint["phase"] == "publication_uncertain"
    assert "private-error-value" not in result.model_dump_json()
    assert len(graph.calls) == 1
    await provider.close()


@pytest.mark.asyncio
async def test_provider_rate_limit_preserves_reset_and_definite_input():
    value, graph = payload(), Provider()
    reset = NOW + timedelta(minutes=15)
    graph.overrides[("POST", "/2/tweets")] = lambda req: httpx.Response(429,
        headers={"x-rate-limit-reset": str(int(reset.timestamp()))}, json={"title": "Rate limited"})
    provider = adapter(graph)
    plan = provider.next_operation(value, {})
    result = await provider.execute(value, plan, credential(provider, value, plan), None)
    assert result.outcome == "definite_failure" and result.retry_safe is True
    assert result.next_action_at == reset and result.checkpoint == {}
    await provider.close()


@pytest.mark.asyncio
async def test_zero_budget_blocks_each_actual_media_and_read_boundary():
    value, graph, media = payload("image"), Provider(), Media()
    graph.processing = True
    provider = adapter(graph)
    checkpoint, boundaries = {}, []
    for _ in range(10):
        plan = provider.next_operation(value, checkpoint)
        phase = checkpoint.get("phase", "empty")
        count_before = len(graph.calls)
        refused = await provider.execute(value, plan, credential(provider, value, plan,
            x_budget_remaining_microusd=0), media)
        assert refused.error_code == "BUDGET_EXHAUSTED" and len(graph.calls) == count_before
        boundaries.append((plan.operation, phase))
        admitted = await provider.execute(value, plan, credential(provider, value, plan), media)
        assert admitted.outcome in {"confirmed_success", "processing"}
        checkpoint = admitted.checkpoint
        if admitted.confirmation_kind == "provider_owned_post_read":
            break
    assert boundaries == [("create_container", "empty"), ("upload", "initialized"), ("finalize", "appended"),
        ("poll", "media_processing"), ("finalize", "media_ready"), ("publish", "metadata_ready"), ("poll", "post_created")]
    read = provider.reconciliation_operation(value, checkpoint)
    count_before = len(graph.calls)
    refused = await provider.reconcile_operation(value, read, {}, credential(provider, value, read,
        x_budget_remaining_microusd=0))
    assert refused.outcome == "unknown" and refused.evidence["code"] == "BUDGET_EXHAUSTED"
    assert len(graph.calls) == count_before
    legacy = await provider.reconcile(value, checkpoint, {}, credential(provider, value, read))
    assert legacy.outcome == "unknown" and len(graph.calls) == count_before
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("proof", [{"users": [{"id": "901", "protected": True}]},
    {"users": [{"id": "901", "protected": 0}]}, {"users": [{"id": "901"}]}, {}])
async def test_publication_needs_actual_public_author_visibility(proof):
    value, graph = payload(), Provider()
    provider = adapter(graph)
    plan = provider.next_operation(value, {})
    created = await provider.execute(value, plan, credential(provider, value, plan), None)
    graph.overrides[("GET", "/2/tweets/777")] = {"data": {"id": "777", "author_id": "901", "text": value.text}, "includes": proof}
    plan = provider.next_operation(value, created.checkpoint)
    assert plan.estimated_cost_microusd == 15_000
    result = await provider.execute(value, plan, credential(provider, value, plan), None)
    assert result.outcome == "ambiguous" and result.visibility_state == "unknown"
    await provider.close()


@pytest.mark.asyncio
async def test_definite_target_retry_does_not_touch_confirmed_sibling():
    good, retry, graph = payload(), payload(text="Another target's approved text"), Provider()
    provider = adapter(graph)
    good_plan = provider.next_operation(good, {})
    good_result = await provider.execute(good, good_plan, credential(provider, good, good_plan), None)
    graph.overrides[("POST", "/2/tweets")] = lambda req: httpx.Response(429, json={"title": "rate limited"})
    plan = provider.next_operation(retry, {})
    rejected = await provider.execute(retry, plan, credential(provider, retry, plan), None)
    assert rejected.outcome == "definite_failure" and rejected.checkpoint == {}
    del graph.overrides[("POST", "/2/tweets")]
    retry_plan = provider.next_operation(retry, rejected.checkpoint)
    result = await provider.execute(retry, retry_plan, credential(provider, retry, retry_plan), None)
    assert result.outcome == "confirmed_success"
    submitted = [json.loads(call[3])["text"] for call in graph.calls if call[:2] == ("POST", "/2/tweets")]
    assert submitted == [good.text, retry.text, retry.text]
    assert good_result.checkpoint["content_hash"] == good.content_hash
    assert retry_plan.operation_id != plan.operation_id
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", [
    {"phase": "post_created", "post_id": None},
    {"phase": "media_ready", "next_segment": 0, "media_ids": [], "media_keys": []},
    {"phase": "initialized", "asset_index": 1},
    {"phase": "metadata_ready", "asset_index": 0},
    {"phase": "appended", "next_segment": 0},
])
async def test_incoherent_checkpoint_cannot_plan_public_mutation(tamper):
    value, graph = payload("image"), Provider()
    provider = adapter(graph)
    plan = provider.next_operation(value, {})
    initialized = await provider.execute(value, plan, credential(provider, value, plan), Media())
    checkpoint = initialized.checkpoint | tamper
    with pytest.raises(ValueError):
        provider.next_operation(value, checkpoint)
    assert len(graph.calls) == 1
    await provider.close()


@pytest.mark.asyncio
async def test_readback_reverses_tco_text_and_strips_only_owned_attachment_link():
    value, graph, media = payload("image", text="Read https://example.com/report"), Provider(), Media()
    provider = adapter(graph)
    checkpoint = {}
    for _ in range(8):
        plan = provider.next_operation(value, checkpoint)
        result = await provider.execute(value, plan, credential(provider, value, plan), media)
        checkpoint = result.checkpoint
        if checkpoint["phase"] == "post_created":
            break
    graph.overrides[("GET", "/2/tweets/777")] = {
        "data": {"id": "777", "author_id": "901", "text": "Read https://t.co/link https://t.co/photo",
            "entities": {"urls": [
                {"url": "https://t.co/link", "expanded_url": "https://example.com/report"},
                {"url": "https://t.co/photo", "expanded_url": "https://x.com/owned_fixture/status/777/photo/1"}]},
            "attachments": {"media_keys": ["3_500"]}},
        "includes": {"users": [{"id": "901", "protected": False}]}}
    plan = provider.next_operation(value, checkpoint)
    result = await provider.execute(value, plan, credential(provider, value, plan), media)
    assert result.outcome == "confirmed_success" and result.visibility_state == "public"
    await provider.close()


@pytest.mark.asyncio
async def test_lost_media_status_is_not_ready_without_explicit_processing_success():
    value, graph, media = payload("image"), Provider(), Media()
    graph.processing = True
    provider = adapter(graph)
    checkpoint = {}
    for _ in range(3):
        plan = provider.next_operation(value, checkpoint)
        result = await provider.execute(value, plan, credential(provider, value, plan), media)
        checkpoint = result.checkpoint
    assert checkpoint["phase"] == "media_processing"
    graph.overrides[("GET", "/2/media/upload")] = {"data": {"id": "500"}}
    plan = provider.next_operation(value, checkpoint)
    result = await provider.execute(value, plan, credential(provider, value, plan), media)
    assert result.outcome == "ambiguous" and result.checkpoint["phase"] == "media_processing"
    assert not any(call[:2] == ("POST", "/2/tweets") for call in graph.calls)
    await provider.close()


@pytest.mark.asyncio
async def test_multichunk_upload_has_separate_immutable_durable_segments():
    from email.parser import BytesParser
    from email.policy import default
    content = BODY + b"a"*4_000_000
    base = payload("image")
    asset = base.assets[0].model_copy(update={"byte_size": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    value = payload("image", assets=(asset,))
    graph, media = Provider(), Media()
    media.body = content
    segments = []
    def append(request):
        parsed = BytesParser(policy=default).parsebytes(
            b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.content)
        parts = {part.get_param("name", header="content-disposition"): part.get_payload(decode=True) for part in parsed.iter_parts()}
        segments.append((int(parts["segment_index"]), parts["media"]))
        return httpx.Response(204)
    graph.overrides[("POST", "/2/media/upload/500/append")] = append
    checkpoint = {}
    for _ in range(8):
        provider = adapter(graph)
        plan = provider.next_operation(value, checkpoint)
        result = await provider.execute(value, plan, credential(provider, value, plan), media)
        assert result.outcome == "confirmed_success", result
        checkpoint = json.loads(json.dumps(result.checkpoint))
        await provider.close()
        if plan.operation == "publish":
            break
    assert [number for number, _ in segments] == [0, 1]
    assert [len(segment) for _, segment in segments] == [4_000_000, len(BODY)]
    assert b"".join(segment for _, segment in segments) == content
    assert len(media.calls) == 2


@pytest.mark.asyncio
async def test_understated_cost_cannot_dispatch_and_other_target_material_cannot_replay():
    value, other, graph = payload(link="https://example.com/report"), payload(), Provider()
    provider = adapter(graph)
    plan = provider.next_operation(value, {})
    cheap = plan.model_copy(update={"estimated_cost_microusd": 15_000})
    result = await provider.execute(value, cheap, credential(provider, value, cheap), None)
    assert result.outcome == "ambiguous" and graph.calls == []
    result = await provider.execute(value, plan, credential(provider, other, plan), None)
    assert result.error_code == "AUTHORIZATION_REQUIRED" and graph.calls == []
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("scalar", [None, True, False, float("nan"), float("inf"), -float("inf"),
    0, -1, 0.0, 15_000.0, "15000", "", {}, []], ids=["null", "true", "false", "nan", "inf", "negative-inf",
    "zero", "negative", "float-zero", "positive-float", "number-string", "blank", "object", "list"])
async def test_budget_scalar_shape_matrix_is_not_coerced(scalar):
    value, graph = payload(), Provider()
    provider = adapter(graph)
    plan = provider.next_operation(value, {})
    for field in ("x_budget_remaining_microusd", "x_reserved_cost_microusd"):
        result = await provider.execute(value, plan, credential(provider, value, plan, **{field: scalar}), None)
        assert result.error_code == "BUDGET_EXHAUSTED" and result.outcome == "definite_failure"
    changed_account = account(value) | {"x_budget_remaining_microusd": scalar}
    assert provider.capabilities(changed_account).eligible is False
    assert graph.calls == []
    await provider.close()


@pytest.mark.parametrize("scalar", [True, False, float("nan"), float("inf"), 0, -1, 1_000_001, "5000", "", {}, []],
    ids=["true", "false", "nan", "inf", "zero", "negative", "over-limit", "number-string", "blank", "object", "list"])
def test_media_tariff_requires_reviewed_positive_bounded_integer(scalar):
    with pytest.raises(ValueError):
        XAdapterConfig(media_request_cost_microusd=scalar)


@pytest.mark.asyncio
async def test_lost_create_recovers_by_one_reserved_bounded_own_post_read():
    value, graph = payload(), Provider()
    provider = adapter(graph)
    graph.timeout = "/2/tweets"
    publish = provider.next_operation(value, {})
    lost = await provider.execute(value, publish, credential(provider, value, publish), None)
    assert lost.outcome == "ambiguous"
    await provider.close()
    provider = adapter(graph)
    lost = lost.model_copy(update={"checkpoint": json.loads(json.dumps(lost.checkpoint))})
    attempt = original_publish_attempt(value, {})
    graph.overrides[("GET", "/2/users/901/tweets")] = own_posts(value)
    plan = provider.reconciliation_operation(value, lost.checkpoint)
    assert plan.estimated_cost_microusd == 35_000
    recovered = await provider.reconcile_operation(value, plan, attempt, credential(provider, value, plan))
    assert recovered.outcome == "confirmed_published" and recovered.result.primary_remote_id == "777"
    assert recovered.result.visibility_state == "public" and recovered.result.checkpoint["phase"] == "post_created"
    assert recovered.absence_proof is None
    assert recovered.evidence["confidence"] == "unique_strong_match"
    assert recovered.evidence["original_request_fingerprint"] == attempt["request_fingerprint"]
    assert [call[:2] for call in graph.calls] == [("POST", "/2/tweets"), ("GET", "/2/users/901/tweets")]
    query = dict(httpx.QueryParams(graph.calls[-1][2]))
    assert query == {"max_results": "5", "start_time": "2026-10-16T11:49:55Z", "end_time": "2026-10-16T11:55:00Z",
        "post.fields": "attachments,created_at,entities,withheld", "expansions": "author_id", "user.fields": "protected"}
    known = provider.reconciliation_operation(value, recovered.result.checkpoint)
    assert known.estimated_cost_microusd == 15_000
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["next-page", "duplicate-match", "missing-time", "naive-time", "outside-window", "empty", "wrong-count", "boolean-count", "too-many", "partial-error", "wrong-author", "duplicate-id", "private-author"])
async def test_own_post_lookup_partial_or_ambiguous_evidence_is_never_absence(kind):
    value, graph = payload(), Provider()
    provider = adapter(graph)
    response = own_posts(value)
    if kind == "next-page": response["meta"]["next_token"] = "another-page"
    elif kind == "duplicate-match":
        response["data"].append(response["data"][0] | {"id": "778"}); response["meta"]["result_count"] = 2
    elif kind == "missing-time": del response["data"][0]["created_at"]
    elif kind == "naive-time": response["data"][0]["created_at"] = "2026-10-16T11:50:01"
    elif kind == "outside-window": response["data"][0]["created_at"] = "2026-10-16T11:40:01Z"
    elif kind == "empty": response["data"] = []; response["meta"]["result_count"] = 0
    elif kind == "wrong-count": response["meta"]["result_count"] = 2
    elif kind == "boolean-count": response["meta"]["result_count"] = True
    elif kind == "too-many":
        response["data"] = [response["data"][0] | {"id": str(770+i)} for i in range(6)]; response["meta"]["result_count"] = 6
    elif kind == "partial-error": response["errors"] = [{"title": "partial failure"}]
    elif kind == "wrong-author": response["data"][0]["author_id"] = "902"
    elif kind == "duplicate-id": response["data"] *= 2; response["meta"]["result_count"] = 2
    elif kind == "private-author": response["includes"]["users"][0]["protected"] = True
    graph.overrides[("GET", "/2/users/901/tweets")] = response
    plan = provider.reconciliation_operation(value, {})
    recovered = await provider.reconcile_operation(value, plan, original_publish_attempt(value, {}), credential(provider, value, plan))
    assert recovered.outcome == "unknown" and recovered.absence_proof is None
    assert len(graph.calls) == 1
    assert recovered.evidence["charge_reservation"] == "held"
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["missing", "wrong-operation", "missing-dispatch", "naive-dispatch", "future-window", "wrong-fingerprint", "nonpublic-intent", "wrong-checkpoint"])
async def test_own_post_lookup_requires_original_payload_bound_dispatch_before_http(kind):
    value, graph = payload(), Provider()
    provider = adapter(graph)
    attempt = original_publish_attempt(value, {})
    if kind == "missing": attempt = None
    elif kind == "wrong-operation": attempt["operation"] = "upload"
    elif kind == "missing-dispatch": attempt["dispatch_started_at"] = None
    elif kind == "naive-dispatch": attempt["dispatch_started_at"] = NOW.replace(tzinfo=None)
    elif kind == "future-window": attempt["dispatch_started_at"] = NOW-timedelta(minutes=1)
    elif kind == "wrong-fingerprint": attempt["request_fingerprint"] = "0"*64
    elif kind == "nonpublic-intent": attempt["receipt"]["intent"]["publication_capable"] = False
    elif kind == "wrong-checkpoint": attempt = original_publish_attempt(value, {"wrong": "checkpoint"})
    plan = provider.reconciliation_operation(value, {})
    result = await provider.reconcile_operation(value, plan, attempt, credential(provider, value, plan))
    assert result.outcome == ("still_reconciling" if kind == "future-window" else "unknown") and result.absence_proof is None
    assert graph.calls == []
    if kind == "future-window": assert result.next_action_at == NOW+timedelta(minutes=4, seconds=1)
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"x_budget_remaining_microusd": 0}, {"x_reserved_cost_microusd": 15_000},
    {"x_budget_remaining_microusd": 34_999}, {"x_reservation_operation_id": uuid4()}])
async def test_own_post_lookup_requires_worst_case_operation_reservation(changes):
    value, graph = payload(), Provider()
    provider = adapter(graph)
    plan = provider.reconciliation_operation(value, {})
    result = await provider.reconcile_operation(value, plan, original_publish_attempt(value, {}), credential(provider, value, plan, **changes))
    assert result.outcome == "unknown" and result.evidence["code"] == "BUDGET_EXHAUSTED"
    assert graph.calls == []
    await provider.close()


@pytest.mark.asyncio
async def test_lost_media_create_lookup_requires_exact_retained_media_keys():
    value, graph, media = payload("image"), Provider(), Media()
    provider = adapter(graph)
    checkpoint = {}
    for _ in range(6):
        plan = provider.next_operation(value, checkpoint)
        if plan.operation == "publish":
            break
        result = await provider.execute(value, plan, credential(provider, value, plan), media)
        checkpoint = result.checkpoint
    assert checkpoint["phase"] == "metadata_ready"
    original_input = json.loads(json.dumps(checkpoint))
    attempt = original_publish_attempt(value, original_input)
    graph.timeout = "/2/tweets"
    publish = provider.next_operation(value, checkpoint)
    result = await provider.execute(value, publish, credential(provider, value, publish), media)
    assert result.checkpoint["phase"] == "publication_uncertain"
    response = own_posts(value)
    response["data"][0]["attachments"] = {"media_keys": ["3_500"]}
    graph.overrides[("GET", "/2/users/901/tweets")] = response
    recovery = provider.reconciliation_operation(value, result.checkpoint)
    found = await provider.reconcile_operation(value, recovery, attempt, credential(provider, value, recovery))
    assert found.outcome == "confirmed_published" and found.result.remote_refs["post_id"] == "777"
    response["data"][0]["attachments"]["media_keys"] = ["3_999"]
    not_found = await provider.reconcile_operation(value, recovery, attempt, credential(provider, value, recovery))
    assert not_found.outcome == "unknown" and not_found.absence_proof is None
    assert len([call for call in graph.calls if call[:2] == ("POST", "/2/tweets")]) == 1
    # Recovery of a process crash before saving the uncertain response uses the
    # unchanged original input and the same fingerprint, still with one read.
    response["data"][0]["attachments"]["media_keys"] = ["3_500"]
    recovery = provider.reconciliation_operation(value, original_input)
    found = await provider.reconcile_operation(value, recovery, attempt, credential(provider, value, recovery))
    assert found.outcome == "confirmed_published"
    await provider.close()


@pytest.mark.asyncio
async def test_own_post_lookup_missing_media_references_never_reads_the_timeline():
    value, graph = payload("image"), Provider()
    provider = adapter(graph)
    plan = provider.reconciliation_operation(value, {})
    result = await provider.reconcile_operation(value, plan, original_publish_attempt(value, {}), credential(provider, value, plan))
    assert result.outcome == "unknown" and result.absence_proof is None
    assert result.evidence["code"] == "X_ORIGINAL_DISPATCH_UNVERIFIED"
    assert graph.calls == []
    await provider.close()


@pytest.mark.asyncio
async def test_unknown_access_expiry_never_permits_create_or_recovery_read():
    graph,value=Provider(),payload()
    provider=adapter(graph)
    plan=provider.next_operation(value,{})
    result=await provider.execute(value,plan,credential(provider,value,plan,access_expires_at=None),None)
    assert result.error_code=='TOKEN_EXPIRED'
    assert graph.calls==[]
    checkpoint=provider._state(value,'post_created',post_id='777')
    plan=provider.reconciliation_operation(value,checkpoint)
    recovered=await provider.reconcile_operation(value,plan,{},credential(provider,value,plan,access_expires_at=None),None)
    assert recovered.outcome=='unknown'
    assert graph.calls==[]
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("headers,seconds,safe", [
    ({"Retry-After": "7200"},7200,True),
    ({"Retry-After": "Fri, 16 Oct 2026 14:00:00 GMT"},7200,True),
    ({"Retry-After": "7200", "x-rate-limit-reset": str(int(NOW.timestamp())+5)},7200,True),
    ({"Retry-After": "5", "x-rate-limit-reset": str(int(NOW.timestamp())+7200)},7200,True),
    ({},None,False), ({"Retry-After":"malformed"},None,False),
    ({"Retry-After":"0"},None,False),
])
async def test_retry_after_uses_latest_valid_provider_delay(headers,seconds,safe):
    value,graph=payload(),Provider()
    graph.overrides[("POST","/2/tweets")]=lambda req:httpx.Response(429,headers=headers,json={"title":"Rate limited"})
    provider=adapter(graph)
    plan=provider.next_operation(value,{})
    try:
        result=await provider.execute(value,plan,credential(provider,value,plan),None)
        assert result.error_code=="RATE_LIMITED"
        assert result.retry_safe is safe
        assert result.next_action_at==(NOW+timedelta(seconds=seconds) if seconds is not None else None)
        assert result.checkpoint=={}
    finally:
        await provider.close()

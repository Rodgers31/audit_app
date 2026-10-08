"""Persisted admission is carried through the final fake HTTP boundary."""
from dataclasses import replace
from uuid import UUID, uuid4

import httpx
import pytest

from social.adapters import FacebookPageAdapter, MetaAdapterConfig
from social.models import SocialAccount, SocialPublishAttempt
from social.native_admission import native_capability_matches
from social.validation import capability_for
from test_connections_support import config, db, graph, PAGE
from test_worker_materials import admitted
import test_native_meta_adapters as native


def restricted(snapshot, change):
    if change == "eligible": return {**snapshot, "eligible": False}
    if change == "adapter": return {**snapshot, "adapter_available": False}
    if change == "publishing": return {**snapshot, "feature_states": {**snapshot["feature_states"], "publishing": "unsupported"}}
    if change == "price": return {**snapshot, "price_class": "paid"}
    if change == "limits": return {**snapshot, "limits": {**snapshot["limits"], "max_text_length": 1}}
    if change == "required_scopes": return {**snapshot, "required_scopes": [*snapshot["required_scopes"], "ads_management"]}
    if change == "granted_scopes": return {**snapshot, "granted_scopes": []}
    if change == "api_version": return {**snapshot, "provider_api_version": "v25.0"}
    if change == "rules_version": return {**snapshot, "rules_version": "changed-rules"}
    if change == "formats": return {**snapshot, "supported_formats": []}
    if change == "malformed": return {"eligible": True, "unexpected": True}
    return snapshot


def connected_snapshot(provider, account):
    return provider.capabilities({"platform": account.platform, "api_product": account.api_product,
        "connection_state": account.connection_state, "granted_scopes": account.granted_scopes,
        "capability_snapshot": {"eligible": True}}).model_dump(mode="json")


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["valid", "eligible", "adapter", "publishing", "price", "limits", "required_scopes",
    "granted_scopes", "api_version", "rules_version", "formats", "malformed"])
async def test_fresh_locked_material_admission_controls_http(admitted, db, monkeypatch, change):
    loader, request, account_id, _ = admitted
    monkeypatch.setattr(native, "TOKEN", PAGE)
    remote = native.Graph()
    provider = FacebookPageAdapter(MetaAdapterConfig("v26.0", True, True), transport=httpx.MockTransport(remote), now=lambda: native.NOW)
    try:
        account = db.get(SocialAccount, account_id)
        snapshot = connected_snapshot(provider, account)
        assert provider.validate(request.payload, provider.capabilities({"platform": account.platform, "api_product": account.api_product,
            "granted_scopes": account.granted_scopes, "connection_state": "connected", "capability_snapshot": snapshot})).valid
        account.capability_snapshot = restricted(snapshot, change)
        db.commit()
        material = await loader(request)
        result = await provider.execute(request.payload, provider.next_operation(request.payload, {}), material, None)
        if change == "valid":
            assert result.outcome == "confirmed_success" and len(remote.calls) == 1
        else:
            assert result.outcome == "definite_failure" and not remote.calls
    finally:
        await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["eligible", "adapter", "publishing", "price", "limits", "required_scopes",
    "granted_scopes", "api_version", "rules_version", "formats", "malformed"])
async def test_restricted_material_allows_owned_read_without_new_mutation(admitted, db, monkeypatch, change):
    loader, request, account_id, _ = admitted
    monkeypatch.setattr(native, "TOKEN", PAGE)
    remote = native.Graph()
    provider = FacebookPageAdapter(MetaAdapterConfig("v26.0", True, True), transport=httpx.MockTransport(remote), now=lambda: native.NOW)
    try:
        account = db.get(SocialAccount, account_id)
        account.capability_snapshot = connected_snapshot(provider, account)
        db.commit()
        sent = await provider.execute(request.payload, provider.next_operation(request.payload, {}), await loader(request), None)
        assert sent.outcome == "confirmed_success"
        account.capability_snapshot = restricted(account.capability_snapshot, change)
        read_id = uuid4()
        db.add(SocialPublishAttempt(id=uuid4(), target_id=UUID(request.claim.target_id),
            sequence=2, operation_id=read_id, operation="poll", request_fingerprint="e" * 64,
            lease_epoch=1, outcome="intent", receipt={"intent": {"mutating": False}}))
        db.commit()
        material = await loader(replace(request, operation_id=read_id, mutating=False))
        remote.calls.clear()
        recovered = await provider.reconcile(request.payload, sent.checkpoint, {"operation": "publish"}, material, None)
        assert recovered.outcome == "confirmed_published"
        polled = await provider.execute(request.payload, provider.next_operation(request.payload, sent.checkpoint), material, None)
        assert polled.visibility_state == "public"
        assert remote.calls and all(method == "GET" for method, _, _ in remote.calls)
    finally:
        await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["eligible", "adapter_available", "provider_api_version", "rules_version",
    "supported_formats", "required_scopes", "granted_scopes", "limits", "feature_states", "price_class", "publishing"])
async def test_raw_admission_requires_explicit_fields(admitted, db, monkeypatch, missing):
    loader, request, account_id, _ = admitted
    monkeypatch.setattr(native, "TOKEN", PAGE)
    remote = native.Graph()
    provider = FacebookPageAdapter(MetaAdapterConfig("v26.0", True, True), transport=httpx.MockTransport(remote), now=lambda: native.NOW)
    try:
        account = db.get(SocialAccount, account_id)
        snapshot = connected_snapshot(provider, account)
        account.capability_snapshot = snapshot
        baseline = capability_for(account, {(account.platform, account.api_product): provider})
        assert baseline.eligible and native_capability_matches(snapshot, baseline)
        if missing == "publishing":
            snapshot["feature_states"].pop("publishing")
        else:
            snapshot.pop(missing)
        account.capability_snapshot = snapshot
        db.commit()
        material = await loader(request)
        result = await provider.execute(request.payload, provider.next_operation(request.payload, {}), material, None)
        assert result.outcome == "definite_failure" and not remote.calls
        assert material.capability_admission is None
        assert not native_capability_matches(snapshot, baseline)
        assert not capability_for(account, {(account.platform, account.api_product): provider}).eligible
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_source_links_and_verification_timestamp_are_not_admission_fields(admitted, db):
    loader, request, account_id, _ = admitted
    provider = FacebookPageAdapter(MetaAdapterConfig("v26.0", True, True), transport=httpx.MockTransport(native.Graph()))
    try:
        account = db.get(SocialAccount, account_id)
        snapshot = connected_snapshot(provider, account)
        snapshot.pop("source_links")
        snapshot.pop("verified_at")
        account.capability_snapshot = snapshot
        db.commit()
        current = capability_for(account, {(account.platform, account.api_product): provider})
        assert current.eligible and native_capability_matches(snapshot, current)
        assert (await loader(request)).capability_admission is not None
    finally:
        await provider.close()

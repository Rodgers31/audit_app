"""Independent local execution against the integration material boundary."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import httpx
from sqlalchemy import select

from social.adapters import MetaAdapterConfig
from social.connections.models import SocialCredential
from social.contracts import PostDocument
from social.models import SocialAccount, SocialMediaAsset
from social.worker.materials import MaterialUnavailable
from social.worker.native_runtime import create_native_registration
from social.validation import registered_capability, validate_document
from test_connections_support import config, db, graph
from test_worker_materials import admitted, final_media
from test_media_support import ENDPOINT, FakeStorage, png


def test_claim_boolean_epoch_is_not_admission(admitted):
    loader, request, _, _ = admitted
    forged = replace(request, claim=replace(request.claim, epoch=True))
    with pytest.raises(MaterialUnavailable):
        asyncio.run(loader(forged))


@pytest.mark.parametrize("value", [0, -1, 1.0, "1", None, float("nan"), float("inf")])
def test_claim_epoch_has_exact_shape(admitted, value):
    loader, request, _, _ = admitted
    with pytest.raises(MaterialUnavailable):
        asyncio.run(loader(replace(request, claim=replace(request.claim, epoch=value))))


@pytest.mark.parametrize("value", [0, 1, "true", None, float("nan")])
def test_mutating_marker_has_exact_shape(admitted, value):
    loader, request, _, _ = admitted
    with pytest.raises(MaterialUnavailable):
        asyncio.run(loader(replace(request, mutating=value)))


@pytest.mark.parametrize("field,value", [("token", ""), ("account_id", None), ("target_id", "../wrong"),
    ("publication_id", "00000000000000000000000000000000")])
def test_claim_ids_have_exact_shape(admitted, field, value):
    loader, request, _, _ = admitted
    with pytest.raises(MaterialUnavailable):
        asyncio.run(loader(replace(request, claim=replace(request.claim, **{field: value}))))


@pytest.mark.parametrize("change", ["user_token", "user_identity", "user_scopes"])
def test_parent_material_has_a_valid_shape(admitted, db, change):
    loader, request, _, credential_id = admitted
    page = db.get(SocialCredential, credential_id)
    parent = db.get(SocialCredential, page.parent_credential_id)
    grant = loader.cipher.decrypt(parent.id, "facebook_user", parent.key_version, parent.encrypted_bundle)
    bundle = loader.cipher.decrypt(page.id, "facebook_page", page.key_version, page.encrypted_bundle)
    if change == "user_token":
        grant["access_token"] = ""
    elif change == "user_identity":
        grant["external_user_id"] = bundle["external_user_id"] = True
        page.key_version, page.encrypted_bundle = loader.cipher.encrypt(page.id, "facebook_page", bundle)
    else:
        grant["scopes"] = None
    parent.key_version, parent.encrypted_bundle = loader.cipher.encrypt(parent.id, "facebook_user", grant)
    db.commit()
    with pytest.raises(MaterialUnavailable):
        asyncio.run(loader(request))


@pytest.mark.parametrize("change", ["leading_space", "embedded_newline", "embedded_tab"])
def test_signed_fetch_raw_url_is_valid(final_media, change):
    access, storage, asset, _ = final_media
    url = ENDPOINT + "/media-test/final/private?fake=fixture"
    if change == "leading_space":
        url = " " + url
    elif change == "embedded_newline":
        url = url.replace("https://", "https:\n//")
    else:
        url = url.replace("/media-test/", "/media-test/\t")
    storage.preview = lambda *args: SimpleNamespace(url=url, expires_at=datetime.now(timezone.utc) + timedelta(seconds=300))
    with pytest.raises(MaterialUnavailable):
        asyncio.run(access.provider_fetch_url(asset, 120))


@pytest.mark.parametrize("suffix", ["#fragment", "/../wrong?fixture=signed", "%2Fother?fixture=signed", "/?fixture=signed"])
def test_signed_path_cannot_drift(final_media, suffix):
    access, storage, asset, _ = final_media
    url = ENDPOINT + "/media-test/final/private" + suffix
    storage.preview = lambda *args: SimpleNamespace(url=url, expires_at=datetime.now(timezone.utc) + timedelta(seconds=300))
    with pytest.raises(MaterialUnavailable):
        asyncio.run(access.provider_fetch_url(asset, 120))


@pytest.mark.parametrize("ttl", [True, 0, -1, 1.0, 241, None, float("nan"), float("inf")])
def test_minimum_fetch_ttl_has_exact_shape(final_media, ttl):
    access, _, asset, _ = final_media
    with pytest.raises(MaterialUnavailable):
        asyncio.run(access.provider_fetch_url(asset, ttl))


@pytest.mark.parametrize("change", ["valid", "disabled", "png", "ratio", "caption", "caption_asset", "disclosure"])
def test_registry_approval_validation_remains_closed(admitted, db, change):
    loader, _, _, _ = admitted
    account = db.scalar(select(SocialAccount).where(SocialAccount.platform == "instagram"))
    account.publishing_enabled = True
    import hashlib
    from uuid import uuid4
    content = png()
    asset = SocialMediaAsset(id=uuid4(), storage_provider="r2", bucket="media-test", storage_key="final/fixture",
        original_filename="fixture.jpg", mime_type="image/jpeg", byte_size=len(content),
        sha256=hashlib.sha256(content).hexdigest(), width=320, height=320, state="ready", created_by=uuid4())
    if change == "png":
        asset.mime_type = "image/png"
    elif change == "ratio":
        asset.height = 1000
    db.add(asset)
    db.commit()
    master = {"text": "Authorized caption", "media": [{"asset_id": str(asset.id), "alt_text": "A fixture"}], "hashtags": []}
    if change == "caption":
        master["text"] = "a" * 2190
        master["hashtags"] = ["LongHashtag"]
    if change == "caption_asset":
        master["media"][0]["caption_asset_id"] = str(asset.id)
    doc = PostDocument.model_validate({"master": master, "targets": [{"account_id": str(account.id), "format": "image"}]})
    registration = create_native_registration(db.bind, MetaAdapterConfig("v26.0", change != "disabled", True, "fake-app-secret"),
        cipher=loader.cipher, storage=FakeStorage(), storage_origin="a" * 32 + ".r2.cloudflarestorage.com",
        transport_factory=lambda: httpx.MockTransport(lambda request: httpx.Response(500)))
    if change != "disabled":
        # Exercise content validation after an explicitly verified capability snapshot.
        account.capability_snapshot = registered_capability(account, registration.adapters).model_dump(mode="json")
        db.commit()
    if change == "valid":
        assert validate_document(db, doc, {}, registration.adapters).valid
    elif change == "disclosure":
        # Disclosures are currently absent from the post document schema.
        from social.contracts import ResolvedPostPayload
        provider = registration.adapters[("instagram", "instagram_graph_facebook_login")]
        result = validate_document(db, doc, {}, registration.adapters)
        forged = result.targets[0].resolved_preview.model_copy(update={"disclosures": ("paid_partnership",)})
        assert not provider.validate(forged, provider.capabilities({"platform": account.platform, "api_product": account.api_product,
            "connection_state": account.connection_state, "granted_scopes": account.granted_scopes, "capability_snapshot": account.capability_snapshot})).valid
    else:
        assert not validate_document(db, doc, {}, registration.adapters).valid
    asyncio.run(registration.close())

"""Final independent native-integration probes against root SQLite fixtures."""
import asyncio
from dataclasses import replace

import httpx
import pytest
from sqlalchemy import select

from social.adapters import MetaAdapterConfig
from social.contracts import PostDocument
from social.models import SocialAccount
from social.service import SocialService
from social.validation import registered_capability, validate_document
from social.worker.materials import MaterialUnavailable
from social.worker.native_runtime import create_native_registration
from test_connections_support import config, db, graph
from test_worker_materials import admitted, final_media
from test_media_support import ENDPOINT, FakeStorage


def registry(db, loader):
    return create_native_registration(db.bind, MetaAdapterConfig("v26.0", True, True, "fixture-app-secret"),
        cipher=loader.cipher, storage=FakeStorage(), storage_origin="a" * 32 + ".r2.cloudflarestorage.com",
        transport_factory=lambda: httpx.MockTransport(lambda request: httpx.Response(500)))


def test_registered_account_list_is_a_valid_projection(admitted, db):
    loader, _, _, _ = admitted
    registration = registry(db, loader)
    try:
        for account in db.scalars(select(SocialAccount)):
            account.capability_snapshot = registered_capability(account, registration.adapters).model_dump(mode="json")
        db.commit()
        result = SocialService(db, available_adapters=registration.adapters).accounts()
        assert len(result["accounts"]) == 2
        assert all(account["capabilities"]["adapter_available"] for account in result["accounts"])
    finally:
        asyncio.run(registration.close())


@pytest.mark.parametrize("change", ["publishing", "price", "limit", "scope"])
def test_persisted_publishing_restriction_survives_registry(admitted, db, change):
    loader, _, account_id, _ = admitted
    account = db.get(SocialAccount, account_id)
    account.publishing_enabled = True
    registration = registry(db, loader)
    try:
        account.capability_snapshot = registered_capability(account, registration.adapters).model_dump(mode="json")
        db.commit()
        document = PostDocument.model_validate({"master": {"text": "Authorized publication"},
            "targets": [{"account_id": str(account.id), "format": "text"}]})
        assert validate_document(db, document, {}, registration.adapters).valid
        snapshot = account.capability_snapshot
        if change == "publishing":
            account.capability_snapshot = {**snapshot,
                "feature_states": {**snapshot["feature_states"], "publishing": "unsupported"}}
        elif change == "price":
            account.capability_snapshot = {**snapshot, "price_class": "paid"}
        elif change == "limit":
            account.capability_snapshot = {**snapshot, "limits": {**snapshot["limits"], "max_text_length": 5}}
        else:
            account.capability_snapshot = {**snapshot, "required_scopes": [*snapshot["required_scopes"], "ads_management"]}
        db.commit()
        assert not validate_document(db, document, {}, registration.adapters).valid
    finally:
        asyncio.run(registration.close())


@pytest.mark.parametrize("field,value", [("claim", None), ("claim", {}), ("payload", None), ("payload", {})])
def test_nested_request_shape_has_safe_error(admitted, field, value):
    loader, request, _, _ = admitted
    with pytest.raises(MaterialUnavailable):
        asyncio.run(loader(replace(request, **{field: value})))


@pytest.mark.parametrize('secret', [' ', '   ', '\u00a0', 'nonascii\u00e9'])
def test_registry_requires_visible_ascii_application_material(admitted, db, secret):
    loader, _, _, _ = admitted
    with pytest.raises(ValueError):
        registration = create_native_registration(db.bind, MetaAdapterConfig('v26.0', True, True, secret),
            cipher=loader.cipher, storage=FakeStorage(), storage_origin='a' * 32 + '.r2.cloudflarestorage.com',
            transport_factory=lambda: httpx.MockTransport(lambda request: httpx.Response(500)))
        asyncio.run(registration.close())

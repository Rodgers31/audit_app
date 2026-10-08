"""Independent local review probes; real boundaries, no provider calls."""
import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest

from social.adapters import MetaAdapterConfig
from social.contracts import InspectedAsset
from social.models import SocialMediaAsset, SocialPostTarget, SocialPublication
from social.worker.materials import MaterialUnavailable, VerifiedMediaAccess
from social.worker.native_runtime import create_native_registration
from social.connections.crypto import CredentialCipher
from social.service import SocialError
from test_connections_support import config, db
from test_media_storage_adversary import BUCKET, KEY, ORIGIN, SDK, signed_url, storage
from test_media_support import FakeStorage, png
from test_worker_materials import final_media
from test_domain_postgres import pg_engine


def test_real_r2_signed_preview_can_supply_native_material(db):
    content = png()
    digest = hashlib.sha256(content).hexdigest()
    url = signed_url(headers="host", **{"X-Amz-Date": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), "versionId": "v1"})
    sdk = SDK(data=content, digest=digest, url=url)
    port = storage(sdk)
    snapshot = port.head(KEY)
    identity = uuid4()
    db.add(SocialMediaAsset(id=identity, storage_provider="r2", bucket=BUCKET, storage_key=KEY,
        original_filename="fixture.png", mime_type="image/png", byte_size=len(content), sha256=digest,
        width=64, height=32, state="ready", created_by=uuid4(),
        codec_metadata={"storage_etag": snapshot.etag, "storage_version": snapshot.version}))
    db.commit()
    asset = InspectedAsset(asset_id=identity, sha256=digest, mime_type="image/png", byte_size=len(content), width=64, height=32)
    access = VerifiedMediaAccess(db.bind, port, allowed_origin=ORIGIN, assets=(asset,))
    result = asyncio.run(access.provider_fetch_url(asset, 120))
    assert result.asset_id == identity
    assert result.expires_at >= datetime.now(timezone.utc) + timedelta(seconds=120)


def test_signed_fetch_cannot_select_foreign_object_version(final_media):
    access, port, asset, _ = final_media
    from test_media_support import ENDPOINT
    port.preview = lambda *args: SimpleNamespace(url=ENDPOINT + "/media-test/final/private?versionId=foreign-version",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=300))
    with pytest.raises(MaterialUnavailable):
        asyncio.run(access.provider_fetch_url(asset, 120))


@pytest.mark.parametrize("missing", ["cipher", "storage", "origin", "transport"])
def test_enabled_registry_requires_working_material_dependencies(db, config, missing):
    values = {"cipher": CredentialCipher(config.active_key_version, config.encryption_keys), "storage": FakeStorage(),
        "storage_origin": ORIGIN, "transport_factory": lambda: httpx.MockTransport(lambda request: httpx.Response(500))}
    values[{"origin": "storage_origin", "transport": "transport_factory"}.get(missing, missing)] = None if missing != "transport" else lambda: None
    with pytest.raises(ValueError):
        registration = create_native_registration(db.bind, MetaAdapterConfig("v26.0", True, True, "fixture-secret"), **values)
        asyncio.run(registration.close())


def test_native_approval_and_worker_use_the_same_current_capabilities(pg_engine, config):
    """A pre-registration connected account must not get a false approval gate."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from social.contracts import CapabilitySet, PublishCommand
    from social.models import SocialAccount, SocialControls, SocialPostRevision
    from social.service import SocialService
    from social.worker.config import WorkerConfig
    from social.worker.repository import QueueRepository
    from test_domain_support import ACTOR, account, draft_body
    registration = create_native_registration(pg_engine, MetaAdapterConfig("v26.0", True, True, "fixture-secret"),
        cipher=CredentialCipher(config.active_key_version, config.encryption_keys), storage=FakeStorage(), storage_origin=ORIGIN,
        transport_factory=lambda: httpx.MockTransport(lambda request: httpx.Response(500)))
    try:
        with Session(pg_engine, expire_on_commit=False) as db:
            row = account(db)
            row.api_product, row.external_account_id = "facebook_pages", "901"
            row.granted_scopes = ["pages_manage_posts", "pages_read_engagement", "pages_show_list"]
            row.capability_snapshot = CapabilitySet(eligible=True, adapter_available=False, supported_formats=(),
                feature_states={"publishing": "unsupported"}).model_dump(mode="json")
            db.add(SocialControls(id=1, publishing_enabled=True))
            db.commit()
            svc = SocialService(db, available_adapters=registration.adapters)
            svc.actor, svc.request_id = ACTOR, uuid4()
            draft = draft_body((row,))
            created = svc.create(draft)
            db.commit()
            # A legacy connection must be explicitly reverified/reconnected;
            # registry presence alone cannot bypass the worker's stored gate.
            with pytest.raises(SocialError, match="TARGET_VALIDATION_FAILED"):
                svc.publish(UUID(created["id"]), PublishCommand(expected_version=created["version"], revision_id=created["revision_id"]))
            assert not list(db.scalars(select(SocialPostTarget)))
            assert not list(db.scalars(select(SocialPublication)))
    finally:
        asyncio.run(registration.close())

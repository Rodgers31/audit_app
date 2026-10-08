"""Capability admission before intent and after intent, in random PG schemas."""
import asyncio
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from social.models import SocialAccount, SocialPostTarget, SocialPublishAttempt
from social.worker.runner import SocialWorker
from test_connections_support import config
from test_domain_postgres import pg_engine
from test_native_capability_admission import restricted
from test_native_meta_adapters import Graph
from test_native_worker_postgres import due, prepare, registration, step
from test_queue_postgres import repository


@pytest.fixture
def native_pg(pg_engine):
    for filename in ("c96d13e2f411_social_meta_credentials.py", "a42b86e1d310_social_private_media_intake.py",
            "b73e19a4f602_social_media_write_settlement.py"):
        path = Path(__file__).resolve().parents[2] / "alembic/versions" / filename
        spec = importlib.util.spec_from_file_location("native_capability_" + filename, path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with pg_engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
    return pg_engine


def change_capability(engine, account_id, change):
    with Session(engine) as db:
        account = db.get(SocialAccount, account_id)
        account.capability_snapshot = restricted(account.capability_snapshot, change)
        db.commit()


@pytest.mark.parametrize("change", ["valid", "eligible", "adapter", "publishing", "price", "limits", "required_scopes",
    "granted_scopes", "api_version", "rules_version", "formats"])
def test_worker_persisted_native_gate_before_intent(native_pg, config, monkeypatch, change):
    graph = Graph()
    storage, target_id = prepare(native_pg, config, graph, monkeypatch)
    with Session(native_pg) as db:
        account_id = db.get(SocialPostTarget, target_id).account_id
    change_capability(native_pg, account_id, change)
    repo = repository(native_pg)
    registered = registration(native_pg, config, storage, graph)
    async def run():
        worker = SocialWorker(repo, adapters=registered.adapters, credential_loader=registered.credential_loader,
            media_access=registered.media_access)
        try:
            claims = await worker.db(repo.claim_due, 1)
            assert len(claims) == 1
            await worker.process(claims[0])
        finally:
            await worker.close()
            await registered.close()
    asyncio.run(run())
    with Session(native_pg) as db:
        target = db.get(SocialPostTarget, target_id)
        if change == "valid":
            assert target.state == "processing" and len(graph.calls) == 1
        else:
            assert target.state in {"blocked", "failed"} and not graph.calls


@pytest.mark.parametrize("change", ["eligible", "adapter", "publishing", "price", "limits", "required_scopes",
    "granted_scopes", "api_version", "rules_version", "formats", "malformed"])
def test_worker_rechecks_locked_capabilities_after_intent(native_pg, config, monkeypatch, change):
    graph = Graph()
    storage, target_id = prepare(native_pg, config, graph, monkeypatch)
    repo = repository(native_pg)
    registered = registration(native_pg, config, storage, graph)
    begin = repo.begin_operation
    def restrict_after_intent(claim, **kwargs):
        intent = begin(claim, **kwargs)
        assert intent is not None
        from uuid import UUID
        change_capability(native_pg, UUID(claim.account_id), change)
        return intent
    repo.begin_operation = restrict_after_intent
    async def run():
        worker = SocialWorker(repo, adapters=registered.adapters, credential_loader=registered.credential_loader,
            media_access=registered.media_access)
        try:
            claims = await worker.db(repo.claim_due, 1)
            assert len(claims) == 1
            await worker.process(claims[0])
        finally:
            await worker.close()
            await registered.close()
    asyncio.run(run())
    assert not graph.calls
    with Session(native_pg) as db:
        target = db.get(SocialPostTarget, target_id)
        assert target.state in {"blocked", "failed"}
        assert target.submit_count == 1


def test_worker_authenticated_readback_preserves_known_send_under_restriction(native_pg, config, monkeypatch):
    graph = Graph()
    storage, target_id = prepare(native_pg, config, graph, monkeypatch)
    async def step():
        registered = registration(native_pg, config, storage, graph)
        worker = SocialWorker(repository(native_pg), adapters=registered.adapters,
            credential_loader=registered.credential_loader, media_access=registered.media_access)
        try:
            claims = await worker.db(worker.repository.claim_due, 1)
            assert len(claims) == 1
            await worker.process(claims[0])
        finally:
            await worker.close()
            await registered.close()
    asyncio.run(step())
    with Session(native_pg) as db:
        target = db.get(SocialPostTarget, target_id)
        assert target.state == "processing" and target.checkpoint["post_id"] == "901_777"
        account_id = target.account_id
    change_capability(native_pg, account_id, "malformed")
    with native_pg.begin() as connection:
        connection.execute(text("UPDATE social_post_targets SET next_action_at=clock_timestamp()-interval '1 second' WHERE id=:id"),
            {"id": target_id})
    asyncio.run(step())
    assert [method for method, _, _ in graph.calls] == ["POST", "GET"]
    with Session(native_pg) as db:
        target = db.get(SocialPostTarget, target_id)
        assert target.state == "published" and target.visibility_state == "public" and target.submit_count == 1


@pytest.mark.parametrize("change", ["valid", "api_version", "granted_scopes"])
def test_processing_instagram_publish_rechecks_before_new_intent(native_pg, config, monkeypatch, change):
    graph = Graph()
    storage, target_id = prepare(native_pg, config, graph, monkeypatch, platform="instagram", image=True)
    for phase in ("quota_checked", "container_created", "container_ready", "publish_ready"):
        due(native_pg, target_id)
        step(native_pg, config, storage, graph)
        with Session(native_pg) as db:
            target = db.get(SocialPostTarget, target_id)
            assert target.checkpoint["phase"] == phase
    with Session(native_pg) as db:
        target = db.get(SocialPostTarget, target_id)
        assert target.state == "processing" and target.submit_count == 0
        account_id = target.account_id
    assert [method for method, _, _ in graph.calls] == ["GET", "POST", "GET", "GET"]
    change_capability(native_pg, account_id, change)
    due(native_pg, target_id)
    step(native_pg, config, storage, graph)
    with Session(native_pg) as db:
        target = db.get(SocialPostTarget, target_id)
        if change == "valid":
            assert target.state == "processing" and target.checkpoint["phase"] == "media_created"
            assert target.submit_count == 1
            assert graph.calls[-1][:2] == ("POST", "/v26.0/801/media_publish")
            assert db.scalar(select(func.count()).select_from(SocialPublishAttempt)) == 5
        else:
            assert target.state == "blocked" and target.checkpoint["phase"] == "publish_ready"
            assert target.submit_count == 0
            assert len(graph.calls) == 4
            assert db.scalar(select(func.count()).select_from(SocialPublishAttempt)) == 4

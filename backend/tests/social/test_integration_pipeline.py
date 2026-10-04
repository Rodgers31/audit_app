"""Integrator-owned API/worker tests on the actual migrated PostgreSQL schema.

No real adapters, credentials or production databases are used. Each test gets
its own schema in an explicitly supplied loopback database.
"""
import asyncio
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from social.api import get_db, require_admin, router, service
from social.contracts import CapabilitySet, OperationPlan, OperationResult, ValidationResult
from social.http_policy import SocialNoStoreMiddleware
from social.models import SocialAccount, SocialControls
from social.service import SocialService
from social.worker.config import WorkerConfig
from social.worker.repository import QueueRepository
from social.worker.runner import SocialWorker
from supabase_auth import AdminUser
from local_postgres import local_postgres_url


@pytest.fixture
def migrated_engine():
    dsn = os.getenv("SOCIAL_INTEGRATION_DATABASE_URL")
    if not dsn:
        pytest.skip("Supply an isolated local integration database explicitly")
    url = local_postgres_url(dsn, 'auditgava_social_test')
    root = create_engine(url, hide_parameters=True)
    schema = "social_integration_" + uuid4().hex
    with root.begin() as conn:
        conn.execute(text("CREATE SCHEMA " + schema))
    engine = create_engine(url, hide_parameters=True, pool_size=2, max_overflow=0,
                           connect_args={"options": "-csearch_path=" + schema})
    migration_path = Path(__file__).parents[2] / "alembic/versions/f38c61a9d203_social_manual_domain_queue.py"
    spec = importlib.util.spec_from_file_location("social_integration_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    try:
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
        yield engine
    finally:
        engine.dispose()
        with root.begin() as conn:
            conn.execute(text("DROP SCHEMA " + schema + " CASCADE"))
        root.dispose()


def setup_client(engine, platforms=("facebook", "threads")):
    actor = uuid4()
    caps = CapabilitySet(eligible=True, supported_formats=("text",),
                         feature_states={"publishing": "supported"},
                         price_class="free", adapter_available=True,
                         provider_api_version="explicit-integration-fake")
    accounts = []
    with Session(engine) as db:
        db.add(SocialControls(id=1, publishing_enabled=True,
                              budget_controls={"x_budget_microusd": 1000}))
        for platform in platforms:
            account = SocialAccount(id=uuid4(), platform=platform, api_product="integration-fake",
                                    connection_method="fixture", external_account_id=uuid4().hex,
                                    display_name="Isolated fixture", connection_state="connected",
                                    publishing_enabled=True, granted_scopes=[],
                                    capability_snapshot=caps.model_dump(mode="json"))
            accounts.append(str(account.id))
            db.add(account)
        db.commit()
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(SocialNoStoreMiddleware)

    def local_db():
        with Session(engine) as db:
            yield db

    def explicit_fakes(db=Depends(get_db)):
        return SocialService(db, available_adapters=platforms)

    app.dependency_overrides[get_db] = local_db
    app.dependency_overrides[service] = explicit_fakes
    app.dependency_overrides[require_admin] = lambda: AdminUser(id=str(actor), email=None, roles=["admin"])
    return TestClient(app), accounts


def command(client, path, body):
    return client.post("/api/v1/admin/social" + path, json=body,
                       headers={"Idempotency-Key": str(uuid4())})


def create_and_publish(client, accounts):
    response = command(client, "/posts", {
        "title": "Integrator fixture", "content_type": "announcement",
        "document": {"schema_version": 1,
                     "master": {"text": "Traceable fixture only", "link": None, "hashtags": [], "media": []},
                     "targets": [{"account_id": account, "format": "text", "overrides": {}} for account in accounts]},
        "references": [],
    })
    assert response.status_code == 201, response.text
    post = response.json()
    response = command(client, "/posts/" + post["id"] + "/publish",
                       {"expected_version": post["version"], "revision_id": post["revision_id"]})
    assert response.status_code == 202, response.text
    return post["id"], response.json()


class ExplicitFake:
    def __init__(self, failure=False):
        self.failure, self.calls = failure, 0

    def capabilities(self, account):
        return CapabilitySet.model_validate(account["capability_snapshot"])

    def validate(self, payload, capabilities):
        return ValidationResult(valid=True)

    def next_operation(self, payload, checkpoint):
        return OperationPlan(operation_id=uuid4(), operation="publish", publication_capable=True,
                             safe_replay_class="requires_reconciliation", checkpoint=checkpoint)

    async def execute(self, payload, operation, credential, media_access):
        self.calls += 1
        assert payload.text == "Traceable fixture only"
        if self.failure:
            return OperationResult(outcome="definite_failure", error_code="FIXTURE_REJECTION", retry_safe=True)
        return OperationResult(outcome="confirmed_success", primary_remote_id="fake-" + str(payload.account_id),
                               visibility_state="public", confirmation_kind="explicit-fake-public-receipt")


def drain(engine, adapters):
    async def run():
        repo = QueueRepository(engine, WorkerConfig(str(engine.url.render_as_string(hide_password=False))), uuid4())
        worker = SocialWorker(repo, adapters=adapters)
        try:
            while True:
                claims = await worker.db(repo.claim_due, 2)
                if not claims:
                    break
                await asyncio.gather(*(worker.process(claim) for claim in claims))
        finally:
            await worker.close()
    asyncio.run(run())


def test_migrated_manual_cascade_and_retry_never_reposts_success(migrated_engine):
    platforms = ("facebook", "instagram", "threads", "x", "tiktok")
    client, accounts = setup_client(migrated_engine, platforms)
    post_id, accepted = create_and_publish(client, accounts)
    assert accepted["status_url"] == "/api/v1/admin/social/posts/" + post_id + "/status"
    adapters = {(platform, "integration-fake"): ExplicitFake(failure=platform == "x") for platform in platforms}
    drain(migrated_engine, adapters)
    detail = client.get("/api/v1/admin/social/posts/" + post_id).json()
    assert detail["delivery_status"] == "partially_published"
    assert sum(target["state"] == "published" for target in detail["targets"]) == 4
    failed = next(target for target in detail["targets"] if target["platform"] == "x")
    assert failed["state"] == "failed"
    response = command(client, "/targets/" + failed["id"] + "/retry", {"reason": "Explicit fake retry verification"})
    assert response.status_code == 200, response.text
    adapters[("x", "integration-fake")].failure = False
    drain(migrated_engine, adapters)
    detail = client.get("/api/v1/admin/social/posts/" + post_id).json()
    assert detail["delivery_status"] == "published"
    assert adapters[("x", "integration-fake")].calls == 2
    assert all(adapter.calls == 1 for (platform, _), adapter in adapters.items() if platform != "x")
    compact = client.get("/api/v1/admin/social/posts/" + post_id + "/status")
    assert compact.status_code == 200
    assert compact.headers["cache-control"] == "private, no-store"
    assert not {"document", "references", "publication"}.intersection(compact.json())
    assert all("resolved_payload" not in target for target in compact.json()["targets"])


def test_actual_migration_prevents_approved_history_mutation(migrated_engine):
    client, accounts = setup_client(migrated_engine)
    post_id, accepted = create_and_publish(client, accounts)
    with migrated_engine.connect() as conn:
        revision = conn.execute(text("SELECT current_revision_id FROM social_posts WHERE id=:id"), {"id": post_id}).scalar_one()
    from sqlalchemy.exc import DBAPIError
    attacks = [
        ("UPDATE social_post_revisions SET document='{}'::jsonb WHERE id=:id", revision),
        ("UPDATE social_post_targets SET payload_hash=repeat('0',64) WHERE id=:id", accepted["targets"][0]["id"]),
        ("UPDATE social_publications SET approved_hash=repeat('0',64) WHERE id=:id", accepted["publication_id"]),
        ("DELETE FROM social_audit_events WHERE post_id=:id", post_id),
    ]
    for sql, resource in attacks:
        with pytest.raises(DBAPIError) as rejected:
            with migrated_engine.begin() as conn:
                conn.execute(text(sql), {"id": resource})
        assert rejected.value.orig.pgcode == "23514"

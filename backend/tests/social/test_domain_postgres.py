"""Real PG proof; explicit DSN must target the dedicated local test database."""
import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from social.contracts import ApproveCommand, PatchPost
from social.models import SocialAccount, SocialAuditEvent, SocialPost, SocialPostRevision, SocialPostTarget, SocialPublication
from social.service import SocialError
from test_domain_support import ACTOR, account, call, draft_body
from local_postgres import local_postgres_url


def migration():
    path = Path(__file__).resolve().parents[2] / "alembic/versions/f38c61a9d203_social_manual_domain_queue.py"
    spec = importlib.util.spec_from_file_location("social_batch_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pg_engine():
    dsn = os.getenv("SOCIAL_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set SOCIAL_TEST_DATABASE_URL for the isolated PostgreSQL lane")
    url = local_postgres_url(dsn, 'social_domain_test')
    schema = "social_domain_" + uuid4().hex
    admin = create_engine(url, pool_size=1, max_overflow=0)
    with admin.begin() as conn:
        conn.execute(text("CREATE SCHEMA " + schema))
    engine = create_engine(url, pool_size=3, max_overflow=0, connect_args={"options": "-csearch_path=" + schema})
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration().upgrade()
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text("DROP SCHEMA " + schema + " CASCADE"))
        admin.dispose()


def test_pg_migration_upgrade_rls_empty_downgrade(pg_engine):
    with pg_engine.begin() as conn:
        rows = conn.execute(text("SELECT relname,relrowsecurity FROM pg_class WHERE relnamespace=current_schema()::regnamespace AND relkind='r'"))
        tables = dict(rows.all())
        assert len(tables) == 12
        assert all(tables.values())
        with Operations.context(MigrationContext.configure(conn)):
            migration().downgrade()
        assert conn.execute(text("SELECT count(*) FROM pg_class WHERE relnamespace=current_schema()::regnamespace AND relkind='r'")).scalar() == 0


def test_pg_same_key_race_and_optimistic_edit(pg_engine):
    body, key = draft_body(), uuid4()
    def create_once():
        with Session(pg_engine, expire_on_commit=False) as db:
            return call(db, body, lambda s: s.create(body), route="create", key=key)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create_once(), range(2)))
    assert results[0] == results[1]
    post_id = UUID(results[0][1]["id"])
    def edit_once(title):
        patch = PatchPost(expected_version=1, title=title)
        with Session(pg_engine, expire_on_commit=False) as db:
            try:
                call(db, patch, lambda s: s.patch(post_id, patch), route="patch")
                return "committed"
            except SocialError as exc:
                return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(edit_once, ("First edit", "Second edit")))
    assert sorted(result) == ["VERSION_CONFLICT", "committed"]
    with Session(pg_engine) as db:
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 1
        assert db.scalar(select(func.count()).select_from(SocialPostRevision)) == 2
        assert db.scalar(select(func.count()).select_from(SocialAuditEvent)) == 2


def test_pg_database_guards_raw_sql_history_target_authorization(pg_engine):
    with Session(pg_engine, expire_on_commit=False) as db:
        row = account(db)
        body = draft_body((row,))
        _, created = call(db, body, lambda s: s.create(body), route="create")
        approve = ApproveCommand(expected_version=1, revision_id=created["revision_id"])
        _, approved = call(db, approve, lambda s: s.approve(UUID(created["id"]), approve), route="approve")
    statements = [
        ("UPDATE social_post_revisions SET content_hash=:hash WHERE id=:id", created["revision_id"]),
        ("UPDATE social_publications SET approved_hash=:hash WHERE id=:id", approved["publication"]["id"]),
        ("UPDATE social_post_targets SET payload_hash=:hash WHERE id=:id", approved["targets"][0]["id"]),
        ("UPDATE social_audit_events SET action='altered' WHERE post_id=:id", created["id"]),
    ]
    for statement, row_id in statements:
        with pg_engine.connect() as conn:
            with pytest.raises(IntegrityError):
                with conn.begin():
                    conn.execute(text(statement), {"id": row_id, "hash": "f" * 64})
    with pg_engine.begin() as conn:
        # Worker state/checkpoint fields remain mutable under the payload guard.
        conn.execute(text("UPDATE social_post_targets SET state='queued', checkpoint='{}'::jsonb WHERE id=:id"), {"id": approved["targets"][0]["id"]})
    with pg_engine.connect() as conn:
        with pytest.raises(RuntimeError, match="history exists"):
            with conn.begin():
                with Operations.context(MigrationContext.configure(conn)):
                    migration().downgrade()


def test_pg_revision_owner_and_one_publication_per_revision(pg_engine):
    with Session(pg_engine, expire_on_commit=False) as db:
        row = account(db)
        first_body, second_body = draft_body((row,)), draft_body((row,), title="Second")
        _, first = call(db, first_body, lambda s: s.create(first_body), route="create1")
        _, second = call(db, second_body, lambda s: s.create(second_body), route="create2")
    with pg_engine.connect() as conn:
        with pytest.raises(IntegrityError):
            with conn.begin():
                conn.execute(text("UPDATE social_posts SET current_revision_id=:revision WHERE id=:post"), {"revision": first["revision_id"], "post": second["id"]})


def test_pg_ready_asset_and_published_proof_guards(pg_engine):
    from social.models import SocialMediaAsset
    with Session(pg_engine, expire_on_commit=False) as db:
        row = account(db)
        asset = SocialMediaAsset(id=uuid4(), storage_provider="fixture", bucket="fixture", storage_key="immutable", original_filename="chart.png", mime_type="image/png", byte_size=100, sha256="a" * 64, width=640, height=640, state="ready", created_by=ACTOR)
        db.add(asset)
        db.commit()
        body = draft_body((row,))
        _, post = call(db, body, lambda s: s.create(body), route="create")
        approve = ApproveCommand(expected_version=1, revision_id=post["revision_id"])
        _, detail = call(db, approve, lambda s: s.approve(UUID(post["id"]), approve), route="approve")
        target_id = detail["targets"][0]["id"]
        asset_id = str(asset.id)
    for statement, row_id in [("UPDATE social_media_assets SET sha256='" + "b" * 64 + "' WHERE id=:id", asset_id), ("UPDATE social_post_targets SET state='published' WHERE id=:id", target_id)]:
        with pg_engine.connect() as conn:
            with pytest.raises(IntegrityError):
                with conn.begin():
                    conn.execute(text(statement), {"id": row_id})
    with pg_engine.begin() as conn:
        conn.execute(text("UPDATE social_post_targets SET state='published', primary_remote_id='opaque-confirmed', confirmation_kind='provider_receipt', published_at=now(), visibility_state='public' WHERE id=:id"), {"id": target_id})

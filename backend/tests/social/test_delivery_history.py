"""Past authorizations remain visible without binding current draft commands."""
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from social.models import SocialPostRevision, SocialPostTarget, SocialPublication
from social.service import SocialError, SocialService
from test_api_admin import key, make_client
from test_domain_support import ACTOR, db
from test_domain_postgres import pg_engine
from test_schedule_management import command_body, scheduled_fixture


def revised_fixture(db):
    client, base, old, accounts = scheduled_fixture(db)
    edited = client.patch(base, json={"expected_version": old["version"], "title": "Revised draft"}, headers=key())
    assert edited.status_code == 200, edited.text
    return client, base, old, edited.json(), accounts


def test_revoked_deliveries_remain_in_history_without_current_authorization(db):
    client, base, old, edited, _ = revised_fixture(db)
    assert edited["publication"] is None and edited["targets"] == []
    assert edited["revision_id"] != old["revision_id"]
    for result in (edited, client.get(base + "/status").json(), client.get("/api/v1/admin/social/posts", params={"delivery_filter": "history"}).json()["posts"][0]):
        assert result["publication"] is None
        assert result["historical_target_count"] == 1
        history = result["historical_targets"][0]
        assert history["id"] == old["targets"][0]["id"]
        assert history["publication_id"] == old["publication"]["id"]
        assert history["revision_id"] == old["revision_id"]
        assert history["state"] == "cancelled" and history["revoked_at"] is not None
        assert history["scheduled_for"] == old["publication"]["scheduled_for"]
    assert client.get("/api/v1/admin/social/posts", params={"delivery_filter": "scheduled"}).json()["total"] == 0


def test_history_previews_are_bounded_and_endpoint_paginates_exact_receipts(db):
    client, base, old, edited, accounts = revised_fixture(db)
    previous = db.get(SocialPostTarget, UUID(old["targets"][0]["id"]))
    source = db.get(SocialPostRevision, UUID(old["revision_id"]))
    now = SocialService(db).now()
    for index in range(24):
        revision = SocialPostRevision(id=uuid4(), post_id=UUID(old["id"]), revision_no=index + 3,
            document=source.document, evidence_snapshot=source.evidence_snapshot, content_hash=source.content_hash)
        db.add(revision); db.flush()
        publication = SocialPublication(id=uuid4(), post_id=UUID(old["id"]), revision_id=revision.id,
            approved_at=now, approved_by=ACTOR, approved_hash=revision.content_hash, revoked_at=now)
        db.add(publication); db.flush()
        db.add(SocialPostTarget(id=uuid4(), publication_id=publication.id, account_id=accounts[0].id,
            resolved_payload=previous.resolved_payload, payload_hash=previous.payload_hash,
            capability_version=previous.capability_version, state="failed" if index == 0 else "cancelled",
            updated_at=now + timedelta(seconds=index)))
    db.commit()
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany): statements.append(statement.lower())
    event.listen(db.bind, "before_cursor_execute", record)
    try:
        listing = client.get("/api/v1/admin/social/posts", params={"delivery_filter": "history"}).json()
        summary = client.get(base + "/status").json()
        pages = [client.get(base + "/history", params={"page": page}).json() for page in (1, 2, 3)]
    finally:
        event.remove(db.bind, "before_cursor_execute", record)
    assert listing["total"] == 1
    for result in (listing["posts"][0], summary):
        assert result["historical_target_count"] == 25
        assert len(result["historical_targets"]) == 20
    assert [len(page["targets"]) for page in pages] == [20, 5, 0]
    assert all(page["total"] == 25 and page["post_id"] == old["id"] for page in pages)
    assert [page["has_more"] for page in pages] == [True, False, False]
    ids = [target["id"] for page in pages for target in page["targets"]]
    assert len(set(ids)) == 25
    assert pages[0]["targets"] == summary["historical_targets"]
    assert not any(any(column in sql for column in ("resolved_payload", "evidence_snapshot", "checkpoint", "receipt", "social_post_revisions")) for sql in statements)
    assert client.get("/api/v1/admin/social/posts", params={"delivery_filter": "needs_attention"}).json()["total"] == 1
    assert client.get(base + "/history", params={"page_size": 21}).status_code == 422
    assert client.get("/api/v1/admin/social/posts/" + str(uuid4()) + "/history").status_code == 404


def test_new_authorization_does_not_replace_prior_delivery_identity(db):
    client, base, old, edited, _ = revised_fixture(db)
    due = SocialService(db).now() + timedelta(days=3)
    response = client.post(base + "/schedule", json={"expected_version": edited["version"], "revision_id": edited["revision_id"],
        "schedule": {"local_time": due.replace(tzinfo=None).isoformat(), "timezone": "UTC", "utc_offset": "+00:00"}}, headers=key())
    assert response.status_code == 202, response.text
    current = client.get(base).json()
    assert current["publication"]["revision_id"] == edited["revision_id"]
    assert current["targets"][0]["state"] == "queued"
    assert current["historical_targets"][0]["publication_id"] == old["publication"]["id"]
    assert current["historical_targets"][0]["revision_id"] != current["revision_id"]
    for view in ("scheduled", "history"):
        assert client.get("/api/v1/admin/social/posts", params={"delivery_filter": view}).json()["total"] == 1


@pytest.mark.parametrize("field,value", [("page", True), ("page", 0), ("page", 1.5), ("page", "1"), ("page", 10 ** 100),
    ("page_size", True), ("page_size", 0), ("page_size", 101), ("page_size", 1.5), ("page_size", "20")])
def test_direct_post_pagination_has_strict_bounds(db, field, value):
    with pytest.raises(SocialError) as error:
        SocialService(db).posts(**{field: value})
    assert error.value.status == 422 and error.value.code == "INVALID_REQUEST"


def test_http_overflow_pages_and_deadlines_are_atomic_client_errors(db):
    client, base, original, _ = scheduled_fixture(db)
    for path in ("/api/v1/admin/social/posts", base + "/history"):
        assert client.get(path, params={"page": str(10 ** 100)}).status_code == 422
    response = client.post(base + "/reschedule", json={**command_body(original), "schedule": {
        "local_time": "9999-12-31T23:30:00", "timezone": "UTC", "utc_offset": "+00:00"}}, headers=key())
    assert response.status_code == 422
    assert client.get(base).json() == original


def test_history_is_admin_only_private_and_empty_pages_stay_bounded(db):
    client, base, original, _ = scheduled_fixture(db)
    path = base + "/history"
    denied = make_client(db.bind, authenticated=False).get(path)
    assert denied.status_code in {401, 403}
    assert denied.headers["cache-control"] == "private, no-store"
    empty = client.get(path, params={"page": 2_147_483_647})
    assert empty.status_code == 200 and empty.json()["targets"] == []
    assert empty.json()["total"] == 0 and empty.json()["has_more"] is False
    assert empty.headers["cache-control"] == "private, no-store"
    assert client.get("/api/v1/admin/social/posts", params={"page": 2_147_483_647, "page_size": 100}).status_code == 200


@pytest.mark.parametrize("check", [test_revoked_deliveries_remain_in_history_without_current_authorization, test_new_authorization_does_not_replace_prior_delivery_identity])
def test_pg_past_authorization_history_remains_visible(pg_engine, check):
    with Session(pg_engine, expire_on_commit=False) as session:
        check(session)


def test_pg_bounded_history_receipts_and_exact_page_counts(pg_engine):
    with Session(pg_engine, expire_on_commit=False) as session:
        test_history_previews_are_bounded_and_endpoint_paginates_exact_receipts(session)

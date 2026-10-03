from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from social.contracts import ApproveCommand, ControlsCommand, PatchPost, PublishCommand, RejectCommand, RetryCommand, VersionCommand
from social.models import SocialAuditEvent, SocialCommandReceipt, SocialPost, SocialPostRevision, SocialPostTarget, SocialPublication, SocialPublishAttempt
from social.service import SocialError, SocialService
from test_domain_support import account, call, db, draft_body


def make(db, accounts=()):
    body = draft_body(accounts)
    _, result = call(db, body, lambda s: s.create(body), route="create", status=201)
    return result


def enable(db):
    body = ControlsCommand(expected_version=1, publishing_enabled=True, reason="Local fixture")
    return call(db, body, lambda s: s.controls(body), route="controls")


def test_create_idempotency_actor_route_and_changed_body(db):
    body, key = draft_body(), uuid4()
    first = call(db, body, lambda s: s.create(body), route="create", key=key)
    second = call(db, body, lambda s: s.create(body), route="create", key=key)
    assert first == second
    assert db.scalar(select(func.count()).select_from(SocialPost)) == 1
    assert db.scalar(select(func.count()).select_from(SocialPostRevision)) == 1
    assert db.scalar(select(func.count()).select_from(SocialAuditEvent)) == 1
    changed = draft_body(title="changed")
    with pytest.raises(SocialError, match="IDEMPOTENCY_CONFLICT"):
        call(db, changed, lambda s: s.create(changed), route="create", key=key)


def test_patch_stale_version_and_old_revision_immutable(db):
    original = make(db)
    post_id = UUID(original["id"])
    body = PatchPost(expected_version=1, title="Edited title")
    _, edited = call(db, body, lambda s: s.patch(post_id, body), route="patch")
    assert edited["version"] == 2
    assert edited["revision_id"] != original["revision_id"]
    old = db.get(SocialPostRevision, UUID(original["revision_id"]))
    assert old.document == original["document"]
    with pytest.raises(SocialError, match="VERSION_CONFLICT"):
        call(db, body, lambda s: s.patch(post_id, body), route="patch")
    old = db.get(SocialPostRevision, UUID(original["revision_id"]))
    old.content_hash = "f" * 64
    with pytest.raises(ValueError, match="immutable"):
        db.flush()
    db.rollback()


def test_pause_and_invalid_subset_commit_nothing(db):
    row = account(db)
    created = make(db, (row,))
    post_id = UUID(created["id"])
    body = PublishCommand(expected_version=1, revision_id=created["revision_id"])
    with pytest.raises(SocialError, match="PUBLISHING_PAUSED"):
        call(db, body, lambda s: s.publish(post_id, body), route="publish")
    assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0
    enable(db)
    row = db.get(type(row), row.id)
    row.publishing_enabled = False
    db.commit()
    with pytest.raises(SocialError, match="TARGET_VALIDATION_FAILED"):
        call(db, body, lambda s: s.publish(post_id, body), route="publish")
    assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0
    assert db.scalar(select(func.count()).select_from(SocialPostTarget)) == 0


def test_approve_ready_edit_revokes_authorization(db):
    row = account(db)
    created = make(db, (row,))
    post_id = UUID(created["id"])
    body = ApproveCommand(expected_version=1, revision_id=created["revision_id"])
    _, approved = call(db, body, lambda s: s.approve(post_id, body), route="approve")
    assert approved["editorial_state"] == "approved"
    assert approved["targets"][0]["state"] == "ready"
    patch = PatchPost(expected_version=2, title="Needs fresh approval")
    _, edited = call(db, patch, lambda s: s.patch(post_id, patch), route="patch")
    assert edited["editorial_state"] == "draft"
    assert edited["publication"] is None
    previous = db.get(SocialPublication, UUID(approved["publication"]["id"]))
    assert previous.revoked_at is not None
    assert db.get(SocialPostTarget, UUID(approved["targets"][0]["id"])).state == "cancelled"


def test_empty_selection_cannot_approve_or_publish(db):
    created = make(db)
    post_id = UUID(created["id"])
    body = ApproveCommand(expected_version=1, revision_id=created["revision_id"])
    with pytest.raises(SocialError, match="TARGET_VALIDATION_FAILED"):
        call(db, body, lambda s: s.approve(post_id, body), route="approve")
    assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0


def test_publish_once_new_key_and_content_lock(db):
    row = account(db)
    created = make(db, (row,))
    enable(db)
    post_id = UUID(created["id"])
    body = PublishCommand(expected_version=1, revision_id=created["revision_id"])
    _, accepted = call(db, body, lambda s: s.publish(post_id, body), route="publish", status=202)
    assert accepted["status"] == "queued"
    current = SocialService(db).detail(post_id)
    again = PublishCommand(expected_version=current["version"], revision_id=current["revision_id"])
    _, second = call(db, again, lambda s: s.publish(post_id, again), route="publish", status=202)
    assert second["publication_id"] == accepted["publication_id"]
    assert db.scalar(select(func.count()).select_from(SocialPostTarget)) == 1
    target = db.get(SocialPostTarget, UUID(accepted["targets"][0]["id"]))
    target.state, target.submit_count = "dispatching", 1
    db.commit()
    patch = PatchPost(expected_version=current["version"], title="Correction")
    with pytest.raises(SocialError, match="CONTENT_LOCKED"):
        call(db, patch, lambda s: s.patch(post_id, patch), route="patch")


def test_cancel_and_duplicate_preserve_inflight_history(db):
    row = account(db)
    created = make(db, (row,))
    enable(db)
    post_id = UUID(created["id"])
    body = PublishCommand(expected_version=1, revision_id=created["revision_id"])
    _, accepted = call(db, body, lambda s: s.publish(post_id, body), route="publish")
    target = db.get(SocialPostTarget, UUID(accepted["targets"][0]["id"]))
    target.state, target.submit_count = "dispatching", 1
    db.commit()
    cancel = VersionCommand(expected_version=2)
    _, cancelled = call(db, cancel, lambda s: s.cancel(post_id, cancel), route="cancel")
    assert cancelled["cancellation"]["in_flight_target_ids"] == [str(target.id)]
    assert cancelled["targets"][0]["state"] == "dispatching"
    duplicate = VersionCommand(expected_version=3)
    _, copied = call(db, duplicate, lambda s: s.duplicate(post_id, duplicate), route="duplicate")
    assert copied["id"] != created["id"]
    assert copied["origin_type"] == "manual"
    assert copied["editorial_state"] == "draft"
    assert copied["targets"] == []
    assert copied["publication"] is None


def test_submit_reject_and_sensitive_review_attestation(db):
    row = account(db)
    created = make(db, (row,))
    post_id = UUID(created["id"])
    submit = VersionCommand(expected_version=1)
    _, pending = call(db, submit, lambda s: s.submit(post_id, submit), route="submit")
    assert pending["editorial_state"] == "pending_review"
    reject = RejectCommand(expected_version=2, reason="References need checking")
    _, rejected = call(db, reject, lambda s: s.reject(post_id, reject), route="reject")
    assert rejected["editorial_state"] == "rejected"
    patch = PatchPost(expected_version=3, content_type="debt_update")
    _, financial = call(db, patch, lambda s: s.patch(post_id, patch), route="patch")
    approve = ApproveCommand(expected_version=4, revision_id=financial["revision_id"])
    with pytest.raises(SocialError, match="REVIEW_ATTESTATION_REQUIRED"):
        call(db, approve, lambda s: s.approve(post_id, approve), route="approve")


def test_retry_rejects_unknown_success_and_missing_safe_receipt(db):
    row = account(db)
    created = make(db, (row,))
    post_id = UUID(created["id"])
    approve = ApproveCommand(expected_version=1, revision_id=created["revision_id"])
    _, approved = call(db, approve, lambda s: s.approve(post_id, approve), route="approve")
    target_id = UUID(approved["targets"][0]["id"])
    retry = RetryCommand(reason="Known failure review")
    target = db.get(SocialPostTarget, target_id)
    target.state = "outcome_unknown"
    db.commit()
    with pytest.raises(SocialError, match="RECONCILIATION_REQUIRED"):
        call(db, retry, lambda s: s.retry(target_id, retry), route="retry")
    target = db.get(SocialPostTarget, target_id)
    target.state = "failed"
    db.commit()
    with pytest.raises(SocialError, match="RETRY_NOT_SAFE"):
        call(db, retry, lambda s: s.retry(target_id, retry), route="retry")


def test_failed_command_rolls_back_revision_targets_receipt_and_audit(db):
    body = draft_body()
    def crash(svc):
        svc.create(body)
        raise RuntimeError("fixture crash")
    with pytest.raises(RuntimeError):
        call(db, body, crash)
    for model in (SocialPost, SocialPostRevision, SocialCommandReceipt, SocialAuditEvent, SocialPublication, SocialPostTarget):
        assert db.scalar(select(func.count()).select_from(model)) == 0


def test_lists_are_compact_and_default_status_truthful(db):
    make(db)
    svc = SocialService(db)
    result = svc.posts()
    assert result["total"] == 1
    assert "document" not in result["posts"][0]
    assert "references" not in result["posts"][0]
    assert svc.accounts() == {"accounts": []}
    assert svc.status()["worker"]["state"] == "unavailable"
    assert svc.status()["publishing_enabled"] is False


def test_safe_retry_only_requeues_failed_destination(db):
    from datetime import timedelta
    from social.models import SocialControls
    rows = (account(db), account(db, "threads"))
    created = make(db, rows)
    enable(db)
    post_id = UUID(created["id"])
    publish = PublishCommand(expected_version=1, revision_id=created["revision_id"])
    _, accepted = call(db, publish, lambda s: s.publish(post_id, publish), route="publish")
    failed = db.get(SocialPostTarget, UUID(accepted["targets"][0]["id"]))
    successful = db.get(SocialPostTarget, UUID(accepted["targets"][1]["id"]))
    failed.state, failed.submit_count = "failed", 1
    successful.state, successful.primary_remote_id = "published", "opaque-id-9223372036854775808"
    successful.confirmation_kind, successful.visibility_state = "provider_receipt", "public"
    successful.published_at = SocialService(db).now()
    db.add(SocialPublishAttempt(target_id=failed.id, sequence=1, operation_id=uuid4(), operation="publish", request_fingerprint=failed.payload_hash, lease_epoch=0, outcome="definite_failure", receipt={"retry_safe": True}))
    db.commit()
    retry = RetryCommand(reason="Verified definite rejection")
    _, result = call(db, retry, lambda s: s.retry(failed.id, retry), route="retry")
    by_id = {t["id"]: t for t in result["targets"]}
    assert by_id[str(failed.id)]["state"] == "retry_wait"
    assert by_id[str(successful.id)]["state"] == "published"
    assert result["delivery_status"] == "partially_published"
    with pytest.raises(SocialError, match="RETRY_NOT_SAFE"):
        call(db, retry, lambda s: s.retry(successful.id, retry), route="retry")


@pytest.mark.parametrize("state, heartbeat_age, scan_age, expected", [("healthy", -8640000, None, "unavailable"), ("active", -8640000, 0, "unavailable"), ("active", 0, None, "unavailable"), ("active", 90, 90, "stale"), ("idle", 90, 90, "idle"), ("idle", 180, 180, "stale"), ("stopped", 0, None, "stopped")])
def test_worker_health_requires_real_recent_scan_and_known_state(db, state, heartbeat_age, scan_age, expected):
    from datetime import timedelta
    from social.models import SocialWorkerHeartbeat
    now = SocialService(db).now()
    db.add(SocialWorkerHeartbeat(worker_id=uuid4(), deployment_version="fixture", started_at=now, heartbeat_at=now-timedelta(seconds=heartbeat_age), last_scan_at=now-timedelta(seconds=scan_age) if scan_age is not None else None, active_claims=0, state=state))
    db.commit()
    assert SocialService(db).status()["worker"]["state"] == expected

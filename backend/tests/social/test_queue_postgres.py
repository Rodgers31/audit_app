"""Executed isolated PostgreSQL locking, restart and crash-boundary fixtures.

Run only with an explicitly supplied LOCAL SOCIAL_WORKER_TEST_DATABASE_URL.
This module never imports backend.main or backend.database.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import threading
import time
from uuid import uuid4

import pytest
from sqlalchemy import event as sqlalchemy_event, text
from sqlalchemy.orm import Session

from social.contracts import CapabilitySet, OperationPlan, OperationResult, ReconciliationResult, ResolvedPostPayload, ValidationResult, canonical_hash
from social.models import SOCIAL_TABLES, SocialAccount, SocialControls, SocialPost, SocialPostRevision, SocialPublication, SocialPostTarget
from social.worker.config import WorkerConfig, create_worker_engine
from social.worker.repository import QueueRepository, LeaseLost
from social.worker.runner import SocialWorker
from local_postgres import local_postgres_url


@pytest.fixture
def engine():
    dsn = os.environ.get("SOCIAL_WORKER_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set an explicit isolated local worker test DSN")
    url = local_postgres_url(dsn, 'social_worker_test')
    config = WorkerConfig(url.render_as_string(hide_password=False))
    engine = create_worker_engine(config)
    SocialPost.metadata.create_all(engine, tables=SOCIAL_TABLES)
    names = ",".join('"'+table.name+'"' for table in SOCIAL_TABLES)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE "+names+" RESTART IDENTITY CASCADE"))
    yield engine
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE "+names+" RESTART IDENTITY CASCADE"))
    engine.dispose()


def repository(engine, **settings):
    return QueueRepository(engine, WorkerConfig(str(engine.url.render_as_string(hide_password=False)), **settings), uuid4())


def seed(engine, *, count=1, same_account=False, paused=False, state="queued", checkpoint=None):
    now = datetime.now(timezone.utc)
    ids = {"post": uuid4(), "revision": uuid4(), "publication": uuid4(), "targets": [], "accounts": []}
    capability = CapabilitySet(eligible=True, supported_formats=("text",),
        feature_states={"publishing": "supported"}, price_class="free", adapter_available=True,
        provider_api_version="fake-v1", granted_scopes=("publish",), required_scopes=("publish",))
    with Session(engine) as db:
        db.add(SocialControls(id=1, publishing_enabled=not paused))
        for index in range(1 if same_account else count):
            account_id = uuid4()
            ids["accounts"].append(account_id)
            db.add(SocialAccount(id=account_id, platform="facebook", api_product="fake",
                connection_method="fixture", external_account_id=str(index), display_name="Test account",
                connection_state="connected", granted_scopes=["publish"], publishing_enabled=True,
                capability_snapshot=capability.model_dump(mode="json")))
        post = SocialPost(id=ids["post"], title="Test", content_type="announcement", editorial_state="approved")
        db.add(post)
        db.flush()
        document = {"schema_version": 1, "master": {"text": "fixture", "link": None, "hashtags": [], "media": []}, "targets": [{"account_id":str(account_id),"format":"text","overrides":{}} for account_id in ids["accounts"]]}
        evidence = {"references": []}
        revision_hash = canonical_hash({"document": document, "evidence_snapshot": evidence})
        db.add(SocialPostRevision(id=ids["revision"], post_id=post.id, revision_no=1,
                                 document=document, evidence_snapshot=evidence, content_hash=revision_hash))
        db.flush()
        post.current_revision_id = ids["revision"]
        db.add(SocialPublication(id=ids["publication"], post_id=post.id,
            revision_id=ids["revision"], approved_by=uuid4(), approved_at=now,
            approved_hash=revision_hash, dispatch_requested_at=now,
            start_deadline=now+timedelta(hours=1), retry_deadline=now+timedelta(hours=24)))
        db.flush()
        # One publication cannot select the same account twice. To exercise account
        # admission, each repeated account target has its own approved publication.
        for index in range(count):
            publication_id = ids["publication"]
            if same_account and index:
                new_post, new_revision, publication_id = uuid4(), uuid4(), uuid4()
                db.add(SocialPost(id=new_post, title="Other test", content_type="announcement", editorial_state="approved"))
                db.flush()
                db.add(SocialPostRevision(id=new_revision, post_id=new_post, revision_no=1, document=document,
                    evidence_snapshot=evidence, content_hash=revision_hash))
                db.flush()
                db.add(SocialPublication(id=publication_id, post_id=new_post, revision_id=new_revision,
                    approved_by=uuid4(), approved_at=now, approved_hash=revision_hash, dispatch_requested_at=now,
                    start_deadline=now+timedelta(hours=1), retry_deadline=now+timedelta(hours=24)))
                db.flush()
            account_id = ids["accounts"][0 if same_account else index]
            payload = ResolvedPostPayload(account_id=account_id, platform="facebook", api_product="fake",
                external_account_id=str(0 if same_account else index), format="text", text="fixture",
                evidence_hash=canonical_hash(evidence), content_hash="0"*64)
            payload = payload.model_copy(update={"content_hash": canonical_hash(payload.model_dump(mode="json", exclude={"content_hash"}))})
            target_id = uuid4()
            ids["targets"].append(target_id)
            db.add(SocialPostTarget(id=target_id, publication_id=publication_id, account_id=account_id,
                resolved_payload=payload.model_dump(mode="json"), payload_hash=payload.content_hash,
                capability_version="social-v1", state=state, next_action="publish",
                next_action_at=now-timedelta(seconds=1), checkpoint=checkpoint if checkpoint is not None else {}))
        db.commit()
    return ids


def row(engine, target_id):
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT * FROM social_post_targets WHERE id=:id"), {"id": target_id}).mappings().one())


def due_now(engine, target_id):
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_post_targets SET next_action_at=now()-interval '1 second' WHERE id=:id"), {"id": target_id})


def expire(engine, target_id):
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_post_targets SET lease_expires_at=now()-interval '1 second' WHERE id=:id"), {"id": target_id})


def intent(repo, claim, *, public=True, operation="publish", replay="requires_reconciliation"):
    snapshot = repo.load(claim)
    return repo.begin_operation(claim, operation_id=uuid4(), operation=operation,
        publication_capable=public, mutating=replay != "read_only", safe_replay_class=replay,
        request_fingerprint="a"*64, checkpoint_input=snapshot["checkpoint"])


class FakeAdapter:
    def __init__(self, results=None, *, gate=None, reconcile_result=None, upload_first=False):
        self.results = list(results or [OperationResult(outcome="confirmed_success", primary_remote_id="remote-1",
            visibility_state="public", confirmation_kind="provider_receipt")])
        self.calls, self.reconciliations = 0, 0
        self.gate, self.reconcile_result, self.upload_first = gate, reconcile_result, upload_first
    def capabilities(self, account):
        return CapabilitySet.model_validate(account["capability_snapshot"])
    def validate(self, payload, capabilities):
        return ValidationResult(valid=True)
    def next_operation(self, payload, checkpoint):
        operation = "upload" if self.upload_first and not checkpoint.get("upload_id") else "poll" if checkpoint.get("processing_id") else "publish"
        return OperationPlan(operation_id=uuid4(), operation=operation,
            publication_capable=operation == "publish", safe_replay_class="read_only" if operation == "poll" else "requires_reconciliation",
            checkpoint=checkpoint)
    async def execute(self, payload, operation, credential, media_access):
        self.calls += 1
        if self.gate:
            await self.gate(operation)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
    async def reconcile(self, payload, checkpoint, attempt, credential, media_access):
        self.reconciliations += 1
        return self.reconcile_result or ReconciliationResult(outcome="unknown", evidence={"lookup": "incomplete"})


def run_claim(repo, adapter=None):
    async def execute():
        worker = SocialWorker(repo, adapters={("facebook", "fake"): adapter} if adapter else {})
        try:
            claims = await worker.db(repo.claim_due, 1)
            assert claims
            await worker.process(claims[0])
        finally:
            await worker.close()
    asyncio.run(execute())


def read_history(engine, target_id, *, count=100, age_seconds=60):
    """Completed reads are charged even when they observed no final result."""
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO social_publish_attempts
                (id,target_id,sequence,operation_id,operation,request_fingerprint,lease_epoch,outcome,receipt,
                 estimated_cost_microusd,cost_reservation_state,completed_at,created_at)
            SELECT gen_random_uuid(),CAST(:id AS uuid),start.sequence+n,gen_random_uuid(),
                   'poll',repeat('a',64),0,'ambiguous',
                   jsonb_build_object('intent',jsonb_build_object('publication_capable',false,
                       'mutating',false,'safe_replay_class','read_only')),
                   0,'not_required',clock_timestamp(),clock_timestamp()-make_interval(secs => :age)
            FROM generate_series(1,:count) AS n
            CROSS JOIN (SELECT COALESCE(MAX(sequence),0) AS sequence
                        FROM social_publish_attempts WHERE target_id=CAST(:id AS uuid)) AS start
        """), {"id":target_id,"count":count,"age":age_seconds})


def test_old_mutation_history_does_not_permanently_strand_reconciliation(engine):
    ids = seed(engine)
    target_id = ids["targets"][0]
    repo = repository(engine)
    fake = FakeAdapter(results=[TimeoutError("ambiguous")],reconcile_result=ReconciliationResult(
        outcome="confirmed_published",evidence={"match":"exact"},
        result=OperationResult(outcome="confirmed_success",primary_remote_id="existing",
                               visibility_state="public",confirmation_kind="verified")))
    run_claim(repo,fake)
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_publish_attempts SET created_at=clock_timestamp()-interval '25 hours' WHERE target_id=:id"), {"id":target_id})
        conn.execute(text("UPDATE social_publications SET retry_deadline=clock_timestamp()-interval '1 second' WHERE id=:id"), {"id":ids["publication"]})
    read_history(engine,target_id,age_seconds=25*3600)
    due_now(engine,target_id)
    run_claim(repo,fake)
    assert row(engine,target_id)["state"] == "published"
    assert fake.calls == 1 and fake.reconciliations == 1


@pytest.mark.parametrize("state", ["processing", "reconciling"])
def test_exhausted_read_budget_defers_checkpoint_then_recovers_after_window(engine,state):
    ids = seed(engine,checkpoint={"upload_id":"preserved"})
    target_id = ids["targets"][0]
    public_result = OperationResult(outcome="confirmed_success",primary_remote_id="existing",
                                   visibility_state="public",confirmation_kind="verified")
    first = (OperationResult(outcome="processing",checkpoint={"upload_id":"preserved","processing_id":"container"})
             if state == "processing" else TimeoutError("ambiguous"))
    fake = FakeAdapter(results=[first,public_result],reconcile_result=ReconciliationResult(
        outcome="confirmed_published",evidence={"match":"exact"},result=public_result))
    repo = repository(engine)
    run_claim(repo,fake)
    before = row(engine,target_id)
    assert before["state"] == state
    read_history(engine,target_id)
    due_now(engine,target_id)
    run_claim(repo,fake)
    waiting = row(engine,target_id)
    assert waiting["state"] == state
    assert waiting["checkpoint"] == before["checkpoint"]
    assert waiting["submit_count"] == 1
    assert waiting["lease_token"] is None
    assert waiting["next_action"] == ("poll" if state == "processing" else "reconcile")
    assert waiting["error_code"] == "STATUS_CHECK_LIMIT"
    assert timedelta(hours=23) < waiting["next_action_at"]-datetime.now(timezone.utc) <= timedelta(hours=24)
    assert fake.calls == 1 and fake.reconciliations == 0
    with engine.connect() as conn:
        hold=conn.execute(text("SELECT hold_reason FROM social_accounts WHERE id=:id"),{"id":ids["accounts"][0]}).scalar_one()
        assert bool(hold) == (state == "reconciling")
        assert conn.execute(text("SELECT COUNT(*) FROM social_publish_attempts WHERE target_id=:id"),{"id":target_id}).scalar_one() == 101
    # Move only read timestamps beyond the window; no sleep or real provider.
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_publish_attempts SET created_at=clock_timestamp()-interval '25 hours' WHERE target_id=:id AND operation IN ('poll','reconcile')"),{"id":target_id})
    due_now(engine,target_id)
    run_claim(repo,fake)
    final = row(engine,target_id)
    assert final["state"] == "published" and final["submit_count"] == 1
    assert fake.calls == (2 if state == "processing" else 1)
    assert fake.reconciliations == (1 if state == "reconciling" else 0)


def test_direct_read_permit_cannot_bypass_exhausted_budget(engine):
    ids = seed(engine,state="processing",checkpoint={"processing_id":"container"})
    target_id = ids["targets"][0]
    repo = repository(engine)
    read_history(engine,target_id)
    claim = repo.claim_due()[0]
    assert intent(repo,claim,public=False,operation="poll",replay="read_only") is None
    assert row(engine,target_id)["state"] == "processing"
    assert row(engine,target_id)["next_action_at"] > datetime.now(timezone.utc)


def test_read_budget_excludes_old_reads_and_mutations_but_counts_unfinished_read_intent(engine):
    ids = seed(engine,state="processing",checkpoint={"processing_id":"container"})
    target_id = ids["targets"][0]
    read_history(engine,target_id,age_seconds=25*3600)
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_publish_attempts SET operation='upload',created_at=clock_timestamp() WHERE target_id=:id AND sequence=1"),{"id":target_id})
    read_history(engine,target_id,count=99)
    repo = repository(engine)
    claim = repo.claim_due()[0]
    assert not repo.read_budget_exhausted(claim)
    assert intent(repo,claim,public=False,operation="poll",replay="read_only") is not None
    assert repo.read_budget_exhausted(claim)
    assert row(engine,target_id)["submit_count"] == 0


def test_read_window_is_independent_of_shorter_public_retry_lifetime(engine):
    ids = seed(engine,state="processing",checkpoint={"processing_id":"container"})
    target_id = ids["targets"][0]
    read_history(engine,target_id,age_seconds=300)
    repo = repository(engine,retry_lifetime_seconds=60)
    claim = repo.claim_due()[0]
    assert intent(repo,claim,public=False,operation="poll",replay="read_only") is None
    assert row(engine,target_id)["next_action_at"]-datetime.now(timezone.utc) > timedelta(hours=23)


def test_imported_over_budget_history_waits_until_fewer_than_100_reads_remain(engine):
    ids = seed(engine,state="processing",checkpoint={"processing_id":"container"})
    target_id = ids["targets"][0]
    read_history(engine,target_id,count=15,age_seconds=2*3600)
    read_history(engine,target_id,count=100,age_seconds=60)
    repo = repository(engine)
    claim = repo.claim_due()[0]
    assert intent(repo,claim,public=False,operation="poll",replay="read_only") is None
    # Expiring just the oldest 15 would still leave 100 reads in the window.
    assert row(engine,target_id)["next_action_at"]-datetime.now(timezone.utc) > timedelta(hours=23)


def test_empty_queue_minimal_query_and_idle_heartbeat(engine):
    repo = repository(engine)
    statements = []
    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    sqlalchemy_event.listen(engine, "before_cursor_execute", observe)
    try:
        assert repo.claim_due(2) == []
        assert len(statements) == 1
        assert repo.next_due_delay(30) == 30
        repo.heartbeat(state="idle", active_claims=0, scanned=True)
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", observe)
    with engine.connect() as conn:
        heartbeat = conn.execute(text("SELECT state,last_scan_at,active_claims FROM social_worker_heartbeats")).one()
    assert heartbeat.state == "idle" and heartbeat.last_scan_at and heartbeat.active_claims == 0


def test_two_workers_skip_locked_and_bounded_claims(engine):
    ids = seed(engine, count=5)
    first, second = repository(engine), repository(engine)
    with engine.connect() as locked:
        transaction = locked.begin()
        locked.execute(text("SELECT id FROM social_post_targets WHERE id=:id FOR UPDATE"), {"id": ids["targets"][0]})
        start = time.monotonic()
        claims = second.claim_due(2)
        assert time.monotonic()-start < 2
        assert len(claims) == 2 and str(ids["targets"][0]) not in {c.target_id for c in claims}
        transaction.rollback()
    barrier = threading.Barrier(2)
    def claim(repo):
        barrier.wait()
        return repo.claim_due(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, (first, second)))
    claimed = [c.target_id for group in results for c in group]
    assert len(claimed) == 3 and len(set(claimed)) == 3
    assert all(set(c.__dict__) == {"target_id","account_id","publication_id","token","epoch","previous_state"} for group in results for c in group)


def test_restart_unsent_claim_is_recoverable_without_submission(engine):
    ids = seed(engine)
    original = repository(engine)
    claim = original.claim_due()[0]
    expire(engine, ids["targets"][0])
    fresh = repository(engine)
    assert fresh.recover_expired() == 1
    recovered = row(engine, ids["targets"][0])
    assert recovered["state"] == "queued" and recovered["submit_count"] == 0
    assert recovered["lease_token"] is None
    assert fresh.claim_due()[0].epoch == claim.epoch+1


def test_expired_dispatched_claim_holds_account_and_fences_late_receipt(engine):
    ids = seed(engine, count=2, same_account=True)
    repo = repository(engine)
    old = repo.claim_due()[0]
    old_intent = intent(repo, old)
    expire(engine, old.target_id)
    assert repo.recover_expired() == 1
    with engine.connect() as conn:
        hold = conn.execute(text("SELECT hold_reason FROM social_accounts WHERE id=:id"), {"id": ids["accounts"][0]}).scalar_one()
    assert hold == "RECONCILIATION_REQUIRED:"+old.target_id
    sibling = next(c for c in repo.claim_due(2) if c.target_id != old.target_id)
    assert intent(repo, sibling) is None
    assert row(engine, sibling.target_id)["state"] == "blocked"
    current = row(engine, old.target_id)
    assert current["state"] == "reconciling"
    assert not repo.finish(old, old_intent, state="published", outcome="confirmed_success",
        checkpoint={}, remote_refs={"post_id":"late-remote"}, remote_id="late-remote",
        visibility_state="public", confirmation_kind="receipt", receipt={"primary_remote_id":"late-remote"})
    assert row(engine, old.target_id)["state"] == "reconciling"
    with engine.connect() as conn:
        receipt = conn.execute(text("SELECT receipt FROM social_publish_attempts WHERE operation_id=:id"), {"id": old_intent.operation_id}).scalar_one()
    assert receipt["primary_remote_id"] == "late-remote"


def test_cancel_and_pause_before_permit_prevent_adapter_call(engine):
    ids = seed(engine, paused=True)
    fake = FakeAdapter()
    run_claim(repository(engine), fake)
    assert fake.calls == 0 and row(engine, ids["targets"][0])["state"] == "queued"
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_controls SET publishing_enabled=true"))
        conn.execute(text("UPDATE social_publications SET cancel_requested_at=now()"))
        conn.execute(text("UPDATE social_post_targets SET state='queued',next_action_at=now()"))
    run_claim(repository(engine), fake)
    assert fake.calls == 0 and row(engine, ids["targets"][0])["state"] == "cancelled"


def test_pause_committed_after_permit_cannot_erase_remote_confirmation(engine):
    ids = seed(engine)
    async def pause(operation):
        with engine.begin() as conn:
            # This executes while an adapter call is active: no row locks remain.
            conn.execute(text("UPDATE social_controls SET publishing_enabled=false"))
            persisted = conn.execute(text("SELECT dispatch_started_at FROM social_publish_attempts")).scalar_one()
            assert persisted is not None
    fake = FakeAdapter(gate=pause)
    run_claim(repository(engine), fake)
    assert fake.calls == 1 and row(engine, ids["targets"][0])["state"] == "published"


def test_missing_adapter_never_marks_success(engine):
    ids = seed(engine)
    run_claim(repository(engine))
    target = row(engine, ids["targets"][0])
    assert target["state"] == "blocked" and target["error_code"] == "ADAPTER_NOT_AVAILABLE"
    assert target["submit_count"] == 0 and target["published_at"] is None


def test_upload_checkpoint_and_processing_poll_do_not_republish(engine):
    ids = seed(engine)
    fake = FakeAdapter(upload_first=True, results=[
        OperationResult(outcome="confirmed_success", checkpoint={"upload_id":"saved-upload"}, remote_refs={"upload_id":"saved-upload"}),
        OperationResult(outcome="processing", checkpoint={"upload_id":"saved-upload", "processing_id":"job"}, remote_refs={"container_id":"job"}),
        OperationResult(outcome="confirmed_success", primary_remote_id="remote-1", visibility_state="public", confirmation_kind="status")])
    repo = repository(engine)
    run_claim(repo, fake)
    assert row(engine, ids["targets"][0])["state"] == "queued"
    assert row(engine, ids["targets"][0])["submit_count"] == 0
    due_now(engine, ids["targets"][0]); run_claim(repo, fake)
    assert row(engine, ids["targets"][0])["state"] == "processing"
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_controls SET publishing_enabled=false"))
    due_now(engine, ids["targets"][0]); run_claim(repo, fake)
    result = row(engine, ids["targets"][0])
    assert result["state"] == "published" and result["submit_count"] == 1
    assert result["checkpoint"]["upload_id"] == "saved-upload"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM social_publish_attempts")).scalar_one() == 3


def test_ambiguous_result_reconciles_without_blind_resend_while_paused(engine):
    ids = seed(engine)
    fake = FakeAdapter(results=[TimeoutError("secret raw failure")], reconcile_result=ReconciliationResult(
        outcome="confirmed_published", evidence={"match":"exact"}, result=OperationResult(outcome="confirmed_success",
        primary_remote_id="existing",visibility_state="public",confirmation_kind="reconciled")))
    repo = repository(engine)
    run_claim(repo, fake)
    assert row(engine, ids["targets"][0])["state"] == "reconciling"
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_controls SET publishing_enabled=false"))
    due_now(engine, ids["targets"][0]); run_claim(repo, fake)
    assert fake.calls == 1 and fake.reconciliations == 1
    assert row(engine, ids["targets"][0])["state"] == "published"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT hold_reason FROM social_accounts")).scalar_one() is None


def test_crash_after_permit_recovers_into_unknown_without_second_send(engine):
    ids = seed(engine)
    repo = repository(engine)
    claim = repo.claim_due()[0]
    assert intent(repo, claim)  # Crash boundary: durable intent, no local result.
    expire(engine, ids["targets"][0])
    replacement = repository(engine)
    assert replacement.recover_expired() == 1
    fake = FakeAdapter()
    run_claim(replacement, fake)
    assert fake.calls == 0 and fake.reconciliations == 1
    assert row(engine, ids["targets"][0])["state"] == "outcome_unknown"
    assert replacement.claim_due() == []


def test_independent_destinations_keep_success_and_retry_only_known_safe_failure(engine):
    ids = seed(engine, count=2)
    fake = FakeAdapter(results=[OperationResult(outcome="confirmed_success",primary_remote_id="done",visibility_state="public",confirmation_kind="receipt"),
        OperationResult(outcome="definite_failure",error_code="RATE_LIMITED",retry_safe=True,
                        next_action_at=datetime.now(timezone.utc)+timedelta(hours=2))])
    repo = repository(engine)
    run_claim(repo, fake); run_claim(repo, fake)
    targets = [row(engine, target) for target in ids["targets"]]
    assert {t["state"] for t in targets} == {"published", "retry_wait"}
    retry = next(t for t in targets if t["state"] == "retry_wait")
    assert retry["next_action_at"] > datetime.now(timezone.utc)+timedelta(hours=1,minutes=59)
    published = next(t for t in targets if t["state"] == "published")
    due_now(engine, retry["id"])
    fake.results.append(OperationResult(outcome="confirmed_success",primary_remote_id="retried",visibility_state="public",confirmation_kind="receipt"))
    run_claim(repo, fake)
    assert row(engine, published["id"])["submit_count"] == 1
    assert row(engine, retry["id"])["submit_count"] == 2


def test_malformed_checkpoint_is_executed_and_fails_closed(engine):
    ids = seed(engine, checkpoint=["invalid"])
    fake = FakeAdapter()
    run_claim(repository(engine), fake)
    assert fake.calls == 0 and row(engine, ids["targets"][0])["state"] == "failed"


def test_database_account_admission_prevents_two_mutations(engine):
    seed(engine, count=2, same_account=True)
    repo = repository(engine)
    one, two = repo.claim_due(2)
    first = intent(repo, one)
    assert first is not None
    assert intent(repo, two) is None
    assert row(engine, two.target_id)["state"] == "queued"
    assert row(engine, two.target_id)["submit_count"] == 0
    assert repo.renew(one)
    with engine.connect() as conn:
        account = conn.execute(text("SELECT publish_lease_target_id,publish_lease_token,publish_lease_expires_at FROM social_accounts")).one()
    assert str(account.publish_lease_target_id) == one.target_id
    assert str(account.publish_lease_token) == one.token
    assert account.publish_lease_expires_at > datetime.now(timezone.utc)


def test_mutation_transaction_acquires_documented_lock_order(engine):
    seed(engine)
    repo = repository(engine)
    claim = repo.claim_due()[0]
    locked_tables = []
    def observe(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement:
            locked_tables.append(statement.split("FROM ")[1].split()[0])
    sqlalchemy_event.listen(engine, "before_cursor_execute", observe)
    try:
        assert intent(repo, claim)
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", observe)
    assert locked_tables == ["social_controls", "social_accounts", "social_publications", "social_post_targets"]


@pytest.mark.parametrize("column", ["start_deadline", "content_valid_until"])
def test_authoritative_deadline_prevents_late_new_send(engine, column):
    ids = seed(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_publications SET "+column+"=now()-interval '1 second'"))
    fake = FakeAdapter()
    run_claim(repository(engine), fake)
    assert fake.calls == 0 and row(engine, ids["targets"][0])["state"] == "blocked"


def test_false_or_incomplete_success_receipt_never_marks_publication(engine):
    ids = seed(engine)
    fake = FakeAdapter(results=[OperationResult(outcome="confirmed_success", primary_remote_id="container")])
    run_claim(repository(engine), fake)
    target = row(engine, ids["targets"][0])
    assert target["state"] == "processing" and target["published_at"] is None


def test_submissions_are_bounded_to_five(engine):
    ids = seed(engine)
    fake = FakeAdapter(results=[OperationResult(outcome="definite_failure",error_code="TEMPORARY_REJECTION",retry_safe=True)]*5)
    repo = repository(engine)
    for index in range(5):
        run_claim(repo, fake)
        target = row(engine, ids["targets"][0])
        assert target["submit_count"] == index+1
        assert target["state"] == ("blocked" if index == 4 else "retry_wait")
        if index < 4:
            due_now(engine, target["id"])
    assert fake.calls == 5 and repo.claim_due() == []


def test_content_capability_and_media_gates_fail_closed(engine):
    ids = seed(engine)
    with engine.begin() as conn:
        conn.execute(SocialAccount.__table__.update().values(granted_scopes=[]))
    fake = FakeAdapter()
    run_claim(repository(engine), fake)
    assert fake.calls == 0
    assert row(engine, ids["targets"][0])["error_code"] == "PERMISSION_DENIED"


def test_synchronous_database_operations_do_not_block_async_loop(engine):
    seed(engine)
    repo = repository(engine)
    real_load = repo.load
    def slow_load(claim):
        time.sleep(0.15)
        return real_load(claim)
    repo.load = slow_load
    async def execute():
        worker = SocialWorker(repo, adapters={("facebook", "fake"): FakeAdapter()})
        ticks = 0
        finished = asyncio.Event()
        async def ticker():
            nonlocal ticks
            while not finished.is_set():
                ticks += 1
                await asyncio.sleep(0.005)
        ticker_task = asyncio.create_task(ticker())
        try:
            claim = (await worker.db(repo.claim_due))[0]
            await worker.process(claim)
        finally:
            finished.set()
            await ticker_task
            await worker.close()
        assert ticks >= 10
    asyncio.run(execute())


def test_completion_database_failure_survives_restart_as_reconciliation(engine, caplog):
    ids = seed(engine)
    repo = repository(engine)
    original_finish = repo.finish
    def unavailable(*args, **kwargs):
        raise RuntimeError("SECRET database connection string")
    repo.finish = unavailable
    fake = FakeAdapter()
    run_claim(repo, fake)
    target = row(engine, ids["targets"][0])
    assert fake.calls == 1 and target["state"] == "dispatching"
    assert "SECRET" not in caplog.text
    expire(engine, ids["targets"][0])
    fresh = repository(engine)
    assert fresh.recover_expired() == 1
    fake.reconcile_result = ReconciliationResult(outcome="confirmed_published", evidence={"match":"exact"},
        result=OperationResult(outcome="confirmed_success", primary_remote_id="remote-1", visibility_state="public", confirmation_kind="reconciliation"))
    run_claim(fresh, fake)
    assert fake.calls == 1 and row(engine, ids["targets"][0])["state"] == "published"


def test_actual_process_kill_after_fake_remote_acceptance_recovers_without_republish(engine, tmp_path):
    import subprocess
    import sys
    ids = seed(engine)
    ledger = tmp_path / "fake-remote-receipt.txt"
    script = r'''
import asyncio, os, sys
from uuid import uuid4
from social.contracts import CapabilitySet, OperationPlan, ValidationResult
from social.worker.config import WorkerConfig,create_worker_engine
from social.worker.repository import QueueRepository
from social.worker.runner import SocialWorker
class ExplicitTestAdapter:
    def capabilities(self,account): return CapabilitySet.model_validate(account['capability_snapshot'])
    def validate(self,payload,capabilities): return ValidationResult(valid=True)
    def next_operation(self,payload,checkpoint):
        return OperationPlan(operation_id=uuid4(),operation='publish',publication_capable=True,safe_replay_class='requires_reconciliation',checkpoint=checkpoint)
    async def execute(self,payload,operation,credential,media_access):
        with open(sys.argv[1],'a') as receipt:
            receipt.write('accepted-remote-id\n'); receipt.flush(); os.fsync(receipt.fileno())
        print('REMOTE_ACCEPTED',flush=True)
        await asyncio.Event().wait()
config=WorkerConfig(os.environ['SOCIAL_WORKER_TEST_DATABASE_URL'])
engine=create_worker_engine(config)
repo=QueueRepository(engine,config,uuid4())
worker=SocialWorker(repo,adapters={('facebook','fake'):ExplicitTestAdapter()})
async def run():
    claim=(await worker.db(repo.claim_due))[0]
    await worker.process(claim)
asyncio.run(run())
'''
    child_env = os.environ.copy()
    # Preserve the endpoint already validated and pinned by the parent fixture.
    # Re-reading the raw DSN would reintroduce libpq environment redirection.
    child_env['SOCIAL_WORKER_TEST_DATABASE_URL'] = engine.url.render_as_string(hide_password=False)
    child = subprocess.Popen([sys.executable, "-c", script, str(ledger)], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=child_env)
    try:
        import select
        readable, _, _ = select.select([child.stdout], [], [], 10)
        assert readable, "Child did not reach the remote-acceptance crash boundary"
        assert child.stdout.readline().strip() == "REMOTE_ACCEPTED"
        child.kill()
        child.wait(timeout=5)
    finally:
        if child.poll() is None:
            child.kill(); child.wait(timeout=5)
        child.stdout.close(); child.stderr.close()
    assert ledger.read_text() == "accepted-remote-id\n"
    assert row(engine, ids["targets"][0])["state"] == "dispatching"
    expire(engine, ids["targets"][0])
    repo = repository(engine)
    assert repo.recover_expired() == 1
    adapter = FakeAdapter(reconcile_result=ReconciliationResult(outcome="confirmed_published", evidence={"receipt":"exact"},
        result=OperationResult(outcome="confirmed_success",primary_remote_id="accepted-remote-id",visibility_state="public",confirmation_kind="reconciled")))
    run_claim(repo, adapter)
    assert adapter.calls == 0 and adapter.reconciliations == 1
    assert ledger.read_text() == "accepted-remote-id\n"
    assert row(engine, ids["targets"][0])["state"] == "published"


def test_pause_resume_retains_schedule_and_checks_deadline_again(engine):
    ids = seed(engine, paused=True)
    fake = FakeAdapter()
    repo = repository(engine)
    run_claim(repo, fake)
    paused = row(engine, ids["targets"][0])
    assert paused["state"] == "queued" and paused["error_code"] == "PUBLISHING_PAUSED"
    assert paused["checkpoint"] == {} and paused["submit_count"] == 0
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_controls SET publishing_enabled=true"))
    due_now(engine, ids["targets"][0]); run_claim(repo, fake)
    assert fake.calls == 1 and row(engine, ids["targets"][0])["state"] == "published"


def test_pause_past_start_deadline_does_not_publish_stale_announcement(engine):
    ids = seed(engine, paused=True)
    fake = FakeAdapter()
    repo = repository(engine)
    run_claim(repo, fake)
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_controls SET publishing_enabled=true"))
        conn.execute(text("UPDATE social_publications SET start_deadline=now()-interval '1 second'"))
    due_now(engine, ids["targets"][0]); run_claim(repo, fake)
    assert fake.calls == 0
    assert row(engine, ids["targets"][0])["error_code"] == "START_DEADLINE_EXCEEDED"


def test_expired_account_admission_blocks_sibling_even_before_recovery_scan(engine):
    seed(engine, count=2, same_account=True)
    repo = repository(engine)
    old, sibling = repo.claim_due(2)
    assert intent(repo, old)
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_accounts SET publish_lease_expires_at=now()-interval '1 second'"))
    assert intent(repo, sibling) is None
    assert row(engine, sibling.target_id)["error_code"] == "ACCOUNT_RECONCILIATION_REQUIRED"


def test_definite_failure_receipt_retains_api_retry_safety_predicate(engine):
    ids = seed(engine)
    repo = repository(engine)
    fake = FakeAdapter(results=[OperationResult(outcome="definite_failure",error_code="INVALID_MEDIA",retry_safe=True)])
    run_claim(repo, fake)
    with engine.connect() as conn:
        attempt = conn.execute(text("SELECT outcome,receipt FROM social_publish_attempts ORDER BY sequence DESC LIMIT 1")).mappings().one()
    assert row(engine, ids["targets"][0])["state"] == "failed"
    # Exact predicate consumed by SocialService.retry, with typed evidence only.
    assert attempt["outcome"] == "definite_failure" and attempt["receipt"]["retry_safe"] is True


def test_poll_exception_keeps_processing_checkpoint_and_never_resubmits(engine):
    ids = seed(engine, state="processing", checkpoint={"processing_id":"accepted-job"})
    fake = FakeAdapter(results=[TimeoutError("provider read failed")])
    repo = repository(engine)
    run_claim(repo, fake)
    target = row(engine, ids["targets"][0])
    assert target["state"] == "processing" and target["checkpoint"]["processing_id"] == "accepted-job"
    assert target["submit_count"] == 0 and target["next_action"] == "poll"


def test_reconciliation_receives_original_mutation_late_evidence_not_its_last_read(engine):
    ids = seed(engine)
    repo = repository(engine)
    claim = repo.claim_due()[0]
    public_intent = intent(repo, claim)
    expire(engine, claim.target_id)
    repo.recover_expired()
    reconciler = repo.claim_due()[0]
    read_intent = intent(repo, reconciler, public=False,operation="reconcile",replay="read_only")
    expire(engine, reconciler.target_id)
    repo.recover_expired()
    repo.finish(claim, public_intent, state="published",outcome="confirmed_success",checkpoint={},remote_refs={},
        remote_id="late-id",receipt={"primary_remote_id":"late-id"})
    fresh = repo.claim_due()[0]
    snapshot = repo.load(fresh)
    assert str(snapshot["last_attempt"]["operation_id"]) == public_intent.operation_id
    assert snapshot["last_attempt"]["receipt"]["primary_remote_id"] == "late-id"


def test_database_failure_before_permit_sends_nothing(engine):
    ids = seed(engine)
    repo = repository(engine)
    def fail(*args, **kwargs):
        raise RuntimeError("do not print secret DB DSN")
    repo.begin_operation = fail
    fake = FakeAdapter()
    run_claim(repo, fake)
    assert fake.calls == 0 and row(engine, ids["targets"][0])["submit_count"] == 0


def test_repository_direct_public_permit_cannot_bypass_mutation_gate(engine):
    seed(engine, paused=True)
    repo = repository(engine)
    claim = repo.claim_due()[0]
    with pytest.raises(ValueError):
        repo.begin_operation(claim,operation_id=uuid4(),operation="publish",publication_capable=True,
            mutating=False,safe_replay_class="requires_reconciliation",request_fingerprint="a"*64,checkpoint_input={})
    with pytest.raises(ValueError):
        repo.claim_due(True)
    assert row(engine, claim.target_id)["submit_count"] == 0


def test_repository_direct_completion_rejects_false_success_and_fake_intent(engine):
    seed(engine)
    repo = repository(engine)
    claim = repo.claim_due()[0]
    real = intent(repo,claim)
    with pytest.raises(ValueError):
        repo.finish(claim,real,state="published",outcome="definite_failure",checkpoint={},remote_refs={},
                    remote_id="truthy-error",visibility_state="public",confirmation_kind="failure-receipt")
    from social.worker.repository import Intent
    assert not repo.finish(claim,Intent(str(uuid4()),1,None),state="published",outcome="confirmed_success",
        checkpoint={},remote_refs={},remote_id="invented",visibility_state="public",confirmation_kind="fabricated")
    assert row(engine,claim.target_id)["state"] == "dispatching"


def test_permit_rechecks_database_clock_after_waiting_for_control_lock(engine):
    seed(engine)
    repo = repository(engine)
    claim = repo.claim_due()[0]
    snapshot = repo.load(claim)
    waiting = threading.Event()
    def observe(conn,cursor,statement,parameters,context,executemany):
        if "social_controls" in statement and "FOR UPDATE" in statement:
            waiting.set()
    sqlalchemy_event.listen(engine,"before_cursor_execute",observe)
    try:
        with engine.connect() as blocker:
            transaction = blocker.begin()
            blocker.execute(text("SELECT id FROM social_controls FOR UPDATE"))
            waiting.clear()
            blocker.execute(text("UPDATE social_post_targets SET lease_expires_at=clock_timestamp()+interval '100 milliseconds' WHERE id=CAST(:id AS uuid)"), {"id": claim.target_id})
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(repo.begin_operation,claim,operation_id=uuid4(),operation="publish",
                    publication_capable=True,mutating=True,safe_replay_class="requires_reconciliation",
                    request_fingerprint="a"*64,checkpoint_input=snapshot["checkpoint"])
                assert waiting.wait(timeout=2)
                time.sleep(0.2)
                transaction.commit()
                with pytest.raises(LeaseLost):
                    pending.result(timeout=3)
        assert row(engine,claim.target_id)["submit_count"] == 0
    finally:
        sqlalchemy_event.remove(engine,"before_cursor_execute",observe)


def test_nonpublic_upload_completion_cannot_be_presented_as_publication(engine):
    seed(engine)
    repo = repository(engine)
    claim = repo.claim_due()[0]
    upload = intent(repo,claim,public=False,operation="upload")
    with pytest.raises(ValueError):
        repo.finish(claim,upload,state="published",outcome="confirmed_success",checkpoint={},remote_refs={},
            remote_id="photo-id",visibility_state="public",confirmation_kind="upload-only")
    assert row(engine,claim.target_id)["state"] == "claimed"


def test_charged_status_read_is_blocked_without_budget_reservation(engine):
    seed(engine,state="processing",checkpoint={"processing_id":"paid-job"})
    repo = repository(engine)
    claim = repo.claim_due()[0]
    assert repo.begin_operation(claim,operation_id=uuid4(),operation="poll",publication_capable=False,
        mutating=False,safe_replay_class="read_only",request_fingerprint="a"*64,
        checkpoint_input={"processing_id":"paid-job"},estimated_cost_microusd=1) is None
    assert row(engine,claim.target_id)["error_code"] == "BUDGET_RESERVATION_UNAVAILABLE"
    assert row(engine,claim.target_id)["submit_count"] == 0


def test_worker_failure_receipt_allows_real_domain_retry_command(engine):
    from social.contracts import CreatePost,ControlsCommand,PublishCommand,RetryCommand
    from social.service import SocialService
    account_id = uuid4()
    caps = CapabilitySet(eligible=True,supported_formats=("text",),feature_states={"publishing":"supported"},
                         price_class="free",adapter_available=True,provider_api_version="fake-v1")
    with Session(engine) as db:
        db.add(SocialAccount(id=account_id,platform="facebook",api_product="fake",connection_method="fixture",
            external_account_id="API-compatible",display_name="Fixture",connection_state="connected",
            publishing_enabled=True,granted_scopes=[],capability_snapshot=caps.model_dump(mode="json")))
        db.commit()
        svc = SocialService(db,available_adapters={"facebook"})
        actor = uuid4()
        def command(body,action,route):
            return svc.command(actor=actor,route=route,key=uuid4(),request_id=uuid4(),
                body=body.model_dump(mode="json"),action=action)[1]
        body = CreatePost(title="Receipt compatibility",document={"master":{"text":"Verified test"},
            "targets":[{"account_id":account_id,"format":"text"}]})
        created = command(body,lambda:svc.create(body),"posts.create")
        controls = ControlsCommand(expected_version=1,publishing_enabled=True,reason="Explicit fake test")
        command(controls,lambda:svc.controls(controls),"controls.update")
        publish = PublishCommand(expected_version=1,revision_id=created["revision_id"])
        accepted = command(publish,lambda:svc.publish(created["id"],publish),"posts.publish")
    target_id = accepted["targets"][0]["id"]
    repo = repository(engine)
    adapter = FakeAdapter(results=[OperationResult(outcome="definite_failure",error_code="INVALID_MEDIA",retry_safe=True)])
    run_claim(repo,adapter)
    assert row(engine,target_id)["state"] == "failed"
    with Session(engine) as db:
        svc = SocialService(db,available_adapters={"facebook"})
        retry = RetryCommand(reason="Known-safe destination retry")
        status,result = svc.command(actor=actor,route="targets.retry",key=uuid4(),request_id=uuid4(),
            body=retry.model_dump(mode="json"),action=lambda:svc.retry(target_id,retry))
    assert status == 200 and result["targets"][0]["state"] == "retry_wait"
    adapter.results.append(OperationResult(outcome="confirmed_success",primary_remote_id="after-manual-retry",visibility_state="public",confirmation_kind="receipt"))
    run_claim(repo,adapter)
    assert row(engine,target_id)["state"] == "published" and adapter.calls == 2


def test_contradictory_validation_verdict_is_not_a_publication_permission(engine):
    from social.contracts import ValidationIssue
    ids = seed(engine)
    class ContradictoryAdapter(FakeAdapter):
        def validate(self,payload,capabilities):
            return ValidationResult(valid=True,errors=(ValidationIssue(code="INVALID",field="text",message="Invalid"),))
    fake = ContradictoryAdapter()
    run_claim(repository(engine),fake)
    assert fake.calls == 0 and row(engine,ids["targets"][0])["state"] == "failed"


def test_duplicate_unresolved_public_permit_on_same_claim_is_rejected(engine):
    seed(engine)
    repo = repository(engine)
    claim = repo.claim_due()[0]
    assert intent(repo,claim)
    from social.worker.repository import GateRejected
    with pytest.raises(GateRejected,match="OPERATION_ALREADY_STARTED"):
        intent(repo,claim)
    assert row(engine,claim.target_id)["submit_count"] == 1


def test_direct_finish_rejects_whitespace_public_evidence(engine):
    seed(engine)
    repo = repository(engine)
    claim = repo.claim_due()[0]
    public = intent(repo,claim)
    with pytest.raises(ValueError):
        repo.finish(claim,public,state="published",outcome="confirmed_success",checkpoint={},remote_refs={},
            remote_id=" ",visibility_state="public",confirmation_kind=" ")
    assert row(engine,claim.target_id)["state"] == "dispatching"


def test_unselected_account_with_self_consistent_unapproved_payload_has_no_permit(engine):
    ids = seed(engine)
    account_id,target_id = uuid4(),uuid4()
    with Session(engine) as db:
        account = db.get(SocialAccount,ids["accounts"][0])
        db.add(SocialAccount(id=account_id,platform=account.platform,api_product="fake",connection_method="fixture",
            external_account_id="unauthorized-B",display_name="B",connection_state="connected",publishing_enabled=True,
            granted_scopes=["publish"],capability_snapshot=account.capability_snapshot))
        db.flush()
        payload = ResolvedPostPayload(account_id=account_id,platform="facebook",api_product="fake",
            external_account_id="unauthorized-B",format="text",text="UNAPPROVED DIFFERENT COPY",
            evidence_hash="f"*64,content_hash="0"*64)
        payload = payload.model_copy(update={"content_hash":canonical_hash(payload.model_dump(mode="json",exclude={"content_hash"}))})
        db.add(SocialPostTarget(id=target_id,publication_id=ids["publication"],account_id=account_id,
            resolved_payload=payload.model_dump(mode="json"),payload_hash=payload.content_hash,capability_version="social-v1",
            state="queued",next_action="publish",next_action_at=datetime.now(timezone.utc)))
        db.commit()
    repo = repository(engine)
    claim = next(c for c in repo.claim_due(2) if c.target_id == str(target_id))
    assert intent(repo,claim) is None
    assert row(engine,target_id)["error_code"] == "TARGET_NOT_AUTHORIZED"
    assert row(engine,target_id)["submit_count"] == 0


@pytest.mark.parametrize("field,value",[("text","UNAPPROVED COPY"),("evidence_hash","f"*64),("hashtags",["unapproved"])])
def test_selected_target_payload_must_match_approved_revision_even_with_valid_hash(engine,field,value):
    ids = seed(engine)
    target = row(engine,ids["targets"][0])
    payload = dict(target["resolved_payload"])
    payload[field] = value
    payload["content_hash"] = canonical_hash({k:v for k,v in payload.items() if k != "content_hash"})
    with engine.begin() as conn:
        # create_all fixture intentionally has no migration trigger; this attacks
        # the worker itself, even if a privileged writer bypassed schema guards.
        conn.execute(SocialPostTarget.__table__.update().where(SocialPostTarget.id == target["id"]).values(
            resolved_payload=payload,payload_hash=payload["content_hash"]))
    repo = repository(engine)
    assert intent(repo,repo.claim_due()[0]) is None
    assert row(engine,target["id"])["error_code"] == "PAYLOAD_REVISION_MISMATCH"


def test_other_selected_account_failure_does_not_block_independent_valid_permit(engine):
    ids = seed(engine,count=2)
    with engine.begin() as conn:
        conn.execute(SocialAccount.__table__.update().where(SocialAccount.id == ids["accounts"][1]).values(connection_state="revoked"))
    repo = repository(engine)
    valid = next(c for c in repo.claim_due(2) if c.account_id == str(ids["accounts"][0]))
    assert intent(repo,valid) is not None


@pytest.mark.parametrize("field",["account_id","publication_id"])
def test_lease_identity_cannot_be_forged_to_lock_a_different_authorization(engine,field):
    from dataclasses import replace
    seed(engine)
    repo = repository(engine)
    claim = repo.claim_due()[0]
    forged = replace(claim,**{field:str(uuid4())})
    with pytest.raises(LeaseLost):
        intent(repo,forged)
    assert row(engine,claim.target_id)["submit_count"] == 0


def test_claim_audit_does_not_deadlock_against_account_then_target_lock_order(engine):
    ids = seed(engine)
    repo = repository(engine)
    auditing = threading.Event()
    def observe(conn,cursor,statement,parameters,context,executemany):
        if "INSERT INTO social_audit_events" in statement:
            auditing.set()
    sqlalchemy_event.listen(engine,"before_cursor_execute",observe)
    try:
        with engine.connect() as blocker:
            transaction = blocker.begin()
            blocker.execute(text("SET LOCAL deadlock_timeout='100ms'"))
            blocker.execute(text("SET LOCAL lock_timeout='2s'"))
            blocker.execute(text("SELECT id FROM social_accounts WHERE id=:id FOR UPDATE"),{"id":ids["accounts"][0]})
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(repo.claim_due)
                assert auditing.wait(timeout=2)
                # Permit/cancel ordering is already holding the account row; a
                # claim owns target first, so cross-row audit FKs must not wait.
                time.sleep(0.05)
                blocker.execute(text("SELECT id FROM social_post_targets WHERE id=:id FOR UPDATE"),{"id":ids["targets"][0]})
                transaction.commit()
                assert len(pending.result(timeout=3)) == 1
        with engine.connect() as conn:
            audit = conn.execute(text("SELECT post_id,account_id,target_id,details FROM social_audit_events WHERE action='target_claimed'")).mappings().one()
        assert audit["post_id"] is None and audit["account_id"] is None
        assert audit["target_id"] == ids["targets"][0]
        assert audit["details"]["account_id"] == str(ids["accounts"][0])
        assert audit["details"]["publication_id"] == str(ids["publication"])
    finally:
        sqlalchemy_event.remove(engine,"before_cursor_execute",observe)


def test_failed_incomplete_absence_lookup_never_authorizes_resend(engine):
    ids = seed(engine)
    repo = repository(engine)
    fake = FakeAdapter(results=[TimeoutError("uncertain publication")],reconcile_result=ReconciliationResult(
        outcome="definitively_unpublished",evidence={"lookup_succeeded":False,"complete":False,"matches":[]}))
    run_claim(repo,fake)
    due_now(engine,ids["targets"][0]); run_claim(repo,fake)
    target=row(engine,ids["targets"][0])
    assert target["state"] == "outcome_unknown"
    assert target["submit_count"] == 1 and fake.calls == 1 and repo.claim_due() == []
    with engine.connect() as conn:
        assert conn.execute(text("SELECT hold_reason FROM social_accounts")).scalar_one() is not None


@pytest.mark.parametrize("kind",["provider_definitive_status","confirmed_not_sent"])
def test_verified_complete_original_mutation_absence_proof_allows_bounded_retry(engine,kind):
    ids = seed(engine)
    repo = repository(engine)
    class ProvedAbsentAdapter(FakeAdapter):
        async def reconcile(self,payload,checkpoint,attempt,credential,media_access):
            self.reconciliations += 1
            return ReconciliationResult(outcome="definitively_unpublished",absence_proof={
                "kind":kind,"verified":True,"coverage_complete":True,
                "account_id":payload.account_id,"operation_id":attempt["operation_id"]})
    fake = ProvedAbsentAdapter(results=[TimeoutError("uncertain")])
    run_claim(repo,fake)
    due_now(engine,ids["targets"][0]); run_claim(repo,fake)
    target=row(engine,ids["targets"][0])
    assert target["state"] == "retry_wait" and target["submit_count"] == 1
    with engine.connect() as conn:
        assert conn.execute(text("SELECT hold_reason FROM social_accounts")).scalar_one() is None
        proof=conn.execute(text("SELECT receipt->'absence_proof' FROM social_publish_attempts WHERE operation='reconcile'")).scalar_one()
    assert proof["kind"] == kind and proof["verified"] is True and proof["coverage_complete"] is True
    fake.results.append(OperationResult(outcome="confirmed_success",primary_remote_id="safe-retry",visibility_state="public",confirmation_kind="receipt"))
    due_now(engine,ids["targets"][0]); run_claim(repo,fake)
    assert fake.calls == 2 and row(engine,ids["targets"][0])["state"] == "published"


@pytest.mark.parametrize("mismatch",["account_id","operation_id"])
def test_absence_proof_for_wrong_account_or_operation_stays_unknown(engine,mismatch):
    ids=seed(engine)
    repo=repository(engine)
    class WrongProofAdapter(FakeAdapter):
        async def reconcile(self,payload,checkpoint,attempt,credential,media_access):
            proof={"kind":"confirmed_not_sent","verified":True,"coverage_complete":True,
                   "account_id":payload.account_id,"operation_id":attempt["operation_id"]}
            proof[mismatch]=uuid4()
            return ReconciliationResult(outcome="definitively_unpublished",absence_proof=proof)
    fake=WrongProofAdapter(results=[TimeoutError("uncertain")])
    run_claim(repo,fake)
    due_now(engine,ids["targets"][0]); run_claim(repo,fake)
    assert row(engine,ids["targets"][0])["state"] == "outcome_unknown" and fake.calls == 1
    with engine.connect() as conn:
        assert conn.execute(text("SELECT hold_reason FROM social_accounts")).scalar_one() is not None


@pytest.mark.parametrize("field,value",[("verified",False),("coverage_complete",False),("verified",1),("kind","incomplete_page_lookup")])
def test_malformed_absence_proof_completes_read_as_unknown_without_resend(engine,field,value):
    ids=seed(engine)
    repo=repository(engine)
    class MalformedProofAdapter(FakeAdapter):
        async def reconcile(self,payload,checkpoint,attempt,credential,media_access):
            proof={"kind":"confirmed_not_sent","verified":True,"coverage_complete":True,
                   "account_id":str(payload.account_id),"operation_id":str(attempt["operation_id"])}
            proof[field]=value
            return {"outcome":"definitively_unpublished","absence_proof":proof}
    fake=MalformedProofAdapter(results=[TimeoutError("uncertain")])
    run_claim(repo,fake)
    due_now(engine,ids["targets"][0]); run_claim(repo,fake)
    target=row(engine,ids["targets"][0])
    assert target["state"] == "outcome_unknown" and target["error_code"] == "INVALID_RECONCILIATION_PROOF"
    assert target["lease_token"] is None and fake.calls == 1
    with engine.connect() as conn:
        assert conn.execute(text("SELECT completed_at FROM social_publish_attempts WHERE operation='reconcile'")).scalar_one() is not None


def test_repository_reconciliation_retry_cannot_use_generic_truthy_evidence(engine):
    ids=seed(engine)
    repo=repository(engine)
    original=repo.claim_due()[0]
    intent(repo,original)
    expire(engine,original.target_id); repo.recover_expired()
    claim=repo.claim_due()[0]
    read=intent(repo,claim,public=False,operation="reconcile",replay="read_only")
    assert repo.finish(claim,read,state="retry_wait",outcome="definite_failure",checkpoint={},remote_refs={},
        receipt={"retry_safe":True,"reconciliation_evidence":{"complete":False}},delay=0,next_action="publish")
    assert row(engine,ids["targets"][0])["state"] == "outcome_unknown" and repo.claim_due() == []


def test_verified_absence_releases_account_hold_even_when_retry_deadline_exhausted(engine):
    ids=seed(engine)
    repo=repository(engine)
    class ProvenAbsent(FakeAdapter):
        async def reconcile(self,payload,checkpoint,attempt,credential,media_access):
            return ReconciliationResult(outcome="definitively_unpublished",absence_proof={
                "kind":"confirmed_not_sent","verified":True,"coverage_complete":True,
                "account_id":payload.account_id,"operation_id":attempt["operation_id"]})
    fake=ProvenAbsent(results=[TimeoutError("uncertain")])
    run_claim(repo,fake)
    with engine.begin() as conn:
        conn.execute(text("UPDATE social_publications SET retry_deadline=clock_timestamp()-interval '1 second'"))
    due_now(engine,ids["targets"][0]); run_claim(repo,fake)
    assert row(engine,ids["targets"][0])["state"] == "blocked" and fake.calls == 1
    with engine.connect() as conn:
        assert conn.execute(text("SELECT hold_reason FROM social_accounts")).scalar_one() is None

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
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from social.contracts import CapabilitySet, OperationPlan, OperationResult, ReconciliationResult, ResolvedPostPayload, ValidationResult, canonical_hash
from social.models import SOCIAL_TABLES, SocialAccount, SocialControls, SocialPost, SocialPostRevision, SocialPublication, SocialPostTarget
from social.worker.config import WorkerConfig, create_worker_engine
from social.worker.repository import QueueRepository, LeaseLost
from social.worker.runner import SocialWorker


@pytest.fixture
def engine():
    dsn = os.environ.get("SOCIAL_WORKER_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set an explicit isolated local worker test DSN")
    url = make_url(dsn)
    if url.host not in ("127.0.0.1", "localhost", "::1") or url.database != "social_worker_test":
        pytest.fail("Worker tests require the dedicated local social_worker_test database")
    config = WorkerConfig(dsn)
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
        document = {"schema_version": 1, "master": {"text": "fixture", "link": None, "hashtags": [], "media": []}, "targets": []}
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
    async def reconcile(self, payload, checkpoint, attempt):
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
        conn.execute(text("UPDATE social_accounts SET granted_scopes='[]'::jsonb"))
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
    child = subprocess.Popen([sys.executable, "-c", script, str(ledger)], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=os.environ.copy())
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

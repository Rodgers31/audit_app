"""Admin admission uses current database time after a forced lock wait."""
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
import time
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from social.contracts import PublishCommand, ResumeCommand, VersionCommand
from social.service import SocialError
from social.worker.config import WorkerConfig
from social.worker.repository import LeaseLost, QueueRepository
from test_domain_commands import enable, make
from test_domain_postgres import pg_engine
from test_domain_support import account, call


def queued_publication(engine):
    with Session(engine, expire_on_commit=False) as db:
        destination = account(db)
        enable(db)
        created = make(db, (destination,))
        post_id = UUID(created["id"])
        publish = PublishCommand(expected_version=1, revision_id=created["revision_id"])
        _, accepted = call(db, publish, lambda svc: svc.publish(post_id, publish), route="publish")
    return post_id, created["revision_id"], UUID(accepted["publication_id"])


def cancel(engine, post_id):
    with Session(engine) as db:
        body = VersionCommand(expected_version=2)
        call(db, body, lambda svc: svc.cancel(post_id, body), route="cancel")


def resume(engine, post_id, revision_id, backend_pid=None):
    with engine.connect() as conn:
        if backend_pid is not None:
            backend_pid.put(conn.execute(text("SELECT pg_backend_pid()")).scalar_one())
            conn.rollback()
        with Session(conn) as db:
            body = ResumeCommand(expected_version=3, revision_id=revision_id, reason="Resume unchanged local fixture")
            return call(db, body, lambda svc: svc.resume(post_id, body), route="resume", status=202)


def test_resume_refuses_authorization_that_expires_while_waiting_for_controls_lock(pg_engine):
    post_id, revision_id, publication_id = queued_publication(pg_engine)
    cancel(pg_engine, post_id)
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        with pg_engine.connect() as blocker:
            transaction = blocker.begin()
            blocker.execute(text("SELECT id FROM social_controls WHERE id=1 FOR UPDATE"))
            backend_pid = Queue()
            future = pool.submit(resume, pg_engine, post_id, revision_id, backend_pid)
            pid = backend_pid.get(timeout=3)
            try:
                limit = time.monotonic()+3
                while time.monotonic() < limit:
                    with pg_engine.connect() as observer:
                        waiting = observer.execute(text("""
                            SELECT EXISTS(SELECT 1 FROM pg_stat_activity
                              WHERE pid=:pid AND wait_event_type='Lock'
                                AND query LIKE '%social_controls%')
                        """), {"pid":pid}).scalar_one()
                    if waiting:
                        break
                    time.sleep(.005)
                assert waiting, "Resume did not enter the forced controls-lock wait"
                # The observed transaction began before expiry. Keep the lock
                # until the authoritative database clock is definitely past it.
                with pg_engine.begin() as observer:
                    observer.execute(text("UPDATE social_publications SET start_deadline=clock_timestamp()+interval '150 milliseconds' WHERE id=:id"), {"id":publication_id})
                    assert observer.execute(text("SELECT now()<start_deadline FROM social_publications WHERE id=:id"), {"id":publication_id}).scalar_one()
                while time.monotonic() < limit:
                    with pg_engine.connect() as observer:
                        expired = observer.execute(text("SELECT clock_timestamp()>start_deadline FROM social_publications WHERE id=:id"), {"id":publication_id}).scalar_one()
                    if expired:
                        break
                    time.sleep(.005)
                assert expired, "The fixture deadline did not expire during the lock wait"
            finally:
                transaction.commit()
            with pytest.raises(SocialError, match="AUTHORIZATION_EXPIRED"):
                future.result(timeout=3)
        with pg_engine.connect() as conn:
            assert conn.execute(text("SELECT cancel_requested_at IS NOT NULL FROM social_publications WHERE id=:id"), {"id":publication_id}).scalar_one()
            assert conn.execute(text("SELECT state FROM social_post_targets WHERE publication_id=:id"), {"id":publication_id}).scalar_one() == "cancelled"
    finally:
        pool.shutdown(wait=True)


def test_pre_cancellation_claim_remains_fenced_after_explicit_resume(pg_engine):
    post_id, revision_id, publication_id = queued_publication(pg_engine)
    config = WorkerConfig(pg_engine.url.render_as_string(hide_password=False))
    repo = QueueRepository(pg_engine, config, uuid4())
    old = repo.claim_due()[0]
    cancel(pg_engine, post_id)
    # Cancellation now retains worker-owned work until the worker acknowledges.
    # A rejected resume must not reopen the retained claim or create an intent.
    with pytest.raises(SocialError, match="INVALID_STATE"):
        resume(pg_engine, post_id, revision_id)
    assert repo.begin_operation(old, operation_id=uuid4(), operation="publish",
        publication_capable=True, mutating=True, safe_replay_class="requires_reconciliation",
        request_fingerprint="a"*64, checkpoint_input={}) is None
    status, accepted = resume(pg_engine, post_id, revision_id)
    assert status == 202 and accepted["publication_id"] == str(publication_id)
    with pytest.raises(LeaseLost):
        repo.begin_operation(old, operation_id=uuid4(), operation="publish",
            publication_capable=True, mutating=True, safe_replay_class="requires_reconciliation",
            request_fingerprint="a"*64, checkpoint_input={})
    current = repo.claim_due()[0]
    assert current.epoch > old.epoch and current.token != old.token

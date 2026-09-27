"""Real PostgreSQL reconciliation races; opt-in, disposable database only.

Run with RECONCILIATION_TEST_DATABASE_URL pointing at a loopback PostgreSQL
database named codex_reconciliation_test. Each test creates/drops its own
random schema. No production database URL is ever consulted by this fixture.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import os
from threading import Event
from time import monotonic
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from models import Base, Country, DocumentStatus, DocumentType, Extraction, SourceDocument
from seeding.extractors import oag_blue_book as bb
from seeding.extractors.reconciliation import IncompleteExtraction, ReconciliationRequired
from tests.test_blue_book_national_walk import _legacy_rows


@pytest.fixture()
def pg_store(tmp_path):
    address = os.environ.get("RECONCILIATION_TEST_DATABASE_URL")
    if not address:
        pytest.skip("explicit disposable PostgreSQL URL required")
    url = make_url(address)
    assert url.get_backend_name() == "postgresql"
    assert url.host in {"127.0.0.1", "localhost", "::1"}
    assert url.database == "codex_reconciliation_test"
    assert url.port and url.port != 5432
    schema = "reconciliation_test_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={
        "options": f"-csearch_path={schema} -cstatement_timeout=10000",
    })
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        with Session() as session:
            country = Country(name="Kenya", iso_code="KEN", currency="KES",
                              timezone="Africa/Nairobi", default_locale="en-KE")
            session.add(country)
            session.flush()
            for doc_id in (1, 2):
                path = tmp_path / f"synthetic-source-{doc_id}.pdf"
                raw = f"Synthetic reconciliation test source {doc_id}".encode()
                path.write_bytes(raw)
                session.add(SourceDocument(
                    id=doc_id, country_id=country.id,
                    publisher="Office of the Auditor-General",
                    title=f"Synthetic source {doc_id}",
                    url=f"https://example.test/source-{doc_id}.pdf",
                    md5=hashlib.md5(raw).hexdigest(), file_path=str(path),
                    fetch_date=datetime.now(timezone.utc),
                    doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE,
                    meta={},
                ))
            session.commit()
        yield engine, Session
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def rows_for(doc, message):
    rows = _legacy_rows(doc)[:1]
    rows[0].extracted_json["finding_text"] = message
    return rows


def apply(session, doc, message, review=None):
    return bb.replace_extractions(session, doc, bb.EXTRACTOR_ID,
                                  rows_for(doc, message), bb.blue_book_row_key,
                                  review=review)


def seed(Session, doc_id=1):
    with Session() as session:
        doc = session.get(SourceDocument, doc_id)
        session.add_all(rows_for(doc, "Original finding"))
        session.commit()


def review_for(Session, message, doc_id=1):
    with Session() as session:
        doc = session.get(SourceDocument, doc_id)
        with pytest.raises(ReconciliationRequired) as exc:
            apply(session, doc, message)
        session.rollback()
        return {"proposal": exc.value.proposal, "source_complete": True,
                "reason": "Synthetic source and exact proposed revision checked."}


def stored(Session, doc_id=1):
    with Session() as session:
        return [row.extracted_json["finding_text"] for row in session.query(Extraction)
                .filter_by(source_document_id=doc_id).order_by(Extraction.id)]


def worker(Session, doc_id, message, review, ready, go, state):
    with Session() as session:
        doc = session.get(SourceDocument, doc_id)
        # Hold instances strongly: a query must refresh the identity map too.
        retained = session.query(Extraction).filter_by(source_document_id=doc_id).all()
        state["pid"] = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        state["cached_rows"] = len(retained)
        ready.set()
        assert go.wait(5), "writer was never released"
        try:
            apply(session, doc, message, review)
            session.commit()
            return "accepted"
        except ReconciliationRequired:
            session.rollback()
            return "refused"


def assert_lock_wait(engine, state, future):
    deadline = monotonic() + 5
    with engine.connect() as observer:
        while monotonic() < deadline:
            wait = observer.execute(text(
                "SELECT wait_event_type, wait_event FROM pg_stat_activity WHERE pid=:pid"
            ), {"pid": state["pid"]}).one()
            observer.commit()  # fresh statistics snapshot at every observation
            if wait[0] == "Lock":
                print(f"observed PostgreSQL lock wait: pid={state['pid']}, event={wait[1]}")
                return
            if future.done():
                pytest.fail(f"second writer completed before owner commit: {future.result()}")
            Event().wait(0.01)
    pytest.fail("second writer never entered a PostgreSQL lock wait")


def test_stale_identity_map_cannot_apply_approval_after_newer_commit(pg_store):
    _, Session = pg_store
    seed(Session)
    review_a = review_for(Session, "Correction A")
    review_b = review_for(Session, "Correction B")
    with Session() as a:
        doc_a = a.get(SourceDocument, 1)
        retained = a.query(Extraction).all()
        a.commit()
        assert retained[0].extracted_json["finding_text"] == "Original finding"
        with Session() as b:
            apply(b, b.get(SourceDocument, 1), "Correction B", review_b)
            b.commit()
        assert stored(Session) == ["Correction B"]
        with pytest.raises(ReconciliationRequired):
            apply(a, doc_a, "Correction A", review_a)
        a.rollback()
    assert stored(Session) == ["Correction B"]


@pytest.mark.parametrize("field", ["url", "md5", "file_path"])
def test_stale_document_identity_cannot_replay_approval(pg_store, field):
    _, Session = pg_store
    seed(Session)
    review = review_for(Session, "Correction A")
    with Session() as a:
        stale_doc = a.get(SourceDocument, 1)
        a.commit()
        with Session() as b:
            fresh_doc = b.get(SourceDocument, 1)
            replacement = {
                "url": "https://example.test/revised-source.pdf",
                "md5": "a" * 32,
                "file_path": b.get(SourceDocument, 2).file_path,
            }[field]
            setattr(fresh_doc, field, replacement)
            b.commit()
        with pytest.raises(ReconciliationRequired):
            apply(a, stale_doc, "Correction A", review)
        a.rollback()
    assert stored(Session) == ["Original finding"]


def test_unrelated_new_document_metadata_survives_valid_review(pg_store):
    _, Session = pg_store
    seed(Session)
    review = review_for(Session, "Correction A")
    with Session() as a:
        stale_doc = a.get(SourceDocument, 1)
        a.commit()
        with Session() as b:
            fresh_doc = b.get(SourceDocument, 1)
            fresh_doc.meta = {"independent_source_inspection": "must survive"}
            b.commit()
        apply(a, stale_doc, "Correction A", review)
        a.commit()
    with Session() as check:
        metadata = check.get(SourceDocument, 1).meta
        assert metadata["independent_source_inspection"] == "must survive"
        assert metadata["last_reconciliation_review"]["proposal"] == review["proposal"]


@pytest.mark.parametrize("rollback", [False, True])
def test_reviewed_writers_serialize_and_revalidate_after_lock(pg_store, rollback):
    engine, Session = pg_store
    seed(Session)
    review_a = review_for(Session, "Correction A")
    review_b = review_for(Session, "Correction B")
    ready, go, state = Event(), Event(), {}
    with Session() as a, ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker, Session, 1, "Correction B", review_b, ready, go, state)
        try:
            assert ready.wait(5)
            assert state["cached_rows"] == 1
            apply(a, a.get(SourceDocument, 1), "Correction A", review_a)
            go.set()
            assert_lock_wait(engine, state, future)
            a.rollback() if rollback else a.commit()
            assert future.result(timeout=5) == ("accepted" if rollback else "refused")
        finally:
            a.rollback()
            go.set()
    assert stored(Session) == ["Correction B" if rollback else "Correction A"]


def test_empty_document_serializes_first_insert_and_refuses_different_candidate(pg_store):
    engine, Session = pg_store
    ready, go, state = Event(), Event(), {}
    with Session() as a, ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker, Session, 1, "First finding B", None, ready, go, state)
        try:
            assert ready.wait(5)
            assert state["cached_rows"] == 0
            apply(a, a.get(SourceDocument, 1), "First finding A")
            go.set()
            assert_lock_wait(engine, state, future)
            a.commit()
            assert future.result(timeout=5) == "refused"
        finally:
            a.rollback()
            go.set()
    assert stored(Session) == ["First finding A"]


def test_unrelated_document_can_commit_while_first_document_is_locked(pg_store):
    _, Session = pg_store
    seed(Session, 1)
    seed(Session, 2)
    review_a = review_for(Session, "Correction A", 1)
    review_b = review_for(Session, "Correction B", 2)
    ready, go, state = Event(), Event(), {}
    with Session() as a, ThreadPoolExecutor(max_workers=1) as pool:
        try:
            apply(a, a.get(SourceDocument, 1), "Correction A", review_a)
            future = pool.submit(worker, Session, 2, "Correction B", review_b, ready, go, state)
            assert ready.wait(5)
            go.set()
            assert future.result(timeout=3) == "accepted"
            # A remains uncommitted: B is independent of its transaction.
            assert stored(Session, 2) == ["Correction B"]
            a.rollback()
        finally:
            a.rollback()
            go.set()
    assert stored(Session, 1) == ["Original finding"]


@pytest.mark.parametrize("pending", ["new", "dirty", "deleted"])
def test_pending_extraction_state_is_refused_before_savepoint_flush(pg_store, pending):
    engine, Session = pg_store
    seed(Session)
    statements = []

    def observe(connection, cursor, statement, parameters, context, many):
        statements.append(statement.lower().lstrip())

    with Session() as session:
        doc = session.get(SourceDocument, 1)
        old = session.query(Extraction).one()
        if pending == "new":
            session.add_all(rows_for(doc, "Unreviewed pending insert"))
        elif pending == "dirty":
            old.extracted_json = {**old.extracted_json, "finding_text": "Unreviewed pending write"}
        else:
            session.delete(old)
        event.listen(engine, "before_cursor_execute", observe)
        try:
            with pytest.raises(IncompleteExtraction, match="unchanged stored extractions"):
                apply(session, doc, "Original finding")
            assert not any(sql.startswith(("insert ", "update ", "delete ")) for sql in statements)
        finally:
            event.remove(engine, "before_cursor_execute", observe)
            session.rollback()
    assert stored(Session) == ["Original finding"]

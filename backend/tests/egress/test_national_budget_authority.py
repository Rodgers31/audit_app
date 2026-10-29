"""National authority ordering, lineage and public-reader PostgreSQL regressions."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep

import pytest
from sqlalchemy import select, event, create_engine, text
from sqlalchemy.orm import Session

from harness import budget_records, seed_country
from models import SourceDocument, DocumentType, DocumentStatus, IngestionJob, IngestionStatus, BudgetLine, Extraction
from seeding.native_report_authority import capture_pdf_report, persist_native_report, KEY
from seeding.native_report_observations import current_native_report
from seeding.source_observations import SourceObservationUnavailable
from seeding.domains.national_budget.writer import persist_national_budget_records
from seeding.config import SeedingSettings
from seeding.types import DomainRunContext
import httpx
from test_cob_publication_producer import pdf_bytes
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response


def setup_proof(engine, tmp_path):
    cid, _ = seed_country(engine)
    with Session(engine) as db:
        job = IngestionJob(domain='national_budget', status=IngestionStatus.RUNNING,
            dry_run=False, started_at=datetime.now(timezone.utc), errors=[], meta={'source_mode': 'live'})
        db.add(job); db.commit(); jid = job.id
    body = pdf_bytes('0', 'Publication date: 2026-09-04').replace(
        b'Controller of Budget County Budget Implementation Review FY2025/26 Annual',
        b'NATIONAL GOVERNMENT BUDGET IMPLEMENTATION REVIEW REPORT FY 2025/2026')
    path = tmp_path / 'national-report.pdf'
    path.write_bytes(body)
    pdf = capture_response(httpx.Response(200, content=body,
        headers={'content-type': 'application/pdf'},
        request=httpx.Request('GET', 'https://cob.go.ke/national-authority.pdf')),
        LocalReceiptStore(tmp_path / 'receipts'), source_kind='pdf')
    proof, reason = capture_pdf_report(path, pdf, domain='national_budget')
    assert proof is not None, reason
    with Session(engine) as db:
        source = SourceDocument(country_id=cid, publisher='Controller of Budget', title='Owned spec report',
            url=proof.value['document_url'], fetch_date=datetime.now(timezone.utc), doc_type=DocumentType.BUDGET,
            status=DocumentStatus.AVAILABLE, md5=proof.value['document_md5'], http_status=200,
            content_type='application/pdf', meta={'padding':'x'*65536, 'custody':{'keep':True}})
        db.add(source); db.commit(); sid = source.id
    return proof, sid, jid


@pytest.mark.parametrize('flags', [(False, True, False), (True, False, True), (False, False, True), (True, False, False), (True, True, False, True)],
    ids=['none-proof-none', 'proof-none-proof', 'none-none-proof', 'proof-none-none', 'proof-proof-none-proof'])
def test_mixed_requests_keep_last_binding_and_exact_lineage(pg_fixture, tmp_path, flags):
    engine, _ = pg_fixture
    proof, sid, jid = setup_proof(engine, tmp_path)
    rows = [replace(r, source_url=proof.value['document_url'], provenance_extra={**r.provenance_extra,
        **({'_native_report_authority': proof} if flag else {})}) for r, flag in zip(budget_records(len(flags)), flags)]
    with Session(engine) as db:
        stats = persist_national_budget_records(db, rows, SeedingSettings(), DomainRunContext(None, False, jid))
        assert stats.created == len(flags) and not stats.errors
        job = db.get(IngestionJob, jid)
        job.status = IngestionStatus.COMPLETED; job.finished_at = datetime.now(timezone.utc)
        db.commit()
    with Session(engine) as db:
        source = db.get(SourceDocument, sid)
        assert source.meta['padding'] == 'x'*65536 and source.meta['custody'] == {'keep':True}
        binding = source.meta.get(KEY, {}).get('national_budget')
        assert bool(binding) is flags[-1]
        retained = list(db.scalars(select(Extraction)))
        assert retained and all(r.extracted_json['response_receipt']['digest'] == proof.receipt['digest'] for r in retained if r.extractor == 'native-report-authority-v1')
        ids = db.get(IngestionJob, jid).meta['native_report_records']['national_budget']
        assert len(ids) == 1
        if flags[-1]:
            observed = current_native_report(db, ids[0], jid, domain='national_budget')
            assert observed['ingestion_id'] == str(jid) and observed['facts'] == []
        else:
            with pytest.raises(SourceObservationUnavailable):
                current_native_report(db, ids[0], jid, domain='national_budget')
        lines = list(db.scalars(select(BudgetLine).order_by(BudgetLine.id)))
        assert [(r.allocated_amount, r.actual_spent) for r in lines] == [(100+i, 50+i) for i in range(len(flags))]
        assert all('_native_report_authority' not in r.provenance[-1] for r in lines)


def test_real_public_financial_reader_is_unchanged_by_authority_invalidation(pg_fixture, tmp_path, monkeypatch):
    import main
    engine, _ = pg_fixture
    proof, sid, jid = setup_proof(engine, tmp_path)
    rows = [replace(r, source_url=proof.value['document_url'], provenance_extra={**r.provenance_extra, '_native_report_authority':proof}) for r in budget_records(2)]
    with Session(engine) as db:
        persist_national_budget_records(db, rows, SeedingSettings(), DomainRunContext(None, False, jid))
        db.commit()
        first = db.scalar(select(BudgetLine))
        entity, period = first.entity_id, first.period_id
    monkeypatch.setattr(main, 'DATABASE_AVAILABLE', True)
    with Session(engine) as db:
        before = asyncio.run(main.get_budget_lines(entity, period, skip=0, limit=100, db=db))
        source = db.get(SourceDocument, sid)
        persist_native_report(db, source, None, context=DomainRunContext(None, False), domain='national_budget')
        db.commit()
    with Session(engine) as db:
        after = asyncio.run(main.get_budget_lines(entity, period, skip=0, limit=100, db=db))
        assert after == before
        assert after['total'] == 2
        assert [r['actual_spent'] for r in after['items']] == [50.0, 51.0]
        assert [r.actual_spent for r in db.scalars(select(BudgetLine).order_by(BudgetLine.id))] == [50, 51]


def test_waiting_invalidation_reads_committed_replacement_and_keeps_lock(pg_fixture):
    engine, _ = pg_fixture
    cid, _ = seed_country(engine)
    with Session(engine) as db:
        source = SourceDocument(country_id=cid, publisher='Controller of Budget', title='Owned wait',
            url='https://cob.go.ke/spec-lock.pdf', fetch_date=datetime.now(timezone.utc), doc_type=DocumentType.BUDGET,
            status=DocumentStatus.FAILED, meta={'old':True})
        db.add(source); db.commit(); sid = source.id
    waiting = Event()
    def before_cursor(conn, cursor, statement, parameters, context, many):
        if 'FOR UPDATE' in statement and 'source_documents' in statement:
            waiting.set()
    event.listen(engine, 'before_cursor_execute', before_cursor)
    replacement = {'padding':'x'*65536, KEY:{'national_budget':{'new':True}, 'audits':{'keep':True}}}
    writer = Session(engine)
    try:
        source = writer.get(SourceDocument, sid)
        source.meta = deepcopy(replacement); writer.flush()
        def invalidate():
            with Session(engine) as db:
                stale = db.get(SourceDocument, sid)
                assert stale.meta == {'old':True}
                persist_native_report(db, stale, None, context=DomainRunContext(None, False), domain='national_budget')
                assert stale.meta == {**replacement, KEY:{'audits':{'keep':True}}}
                db.commit()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(invalidate)
            assert waiting.wait(2), 'Changed row-lock path never executed'
            assert not future.done()
            writer.commit()
            future.result(timeout=4)
    finally:
        writer.rollback(); writer.close()
        event.remove(engine, 'before_cursor_execute', before_cursor)
    with Session(engine) as db:
        assert db.get(SourceDocument, sid).meta == {**replacement, KEY:{'audits':{'keep':True}}}


def test_concurrent_missing_and_positive_writer_preserve_domain_before_financial_lock_order(pg_fixture, tmp_path):
    engine, _ = pg_fixture
    proof, sid, jid = setup_proof(engine, tmp_path)
    base = [replace(r, source_url=proof.value['document_url']) for r in budget_records(2)]
    with Session(engine) as db:
        persist_national_budget_records(db, base, SeedingSettings(), DomainRunContext(None, False))
        db.commit()
    a_financial_lock = Event()
    release_a = Event()
    b_financial_attempt = Event()
    b_advisory_attempt = Event()
    pids = {}
    def before_cursor(conn, cursor, statement, parameters, context, many):
        if statement.startswith('UPDATE budget_lines') and conn.info.get('spec_role') == 'B':
            b_financial_attempt.set()
        if 'pg_advisory_xact_lock' in statement and conn.info.get('spec_role') == 'B':
            b_advisory_attempt.set()
    def after_cursor(conn, cursor, statement, parameters, context, many):
        if statement.startswith('UPDATE budget_lines') and conn.info.get('spec_role') == 'A' and not a_financial_lock.is_set():
            a_financial_lock.set()
            if not release_a.wait(5):
                raise RuntimeError('Owned schedule was not released')
    event.listen(engine, 'before_cursor_execute', before_cursor)
    event.listen(engine, 'after_cursor_execute', after_cursor)
    errors = []
    def write(role, qualified):
        values = [replace(r, actual_spent=r.actual_spent + (1000 if role == 'A' else 2000),
            provenance_extra={**r.provenance_extra, **({'_native_report_authority':proof} if qualified else {})}) for r in base]
        try:
            with Session(engine) as db:
                db.connection().info['spec_role'] = role
                db.execute(text("SET LOCAL lock_timeout='2000ms'"))
                pids[role] = db.scalar(text('SELECT pg_backend_pid()'))
                persist_national_budget_records(db, values, SeedingSettings(), DomainRunContext(None, False, jid))
                db.commit()
        except Exception as exc:
            errors.append((role, type(exc).__name__, str(exc)))
    monitor = create_engine(engine.url, pool_size=1, max_overflow=0,
        isolation_level='AUTOCOMMIT', connect_args={'connect_timeout':2})
    observed_wait = None
    observed_locks = []
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(write, 'A', False)
            assert a_financial_lock.wait(2), 'First writer never held actual financial row lock'
            b = pool.submit(write, 'B', True)
            assert b_advisory_attempt.wait(2), 'Second writer never attempted native domain lock'
            # Observe the real PostgreSQL wait; no scheduler-delay assumption.
            # Old ordering blocks B at advisory. Inverted ordering lets B own
            # advisory and block on A's still-held financial transaction.
            deadline = monotonic() + 1
            with monitor.connect() as inspection:
                while monotonic() < deadline:
                    state = inspection.execute(text('SELECT wait_event_type,wait_event FROM pg_stat_activity WHERE pid=:pid'), {'pid':pids['B']}).one()
                    if state[0] == 'Lock' and state[1] in ('advisory', 'transactionid', 'tuple'):
                        observed_wait = tuple(state)
                        observed_locks = [tuple(row) for row in inspection.execute(text('SELECT locktype,mode,granted FROM pg_locks WHERE pid=:pid ORDER BY locktype,mode,granted'), {'pid':pids['B']})]
                        break
                    sleep(.005)
            assert observed_wait is not None, 'Second writer never reached a real PostgreSQL lock wait'
            assert any(not lock[2] for lock in observed_locks), observed_locks
            crossed = b_financial_attempt.is_set()
            release_a.set()
            a.result(timeout=6); b.result(timeout=6)
    finally:
        release_a.set()
        event.remove(engine, 'before_cursor_execute', before_cursor)
        event.remove(engine, 'after_cursor_execute', after_cursor)
        monitor.dispose()
    print({'crossed_domain_before_financial_lock':crossed, 'observed_wait':observed_wait,
        'observed_locks':observed_locks, 'errors':errors})
    assert not errors, errors
    assert observed_wait == ('Lock', 'advisory') and not crossed

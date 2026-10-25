"""Executable review regressions; owned retained bytes and current PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

import pytest
from sqlalchemy import select, text

from models import SourceDocument
from seeding.native_report_authority import KEY, capture_pdf_report, lock_native_domain
from seeding.native_report_observations import current_native_report
from seeding.source_observations import read_revenue_report_observation
from test_b83_generation_postgres import pg, no_publication
from test_b86_native_authority import receipt
from test_b86_native_postgres import ingest


@pytest.mark.parametrize('domain,url', [
    ('national_budget', 'https://cob.go.ke/malformed.pdf'),
    ('audits', 'https://www.oagkenya.go.ke/malformed.pdf'),
])
@pytest.mark.parametrize('body', [b'%PDF-1.4\nnot a document', b'not PDF bytes'])
def test_malformed_retained_pdf_returns_explicit_refusal(tmp_path, domain, url, body):
    path = tmp_path / 'malformed.pdf'
    path.write_bytes(body)
    proof, reason = capture_pdf_report(path, receipt(tmp_path, body, url, 'application/pdf'), domain=domain)
    assert proof is None
    assert reason == 'native_report_date_or_scope_unavailable'


def test_nullable_source_metadata_already_normalizes_before_update(pg, tmp_path):
    factory, _ = pg
    job, record = ingest(factory, tmp_path)
    with factory.begin() as db:
        db.execute(text('UPDATE source_documents SET metadata = NULL'))
    # Update the retained existing row rather than creating another source.
    job, record = ingest(factory, tmp_path)
    value = read_revenue_report_observation(factory, record_id=record, ingestion_id=job)
    assert value['report']['source_record_id'] == record
    with factory() as db:
        source = db.scalar(select(SourceDocument))
        assert source.meta[KEY]['revenue_by_source']['extraction_id'] == record
        assert db.scalar(select(text('count(*)')).select_from(SourceDocument)) == 1
    no_publication(factory)


def test_completion_after_reader_transaction_start_survives_real_lock_wait(pg, tmp_path):
    factory, engine = pg
    job, record = ingest(factory, tmp_path)
    reader_started = Event()
    reader_pid = []

    def read():
        with factory.begin() as db:
            reader_pid.append(db.scalar(text('SELECT pg_backend_pid()')))
            db.scalar(text('SELECT current_timestamp'))
            reader_started.set()
            return current_native_report(db, record, job, domain='revenue_by_source', lock=True)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with factory.begin() as writer:
            lock_native_domain(writer, 'revenue_by_source')
            result = pool.submit(read)
            assert reader_started.wait(2)
            deadline = monotonic() + 1
            while True:
                with engine.connect() as observer:
                    waiting = observer.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid=:pid AND locktype='advisory' AND NOT granted)"), {'pid': reader_pid[0]})
                if waiting:
                    break
                assert monotonic() < deadline, 'Reader never waited on the native domain lock'
                reader_started.wait(0.01)
            # This valid completion is later than the reader transaction began,
            # and becomes visible when the reader acquires the domain lock.
            writer.execute(text('UPDATE ingestion_jobs SET finished_at=clock_timestamp() WHERE id=:id'), {'id': job})
        value = result.result(timeout=3)
    assert value['report']['source_record_id'] == record
    no_publication(factory)


@pytest.mark.parametrize('domain', ['national_budget', 'revenue_by_source', 'audits'])
def test_timeout_identity_diagnostic_is_domain_neutral(domain):
    from seeding.generation_dispatch import record_generation_timeout
    with pytest.raises(ValueError, match='Bounded ingestion identity required'):
        record_generation_timeout(None, domain=domain, ingestion_id=True)

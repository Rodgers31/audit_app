"""Numerical success and retained-byte success must be independently visible."""
import pytest
from contextvars import copy_context
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from models import IngestionJob, IngestionStatus
from routers.admin_operations import safe_job_metadata
from seeding import cli, freshness
from seeding.config import SeedingSettings
from seeding.types import DomainRunResult
from services.response_receipts import capture_response
from test_hollow_run_gate import HEALTHY_NIGHT, _write_db, _run_step
from test_receipt_upload_recovery import source_response
from test_seeding_cli_budget import clock, sessionmaker_factory, _FakeRegistry, _args, _jobs_by_domain
from services.receipt_retention import RetentionScope, safe_retention_summary
from test_national_gdp_source_creation import pg as receipt_pg


MISSING = dict(state="missing_bytes", observed=1, retained=0, missing=1, recovered=0, retry_requests=0)


def test_completed_numerical_job_records_missing_receipt_bytes(clock, sessionmaker_factory, monkeypatch):
    class UnavailableStore:
        def put(self, body):
            raise OSError("inert unavailable receipt storage")

    def handler(**kwargs):
        capture_response(source_response(), UnavailableStore())
        freshness.mark_live("economic_indicators")
        return DomainRunResult(domain="economic_indicators", items_processed=1, items_updated=1)

    monkeypatch.setenv("SOCIAL_GENERATION_HOOK_ENABLED", "false")
    monkeypatch.setattr(cli, "REGISTRY", _FakeRegistry({"economic_indicators": handler}))
    assert cli.run_seed_command(_args(), SeedingSettings(total_timeout_seconds=0)) == 0
    job = _jobs_by_domain(sessionmaker_factory)["economic_indicators"]
    assert job.status == IngestionStatus.COMPLETED and job.items_updated == 1
    assert job.meta.get("receipt_retention") == MISSING
    assert safe_job_metadata(job.meta)["receipt_retention"] == MISSING


@pytest.mark.parametrize('mode', ['dry_run', 'failure', 'domain_timeout', 'global_timeout'])
def test_retention_summary_survives_rollback_and_timeout(clock, sessionmaker_factory, monkeypatch, mode):
    from seeding.cli import DomainTimeoutError
    def handler(**kwargs):
        capture_response(source_response(), None)
        if mode in {'domain_timeout', 'global_timeout'}:
            raise DomainTimeoutError('inert timeout')
        if mode == 'failure':
            raise RuntimeError('inert handler failure')
        freshness.mark_live('economic_indicators')
        return DomainRunResult(domain='economic_indicators', items_processed=1, items_updated=1)
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'false')
    monkeypatch.setattr(cli, 'REGISTRY', _FakeRegistry({'economic_indicators':handler}))
    args = _args()
    args.dry_run = mode == 'dry_run'
    status = cli.run_seed_command(args, SeedingSettings(total_timeout_seconds=1 if mode == 'global_timeout' else 0))
    job = _jobs_by_domain(sessionmaker_factory)['economic_indicators']
    assert status == (0 if mode == 'dry_run' else 1)
    assert job.meta['receipt_retention'] == MISSING
    # A subsequent invocation has no inherited counters, including after errors.
    scope = RetentionScope()
    try:
        assert scope.summary()['state'] == 'not_observed'
    finally:
        scope.close()


def test_safe_admin_projection_keeps_bounded_retention_outcome():
    assert safe_job_metadata({"receipt_retention": MISSING}) == {"receipt_retention": MISSING}


@pytest.mark.parametrize('raw', [None, {}, [], {**MISSING, 'observed': True},
    {**MISSING, 'missing': -1}, {**MISSING, 'retained': 1},
    {**MISSING, 'state': 'confirmed'}, {**MISSING, 'recovered': 1},
    {**MISSING, 'retry_requests': 1000001}, {**MISSING, 'provider': 'PRIVATE'}])
def test_malformed_summary_is_unknown_without_echoing_arbitrary_metadata(raw):
    assert safe_retention_summary(raw) == {'state': 'unverified'}
    assert safe_job_metadata({'receipt_retention': raw}) == {'receipt_retention': {'state': 'unverified'}}


def test_nested_scopes_and_late_context_do_not_contaminate_another_job():
    outer = RetentionScope()
    inner = RetentionScope()
    late = copy_context()
    inner.close()
    late.run(capture_response, source_response(), None)
    assert inner.summary()['observed'] == outer.summary()['observed'] == 0
    capture_response(source_response(), None)
    outer.close()
    outer.close()  # Finally cleanup is intentionally idempotent.
    assert outer.summary() == MISSING
    next_job = RetentionScope()
    try:
        assert next_job.summary() == dict(state='not_observed', observed=0, retained=0, missing=0, recovered=0, retry_requests=0)
    finally:
        next_job.close()


def test_retry_without_any_recovered_or_missing_capture_is_incoherent():
    raw = dict(state='confirmed', observed=1, retained=1, missing=0, recovered=0, retry_requests=1)
    assert safe_retention_summary(raw) == {'state':'unverified'}


def test_local_claim_conflict_downgrades_the_original_capture(tmp_path):
    from services.response_receipts import capture_local_bytes
    from services.receipt_store import LocalReceiptStore
    scope = RetentionScope()
    try:
        receipt = capture_local_bytes(b'body', LocalReceiptStore(tmp_path), url='https://source.example.test/report.pdf',
                                      claimed_receipt={'digest':'wrong','byte_size':4})
        assert receipt['byte_check']['status'] == 'conflict'
        assert scope.summary() == MISSING
    finally:
        scope.close()


@pytest.mark.parametrize('copy_kind', ['direct', 'parser_copy', 'deepcopy', 'recovered_copy'])
def test_persistence_recheck_downgrades_one_shared_capture(receipt_pg, tmp_path, monkeypatch, copy_kind):
    from copy import deepcopy
    from datetime import datetime, timezone
    import httpx
    from models import SourceDocument, Country, DocumentType, Extraction
    from services.response_receipts import copy_receipt, seal_receipt, persist_receipt
    from services.r2_receipt_store import R2ReceiptStore
    from services import r2_receipt_store as adapter
    from test_r2_receipt_store import Boundary, ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL
    from sqlalchemy.orm import sessionmaker
    factory = sessionmaker(bind=receipt_pg, expire_on_commit=False)
    with factory() as session:
        session.add(Country(id=1, name='Kenya', iso_code='KEN', currency='KES', timezone='Africa/Nairobi', default_locale='en-KE'))
        session.commit()
    monkeypatch.setattr(cli, 'SessionLocal', factory)
    monkeypatch.setattr(cli, 'load_builtin_domains', lambda:None)
    monkeypatch.setenv('SOCIAL_GENERATION_HOOK_ENABLED', 'false')
    monkeypatch.setattr(adapter.time, 'sleep', lambda _:None)
    boundary = Boundary(tmp_path)
    reads = []
    interrupted_put = []
    def transport(request):
        if copy_kind == 'recovered_copy' and request.method == 'PUT' and not interrupted_put:
            interrupted_put.append(request)
            return httpx.Response(503)
        if request.method == 'GET' and '/manifests/' in request.url.path:
            reads.append(request)
            if len(reads) >= 2:
                return httpx.Response(503)
        return boundary(request)
    store = R2ReceiptStore(ACCOUNT, R2_BUCKET, ACCESS, SECRET, CONTROL, max_bytes=1024,
                           part_max_bytes=4, transport=httpx.MockTransport(transport))
    def handler(*, session, **kwargs):
        source = SourceDocument(country_id=session.scalar(select(Country.id)), publisher='Owned publisher',
            title='Owned source', url='https://source.example.test/report.pdf', doc_type=DocumentType.REPORT,
            fetch_date=datetime.now(timezone.utc), meta={})
        session.add(source)
        session.flush()
        original = capture_response(source_response(), store)
        receipt = copy_receipt(original, parser_version='inert-parser') if copy_kind == 'parser_copy' else deepcopy(original) if copy_kind == 'deepcopy' else original
        seal_receipt(receipt, [])
        persisted = persist_receipt(session, source, receipt)
        assert persisted.extracted_json['response_receipt']['byte_check']['status'] == 'missing'
        freshness.mark_live('economic_indicators')
        return DomainRunResult(domain='economic_indicators', items_processed=1, items_updated=1)
    monkeypatch.setattr(cli, 'REGISTRY', _FakeRegistry({'economic_indicators':handler}))
    assert cli.run_seed_command(_args(), SeedingSettings(total_timeout_seconds=0)) == 0
    job = _jobs_by_domain(factory)['economic_indicators']
    assert job.meta['receipt_retention'] == {**MISSING, 'retry_requests':3 if copy_kind == 'recovered_copy' else 2}
    with factory() as session:
        assert session.scalar(select(Extraction)).extracted_json['response_receipt']['byte_check']['status'] == 'missing'


def test_retained_pdf_validation_failure_is_not_an_empty_healthy_scope(monkeypatch):
    from seeding import retained_report_receipts
    from services.response_receipts import capture_retained_pdf
    def refuse(*args, **kwargs):
        raise ValueError('inert missing retained original')
    monkeypatch.setattr(retained_report_receipts, 'verified_retained_pdf', refuse)
    scope = RetentionScope()
    try:
        with pytest.raises(ValueError):
            capture_retained_pdf(None, None, None, domain='national_budget', url='https://source.example.test/report.pdf', body=b'body')
        assert scope.summary() == MISSING
    finally:
        scope.close()


def test_actual_workflow_reports_receipt_warning_separately_from_numerical_success(tmp_path):
    url = _write_db(tmp_path, HEALTHY_NIGHT)
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            row = session.scalar(select(IngestionJob).where(IngestionJob.domain == "pending_bills"))
            row.meta = {**row.meta, "receipt_retention": MISSING}
            session.commit()
    finally:
        engine.dispose()
    result = _run_step(url)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[RECEIPT WARNING] pending_bills" in result.stdout
    assert "1 unconfirmed" in result.stdout

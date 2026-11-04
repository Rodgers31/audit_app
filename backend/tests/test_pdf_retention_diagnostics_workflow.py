"""The actual nightly result step prints only validated phase diagnostics."""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from models import IngestionJob
from tests.test_hollow_run_gate import _run_step, _write_db


@compiles(JSONB, 'sqlite')
def _sqlite_jsonb(element, compiler, **kwargs):
    # The ordinary suite registers this same fixture dialect in conftest.
    # Keep the real workflow test self-contained under isolated noconftest runs.
    return 'TEXT'


@pytest.mark.parametrize('malformed', [False, True])
def test_nightly_phase_diagnostics_preserve_incomplete_source_failure(tmp_path, malformed):
    url = _write_db(tmp_path, [('audits', 'completed_with_errors', 0, 4, 8105, 'partial',
                              'native_report_reconciliation_required')])
    detailed = dict(state='missing_bytes', observed=2, retained=1, missing=1,
                    recovered=0, retry_requests=0, diagnostics={
                        'retained_pdf_restore': {'origin_missing': 1},
                        'local_pdf_fallback': {'bytes_retained': 1}})
    if malformed:
        detailed['diagnostics'] = {'https://private.invalid?token=never-echo': {'origin_missing': 1}}
    engine = create_engine(url)
    try:
        with Session(engine) as db:
            job = db.scalar(select(IngestionJob))
            job.meta = {**job.meta, 'receipt_retention': detailed}
            db.commit()
        result = _run_step(url, domain='audits')
    finally:
        engine.dispose()
    assert result.returncode == 1, result.stdout + result.stderr
    assert '[INCOMPLETE] audits:' in result.stdout
    assert 'All domains completed successfully.' not in result.stdout
    assert 'private.invalid' not in result.stdout and 'never-echo' not in result.stdout
    if malformed:
        assert '[RECEIPT DIAGNOSTIC]' not in result.stdout
        assert 'retention outcome unknown' in result.stdout
    else:
        assert '[RECEIPT DIAGNOSTIC] audits: retained_pdf_restore origin_missing=1' in result.stdout
        assert '[RECEIPT DIAGNOSTIC] audits: local_pdf_fallback bytes_retained=1' in result.stdout

"""A catalogue proves report availability, never dated financial authority."""
import pytest
from sqlalchemy import select, text

from models import RevenueBySource
from seeding.native_financial_observations import read_native_financial_observation
from seeding.source_observations import SourceObservationUnavailable
from native_worker_fixture import restricted
from test_b83_generation_postgres import pg
from test_b86_native_postgres import enable
from test_kra_catalogue_postgres import ingest


@pytest.mark.parametrize('view', ['social_native_source_authority',
                                  'social_native_source_authority_snapshot'])
@pytest.mark.parametrize('kind', ['report', 'financial'])
def test_catalogue_witness_is_report_only(restricted, tmp_path, monkeypatch, view, kind):
    factory, owner, worker, _ = restricted
    enable(factory, monkeypatch)
    job, report_record = ingest(factory, tmp_path)
    with factory() as db:
        record = db.scalar(select(RevenueBySource.id).where(
            RevenueBySource.meta.contains({'ingestion_job_id': job})).order_by(RevenueBySource.id))
    assert record is not None
    # The real catalogue producer has no dated financial authority. Depending
    # on the selected head, the privileged reader can refuse even earlier at
    # its publishability check; neither refusal permits a financial digest.
    with pytest.raises(SourceObservationUnavailable):
        read_native_financial_observation(factory, record_id=record,
                                         ingestion_id=job, domain='revenue_by_source')
    # The snapshot is intentionally private to the owner; existing role tests
    # separately prove that the worker is not granted SELECT on it.
    reader = worker if view == 'social_native_source_authority' else owner
    with reader.begin() as conn:
        rows = conn.execute(text('SELECT authority_fingerprint FROM ' + view +
            ' WHERE source_kind=:kind AND native_domain=:domain AND record_id=:record AND ingestion_id=:job'),
            dict(kind=kind, domain='revenue_by_source',
                 record=report_record if kind == 'report' else record, job=job)).scalars().all()
    if kind == 'report':
        assert len(rows) == 1 and len(rows[0]) == 64
    else:
        assert rows == [], 'Undated catalogue yielded a financial worker witness'

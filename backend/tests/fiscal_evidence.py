"""Explicit synthetic measure evidence for reader fixtures, never source acceptance.

The digest identifies inert test evidence, not downloaded official PDF bytes.
Tests of real source authority use the separately hash-bound official PDFs.
"""
import hashlib
import pytest
from services.fiscal_qualification import MONEY_BASES, VERSION, measure_evidence

SYNTHETIC_SHA=hashlib.sha256(b'inert fiscal reader fixture; not official source acceptance').hexdigest()


def qualify_synthetic_row(row):
    meta=dict(row.meta or {})
    source={'url':'https://www.treasury.go.ke/synthetic-test-fixture.pdf',
            'page':'PDF p.37','sha256':SYNTHETIC_SHA,'title':'SYNTHETIC TEST EVIDENCE'}
    measures={}
    for field,bases in MONEY_BASES.items():
        value=getattr(row,field,None)
        if value is not None and bases:
            measures[field]=measure_evidence(float(value),row.fiscal_year,next(iter(bases)),
                'Approved',100_000_000,dict(source))
    meta['fiscal_measure_contract']={'version':VERSION,'measures':measures}
    row.meta=meta
    return row


def bind_framework(framework):
    framework['source']['sha256']=SYNTHETIC_SHA
    framework.setdefault('precision_kes',100_000_000)
    from services.fiscal_framework_qualification import bind_framework_evidence
    bind_framework_evidence(framework)
    return framework


@pytest.fixture(autouse=True)
def isolated_fiscal_debt_peer_worker(monkeypatch):
    """Canonical clients omit lifespan; do not reuse a previously closed worker.

    The real bounded worker still executes. This owns and closes exactly the
    worker created for this test, including after a preceding lifespan test.
    """
    import main
    from services.endpoint_resources import SingleWorker
    worker = SingleWorker()
    monkeypatch.setattr(main, '_peer_worker', worker)
    try:
        yield
    finally:
        worker.close()

"""Actual isolated PG, declared coherent legacy-contract rewrites, no production.

The untouched current source and witness are first accepted; missing/unknown
producer contracts must then refuse independently in the reader and digest view.
"""
from copy import deepcopy
import pytest
from sqlalchemy import text
from models import Extraction,SourceDocument
from seeding.native_report_authority import KEY,digest,source_identity
from seeding.source_observations import read_revenue_report_observation,SourceObservationUnavailable
from social.generation.worker_authority import capture_worker_authority,verify_worker_authority
from social.generation.contracts import SourceObservation
from native_worker_fixture import restricted
from test_b83_generation_postgres import pg
from test_native_financial_changes_postgres import enable,ingest_revenue,read


def reader(factory,kind,job,record):
    if kind=='financial':return read(factory,job,record)
    return SourceObservation.model_validate(read_revenue_report_observation(factory,record_id=record,ingestion_id=job)).model_dump(mode='json')


def source_fixture(restricted,tmp_path,monkeypatch,kind):
    factory,owner,worker,role=restricted
    enable(factory,monkeypatch)
    job,financial_record=ingest_revenue(factory,tmp_path,monkeypatch)
    financial=read(factory,job,financial_record)
    report_record=financial['financial']['report_record_id']
    record=financial_record if kind=='financial' else report_record
    original=reader(factory,kind,job,record)
    with factory.begin() as db:
        witness=capture_worker_authority(db,original)
    assert witness is not None,'Positive current witness control did not execute'
    with worker.begin() as conn:verify_worker_authority(conn,original,witness)
    return factory,worker,job,record,report_record,deepcopy(original),deepcopy(witness)


def rewrite_legacy_contract(factory,job,report_record,marker):
    # This explicitly models a coherent stored legacy format, not a source-byte
    # change or a malformed-proof hash mismatch. The immutable original test
    # source/witness remains held separately as the positive pre-change control.
    with factory.begin() as db:
        ext=db.get(Extraction,report_record)
        stored=deepcopy(ext.extracted_json)
        receipt=stored['response_receipt'];value=receipt['observations'][0]
        if marker=='missing':value.pop('publication_contract',None)
        else:value['publication_contract']='unreviewed-publication-contract'
        ext.extracted_json=stored
        source=db.get(SourceDocument,ext.source_document_id)
        metadata=deepcopy(source.meta);binding=metadata[KEY]['revenue_by_source']
        binding['authority_hash']=digest(dict(receipt=receipt,value=value,country_id=source.country_id,publisher=source.publisher,ingestion_id=job,source_identity=source_identity(source)))
        source.meta=metadata


@pytest.mark.parametrize('kind',['report','financial'])
@pytest.mark.parametrize('marker',['missing','unknown'])
def test_privileged_reader_refuses_coherent_unreviewed_kra_contract(restricted,tmp_path,monkeypatch,kind,marker):
    factory,worker,job,record,report_record,original,witness=source_fixture(restricted,tmp_path,monkeypatch,kind)
    rewrite_legacy_contract(factory,job,report_record,marker)
    with pytest.raises(SourceObservationUnavailable):reader(factory,kind,job,record)


@pytest.mark.parametrize('kind',['report','financial'])
@pytest.mark.parametrize('marker',['missing','unknown'])
def test_restricted_digest_view_refuses_coherent_unreviewed_kra_contract(restricted,tmp_path,monkeypatch,kind,marker):
    factory,worker,job,record,report_record,original,witness=source_fixture(restricted,tmp_path,monkeypatch,kind)
    rewrite_legacy_contract(factory,job,report_record,marker)
    with worker.begin() as conn:
        rows=conn.execute(text('SELECT authority_fingerprint FROM social_native_source_authority WHERE source_kind=:kind AND native_domain=:domain AND record_id=:record AND ingestion_id=:job'),dict(kind=kind,domain='revenue_by_source',record=record,job=job)).scalars().all()
    assert rows==[],'Invalid publication producer contract still yields a restricted worker witness'

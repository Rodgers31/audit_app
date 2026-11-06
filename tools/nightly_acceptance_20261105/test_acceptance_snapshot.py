"""Real native publication reader interleaving; source data stays fixture-only."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from common import Refusal
from acceptance_authority import observe_oag_report
from test_acceptance_authority import owned_database


def native_fixture(engine,tmp_path):
    from tests.test_cob_publication_producer import pdf_bytes
    from models import Country,DocumentStatus,DocumentType,IngestionJob,IngestionStatus,SourceDocument
    from services.receipt_store import LocalReceiptStore
    from services.response_receipts import capture_response
    from seeding.native_report_authority import capture_pdf_report,persist_native_report
    from seeding.types import DomainRunContext
    url='https://www.oagkenya.go.ke/owned-native-control.pdf'
    title=b'REPORT OF THE AUDITOR-GENERAL ON TEST MINISTRY FOR THE YEAR ENDED 30 JUNE 2025'
    body=pdf_bytes('0','Publication date: 2025-07-10').replace(
        b'Controller of Budget County Budget Implementation Review FY2025/26 Annual',title)
    original=tmp_path/'native.pdf';retained=tmp_path/'retained.pdf'
    original.write_bytes(body);retained.write_bytes(body)
    with Session(engine) as db:
        country=Country(iso_code='KEN',name='Kenya',currency='KES',timezone='Africa/Nairobi',default_locale='en_KE')
        job=IngestionJob(domain='audits',status=IngestionStatus.RUNNING,dry_run=False,
                         started_at=datetime.now(timezone.utc),errors=[],meta={'source_mode':'live'})
        db.add_all([country,job]);db.flush()
        source=SourceDocument(country_id=country.id,publisher='Office of the Auditor-General',title='Owned native control',
            url=url,fetch_date=datetime.now(timezone.utc),doc_type=DocumentType.AUDIT,status=DocumentStatus.AVAILABLE,
            md5=hashlib.md5(body).hexdigest(),http_status=200,content_type='application/pdf',file_path=str(original),meta={})
        db.add(source);db.flush()
        source.meta={'pdf_artifact_v1':dict(schema_version=1,sha256=hashlib.sha256(body).hexdigest(),md5=source.md5,
            size_bytes=len(body),source_document_id=source.id,source_url=url,report_title=source.title,publisher=source.publisher,
            validation='pdf_magic_and_final_eof',verification_time=None,verification_time_reason='download_time_not_available')}
        receipt=capture_response(httpx.Response(200,content=body,headers={'content-type':'application/pdf'},
            request=httpx.Request('GET',url)),LocalReceiptStore(tmp_path/'store'),source_kind='pdf')
        authority,reason=capture_pdf_report(original,receipt,domain='audits')
        assert authority is not None,reason
        record=persist_native_report(db,source,authority,context=DomainRunContext(None,False,job.id),domain='audits')
        job.status=IngestionStatus.COMPLETED;job.finished_at=datetime.now(timezone.utc)
        result=job.id,record,source.id,original,retained
        db.commit()
    return result


def test_real_native_observation_accepts_coherent_read_only_snapshot(owned_database,tmp_path):
    job,record,source,original,retained=native_fixture(owned_database,tmp_path)
    with Session(owned_database) as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        db.execute(text('SET LOCAL row_security=off'))
        observed=observe_oag_report(db,job_id=job,record_id=record,original_pdf=original,retained_pdf=retained)
        assert observed['source_document_id']==source
        assert observed['publication']['report']['publisher']=='Office of the Auditor-General'


def test_publication_and_source_cannot_mix_across_a_concurrent_commit(owned_database,tmp_path,monkeypatch):
    from models import SourceDocument
    import seeding.native_report_observations as product
    job,record,source_id,original,retained=native_fixture(owned_database,tmp_path)
    actual=product.current_native_report
    def interleave(*args,**kwargs):
        observed=actual(*args,**kwargs)
        with Session(owned_database) as writer:
            source=writer.get(SourceDocument,source_id)
            metadata=deepcopy(source.meta);source.publisher='Changed concurrent publisher'
            metadata['pdf_artifact_v1']['publisher']=source.publisher;source.meta=metadata
            writer.commit()
        return observed
    monkeypatch.setattr(product,'current_native_report',interleave)
    with Session(owned_database) as db:
        db.execute(text('SET TRANSACTION READ ONLY'));db.execute(text('SET LOCAL row_security=off'))
        try:
            result=observe_oag_report(db,job_id=job,record_id=record,original_pdf=original,retained_pdf=retained)
        except Refusal as exc:
            assert 'snapshot' in str(exc).lower() or 'isolation' in str(exc).lower()
        else:
            assert result['source_identity']['publisher']==result['publication']['report']['publisher'],result

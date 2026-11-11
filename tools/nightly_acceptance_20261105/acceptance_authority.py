"""Domain authority adapters read original bytes and actual committed product rows.

No attachment supplies a success flag. Publication and original acquisition are
different authorities; a hash match or an ordinary current-run result cannot
substitute for either. No acquisition, adoption or provider write occurs here.
"""
import hashlib
from pathlib import Path

from common import BoundEvidence, Refusal, canonical, digest, fields, integer, require
from acceptance_database import readonly


def source_snapshot_reader(session):
    from sqlalchemy import text
    readonly(session)
    require(session.scalar(text('SHOW transaction_isolation')) == 'repeatable read',
            'coherent REPEATABLE READ source snapshot required')


def observe_oag_acquisition(session, *, job_id, source_id, validation_id, original_pdf, retained_pdf):
    from models import Country, DocumentType, Extraction, IngestionJob, IngestionStatus, SourceDocument
    from seeding.retained_report_receipts import aware, validate_retained_pdf
    from seeding.native_report_authority import official_url, source_identity
    from seeding.pdf_artifact import artifact_matches_document
    readonly(session)
    for number in (job_id, source_id, validation_id): integer(number, 1)
    job = session.get(IngestionJob, job_id, populate_existing=True)
    source = session.get(SourceDocument, source_id, populate_existing=True)
    ext = session.get(Extraction, validation_id, populate_existing=True)
    require(job is not None and job.domain == 'audits' and job.dry_run is False
            and job.status in (IngestionStatus.COMPLETED, IngestionStatus.COMPLETED_WITH_ERRORS)
            and job.started_at is not None and job.finished_at is not None,
            'completed exact OAG job required')
    require(source is not None and source.doc_type == DocumentType.AUDIT
            and source.publisher == 'Office of the Auditor-General' and official_url(source.url, 'audits')
            and session.get(Country, source.country_id).iso_code == 'KEN'
            and ext is not None and ext.source_document_id == source_id and ext.extractor == 'pdf-receipt-v1'
            and type(ext.extracted_json) is dict, 'OAG original source/receipt binding differs')
    receipt = ext.extracted_json.get('response_receipt')
    require(type(receipt) is dict, 'OAG response receipt missing')
    validate_retained_pdf(session, source, receipt, job, started=aware(job.started_at), finished=aware(job.finished_at))
    with BoundEvidence() as originals:
        body, readback = originals.read(original_pdf), originals.read(retained_pdf)
        checksum = hashlib.sha256(body).hexdigest()
        artifact = (source.meta or {}).get('pdf_artifact_v1')
        require(body == readback and body.startswith(b'%PDF-') and body[-2048:].rstrip().endswith(b'%%EOF')
                and artifact_matches_document(artifact, source) and artifact['sha256'] == checksum
                and receipt.get('digest') == checksum and receipt.get('byte_size') == len(body),
                'OAG acquisition/original/retained readback differs')
    return {'schema': 'nightly-oag-acquisition-observation-v1', 'job_id': job_id,
            'source_document_id': source_id, 'validation_id': validation_id,
            'source_identity': source_identity(source), 'digest': checksum,
            'publication_authority': False, 'source_adoption_authorized': False}


def observe_oag_report(session, *, job_id, record_id, original_pdf, retained_pdf):
    from models import Extraction, SourceDocument
    from seeding.native_report_observations import current_native_report
    from seeding.retained_report_receipts import _check_origin, aware, validate_retained_pdf
    from seeding.native_report_authority import source_identity
    from seeding.pdf_artifact import artifact_matches_document
    source_snapshot_reader(session); integer(job_id, 1); integer(record_id, 1)
    # The product reader validates current job, source identity, parser, period,
    # publication/catalogue contract, active authority and retained lineage.
    observation = current_native_report(session, record_id, job_id, domain='audits')
    ext = session.get(Extraction, record_id, populate_existing=True)
    source = session.get(SourceDocument, ext.source_document_id, populate_existing=True)
    receipt = ext.extracted_json['response_receipt']
    with BoundEvidence() as originals:
        body = originals.read(original_pdf)
        readback = originals.read(retained_pdf)
        require(0 < len(body) <= 64*1024*1024 and body == readback
                and body.startswith(b'%PDF-') and body[-2048:].rstrip().endswith(b'%%EOF'),
                'OAG original/retained PDF bytes absent, malformed or different')
        checksum = hashlib.sha256(body).hexdigest()
        require(checksum == receipt['digest'] == observation['report']['document_checksum']
                and len(body) == receipt['byte_size'], 'OAG source/acquisition/readback identity differs')
        artifact = (source.meta or {}).get('pdf_artifact_v1')
        require(artifact_matches_document(artifact, source) and artifact['sha256'] == checksum,
                'OAG exact registered source edition differs')
        # current_native_report has already checked the original origin query
        # for retained reuse; fresh receipts must themselves have HTTP authority.
        if 'retained_pdf_validation' not in receipt:
            _check_origin(source, receipt, url=source.url, checksum=checksum, size=len(body),
                          at=aware(observation['report']['verified_at']))
    return {'schema': 'nightly-oag-authority-observation-v1', 'job_id': job_id,
            'source_document_id': source.id, 'source_identity': source_identity(source),
            'acquisition_sha256': checksum, 'publication': observation,
            'source_adoption_authorized': False}


def observe_fiscal_debt(session, *, fiscal_years, debt_years):
    """Consume the fiscal lane's delivered semantic port, never a caller plugin."""
    source_snapshot_reader(session)
    require(type(fiscal_years) is list and len(fiscal_years) == 5
            and all(type(year) is str for year in fiscal_years) and len(set(fiscal_years)) == 5,
            'exact five fiscal years required')
    require(type(debt_years) is list and len(debt_years) == 14
            and all(type(year) is int for year in debt_years) and len(set(debt_years)) == 14,
            'exact fourteen debt years required')
    try:
        from services.fiscal_authority import verify_fiscal_debt_authority
    except ModuleNotFoundError as exc:
        raise Refusal('fiscal lane immutable services.fiscal_authority delivery is pending') from exc
    observation = verify_fiscal_debt_authority(session, fiscal_years=fiscal_years, debt_years=debt_years)
    require(type(observation) is dict and bool(observation), 'fiscal semantic observation unavailable')
    # Return the actual domain report without promoting its unknown/unreviewed
    # schema to an authority verdict. Final integration freezes that schema.
    return {'schema': 'nightly-fiscal-debt-observation-v1', 'observation': observation,
            'source_adoption_authorized': False, 'final_source_schema_acceptance': 'pending'}

"""Optional actual-source receipt acceptance; run only in the bounded OS sandbox.

Assets are supplied outside Git by the trusted launcher. An ordinary skip is not
source qualification. B91_PG_URL must refer to that launcher's private PostgreSQL.
No external source, credentials, production service or dependency fetch is used.
"""
import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

SOURCE_SHA = '033e2aa26aa77351ec46f062573f25ede47d3e3a99978aeacf9a66af5ba717a5'
RETAINED_SHA = '62e30bdc96b78254e8ae67cfa149d2f3dc530abec6d0a9a739376389f2fa04d0'
OLD_SHA = '665f73daf550ce77114683ddadb8d84d575380b17b27a749aac005acd3f9a956'
CANDIDATE_SHA = '4161605e45f79c7e0e89b4ed71cb811308fe39db06e816bfa13b165623cc4330'


def test_actual_pdf_and_postgres_fresh_review_receipt(monkeypatch):
    from sqlalchemy import create_engine, insert, select
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from models import (Audit, Base, Country, DocumentStatus, DocumentType,
                        Entity, EntityType, Extraction, FiscalPeriod, Severity,
                        SourceDocument)
    from seeding.config import SeedingSettings
    from seeding.extractors import oag_county_volume as volume
    from seeding.extractors.reconciliation import _digest, _row, require_review
    from seeding.extractors.reviewed_proposals import without_binding
    from seeding.pdf_parsers import KENYAN_COUNTIES

    pdf = Path(os.environ.get('B96_OAG_REVIEW_PDF', 'tests/fixtures/b93-oag.pdf'))
    retained = Path(os.environ.get('B96_OAG_REVIEW_PROPOSAL', 'tests/fixtures/b93-proposal.json'))
    pg_url = os.environ.get('B91_PG_URL')
    if not pdf.is_file() or not retained.is_file() or not pg_url:
        pytest.skip('optional source/retained-receipt/private-PG inputs absent; not qualification')
    target = make_url(pg_url)
    if (target.get_backend_name(), target.host, target.port, target.database) != ('postgresql', '127.0.0.1', 55867, 'postgres'):
        pytest.fail('only the trusted sandbox private-PG endpoint is admitted')
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == SOURCE_SHA
    assert hashlib.sha256(retained.read_bytes()).hexdigest() == RETAINED_SHA
    observed = json.loads(retained.read_text())
    proposal = observed['attempt']['proposal']
    binding = proposal['revised_rows'][0]['after']['payload']['pdf_artifact_binding_v1']
    doc = SimpleNamespace(id=2542, title=observed['title'], url=observed['url'],
        md5=observed['md5'], file_path=str(pdf), publisher='Office of the Auditor-General',
        meta={'pdf_artifact_v1': binding['artifact'],
              'oag_discovery': {'kind': 'executives', 'fiscal_year': '2024/2025'}})
    captured = []

    def capture(_session, _doc, _extractor, rows, **kwargs):
        captured.extend(rows)
        return {'kept': 0, 'updated': 0, 'inserted': len(rows), 'removed': 0,
                'audits_removed': 0, 'fresh_extraction_ids': []}

    class CaptureQuery:
        def filter_by(self, **kwargs):
            return self

        def count(self):
            return 0

    class CaptureSession:
        def query(self, *args):
            return CaptureQuery()

        def flush(self):
            pass

    monkeypatch.setattr(volume, 'already_extracted', lambda *args: 0)
    monkeypatch.setattr(volume, 'replace_extractions', capture)
    stats = volume.extract_county_volume(CaptureSession(), doc, SeedingSettings(audits_ocr_enabled=False),
        known_counties={volume._letters(c): c for c in KENYAN_COUNTIES})
    assert stats['partial'] is False and len(captured) == 1269
    assert _digest([without_binding(_row(r)) for r in captured]) == CANDIDATE_SHA
    before = {r['id']: r['before'] for r in proposal['revised_rows']}
    old = []
    for offset, candidate in enumerate(captured):
        extraction_id = 4346 + offset
        row = deepcopy(without_binding(_row(candidate)))
        if extraction_id in before:
            row = deepcopy(before[extraction_id])
            row['payload']['amounts'] = [float(v) for v in row['payload']['amounts']]
        old.append({'id': extraction_id, 'source_document_id': 2542,
            'extractor': 'oag_county_volume', 'extracted_json': row['payload'],
            'page_number': row['page'], 'confidence': row['confidence']})
    restored = [SimpleNamespace(id=r['id'], extracted_json=r['extracted_json'],
        page_number=r['page_number'], confidence=r['confidence']) for r in old]
    assert _digest([{'id': r.id, **_row(r)} for r in restored]) == OLD_SHA
    assert [r['id'] - 480 for r in old] == proposal['audit_ids']

    admin = create_engine(target, isolation_level='AUTOCOMMIT')
    name = 'b96_oag_' + uuid4().hex[:16]
    engine = None
    with admin.connect() as conn:
        conn.exec_driver_sql('CREATE DATABASE ' + name)
    try:
        engine = create_engine(target.set(database=name))
        Base.metadata.create_all(engine, tables=[Country.__table__, Entity.__table__,
            FiscalPeriod.__table__, SourceDocument.__table__, Extraction.__table__, Audit.__table__])
        with Session(engine) as db:
            db.add(Country(id=1, iso_code='ZZZ', name='Inert fixture', currency='KES',
                           timezone='UTC', default_locale='en'))
            db.flush()
            db.add(Entity(id=1, country_id=1, type=EntityType.NATIONAL,
                          canonical_name='Inert fixture', slug='inert'))
            db.add(FiscalPeriod(id=1, country_id=1, label='2024/2025',
                start_date=datetime(2024, 7, 1), end_date=datetime(2025, 6, 30)))
            db.flush()
            stored = SourceDocument(id=2542, country_id=1, publisher=doc.publisher,
                title=doc.title, url=doc.url, file_path=doc.file_path, md5=doc.md5,
                fetch_date=datetime(2026, 10, 26), doc_type=DocumentType.AUDIT,
                status=DocumentStatus.AVAILABLE, meta=deepcopy(doc.meta))
            db.add(stored)
            db.flush()
            db.execute(insert(Extraction), old)
            db.execute(insert(Audit), [{'id': r['id'] - 480, 'entity_id': 1,
                'period_id': 1, 'source_document_id': 2542, 'extraction_id': r['id'],
                'finding_text': 'inert reference only', 'severity': Severity.INFO,
                'publishable': False} for r in old])
            db.commit()
            pg_old = list(db.scalars(select(Extraction).order_by(Extraction.id)))
            assert _digest([{'id': r.id, **_row(r)} for r in pg_old]) == OLD_SHA
            assert list(db.scalars(select(Audit.id).order_by(Audit.id))) == proposal['audit_ids']
            require_review(db, stored, 'oag_county_volume', pg_old, captured,
                list(zip(pg_old, captured)), [], 'oag-2542-20261026')
            review = stored.meta['last_reconciliation_review']
            assert review['proposal']['update_ids'] == proposal['update_ids']
            assert review['proposal']['retire_ids'] == []
            assert _digest([without_binding(_row(r)) for r in captured]) == CANDIDATE_SHA
            db.rollback()
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as conn:
            conn.exec_driver_sql('DROP DATABASE ' + name)
        admin.dispose()

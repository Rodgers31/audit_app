"""Real private PostgreSQL: bounded audit writes without partial/stale success."""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from models import Audit, Base, Country, Entity, Extraction, FiscalPeriod, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains.audits import loader
from seeding.types import DomainRunContext


def payload_update(statement):
    sql = statement.lower()
    return sql.startswith('update audits set') and 'finding_text' in sql.split(' where ', 1)[0]


@pytest.fixture()
def store():
    address = os.getenv('B91_PG_URL')
    if not address:
        pytest.skip('explicit private fixture PostgreSQL required')
    url = make_url(address)
    if (url.get_backend_name(), url.host, url.port, url.database) != ('postgresql', '127.0.0.1', 55867, 'postgres'):
        raise ValueError('private fixture identity mismatch')
    schema = 'audit_batch_' + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema} -cstatement_timeout=5000'})
    Base.metadata.create_all(engine, tables=[m.__table__ for m in (Country, Entity, FiscalPeriod, SourceDocument, Extraction, Audit)])
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as session:
            yield session
    finally:
        engine.dispose()
        with admin.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def prepared(session, count=205):
    from datetime import datetime, timezone
    from models import DocumentStatus, DocumentType
    country = Country(name='Kenya', iso_code='KEN', currency='KES', timezone='Africa/Nairobi', default_locale='en-KE')
    session.add(country)
    session.flush()
    doc = SourceDocument(country_id=country.id, publisher='Office of the Auditor-General',
        title='Synthetic audit update fixture', url='https://www.oagkenya.go.ke/fixture.pdf',
        md5='0' * 32, fetch_date=datetime.now(timezone.utc), doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE)
    session.add(doc)
    session.flush()
    for i in range(count):
        session.add(Extraction(source_document_id=doc.id, page_number=i + 1,
            extractor='oag_blue_book', confidence=.9, extracted_json={
                'schema': 'oag_blue_book/v1', 'entity_name': 'The National Treasury',
                'fiscal_year': '2024/2025', 'paragraph_no': i, 'severity': 'INFO',
                'finding_text': f'Original finding {i}', 'pdf_page': i + 1,
                'amounts': [] if i % 3 == 0 else [0 if i % 3 == 1 else i],
                'extraction_method': 'pdfplumber'}))
    session.flush()
    stats = loader.load_blue_book_extractions(session, doc, SeedingSettings(), DomainRunContext(since=None, dry_run=False))
    if stats.created != count:
        raise RuntimeError('fixture did not create expected audit rows')
    for audit in session.scalars(select(Audit)):
        audit.management_response = 'Unrelated operator response'
    session.commit()
    for ext in session.scalars(select(Extraction)):
        ext.extracted_json = {**ext.extracted_json, 'finding_text': ext.extracted_json['finding_text'].replace('Original', 'Revised')}
    session.commit()
    return doc


@pytest.mark.parametrize('count,max_commands', [(205, 3), (1047, 11)])
def test_existing_audit_updates_use_bounded_driver_commands_and_preserve_fields(store, count, max_commands):
    doc = prepared(store, count=count)
    commands = []

    def record_write(conn, cursor, statement, params, context, many):
        if payload_update(statement):
            commands.append(len(params) if many else 1)

    event.listen(store.bind, 'before_cursor_execute', record_write)
    try:
        result = loader.load_blue_book_extractions(store, doc, SeedingSettings(), DomainRunContext(since=None, dry_run=False))
        assert result.updated == count
        assert commands and sum(commands) <= max_commands, f'psycopg2 audit update commands remain per row: {commands}'
        assert store.scalar(text("SELECT count(*) FROM audits WHERE finding_text LIKE 'Revised%'")) == count
        assert all(a.finding_text.startswith('Revised') and a.management_response == 'Unrelated operator response' for a in store.scalars(select(Audit)))
        amounts = [a.amount for a in store.scalars(select(Audit).order_by(Audit.id))]
        assert amounts[0] is None and amounts[1] == 0 and amounts[2] == 2
        commands.clear()
        repeat = loader.load_blue_book_extractions(store, doc, SeedingSettings(), DomainRunContext(since=None, dry_run=False))
        assert repeat.updated == 0 and not commands
        store.rollback()
        assert all(a.finding_text.startswith('Original') for a in store.scalars(select(Audit)))
    finally:
        event.remove(store.bind, 'before_cursor_execute', record_write)


def test_missing_later_update_rolls_back_all_batches_and_new_audits(store):
    doc = prepared(store)
    original_ids = list(store.scalars(select(Audit.id).order_by(Audit.id)))
    template = store.scalars(select(Extraction).limit(1)).one()
    store.add(Extraction(source_document_id=doc.id, page_number=999,
        extractor='oag_blue_book', confidence=.9,
        extracted_json={**template.extracted_json, 'paragraph_no': 999, 'finding_text': 'New finding', 'pdf_page': 999}))
    store.flush()
    injected = []

    def remove_later(conn, cursor, statement, params, context, many):
        if not injected and payload_update(statement):
            injected.append(True)
            conn.execute(text('DELETE FROM audits WHERE id=:id'), {'id': original_ids[-1]})

    event.listen(store.bind, 'before_cursor_execute', remove_later)
    try:
        with pytest.raises(StaleDataError):
            # Same caller-owned source savepoint as extract_and_load.
            with store.begin_nested():
                loader.load_blue_book_extractions(store, doc, SeedingSettings(), DomainRunContext(since=None, dry_run=False))
        assert injected
        assert list(store.scalars(select(Audit.id).order_by(Audit.id))) == original_ids
        assert all(a.finding_text.startswith('Original') for a in store.scalars(select(Audit)))
    finally:
        event.remove(store.bind, 'before_cursor_execute', remove_later)


def test_enclosing_source_rollback_restores_refreshed_identity_map(store):
    doc = prepared(store, count=3)
    audit = store.scalars(select(Audit).order_by(Audit.id).limit(1)).one()
    original = audit.finding_text

    class SourceRefused(RuntimeError):
        pass

    with pytest.raises(SourceRefused):
        with store.begin_nested():
            loader.load_blue_book_extractions(store, doc, SeedingSettings(), DomainRunContext(since=None, dry_run=False))
            assert audit.finding_text.startswith('Revised')
            raise SourceRefused()
    assert audit.finding_text == original
    assert store.scalar(select(Audit.finding_text).where(Audit.id == audit.id)) == original


def test_concurrent_source_hash_change_refuses_without_overwriting_other_writer(store):
    doc = prepared(store, count=205)
    identity = store.scalars(select(Audit.id).order_by(Audit.id.desc()).limit(1)).one()
    injected = []

    def changed_elsewhere(conn, cursor, statement, params, context, many):
        if not injected and payload_update(statement):
            injected.append(True)
            with store.bind.begin() as other:
                other.execute(text('UPDATE audits SET source_hash=:hash WHERE id=:id'),
                              {'hash': 'e' * 64, 'id': identity})

    event.listen(store.bind, 'before_cursor_execute', changed_elsewhere)
    try:
        with pytest.raises(StaleDataError):
            with store.begin_nested():
                loader.load_blue_book_extractions(store, doc, SeedingSettings(), DomainRunContext(since=None, dry_run=False))
        assert injected
        assert store.scalar(select(Audit.source_hash).where(Audit.id == identity)) == 'e' * 64
        assert all(value.startswith('Original') for value in store.scalars(select(Audit.finding_text)))
    finally:
        event.remove(store.bind, 'before_cursor_execute', changed_elsewhere)


def test_duplicate_identity_across_batches_refuses_before_writing(store):
    from copy import deepcopy

    doc = prepared(store, count=101)
    rows = list(store.scalars(select(Audit).order_by(Audit.id)))
    changes = [(row, {**{key: deepcopy(getattr(row, key)) for key in loader._WRITE_FIELDS},
                      'finding_text': 'First bounded revision'}) for row in rows]
    changes.append((rows[0], {**changes[0][1], 'finding_text': 'Conflicting revision'}))
    with pytest.raises(StaleDataError):
        loader._persist_audit_changes(store, doc.id, changes, [])
    assert all(row.finding_text.startswith('Original') for row in rows)
    assert store.scalar(text("SELECT count(*) FROM audits WHERE finding_text LIKE 'Original%'")) == 101


def test_failed_later_batch_expires_mid_batch_orm_refresh(store):
    doc = prepared(store, count=205)
    first = store.scalars(select(Audit).order_by(Audit.id).limit(1)).one()
    last = store.scalar(select(Audit.id).order_by(Audit.id.desc()).limit(1))
    original = first.finding_text
    refreshed = []

    def refresh_after_first(conn, cursor, statement, params, context, many):
        if not refreshed and payload_update(statement):
            refreshed.append(True)
            store.refresh(first, ['finding_text'])
            assert first.finding_text.startswith('Revised')
            conn.execute(text('DELETE FROM audits WHERE id=:id'), {'id': last})

    event.listen(store.bind, 'after_cursor_execute', refresh_after_first)
    try:
        with pytest.raises(StaleDataError):
            with store.begin_nested():
                loader.load_blue_book_extractions(store, doc, SeedingSettings(), DomainRunContext(since=None, dry_run=False))
        assert refreshed
        assert store.scalar(select(Audit.finding_text).where(Audit.id == first.id)) == original
        assert first.finding_text == original
    finally:
        event.remove(store.bind, 'after_cursor_execute', refresh_after_first)

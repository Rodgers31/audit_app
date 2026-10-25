"""One caller-owned transaction for source, extraction and dated instruments."""
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from hashlib import md5

from sqlalchemy import select, text
from models import (Country, Entity, EntityType, SourceDocument, Extraction,
                    DocumentStatus, DocumentType, FigureBasis, DebtCategory, CountyDebtInstrument, CountyDebtObservation)
from services.county_debt import record_county_debt_observation, _county_instrument_schema_available, normalize_county_debt_observation, require_county_debt_keys
from services.receipt_store import configured_receipt_store
from .ownership import require_ownership, TOLERANCE
from seeding.county_borrowing_contract import canonical, parse_publication, EXTRACTOR, DATASET, document_fields, document_metadata, document_matches
from seeding.county_borrowing_contract import CountyBorrowingRefused, edition, county_scope_key


def require_enabled(settings):
    if getattr(settings, 'county_borrowing_ingestion_enabled', None) is not True:
        raise CountyBorrowingRefused('County borrowing ingestion is disabled; explicit opt-in required')


def persist(session, settings, context, key, payload, parsed, fetched_at):
    require_enabled(settings)
    start, now = require_ownership(session, context)
    if (type(fetched_at) is not datetime or fetched_at.utcoffset() is None
            or not start - TOLERANCE <= fetched_at <= now + TOLERANCE):
        raise CountyBorrowingRefused('County borrowing fetch time is outside the owned run')
    expected = parse_publication(key, payload)
    if type(parsed) is not dict or canonical(parsed) != canonical(expected):
        raise CountyBorrowingRefused('County borrowing parsed facts differ from source bytes')
    spec = edition(key)
    country = session.scalar(select(Country).where(Country.iso_code == 'KEN'))
    if country is None:
        raise CountyBorrowingRefused('County borrowing requires an existing Kenya country')
    # Refuse absent/partial tables even for a coverage-only edition: activation
    # must not silently succeed on a destination unable to retain instruments.
    if not _county_instrument_schema_available(session):
        raise CountyBorrowingRefused('County borrowing instrument schema is not adopted')
    entities = session.execute(select(Entity.id, Entity.canonical_name).where(Entity.country_id == country.id,
                              Entity.type == EntityType.COUNTY).limit(48)).all()
    require_county_debt_keys(country.id, *(e.id for e in entities))
    by_slug = {county_scope_key(e.canonical_name): e for e in entities}
    if None in by_slug or len(entities) != len(by_slug) or len(entities) > 47:
        raise CountyBorrowingRefused('County borrowing county identities are ambiguous')
    if any(slug not in by_slug for slug in spec['county_slugs']):
        raise CountyBorrowingRefused('County borrowing requires the declared county identity')
    docs = session.scalars(select(SourceDocument).where(SourceDocument.url == spec['url'])
                           .execution_options(populate_existing=True).limit(3)).all()
    if len(docs) > 1:
        raise CountyBorrowingRefused('County borrowing source identity is ambiguous')
    doc = docs[0] if docs else None
    if doc is not None:
        require_county_debt_keys(doc.id)
    metadata = document_metadata(key)
    fields = document_fields(key, country.id)
    if md5(payload, usedforsecurity=False).hexdigest() != fields['md5']:
        raise CountyBorrowingRefused('County borrowing source checksum differs')
    if doc is not None and not document_matches(doc, key, country.id):
        raise CountyBorrowingRefused('County borrowing stored source provenance differs')
    existing = [] if doc is None else session.scalars(select(Extraction).where(
        Extraction.source_document_id == doc.id).execution_options(populate_existing=True).limit(3)).all()
    require_county_debt_keys(*(e.id for e in existing))
    if existing and (len(existing) != 1 or existing[0].extractor != EXTRACTOR
            or existing[0].page_number != min(map(int, spec['pages']))
            or existing[0].confidence is not None or canonical(existing[0].extracted_json) != canonical(expected)):
        raise CountyBorrowingRefused('County borrowing stored extraction differs')
    intents = []
    for record in expected['instruments']:
        args = dict(record)
        slug = args.pop('county_slug')
        args.pop('obligation_kind')
        args['issue_date'] = datetime.fromisoformat(args['issue_date'])
        args['as_at'] = date.fromisoformat(args['as_at'])
        args['basis'] = FigureBasis(args['basis'])
        args['debt_category'] = DebtCategory(args['debt_category'])
        args = normalize_county_debt_observation(**args)
        args['entity_id'] = by_slug[slug].id
        intents.append(args)
    if context.dry_run:
        return {'created': 0, 'unchanged': int(bool(existing)), 'instruments': 0}
    store = configured_receipt_store(settings)
    if doc is None:
        if store.put(payload) != spec['sha256'] or store.read(spec['sha256']) != payload:
            raise CountyBorrowingRefused('County borrowing retained source bytes differ')
    elif store.read(spec['sha256']) != payload:
        raise CountyBorrowingRefused('County borrowing retained source bytes differ')
    # Validate everything above before any database effects. A savepoint also
    # protects a direct caller that catches a refusal and commits other work.
    with session.begin_nested():
        document_times = {k: fetched_at if doc is None else getattr(doc, k)
                          for k in ('fetch_date', 'last_verified_at', 'last_seen_at', 'created_at')}
        expected_document = freeze(session, {**fields, 'metadata': metadata, **document_times})
        if doc is None:
            doc = SourceDocument(**fields, meta=metadata, **document_times)
            session.add(doc)
            session.flush()
        require_county_debt_keys(doc.id)
        extraction_values = dict(source_document_id=doc.id, page_number=min(map(int, spec['pages'])),
            extractor=EXTRACTOR, extracted_json=expected, confidence=None,
            created_at=existing[0].created_at if existing else fetched_at)
        expected_extraction = freeze(session, extraction_values)
        extraction = existing[0] if existing else Extraction(**extraction_values)
        if not existing:
            session.add(extraction)
            session.flush()
        require_county_debt_keys(extraction.id)
        # This is the sole producer bridge. Only reviewed actual contract
        # mappings enter the existing writer; current live editions have none.
        expected_stocks = []
        for args in intents:
            args['source_document_id'] = doc.id
            args['provenance'] = {'dataset': DATASET, 'extraction_id': extraction.id,
                'artifact_sha256': spec['sha256'], 'edition': key, 'scope': spec['scope']}
            prior = session.execute(select(CountyDebtObservation.revision).join(CountyDebtInstrument).where(
                CountyDebtInstrument.entity_id == args['entity_id'],
                CountyDebtInstrument.identity_namespace == args['identity_namespace'],
                CountyDebtInstrument.instrument_reference == args['instrument_reference'],
                CountyDebtObservation.as_at == args['as_at'],
                CountyDebtObservation.source_document_id == doc.id)).scalar_one_or_none()
            stock = {k: args[k] for k in ('as_at', 'source_document_id', 'page_ref', 'basis',
                                         'principal', 'outstanding', 'interest_rate', 'provenance')}
            stock.update(revision=prior if prior is not None else 1, quarantine_reason=None)
            # Freeze intent before ORM hooks or database triggers can touch it.
            frozen_stock = freeze(session, stock)
            instrument = {k: args[k] for k in ('entity_id', 'identity_namespace', 'instrument_reference',
                                              'lender', 'issue_date', 'currency', 'debt_category')}
            frozen_instrument = freeze(session, instrument)
            identity = record_county_debt_observation(session, **args)
            expected_stocks.append((identity, frozen_stock, frozen_instrument))
        session.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
        docs = session.execute(select(SourceDocument.__table__).where(SourceDocument.url == spec['url']).limit(3)).mappings().all()
        extracts = session.execute(select(Extraction.__table__).where(Extraction.source_document_id == doc.id).limit(3)).mappings().all()
        for rows, identity, frozen in ((docs, doc.id, expected_document), (extracts, extraction.id, expected_extraction)):
            if len(rows) != 1 or rows[0]['id'] != identity or freeze(session, {k:v for k,v in rows[0].items() if k != 'id'}) != frozen:
                raise CountyBorrowingRefused('County borrowing persisted source/extraction readback differs')
        retained_stock_ids = session.scalars(select(CountyDebtObservation.id).where(
            CountyDebtObservation.source_document_id == doc.id).limit(48)).all()
        if set(retained_stock_ids) != {identity for identity, _, _ in expected_stocks}:
            raise CountyBorrowingRefused('County borrowing persisted stock identity set readback differs')
        for identity, frozen_stock, frozen_instrument in expected_stocks:
            observation = session.execute(select(CountyDebtObservation.__table__).where(CountyDebtObservation.id == identity)).mappings().one()
            instrument = session.execute(select(CountyDebtInstrument.__table__).where(CountyDebtInstrument.id == observation['instrument_id'])).mappings().one()
            if (freeze(session, {k:v for k,v in observation.items() if k not in ('id','instrument_id')}) != frozen_stock
                    or freeze(session, {k:v for k,v in instrument.items() if k != 'id'}) != frozen_instrument):
                raise CountyBorrowingRefused('County borrowing persisted stock/instrument readback differs')
        require_ownership(session, context)
        return {'created': int(not existing), 'unchanged': int(bool(existing)),
                'instruments': len(expected['instruments'])}


def freeze(session, values):
    normalized = {}
    for key, value in values.items():
        if isinstance(value, datetime) and value.utcoffset() is not None:
            value = session.scalar(text("SELECT timezone(current_setting('TimeZone'), CAST(:v AS timestamptz))"), {'v':value})
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = str(value.normalize())
        elif isinstance(value, Enum):
            value = value.value
        normalized[key] = value
    return canonical(normalized)

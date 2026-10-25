"""Bounded read-side coverage from existing source/extraction records.

A checked national guarantee register is only that scope. An audit narrative
without a dated contract balance does not become an instrument or a zero.
"""
from sqlalchemy import select
from models import Country, Entity, EntityType, SourceDocument, Extraction, DocumentStatus
from seeding import county_borrowing_contract as parser, county_borrowing_contract as source

MAX_COUNTIES = 47
MAX_SOURCE_ACCOUNTS = 8


def county_borrowing_coverage(db, entity_ids):
    ids = tuple(entity_ids)
    if (not 1 <= len(ids) <= MAX_COUNTIES or len(set(ids)) != len(ids)
            or any(type(i) is not int or i <= 0 for i in ids)):
        raise ValueError('County borrowing coverage requires 1..47 distinct county IDs')
    entities = db.execute(select(Entity.id, Entity.slug, Entity.country_id).join(Country).where(
        Entity.id.in_(ids), Entity.type == EntityType.COUNTY, Country.iso_code == 'KEN')).all()
    if len(entities) != len(ids):
        raise ValueError('County borrowing coverage requires existing Kenyan counties')
    # One source/extraction cohort for all counties; never one query per county.
    rows = db.execute(select(SourceDocument, Extraction).join(Extraction).where(
        SourceDocument.meta['dataset'].astext == parser.DATASET,
        Extraction.extractor == parser.EXTRACTOR).order_by(Extraction.id.desc())
        .limit(MAX_SOURCE_ACCOUNTS + 1)).all()
    if len(rows) > MAX_SOURCE_ACCOUNTS:
        raise RuntimeError('County borrowing coverage source bound exceeded; reconcile accounts')
    result = {i: {'status': 'not_integrated', 'complete_liability_coverage': False, 'sources': []}
              for i in ids}
    seen = set()
    for doc, extraction in rows:
        meta = doc.meta if type(doc.meta) is dict else {}
        key = meta.get('edition')
        spec = source.edition(key)
        if (doc.country_id not in {row.country_id for row in entities}
                or key in seen or not parser.document_matches(doc, key, doc.country_id)
                or extraction.page_number != min(map(int, spec['pages'])) or extraction.confidence is not None
                or parser.canonical(extraction.extracted_json) != parser.canonical(parser.expected_extraction(key))):
            raise RuntimeError('County borrowing coverage provenance differs; withhold the projection')
        seen.add(key)
        for i, slug, _ in entities:
            if spec['county_slugs'] and slug not in spec['county_slugs']:
                continue
            account = {'status': spec['status'], 'scope': spec['scope'], 'reason': spec['reason'],
                'reporting_period_end': spec['reporting_period_end'], 'source_document_id': doc.id,
                'extraction_id': extraction.id, 'url': doc.url,
                'pdf_pages': [int(p) for p in spec['pages']], 'artifact_sha256': spec['sha256']}
            result[i]['sources'].append(account)
            if result[i]['status'] != 'withheld_or_conflicting':
                result[i]['status'] = spec['status']
    return result

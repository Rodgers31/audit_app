"""Require a parser outcome and retained evidence before accepting a PDF."""
from models import Extraction
from sqlalchemy import func, select
from ...extractors.reconciliation import IncompleteExtraction


def verify_outcome(session, doc, stats, parser_id):
    if not isinstance(stats, dict):
        raise IncompleteExtraction('parser outcome must be an object')
    counts = [stats.get(key, 0) for key in ('created', 'skipped', 'existing')]
    if (any(type(n) is not int or n < 0 for n in counts) or not sum(counts)
            or 'partial' in stats and type(stats['partial']) is not bool):
        raise IncompleteExtraction('parser returned no valid extraction outcome')
    admitted = {'oag_blue_book': ('oag_blue_book',),
                'oag_county_audit': ('oag_blue_book', 'oag_county_volume', 'oag_county_audit')}.get(parser_id, ())
    evidence = session.execute(select(func.count()).select_from(Extraction).where(
        Extraction.source_document_id == doc.id,
        Extraction.extractor.in_(admitted),
    )).scalar_one()
    if evidence != sum(counts):
        raise IncompleteExtraction('parser outcome disagrees with retained extraction inventory')
    if (not isinstance(doc.md5, str) or len(doc.md5) != 32
            or any(c not in '0123456789abcdef' for c in doc.md5)):
        raise IncompleteExtraction('source digest is missing or malformed')
    if parser_id == 'oag_blue_book':
        from ...extractors.oag_blue_book import extraction_is_current
        if not extraction_is_current(doc):
            raise IncompleteExtraction('national extraction does not match current source and parser')
    elif not doc.md5 or not isinstance(doc.meta, dict) or doc.meta.get('extracted_md5') != doc.md5:
        raise IncompleteExtraction('county extraction does not match current source')

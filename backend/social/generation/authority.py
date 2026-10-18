"""Digest-only current source port, shared by the reader and admission gates.

The view exposes no monetary cells or source rows to the worker. An immutable
event proves what was reviewed; this witness additionally proves that its
underlying record, eligibility, lineage and retained receipts still match.
"""
from sqlalchemy import text


def current_report_authority(db, record_id, ingestion_id, *, lock=True):
    relation = 'social_report_source_authority' if lock else 'social_report_source_authority_snapshot'
    query = text('''SELECT authority_fingerprint
        FROM '''+relation+'''
        WHERE record_id=:record AND ingestion_id=:ingestion LIMIT 2''')
    params = {'record': record_id, 'ingestion': ingestion_id}
    if lock and db.scalar(text('SHOW transaction_isolation')) != 'read committed':
        return None
    rows = list(db.execute(query, params).scalars())
    if lock and len(rows) == 1:
        # The first statement may wait for an already-running source writer.
        # Its statement snapshot predates that writer's commit. Locks now hold
        # the county/inputs stable; a second READ COMMITTED statement sees the
        # completed writer and any conflicting cohort insertion it committed.
        rows = list(db.execute(query, params).scalars())
    return rows[0] if len(rows) == 1 else None


def verify_report_authority(db, source):
    from ..service import SocialError
    report = source.get('report') if isinstance(source, dict) else None
    if report is None:
        return
    record = report.get('source_record_id') if isinstance(report, dict) else None
    ingestion = source.get('ingestion_id')
    expected = report.get('authority_fingerprint') if isinstance(report, dict) else None
    if (type(record) is not int or not 0 < record <= 2147483647
            or type(ingestion) is not str or not ingestion.isascii() or not ingestion.isdecimal()
            or not 0 < int(ingestion) <= 2147483647
            or type(expected) is not str or len(expected) != 64
            or current_report_authority(db, record, int(ingestion)) != expected):
        raise SocialError('SOURCE_REVIEW_REQUIRED', 'Current report source authority changed. Review its evidence again.', 422)

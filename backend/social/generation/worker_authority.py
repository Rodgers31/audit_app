"""Digest-only delivery witness; no ORM or source-table access in the worker.

The qualified reader remains the authority for meaning. An immutable revision binds
this separate witness to the exact inputs it read. Changed inputs require human
review again; missing/legacy witnesses never become delivery authority.
"""
import re

from sqlalchemy import text

from ..service import SocialError

VERSION = 1
DOMAIN_LOCKS = {'national_budget': 1, 'revenue_by_source': 2, 'audits': 3, 'pending_bills': 4}
FIELDS = {'version', 'kind', 'domain', 'record_id', 'ingestion_id', 'fingerprint'}


def identity(source):
    if type(source) is not dict:
        raise ValueError('Exact source required')
    job = source.get('ingestion_id')
    if type(job) is not str or not re.fullmatch(r'[1-9][0-9]{0,9}', job) or int(job) > 2147483647:
        raise ValueError('Exact job required')
    report, financial = source.get('report'), source.get('financial')
    if type(financial) is dict and report is None:
        kind, domain, record = 'financial', financial.get('native_domain'), financial.get('record_id')
        if domain not in {'national_budget', 'revenue_by_source', 'pending_bills'}:
            raise ValueError('Supported financial domain required')
    elif type(report) is dict and report.get('native_domain') is not None and financial is None:
        kind, domain, record = 'report', report.get('native_domain'), report.get('source_record_id')
        if domain not in DOMAIN_LOCKS:
            raise ValueError('Supported native domain required')
    elif report is None and financial is None:
        key = source.get('source_key')
        match = re.fullmatch(r'budget_lines:([1-9][0-9]{0,9}):actual_spent', key or '')
        if source.get('source_type') != 'cob' or match is None:
            raise ValueError('Supported county financial source required')
        kind, domain, record = 'county_financial', 'counties_budget', int(match[1])
    else:
        raise ValueError('Separate native source required')
    if type(record) is not int or not 0 < record <= 2147483647:
        raise ValueError('Exact record required')
    return dict(version=VERSION, kind=kind, domain=domain, record_id=record, ingestion_id=int(job))


def _fingerprint(db, selected, *, lock):
    if selected['kind'] == 'county_financial':
        from .authority import current_report_authority
        return current_report_authority(db, selected['record_id'], selected['ingestion_id'], lock=lock)
    relation = 'public.social_native_source_authority' if lock else 'public.social_native_source_authority_snapshot'
    available = db.scalar(text('''SELECT CASE WHEN to_regclass(:relation) IS NULL THEN false
        ELSE has_table_privilege(current_user,to_regclass(:relation),'SELECT') END'''), {'relation': relation})
    if available is not True:
        return None
    query = text('SELECT authority_fingerprint FROM '+relation+''' WHERE source_kind=:kind
        AND native_domain=:domain AND record_id=:record_id AND ingestion_id=:ingestion_id LIMIT 2''')
    rows = list(db.execute(query, selected).scalars())
    if lock and len(rows) == 1:
        # A statement started before a competing writer committed can wait on
        # its locks. The second READ COMMITTED snapshot sees that commit.
        rows = list(db.execute(query, selected).scalars())
    return rows[0] if len(rows) == 1 else None


def capture_worker_authority(db, source):
    """Optional revision annotation, after the privileged reader qualified it.

    Draft creation remains available on pre-migration schemas. Absence is an
    explicit delivery hold, never a reason to fabricate a witness or grant SQL.
    """
    if db.get_bind().dialect.name != 'postgresql':
        return None
    try:
        selected = identity(source)
    except (ValueError, TypeError):
        return None
    relation = ('public.social_report_source_authority_snapshot' if selected['kind'] == 'county_financial'
                else 'public.social_native_source_authority_snapshot')
    if db.scalar(text('SELECT to_regclass(:relation)'), {'relation': relation}) is None:
        return None
    if selected['kind'] != 'county_financial':
        from importlib import import_module
        prefix = 'backend.seeding.' if __package__.startswith('backend.') else 'seeding.'
        import_module(prefix+'native_report_authority').lock_native_domain(db, selected['domain'])
    # Lock the full digest dependency set first, then re-read meaning from the
    # privileged reader. A writer can finish between the initial qualification
    # and this call; its invalid new state must not mint a fresh valid witness.
    fingerprint = _fingerprint(db, selected, lock=True)
    if type(fingerprint) is not str or not re.fullmatch(r'[a-f0-9]{64}', fingerprint):
        raise SocialError('SOURCE_REVIEW_REQUIRED', 'Current source witness is unavailable.', 422)
    from importlib import import_module
    prefix = 'backend.seeding.' if __package__.startswith('backend.') else 'seeding.'
    try:
        if selected['kind'] == 'county_financial':
            module = import_module(prefix+'source_observations')
            current = module.current_county_evidence(db, record_id=selected['record_id'],
                ingestion_id=selected['ingestion_id'], report=False)
        else:
            name = 'native_report_observations' if selected['kind'] == 'report' else 'native_financial_observations'
            module = import_module(prefix+name)
            reader = module.current_native_report if selected['kind'] == 'report' else module.current_native_financial
            current = reader(db, selected['record_id'], selected['ingestion_id'], domain=selected['domain'], lock=True)
        from .contracts import SourceObservation
        if SourceObservation.model_validate(current).model_dump(mode='json') != source:
            raise ValueError('Current source facts differ')
        if _fingerprint(db, selected, lock=True) != fingerprint:
            raise ValueError('Source dependencies changed during qualification')
    except (ValueError, TypeError, KeyError):
        raise SocialError('SOURCE_REVIEW_REQUIRED', 'Current source evidence changed. Review it again.', 422) from None

    return dict(selected, fingerprint=fingerprint)


def verify_worker_authority(db, source, witness):
    """Core Connection-safe check with only digest-view SELECT privileges."""
    try:
        selected = identity(source)
        if (type(witness) is not dict or set(witness) != FIELDS
                or type(witness.get('version')) is not int or witness['version'] != VERSION
                or any(type(witness.get(k)) is not type(v) or witness[k] != v for k,v in selected.items())
                or type(witness.get('fingerprint')) is not str
                or not re.fullmatch(r'[a-f0-9]{64}', witness['fingerprint'])
                or db.scalar(text('SHOW transaction_isolation')) != 'read committed'):
            raise ValueError('Exact current witness required')
        if selected['kind'] != 'county_financial':
            db.execute(text("SELECT set_config('lock_timeout', CASE WHEN setting::bigint=0 THEN '2000' ELSE LEAST(setting::bigint,2000)::text END, true) FROM pg_settings WHERE name='lock_timeout'"))
            db.execute(text('SELECT pg_advisory_xact_lock(802,:domain)'), {'domain': DOMAIN_LOCKS[selected['domain']]})
        if _fingerprint(db, selected, lock=True) != witness['fingerprint']:
            raise ValueError('Source inputs changed')
    except (ValueError, TypeError, KeyError):
        raise SocialError('SOURCE_REVIEW_REQUIRED', 'Current source evidence changed. Review it again.', 422) from None


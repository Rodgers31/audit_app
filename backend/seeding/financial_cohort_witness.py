"""Private, bounded snapshots of inputs held while financial evidence qualifies.

Only hashes cross the database connection. PostgreSQL's built-in SHA256 needs
no extension or permission change. These snapshots supplement, never replace,
the existing native qualification and report-authority readers.
"""
from copy import deepcopy
import re
from weakref import WeakKeyDictionary

from sqlalchemy import text

from .native_report_authority import digest
from .source_observations import SourceObservationUnavailable

_TABLES = frozenset({'loans', 'budget_lines', 'revenue_by_source', 'source_documents',
    'countries', 'entities', 'fiscal_periods', 'extractions'})
_TOKEN = object()
_ISSUED = WeakKeyDictionary()


class FinancialCohortWitness:
    def __init__(self, value, *, token=None):
        if token is not _TOKEN:
            raise TypeError('Qualified financial cohort witness required')
        self.value = deepcopy(value)
        _ISSUED[self] = digest(self.value)

    def intact(self):
        return witness_is_intact(self)


def witness_is_intact(witness):
    """Issuer-owned validation: never dispatch a method supplied by the object."""
    try:
        return (type(witness) is FinancialCohortWitness and type(witness.value) is dict
                and _ISSUED.get(witness) == digest(witness.value))
    except (TypeError, ValueError, AttributeError):
        return False


def input_fingerprints(db, selections, *, lock):
    if (type(lock) is not bool or db.get_bind().dialect.name != 'postgresql'
            or type(selections) is not dict or not selections or set(selections) - _TABLES):
        raise SourceObservationUnavailable('Bounded financial input snapshot required')
    branches, params, expected = [], {}, set()
    for table, values in sorted(selections.items()):
        if (type(values) not in (list, tuple, set) or not 1 <= len(values) <= 4000
                or any(type(v) is not int or not 0 < v <= 2147483647 for v in values)):
            raise SourceObservationUnavailable('Bounded financial input snapshot required')
        ids = sorted(set(values))
        expected.update((table, value) for value in ids)
        params[table] = ids
        # Every identifier comes from the fixed whitelist, never source text.
        held = ' FOR SHARE' if lock else ''
        branches.append(f"SELECT '{table}' AS kind,r.id,"
            "encode(sha256(convert_to(r::text,'UTF8')),'hex') AS fingerprint "
            f"FROM (SELECT * FROM {table} WHERE id=ANY(:{table}) ORDER BY id{held}) AS r")
    if len(expected) > 10000:
        raise SourceObservationUnavailable('Bounded financial input snapshot required')
    rows = db.execute(text(' UNION ALL '.join(branches)), params).all()
    if (len(rows) != len(expected) or {(r[0], r[1]) for r in rows} != expected
            or any(type(r[2]) is not str or re.fullmatch('[a-f0-9]{64}', r[2]) is None for r in rows)):
        raise SourceObservationUnavailable('Complete financial input snapshot required')
    result = {}
    for table, identity, fingerprint in rows:
        result.setdefault(table, {})[str(identity)] = fingerprint
    return result


def lock_qualified_inputs(db, *, domain, row, source, report, evidence_row):
    """Lock context before measure qualification, retaining only input hashes."""
    if __package__.startswith('backend.'):
        from backend.services.figure_qualification import _evidence_entries
    else:
        from services.figure_qualification import _evidence_entries
    model_table = {'pending_bills': 'loans', 'national_budget': 'budget_lines',
                   'revenue_by_source': 'revenue_by_source'}[domain]
    receipts = {report['source_record_id']}
    documents = {source.id}
    for item in _evidence_entries(evidence_row):
        ref = item.get('receipt') if type(item) is dict else None
        if type(ref) is dict:
            receipt_id, document_id = ref.get('extraction_id'), ref.get('source_document_id')
            if type(receipt_id) is int and 0 < receipt_id <= 2147483647:
                receipts.add(receipt_id)
            if type(document_id) is int and 0 < document_id <= 2147483647:
                documents.add(document_id)
    if len(receipts) > 4000 or len(documents) > 4000:
        raise SourceObservationUnavailable('Bounded financial input snapshot required')
    # Retained receipts refer directly to the original acquisition. Lock both;
    # the native reader still validates the actual origin and all chronology.
    origins = db.execute(text("SELECT extracted_json->'response_receipt'->'retained_pdf_validation'"
        "->'origin_extraction_id' FROM extractions WHERE id=ANY(:ids) ORDER BY id FOR SHARE"),
        {'ids': sorted(receipts)}).scalars().all()
    for origin in origins:
        if origin is not None:
            if type(origin) is not int or not 0 < origin <= 2147483647:
                raise SourceObservationUnavailable('Exact retained financial origin required')
            receipts.add(origin)
    selections = {model_table: {row.id}, 'source_documents': documents,
        'countries': {source.country_id}, 'extractions': receipts}
    if domain in ('national_budget', 'pending_bills'):
        selections['entities'] = {row.entity_id}
    if domain == 'national_budget':
        selections['fiscal_periods'] = {row.period_id}
    return input_fingerprints(db, selections, lock=True)


def _qualified_witness(observation, inputs):
    from importlib import import_module
    service = import_module('backend.social.generation.service'
        if __package__.startswith('backend.') else 'social.generation.service')
    contracts = import_module('backend.social.generation.contracts'
        if __package__.startswith('backend.') else 'social.generation.contracts')
    value = contracts.SourceObservation.model_validate(observation)
    return FinancialCohortWitness(dict(record_id=value.financial.record_id,
        ingestion_id=value.evidence_version, domain=value.financial.native_domain,
        source_type=value.source_type, source_key=value.source_key,
        fingerprint=service.semantic_fingerprint(value), state=service.financial_state(value),
        report_record_id=value.financial.report_record_id,
        authority_fingerprint=value.financial.authority_fingerprint, inputs=inputs), token=_TOKEN)

"""Bind reviewed contract mappings to visible source fields before any write.

This checks transcription, not the truth or legal approval of a publisher's
statement. Human source review must still establish that the fields describe
one actual county contract and outstanding stock, rather than a flow/aggregate.
Coverage-only v1 editions keep their original extraction/parser identities.
"""
from datetime import datetime, time
from decimal import Decimal, InvalidOperation, localcontext
from io import BytesIO
import re

import pdfplumber

from seeding.county_borrowing_contract import CountyBorrowingRefused, county_scope_key

_SCALES = {'units': Decimal(1), 'thousands': Decimal(1000),
           'millions': Decimal(1000000), 'billions': Decimal(1000000000)}
_FIELDS = {'county_name', 'identity_namespace', 'instrument_reference', 'lender', 'issue_date', 'as_at',
           'principal', 'outstanding', 'interest_rate'}
_CONTEXT = {'format', 'statement', 'fields', 'currency_text', 'unit', 'unit_text', 'stock_label'}
_NUMBER = re.compile(r'(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.[0-9]+)?\Z')
_LABELS = (
    ('County', 'county_name'), ('Identity namespace', 'identity_namespace'),
    ('Contract reference', 'instrument_reference'), ('Lender', 'lender'),
    ('Issue date', 'issue_date'), ('As at', 'as_at'), ('Currency', 'currency'),
    ('Unit', 'unit'), ('Basis', 'basis'), ('Obligation', 'obligation_kind'),
    ('Principal', 'principal'), ('Outstanding', 'outstanding'), ('Interest rate', 'interest_rate'),
)
_STATEMENT = re.compile(' '.join(
    re.escape(label) + r': (?P<' + name + r'>[^;]+);' for label, name in _LABELS
))


def _refuse():
    raise CountyBorrowingRefused('County borrowing mapping source evidence is absent, malformed or differs')


def _text(value):
    if type(value) is not str or not value.strip() or len(value) > 8000:
        _refuse()
    return ' '.join(value.split())


def _date(value):
    value = _text(value)
    for fmt in ('%Y-%m-%d', '%d %B %Y', '%d %b %Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    _refuse()


def _number(value, scale):
    if type(value) is not str or len(value) > 80 or not _NUMBER.fullmatch(value):
        _refuse()
    try:
        # The source token is bounded at 80 characters; 128 digits covers all
        # supported scales without rounding away a nonzero source fraction.
        with localcontext() as context:
            context.prec = 128
            return Decimal(value.replace(',', '')) * scale
    except InvalidOperation:
        _refuse()


def validate_mapping_source_evidence(records, payload):
    """Require one bounded, same-page labelled statement per nonempty mapping.

    Call after the shared instrument validator and verified-edition parser,
    before preview success, receipt storage or database mutation. Every mapped
    value is checked; missing numeric values remain missing, never printed zero.
    Only the explicit labelled_contract_stock_v1 grammar is supported. A table
    or narrative with a different layout requires a reviewed source adapter;
    arbitrary metadata cannot choose labels, spans or field associations.
    """
    if type(records) is not list or len(records) > 47 or type(payload) is not bytes:
        _refuse()
    if not records:
        return
    pages = {}
    try:
        with pdfplumber.open(BytesIO(payload)) as pdf:
            for record in records:
                evidence = record.get('source_evidence')
                if type(evidence) is not dict or set(evidence) != _CONTEXT:
                    _refuse()
                fields = evidence['fields']
                if type(fields) is not dict or set(fields) != _FIELDS:
                    _refuse()
                page_ref = record['page_ref']
                if type(page_ref) is not str or not re.fullmatch(r'p\.[1-9][0-9]*', page_ref):
                    _refuse()
                page_number = int(page_ref[2:])
                if not 1 <= page_number <= len(pdf.pages):
                    _refuse()
                if page_number not in pages:
                    pages[page_number] = ' '.join((pdf.pages[page_number-1].extract_text() or '').split())
                statement = _text(evidence['statement'])
                if (evidence['format'] != 'labelled_contract_stock_v1'
                        or statement not in pages[page_number]):
                    _refuse()
                match = _STATEMENT.fullmatch(statement)
                if match is None:
                    _refuse()
                extracted = match.groupdict()
                for name in ('principal', 'outstanding', 'interest_rate'):
                    if extracted[name] == 'not reported':
                        extracted[name] = None
                if (any(fields[name] != extracted[name] for name in _FIELDS)
                        or evidence['currency_text'] != extracted['currency']
                        or evidence['unit'] != extracted['unit']
                        or extracted['basis'] != record['basis']
                        or extracted['obligation_kind'] != record['obligation_kind']
                        or fields['identity_namespace'] != record['identity_namespace']
                        or evidence['currency_text'] != 'KES'
                        or evidence['unit'] not in _SCALES
                        or evidence['unit_text'] != evidence['unit']
                        or evidence['stock_label'] != 'Outstanding'
                        or record['currency'] != 'KES' or record['basis'] != 'actual'
                        or county_scope_key(fields['county_name']) != record['county_slug']
                        or fields['instrument_reference'] != record['instrument_reference']
                        or fields['lender'] != record['lender']):
                    _refuse()
                issue = datetime.fromisoformat(record['issue_date'])
                if (issue.tzinfo is not None or issue.time() != time()
                        or _date(fields['issue_date']) != issue.date()
                        or _date(fields['as_at']).isoformat() != record['as_at']):
                    _refuse()
                for name in ('principal', 'outstanding', 'interest_rate'):
                    raw, mapped = fields[name], record.get(name)
                    if raw is None or mapped is None:
                        if raw is not None or mapped is not None:
                            _refuse()
                    else:
                        # Interest rates are percentages, never currency-scaled.
                        scale = Decimal(1) if name == 'interest_rate' else _SCALES[evidence['unit']]
                        if _number(raw, scale) != Decimal(str(mapped)):
                            _refuse()
    except CountyBorrowingRefused:
        raise
    except Exception:
        _refuse()

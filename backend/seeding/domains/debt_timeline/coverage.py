"""Versioned per-year diagnostics; never a replacement publication gate.

A CBK row is the latest *monthly* stock observed within a calendar year. A
World Bank denominator is calendar-year GDP. Their ratio is a derived pair,
not an assertion that a mid-year debt stock is a year-end balance.
"""
from datetime import datetime, timezone
import re
from models import DebtTimeline, Extraction
from services.figure_qualification import qualify_rows
from .writer import _observed_evidence, _raw_kes

CONTRACT = 'debt-calendar-observation-coverage-v1'


def coverage_report(session, records, *, now=None):
    now = now or datetime.now(timezone.utc)
    if not records or len({r.year for r in records}) != len(records):
        raise ValueError('Nonempty distinct debt coverage years required')
    if any(type(r.year) is not int or not 1900 <= r.year <= 9999 for r in records):
        raise ValueError('Calendar coverage years required')
    rows = session.query(DebtTimeline).filter(DebtTimeline.year.in_([r.year for r in records])).all()
    by_year = {r.year: r for r in rows}
    qualifications = qualify_rows(session, 'debt_timeline', rows)
    ids = {item.get('receipt', {}).get('extraction_id')
           for row in rows for item in (row.meta or {}).get('source_evidence', [])
           if isinstance(item, dict) and type(item.get('receipt')) is dict}
    extractions = {e.id: e for e in session.query(Extraction).filter(Extraction.id.in_(ids - {None})).all()} if ids - {None} else {}
    output = []
    for record in sorted(records, key=lambda r: r.year):
        row = by_year.get(record.year)
        measures = {}
        for measure in ('external', 'domestic', 'total', 'gdp'):
            qualified = row is not None and qualifications.get(row.id, {}).get(measure, {}).get('status') == 'verified'
            incoming = _observed_evidence(record, measure, _raw_kes(getattr(record, measure)))
            stored = [item for item in (row.meta or {}).get('source_evidence', [])
                      if isinstance(item, dict) and item.get('identity', {}).get('measure') == measure] if row else []
            current = []
            if len(incoming) == len(stored) == 1:
                candidate, accepted = incoming[0], stored[0]
                extraction = extractions.get(accepted.get('receipt', {}).get('extraction_id'))
                captured = candidate['_response_receipt']
                persisted = (extraction.extracted_json or {}).get('response_receipt', {}) if extraction else {}
                fields = ('identity', 'locator', 'raw_value', 'raw_unit', 'transformation', 'value')
                if (extraction is not None
                        and captured._bound_source
                        and captured._bound_source[0][0] == extraction.source_document_id
                        and all(candidate.get(k) == accepted.get(k) for k in fields)
                        and persisted.get('digest') == captured.get('digest')
                        and persisted.get('acquired_at') == captured.get('acquired_at')
                        and _raw_kes(getattr(record, measure)) == getattr(row, measure)):
                    current = incoming
            state = ('observed_this_run' if qualified else 'observed_unretained') if current else 'retained_qualified' if qualified else 'unqualified'
            absence = None if current or qualified else ('annual_period_not_ended' if measure == 'gdp' and record.year >= now.year else 'not_observed_in_selected_source')
            entries = current or (stored if qualified else [])
            item = entries[0] if len(entries) == 1 else {}
            receipt = item.get('_response_receipt')
            if receipt is None:
                extraction = extractions.get(item.get('receipt', {}).get('extraction_id'))
                receipt = (extraction.extracted_json or {}).get('response_receipt', {}) if extraction else {}
            locator = item.get('locator') or {}
            match = re.match(r'^(\d{4})-(\d{2}) / ', str(locator.get('cell', '')))
            month = match.group(0).split(' / ')[0] if match and int(match[1]) == record.year and 1 <= int(match[2]) <= 12 else None
            measures[measure] = {
                'state': state, 'absence_reason': absence, 'period': str(record.year),
                'period_kind': 'calendar_year' if measure == 'gdp' else 'latest_observed_month_in_calendar_year',
                'stock_as_of_month': month, 'unit': 'KES',
                'basis': 'current_prices' if measure == 'gdp' else 'actual',
                'source_url': receipt.get('request_url'), 'source_digest': receipt.get('digest'),
                'acquired_at': receipt.get('acquired_at'), 'locator': locator or None,
                # Acquisition time is not publication time or source vintage.
                'publication_date': None, 'vintage_date': None,
            }
        stock_month = measures['total']['stock_as_of_month']
        ratio_qualified = row is not None and qualifications.get(row.id, {}).get('gdp_ratio', {}).get('status') == 'verified'
        output.append({'year': record.year, 'measures': measures,
            'ratio': {'state': 'qualified_derived_pair' if ratio_qualified else 'unavailable',
                      'stock_as_of_month': stock_month, 'gdp_calendar_year': record.year,
                      'year_end_stock': stock_month == f'{record.year}-12',
                      'reason': None if ratio_qualified else 'stock_denominator_pair_unqualified'}})
    return {'contract': CONTRACT, 'years': output,
            'note': 'Acquisition is not publication. Unknown vintage remains null; no forecast or county balance admitted.'}

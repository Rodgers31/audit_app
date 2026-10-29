"""Versioned financial wording from qualified cells, without derived claims."""
from decimal import Decimal

from ..service import SocialError
from .contracts import SourceObservation

VERSION = 'financial-v2'
SCALES = {'units': '', 'thousands': ' thousand', 'millions': ' million', 'billions': ' billion'}
PENDING_NOTES = {
    'assembly figure not reported': 'The assembly figure was not reported.',
    'publisher marks this row inconsistent': 'The publisher marks this row as inconsistent.',
    'chapter table differs from the Grand Total': 'The chapter table differs from the Grand Total.',
}


def unavailable():
    raise SocialError('UNRESOLVED_TEMPLATE', 'The financial copy needs one consistent, supported reporting scope.', 422)


def amount(fact):
    number = Decimal(fact.value)
    if number == 0:
        number = Decimal(0)
    whole, point, fraction = format(number, ',f').partition('.')
    fraction = fraction.rstrip('0')
    exact = whole + (point + fraction if fraction else '')
    return ('KSh' if fact.unit == 'KES' else fact.unit) + ' ' + exact + SCALES[fact.scale]


def day(value):
    months = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
              'September', 'October', 'November', 'December')
    return f'{value.day} {months[value.month - 1]} {value.year}'


def render_financial(observation):
    observation = SourceObservation.model_validate(observation.model_dump(mode='python'))
    if observation.financial is None or not observation.facts:
        unavailable()
    facts = observation.facts
    first = facts[0]
    if (any(f.classification != 'actual' or f.unit != 'KES' for f in facts)
            or any((f.entity, f.period, f.publisher, f.source_document_id, f.document_checksum)
                   != (first.entity, first.period, first.publisher, first.source_document_id,
                       first.document_checksum) for f in facts)):
        unavailable()
    domain = observation.financial.native_domain
    paragraphs = []
    if domain == 'pending_bills':
        if len(facts) != 1 or not first.metric.startswith('Reported pending bills: '):
            unavailable()
        scope = first.metric.removeprefix('Reported pending bills: ')
        if not scope:
            unavailable()
        subject = first.entity if scope.lower() == 'county' else f'{first.entity} ({scope})'
        paragraphs.append(f'{subject}: {amount(first)} in reported pending bills as at {day(observation.financial.period_end)}.')
        basis = (f'publisher-reported Grand Total stock as at {observation.financial.period_end.isoformat()}; '
                 'completeness is not assumed')
        if first.comparison_basis == basis or first.comparison_basis.startswith(basis + '; '):
            paragraphs.append('This is the report’s Grand Total. Completeness is not established by this figure.')
            notes = first.comparison_basis[len(basis):].removeprefix('; ').split('; ')
            for note in filter(None, notes):
                paragraphs.append(PENDING_NOTES[note] if note in PENDING_NOTES else f'Reporting note: {note}' + ('' if note.endswith(('.', '!', '?')) else '.'))
        else:
            unavailable()
    elif domain == 'national_budget':
        measures = {}
        scopes = set()
        bases = {'Actual expenditure': 'actual expenditure, same sector and annual reporting period',
                 'Revised gross budget': 'revised gross budget, same sector and annual reporting period'}
        for fact in facts:
            label, separator, scope = fact.metric.partition(': ')
            if not separator or not scope or label not in bases or label in measures:
                unavailable()
            measures[label] = fact
            scopes.add(scope)
            if fact.comparison_basis != bases[label]:
                unavailable()
        if len(scopes) != 1:
            unavailable()
        scope = next(iter(scopes))
        actual, budget = measures.get('Actual expenditure'), measures.get('Revised gross budget')
        if actual:
            paragraphs.append(f'{first.entity}: {amount(actual)} in actual expenditure for {scope} in {first.period}.')
            if budget:
                paragraphs.append(f'The revised gross budget for the same sector and reporting year was {amount(budget)}.')
        elif budget:
            paragraphs.append(f'{first.entity}: a revised gross budget of {amount(budget)} for {scope} in {first.period}.')
        else:
            unavailable()
    elif domain == 'revenue_by_source':
        prefix = 'Revenue collected: '
        if len(facts) != 1 or not first.metric.startswith(prefix) or not first.metric[len(prefix):]:
            unavailable()
        paragraphs.append(f'{first.entity}, {first.period}: {amount(first)} reported for {first.metric[len(prefix):]}.')
        if first.comparison_basis != 'published collections on the same revenue-head basis and annual reporting period':
            unavailable()
    else:
        unavailable()
    paragraphs.append(f'Source: {first.publisher}, {first.period}.')
    paragraphs.append('Explore the figures and original source on AuditGava.')
    if observation.correction_pending or observation.category == 'correction':
        paragraphs.insert(0, 'Correction awaiting human review.')
    return '\n\n'.join(paragraphs)

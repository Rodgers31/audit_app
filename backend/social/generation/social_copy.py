"""Plain, attributed copy for every existing fact category and report family.

This words supplied evidence. It does not extract arbitrary documents, invent a
summary of findings, infer wrongdoing, convert currencies or authorize delivery.
"""
from .contracts import CataloguedNativeReportEvidence, SourceObservation
from .copy_common import compact_value
from .financial_copy import day
from ..service import SocialError

FACT_VERSION = 'factual-v2'
REPORT_VERSION = 'report-availability-v3'
CATALOGUE_VERSION = 'catalogue-availability-v3'
VERSIONS = {FACT_VERSION, REPORT_VERSION, CATALOGUE_VERSION, 'report-availability-v2', 'catalogue-availability-v2'}


def quantity(fact):
    value, approximate = compact_value(fact)
    if fact.unit == 'KES':
        display = 'KSh ' + value
    elif fact.unit in ('%', 'percent') and fact.scale == 'units':
        display = value + '%'
    else:
        display = value + ' ' + fact.unit
    return ('about ' if approximate else '') + display


def sentence(value):
    return value if value.endswith(('.', '!', '?')) else value + '.'


def render_social(observation, *, version):
    observation = SourceObservation.model_validate(observation.model_dump(mode='python'))
    supported = (set() if observation.financial is not None
                 else {CATALOGUE_VERSION, 'catalogue-availability-v2'} if isinstance(observation.report, CataloguedNativeReportEvidence)
                 else {REPORT_VERSION, 'report-availability-v2'} if observation.report else {FACT_VERSION})
    if type(version) is not str or version not in supported:
        raise SocialError('UNRESOLVED_TEMPLATE', 'Choose a supported source copy version before review.', 422)
    paragraphs = []
    if observation.correction_pending or observation.category == 'correction':
        paragraphs.append('Correction awaiting human review.')
    if observation.report:
        report = observation.report
        label = {'national_budget': 'national budget', 'revenue_by_source': 'revenue',
                 'audits': 'audit', 'pending_bills': 'pending-bills'}.get(
                     getattr(report, 'native_domain', None), 'budget implementation')
        if isinstance(report, CataloguedNativeReportEvidence):
            paragraphs.append(f'{report.entity}: a {label} report for {report.period} is listed in {report.publisher}’s catalogue.')
            paragraphs.append(f'Catalogue entry dated {day(report.catalogued_on)}. The report’s publication date is not stated. Human review is required.')
        else:
            paragraphs.append(f'{report.entity}: explore the {label} report for {report.period}.')
            paragraphs.append(f'Published by {report.publisher} on {day(report.published_on)}.')
        if version in (REPORT_VERSION, CATALOGUE_VERSION):
            paragraphs.append('Read the original report entry on the publisher’s website.' if isinstance(report, CataloguedNativeReportEvidence)
                              else 'Read the original report on the publisher’s website.')
        else:
            paragraphs.append('Read the report and follow its source on AuditGava.')
    else:
        lead = observation.title
        if observation.category == 'dataset_availability':
            lead += ' is available on AuditGava'
        elif observation.category == 'audit_finding':
            lead = 'Audit finding: ' + lead
        paragraphs.append(sentence(lead))
        types = {'actual': 'Reported figure', 'modelled': 'Modelled estimate', 'projected': 'Projection'}
        for fact in sorted(observation.facts, key=lambda f: f.fact_id):
            paragraphs.append(f'{fact.entity}, {fact.period}\n'
                f'{types[fact.classification]} — {fact.metric}: {quantity(fact)}.\n'
                f'Reporting basis: {sentence(fact.comparison_basis)}\n'
                f'Source: {sentence(fact.publisher)}')
        paragraphs.append('Explore the figures and original sources on AuditGava.')
    return '\n\n'.join(paragraphs)

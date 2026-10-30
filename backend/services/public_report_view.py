"""Public, source-only report views. No social/editorial records are queried.

The URL binds meaning rather than an ingestion attempt. Unchanged reacquisition
can resolve the same view; a changed source/figure never becomes a new default.
"""
from decimal import Decimal, localcontext
from importlib import import_module
import re
from urllib.parse import urlencode

from sqlalchemy import select

PREFIX = 'backend.' if __package__.startswith('backend.') else ''
DOMAINS = {'national_budget', 'revenue_by_source', 'audits', 'pending_bills', 'counties_budget'}
LABELS = {'national_budget': 'National budget', 'revenue_by_source': 'Revenue',
          'audits': 'Audit', 'pending_bills': 'Pending bills', 'counties_budget': 'County budget'}


def _contracts():
    return import_module(PREFIX + 'social.generation.contracts')


def view_snapshot(observation):
    """Only public source meaning enters the stable, non-secret selector."""
    source = _contracts().SourceObservation.model_validate(observation.model_dump(mode='python'))
    if source.report:
        keys = {'entity_id', 'entity', 'period', 'period_start', 'period_end', 'source_document_id',
                'document_url', 'document_checksum', 'publisher', 'published_on', 'catalogued_on', 'evidence_kind'}
        value = source.report.model_dump(mode='json', include=keys)
    else:
        keys = {'entity', 'metric', 'period', 'comparison_basis', 'value', 'unit', 'scale', 'classification',
                'source_document_id', 'document_url', 'document_checksum', 'publisher', 'published_on'}
        value = []
        for fact in source.facts:
            item = fact.model_dump(mode='json', include=keys)
            with localcontext() as context:
                context.prec = 80
                number = Decimal(item['value'])
                item['value'] = '0' if number == 0 else format(number.normalize(), 'f')
            value.append(item)
        value.sort(key=lambda item: (item['entity'], item['metric'], item['period']))
    canonical_hash = import_module(PREFIX + 'social.contracts').canonical_hash
    return canonical_hash({'public_report_view': 1, 'domain': getattr(source.report or source.financial, 'native_domain', 'counties_budget'), 'kind': 'report' if source.report else 'financial', 'source': value})


def report_view_url(observation):
    source = _contracts().SourceObservation.model_validate(observation.model_dump(mode='python'))
    if source.report:
        domain = getattr(source.report, 'native_domain', 'counties_budget')
        document_id = source.report.source_document_id
        params = {'view': 'report', 'entity': source.report.entity_id}
        if domain == 'counties_budget':
            params['record'] = source.report.source_record_id
    elif source.financial:
        domain = source.financial.native_domain
        document_id = source.facts[0].source_document_id
        params = {'view': 'financial', 'record': source.financial.record_id}
    else:
        match = re.fullmatch(r'budget_lines:([1-9][0-9]{0,9}):actual_spent', source.source_key)
        if source.source_type != 'cob' or not match or len(source.facts) != 1:
            raise ValueError('A supported qualified report view is required')
        domain, document_id = 'counties_budget', source.facts[0].source_document_id
        params = {'view': 'financial', 'record': int(match[1])}
    params['snapshot'] = view_snapshot(source)
    return f'https://www.auditgava.com/reports/{domain}/{document_id}?' + urlencode(params)


class ReportViewUnavailable(Exception):
    pass


def public_report_view(db, *, domain, document_id, view, snapshot, entity=None, record=None):
    """Called in a fresh repeatable-read/read-only transaction, without writes."""
    if (type(domain) is not str or domain not in DOMAINS or type(document_id) is not int
            or not 0 < document_id <= 2147483647 or view not in ('report', 'financial')
            or type(snapshot) is not str or re.fullmatch('[a-f0-9]{64}', snapshot) is None
            or any(value is not None and (type(value) is not int or not 0 < value <= 2147483647) for value in (entity, record))
            or (view == 'financial' and (record is None or entity is not None))
            or (view == 'report' and (entity is None or (domain == 'counties_budget') != (record is not None)))):
        raise ReportViewUnavailable()
    models = import_module(PREFIX + 'models')
    readers = import_module(PREFIX + 'seeding.source_observations')
    source_doc = db.get(models.SourceDocument, document_id, populate_existing=True)
    if source_doc is None:
        raise ReportViewUnavailable()
    if domain == 'counties_budget':
        row = db.get(models.BudgetLine, record, populate_existing=True)
        if row is None or row.source_document_id != document_id or (view == 'report' and row.entity_id != entity):
            raise ReportViewUnavailable()
        entries = row.provenance if type(row.provenance) is list else []
        jobs = sorted({item['ingestion_job_id'] for item in entries if type(item) is dict
            and type(item.get('ingestion_job_id')) is int and item['ingestion_job_id'] > 0
            and item.get('data_quality') == 'official'}, reverse=True)
        if not jobs:
            raise ReportViewUnavailable()
        # Exact stable row; reacquisition may advance its job but not its scope.
        observation = _contracts().SourceObservation.model_validate(readers.current_county_evidence(
            db, record_id=row.id, ingestion_id=jobs[0], report=view == 'report'))
    else:
        authority = import_module(PREFIX + 'seeding.native_report_authority')
        meta = source_doc.meta if type(source_doc.meta) is dict else {}
        bindings = meta.get(authority.KEY)
        binding = bindings.get(domain) if type(bindings) is dict else None
        if type(binding) is not dict:
            raise ReportViewUnavailable()
        job, report_record = binding.get('ingestion_id'), binding.get('extraction_id')
        if type(job) is not int or type(report_record) is not int:
            raise ReportViewUnavailable()
        if view == 'financial':
            financial = import_module(PREFIX + 'seeding.native_financial_observations')
            if domain not in financial.MODELS:
                raise ReportViewUnavailable()
            raw = financial.current_native_financial(db, record, job, domain=domain)
        else:
            reports = import_module(PREFIX + 'seeding.native_report_observations')
            raw = reports.current_native_report(db, report_record, job, domain=domain)
        observation = _contracts().SourceObservation.model_validate(raw)
        if observation.report and observation.report.entity_id != entity:
            raise ReportViewUnavailable()
    items = (observation.report,) if observation.report else observation.facts
    if (any(item.source_document_id != document_id for item in items)
            or not observation.committed or observation.fixture or observation.quarantined or not observation.publishable
            or view_snapshot(observation) != snapshot):
        raise ReportViewUnavailable()
    first = items[0]
    scope = observation.report or observation.financial
    quantity = import_module(PREFIX + 'social.generation.social_copy').quantity
    figures = [dict(entity=f.entity, metric=f.metric, period=f.period, value=f.value,
        display_value=quantity(f), unit=f.unit, scale=f.scale, classification=f.classification,
        comparison_basis=f.comparison_basis, locator=f.locator) for f in observation.facts]
    sources = [dict(url=item.document_url, publisher=item.publisher, locator=item.locator) for item in items]
    return dict(schema_version=1, domain=domain, view=view, snapshot=snapshot,
        title=LABELS[domain] + (' report' if observation.report else ' figures'), entity=first.entity,
        period=first.period, period_start=getattr(scope, 'period_start', None), period_end=getattr(scope, 'period_end', None),
        publisher=first.publisher, published_on=first.published_on,
        catalogued_on=getattr(observation.report, 'catalogued_on', None),
        availability='catalogued' if getattr(observation.report, 'evidence_kind', None) == 'publisher_catalogue' else 'published',
        figures=figures, sources=sources)

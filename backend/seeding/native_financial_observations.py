"""Current committed financial cells, separate from report availability.

No acquisition or social mutation. Native publication authority and existing
measure-specific qualification must both agree with the exact current job.
"""
from decimal import Decimal
from types import SimpleNamespace
import re

from sqlalchemy import select, text

if __package__.startswith('backend.'):
    from backend.models import BudgetLine, Entity, EntityType, FiscalPeriod, Loan, DebtCategory, RevenueBySource, Extraction
    from backend.services.figure_qualification import qualify_rows
else:
    from models import BudgetLine, Entity, EntityType, FiscalPeriod, Loan, DebtCategory, RevenueBySource, Extraction
    from services.figure_qualification import qualify_rows
from .native_report_authority import KEY, DOMAINS, digest, lock_native_domain
from .native_report_observations import _session, _job, current_native_report
from .source_observations import SourceObservationUnavailable, _positive_id, _read_limits, _aware

MODELS = {'national_budget': BudgetLine, 'revenue_by_source': RevenueBySource, 'pending_bills': Loan}


def _lineage(row, domain, ingestion_id):
    if domain == 'revenue_by_source':
        entries = [row.meta]
    else:
        entries = row.provenance if type(row.provenance) is list else [row.provenance]
    exact = [e for e in entries if type(e) is dict and type(e.get('ingestion_job_id')) is int
             and e['ingestion_job_id'] == ingestion_id]
    if len(exact) != 1:
        raise SourceObservationUnavailable('Exact record ingestion lineage unavailable')
    return exact[0]


def read_native_financial_record_ids(factory, *, ingestion_id, domain):
    _positive_id(ingestion_id)
    if domain not in MODELS:
        raise SourceObservationUnavailable('Verified measure-specific PDF evidence required')
    model = MODELS[domain]
    with _session(factory) as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        _read_limits(db)
        _job(db, ingestion_id, domain)
        if domain == 'revenue_by_source':
            condition = model.meta.contains({'ingestion_job_id': ingestion_id})
        elif domain == 'pending_bills':
            condition = model.provenance.contains({'ingestion_job_id': ingestion_id})
        else:
            condition = model.provenance.contains([{'ingestion_job_id': ingestion_id}])
        ids = tuple(db.scalars(select(model.id).where(condition).order_by(model.id).limit(1001)))
        if len(ids) > 1000:
            raise SourceObservationUnavailable('Bounded exact ingestion lineage required')
        return ids


def current_native_financial(db, record_id, ingestion_id, *, domain, lock=False):
    _positive_id(record_id); _positive_id(ingestion_id)
    if domain not in MODELS:
        raise SourceObservationUnavailable('Verified measure-specific PDF evidence required')
    if lock:
        if db.scalar(text('SHOW transaction_isolation')) != 'read committed':
            raise SourceObservationUnavailable('Current report authority unavailable')
        lock_native_domain(db, domain)
    job, started, finished = _job(db, ingestion_id, domain)
    model = MODELS[domain]
    stmt = select(model).where(model.id == record_id).execution_options(populate_existing=True)
    row = db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise SourceObservationUnavailable('Exact record ingestion lineage unavailable')
    if row.quarantine_reason or row.publishable is not True:
        raise SourceObservationUnavailable('Publishable actual CoB record required')
    entry = _lineage(row, domain, ingestion_id)
    if __package__.startswith('backend.'):
        from backend.models import SourceDocument
    else:
        from models import SourceDocument
    source = db.get(SourceDocument, row.source_document_id, populate_existing=True)
    bindings = source.meta.get(KEY) if source and type(source.meta) is dict else None
    binding = bindings.get(domain) if type(bindings) is dict else None
    if type(binding) is not dict:
        raise SourceObservationUnavailable('Current report authority unavailable')
    report_observation = current_native_report(db, binding.get('extraction_id'), ingestion_id, domain=domain, lock=lock)
    report = report_observation['report']
    if report.get('published_on') is None or report.get('evidence_kind') == 'publisher_catalogue':
        raise SourceObservationUnavailable('Publisher publication date unavailable')
    period = report['period'].replace(' ', '')
    if domain == 'national_budget':
        entity, fiscal = db.get(Entity,row.entity_id,populate_existing=True), db.get(FiscalPeriod,row.period_id,populate_existing=True)
        if (entity is None or entity.type != EntityType.NATIONAL or entity.country_id != report['entity_id']
                or fiscal is None or fiscal.label.replace(' ','') != period
                or fiscal.start_date.date().isoformat() != report['period_start']
                or fiscal.end_date.date().isoformat() != report['period_end']
                or row.currency != 'KES' or row.publishable is not True or row.quarantine_reason
                or entry.get('data_quality') != 'official' or entry.get('measure') != 'expenditure'):
            raise SourceObservationUnavailable('Exact report period and publication locator required')
        table, measures = 'budget_lines', ('allocated_amount','actual_spent')
        identity = dict(entity=entity.canonical_name, category=row.category, subcategory=row.subcategory,
                        line_type=row.line_type)
        metric = f'{row.category}' + (f' / {row.subcategory}' if row.subcategory else '')
        labels = {'allocated_amount': 'Revised gross budget', 'actual_spent': 'Actual expenditure'}
        comparison = {'allocated_amount': 'revised gross budget, same sector and annual reporting period',
                      'actual_spent': 'actual expenditure, same sector and annual reporting period'}
        unit, scale, entity_name = 'KES', 'units', entity.canonical_name
        view = SimpleNamespace(**{c.key:getattr(row,c.key) for c in row.__table__.columns})
        view.provenance = [entry]
    elif domain == 'revenue_by_source':
        if row.fiscal_year.replace(' ','') != period or entry.get('basis') != 'published' or entry.get('absent_reason'):
            raise SourceObservationUnavailable('Exact report period and publication locator required')
        table, measures = 'revenue_by_source', ('amount_billion_kes',)
        identity = dict(entity='Kenya', revenue_type=row.revenue_type, category=row.category)
        if __package__.startswith('backend.'):
            from backend.services.revenue_publication import revenue_source_row
        else:
            from services.revenue_publication import revenue_source_row
        metric = revenue_source_row(row)['measure']
        labels, comparison = {'amount_billion_kes':'Revenue collected'}, {'amount_billion_kes':'published collections on the same revenue-head basis and annual reporting period'}
        unit, scale, entity_name, view = 'KES', 'billions', 'Kenya', row
    else:
        entity = db.get(Entity,row.entity_id,populate_existing=True)
        if (row.debt_category != DebtCategory.PENDING_BILLS or row.currency != 'KES'
                or entity is None or entity.type != EntityType.COUNTY or entity.country_id != report['entity_id']
                or entry.get('as_at') != report['period_end']
                or str(entry.get('fiscal_year','')).replace(' ','') != period):
            raise SourceObservationUnavailable('Exact report period and publication locator required')
        table, measures = 'loans', ('outstanding',)
        identity = dict(entity=entity.canonical_name, lender=row.lender, category=entry.get('category'))
        metric = str(entry.get('category') or row.lender)
        warnings={'assembly_not_printed':'assembly figure not reported',
            'cob_marked_inconsistent':'publisher marks this row inconsistent',
            'chapter_table_differs':'chapter table differs from the Grand Total'}
        notes=entry.get('reader_notes',[])
        if (type(notes) is not list or len(notes)>3 or any(type(n) is not dict
                or type(n.get('code')) is not str or n['code'] not in warnings for n in notes)
                or len({n['code'] for n in notes})!=len(notes)):
            raise SourceObservationUnavailable('Exact report period and publication locator required')
        basis=f'publisher-reported Grand Total stock as at {entry["as_at"]}; completeness is not assumed'
        if notes:
            basis+='; '+'; '.join(warnings[code] for code in sorted(n['code'] for n in notes))
        labels, comparison = {'outstanding':'Reported pending bills'}, {'outstanding':basis}
        unit, scale, entity_name, view = 'KES','units',entity.canonical_name,row
    qualifications = qualify_rows(db, table, [view], refresh_identity_map=True)[row.id]
    key = f'{DOMAINS[domain][0]}:financial:{domain}:'+digest(identity)
    facts = []
    for measure in measures:
        amount = getattr(row,measure)
        if amount is None:
            continue  # Missing measures remain absent; another exact measure may qualify.
        q = qualifications[measure]
        if (q['status'] != 'verified' or q['document_bytes_checked'] is not True or q['value_checked'] is not True
                or q['identity']['basis'] != 'actual' or q['source_document_id'] != source.id
                or q['digest'] != report['document_checksum']):
            raise SourceObservationUnavailable('Verified measure-specific PDF evidence required')
        ext = db.get(Extraction,q['receipt_id'],populate_existing=True)
        receipt = ext.extracted_json.get('response_receipt') if ext and type(ext.extracted_json) is dict else None
        if type(receipt) is not dict or receipt.get('request_url') != source.url:
            raise SourceObservationUnavailable('Qualified evidence ingestion lineage unavailable')
        acquired, checked = _aware(receipt['acquired_at']), _aware(receipt['byte_check']['checked_at'])
        if 'retained_pdf_validation' in receipt:
            from .retained_report_receipts import validate_retained_pdf
            checked = validate_retained_pdf(db,source,receipt,job,started=started,finished=finished)
            if not acquired <= _aware(receipt['byte_check']['checked_at']) <= checked:
                raise SourceObservationUnavailable('Stored evidence chronology invalid')
        elif not started <= acquired <= checked <= finished:
            raise SourceObservationUnavailable('Stored evidence chronology invalid')
        number = Decimal(amount)
        value = format(number, 'f')
        if not number.is_finite() or number < 0 or not re.fullmatch(r'(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,8})?',value):
            raise SourceObservationUnavailable('Bounded exact monetary value required')
        facts.append(dict(fact_id=key+':'+measure, entity=entity_name,
            metric=f'{labels[measure]}: {metric}', period=report['period'], comparison_basis=comparison[measure],
            value=value, unit=unit, scale=scale, classification='actual', source_document_id=source.id,
            document_url=source.url, locator=str(q['locator']), document_checksum=q['digest'],
            publisher=source.publisher, published_on=report['published_on'], retrieved_at=acquired.isoformat(),
            verified_at=checked.isoformat(), canonical_url=report['canonical_url']))
    if not facts:
        raise SourceObservationUnavailable('Verified measure-specific PDF evidence required')
    value = dict(schema_version=1,source_type=DOMAINS[domain][0],source_key=key,
        evidence_version=ingestion_id,ingestion_id=str(ingestion_id), category='budget_update' if domain!='pending_bills' else 'debt_update',
        title=f'{entity_name} {domain.replace("_", " ")} data',committed=True,fixture=False,quarantined=False,
        publishable=True,correction_pending=False,facts=facts,
        financial=dict(native_domain=domain,record_id=row.id,report_record_id=report['source_record_id'],
                       authority_fingerprint=report['authority_fingerprint'],
                       **{key:report[key] for key in ('period_start','period_end','published_on')}))
    from importlib import import_module
    contracts = import_module('backend.social.generation.contracts' if __package__.startswith('backend.') else 'social.generation.contracts')
    return contracts.SourceObservation.model_validate(value).model_dump(mode='json')


def read_native_financial_observation(factory, *, record_id, ingestion_id, domain):
    with _session(factory) as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        _read_limits(db)
        return current_native_financial(db,record_id,ingestion_id,domain=domain)

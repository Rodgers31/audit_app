"""Prospective numeric eligibility for native writer rows; no publication date.

This verdict never grants announcement authority. Committed readers separately
require current publisher evidence and complete successful live-job linkage.
"""
from types import SimpleNamespace
import os
from sqlalchemy import select
if __package__.startswith('backend.'):
    from backend.services.figure_qualification import qualify_rows
    from backend.models import SourceDocument, DocumentStatus
else:
    from services.figure_qualification import qualify_rows
    from models import SourceDocument, DocumentStatus

TABLES={'national_budget':('budget_lines',('actual_spent','allocated_amount')),
        'revenue_by_source':('revenue_by_source',('amount_billion_kes',)),
        'pending_bills':('loans',('outstanding',))}
REASON='native_financial_cells_unverified'


def qualify_native_financial_rows(session, rows, *, domain, context):
    # Prospective rollout must not alter existing numeric publication verdicts
    # while the new native financial lane remains explicitly paused.
    if os.environ.get('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED','false')!='true':
        return
    if context is None or context.dry_run is not False or type(context.job_id) is not int or context.job_id<=0:
        return
    table, measures=TABLES[domain]
    rows=list({id(row):row for row in rows}.values())
    if not rows:
        return
    if len(rows)>1000:
        raise ValueError('Bounded native financial cohort required')
    from .native_financial_observations import _lineage
    from .native_report_authority import KEY, DOMAINS, official_url
    # A shared ingestion domain can also write other publishers and scopes.
    # Only rows bound by this native producer in this exact job are prospective
    # candidates; unrelated numerical-publication decisions remain untouched.
    sources = {sid: (status, publisher, url, country, binding)
        for sid, status, publisher, url, country, binding in session.execute(
            select(SourceDocument.id, SourceDocument.status, SourceDocument.publisher,
                SourceDocument.url, SourceDocument.country_id, SourceDocument.meta[KEY][domain])
            .where(SourceDocument.id.in_({row.source_document_id for row in rows}))).all()}
    views=[]
    native_rows=[]
    for row in rows:
        source_state = sources.get(row.source_document_id)
        if source_state is None:
            continue
        status, publisher, url, country, binding = source_state
        if (publisher != DOMAINS[domain][2] or not official_url(url, domain)
                or type(binding) is not dict
                or type(binding.get('ingestion_id')) is not int or binding['ingestion_id'] != context.job_id
                or type(binding.get('country_id')) is not int or binding['country_id'] != country):
            continue
        entry=_lineage(row,domain,context.job_id)
        if domain == 'pending_bills' and entry.get('category') != 'county':
            continue
        view=SimpleNamespace(**{c.key:getattr(row,c.key) for c in row.__mapper__.column_attrs})
        view.__tablename__=row.__tablename__
        if domain=='national_budget':view.provenance=[entry]
        views.append(view)
        native_rows.append(row)
    if not native_rows:
        return
    qualified=qualify_rows(session,table,views)
    for row in native_rows:
        if row.quarantine_reason not in (None,REASON):
            continue  # Explicit operator/source quarantine cannot be cleared here.
        cells=[qualified[row.id][m] for m in measures if getattr(row,m) is not None]
        passed=sources[row.source_document_id][0]==DocumentStatus.AVAILABLE and bool(cells) and all(q['status']=='verified' and q['value_checked'] is True
            and q['document_bytes_checked'] is True for q in cells)
        row.publishable=passed
        row.quarantine_reason=None if passed else REASON

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
    views=[]
    for row in rows:
        entry=_lineage(row,domain,context.job_id)
        view=SimpleNamespace(**{c.key:getattr(row,c.key) for c in row.__mapper__.column_attrs})
        view.__tablename__=row.__tablename__
        if domain=='national_budget':view.provenance=[entry]
        views.append(view)
    qualified=qualify_rows(session,table,views)
    sources=dict(session.execute(select(SourceDocument.id,SourceDocument.status).where(
        SourceDocument.id.in_({row.source_document_id for row in rows}))).all())
    for row in rows:
        if row.quarantine_reason not in (None,REASON):
            continue  # Explicit operator/source quarantine cannot be cleared here.
        cells=[qualified[row.id][m] for m in measures if getattr(row,m) is not None]
        passed=sources.get(row.source_document_id)==DocumentStatus.AVAILABLE and bool(cells) and all(q['status']=='verified' and q['value_checked'] is True
            and q['document_bytes_checked'] is True for q in cells)
        row.publishable=passed
        row.quarantine_reason=None if passed else REASON

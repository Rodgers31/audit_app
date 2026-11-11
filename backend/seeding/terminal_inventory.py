"""Typed terminal inventories; ownership receipts are an explicit caller scope."""


DISCOVERY_ONLY = {
    'mode': 'discovery_only',
    'extraction': 'not_requested',
    'publication': 'not_requested',
}


def valid_terminal_inventory(job, *, completed, receipt_kind='source'):
    """Validate durable rows independently of Pydantic and handler return values.

    The two ownership-only callers must first prove their own nonce-bearing
    scope. Row metadata alone never enables either zero-inventory exception.
    """
    if (type(completed) is not bool or type(receipt_kind) is not str
            or receipt_kind not in ('source', 'reference', 'legacy_ownership')):
        return False
    counts = (job.items_processed, job.items_created, job.items_updated)
    if (type(job.domain) is not str or not job.domain or job.domain != job.domain.strip()
            or type(job.dry_run) is not bool
            or any(type(value) is not int or not 0 <= value <= 2147483647 for value in counts)
            or counts[1] + counts[2] > counts[0]
            or type(job.errors) is not list
            or any(type(error) is not str or not error.strip() for error in job.errors)):
        return False
    if not completed:
        return True
    if job.errors:
        return False
    if counts[0] > 0:
        return True
    if type(job.meta) is not dict:
        return False
    if receipt_kind == 'reference':
        return job.domain == 'bootstrap_reference_data' and job.dry_run is False
    if receipt_kind == 'legacy_ownership':
        return (job.dry_run is False and job.meta.get('writer') == 'legacy_etl'
                and job.meta.get('counts_scope') == 'ownership_only')
    return (job.domain == 'audits' and job.dry_run is True
            and type(job.meta.get('dry_run_plan')) is dict
            and job.meta['dry_run_plan'] == DISCOVERY_ONLY)

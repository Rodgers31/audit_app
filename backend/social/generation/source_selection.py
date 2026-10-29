"""Bounded, read-only navigation to the existing committed source readers.

These IDs are candidates, not a qualification receipt. Preview and detection
still re-read every record under their existing authority checks.
"""
from importlib import import_module

from ..service import SocialError


def source_records(factory, *, domain, ingestion_id, reports, page):
    if (type(domain) is not str or type(ingestion_id) is not int
            or not 1 <= ingestion_id <= 2147483647 or type(reports) is not bool
            or type(page) is not int or not 1 <= page <= 40):
        raise SocialError('INVALID_SOURCE_SELECTION', 'Choose a completed source job and a valid page.', 422)
    prefix = 'backend.' if __package__.startswith('backend.') else ''
    registry = import_module(prefix + 'seeding.generation_capabilities')
    selected = registry.capability(domain)
    if not (selected.reports if reports else selected.financial):
        raise SocialError('SOURCE_NOT_ELIGIBLE', 'This source has no reviewed adapter for the selected content.', 422)
    adapter = import_module(prefix + 'seeding.source_observations')
    try:
        if reports and domain != 'counties_budget':
            ids = adapter.read_native_report_record_ids(factory, ingestion_id=ingestion_id, domain=domain)
        elif domain == 'counties_budget':
            ids = adapter.read_county_budget_record_ids(factory, ingestion_id=ingestion_id)
        else:
            ids = adapter.read_native_financial_record_ids(factory, ingestion_id=ingestion_id, domain=domain)
    except adapter.SourceObservationUnavailable as error:
        if error.operational:
            raise SocialError('SOURCE_SELECTION_UNAVAILABLE', 'The committed source reader is unavailable. Retry the read before continuing.', 503) from None
        raise SocialError('SOURCE_NOT_ELIGIBLE', 'Current committed lineage is unavailable for this job. Inspect its outcome or choose a newer completed job.', 422) from None
    if (type(ids) is not tuple or len(ids) > 1000
            or any(type(v) is not int or not 1 <= v <= 2147483647 for v in ids)
            or len(set(ids)) != len(ids)):
        raise SocialError('SOURCE_SELECTION_UNAVAILABLE', 'The committed source list could not be verified.', 503)
    start = (page - 1) * 25
    return dict(domain=domain, ingestion_id=ingestion_id, reports=reports, page=page,
                page_size=25, total=len(ids), record_ids=list(ids[start:start + 25]),
                has_more=page * 25 < len(ids))

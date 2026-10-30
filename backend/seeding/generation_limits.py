"""Shared finite budgets for post-commit generation and its CLI envelope."""

DEFAULT_PHASE_SECONDS = 30
PENDING_BILLS_FINANCIAL_SECONDS = 120
SOURCE_AND_RECEIPT_SECONDS = 10


def generation_phase_seconds(domain, *, reports=False):
    if type(reports) is not bool:
        raise ValueError('Explicit generation phase required')
    return (PENDING_BILLS_FINANCIAL_SECONDS
            if domain == 'pending_bills' and not reports else DEFAULT_PHASE_SECONDS)


def generation_envelope_seconds(domain, *, include_reports):
    if type(include_reports) is not bool:
        raise ValueError('Explicit report phase selection required')
    return (generation_phase_seconds(domain)
            + (generation_phase_seconds(domain, reports=True) if include_reports else 0)
            + SOURCE_AND_RECEIPT_SECONDS)

"""Shared finite budgets for post-commit generation and its CLI envelope."""
import math

DEFAULT_PHASE_SECONDS = 30
# Reviewed 46-row changed cohort with installed authority/account ports:
# 2,880 driver calls at a conservative 150 ms account for 432 seconds.
# Retain finite room for connection/commit protocol, CPU and receipt writes.
PENDING_BILLS_FINANCIAL_SECONDS = 600
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


def bounded_generation_envelope_seconds(domain, *, include_reports, remaining_seconds=None):
    envelope = generation_envelope_seconds(domain, include_reports=include_reports)
    if remaining_seconds is None:
        return envelope
    try:
        valid = type(remaining_seconds) in (int, float) and math.isfinite(remaining_seconds)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError('Finite remaining run budget required')
    # Timeout telemetry runs after the alarm is cancelled. Reserve that existing
    # cleanup allowance inside the remaining whole-run limit too.
    return min(envelope, max(0, int(remaining_seconds - SOURCE_AND_RECEIPT_SECONDS)))

"""Bounded SQL aggregates of stored audit amounts, with explicit coverage.

Amounts on general findings can be balances discussed, not expenditure queried.
This module never infers an amount from legacy text or a classification.
"""
import math
from typing import Literal, Optional

from pydantic import BaseModel

from sqlalchemy import String, case, cast, func

from models import Audit
from services.publication_gate import publishable_audit_criterion


class AuditAmountCoverage(BaseModel):
    status: Literal["complete", "partial", "unavailable"]
    reason: Optional[str] = None
    total_findings: int
    findings_with_amount: int
    findings_without_amount: int
    findings_with_invalid_amount: int
    withheld_findings: int


def finite_audit_amount(column=Audit.amount):
    """Exclude PostgreSQL numeric NaN/infinities before SUM (NULL stays NULL)."""
    return case((~cast(column, String).in_(("NaN", "Infinity", "-Infinity")), column),
                else_=None)


def audit_amount_columns(criterion=None, *, scope_criterion=None):
    """Subtotal and coverage in one query, optionally per SQL group.

    Raw count distinguishes an empty scope from one with only withheld findings.
    Callers apply entity, period, and classification filters to the whole query.
    """
    if criterion is None:
        criterion = publishable_audit_criterion()
    amount = case((criterion, finite_audit_amount()))
    return (
        func.sum(amount),
        func.count(case((criterion, Audit.id))),
        func.count(amount),
        func.count(case((criterion, Audit.amount))),
        (func.count(Audit.id).filter(scope_criterion) if scope_criterion is not None
         else func.count(Audit.id)),
    )


def audit_amount_result(row=None, *, reason=None):
    """JSON-safe value and coverage; a finite zero remains a measured zero."""
    subtotal, published, finite, stored, raw = row or (None, 0, 0, 0, 0)
    invalid, missing = stored - finite, published - stored
    value = float(subtotal) if subtotal is not None else None
    if value is not None and not math.isfinite(value):
        value, reason = None, "non_finite_total"
    if reason is None:
        if not published:
            reason = "no_publishable_findings" if raw else "no_findings"
        elif not finite:
            reason = ("no_finite_amounts" if invalid and missing else
                      "invalid_stored_amount" if invalid else "no_amounts_recorded")
        elif invalid or missing:
            reason = "incomplete_amount_coverage"
    status = "unavailable" if value is None else "partial" if reason else "complete"
    return value, {
        "status": status,
        "reason": reason,
        "total_findings": published,
        "findings_with_amount": finite,
        "findings_without_amount": missing,
        "findings_with_invalid_amount": invalid,
        "withheld_findings": raw - published,
    }

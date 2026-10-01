"""Nullable financial fields at publishing boundaries; zero requires a value."""
from services.entity_financials import _amount


def monetary_fields(row, fields, *, scale=1, unit_valid=True):
    """Preserve measured zero and explain missing, malformed or unsupported units."""
    values, reasons = {}, {}
    for field in fields:
        raw = getattr(row, field, None)
        amount = _amount(raw) if unit_valid else None
        values[field] = amount / scale if amount is not None else None
        if amount is None:
            reasons[field] = (
                "unsupported_unit"
                if not unit_valid
                else "not_reported"
                if raw is None
                else "invalid_amount"
            )
    return {**values, "absent_reasons": reasons}


FISCAL_MONEY_FIELDS = (
    "appropriated_budget",
    "total_revenue",
    "tax_revenue",
    "non_tax_revenue",
    "total_borrowing",
    "debt_service_cost",
    "development_spending",
    "recurrent_spending",
    "county_allocation",
)


def fiscal_history_entry(row):
    """Convert a raw-KES account independently; never fill gaps from another year."""
    money = monetary_fields(
        row, FISCAL_MONEY_FIELDS, scale=1e9, unit_valid=row.unit == "KES"
    )
    ratio = monetary_fields(row, ["borrowing_pct_of_budget"])
    meta = row.meta if isinstance(row.meta, dict) else {}
    return {
        "fiscal_year": row.fiscal_year,
        "unit": "billion_kes",
        **money,
        "borrowing_pct_of_budget": ratio["borrowing_pct_of_budget"],
        "absent_reasons": {**money["absent_reasons"], **ratio["absent_reasons"]},
        "budget_basis": meta.get("budget_basis"),
        "budget_basis_source": meta.get("budget_basis_source"),
        "metadata_absent_reason": "invalid_metadata"
        if row.meta is not None and not isinstance(row.meta, dict)
        else None,
        "source_document_id": row.source_document_id,
        "page_ref": row.page_ref,
    }


def _debt_reporting_date(loan):
    from datetime import date

    provenance = getattr(loan, "provenance", None)
    entries = provenance if isinstance(provenance, list) else [provenance]
    dates = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for key in ("as_at", "as_of"):
            if key not in entry:
                continue
            try:
                dates.add(date.fromisoformat(entry[key]).isoformat())
            except (TypeError, ValueError):
                return None, "invalid_reporting_date"
    if len(dates) > 1:
        return None, "conflicting_reporting_dates"
    return next(iter(dates), None), None


def _loan_unreported(loan):
    from services.entity_financials import budget_evidence_is_unreported

    basis = getattr(loan, "basis", None)
    basis_value = getattr(basis, "value", basis)
    return basis_value not in (None, "actual") or budget_evidence_is_unreported(
        getattr(loan, "quarantine_reason", None),
        basis,
        getattr(loan, "provenance", None),
        getattr(getattr(loan, "source_document", None), "meta", None),
    )


def county_debt_instrument_fields(loan):
    fields = monetary_fields(
        loan,
        ("principal", "outstanding"),
        unit_valid=getattr(loan, "currency", None) == "KES",
    )
    rate = monetary_fields(loan, ("interest_rate",))
    fields["interest_rate"] = rate["interest_rate"]
    fields["absent_reasons"].update(rate["absent_reasons"])
    if _loan_unreported(loan):
        fields.update(
            principal=None,
            outstanding=None,
            interest_rate=None,
            absent_reasons={
                "principal": "unreported_accounting_basis",
                "outstanding": "unreported_accounting_basis",
                "interest_rate": "unreported_accounting_basis",
            },
        )
    return fields


def _instrument_identity(loan):
    provenance = getattr(loan, "provenance", None)
    entries = provenance if isinstance(provenance, list) else [provenance]
    identifiers = set()
    for entry in entries:
        if isinstance(entry, dict):
            for key in ("source_instrument_id", "instrument_id", "loan_reference"):
                raw = entry.get(key)
                if isinstance(raw, str) and raw.strip():
                    identifiers.add(raw.strip())
    if len(identifiers) > 1:
        return None, "conflicting_instrument_identity"
    if identifiers:
        return ("source_identifier", next(iter(identifiers))), None
    # Lender/date can establish ambiguity, never proven duplicate borrowing.
    return (
        "lender_date",
        " ".join(str(loan.lender).casefold().split()),
        getattr(loan, "issue_date", None),
    ), None


def county_debt_summary(loans):
    """Selected eligible instruments' outstanding balances, excluding arrears.

    This is a sum of the selected instrument rows, not proof of complete county
    liability coverage. One balance may stand alone without a reporting date;
    addition requires a common explicit reporting date, entity and actual basis.
    Original principal never substitutes for outstanding, even at zero.
    """
    from models import DebtCategory
    from services.publication_gate import (
        county_debt_instrument_failure,
        loan_is_modelled_fixture,
    )

    rows = [
        loan
        for loan in loans or []
        if getattr(loan, "debt_category", None) != DebtCategory.PENDING_BILLS
        and not loan_is_modelled_fixture(loan)
        and not county_debt_instrument_failure(loan)
    ]
    reason = "no_eligible_instruments" if not rows else None
    amounts, dates, bases, entities = [], set(), set(), set()
    for loan in rows:
        amount = _amount(getattr(loan, "outstanding", None))
        amounts.append(amount)
        day, date_reason = _debt_reporting_date(loan)
        dates.add(day)
        basis = getattr(loan, "basis", None)
        basis_value = getattr(basis, "value", basis)
        bases.add(
            basis_value
            if isinstance(basis_value, (str, type(None)))
            else "invalid_basis"
        )
        entities.add(getattr(loan, "entity_id", None))
        if reason is None:
            if getattr(loan, "source_document", None) is None:
                reason = "no_source_document"
            elif getattr(loan, "currency", None) != "KES":
                reason = "unsupported_currency"
            elif amount is None:
                reason = "outstanding_not_reported_or_invalid"
            elif _loan_unreported(loan):
                reason = "unreported_accounting_basis"
            elif date_reason:
                reason = date_reason
    if reason is None and len(rows) > 1:
        if len(entities) != 1 or None in entities:
            reason = "incompatible_entities"
        elif len(dates) != 1 or None in dates:
            reason = "incompatible_or_missing_reporting_dates"
        elif bases != {"actual"}:
            reason = "incompatible_or_missing_accounting_basis"
        else:
            identities = [_instrument_identity(loan) for loan in rows]
            identity_reasons = [failure for _, failure in identities if failure]
            if identity_reasons:
                reason = identity_reasons[0]
            elif len({identity for identity, _ in identities}) != len(rows):
                reason = (
                    "ambiguous_instrument_identity"
                    if any(identity[0] == "lender_date" for identity, _ in identities)
                    else "duplicate_instrument_observations"
                )
    total = sum(amounts) if reason is None else None
    total = _amount(total)
    if total is None and reason is None:
        reason = "invalid_total"
    return {
        "total_debt": total,
        "total_debt_absent_reason": reason,
        "debt_currency": "KES"
        if rows and all(getattr(loan, "currency", None) == "KES" for loan in rows)
        else None,
        "debt_accounting_basis": "selected_instrument_outstanding",
        "debt_as_at": next(iter(dates)) if len(dates) == 1 else None,
        "debt_basis": "actual" if bases == {"actual"} else None,
        "debt_coverage": "selected_eligible_instruments_only",
    }


def county_debt_budget_ratio(debt, budget):
    """Stock at the budget period's exact closing day / that period's allocation.

    Issue dates are never stock dates. A missing as-of date cannot borrow the
    selected budget year. Zero debt is a ratio of zero only over a positive,
    compatible allocation; a zero/missing denominator is an absent ratio.
    """
    from datetime import date

    amount = _amount(debt.get("total_debt"))
    allocation = _amount(budget.get("total_allocation"))
    budget_reasons = budget.get("absent_reasons")
    allocation_reason = (
        budget_reasons.get("total_allocation")
        if isinstance(budget_reasons, dict)
        else None
    )
    reason = debt.get("total_debt_absent_reason") or allocation_reason
    if reason:
        pass  # Explicit rejection always outranks a contradictory numeric value.
    elif amount is None:
        reason = reason or "debt_not_reported_or_invalid"
    elif allocation is None:
        reason = "budget_not_reported_or_invalid"
    elif allocation == 0:
        reason = "zero_budget_denominator"
    elif debt.get("debt_basis") != "actual":
        reason = "incompatible_or_missing_accounting_basis"
    elif debt.get("debt_currency") != "KES" or budget.get("currency") != "KES":
        reason = "incompatible_or_missing_currency"
    else:
        period = budget.get("fiscal_period")
        try:
            if not isinstance(period, dict) or not period.get("start_date"):
                raise ValueError("No dated period")
            day = date.fromisoformat(debt.get("debt_as_at"))
            start = date.fromisoformat(period["start_date"][:10])
            end = date.fromisoformat(period["end_date"][:10])
            if start > end or day != end:
                raise ValueError("Incompatible stock date")
        except (TypeError, ValueError, KeyError):
            reason = "incompatible_or_missing_budget_period"
    value = amount / allocation * 100 if reason is None else None
    value = _amount(value)
    if value is None and reason is None:
        reason = "invalid_ratio"
    return {"debt_to_budget_ratio": value, "debt_to_budget_ratio_absent_reason": reason}

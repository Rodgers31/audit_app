"""What a register row may publish about the cost of its debt.

Every row in the national-debt register used to carry one number for this —
``Loan.interest_rate`` — and every consumer multiplied it by the outstanding
balance to get an "annual service cost". Measured on production 2026-09-26
(issue #235):

* 45 of 48 rows published ``0.00%`` and ``KES 0``. The live overlays carry no
  rate, and the writer created each row with ``interest_rate or Decimal("0")``
  — a figure nobody measured, printed as a measurement.
* The other rows' rates were the April-2025 fixture's (14.5% bonds, 16% bills),
  kept forever because the writer only overwrote a rate the live record had.
  CBK's own 91-day yield was 8.778% on the day this was measured.
* The homepage "Annual service" (KES 1,022Bn) was those three fixture rates
  times three balances.

So a row now carries a DECLARATION instead of a bare rate: for the rate and for
the annual cost separately, either a value with its basis and source, or an
explicit reason there is none. The fetcher writes it, the writer records it in
the row's provenance, and the API publishes only what it declares. A row with
no declaration — every row written before this existed — publishes neither
figure, because the column's value cannot say where it came from.

Two bases for the annual cost, and they are never summed together:

``published``
    A figure a publisher states. World Bank IDS reports interest actually paid
    to each external creditor in a calendar year (``DT.INT.*``).
``modelled``
    ``outstanding x rate``, where the rate is itself published (a CBK coupon or
    yield). Arithmetic, not a measurement — labelled as such wherever shown.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

#: Key under which the declaration rides on a payload loan row and in a
#: ``Loan.provenance`` entry.
TERMS_KEY = "interest_terms"

RATE_BASES = {
    # Face-value-weighted mean of the coupons CBK lists for the individual
    # securities in its Treasury bond register.
    "coupon_weighted_average",
    # CBK's published yield for one Treasury-bill tenor at auction.
    "auction_yield",
}
COST_BASES = {"published", "modelled"}

_SOURCE_KEYS = ("publisher", "title", "url")


def _source_ok(source: Any) -> bool:
    return isinstance(source, dict) and all(
        isinstance(source.get(k), str) and source.get(k) for k in _SOURCE_KEYS
    )


def _positive_number(value: Any) -> bool:
    # bool is an int subclass; True is not a rate.
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value  # not NaN
        and value not in (float("inf"), float("-inf"))
        and value >= 0
    )


def validate_terms(terms: Any) -> List[str]:
    """Why ``terms`` cannot be published, or ``[]`` when it can.

    Each half (rate, cost) must be EXACTLY one of: a value with a known basis,
    a label and a source; or an absent reason. Both, or neither, is refused —
    a value with a reason attached is a contradiction, and neither is the
    silent state this module exists to remove.
    """
    if not isinstance(terms, dict):
        return ["terms is not an object"]
    problems: List[str] = []

    rate = terms.get("rate_pct")
    rate_reason = terms.get("rate_absent_reason")
    if rate is None:
        if not (isinstance(rate_reason, str) and rate_reason.strip()):
            problems.append("rate has neither a value nor an absent reason")
    else:
        if rate_reason:
            problems.append("rate has both a value and an absent reason")
        if not _positive_number(rate) or rate > 100:
            problems.append(f"rate_pct {rate!r} is not a percentage")
        if terms.get("rate_basis") not in RATE_BASES:
            problems.append(f"rate_basis {terms.get('rate_basis')!r} is not declared")
        if not (isinstance(terms.get("rate_label"), str) and terms["rate_label"]):
            problems.append("rate has no label")
        if not _source_ok(terms.get("rate_source")):
            problems.append("rate has no source")

    cost = terms.get("annual_cost_kes")
    cost_reason = terms.get("annual_cost_absent_reason")
    if cost is None:
        if not (isinstance(cost_reason, str) and cost_reason.strip()):
            problems.append("annual cost has neither a value nor an absent reason")
    else:
        if cost_reason:
            problems.append("annual cost has both a value and an absent reason")
        if not _positive_number(cost):
            problems.append(f"annual_cost_kes {cost!r} is not an amount")
        basis = terms.get("annual_cost_basis")
        if basis not in COST_BASES:
            problems.append(f"annual_cost_basis {basis!r} is not declared")
        if basis == "modelled" and rate is None:
            problems.append("a modelled annual cost needs a published rate")
        if not (isinstance(terms.get("annual_cost_label"), str) and terms["annual_cost_label"]):
            problems.append("annual cost has no label")
        if not _source_ok(terms.get("annual_cost_source")):
            problems.append("annual cost has no source")
    return problems


def absent_terms(rate_reason: str, cost_reason: Optional[str] = None) -> Dict[str, Any]:
    """A declaration that neither figure is published, and why."""
    return {
        "rate_pct": None,
        "rate_basis": None,
        "rate_label": None,
        "rate_source": None,
        "rate_absent_reason": rate_reason,
        "annual_cost_kes": None,
        "annual_cost_basis": None,
        "annual_cost_label": None,
        "annual_cost_source": None,
        "annual_cost_absent_reason": cost_reason or rate_reason,
    }


def published_rate_terms(
    *,
    rate_pct: float,
    basis: str,
    label: str,
    source: Dict[str, Any],
    outstanding_kes: float,
    cost_label: str,
) -> Dict[str, Any]:
    """A published rate, and the annual cost MODELLED from it.

    The cost is ``outstanding x rate`` and says so: a coupon average or one
    tenor's yield applied to a whole stock is an estimate, however good the
    inputs.
    """
    return {
        "rate_pct": round(float(rate_pct), 4),
        "rate_basis": basis,
        "rate_label": label,
        "rate_source": source,
        "rate_absent_reason": None,
        "annual_cost_kes": round(float(outstanding_kes) * float(rate_pct) / 100, 2),
        "annual_cost_basis": "modelled",
        "annual_cost_label": cost_label,
        "annual_cost_source": source,
        "annual_cost_absent_reason": None,
    }


def published_cost_terms(
    *,
    cost_kes: float,
    label: str,
    source: Dict[str, Any],
    rate_reason: str,
) -> Dict[str, Any]:
    """A publisher's own figure for interest paid, with no rate to go with it."""
    return {
        "rate_pct": None,
        "rate_basis": None,
        "rate_label": None,
        "rate_source": None,
        "rate_absent_reason": rate_reason,
        "annual_cost_kes": round(float(cost_kes), 2),
        "annual_cost_basis": "published",
        "annual_cost_label": label,
        "annual_cost_source": source,
        "annual_cost_absent_reason": None,
    }


#: What the API says for a row that carries no declaration at all.
UNDECLARED_REASON = (
    "No publisher's rate or interest figure has been recorded for this row."
)


def terms_from_provenance(provenance: Any) -> Dict[str, Any]:
    """The declaration on a row's latest provenance entry, or an absent one.

    Fail-closed. A row whose newest entry carries no declaration, or one that
    does not validate, publishes neither figure — whatever ``interest_rate``
    the column holds. That column is exactly what carried the fixture's 2025
    rates and the manufactured zeros; it cannot say where its value came from.
    """
    entries = provenance if isinstance(provenance, list) else [provenance]
    latest = next(
        (e for e in reversed(entries) if isinstance(e, dict)),
        None,
    )
    terms = latest.get(TERMS_KEY) if latest else None
    if terms is None:
        return absent_terms(UNDECLARED_REASON)
    problems = validate_terms(terms)
    if problems:
        return absent_terms(
            "The recorded rate for this row failed validation and is withheld: "
            + "; ".join(problems)
        )
    return terms


__all__ = [
    "TERMS_KEY",
    "UNDECLARED_REASON",
    "absent_terms",
    "published_cost_terms",
    "published_rate_terms",
    "terms_from_provenance",
    "validate_terms",
]

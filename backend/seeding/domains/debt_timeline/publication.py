"""One debt-ratio boundary for writer, coverage and public consumers."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

from services.figure_qualification import qualify_rows, qualify_ratio
from services.fiscal_outturns import finite_number


def _stock_month(qualification, year):
    locator = qualification.get("locator")
    cell = locator.get("cell") if isinstance(locator, dict) else None
    match = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2]) / (?:total|external|domestic)", cell or "") if isinstance(cell, str) else None
    return f"{match[1]}-{match[2]}" if match and int(match[1]) == year else None


def debt_qualifications(db, rows, *, now=None):
    """Keep original amount qualifications; require a compatible observed pair."""
    now = now or datetime.now(timezone.utc)
    result = qualify_rows(db, "debt_timeline", rows)
    for row in rows:
        q = result[row.id]
        for field in ('external', 'domestic', 'total', 'gdp'):
            raw = getattr(row, field)
            if row.unit != 'KES' or finite_number(raw) is None:
                q[field].update(status='unavailable',
                    reason=('debt_requires_declared_raw_kes' if row.unit != 'KES' else
                            'value_not_reported' if raw is None else 'invalid_nonnegative_debt_amount'),
                    value_checked=False, document_bytes_checked=False)
        ratio = q["gdp_ratio"]
        reason = None
        if row.unit != "KES":
            reason = "debt_ratio_requires_declared_raw_kes"
        elif row.year >= now.year:
            reason = "annual_gdp_period_not_ended"
            q['gdp'].update(status='unavailable', reason=reason,
                            value_checked=False, document_bytes_checked=False)
        elif _stock_month(q["total"], row.year) is None:
            reason = "stock_as_of_month_unconfirmed"
        elif any(finite_number(getattr(row, field)) is None for field in ("total", "gdp")):
            reason = "invalid_ratio_operands"
        if reason:
            ratio.update(status="unavailable", reason=reason, value_checked=False, document_bytes_checked=False)
    return result


def _verified_ratio(numerator, denominator, n, d, *, measure="gdp_ratio"):
    """Compute at the stored precision, then independently qualify both operands."""
    if finite_number(n) is None or finite_number(d) is None or d <= 0:
        return None
    try:
        value = (Decimal(str(n)) / Decimal(str(d)) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, OverflowError):
        return None
    qualification = qualify_ratio(numerator, denominator, value, n, d, measure=measure)
    return value if qualification["status"] == "verified" else None


def persist_qualified_ratios(db, rows, *, now=None):
    """Never copy an upstream ratio or let a new denominator certify old stock."""
    qualifications = debt_qualifications(db, rows, now=now)
    for row in rows:
        q = qualifications[row.id]
        if q["gdp_ratio"]["reason"] in {
                "debt_ratio_requires_declared_raw_kes", "annual_gdp_period_not_ended", "stock_as_of_month_unconfirmed"}:
            row.gdp_ratio = None
        else:
            row.gdp_ratio = _verified_ratio(q["total"], q["gdp"], row.total, row.gdp)


def public_debt_rows(db, rows, *, now=None):
    """Serialize nullable ratios and disclose monthly stock versus annual GDP."""
    qualifications = debt_qualifications(db, rows, now=now)
    output = {}
    for row in rows:
        q = qualifications[row.id]
        ratio_ok = q["gdp_ratio"]["status"] == "verified"
        stock_month = _stock_month(q["total"], row.year)
        values = {field: finite_number(getattr(row, field)) for field in ("external", "domestic", "total", "gdp")}
        for field in values:
            if q[field]['status'] not in {'qualified', 'verified'}:
                values[field] = None
        absent = {field: q[field]['reason'] for field, value in values.items() if value is None}
        if not ratio_ok:
            absent['gdp_ratio'] = q['gdp_ratio']['reason']
        external_share = _verified_ratio(q["external"], q["total"], row.external, row.total, measure="external_debt_share")
        # Partitions must describe the same monthly stock, not merely the same
        # annual identity. An independently qualified different month is held.
        if (_stock_month(q["external"], row.year) != stock_month or stock_month is None
                or any(q['external'].get(key) != q['total'].get(key)
                       for key in ('digest', 'source_document_id', 'source_url'))
                or finite_number(row.external) is None or finite_number(row.total) is None
                or row.external > row.total):
            external_share = None
        output[row.id] = {
            "year": row.year, "unit": row.unit,
            **values,
            "gdp_ratio": finite_number(row.gdp_ratio) if ratio_ok else None,
            "qualifications": deepcopy(q),
            "absent_reasons": absent,
            "external_debt_share": float(external_share) if external_share is not None else None,
            "external_debt_share_absent_reason": None if external_share is not None else "compatible_qualified_stock_components_required",
            "period": {"stock_as_of_month": stock_month, "gdp_calendar_year": row.year,
                       "year_end_stock": stock_month == f"{row.year}-12",
                       "vintage_date": None, "publication_date": None},
        }
    return output

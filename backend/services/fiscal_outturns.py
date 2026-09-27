"""Serialize one published fiscal-framework column without mixing accounting bases."""
from math import isfinite
from urllib.parse import urlsplit


def finite_number(value, *, nonnegative=True):
    if value is None or isinstance(value, (bool, str)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) and (number >= 0 or not nonnegative) else None


def has_source_locator(source):
    """Require an openable document URL and a nonempty page locator."""
    if not isinstance(source, dict):
        return False
    url, page = source.get("url"), source.get("page")
    try:
        url_ok = isinstance(url, str) and urlsplit(url).scheme in {"http", "https"} and bool(urlsplit(url).netloc)
    except ValueError:
        url_ok = False
    page_ok = (isinstance(page, str) and bool(page.strip())) or (type(page) is int and page > 0)
    if isinstance(page, str):
        try:
            numeric_page = float(page)
        except ValueError:
            pass  # Descriptive locators such as "Annex 2, p.63" are valid.
        else:
            page_ok = isfinite(numeric_page) and numeric_page > 0
    return url_ok and page_ok


def fiscal_outturn(row):
    meta = row.meta if isinstance(row.meta, dict) else {}
    framework = meta.get("fiscal_framework")
    framework = framework if isinstance(framework, dict) else {}
    source = framework.get("source")
    source = source if isinstance(source, dict) else {}
    result = {
        "period": row.fiscal_year, "revenue": None, "expenditure": None,
        "balance": None, "financing": None, "source": source or None,
        "column": source.get("column") or "Vintage unconfirmed",
        "basis": "treasury_fiscal_framework",
        "measure": "Revenue includes A-i-A; expenditure and net lending includes county transfers and contingency; balance includes grants.",
        "absent_reason": "No complete, reconciled fiscal-framework column with a source is available.",
    }
    if framework.get("basis") != "treasury_fiscal_framework" or not has_source_locator(source):
        return result
    fields = {
        "revenue": "total_revenue_incl_aia_billion", "expenditure": "total_expenditure_billion",
        "deficit": "fiscal_deficit_incl_grants_billion", "financing": "total_financing_billion",
        "grants": "grants_billion", "cash_adjustment": "adjustment_to_cash_basis_billion",
        "statistical_discrepancy": "statistical_discrepancy_billion",
    }
    amounts = {key: finite_number(framework.get(field), nonnegative=key in {"revenue", "expenditure", "grants"}) for key, field in fields.items()}
    if any(value is None for value in amounts.values()):
        return result
    a = amounts
    # Four printed one-decimal amounts: at most 4 × 0.05B rounding error.
    if abs(a["revenue"] + a["grants"] - a["expenditure"] + a["deficit"]) > 0.200001:
        return result
    if abs(a["deficit"] - a["financing"] - a["cash_adjustment"] + a["statistical_discrepancy"]) > 0.200001:
        return result
    result.update({key: value for key, value in a.items() if key != "deficit"})
    result.update(balance=-a["deficit"], absent_reason=None)
    return result

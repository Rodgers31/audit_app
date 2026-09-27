"""Parser for fiscal summary data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("seeding.fiscal_summary.parser")


@dataclass
class FiscalSummaryRecord:
    """One fiscal year of national fiscal data."""

    fiscal_year: str  # "FY 2024/25"
    appropriated_budget: float | None
    total_revenue: float | None
    tax_revenue: float | None
    non_tax_revenue: float | None
    total_borrowing: float | None
    borrowing_pct_of_budget: float | None
    debt_service_cost: float | None
    debt_service_per_shilling: float | None
    debt_ceiling: float | None
    actual_debt: float | None
    debt_ceiling_usage_pct: float | None
    development_spending: float | None
    recurrent_spending: float | None
    county_allocation: float | None
    # Which measure ``appropriated_budget`` is on ("cob_gross"), and the
    # document/page it was read from. Carried to the DB so the published
    # figure can never be re-interpreted as a different measure later: the
    # 4.19T Budget Policy Statement number and the 4.69T COB gross one are
    # both "the budget" and are 12% apart.
    budget_basis: str | None = None
    budget_basis_source: dict[str, Any] | None = None
    #: Billions KES of the gross budget that is redemption of maturing debt
    #: rather than new spending — the largest single reason the gross figure
    #: and the enacted headline differ. Absent where it could not be proved.
    debt_redemption: float | None = None
    #: The document ``debt_service_cost`` was read from. NOT the same thing as
    #: ``budget_basis_source``, which is where the BUDGET figure came from —
    #: for FY2025/26 that is COB's nine-month report while the debt service is
    #: the BPS budget estimate. Citing one for the other mis-cites (issue #235).
    debt_service_source: dict[str, Any] | None = None
    #: The Budget Summary's fiscal-framework split for this year — one basis,
    #: its own reconciling total, page and checks. See ``fiscal_framework.py``.
    #: Absent on a year no edition could supply.
    fiscal_framework: dict[str, Any] | None = None
    #: Which basis ``recurrent_spending`` / ``development_spending`` /
    #: ``county_allocation`` / ``total_borrowing`` are on. ``None`` means
    #: undeclared, never "the same as the others".
    split_basis: str | None = None
    #: Why a year has no split, or no tax split. Carried so the page can say
    #: so rather than drawing a bare gap.
    fiscal_framework_absent_reason: str | None = None
    tax_split_absent_reason: str | None = None


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _derive_debt_service_per_shilling(
    debt_service_cost: float | None,
    total_revenue: float | None,
    declared: float | None,
    *,
    label: str,
) -> float | None:
    """Debt service per KSh 100 of revenue — DERIVED from the numerator and
    denominator rather than read as a hand-entered figure.

    Why derived: a stored ratio drifts from its inputs. FY2025/26 had a
    declared 55.7 computed off a narrow "CFS charge" numerator, understating
    the true ratio (authoritative ~64-65%; Treasury APDMR / Cytonn 2025).
    Computing ``debt_service_cost / total_revenue`` guarantees the published
    number always matches the inputs and **auto-updates** when either changes
    on the next seed run. If the JSON still carries a declared value that
    diverges by >2pp we warn (data-quality signal) but always serve the
    computed one. Also flags an implausible result (outside a 30-95% band).
    """
    if not debt_service_cost or not total_revenue:
        return declared  # nothing to compute from — keep any declared value
    computed = round(debt_service_cost / total_revenue * 100, 1)
    if declared is not None and abs(declared - computed) > 2.0:
        logger.warning(
            "fiscal_summary %s: declared debt_service_per_shilling %.1f diverges "
            "from computed %.1f (ds=%.0f / rev=%.0f) — serving computed",
            label, declared, computed, debt_service_cost, total_revenue,
        )
    if not (30.0 <= computed <= 95.0):
        logger.warning(
            "fiscal_summary %s: debt-service-to-revenue %.1f%% outside the "
            "plausible 30-95%% band — review inputs (ds=%.0f / rev=%.0f)",
            label, computed, debt_service_cost, total_revenue,
        )
    return computed


def _derive_borrowing_pct_of_budget(
    total_borrowing: float | None,
    fiscal_framework: dict[str, Any] | None,
    declared: float | None,
    *,
    label: str,
) -> float | None:
    """Borrowing as a % of spending, DERIVED from two figures on ONE basis.

    ``total_borrowing`` is deficit financing from Treasury's fiscal
    framework, so its denominator is that framework's own spending total
    ("Expenditure and Net Lending"), carried in ``fiscal_framework``.

    It used to divide by ``appropriated_budget``. That is the Controller of
    Budget's GROSS figure, which counts principal redemption and excludes
    county transfers. Borrowing measured one way over spending measured
    another is a ratio of two bases, and that is what every row published
    (FY 2023/24: 918 over the COB gross 4,340 = 21.2, while the fixture
    itself declared 25.5 = 918 over the BPS 3,600). A row with no spending
    total on the borrowing's basis gets ``None``, not a mixed ratio. The
    declared value is never served, because nothing checks it.
    """
    total = (fiscal_framework or {}).get("total_expenditure_billion")
    if total_borrowing and total:
        computed = round(total_borrowing / float(total) * 100, 1)
        if declared is not None and abs(declared - computed) > 1.0:
            logger.warning(
                "fiscal_summary %s: declared borrowing_pct_of_budget %.1f diverges "
                "from computed %.1f (borrow=%.1f / spending=%.1f) — serving computed",
                label, declared, computed, total_borrowing, float(total),
            )
        return computed
    if total_borrowing:
        logger.info(
            "fiscal_summary %s: borrowing share withheld — no spending total on "
            "the borrowing's basis to divide by",
            label,
        )
    return None


def parse_fiscal_summary_payload(payload: dict[str, Any]) -> list[FiscalSummaryRecord]:
    """Parse fiscal summary JSON payload into records."""
    fiscal_years = payload.get("fiscal_years", [])
    if not fiscal_years:
        logger.warning("No fiscal_years entries found in payload")
        return []

    records: list[FiscalSummaryRecord] = []
    for fy in fiscal_years:
        label = fy.get("fiscal_year")
        if not label:
            logger.warning("Skipping fiscal entry without fiscal_year label")
            continue

        records.append(
            FiscalSummaryRecord(
                fiscal_year=label,
                appropriated_budget=_safe_float(fy.get("appropriated_budget")),
                total_revenue=_safe_float(fy.get("total_revenue")),
                tax_revenue=_safe_float(fy.get("tax_revenue")),
                non_tax_revenue=_safe_float(fy.get("non_tax_revenue")),
                total_borrowing=_safe_float(fy.get("total_borrowing")),
                # DERIVED from total_borrowing over the fiscal framework's own
                # spending total, so both sides are on one basis.
                borrowing_pct_of_budget=_derive_borrowing_pct_of_budget(
                    _safe_float(fy.get("total_borrowing")),
                    fy.get("fiscal_framework"),
                    _safe_float(fy.get("borrowing_pct_of_budget")),
                    label=label,
                ),
                debt_service_cost=_safe_float(fy.get("debt_service_cost")),
                # DERIVED from debt_service_cost / total_revenue so it can never
                # drift from its inputs and updates automatically on re-seed.
                debt_service_per_shilling=_derive_debt_service_per_shilling(
                    _safe_float(fy.get("debt_service_cost")),
                    _safe_float(fy.get("total_revenue")),
                    _safe_float(fy.get("debt_service_per_shilling")),
                    label=label,
                ),
                debt_ceiling=_safe_float(fy.get("debt_ceiling")),
                actual_debt=_safe_float(fy.get("actual_debt")),
                debt_ceiling_usage_pct=_safe_float(fy.get("debt_ceiling_usage_pct")),
                development_spending=_safe_float(fy.get("development_spending")),
                recurrent_spending=_safe_float(fy.get("recurrent_spending")),
                county_allocation=_safe_float(fy.get("county_allocation")),
                budget_basis=fy.get("budget_basis"),
                debt_redemption=_safe_float(fy.get("debt_redemption")),
                budget_basis_source=fy.get("budget_basis_source"),
                debt_service_source=fy.get("debt_service_source"),
                fiscal_framework=(
                    fy.get("fiscal_framework")
                    if isinstance(fy.get("fiscal_framework"), dict)
                    else None
                ),
                split_basis=fy.get("split_basis"),
                fiscal_framework_absent_reason=fy.get("fiscal_framework_absent_reason"),
                tax_split_absent_reason=fy.get("tax_split_absent_reason"),
            )
        )

    logger.info(f"Parsed {len(records)} fiscal summary records")
    return records

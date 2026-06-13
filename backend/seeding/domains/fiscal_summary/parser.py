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
                borrowing_pct_of_budget=_safe_float(fy.get("borrowing_pct_of_budget")),
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
            )
        )

    logger.info(f"Parsed {len(records)} fiscal summary records")
    return records

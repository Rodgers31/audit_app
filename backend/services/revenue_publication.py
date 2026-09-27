"""KRA departmental collections cannot form an Exchequer tax-head partition."""
from services.fiscal_outturns import finite_number

RESIDUAL_REASON = (
    "Other Tax Revenue is unavailable: Customs departmental collections include "
    "agency levies, and the source does not identify their Exchequer component."
)


def revenue_source_row(row):
    meta = row.meta if isinstance(row.meta, dict) else {}
    unsupported = row.revenue_type == "Other Tax Revenue" and meta.get("basis") != "published"
    reason = RESIDUAL_REASON if unsupported else meta.get("absent_reason")
    source = meta.get("source") if isinstance(meta.get("source"), dict) else None
    return {
        "revenue_type": row.revenue_type, "category": row.category,
        "basis": meta.get("basis"), "basis_note": meta.get("notes"),
        "amount": None if reason else finite_number(row.amount_billion_kes),
        "target": None if unsupported else finite_number(row.target_billion_kes),
        "performance_pct": None if reason else finite_number(row.performance_pct),
        "yoy_growth_pct": None if reason else finite_number(row.yoy_growth_pct, nonnegative=False),
        "share_pct": None,
        "share_absent_reason": "Collections on different bases do not form a partition of tax or Exchequer revenue.",
        "absent_reason": reason,
        "source_document_id": row.source_document_id,
        "source": source,
        "source_absent_reason": None if source and isinstance(source.get("url"), str) and source["url"].strip() else "Source version and observation date are not recorded for this row.",
        "measure": meta.get("measure") or (
            "Customs departmental collections, including agency levies"
            if row.revenue_type == "Customs & Import Duty" else row.revenue_type
        ),
    }

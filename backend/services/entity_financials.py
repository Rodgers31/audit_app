"""Dated expenditure summaries. Ambiguous accounting is withheld, never added up."""
from collections import defaultdict
import math
from decimal import Decimal, InvalidOperation

from models import BudgetLine
from sqlalchemy.orm import joinedload

from services.county_budget import CLASSIFICATION_CATEGORIES, BUDGET_PROVENANCE_LABELS
from services.publication_gate import _has_page_locator


def _amount(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return (
        float(number)
        if number.is_finite() and number >= 0 and math.isfinite(float(number))
        else None
    )


def budget_evidence_is_unreported(quarantine_reason, basis, provenance, source_meta):
    """Inspect the fields needed to distinguish reported from modelled lines."""
    if quarantine_reason or getattr(basis, "value", basis) in {
        "modelled",
        "projected",
    }:
        return True
    entries = provenance if isinstance(provenance, list) else [provenance]
    entries = [*entries, source_meta]
    return any(
        isinstance(entry, dict)
        and (
            str(entry.get("data_quality", "")).lower()
            in {"modelled", "modeled", "estimated", "projected", "synthetic", "fixture"}
            or str(entry.get("dataset_id", "")).startswith(
                ("bootstrap", "enhanced_county_data")
            )
            or entry.get("source") == "bootstrap"
        )
        for entry in entries
    )


def budget_line_is_unreported(line):
    provenance = getattr(line, "provenance", None)
    if budget_evidence_is_unreported(line.quarantine_reason, line.basis, provenance, None):
        return True
    return budget_evidence_is_unreported(
        line.quarantine_reason,
        line.basis,
        provenance,
        getattr(line.source_document, "meta", None),
    )


def financial_summary(lines, period=None):
    """One entity, period, document and currency; Total takes precedence over parts.

    Sector rows lack a completeness contract, so cannot stand in for the whole
    budget. Two documents are competing accounts, not additive components.
    Source/page presence establishes traceability, not independent verification.
    """
    classified = defaultdict(list)
    for line in lines:
        category = (line.category or "").strip().lower()
        if category in CLASSIFICATION_CATEGORIES and not line.subcategory:
            classified[category].append(line)
    selected = classified.get("total", [])
    basis = "reported_total" if selected else "recurrent_plus_development"
    reason = None
    if not selected:
        selected = classified.get("recurrent", []) + classified.get("development", [])
        if not all(classified.get(cat) for cat in ("recurrent", "development")):
            reason = "incomplete_classification" if selected else "no_reported_total"
    source_ids = {line.source_document_id for line in selected}
    currencies = {line.currency for line in selected}
    sources = []
    for doc_id in sorted(source_ids, key=str):
        rows = [line for line in selected if line.source_document_id == doc_id]
        doc = rows[0].source_document
        sources.append(
            {
                "id": doc_id,
                "title": doc.title if doc else None,
                "publisher": doc.publisher if doc else None,
                "url": doc.url if doc else None,
                "page_refs": sorted(
                    {
                        str(line.page_ref).strip()
                        for line in rows
                        if line.page_ref and str(line.page_ref).strip()
                    }
                ),
            }
        )
    if (
        period is None
        or not period.start_date
        or not period.end_date
        or period.end_date < period.start_date
    ):
        reason = "no_valid_period"
    elif any(line.period_id != period.id for line in selected):
        reason = "mixed_periods"
    elif len(source_ids) > 1:
        reason = "multiple_sources"
    elif len(currencies) > 1 or (selected and not all(currencies)):
        reason = "incompatible_currencies"
    elif any(
        len(classified[cat]) > 1
        for cat in (
            {"total"} if classified.get("total") else {"recurrent", "development"}
        )
    ):
        reason = "duplicate_classification"
    elif any(not (source["url"] or "").strip() for source in sources):
        reason = "source_document_has_no_url"
    elif any(
        line.page_ref
        and str(line.page_ref).strip()
        and not _has_page_locator(line.page_ref, allow_descriptive=True)
        for line in selected
    ):
        reason = "no_page_reference"
    elif any(budget_line_is_unreported(line) for line in selected):
        reason = "not_reported_actuals"

    def total(field):
        values = [_amount(getattr(line, field)) for line in selected]
        return (
            _amount(sum(values))
            if values and all(value is not None for value in values)
            else None
        )

    allocation = None if reason else total("allocated_amount")
    spent = None if reason else total("actual_spent")
    execution = (
        _amount(spent / allocation * 100) if allocation and spent is not None else None
    )
    absent = {}
    if allocation is None:
        absent["total_allocation"] = reason or "allocation_not_reported"
    if spent is None:
        absent["total_spent"] = reason or "spending_not_reported"
    if execution is None:
        absent["execution_rate"] = reason or (
            "spending_not_reported" if spent is None else "no_positive_allocation"
        )
    return {
        "fiscal_period": (
            {
                "id": period.id,
                "label": period.label,
                "start_date": period.start_date.isoformat()
                if period.start_date
                else None,
                "end_date": period.end_date.isoformat() if period.end_date else None,
            }
            if period
            else None
        ),
        "total_allocation": allocation,
        "total_spent": spent,
        "execution_rate": execution,
        "accounting_basis": basis if selected else None,
        "currency": next(iter(currencies)) if len(currencies) == 1 else None,
        "sources": sources,
        "absent_reasons": absent,
        "budget_lines_count": len(selected),
    }


def entity_financial_series(db, entity_ids):
    """Batch-load source and period once for the entire entity page."""
    if not entity_ids:
        return {}
    lines = (
        db.query(BudgetLine)
        .options(joinedload(BudgetLine.period), joinedload(BudgetLine.source_document))
        .filter(BudgetLine.entity_id.in_(entity_ids))
        .all()
    )
    grouped = defaultdict(lambda: defaultdict(list))
    for line in lines:
        grouped[line.entity_id][line.period_id].append(line)
    result = {}
    for entity_id, periods in grouped.items():
        ordered = sorted(
            periods.values(),
            key=lambda rows: (
                rows[0].period.start_date,
                rows[0].period.end_date,
                rows[0].period_id,
            ),
            reverse=True,
        )
        result[entity_id] = [
            financial_summary(rows, rows[0].period) for rows in ordered
        ]
    return result


def summary_budget_source(summary):
    """A classification row cannot establish who published its report.

    Keep the existing CBIRR code only when the selected document identifies
    both the publisher and report series. Other publishers retain their exact
    document metadata in ``sources`` without inheriting a CoB attribution.
    """
    if summary["total_allocation"] is None or not summary["sources"]:
        return None
    for source in summary["sources"]:
        publisher = " ".join((source.get("publisher") or "").casefold().split())
        title = " ".join((source.get("title") or "").casefold().split())
        if publisher not in {"controller of budget", "office of the controller of budget"}:
            return None
        if not ("county" in title and "budget implementation review" in title) and "cbirr" not in title:
            return None
    return "cob_cbirr"


def publish_county_budget(payload, summary, *, comprehensive=False):
    """Use the same accounting contract for county map, list and detail figures."""
    allocation, spent, rate = (
        summary[key] for key in ("total_allocation", "total_spent", "execution_rate")
    )
    valid = allocation is not None
    source_code = summary_budget_source(summary)
    published = {
        "total_allocated": allocation,
        "total_spent": spent,
        "utilization_rate": rate,
        "fiscal_period": summary["fiscal_period"],
        "sources": summary["sources"],
        "accounting_basis": summary["accounting_basis"],
        "absent_reasons": summary["absent_reasons"],
    }
    if comprehensive:
        payload["budget"].update(published)
        payload["budget"]["source"] = source_code
        payload["data_sources"]["budget"] = (
            BUDGET_PROVENANCE_LABELS.get(source_code) or "; ".join(
                " — ".join(value for value in (source.get("publisher"), source.get("title")) if value)
                for source in summary["sources"]
            ) or None
        ) if valid else None
        payload["budget"]["per_capita_budget"] = (
            round(allocation / payload["demographics"]["population"], 2)
            if allocation is not None and payload["demographics"].get("population")
            else None
        )
        payload["financial_summary"]["budget_execution_rate"] = rate
        for section, key, amount in [
            ("debt", "debt_to_budget_ratio", payload["debt"].get("total_debt")),
            (
                "financial_summary",
                "pending_bills_ratio",
                payload["debt"].get("pending_bills"),
            ),
        ]:
            payload[section][key] = (
                amount / allocation * 100 if allocation and amount is not None else None
            )
        if not allocation or spent is None:
            for key in ("health_score", "grade", "debt_sustainability"):
                payload["financial_summary"][key] = None
            for key in ("health_score", "grade"):
                payload["audit"][key] = None
        if not valid:
            payload["budget"].update(
                source=None,
                development_budget=None,
                recurrent_budget=None,
                sector_breakdown={},
            )
            payload["data_sources"]["budget"] = None
    else:
        payload.update(
            budget_source=source_code,
            financial_summary=summary,
            total_budget=allocation,
            budget_2025=allocation,
            total_spent=spent,
            budget_utilization=rate,
        )
        if not allocation or spent is None:
            payload.update(financial_health=None, financial_health_score=None)
        if not valid:
            payload.update(
                budget_source=None,
                development_budget=None,
                recurrent_budget=None,
                sector_breakdown={},
            )
    return payload

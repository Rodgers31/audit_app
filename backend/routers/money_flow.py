"""
Follow the Money – county and national money-flow waterfall endpoints.

Traces public funds through: Allocation → Release → Expenditure → Audit Flags.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Audit, BudgetLine, Entity, EntityType, FiscalPeriod

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["money-flow"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_stage(
    stage: str,
    label: str,
    amount: Optional[float],
    source: Optional[str] = None,
    source_doc: Optional[str] = None,
    gap_from_prev: Optional[float] = None,
    gap_label: Optional[str] = None,
    data_unavailable: bool = False,
) -> Dict[str, Any]:
    """Build a single waterfall stage dict."""
    d: Dict[str, Any] = {
        "stage": stage,
        "label": label,
        "amount": amount,
    }
    if source is not None:
        d["source"] = source
    if source_doc is not None:
        d["source_doc"] = source_doc
    if gap_from_prev is not None:
        d["gap_from_prev"] = gap_from_prev
    if gap_label is not None:
        d["gap_label"] = gap_label
    if data_unavailable:
        d["data_unavailable"] = True
    return d


def _resolve_periods(db: Session, fiscal_year: str) -> List[int]:
    """Return period IDs whose label contains the given fiscal year string."""
    periods = (
        db.query(FiscalPeriod.id)
        .filter(FiscalPeriod.label.ilike(f"%{fiscal_year}%"))
        .all()
    )
    return [p.id for p in periods]


def _money_flow_for_entity(
    db: Session,
    entity_id: int,
    period_ids: List[int],
) -> Dict[str, Any]:
    """Compute money-flow stages for a single entity and period set."""
    # --- Allocated & Spent from BudgetLine ---
    # If no matching periods found, there's no data for this year
    if not period_ids:
        return {
            "stages": [
                _build_stage("Allocated", "Budget Allocation", None,
                             source="CRA Allocation + Conditional Grants", data_unavailable=True),
                _build_stage("Released", "Funds Released", None,
                             gap_label="Withheld/Delayed", data_unavailable=True),
                _build_stage("Spent", "Actual Expenditure", None,
                             gap_label="Unspent Funds", data_unavailable=True),
                _build_stage("Flagged", "Auditor Flagged", None,
                             gap_label="Irregular/Unsupported Expenditure", data_unavailable=True),
            ],
            "total_waste_estimate": None,
            "efficiency_score": None,
        }

    budget_q = db.query(BudgetLine).filter(
        BudgetLine.entity_id == entity_id,
        BudgetLine.period_id.in_(period_ids),
    )
    budget_lines = budget_q.all()

    if budget_lines:
        allocated = sum(float(b.allocated_amount or 0) for b in budget_lines)
        spent = sum(float(b.actual_spent or 0) for b in budget_lines)
        # COB data doesn't have a separate "released" column – use committed_amount
        # as a proxy for releases if available, otherwise mark unavailable.
        committed_amounts = [b.committed_amount for b in budget_lines if b.committed_amount is not None]
        if committed_amounts:
            released = sum(float(c) for c in committed_amounts)
        else:
            released = None

        # Source doc URL from first budget line
        first_doc = budget_lines[0].source_document if budget_lines else None
        source_doc_url = first_doc.url if first_doc and hasattr(first_doc, "url") else None
    else:
        allocated = None
        released = None
        spent = None
        source_doc_url = None

    # --- Audit flagged amounts ---
    audit_q = db.query(func.sum(Audit.amount)).filter(
        Audit.entity_id == entity_id,
        Audit.period_id.in_(period_ids),
    )
    flagged = audit_q.scalar()
    flagged = float(flagged) if flagged else None

    # --- Build stages ---
    stages: List[Dict[str, Any]] = []

    # 1. Allocated
    stages.append(_build_stage(
        stage="Allocated",
        label="Budget Allocation",
        amount=allocated,
        source="CRA Allocation + Conditional Grants",
        source_doc=source_doc_url,
        data_unavailable=allocated is None,
    ))

    # 2. Released
    if released is not None and allocated is not None:
        gap = round(allocated - released, 2)
    else:
        gap = None
    stages.append(_build_stage(
        stage="Released",
        label="Funds Released",
        amount=released,
        gap_from_prev=gap,
        gap_label="Withheld/Delayed",
        data_unavailable=released is None,
    ))

    # 3. Spent
    prev_for_spent = released if released is not None else allocated
    if spent is not None and prev_for_spent is not None:
        gap_spent = round(prev_for_spent - spent, 2)
    else:
        gap_spent = None
    stages.append(_build_stage(
        stage="Spent",
        label="Actual Expenditure",
        amount=spent,
        gap_from_prev=gap_spent,
        gap_label="Unspent Funds",
        data_unavailable=spent is None,
    ))

    # 4. Flagged
    stages.append(_build_stage(
        stage="Flagged",
        label="Auditor Flagged",
        amount=flagged,
        gap_from_prev=None,
        gap_label="Irregular/Unsupported Expenditure",
        data_unavailable=flagged is None,
    ))

    # --- Derived metrics ---
    efficiency = None
    if spent is not None and allocated and allocated > 0:
        efficiency = round((spent / allocated) * 100, 2)

    return {
        "stages": stages,
        "total_waste_estimate": flagged,
        "efficiency_score": efficiency,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/counties/{county_id}/money-flow")
async def county_money_flow(
    county_id: int,
    year: str = Query(..., description="Fiscal year label, e.g. '2024/25'"),
    db: Session = Depends(get_db),
):
    """Trace the full money flow for a county in a fiscal year."""
    entity = (
        db.query(Entity)
        .filter(Entity.id == county_id, Entity.type == EntityType.COUNTY)
        .first()
    )
    if not entity:
        raise HTTPException(status_code=404, detail="County not found")

    period_ids = _resolve_periods(db, year)

    result = _money_flow_for_entity(db, entity.id, period_ids)

    return {
        "county_id": entity.id,
        "county_name": entity.canonical_name,
        "fiscal_year": year,
        **result,
    }


@router.get("/audit/money-flow/national")
async def national_money_flow(
    year: str = Query(..., description="Fiscal year label, e.g. '2024/25'"),
    db: Session = Depends(get_db),
):
    """Aggregate money flow across all counties for a fiscal year."""
    period_ids = _resolve_periods(db, year)

    county_entities = (
        db.query(Entity).filter(Entity.type == EntityType.COUNTY).all()
    )
    if not county_entities:
        raise HTTPException(status_code=404, detail="No county entities found")

    entity_ids = [e.id for e in county_entities]

    # --- Aggregated budget data ---
    if not period_ids:
        allocated = None
        released = None
        spent = None
        source_doc_url = None
        flagged = None
    else:
        budget_q = db.query(BudgetLine).filter(
            BudgetLine.entity_id.in_(entity_ids),
            BudgetLine.period_id.in_(period_ids),
        )
        budget_lines = budget_q.all()

        if budget_lines:
            allocated = sum(float(b.allocated_amount or 0) for b in budget_lines)
            spent = sum(float(b.actual_spent or 0) for b in budget_lines)
            committed = [b.committed_amount for b in budget_lines if b.committed_amount is not None]
            released = sum(float(c) for c in committed) if committed else None
            first_doc = budget_lines[0].source_document if budget_lines else None
            source_doc_url = first_doc.url if first_doc and hasattr(first_doc, "url") else None
        else:
            allocated = None
            released = None
            spent = None
            source_doc_url = None

        # --- Aggregated audit flags ---
        audit_q = db.query(func.sum(Audit.amount)).filter(
            Audit.entity_id.in_(entity_ids),
            Audit.period_id.in_(period_ids),
        )
        flagged_raw = audit_q.scalar()
        flagged = float(flagged_raw) if flagged_raw else None

    # --- Build stages ---
    stages = []

    stages.append(_build_stage(
        stage="Allocated",
        label="Budget Allocation",
        amount=allocated,
        source="CRA Allocation + Conditional Grants",
        source_doc=source_doc_url,
        data_unavailable=allocated is None,
    ))

    if released is not None and allocated is not None:
        gap = round(allocated - released, 2)
    else:
        gap = None
    stages.append(_build_stage(
        stage="Released",
        label="Funds Released",
        amount=released,
        gap_from_prev=gap,
        gap_label="Withheld/Delayed",
        data_unavailable=released is None,
    ))

    prev_for_spent = released if released is not None else allocated
    if spent is not None and prev_for_spent is not None:
        gap_spent = round(prev_for_spent - spent, 2)
    else:
        gap_spent = None
    stages.append(_build_stage(
        stage="Spent",
        label="Actual Expenditure",
        amount=spent,
        gap_from_prev=gap_spent,
        gap_label="Unspent Funds",
        data_unavailable=spent is None,
    ))

    stages.append(_build_stage(
        stage="Flagged",
        label="Auditor Flagged",
        amount=flagged,
        gap_from_prev=None,
        gap_label="Irregular/Unsupported Expenditure",
        data_unavailable=flagged is None,
    ))

    efficiency = None
    if spent is not None and allocated and allocated > 0:
        efficiency = round((spent / allocated) * 100, 2)

    return {
        "county_id": None,
        "county_name": "National (All Counties)",
        "fiscal_year": year,
        "county_count": len(county_entities),
        "stages": stages,
        "total_waste_estimate": flagged,
        "efficiency_score": efficiency,
    }

"""
Follow the Money – county and national money-flow waterfall endpoints.

Traces public funds through: Allocation → Release → Expenditure → Audit Flags.
"""

import functools
import logging
import re
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from services.publication_gate import publishable_audit_criterion

from database import get_db
from models import Audit, BudgetLine, Entity, EntityType, FiscalPeriod

logger = logging.getLogger(__name__)

# Try to import Redis cache; fall back to in-memory TTL cache
try:
    from cache.redis_cache import RedisCache
    _redis_cache = RedisCache()
except Exception:
    _redis_cache = None


def _effective_ttl(result: object, ttl: int) -> int:
    """Cache lifetime for ``result`` — shortened when it reports an unreadable
    source, so a recovered source is visible in seconds rather than hours.
    See cache/redis_cache.py::is_transient_failure and issue #141."""
    from cache.redis_cache import TRANSIENT_FAILURE_TTL, is_transient_failure

    return min(ttl, TRANSIENT_FAILURE_TTL) if is_transient_failure(result) else ttl


def _cached(key_prefix: str, ttl: int = 1800):
    """Cache decorator with Redis + in-memory fallback."""
    def decorator(fn):
        _mem: Dict[str, Dict[str, Any]] = {}

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            parts = [key_prefix]
            for k, v in kwargs.items():
                if k not in ("db", "request", "background_tasks"):
                    parts.append(f"{k}:{v}")
            cache_key = ":".join(parts)

            if _redis_cache:
                hit = _redis_cache.get(cache_key)
                if hit is not None:
                    return hit
                result = await fn(*args, **kwargs)
                _redis_cache.set(cache_key, result, ttl=_effective_ttl(result, ttl))
                return result

            rec = _mem.get(cache_key)
            # Honour the TTL the entry was stored with (see main.py).
            if rec and (time.time() - rec["ts"]) < rec.get("ttl", ttl):
                return rec["value"]
            result = await fn(*args, **kwargs)
            _mem[cache_key] = {
                "value": result,
                "ts": time.time(),
                "ttl": _effective_ttl(result, ttl),
            }
            return result

        # NB: _mem is the no-Redis-object fallback and is only reached if
        # RedisCache() itself failed to construct — an instance is truthy even
        # when it has no server, so the branch above normally wins and the real
        # cache is _redis_cache._memory_cache.  That instance is cleared
        # between tests via RedisCache._instances (see main.clear_all_caches).
        wrapper._cache = _mem
        return wrapper
    return decorator

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


class UnparseableFiscalYear(ValueError):
    """The caller sent something that is not a fiscal-year label at all."""


def _normalize_fiscal_year(fiscal_year: str) -> List[str]:
    """Return candidate DB label forms for a fiscal year input.

    Accepts "2023/24", "2023/2024", "FY2023/24", "FY 2023/24", "2023-24",
    "2023-2024", "23/24", and the same forms carrying a PERIOD QUALIFIER —
    "FY2025/26 9M", "FY2025/26 H1" — which is how the Controller of Budget
    labels its part-year implementation reports.

    Two defects lived here (credibility audit F3/F36):

    * The pattern was anchored to end-of-string right after the second year
      group, so every qualified label failed to parse. `/audits/fiscal-years`
      offers "FY2025/26 9M" and "FY2025/26 H1" and the Follow the Money picker
      renders both, but the money-flow endpoints could never resolve them — the
      page showed "no data yet" for periods that exist in the database.

    * A value that is not a fiscal year at all (a bare calendar year, "2024")
      also returned [], and the caller could not tell that from "this period
      has nothing published". That is what sent the audit that commissioned
      this work looking for a missing ETL join that was really a wrong
      parameter format. Unparseable input now raises.

    A qualified input matches ONLY qualified labels, and an unqualified input
    matches only the unqualified label — asking for the full year must not
    silently return the 9-month report.
    """
    if not fiscal_year or not fiscal_year.strip():
        raise UnparseableFiscalYear("empty fiscal year")
    raw = fiscal_year.strip().upper().replace("FY", "").strip()
    m = re.match(r"^\s*(\d{2,4})\s*[/\-]\s*(\d{2,4})\s*(.*)$", raw)
    if not m:
        raise UnparseableFiscalYear(
            f"{fiscal_year!r} is not a fiscal-year label; expected e.g. "
            "'FY2024/25' or 'FY2025/26 9M'"
        )
    y1, y2, qualifier = m.group(1), m.group(2), m.group(3).strip()
    y1_full = y1 if len(y1) == 4 else f"20{y1}"
    y2_short = y2[-2:] if len(y2) >= 2 else y2.zfill(2)
    y2_full = f"{y1_full[:2]}{y2_short}"

    bases = [
        f"FY{y1_full}/{y2_short}",        # canonical: FY2023/24
        f"FY{y1_full}/{y2_full}",         # FY2023/2024
        f"{y1_full}/{y2_short}",          # 2023/24
        f"{y1_full}/{y2_full}",           # 2023/2024
        f"FY{y1_full}-{y2_short}",        # FY2023-24
    ]
    if not qualifier:
        return bases
    # "FY2025/26 9M" — keep the qualifier attached, and try the couple of
    # spacings the labels are written with.
    return [f"{b} {qualifier}" for b in bases] + [f"{b}{qualifier}" for b in bases]


def _resolve_periods(db: Session, fiscal_year: str) -> List[int]:
    """Period IDs for a fiscal year label. Raises on unparseable input.

    An empty list now means exactly one thing — the label parsed but no such
    period exists in the database — so callers can report that separately from
    "you sent us something we could not read".
    """
    candidates = _normalize_fiscal_year(fiscal_year)
    periods = (
        db.query(FiscalPeriod.id)
        .filter(FiscalPeriod.label.in_(candidates))
        .all()
    )
    return [p.id for p in periods]


def _period_exists(db: Session, fiscal_year: str) -> bool:
    """Does any fiscal period carry this label? Used to tell 'unknown period'
    from 'known period with nothing published in it'."""
    return bool(_resolve_periods(db, fiscal_year))


def _resolve_periods_or_400(db: Session, year: str) -> List[int]:
    """Resolve a fiscal-year parameter, refusing input that is not one.

    Silently answering an unreadable parameter with a well-formed "no data"
    object is how a wrong request format reads as a missing dataset
    (credibility audit F36).
    """
    try:
        return _resolve_periods(db, year)
    except UnparseableFiscalYear as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_fiscal_year",
                "message": str(exc),
                "hint": (
                    "Use a fiscal-year label, e.g. 'FY2024/25'. Part-year "
                    "Controller of Budget periods carry a qualifier: "
                    "'FY2025/26 H1', 'FY2025/26 9M'. A bare calendar year is "
                    "not a fiscal year."
                ),
            },
        ) from exc



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
        # Treat "no non-null spent rows" as data-unavailable (projected-
        # year budgets don't have execution figures yet). Returning 0
        # would misleadingly render as "100% unspent" in the waterfall.
        spent_vals = [b.actual_spent for b in budget_lines if b.actual_spent is not None]
        spent = sum(float(s) for s in spent_vals) if spent_vals else None
        # "Committed" = procurement encumbrances (contracts awarded but
        # not yet paid out). This is NOT the same as "exchequer release"
        # — Treasury disbursements aren't currently captured in the COB
        # reports we ingest. Kept for future-use but deliberately NOT
        # surfaced as a waterfall stage: an earlier version rendered this
        # as "Funds Released" which was actively misleading (committed
        # << spent for most counties, which is impossible to read as
        # "received < paid").
        committed_amounts = [b.committed_amount for b in budget_lines if b.committed_amount is not None]
        committed = sum(float(c) for c in committed_amounts) if committed_amounts else None

        # Source doc URL + label from first budget line. The CoB budget
        # implementation review reports are often H1 (half-year) or Q-
        # specific, so we surface the exact title rather than implying
        # a full-year snapshot.
        first_doc = budget_lines[0].source_document if budget_lines else None
        source_doc_url = first_doc.url if first_doc and hasattr(first_doc, "url") else None
        source_doc_title = (
            first_doc.title if first_doc and hasattr(first_doc, "title") else None
        )
    else:
        allocated = None
        committed = None
        spent = None
        source_doc_url = None
        source_doc_title = None

    # --- Audit flagged amounts ---
    audit_q = db.query(func.sum(Audit.amount)).filter(
        publishable_audit_criterion(),
        Audit.entity_id == entity_id,
        Audit.period_id.in_(period_ids),
    )
    flagged = audit_q.scalar()
    flagged = float(flagged) if flagged else None

    # --- Build stages ---
    # We surface three stages from data we ACTUALLY have:
    #   • Allocated — from COB `allocated_amount` per budget line
    #   • Spent     — from COB `actual_spent`
    #   • Flagged   — from OAG audit findings with a KES amount
    # An older version also rendered a "Funds Released" stage between
    # allocated and spent, using `committed_amount` as a proxy. That's a
    # different quantity (procurement encumbrances, not Treasury
    # disbursements) and produced impossible-looking figures like
    # "spent > released". Removed until we parse the real exchequer-
    # release column from CoB.
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

    # 2. Spent
    if spent is not None and allocated is not None:
        gap_spent = round(allocated - spent, 2)
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
        # Provenance — surfaced in the UI so every figure is traceable
        # back to an official Controller of Budget (CoB) publication.
        "source_document_title": source_doc_title,
        "source_document_url": source_doc_url,
        # Surface committed separately (not as a waterfall stage) for
        # callers that want to show "procurement encumbered" as a
        # supplementary figure.
        "committed_amount": committed,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/counties/{county_id}/money-flow")
async def county_money_flow(
    county_id: str,
    year: str = Query(..., description="Fiscal year label, e.g. '2024/25'"),
    db: Session = Depends(get_db),
):
    """Trace the full money flow for a county in a fiscal year.

    ``county_id`` accepts any of:
      * the 3-digit Kenyan county code ("001" → Nairobi, "047" → Mombasa),
      * the raw numeric ``Entity.id`` (database primary key),
      * the county ``slug`` (e.g. ``nairobi-city``).
    The 3-digit-code path is what the frontend actually links from, so
    resolve it first via the canonical COUNTY_MAPPING.
    """
    q = db.query(Entity).filter(Entity.type == EntityType.COUNTY)
    entity = None

    # 3-digit county-code lookup (most common path from the UI).
    if county_id.isdigit() and len(county_id) == 3:
        try:
            from main import COUNTY_MAPPING  # avoid circular import at module load
        except ImportError:
            COUNTY_MAPPING = {}
        county_name = COUNTY_MAPPING.get(county_id)
        if county_name:
            entity = q.filter(
                Entity.canonical_name == f"{county_name} County"
            ).first()
            if not entity:
                slug = county_name.lower().replace(" ", "-") + "-county"
                entity = q.filter(Entity.slug == slug).first()

    # Fallbacks: raw Entity.id then slug.
    if not entity:
        if county_id.isdigit():
            entity = q.filter(Entity.id == int(county_id)).first()
        else:
            entity = q.filter(Entity.slug == county_id).first()

    if not entity:
        raise HTTPException(status_code=404, detail="County not found")

    period_ids = _resolve_periods_or_400(db, year)

    result = _money_flow_for_entity(db, entity.id, period_ids)

    return {
        "county_id": entity.id,
        "county_name": entity.canonical_name,
        "fiscal_year": year,
        **result,
    }


@router.get("/audit/money-flow/national")
@_cached(key_prefix="money-flow:national", ttl=1800)
async def national_money_flow(
    year: str = Query(..., description="Fiscal year label, e.g. '2024/25'"),
    db: Session = Depends(get_db),
):
    """Aggregate money flow across all counties for a fiscal year."""
    period_ids = _resolve_periods_or_400(db, year)

    county_entities = (
        db.query(Entity).filter(Entity.type == EntityType.COUNTY).all()
    )
    if not county_entities:
        raise HTTPException(status_code=404, detail="No county entities found")

    entity_ids = [e.id for e in county_entities]

    # --- Aggregated budget data ---
    if not period_ids:
        allocated = None
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
            # Treat "no non-null spent rows" as data-unavailable (e.g.
            # projected-year budgets where CoB has not yet released the
            # execution figures). Returning 0 in that case lies by
            # omission — the waterfall would show 100% unspent.
            spent_vals = [b.actual_spent for b in budget_lines if b.actual_spent is not None]
            spent = sum(float(s) for s in spent_vals) if spent_vals else None
            first_doc = budget_lines[0].source_document if budget_lines else None
            source_doc_url = first_doc.url if first_doc and hasattr(first_doc, "url") else None
        else:
            allocated = None
            spent = None
            source_doc_url = None

        # --- Aggregated audit flags ---
        audit_q = db.query(func.sum(Audit.amount)).filter(
            publishable_audit_criterion(),
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

    # See _money_flow_for_entity — the "Released" stage is intentionally
    # omitted. Treasury exchequer disbursements aren't captured by the
    # CoB budget-implementation seeder, and using `committed_amount` as
    # a proxy (previous behaviour) produced misleading numbers.
    if spent is not None and allocated is not None:
        gap_spent = round(allocated - spent, 2)
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
        "source_document_url": source_doc_url,
        # Why the stages are empty, when they are. A caller could previously
        # not tell "this fiscal period is not in the database" from "the
        # period is there but nothing has been published for it yet"
        # (credibility audit F36).
        "unavailable_reason": (
            None
            if period_ids
            else "fiscal_period_not_found"
        ),
    }


@router.get("/money-flow/all-counties")
@_cached(key_prefix="money-flow:all-counties", ttl=1800)
async def all_counties_money_flow(
    year: str = Query(..., description="Fiscal year label, e.g. '2024/25'"),
    db: Session = Depends(get_db),
):
    """Batch endpoint: money flow for every county in a single response.

    Replaces N individual /counties/{id}/money-flow calls with 3 SQL queries.
    """
    period_ids = _resolve_periods_or_400(db, year)

    # 1. All county entities in ONE query
    county_entities = (
        db.query(Entity.id, Entity.canonical_name)
        .filter(Entity.type == EntityType.COUNTY)
        .all()
    )
    if not county_entities:
        return []

    entity_map = {eid: name for eid, name in county_entities}
    entity_ids = list(entity_map.keys())

    # Short-circuit if no matching fiscal periods
    if not period_ids:
        no_data_stages = [
            _build_stage("Allocated", "Budget Allocation", None,
                         source="CRA Allocation + Conditional Grants", data_unavailable=True),
            _build_stage("Spent", "Actual Expenditure", None,
                         gap_label="Unspent Funds", data_unavailable=True),
            _build_stage("Flagged", "Auditor Flagged", None,
                         gap_label="Irregular/Unsupported Expenditure", data_unavailable=True),
        ]
        return [
            {
                "county_id": eid,
                "county_name": name,
                "fiscal_year": year,
                "stages": no_data_stages,
                "total_waste_estimate": None,
                "efficiency_score": None,
            }
            for eid, name in county_entities
        ]

    # 2. Aggregate budget lines per entity in ONE query
    budget_rows = (
        db.query(
            BudgetLine.entity_id,
            func.sum(func.coalesce(BudgetLine.allocated_amount, 0)).label("allocated"),
            func.sum(func.coalesce(BudgetLine.actual_spent, 0)).label("spent"),
            func.sum(BudgetLine.committed_amount).label("committed"),
        )
        .filter(
            BudgetLine.entity_id.in_(entity_ids),
            BudgetLine.period_id.in_(period_ids),
        )
        .group_by(BudgetLine.entity_id)
        .all()
    )
    budget_map: Dict[int, Dict[str, Any]] = {}
    for eid, alloc, spent, committed in budget_rows:
        budget_map[eid] = {
            "allocated": float(alloc) if alloc else None,
            "spent": float(spent) if spent else None,
            "committed": float(committed) if committed else None,
        }

    # 3. Aggregate audit flagged amounts per entity in ONE query
    audit_rows = (
        db.query(
            Audit.entity_id,
            func.sum(Audit.amount),
        )
        .filter(
            publishable_audit_criterion(),
            Audit.entity_id.in_(entity_ids),
            Audit.period_id.in_(period_ids),
        )
        .group_by(Audit.entity_id)
        .all()
    )
    flagged_map: Dict[int, float] = {
        eid: float(amt) for eid, amt in audit_rows if amt
    }

    # 4. Build response for every county
    results = []
    for eid, name in county_entities:
        b = budget_map.get(eid, {})
        allocated = b.get("allocated")
        committed = b.get("committed")
        spent = b.get("spent")
        flagged = flagged_map.get(eid)

        stages: List[Dict[str, Any]] = []

        stages.append(_build_stage(
            stage="Allocated", label="Budget Allocation", amount=allocated,
            source="CRA Allocation + Conditional Grants",
            data_unavailable=allocated is None,
        ))

        # "Released" stage intentionally omitted — see comment in
        # _money_flow_for_entity. Treasury disbursements aren't in our
        # data, and `committed_amount` is not an equivalent quantity.
        gap_spent = round(allocated - spent, 2) if (spent is not None and allocated is not None) else None
        stages.append(_build_stage(
            stage="Spent", label="Actual Expenditure", amount=spent,
            gap_from_prev=gap_spent, gap_label="Unspent Funds",
            data_unavailable=spent is None,
        ))

        stages.append(_build_stage(
            stage="Flagged", label="Auditor Flagged", amount=flagged,
            gap_from_prev=None, gap_label="Irregular/Unsupported Expenditure",
            data_unavailable=flagged is None,
        ))

        efficiency = None
        if spent is not None and allocated and allocated > 0:
            efficiency = round((spent / allocated) * 100, 2)

        results.append({
            "county_id": eid,
            "county_name": name,
            "fiscal_year": year,
            "stages": stages,
            "total_waste_estimate": flagged,
            "efficiency_score": efficiency,
        })

    return results

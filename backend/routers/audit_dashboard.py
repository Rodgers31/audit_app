"""
Audit Dashboard Router — National Audit Findings API

Provides endpoints for:
- Summary statistics (totals, breakdowns, worst counties)
- Year-over-year trends
- Recurring findings detection
- Paginated findings list with filters
"""

import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, desc, func
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from database import get_db
    from models import Audit, Entity, EntityType, Extraction, SourceDocument

    DATABASE_AVAILABLE = True
except Exception:
    DATABASE_AVAILABLE = False

    def get_db():
        return None


router = APIRouter(prefix="/api/v1/audit", tags=["Audit Dashboard"])
logger = logging.getLogger(__name__)


# ===== Response Models =====


class WorstCounty(BaseModel):
    county_id: int
    county_name: str
    total_amount: float
    finding_count: int


class YearRange(BaseModel):
    min_year: Optional[int] = None
    max_year: Optional[int] = None


class AuditSummaryResponse(BaseModel):
    total_irregular_expenditure: float
    total_unsupported_expenditure: float
    total_findings: int
    findings_by_type: Dict[str, int]
    findings_by_opinion: Dict[str, int]
    worst_counties: List[WorstCounty]
    year_range: YearRange


class AuditTrendsResponse(BaseModel):
    years: List[int]
    findings_per_year: Dict[str, int]
    amount_per_year: Dict[str, float]
    opinion_per_year: Dict[str, Dict[str, int]]


class RecurringFinding(BaseModel):
    county_name: str
    query_type: str
    years_appeared: List[int]
    total_amount: float
    finding_ids: List[int]


class RecurringFindingsResponse(BaseModel):
    recurring_findings: List[RecurringFinding]
    total: int


class FindingDetail(BaseModel):
    id: int
    entity_id: int
    county_name: Optional[str] = None
    period_id: int
    finding_text: str
    severity: str
    recommended_action: Optional[str] = None
    query_type: Optional[str] = None
    amount: Optional[float] = None
    status: Optional[str] = None
    audit_opinion: Optional[str] = None
    audit_year: Optional[int] = None
    follow_up_status: Optional[str] = None
    external_reference: Optional[str] = None
    management_response: Optional[str] = None
    source_document_url: Optional[str] = None
    confidence_score: Optional[float] = None


class FindingsListResponse(BaseModel):
    items: List[FindingDetail]
    total: int
    page: int
    limit: int


# ===== Helpers =====


def _check_db(db: Session):
    if not DATABASE_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")


# ===== Endpoints =====


@router.get("/summary", response_model=AuditSummaryResponse)
async def get_audit_summary(db: Session = Depends(get_db)):
    """Return aggregate audit statistics for the national dashboard."""
    _check_db(db)
    try:
        # Total findings
        total_findings = db.query(func.count(Audit.id)).scalar() or 0

        # Total irregular expenditure
        total_irregular = (
            db.query(func.coalesce(func.sum(Audit.amount), 0))
            .filter(Audit.query_type == "Financial Irregularity")
            .scalar()
        )

        # Total unsupported expenditure (status != Resolved)
        total_unsupported = (
            db.query(func.coalesce(func.sum(Audit.amount), 0))
            .filter(Audit.status != "Resolved")
            .scalar()
        )

        # Findings by type
        type_rows = (
            db.query(Audit.query_type, func.count(Audit.id))
            .filter(Audit.query_type.isnot(None))
            .group_by(Audit.query_type)
            .all()
        )
        findings_by_type = {t: c for t, c in type_rows}

        # Findings by opinion
        opinion_rows = (
            db.query(Audit.audit_opinion, func.count(Audit.id))
            .filter(Audit.audit_opinion.isnot(None))
            .group_by(Audit.audit_opinion)
            .all()
        )
        findings_by_opinion = {o: c for o, c in opinion_rows}

        # Worst counties by total flagged amount
        worst_rows = (
            db.query(
                Entity.id,
                Entity.canonical_name,
                func.coalesce(func.sum(Audit.amount), 0).label("total_amount"),
                func.count(Audit.id).label("finding_count"),
            )
            .join(Entity, Audit.entity_id == Entity.id)
            .filter(Audit.amount.isnot(None))
            .group_by(Entity.id, Entity.canonical_name)
            .order_by(desc("total_amount"))
            .limit(10)
            .all()
        )
        worst_counties = [
            WorstCounty(
                county_id=r[0],
                county_name=r[1],
                total_amount=float(r[2]),
                finding_count=r[3],
            )
            for r in worst_rows
        ]

        # Year range
        year_agg = db.query(
            func.min(Audit.audit_year), func.max(Audit.audit_year)
        ).first()
        year_range = YearRange(
            min_year=year_agg[0] if year_agg else None,
            max_year=year_agg[1] if year_agg else None,
        )

        return AuditSummaryResponse(
            total_irregular_expenditure=float(total_irregular),
            total_unsupported_expenditure=float(total_unsupported),
            total_findings=total_findings,
            findings_by_type=findings_by_type,
            findings_by_opinion=findings_by_opinion,
            worst_counties=worst_counties,
            year_range=year_range,
        )

    except OperationalError as e:
        logger.error("Database connection error: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")


@router.get("/trends", response_model=AuditTrendsResponse)
async def get_audit_trends(
    county_id: Optional[int] = Query(None, description="Filter by county entity ID"),
    query_type: Optional[str] = Query(None, description="Filter by query type"),
    db: Session = Depends(get_db),
):
    """Return year-over-year audit trend data."""
    _check_db(db)
    try:
        base = db.query(Audit).filter(Audit.audit_year.isnot(None))
        if county_id is not None:
            base = base.filter(Audit.entity_id == county_id)
        if query_type is not None:
            base = base.filter(Audit.query_type == query_type)

        rows = base.all()

        years_set = set()
        findings_per_year: Dict[int, int] = defaultdict(int)
        amount_per_year: Dict[int, float] = defaultdict(float)
        opinion_per_year: Dict[int, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        for r in rows:
            yr = r.audit_year
            years_set.add(yr)
            findings_per_year[yr] += 1
            if r.amount is not None:
                amount_per_year[yr] += float(r.amount)
            if r.audit_opinion:
                opinion_per_year[yr][r.audit_opinion] += 1

        years = sorted(years_set)

        return AuditTrendsResponse(
            years=years,
            findings_per_year={str(y): c for y, c in sorted(findings_per_year.items())},
            amount_per_year={str(y): a for y, a in sorted(amount_per_year.items())},
            opinion_per_year={
                str(y): dict(ops) for y, ops in sorted(opinion_per_year.items())
            },
        )

    except OperationalError as e:
        logger.error("Database connection error: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")


@router.get("/recurring", response_model=RecurringFindingsResponse)
async def get_recurring_findings(db: Session = Depends(get_db)):
    """Return findings flagged as recurring or appearing in 2+ years."""
    _check_db(db)
    try:
        # 1. Findings explicitly flagged as recurring
        flagged = (
            db.query(Audit)
            .join(Entity, Audit.entity_id == Entity.id)
            .filter(Audit.follow_up_status == "Recurring")
            .all()
        )

        # 2. Same county + query_type appearing in 2+ distinct years
        multi_year_keys = (
            db.query(Audit.entity_id, Audit.query_type)
            .filter(
                Audit.audit_year.isnot(None),
                Audit.query_type.isnot(None),
            )
            .group_by(Audit.entity_id, Audit.query_type)
            .having(func.count(func.distinct(Audit.audit_year)) >= 2)
            .all()
        )

        # Collect all relevant findings
        seen_keys = set()
        result_map: Dict[tuple, dict] = {}

        # Add flagged recurring
        for a in flagged:
            key = (a.entity_id, a.query_type or "Unknown")
            if key not in result_map:
                entity = db.query(Entity).get(a.entity_id)
                result_map[key] = {
                    "county_name": entity.canonical_name if entity else "Unknown",
                    "query_type": a.query_type or "Unknown",
                    "years": set(),
                    "amount": 0.0,
                    "ids": [],
                }
            if a.audit_year:
                result_map[key]["years"].add(a.audit_year)
            if a.amount:
                result_map[key]["amount"] += float(a.amount)
            result_map[key]["ids"].append(a.id)

        # Add multi-year findings (merge if already captured from flagged)
        for entity_id, qt in multi_year_keys:
            key = (entity_id, qt)
            findings = (
                db.query(Audit)
                .filter(
                    Audit.entity_id == entity_id,
                    Audit.query_type == qt,
                )
                .all()
            )
            entity = db.query(Entity).get(entity_id)
            if key not in result_map:
                result_map[key] = {
                    "county_name": entity.canonical_name if entity else "Unknown",
                    "query_type": qt,
                    "years": set(),
                    "amount": 0.0,
                    "ids": [],
                }
            entry = result_map[key]
            for f in findings:
                if f.audit_year:
                    entry["years"].add(f.audit_year)
                if f.amount:
                    # Avoid double-counting IDs already added from flagged pass
                    if f.id not in entry["ids"]:
                        entry["amount"] += float(f.amount)
                elif f.id not in entry["ids"]:
                    pass  # no amount to add
                if f.id not in entry["ids"]:
                    entry["ids"].append(f.id)

        recurring = [
            RecurringFinding(
                county_name=v["county_name"],
                query_type=v["query_type"],
                years_appeared=sorted(v["years"]),
                total_amount=v["amount"],
                finding_ids=v["ids"],
            )
            for v in result_map.values()
        ]

        return RecurringFindingsResponse(
            recurring_findings=recurring,
            total=len(recurring),
        )

    except OperationalError as e:
        logger.error("Database connection error: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")


@router.get("/findings", response_model=FindingsListResponse)
async def get_audit_findings(
    county_id: Optional[int] = Query(None, description="Filter by county entity ID"),
    year: Optional[int] = Query(None, description="Filter by audit year"),
    query_type: Optional[str] = Query(None, description="Filter by query type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    audit_opinion: Optional[str] = Query(None, description="Filter by audit opinion"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
):
    """Return paginated list of audit findings with filters."""
    _check_db(db)
    try:
        # Subquery: average confidence per source_document from extractions
        confidence_sub = (
            db.query(
                Extraction.source_document_id,
                func.avg(Extraction.confidence).label("avg_confidence"),
            )
            .group_by(Extraction.source_document_id)
            .subquery()
        )

        query = (
            db.query(
                Audit,
                Entity.canonical_name,
                SourceDocument.url.label("doc_url"),
                confidence_sub.c.avg_confidence,
            )
            .join(Entity, Audit.entity_id == Entity.id)
            .outerjoin(SourceDocument, Audit.source_document_id == SourceDocument.id)
            .outerjoin(
                confidence_sub,
                Audit.source_document_id == confidence_sub.c.source_document_id,
            )
        )

        if county_id is not None:
            query = query.filter(Audit.entity_id == county_id)
        if year is not None:
            query = query.filter(Audit.audit_year == year)
        if query_type is not None:
            query = query.filter(Audit.query_type == query_type)
        if severity is not None:
            query = query.filter(Audit.severity == severity)
        if audit_opinion is not None:
            query = query.filter(Audit.audit_opinion == audit_opinion)
        if status is not None:
            query = query.filter(Audit.status == status)

        total = query.count()
        offset = (page - 1) * limit
        rows = query.order_by(desc(Audit.audit_year), desc(Audit.id)).offset(offset).limit(limit).all()

        items = []
        for a, county_name, doc_url, avg_conf in rows:
            # Build source document URL: prefer external_reference, then doc URL
            source_url = None
            if a.external_reference:
                ref = a.external_reference.strip()
                if ref.startswith("http"):
                    source_url = ref
                else:
                    source_url = f"https://www.oagkenya.go.ke/wp-content/uploads/{ref}"
            elif doc_url:
                source_url = doc_url

            items.append(
                FindingDetail(
                    id=a.id,
                    entity_id=a.entity_id,
                    county_name=county_name,
                    period_id=a.period_id,
                    finding_text=a.finding_text,
                    severity=a.severity.value if hasattr(a.severity, "value") else str(a.severity),
                    recommended_action=a.recommended_action,
                    query_type=a.query_type,
                    amount=float(a.amount) if a.amount is not None else None,
                    status=a.status,
                    audit_opinion=a.audit_opinion,
                    audit_year=a.audit_year,
                    follow_up_status=a.follow_up_status,
                    external_reference=a.external_reference,
                    management_response=a.management_response,
                    source_document_url=source_url,
                    confidence_score=float(avg_conf) if avg_conf is not None else None,
                )
            )

        return FindingsListResponse(
            items=items,
            total=total,
            page=page,
            limit=limit,
        )

    except OperationalError as e:
        logger.error("Database connection error: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")

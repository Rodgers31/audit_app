"""
Admin API Router - Ingestion job monitoring and management.

Provides endpoints for:
- Viewing ingestion job history
- Checking job status and metrics
- Filtering jobs by domain, status, date range
"""

from datetime import datetime, timedelta, timezone
import logging
from time import monotonic
from typing import List, Optional

from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from models import IngestionJob, IngestionStatus
from pydantic import ConfigDict, BaseModel, Field
from sqlalchemy import case, desc, func, or_
from sqlalchemy.orm import Session

from supabase_auth import require_admin
from routers.admin_operations import (OperationsRoute, PRIVATE_HEADERS, bounded_domain, bounded_integer, error_count_expression, job_projection, private_operations_response)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Admin"],
    route_class=OperationsRoute,
    dependencies=[Depends(require_admin), Depends(private_operations_response)],
)


# Response models
class IngestionJobResponse(BaseModel):
    """Response model for a single ingestion job."""

    id: int
    domain: str
    status: str
    dry_run: bool
    started_at: datetime
    finished_at: Optional[datetime]
    duration_seconds: Optional[float]
    items_processed: int = Field(ge=0)
    items_created: int = Field(ge=0)
    items_updated: int = Field(ge=0)
    errors: list
    error_count: int
    diagnostics_redacted: bool
    metadata: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IngestionJobListResponse(BaseModel):
    """Paginated list of ingestion jobs."""

    jobs: List[IngestionJobResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class IngestionJobStatsResponse(BaseModel):
    """Summary statistics for ingestion jobs."""

    total_jobs: int
    completed: int
    failed: int
    running: int
    pending: int
    completed_with_errors: int
    total_items_processed: int
    total_items_created: int
    total_items_updated: int
    domains: dict  # domain -> count


@router.get(
    "/ingestion-jobs",
    response_model=IngestionJobListResponse,
    summary="List ingestion jobs",
)
async def list_ingestion_jobs(
    domain: Optional[str] = Query(None, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$", description="Filter by domain name"),
    status: Optional[str] = Query(None, max_length=32, description="Filter by status"),
    days: Optional[int] = Query(7, ge=1, le=365, description="Number of days to look back"),
    page: int = Query(1, ge=1, le=10000, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
):
    """
    List ingestion jobs with optional filters.

    Query parameters:
    - domain: Filter by specific domain (e.g., 'counties_budget', 'audits')
    - status: Filter by status (pending, running, completed, failed, completed_with_errors)
    - days: Number of days to look back (default: 7)
    - page: Page number for pagination (default: 1)
    - page_size: Number of items per page (default: 20, max: 100)

    Returns paginated list with job details including:
    - Job ID, domain, status, timing
    - Processing metrics (processed, created, updated)
    - Error information if any
    """
    bounded_integer(page, 1, 10000)
    bounded_integer(page_size, 1, 100)
    bounded_domain(domain)
    if days is not None:
        bounded_integer(days, 1, 365)
    # Build query
    query = db.query(IngestionJob)

    # Apply filters
    if domain:
        query = query.filter(IngestionJob.domain == domain)

    if status:
        try:
            status_enum = IngestionStatus[status.upper()]
            query = query.filter(IngestionJob.status == status_enum)
        except KeyError:
            raise HTTPException(
                status_code=400,
                detail="Invalid ingestion status", headers=PRIVATE_HEADERS,
            )

    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(IngestionJob.created_at >= cutoff)

    # Get total count
    total = query.with_entities(func.count(IngestionJob.id)).scalar()

    # Apply pagination and ordering
    jobs = (
        query.with_entities(
            IngestionJob.id, IngestionJob.domain, IngestionJob.status, IngestionJob.dry_run,
            IngestionJob.started_at, IngestionJob.finished_at, IngestionJob.items_processed,
            IngestionJob.items_created, IngestionJob.items_updated, IngestionJob.created_at,
            error_count_expression(db),
        ).order_by(desc(IngestionJob.started_at), desc(IngestionJob.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    job_responses = [IngestionJobResponse(**job_projection(job, error_count=job.error_count)) for job in jobs]

    return IngestionJobListResponse(
        jobs=job_responses,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.get(
    "/ingestion-jobs/{job_id}",
    response_model=IngestionJobResponse,
    summary="Get ingestion job details",
)
async def get_ingestion_job(
    job_id: int = Path(..., ge=1, le=2147483647),
    db: Session = Depends(get_db),
):
    """
    Get detailed information for a specific ingestion job.

    Returns:
    - Complete job information including status, metrics, errors
    - Timing information (started_at, finished_at, duration)
    - Processing results (items processed/created/updated)
    """
    bounded_integer(job_id, 1, 2147483647)
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found", headers=PRIVATE_HEADERS)
    errors = job.errors
    count = len(errors) if isinstance(errors, list) else (0 if errors is None else 1)
    return IngestionJobResponse(**job_projection(job, error_count=count, metadata=job.meta))



@router.get(
    "/ingestion-jobs/stats/summary",
    response_model=IngestionJobStatsResponse,
    summary="Get ingestion job statistics",
)
async def get_ingestion_stats(
    days: Optional[int] = Query(30, ge=1, le=365, description="Number of days to look back"),
    db: Session = Depends(get_db),
):
    """
    Get summary statistics for ingestion jobs.

    Query parameters:
    - days: Number of days to look back (default: 30)

    Returns:
    - Total jobs by status (completed, failed, running, etc.)
    - Total items processed, created, and updated
    - Breakdown by domain
    """
    started = monotonic()
    # Retain the existing direct-call None/0 and negative-window controls while
    # preventing overflow or bool-as-int inputs. HTTP accepts only 1..365 days.
    if days is not None:
        bounded_integer(days, -365, 365)
    # The response only needs counts and counters. Diagnostics and job metadata
    # stay in PostgreSQL instead of being downloaded for Python aggregation.
    query = db.query(
        IngestionJob.domain, IngestionJob.status,
        func.count(IngestionJob.id).label("job_count"),
        func.sum(IngestionJob.items_processed).label("items_processed"),
        func.sum(IngestionJob.items_created).label("items_created"),
        func.sum(IngestionJob.items_updated).label("items_updated"),
        func.sum(case((or_(IngestionJob.items_processed < 0, IngestionJob.items_created < 0,
            IngestionJob.items_updated < 0), 1), else_=0)).label("invalid_counters"),
    )
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(IngestionJob.created_at >= cutoff)

    rows = query.group_by(IngestionJob.domain, IngestionJob.status).all()

    # Calculate statistics
    stats = {
        "total_jobs": 0,
        "completed": 0,
        "failed": 0,
        "running": 0,
        "pending": 0,
        "completed_with_errors": 0,
        "total_items_processed": 0,
        "total_items_created": 0,
        "total_items_updated": 0,
        "domains": {},
    }

    for row in rows:
        if row.invalid_counters:
            raise HTTPException(status_code=503, detail="Operations data unavailable", headers=PRIVATE_HEADERS)
        stats["total_jobs"] += row.job_count
        stats[row.status.value] += row.job_count
        stats["total_items_processed"] += row.items_processed
        stats["total_items_created"] += row.items_created
        stats["total_items_updated"] += row.items_updated
        stats["domains"][row.domain] = stats["domains"].get(row.domain, 0) + row.job_count

    logger.info("ingestion_stats_compacted", extra={
        "result_rows": len(rows), "duration_ms": int((monotonic()-started)*1000),
    })

    return IngestionJobStatsResponse(**stats)

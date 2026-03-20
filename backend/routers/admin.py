"""
Admin API Router - Ingestion job monitoring and management.

Provides endpoints for:
- Viewing ingestion job history
- Checking job status and metrics
- Filtering jobs by domain, status, date range
"""

import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from models import IngestionJob, IngestionStatus
from pydantic import ConfigDict, BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

# Optional: Add authentication dependency
# Set ADMIN_API_AUTH_REQUIRED=true in production to enable authentication
_admin_dep = []
if os.getenv("ADMIN_API_AUTH_REQUIRED", "false").lower() == "true":
    try:
        from auth import require_roles

        _admin_dep = [Depends(require_roles(["admin"]))]
    except Exception:
        pass  # Auth module not available

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Admin"],
    dependencies=_admin_dep,
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
    items_processed: int
    items_created: int
    items_updated: int
    errors: list
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
    domain: Optional[str] = Query(None, description="Filter by domain name"),
    status: Optional[str] = Query(None, description="Filter by status"),
    days: Optional[int] = Query(7, description="Number of days to look back"),
    page: int = Query(1, ge=1, description="Page number"),
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
                detail=f"Invalid status: {status}. Valid values: {[s.value for s in IngestionStatus]}",
            )

    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(IngestionJob.created_at >= cutoff)

    # Get total count
    total = query.count()

    # Apply pagination and ordering
    jobs = (
        query.order_by(desc(IngestionJob.started_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Calculate duration for each job
    job_responses = []
    for job in jobs:
        duration_seconds = None
        if job.finished_at and job.started_at:
            duration_seconds = (job.finished_at - job.started_at).total_seconds()

        job_responses.append(
            IngestionJobResponse(
                id=job.id,
                domain=job.domain,
                status=job.status.value,
                dry_run=job.dry_run,
                started_at=job.started_at,
                finished_at=job.finished_at,
                duration_seconds=duration_seconds,
                items_processed=job.items_processed,
                items_created=job.items_created,
                items_updated=job.items_updated,
                errors=job.errors or [],
                metadata=job.meta or {},
                created_at=job.created_at,
            )
        )

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
    job_id: int,
    db: Session = Depends(get_db),
):
    """
    Get detailed information for a specific ingestion job.

    Returns:
    - Complete job information including status, metrics, errors
    - Timing information (started_at, finished_at, duration)
    - Processing results (items processed/created/updated)
    """
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail=f"Ingestion job {job_id} not found")

    duration_seconds = None
    if job.finished_at and job.started_at:
        duration_seconds = (job.finished_at - job.started_at).total_seconds()

    return IngestionJobResponse(
        id=job.id,
        domain=job.domain,
        status=job.status.value,
        dry_run=job.dry_run,
        started_at=job.started_at,
        finished_at=job.finished_at,
        duration_seconds=duration_seconds,
        items_processed=job.items_processed,
        items_created=job.items_created,
        items_updated=job.items_updated,
        errors=job.errors or [],
        metadata=job.meta or {},
        created_at=job.created_at,
    )


@router.get(
    "/ingestion-jobs/stats/summary",
    response_model=IngestionJobStatsResponse,
    summary="Get ingestion job statistics",
)
async def get_ingestion_stats(
    days: Optional[int] = Query(30, description="Number of days to look back"),
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
    # Build query with date filter
    query = db.query(IngestionJob)
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.filter(IngestionJob.created_at >= cutoff)

    jobs = query.all()

    # Calculate statistics
    stats = {
        "total_jobs": len(jobs),
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

    for job in jobs:
        # Count by status
        if job.status == IngestionStatus.COMPLETED:
            stats["completed"] += 1
        elif job.status == IngestionStatus.FAILED:
            stats["failed"] += 1
        elif job.status == IngestionStatus.RUNNING:
            stats["running"] += 1
        elif job.status == IngestionStatus.PENDING:
            stats["pending"] += 1
        elif job.status == IngestionStatus.COMPLETED_WITH_ERRORS:
            stats["completed_with_errors"] += 1

        # Sum metrics
        stats["total_items_processed"] += job.items_processed
        stats["total_items_created"] += job.items_created
        stats["total_items_updated"] += job.items_updated

        # Count by domain
        stats["domains"][job.domain] = stats["domains"].get(job.domain, 0) + 1

    return IngestionJobStatsResponse(**stats)

"""
Data Freshness Router — reports how recent each data source is.

GET /api/v1/data/freshness
"""

import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from database import get_db
    from models import IngestionJob, IngestionStatus, SourceDocument

    DATABASE_AVAILABLE = True
except Exception:
    DATABASE_AVAILABLE = False

    def get_db():
        return None


router = APIRouter(prefix="/api/v1/data", tags=["Data Quality"])
logger = logging.getLogger(__name__)


# ── response models ──────────────────────────────────────────────

class SourceFreshness(BaseModel):
    source: str
    label: str
    last_updated: Optional[str] = None
    covers_through: Optional[str] = None
    update_frequency: str
    status: str  # fresh | stale | outdated


class FreshnessResponse(BaseModel):
    sources: List[SourceFreshness]


# ── source config (static metadata) ─────────────────────────────

SOURCE_CONFIG = [
    {
        "source": "COB",
        "label": "Controller of Budget",
        "publisher_pattern": "Controller of Budget",
        "domain": "budget",
        "covers_through": "Q2 FY2024/25",
        "update_frequency": "Quarterly",
    },
    {
        "source": "OAG",
        "label": "Office of the Auditor General",
        "publisher_pattern": "Auditor General",
        "domain": "audit",
        "covers_through": "FY2022/23",
        "update_frequency": "Annually",
    },
    {
        "source": "KNBS",
        "label": "Kenya National Bureau of Statistics",
        "publisher_pattern": "KNBS",
        "domain": "economic",
        "covers_through": "2024",
        "update_frequency": "Annually",
    },
    {
        "source": "Treasury",
        "label": "National Treasury",
        "publisher_pattern": "Treasury",
        "domain": "debt",
        "covers_through": "Q2 FY2024/25",
        "update_frequency": "Quarterly",
    },
    {
        "source": "CBK",
        "label": "Central Bank of Kenya",
        "publisher_pattern": "Central Bank",
        "domain": "debt",
        "covers_through": "Feb 2025",
        "update_frequency": "Monthly",
    },
    {
        "source": "CRA",
        "label": "Commission on Revenue Allocation",
        "publisher_pattern": "CRA",
        "domain": "budget",
        "covers_through": "FY2024/25",
        "update_frequency": "Annually",
    },
]


def _freshness_status(last_updated: Optional[date]) -> str:
    """fresh = <45 days, stale = 45-180 days, outdated = >180 days."""
    if last_updated is None:
        return "outdated"
    delta = (date.today() - last_updated).days
    if delta < 45:
        return "fresh"
    if delta <= 180:
        return "stale"
    return "outdated"


@router.get("/freshness", response_model=FreshnessResponse)
async def get_data_freshness(db: Session = Depends(get_db)):
    """Return freshness information for each data source."""

    results: List[SourceFreshness] = []

    for cfg in SOURCE_CONFIG:
        last_updated_date: Optional[date] = None

        if DATABASE_AVAILABLE and db is not None:
            # Try IngestionJob first (most accurate)
            # Use the IngestionStatus enum values (not plain strings) to match the column type
            job = (
                db.query(func.max(IngestionJob.finished_at))
                .filter(
                    IngestionJob.domain.ilike(f"%{cfg['domain']}%"),
                    IngestionJob.status.in_([
                        IngestionStatus.COMPLETED,
                        IngestionStatus.COMPLETED_WITH_ERRORS,
                    ]),
                )
                .scalar()
            )
            if job:
                last_updated_date = job.date() if isinstance(job, datetime) else job

            # Fallback to SourceDocument fetch_date
            if last_updated_date is None:
                doc_date = (
                    db.query(func.max(SourceDocument.fetch_date))
                    .filter(
                        SourceDocument.publisher.ilike(
                            f"%{cfg['publisher_pattern']}%"
                        )
                    )
                    .scalar()
                )
                if doc_date:
                    last_updated_date = (
                        doc_date.date()
                        if isinstance(doc_date, datetime)
                        else doc_date
                    )

        results.append(
            SourceFreshness(
                source=cfg["source"],
                label=cfg["label"],
                last_updated=(
                    last_updated_date.isoformat() if last_updated_date else None
                ),
                covers_through=cfg["covers_through"],
                update_frequency=cfg["update_frequency"],
                status=_freshness_status(last_updated_date),
            )
        )

    return FreshnessResponse(sources=results)

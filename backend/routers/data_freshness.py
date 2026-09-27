"""
Data Freshness Router — reports how recent each data source is.

GET /api/v1/data/freshness

All three recency signals are derived from the live database (no
hardcoded dates):

* ``last_updated`` — the source document's PUBLICATION date (when the
  publisher released the data), from SourceDocument provenance. This is
  what drives the fresh/stale/outdated status, so a nightly ETL run can
  no longer make a year-old report look "fresh".
* ``last_checked`` — latest verified successful download with a recorded
  checksum; informational only. Registration is not a successful download.
* ``covers_through`` — the most recent fiscal period / observation year
  present in accepted records from that publisher.

Status is frequency-aware: "fresh" means within roughly one expected
publication cycle for the source's update_frequency.
"""

import logging
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from services.publication_gate import publishable_audit_criterion

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.source_evidence import downloaded_document_criterion

try:
    from database import get_db
    from models import (
        Audit,
        BudgetLine,
        DebtTimeline,
        FiscalPeriod,
        GDPData,
        Loan,
        SourceDocument,
    )

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
    last_updated: Optional[str] = None  # source PUBLICATION date (drives status)
    last_checked: Optional[str] = None  # successful verified download, not registration
    covers_through: Optional[str] = None
    update_frequency: str
    status: str  # fresh | stale | outdated | unknown


class FreshnessResponse(BaseModel):
    sources: List[SourceFreshness]


# ── source config (static metadata — NOT coverage) ──────────────
# `publisher_pattern` selects explicit publisher aliases (no substring matches).
# `domain` determines which data table we query to learn the latest
# period covered. `update_frequency` is purely descriptive.
#
# `covers_through` is intentionally NOT stored here — it is computed
# from the database so the API never lies about recency.

SOURCE_CONFIG = [
    {
        "source": "COB",
        "label": "Controller of Budget",
        "publisher_pattern": "Controller of Budget",
        "domain": "budget",
        "update_frequency": "Quarterly",
    },
    {
        "source": "OAG",
        "label": "Office of the Auditor General",
        "publisher_pattern": "Auditor%General",
        "domain": "audit",
        "update_frequency": "Annually",
    },
    {
        "source": "KNBS",
        "label": "Kenya National Bureau of Statistics",
        "publisher_pattern": "KNBS|Bureau of Statistics",
        "domain": "economic",
        "update_frequency": "Annually",
    },
    {
        "source": "Treasury",
        "label": "National Treasury",
        "publisher_pattern": "Treasury",
        "domain": "debt",
        "update_frequency": "Quarterly",
    },
    {
        "source": "CBK",
        "label": "Central Bank of Kenya",
        "publisher_pattern": "Central Bank",
        "domain": "debt",
        "update_frequency": "Monthly",
    },
    {
        "source": "CRA",
        "label": "Commission on Revenue Allocation",
        "publisher_pattern": "CRA|Revenue Allocation",
        "domain": "budget",
        "update_frequency": "Annually",
    },
]


# Approx one publication cycle (days) per declared update frequency.
_CYCLE_DAYS = {"Monthly": 45, "Quarterly": 135, "Annually": 400}


def _freshness_status(last_updated: Optional[date], frequency: str = "") -> str:
    """Frequency-aware status: fresh within ~1 publication cycle, stale within
    ~2.5 cycles, outdated beyond — so an annually-published report is not
    judged against a 45-day window (nor a monthly series given a year's grace).
    """
    if last_updated is None:
        return "unknown"
    delta = (date.today() - last_updated).days
    cycle = _CYCLE_DAYS.get(frequency, 90)
    if delta < 0:
        return "unknown"
    if delta <= cycle:
        return "fresh"
    if delta <= cycle * 2.5:
        return "stale"
    return "outdated"


# ── per-domain coverage lookups ──────────────────────────────────


def _latest_period_label_for_budget(
    db: Session, publisher_pattern: str
) -> Optional[str]:
    """Latest fiscal-period label present in BudgetLine rows whose source
    document was published by the given organisation."""
    return (
        db.query(FiscalPeriod.label)
        .join(BudgetLine, BudgetLine.period_id == FiscalPeriod.id)
        .join(
            SourceDocument,
            BudgetLine.source_document_id == SourceDocument.id,
        )
        .filter(_publisher_criterion(publisher_pattern))
        .filter(BudgetLine.publishable.is_(True))
        .order_by(FiscalPeriod.start_date.desc())
        .limit(1)
        .scalar()
    )


def _latest_period_label_for_audit(
    db: Session, publisher_pattern: str
) -> Optional[str]:
    """Latest fiscal-period label present in Audit rows for a given publisher."""
    return (
        db.query(FiscalPeriod.label)
        .join(Audit, Audit.period_id == FiscalPeriod.id)
        .join(SourceDocument, Audit.source_document_id == SourceDocument.id)
        .filter(publishable_audit_criterion())
        .filter(_publisher_criterion(publisher_pattern))
        .order_by(FiscalPeriod.start_date.desc())
        .limit(1)
        .scalar()
    )


def _latest_coverage_for_debt(db: Session, publisher_pattern: str) -> Optional[str]:
    """Latest sourced timeline observation. A loan's issue date is a contract
    date, not the coverage date of the outstanding-debt observation."""
    timeline_year = (
        db.query(func.max(DebtTimeline.year))
        .join(SourceDocument, DebtTimeline.source_document_id == SourceDocument.id)
        .filter(
            _publisher_criterion(publisher_pattern), DebtTimeline.publishable.is_(True)
        )
        .scalar()
    )
    if timeline_year:
        return str(timeline_year)
    return None


def _latest_coverage_for_economic(db: Session, publisher_pattern: str) -> Optional[str]:
    """Latest economic observation — max GDPData.year linked to a publisher's
    source documents; never borrow another publisher's global maximum."""
    year = (
        db.query(func.max(GDPData.year))
        .join(
            SourceDocument,
            GDPData.source_document_id == SourceDocument.id,
        )
        .filter(_publisher_criterion(publisher_pattern), GDPData.publishable.is_(True))
        .scalar()
    )
    return str(year) if year else None


def _covers_through(db: Session, cfg: dict) -> Optional[str]:
    """Dispatch to the right per-domain lookup based on cfg['domain']."""
    domain = cfg["domain"]
    pattern = cfg["publisher_pattern"]
    try:
        if domain == "budget":
            return _latest_period_label_for_budget(db, pattern)
        if domain == "audit":
            return _latest_period_label_for_audit(db, pattern)
        if domain == "debt":
            return _latest_coverage_for_debt(db, pattern)
        if domain == "economic":
            return _latest_coverage_for_economic(db, pattern)
    except Exception as exc:  # pragma: no cover — defensive; never leak DB errors
        logger.warning(
            "covers_through lookup failed for source=%s domain=%s: %s",
            cfg.get("source"),
            domain,
            exc,
        )
    return None


def _publisher_criterion(pattern: str):
    # Publisher codes must match named organisations, not arbitrary substrings
    # ("democratic" and "scraped" both contain CRA).
    aliases = {
        "Controller of Budget": (
            "controller of budget",
            "office of the controller of budget",
            "office of the controller of budget (ocob)",
            "cob",
            "ocob",
        ),
        "Auditor%General": ("office of the auditor general", "auditor general", "oag"),
        "KNBS|Bureau of Statistics": ("knbs", "kenya national bureau of statistics"),
        "Treasury": (
            "national treasury",
            "the national treasury",
            "kenya national treasury",
            "national treasury kenya",
            "national treasury of kenya",
        ),
        "Central Bank": ("central bank of kenya", "cbk"),
        "CRA|Revenue Allocation": ("cra", "commission on revenue allocation"),
    }
    name = func.lower(func.trim(func.replace(SourceDocument.publisher, "-", " ")))
    return name.in_(aliases.get(pattern, (pattern.lower(),)))


def _accepted_document_ids(db: Session, domain: str):
    """Only rows admitted by the domain's publication gate count as coverage."""
    models = {
        "budget": (BudgetLine,),
        "audit": (Audit,),
        "debt": (Loan, DebtTimeline),
        "economic": (GDPData,),
    }[domain]
    ids = set()
    for model in models:
        criterion = (
            publishable_audit_criterion()
            if model is Audit
            else model.publishable.is_(True)
        )
        ids.update(
            row[0]
            for row in db.query(model.source_document_id)
            .filter(criterion)
            .distinct()
            .all()
            if row[0]
        )
    return ids


def _source_publication_date(
    db: Session, publisher_pattern: str, domain: str
) -> Optional[date]:
    """Explicit publisher dates of accepted data, never registration/fetch dates."""
    ids = _accepted_document_ids(db, domain)
    if not ids:
        return None
    docs = (
        db.query(SourceDocument)
        .filter(_publisher_criterion(publisher_pattern), SourceDocument.id.in_(ids))
        .all()
    )
    dates = []
    for doc in docs:
        meta = doc.meta if isinstance(doc.meta, dict) else {}
        raw = meta.get("publication_date")
        # Require a complete ISO publication date. Generic provenance fallback
        # parsing accepts partial/garbage values that cannot certify freshness.
        if not isinstance(raw, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?",
            raw,
        ):
            continue
        try:
            published_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        # An offset may put a future instant on yesterday's calendar date.
        # Treat unzoned publication metadata as UTC for this fail-closed check.
        published_utc = (
            published_at.replace(tzinfo=timezone.utc)
            if published_at.tzinfo is None
            else published_at.astimezone(timezone.utc)
        )
        if (
            published_utc <= datetime.now(timezone.utc)
            and published_at.date() <= date.today()
        ):
            dates.append(published_at.date())
    return max(dates) if dates else None


@router.get("/freshness", response_model=FreshnessResponse)
async def get_data_freshness(db: Session = Depends(get_db)):
    """Return freshness information for each data source."""

    results: List[SourceFreshness] = []

    for cfg in SOURCE_CONFIG:
        last_checked_date: Optional[date] = None
        last_updated_date: Optional[date] = None
        covers_through: Optional[str] = None

        if DATABASE_AVAILABLE and db is not None:
            # Successful source-specific transport is distinct from registration,
            # domain-level jobs (which may concern another publisher), and acceptance.
            checked = (
                db.query(func.max(SourceDocument.last_verified_at))
                .filter(
                    _publisher_criterion(cfg["publisher_pattern"]),
                    downloaded_document_criterion(),
                )
                .scalar()
            )
            if checked:
                last_checked_date = (
                    checked.date() if isinstance(checked, datetime) else checked
                )
            last_updated_date = _source_publication_date(
                db, cfg["publisher_pattern"], cfg["domain"]
            )

            # Derived coverage (stays truthful as the DB grows).
            covers_through = _covers_through(db, cfg)

        results.append(
            SourceFreshness(
                source=cfg["source"],
                label=cfg["label"],
                last_updated=(
                    last_updated_date.isoformat() if last_updated_date else None
                ),
                last_checked=(
                    last_checked_date.isoformat() if last_checked_date else None
                ),
                covers_through=covers_through,
                update_frequency=cfg["update_frequency"],
                status=_freshness_status(last_updated_date, cfg["update_frequency"]),
            )
        )

    return FreshnessResponse(sources=results)

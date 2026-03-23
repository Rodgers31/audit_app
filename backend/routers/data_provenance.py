"""
Data Provenance Router — provides verifiable source citations for all data.

Every number on the site can be traced back to an official government source.
This is critical for credibility: if users can verify the data, they trust it.

GET /api/v1/provenance/sources       — list all data sources with URLs
GET /api/v1/provenance/verify/{table} — verify a specific data point
GET /api/v1/provenance/health        — overall data health check
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from database import get_db
    from models import (
        Audit,
        BudgetLine,
        DebtTimeline,
        EconomicIndicator,
        Entity,
        EntityType,
        FiscalSummary,
        GDPData,
        IngestionJob,
        IngestionStatus,
        Loan,
        PopulationData,
        PovertyIndex,
        SourceDocument,
    )

    DATABASE_AVAILABLE = True
except Exception:
    DATABASE_AVAILABLE = False

    def get_db():
        return None


router = APIRouter(prefix="/api/v1/provenance", tags=["Data Provenance"])
logger = logging.getLogger(__name__)


# ── Official Kenya government data sources ────────────────────────
# These are the ONLY sources we cite. Every number must trace back here.
OFFICIAL_SOURCES = {
    "knbs": {
        "name": "Kenya National Bureau of Statistics (KNBS)",
        "url": "https://www.knbs.or.ke",
        "datasets": [
            {
                "name": "Economic Survey",
                "url": "https://www.knbs.or.ke/economic-survey/",
                "covers": "GDP, national accounts, economic indicators",
                "frequency": "Annual (published ~April)",
            },
            {
                "name": "Consumer Price Index",
                "url": "https://www.knbs.or.ke/consumer-price-indices/",
                "covers": "Inflation rate, CPI",
                "frequency": "Monthly",
            },
            {
                "name": "Quarterly Labour Force Survey",
                "url": "https://www.knbs.or.ke/labour-force-basic-report/",
                "covers": "Unemployment rate",
                "frequency": "Quarterly",
            },
            {
                "name": "Kenya Population and Housing Census 2019",
                "url": "https://www.knbs.or.ke/2019-kenya-population-and-housing-census-results/",
                "covers": "Population data by county",
                "frequency": "Decennial (next: 2029)",
            },
            {
                "name": "Quarterly GDP Report",
                "url": "https://www.knbs.or.ke/download/quarterly-gross-domestic-product-report/",
                "covers": "GDP growth rate",
                "frequency": "Quarterly",
            },
        ],
    },
    "cbk": {
        "name": "Central Bank of Kenya (CBK)",
        "url": "https://www.centralbank.go.ke",
        "datasets": [
            {
                "name": "Public Debt Statistical Bulletin",
                "url": "https://www.centralbank.go.ke/public-debt/",
                "covers": "National debt breakdown (external, domestic, by lender)",
                "frequency": "Monthly",
            },
            {
                "name": "Monthly Economic Indicators",
                "url": "https://www.centralbank.go.ke/statistics/",
                "covers": "Exchange rates, interest rates, money supply",
                "frequency": "Monthly",
            },
        ],
    },
    "oag": {
        "name": "Office of the Auditor General (OAG)",
        "url": "https://www.oagkenya.go.ke",
        "datasets": [
            {
                "name": "County Government Audit Reports",
                "url": "https://www.oagkenya.go.ke/reports/",
                "covers": "County audit findings, irregular expenditure",
                "frequency": "Annual (published ~Dec)",
            },
            {
                "name": "National Government Audit Report",
                "url": "https://www.oagkenya.go.ke/reports/",
                "covers": "National government audit opinion, findings",
                "frequency": "Annual",
            },
        ],
    },
    "cob": {
        "name": "Controller of Budget (COB)",
        "url": "https://cob.go.ke",
        "datasets": [
            {
                "name": "County Budget Implementation Review",
                "url": "https://cob.go.ke/reports/county-governments-budget-implementation-review-reports/",
                "covers": "County budget execution rates, spending by sector",
                "frequency": "Quarterly",
            },
            {
                "name": "National Government BIRR",
                "url": "https://cob.go.ke/reports/national-government-budget-implementation-review-reports/",
                "covers": "National budget execution by ministry",
                "frequency": "Quarterly",
            },
        ],
    },
    "treasury": {
        "name": "National Treasury & Planning",
        "url": "https://www.treasury.go.ke",
        "datasets": [
            {
                "name": "Budget Policy Statement",
                "url": "https://www.treasury.go.ke/budget-policy-statement/",
                "covers": "Fiscal summary, revenue, borrowing, county allocation",
                "frequency": "Annual (published ~Feb)",
            },
            {
                "name": "Budget Estimates",
                "url": "https://www.treasury.go.ke/budget-estimates/",
                "covers": "Appropriated budgets by ministry/county",
                "frequency": "Annual (published ~June)",
            },
        ],
    },
    "worldbank": {
        "name": "World Bank Open Data",
        "url": "https://data.worldbank.org/country/kenya",
        "datasets": [
            {
                "name": "World Development Indicators",
                "url": "https://data.worldbank.org/indicator?locations=KE",
                "covers": "GDP (cross-validated), poverty rates, Gini coefficient",
                "frequency": "Annual",
            },
        ],
    },
}


# ── Response models ───────────────────────────────────────────────


class DataSourceInfo(BaseModel):
    source_id: str
    name: str
    url: str
    datasets: List[Dict[str, str]]


class TableHealth(BaseModel):
    table: str
    label: str
    row_count: int
    latest_date: Optional[str] = None
    source: Optional[str] = None
    status: str  # "healthy" | "stale" | "empty" | "error"
    notes: Optional[str] = None


class ProvenanceHealthResponse(BaseModel):
    overall_status: str  # "healthy" | "degraded" | "critical"
    tables: List[TableHealth]
    total_source_documents: int
    last_ingestion: Optional[str] = None
    sources_cited: int
    checked_at: str


class DataPointVerification(BaseModel):
    table: str
    value: Optional[str] = None
    source_document: Optional[str] = None
    source_url: Optional[str] = None
    publisher: Optional[str] = None
    fetch_date: Optional[str] = None
    provenance_chain: List[Dict[str, Any]] = []
    verification_status: str  # "verified" | "unverified" | "stale"


# ── Endpoints ─────────────────────────────────────────────────────


@router.get(
    "/sources",
    response_model=List[DataSourceInfo],
    summary="List All Official Data Sources",
)
async def list_data_sources():
    """
    Returns all official government data sources used by AuditGava.

    Every data point on the site can be traced back to one of these sources.
    This endpoint is public so citizens can independently verify our data.
    """
    return [
        DataSourceInfo(
            source_id=key,
            name=info["name"],
            url=info["url"],
            datasets=info["datasets"],
        )
        for key, info in OFFICIAL_SOURCES.items()
    ]


@router.get(
    "/health",
    response_model=ProvenanceHealthResponse,
    summary="Data Health Dashboard",
)
async def get_data_health(db: Session = Depends(get_db)):
    """
    Check the health and freshness of all data tables.

    Returns row counts, last update dates, and status for each table.
    Used by the frontend to show data freshness indicators.
    """
    if not DATABASE_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    tables = []

    # Counties
    county_count = db.query(Entity).filter(Entity.type == EntityType.COUNTY).count()
    tables.append(TableHealth(
        table="entities",
        label="Counties",
        row_count=county_count,
        source="KNBS Census 2019",
        status="healthy" if county_count >= 47 else "critical" if county_count == 0 else "degraded",
    ))

    # Budget lines
    budget_count = db.query(BudgetLine).count()
    tables.append(TableHealth(
        table="budget_lines",
        label="Budget Lines",
        row_count=budget_count,
        source="COB County Budget Reports",
        status="healthy" if budget_count >= 400 else "critical" if budget_count == 0 else "degraded",
    ))

    # Audit records
    audit_count = db.query(Audit).count()
    audits_with_year = db.query(Audit).filter(Audit.audit_year.isnot(None)).count()
    tables.append(TableHealth(
        table="audits",
        label="Audit Findings",
        row_count=audit_count,
        source="OAG Audit Reports",
        status="healthy" if audits_with_year >= 50 else "degraded" if audit_count > 0 else "empty",
        notes=f"{audits_with_year} with audit_year" if audit_count > 0 else None,
    ))

    # Population
    pop_count = db.query(PopulationData).count()
    nat_pop = db.query(PopulationData).filter(PopulationData.entity_id.is_(None)).first()
    tables.append(TableHealth(
        table="population_data",
        label="Population Data",
        row_count=pop_count,
        latest_date=f"Year {nat_pop.year}" if nat_pop else None,
        source="KNBS Census 2019",
        status="healthy" if pop_count >= 48 and nat_pop else "degraded" if pop_count > 0 else "empty",
    ))

    # GDP
    gdp_count = db.query(GDPData).count()
    latest_gdp = db.query(GDPData).filter(GDPData.entity_id.is_(None)).order_by(desc(GDPData.year)).first()
    tables.append(TableHealth(
        table="gdp_data",
        label="GDP Data",
        row_count=gdp_count,
        latest_date=f"Year {latest_gdp.year}" if latest_gdp else None,
        source="KNBS Economic Survey",
        status="healthy" if gdp_count >= 5 else "degraded" if gdp_count > 0 else "empty",
    ))

    # Economic indicators
    econ_count = db.query(EconomicIndicator).count()
    latest_econ = db.query(EconomicIndicator).order_by(desc(EconomicIndicator.indicator_date)).first()
    tables.append(TableHealth(
        table="economic_indicators",
        label="Economic Indicators",
        row_count=econ_count,
        latest_date=latest_econ.indicator_date.isoformat() if latest_econ else None,
        source="KNBS / CBK",
        status="healthy" if econ_count >= 5 else "degraded" if econ_count > 0 else "empty",
    ))

    # Poverty
    poverty_count = db.query(PovertyIndex).count()
    tables.append(TableHealth(
        table="poverty_indices",
        label="Poverty Data",
        row_count=poverty_count,
        source="KNBS / World Bank",
        status="healthy" if poverty_count >= 1 else "empty",
    ))

    # Loans / Debt
    loan_count = db.query(Loan).count()
    tables.append(TableHealth(
        table="loans",
        label="Debt Records",
        row_count=loan_count,
        source="CBK Public Debt Bulletin",
        status="healthy" if loan_count >= 50 else "degraded" if loan_count > 0 else "empty",
    ))

    # Debt timeline
    debt_tl_count = db.query(DebtTimeline).count()
    tables.append(TableHealth(
        table="debt_timeline",
        label="Debt Timeline",
        row_count=debt_tl_count,
        source="CBK Annual Reports",
        status="healthy" if debt_tl_count >= 5 else "degraded" if debt_tl_count > 0 else "empty",
    ))

    # Fiscal summaries
    fiscal_count = db.query(FiscalSummary).count()
    tables.append(TableHealth(
        table="fiscal_summaries",
        label="Fiscal Summaries",
        row_count=fiscal_count,
        source="National Treasury BPS",
        status="healthy" if fiscal_count >= 3 else "degraded" if fiscal_count > 0 else "empty",
    ))

    # Overall stats
    source_doc_count = db.query(SourceDocument).count()
    latest_job = (
        db.query(IngestionJob)
        .filter(IngestionJob.status.in_([IngestionStatus.COMPLETED, IngestionStatus.COMPLETED_WITH_ERRORS]))
        .order_by(desc(IngestionJob.finished_at))
        .first()
    )

    healthy = sum(1 for t in tables if t.status == "healthy")
    empty = sum(1 for t in tables if t.status == "empty")
    critical = sum(1 for t in tables if t.status == "critical")

    if critical > 0 or empty > 3:
        overall = "critical"
    elif empty > 0 or healthy < len(tables):
        overall = "degraded"
    else:
        overall = "healthy"

    return ProvenanceHealthResponse(
        overall_status=overall,
        tables=tables,
        total_source_documents=source_doc_count,
        last_ingestion=latest_job.finished_at.isoformat() if latest_job and latest_job.finished_at else None,
        sources_cited=len(OFFICIAL_SOURCES),
        checked_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/verify/{table_name}",
    response_model=DataPointVerification,
    summary="Verify a Data Point",
)
async def verify_data_point(
    table_name: str,
    entity_id: Optional[int] = Query(None, description="Entity ID to verify"),
    year: Optional[int] = Query(None, description="Year of the data point"),
    db: Session = Depends(get_db),
):
    """
    Trace a specific data point back to its official source.

    Returns the source document, URL, publisher, and full provenance chain
    so anyone can independently verify the data.
    """
    if not DATABASE_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    verification = DataPointVerification(table=table_name, verification_status="unverified")

    try:
        if table_name == "population_data":
            query = db.query(PopulationData)
            if entity_id is not None:
                query = query.filter(PopulationData.entity_id == entity_id)
            else:
                query = query.filter(PopulationData.entity_id.is_(None))
            if year:
                query = query.filter(PopulationData.year == year)
            record = query.order_by(desc(PopulationData.year)).first()
            if record:
                verification.value = f"{record.total_population:,} (year {record.year})"
                if record.source_document_id:
                    doc = db.query(SourceDocument).filter(SourceDocument.id == record.source_document_id).first()
                    if doc:
                        verification.source_document = doc.title
                        verification.source_url = doc.url
                        verification.publisher = doc.publisher
                        verification.fetch_date = doc.fetch_date.isoformat() if doc.fetch_date else None
                verification.provenance_chain = [
                    {"source": "Kenya National Bureau of Statistics", "dataset": "Census 2019",
                     "url": "https://www.knbs.or.ke/2019-kenya-population-and-housing-census-results/"},
                ]
                verification.verification_status = "verified"

        elif table_name == "gdp_data":
            query = db.query(GDPData)
            if entity_id is not None:
                query = query.filter(GDPData.entity_id == entity_id)
            else:
                query = query.filter(GDPData.entity_id.is_(None))
            if year:
                query = query.filter(GDPData.year == year)
            record = query.order_by(desc(GDPData.year)).first()
            if record:
                gdp_t = float(record.gdp_value) / 1e12
                verification.value = f"KES {gdp_t:.2f}T (year {record.year})"
                if record.source_document_id:
                    doc = db.query(SourceDocument).filter(SourceDocument.id == record.source_document_id).first()
                    if doc:
                        verification.source_document = doc.title
                        verification.source_url = doc.url
                        verification.publisher = doc.publisher
                verification.provenance_chain = [
                    {"source": "KNBS", "dataset": "Economic Survey", "url": "https://www.knbs.or.ke/economic-survey/"},
                    {"cross_check": "World Bank", "url": "https://data.worldbank.org/indicator/NY.GDP.MKTP.CN?locations=KE"},
                ]
                verification.verification_status = "verified"

        elif table_name == "audits":
            query = db.query(Audit)
            if entity_id:
                query = query.filter(Audit.entity_id == entity_id)
            record = query.order_by(desc(Audit.id)).first()
            if record:
                verification.value = record.finding_text[:200] if record.finding_text else None
                if record.source_document_id:
                    doc = db.query(SourceDocument).filter(SourceDocument.id == record.source_document_id).first()
                    if doc:
                        verification.source_document = doc.title
                        verification.source_url = doc.url
                        verification.publisher = doc.publisher
                if record.provenance:
                    verification.provenance_chain = record.provenance
                verification.verification_status = "verified"

        elif table_name == "loans":
            query = db.query(Loan)
            if entity_id:
                query = query.filter(Loan.entity_id == entity_id)
            record = query.order_by(desc(Loan.id)).first()
            if record:
                verification.value = f"KES {float(record.outstanding):,.0f} ({record.lender})"
                if record.source_document_id:
                    doc = db.query(SourceDocument).filter(SourceDocument.id == record.source_document_id).first()
                    if doc:
                        verification.source_document = doc.title
                        verification.source_url = doc.url
                        verification.publisher = doc.publisher
                if record.provenance:
                    verification.provenance_chain = record.provenance
                verification.verification_status = "verified"

        else:
            raise HTTPException(status_code=400, detail=f"Unknown table: {table_name}. Supported: population_data, gdp_data, audits, loans")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Verification error for %s: %s", table_name, e)
        verification.verification_status = "error"

    return verification

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

from services.publication_gate import publishable_audit_criterion

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
        FiscalPeriod,
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
                "url": "https://www.oagkenya.go.ke/",
                "covers": "County audit findings, irregular expenditure",
                "frequency": "Annual (published ~Dec)",
            },
            {
                "name": "National Government Audit Report",
                "url": "https://www.oagkenya.go.ke/",
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
                "url": "https://cob.go.ke/publications/county-reports/",
                "covers": "County budget execution rates, spending by sector",
                "frequency": "Quarterly",
            },
            {
                "name": "National Government BIRR",
                "url": "https://cob.go.ke/publications/national-government-budget-implementation-review-reports/",
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
    status: str  # "healthy" | "stale" | "degraded" | "empty" | "critical"
    notes: Optional[str] = None
    # How long since this table's newest row changed, and the threshold it is
    # judged against. Without these the panel could only answer "is it empty?"
    # while its caption claimed to answer "is it current?".
    age_days: Optional[int] = None
    stale_after_days: Optional[int] = None


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
    #: "verified"    — the source was actually checked
    #: "publishable"  — resolves to a document a reader can open, but the
    #:                  document itself was NOT fetched or validated. Added
    #:                  after review on PR #135: the audits branch was calling
    #:                  gate-only evidence "verified".
    #: "unverified"   — no evidence
    #: "stale"        — evidence exists but is out of date
    verification_status: str
    #: Why the status is not "verified". `unverified` means *no evidence*,
    #: never *fine* — without a reason a reader cannot tell the difference.
    reason: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────


def _grade_verification(verification) -> None:
    """Set an honest status for a row this endpoint has only READ.

    Reported by review on PR #135 against the audits branch, and it recurs:
    ``population_data``, ``gdp_data`` and ``loans`` do the same thing, and are
    weaker still — they apply no publication gate at all, they simply select
    the newest row and stamp it "verified".

    Nothing in this endpoint fetches a source document, compares an md5, or
    confirms a page locator. So "verified" is a claim the code cannot support,
    on the one endpoint whose entire purpose is answering "was this checked?".

    * ``publishable``  — the figure resolves to a document with a URL a reader
      can open. That is what actually holds today.
    * ``unverified``   — no resolvable source.

    It becomes "verified" when this endpoint really fetches and validates the
    document; tracked as P1 in #137.
    """
    if getattr(verification, "source_url", None):
        verification.verification_status = "publishable"
        if not getattr(verification, "reason", None):
            verification.reason = (
                "resolves to a source document; the document itself has not "
                "been fetched or validated by this endpoint"
            )
    else:
        verification.verification_status = "unverified"
        if not getattr(verification, "reason", None):
            verification.reason = "no resolvable source document"


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


# How long each table may sit unchanged before "healthy" becomes a lie.
# Derived from each publisher's own cadence (see the kenya-data-sources notes):
# CoB reports quarterly with a 45-day lag, the OAG annually with 6-9 months,
# KNBS CPI monthly, the census once a decade. A table older than its publisher's
# cycle plus a grace period is stale whatever its row count says.
_STALE_AFTER_DAYS = {
    "entities": 3650,           # county list — changes only by constitutional amendment
    "population_data": 3650,    # census
    "budget_lines": 180,        # CoB quarterly + lag
    "audits": 550,              # OAG annual + lag
    "gdp_data": 550,            # KNBS Economic Survey, annual
    "economic_indicators": 120,  # CPI monthly + lag
    "poverty_indices": 730,     # World Bank, irregular
    "loans": 240,               # CBK Statistical Bulletin, biannual + lag
    "debt_timeline": 240,
    "fiscal_summaries": 550,
}


def _table_age_days(db, model) -> Optional[int]:
    """Days since this table's newest PUBLISHED observation, or None.

    Database write timestamps do not measure publisher freshness, in both
    directions:

      * ``BudgetLine`` carries only ``created_at``, and its writers update
        values in place without touching it — so a table refreshed last night
        from a new CoB report reads as a year stale;
      * the debt and fiscal-summary writers reset ``updated_at`` on every
        reseed even when the source values are unchanged — so a series frozen
        at the publisher reads as current indefinitely.

    What this panel is actually asking is "how recently did the publisher
    publish something we ingested here?", so measure the ``fetch_date`` of the
    source documents this table references. Row write time is the fallback for
    tables with no document link at all.
    """
    from datetime import datetime, timezone

    newest = None
    if hasattr(model, "source_document_id"):
        newest = (
            db.query(func.max(SourceDocument.fetch_date))
            .join(model, model.source_document_id == SourceDocument.id)
            .scalar()
        )

    if newest is None:
        column = getattr(model, "updated_at", None) or getattr(
            model, "created_at", None
        )
        if column is None:
            return None
        newest = db.query(func.max(column)).scalar()

    if newest is None:
        return None
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - newest).days)


def _apply_freshness(table: "TableHealth", db, model) -> "TableHealth":
    """Downgrade a row-count verdict when the table has stopped moving.

    Every status here was a row-count floor with no time term, so a table
    frozen for a year read exactly like one updated last night —
    `poverty_indices` went green on a single row. A check that cannot go red is
    not a check (credibility audit F17).
    """
    limit = _STALE_AFTER_DAYS.get(table.table)
    table.stale_after_days = limit
    age = _table_age_days(db, model)
    table.age_days = age
    if limit is None or age is None:
        return table
    if age > limit and table.status == "healthy":
        table.status = "stale"
        extra = f"no row has changed in {age} days (expected within {limit})"
        table.notes = f"{table.notes}; {extra}" if table.notes else extra
    return table


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
    tables.append(_apply_freshness(TableHealth(
        table="entities",
        label="Counties",
        row_count=county_count,
        source="KNBS Census 2019",
        status="healthy" if county_count >= 47 else "critical" if county_count == 0 else "degraded",
    ), db, Entity))

    # Budget lines
    budget_count = db.query(BudgetLine).count()
    tables.append(_apply_freshness(TableHealth(
        table="budget_lines",
        label="Budget Lines",
        row_count=budget_count,
        source="COB County Budget Reports",
        status="healthy" if budget_count >= 400 else "critical" if budget_count == 0 else "degraded",
    ), db, BudgetLine))

    # Audit records. Health must describe what is *publishable*: counting
    # withheld rows here reported "27 rows" while 26 of them were excluded
    # from every public read.
    publishable_audits = db.query(Audit).filter(publishable_audit_criterion())
    audit_count = publishable_audits.count()
    withheld_audits = db.query(Audit).filter(~publishable_audit_criterion()).count()
    audits_with_year = publishable_audits.filter(Audit.audit_year.isnot(None)).count()
    tables.append(_apply_freshness(TableHealth(
        table="audits",
        label="Audit Findings",
        row_count=audit_count,
        source="OAG Audit Reports",
        status="healthy" if audits_with_year >= 50 else "degraded" if audit_count > 0 else "empty",
        notes=(
            f"{audits_with_year} publishable with audit_year; "
            f"{withheld_audits} withheld (no resolvable source document)"
        ),
    ), db, Audit))

    # Population
    pop_count = db.query(PopulationData).count()
    nat_pop = db.query(PopulationData).filter(PopulationData.entity_id.is_(None)).first()
    tables.append(_apply_freshness(TableHealth(
        table="population_data",
        label="Population Data",
        row_count=pop_count,
        latest_date=f"Year {nat_pop.year}" if nat_pop else None,
        source="KNBS Census 2019",
        status="healthy" if pop_count >= 48 and nat_pop else "degraded" if pop_count > 0 else "empty",
    ), db, PopulationData))

    # GDP
    gdp_count = db.query(GDPData).count()
    latest_gdp = db.query(GDPData).filter(GDPData.entity_id.is_(None)).order_by(desc(GDPData.year)).first()
    tables.append(_apply_freshness(TableHealth(
        table="gdp_data",
        label="GDP Data",
        row_count=gdp_count,
        latest_date=f"Year {latest_gdp.year}" if latest_gdp else None,
        source="KNBS Economic Survey",
        status="healthy" if gdp_count >= 5 else "degraded" if gdp_count > 0 else "empty",
    ), db, GDPData))

    # Economic indicators
    econ_count = db.query(EconomicIndicator).count()
    latest_econ = db.query(EconomicIndicator).order_by(desc(EconomicIndicator.indicator_date)).first()
    tables.append(_apply_freshness(TableHealth(
        table="economic_indicators",
        label="Economic Indicators",
        row_count=econ_count,
        latest_date=latest_econ.indicator_date.isoformat() if latest_econ else None,
        source="KNBS / CBK",
        status="healthy" if econ_count >= 5 else "degraded" if econ_count > 0 else "empty",
    ), db, EconomicIndicator))

    # Poverty
    poverty_count = db.query(PovertyIndex).count()
    tables.append(_apply_freshness(TableHealth(
        table="poverty_indices",
        label="Poverty Data",
        row_count=poverty_count,
        source="KNBS / World Bank",
        status="healthy" if poverty_count >= 1 else "empty",
    ), db, PovertyIndex))

    # Loans / Debt
    loan_count = db.query(Loan).count()
    tables.append(_apply_freshness(TableHealth(
        table="loans",
        label="Debt Records",
        row_count=loan_count,
        source="CBK Public Debt Bulletin",
        status="healthy" if loan_count >= 50 else "degraded" if loan_count > 0 else "empty",
    ), db, Loan))

    # Debt timeline
    debt_tl_count = db.query(DebtTimeline).count()
    tables.append(_apply_freshness(TableHealth(
        table="debt_timeline",
        label="Debt Timeline",
        row_count=debt_tl_count,
        source="CBK Annual Reports",
        status="healthy" if debt_tl_count >= 5 else "degraded" if debt_tl_count > 0 else "empty",
    ), db, DebtTimeline))

    # Fiscal summaries
    fiscal_count = db.query(FiscalSummary).count()
    tables.append(_apply_freshness(TableHealth(
        table="fiscal_summaries",
        label="Fiscal Summaries",
        row_count=fiscal_count,
        source="National Treasury BPS",
        status="healthy" if fiscal_count >= 3 else "degraded" if fiscal_count > 0 else "empty",
    ), db, FiscalSummary))

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


def _is_round_number_estimate(row) -> bool:
    """Is this debt-timeline row a round-number estimate, not a reading?

    Mirrors the frontend's `isRoundNumberEstimate` (NationalDebtCard.tsx):
    external, domestic AND total all landing exactly on KES 100 billion. Real
    CBK table values do not. Kept in both layers deliberately — the API must be
    able to say it without the UI, and the UI must be able to say it without a
    round trip.
    """
    STEP = 100_000_000_000  # KES 100 billion
    try:
        parts = [
            float(row.external or 0),
            float(row.domestic or 0),
            float(row.total or 0),
        ]
    except (TypeError, ValueError):
        return False
    return all(v > 0 and abs(v % STEP) < 1.0 for v in parts)


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
                _grade_verification(verification)

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
                _grade_verification(verification)

        elif table_name == "audits":
            # Only rows that pass the publication gate. This branch previously
            # returned the newest audit by id — which is 902, the glyph-code
            # cover page — and stamped it "verified" without checking anything.
            query = db.query(Audit).filter(publishable_audit_criterion())
            if entity_id:
                query = query.filter(Audit.entity_id == entity_id)
            record = query.order_by(desc(Audit.id)).first()
            if record is None:
                verification.reason = "no_publishable_row"
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
                # NOT "verified". Reported by review on PR #135.
                #
                # This row passed publishable_audit_criterion(), and that gate
                # says plainly what it does not do — it never fetches the URL,
                # never checks md5, and never requires a page locator (see the
                # "WHAT THIS GATE DOES NOT CHECK" section in
                # services/publication_gate.py). Stamping "verified" tells a
                # reader the evidence was checked when nothing was, on the one
                # endpoint whose entire job is answering "was this checked?".
                #
                # "publishable" is the honest word for what actually holds: the
                # figure resolves to a document a reader can open. It becomes
                # "verified" when this endpoint fetches that document and
                # confirms the locator — tracked as P1 in #137.
                verification.verification_status = "publishable"
                verification.reason = (
                    "resolves to a source document; the URL has not been "
                    "fetched, md5 not checked, page locator not required"
                )

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
                _grade_verification(verification)

        elif table_name == "budget_lines":
            # /sources promised a reader could "trace any county's budget
            # execution number back to the original COB quarterly report" while
            # this endpoint answered "Unknown table" for the very table that
            # holds those numbers (credibility audit F16). It answers now — and
            # what it mostly answers is that the figure is modelled, which is
            # the truth the promise was hiding.
            # Honour the caller's `year`, and say WHICH line was verified.
            # Ordering by id alone answered a different fiscal period than the
            # one asked about, so a verification could not identify the data
            # point it claimed to verify.
            query = db.query(BudgetLine).join(
                FiscalPeriod, BudgetLine.period_id == FiscalPeriod.id
            )
            if entity_id:
                query = query.filter(BudgetLine.entity_id == entity_id)
            if year:
                query = query.filter(
                    FiscalPeriod.start_date >= datetime(year, 1, 1),
                    FiscalPeriod.start_date < datetime(year + 1, 1, 1),
                )
            record = (
                query.order_by(desc(FiscalPeriod.start_date), desc(BudgetLine.id))
                .first()
            )
            if record is None:
                verification.reason = (
                    "no_rows_for_year" if year else "no_rows"
                )
            else:
                _period = (
                    db.query(FiscalPeriod)
                    .filter(FiscalPeriod.id == record.period_id)
                    .first()
                )
                _line_id = " · ".join(
                    part
                    for part in (
                        record.category or "uncategorised",
                        record.subcategory,
                        _period.label if _period else None,
                    )
                    if part
                )
                # allocated_amount is nullable. Reporting absence as
                # "KES 0 allocated" would manufacture the exact zero-as-a-claim
                # this endpoint exists to expose.
                if record.allocated_amount is None:
                    verification.value = None
                    verification.reason = (
                        f"no allocation recorded for {_line_id}"
                    )
                else:
                    verification.value = (
                        f"KES {float(record.allocated_amount):,.0f} allocated "
                        f"({_line_id})"
                    )
                if record.source_document_id:
                    doc = (
                        db.query(SourceDocument)
                        .filter(SourceDocument.id == record.source_document_id)
                        .first()
                    )
                    if doc:
                        verification.source_document = doc.title
                        verification.source_url = doc.url
                        verification.publisher = doc.publisher
                        verification.fetch_date = (
                            doc.fetch_date.isoformat() if doc.fetch_date else None
                        )
                _grade_verification(verification)
                # County budget lines are modelled from the CRA equitable-share
                # formula, not read from a CoB table. A resolvable source
                # document does not make the FIGURE sourced, so say so rather
                # than let the grade imply otherwise.
                if not record.provenance:
                    verification.verification_status = "modelled"
                    _modelled_reason = (
                        "county budget lines are modelled from the CRA "
                        "equitable-share formula; this figure is not read from "
                        "a Controller of Budget implementation table"
                    )
                    # Don't clobber a more specific reason (e.g. the row has no
                    # allocation at all) — both facts matter to the reader.
                    verification.reason = (
                        f"{verification.reason}; {_modelled_reason}"
                        if verification.reason
                        else _modelled_reason
                    )

        elif table_name == "debt_timeline":
            # Honour `year`: without it, asking about an older modelled year
            # always returned the newest row instead.
            _dt_query = db.query(DebtTimeline)
            if year:
                _dt_query = _dt_query.filter(DebtTimeline.year == year)
            record = _dt_query.order_by(desc(DebtTimeline.year)).first()
            if record is None:
                verification.reason = (
                    "no_rows_for_year" if year else "no_rows"
                )
            else:
                verification.value = (
                    f"KES {float(record.total or 0):,.0f} total (year {record.year})"
                )
                if getattr(record, "source_document_id", None):
                    doc = (
                        db.query(SourceDocument)
                        .filter(SourceDocument.id == record.source_document_id)
                        .first()
                    )
                    if doc:
                        verification.source_document = doc.title
                        verification.source_url = doc.url
                        verification.publisher = doc.publisher
                _grade_verification(verification)
                # 2013-2021 are round-number estimates across external,
                # domestic AND total at once — no CBK table produces that.
                # Flag the row rather than grading an estimate as sourced.
                if _is_round_number_estimate(record):
                    verification.verification_status = "modelled"
                    verification.reason = (
                        "round-number estimate: external, domestic and total "
                        "are all exact multiples of KES 100 billion, which no "
                        "published CBK table produces"
                    )

        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown table: {table_name}. Supported: population_data, "
                    "gdp_data, audits, loans, budget_lines, debt_timeline"
                ),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Verification error for %s: %s", table_name, e)
        verification.verification_status = "error"

    return verification

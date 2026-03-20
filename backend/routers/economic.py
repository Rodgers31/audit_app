"""
Economic Data Router - KNBS Economic Indicators API

Provides endpoints for:
- Population data (national and county-level)
- GDP and Gross County Product
- Economic indicators (CPI, inflation, unemployment)
- Poverty indices
- Comprehensive county economic profiles
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, desc, func
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from database import get_db
    from models import (
        EconomicIndicator,
        Entity,
        EntityType,
        GDPData,
        PopulationData,
        PovertyIndex,
    )

    DATABASE_AVAILABLE = True
except Exception as e:
    DATABASE_AVAILABLE = False

    # Mock database functions
    def get_db():
        return None


router = APIRouter(prefix="/api/v1/economic", tags=["Economic Data"])
logger = logging.getLogger(__name__)


# ===== Response Models =====


class PopulationResponse(BaseModel):
    """Population data response."""

    id: int
    entity_id: Optional[int]
    entity_name: Optional[str]
    entity_type: Optional[str]  # national, county
    year: int
    total_population: int
    male_population: Optional[int]
    female_population: Optional[int]
    urban_population: Optional[int]
    rural_population: Optional[int]
    population_density: Optional[float]
    confidence: Optional[float]
    source_document_id: Optional[int]
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class PopulationLatestResponse(BaseModel):
    """Lightweight response for the latest national population figure."""

    population: int
    year: int
    source: Optional[str] = None
    updated_at: Optional[str] = None


class GDPResponse(BaseModel):
    """GDP/GCP data response."""

    id: int
    entity_id: Optional[int]
    entity_name: Optional[str]
    entity_type: Optional[str]  # national, county
    year: int
    quarter: Optional[str]
    gdp_value: float
    gdp_growth_rate: Optional[float]
    currency: str
    confidence: Optional[float]
    source_document_id: Optional[int]
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class EconomicIndicatorResponse(BaseModel):
    """Economic indicator response."""

    id: int
    indicator_type: str
    indicator_date: str
    value: float
    entity_id: Optional[int]
    entity_name: Optional[str]
    entity_type: Optional[str]
    unit: Optional[str]
    confidence: Optional[float]
    source_document_id: Optional[int]
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class PovertyIndexResponse(BaseModel):
    """Poverty index response."""

    id: int
    entity_id: Optional[int]
    entity_name: Optional[str]
    entity_type: Optional[str]
    year: int
    poverty_headcount_rate: Optional[float]
    extreme_poverty_rate: Optional[float]
    gini_coefficient: Optional[float]
    confidence: Optional[float]
    source_document_id: Optional[int]
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class CountyEconomicProfile(BaseModel):
    """Comprehensive county economic profile."""

    county_id: int
    county_name: str
    latest_population: Optional[PopulationResponse]
    latest_gcp: Optional[GDPResponse]
    latest_poverty: Optional[PovertyIndexResponse]
    economic_indicators: List[EconomicIndicatorResponse]
    per_capita_gcp: Optional[float]
    population_growth_rate: Optional[float]


class EconomicSummary(BaseModel):
    """National economic summary."""

    total_population: Optional[int]
    total_gdp: Optional[float]
    gdp_growth_rate: Optional[float]
    inflation_rate: Optional[float]
    unemployment_rate: Optional[float]
    poverty_rate: Optional[float]
    data_as_of: str


# ===== Helper Functions =====


def get_entity_info(entity_id: Optional[int], db: Session) -> tuple:
    """Get entity name and type."""
    if not entity_id or not DATABASE_AVAILABLE:
        return None, "national"

    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        return None, "unknown"
    # models.Entity has `type` as Enum(EntityType) and canonical_name as the label
    try:
        if entity.type == EntityType.COUNTY:
            entity_type = "county"
        elif entity.type == EntityType.NATIONAL:
            entity_type = "national"
        else:
            # Fallback to enum value string
            entity_type = getattr(entity.type, "value", str(entity.type)).lower()
    except Exception:
        entity_type = "unknown"
    return getattr(entity, "canonical_name", None), entity_type


# ===== Population Endpoints =====


@router.get(
    "/population/latest",
    response_model=PopulationLatestResponse,
    summary="Get Latest National Population",
)
async def get_population_latest(db: Session = Depends(get_db)):
    """Return the most recent national-level population record."""
    if not DATABASE_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        row = (
            db.query(PopulationData)
            .filter(PopulationData.entity_id.is_(None))
            .order_by(desc(PopulationData.year))
            .first()
        )
    except OperationalError as e:
        logger.error("Database connection error on /population/latest: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error on /population/latest: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")

    if not row:
        raise HTTPException(status_code=404, detail="No population data found")

    source_name = None
    if row.source_document:
        source_name = row.source_document.title

    return PopulationLatestResponse(
        population=row.total_population,
        year=row.year,
        source=source_name or "KNBS",
        updated_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.get(
    "/population",
    response_model=List[PopulationResponse],
    summary="Get Population Data",
)
async def get_population(
    entity_id: Optional[int] = Query(
        None, description="Filter by entity ID (county or national)"
    ),
    year: Optional[int] = Query(None, description="Filter by specific year"),
    start_year: Optional[int] = Query(None, description="Start year for range query"),
    end_year: Optional[int] = Query(None, description="End year for range query"),
    min_confidence: float = Query(
        0.7, description="Minimum confidence score", ge=0, le=1
    ),
    limit: int = Query(100, description="Maximum results to return", le=1000),
    db: Session = Depends(get_db),
):
    """
    Get population data from KNBS.

    Supports filtering by:
    - Entity (county or national)
    - Specific year or year range
    - Confidence score threshold

    Returns population statistics including:
    - Total population
    - Male/female breakdown
    - Urban/rural distribution
    - Population density
    """
    if not DATABASE_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # Build query
        query = db.query(PopulationData)

        # Apply filters
        if entity_id is not None:
            query = query.filter(PopulationData.entity_id == entity_id)

        if year is not None:
            query = query.filter(PopulationData.year == year)
        elif start_year is not None or end_year is not None:
            if start_year:
                query = query.filter(PopulationData.year >= start_year)
            if end_year:
                query = query.filter(PopulationData.year <= end_year)

        if min_confidence:
            query = query.filter(PopulationData.confidence >= min_confidence)

        # Order by year descending
        query = query.order_by(desc(PopulationData.year))

        # Execute query with limit
        results = query.limit(limit).all()
    except OperationalError as e:
        logger.error("Database connection error on /population: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error on /population: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")

    # Enrich with entity information
    response = []
    for row in results:
        entity_name, entity_type = get_entity_info(row.entity_id, db)
        response.append(
            PopulationResponse(
                id=row.id,
                entity_id=row.entity_id,
                entity_name=entity_name,
                entity_type=entity_type,
                year=row.year,
                total_population=row.total_population,
                male_population=row.male_population,
                female_population=row.female_population,
                urban_population=row.urban_population,
                rural_population=row.rural_population,
                population_density=(
                    float(row.population_density) if row.population_density else None
                ),
                confidence=float(row.confidence) if row.confidence else None,
                source_document_id=row.source_document_id,
                created_at=row.created_at.isoformat() if row.created_at else "",
            )
        )

    return response


# ===== GDP Endpoints =====


@router.get("/gdp", response_model=List[GDPResponse], summary="Get GDP Data")
async def get_gdp(
    entity_id: Optional[int] = Query(
        None,
        description="Filter by entity ID (NULL for national GDP, county ID for GCP)",
    ),
    year: Optional[int] = Query(None, description="Filter by specific year"),
    quarter: Optional[str] = Query(
        None, description="Filter by quarter (Q1, Q2, Q3, Q4)"
    ),
    start_year: Optional[int] = Query(None, description="Start year for range query"),
    end_year: Optional[int] = Query(None, description="End year for range query"),
    min_confidence: float = Query(
        0.7, description="Minimum confidence score", ge=0, le=1
    ),
    limit: int = Query(100, description="Maximum results to return", le=1000),
    db: Session = Depends(get_db),
):
    """
    Get GDP and Gross County Product data from KNBS.

    Supports filtering by:
    - Entity (NULL for national GDP, county_id for GCP)
    - Specific year or year range
    - Quarter (Q1-Q4)
    - Confidence score threshold

    Returns GDP statistics including:
    - GDP value in KES
    - GDP growth rate
    - Quarterly or annual data
    """
    if not DATABASE_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # Build query
        query = db.query(GDPData)

        # Apply filters
        if entity_id is not None:
            query = query.filter(GDPData.entity_id == entity_id)

        if year is not None:
            query = query.filter(GDPData.year == year)
        elif start_year is not None or end_year is not None:
            if start_year:
                query = query.filter(GDPData.year >= start_year)
            if end_year:
                query = query.filter(GDPData.year <= end_year)

        if quarter:
            query = query.filter(GDPData.quarter == quarter.upper())

        if min_confidence:
            query = query.filter(GDPData.confidence >= min_confidence)

        # Order by year and quarter descending
        query = query.order_by(desc(GDPData.year), desc(GDPData.quarter))

        # Execute query with limit
        results = query.limit(limit).all()
    except OperationalError as e:
        logger.error("Database connection error on /gdp: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error on /gdp: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")

    # Enrich with entity information
    response = []
    for row in results:
        entity_name, entity_type = get_entity_info(row.entity_id, db)
        response.append(
            GDPResponse(
                id=row.id,
                entity_id=row.entity_id,
                entity_name=entity_name,
                entity_type=entity_type,
                year=row.year,
                quarter=row.quarter,
                gdp_value=float(row.gdp_value),
                gdp_growth_rate=(
                    float(row.gdp_growth_rate) if row.gdp_growth_rate else None
                ),
                currency=row.currency,
                confidence=float(row.confidence) if row.confidence else None,
                source_document_id=row.source_document_id,
                created_at=row.created_at.isoformat() if row.created_at else "",
            )
        )

    return response


# ===== Economic Indicators Endpoints =====


@router.get(
    "/indicators",
    response_model=List[EconomicIndicatorResponse],
    summary="Get Economic Indicators",
)
async def get_economic_indicators(
    indicator_type: Optional[str] = Query(
        None,
        description="Filter by indicator type (CPI, PPI, inflation_rate, unemployment_rate)",
    ),
    entity_id: Optional[int] = Query(
        None, description="Filter by entity ID (NULL for national)"
    ),
    start_date: Optional[str] = Query(
        None, description="Start date for range query (YYYY-MM-DD)"
    ),
    end_date: Optional[str] = Query(
        None, description="End date for range query (YYYY-MM-DD)"
    ),
    min_confidence: float = Query(
        0.7, description="Minimum confidence score", ge=0, le=1
    ),
    limit: int = Query(100, description="Maximum results to return", le=1000),
    db: Session = Depends(get_db),
):
    """
    Get economic indicators from KNBS.

    Supports filtering by:
    - Indicator type (CPI, PPI, inflation_rate, unemployment_rate)
    - Entity (NULL for national, county_id for county-level)
    - Date range
    - Confidence score threshold

    Returns economic indicators including:
    - Consumer Price Index (CPI)
    - Producer Price Index (PPI)
    - Inflation rates
    - Unemployment rates
    """
    if not DATABASE_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # Build query
        query = db.query(EconomicIndicator)

        # Apply filters
        if indicator_type:
            query = query.filter(EconomicIndicator.indicator_type == indicator_type)

        if entity_id is not None:
            query = query.filter(EconomicIndicator.entity_id == entity_id)

        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date)
                query = query.filter(EconomicIndicator.indicator_date >= start_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format")

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date)
                query = query.filter(EconomicIndicator.indicator_date <= end_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format")

        if min_confidence:
            query = query.filter(EconomicIndicator.confidence >= min_confidence)

        # Order by date descending
        query = query.order_by(desc(EconomicIndicator.indicator_date))

        # Execute query with limit
        results = query.limit(limit).all()
    except OperationalError as e:
        logger.error("Database connection error on /indicators: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error on /indicators: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")

    # Enrich with entity information
    response = []
    for row in results:
        entity_name, entity_type = get_entity_info(row.entity_id, db)
        response.append(
            EconomicIndicatorResponse(
                id=row.id,
                indicator_type=row.indicator_type,
                indicator_date=(
                    row.indicator_date.isoformat() if row.indicator_date else ""
                ),
                value=float(row.value),
                entity_id=row.entity_id,
                entity_name=entity_name,
                entity_type=entity_type,
                unit=row.unit,
                confidence=float(row.confidence) if row.confidence else None,
                source_document_id=row.source_document_id,
                created_at=row.created_at.isoformat() if row.created_at else "",
            )
        )

    return response


# ===== Poverty Endpoints =====


@router.get(
    "/poverty",
    response_model=List[PovertyIndexResponse],
    summary="Get Poverty Indices",
)
async def get_poverty_indices(
    entity_id: Optional[int] = Query(
        None, description="Filter by entity ID (county or national)"
    ),
    year: Optional[int] = Query(None, description="Filter by specific year"),
    start_year: Optional[int] = Query(None, description="Start year for range query"),
    end_year: Optional[int] = Query(None, description="End year for range query"),
    min_confidence: float = Query(
        0.7, description="Minimum confidence score", ge=0, le=1
    ),
    limit: int = Query(100, description="Maximum results to return", le=1000),
    db: Session = Depends(get_db),
):
    """
    Get poverty indices from KNBS.

    Supports filtering by:
    - Entity (county or national)
    - Specific year or year range
    - Confidence score threshold

    Returns poverty statistics including:
    - Poverty headcount rate
    - Extreme poverty rate
    - Gini coefficient (income inequality)
    """
    if not DATABASE_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # Build query
        query = db.query(PovertyIndex)

        # Apply filters
        if entity_id is not None:
            query = query.filter(PovertyIndex.entity_id == entity_id)

        if year is not None:
            query = query.filter(PovertyIndex.year == year)
        elif start_year is not None or end_year is not None:
            if start_year:
                query = query.filter(PovertyIndex.year >= start_year)
            if end_year:
                query = query.filter(PovertyIndex.year <= end_year)

        if min_confidence:
            query = query.filter(PovertyIndex.confidence >= min_confidence)

        # Order by year descending
        query = query.order_by(desc(PovertyIndex.year))

        # Execute query with limit
        results = query.limit(limit).all()
    except OperationalError as e:
        logger.error("Database connection error on /poverty: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error on /poverty: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")

    # Enrich with entity information
    response = []
    for row in results:
        entity_name, entity_type = get_entity_info(row.entity_id, db)
        response.append(
            PovertyIndexResponse(
                id=row.id,
                entity_id=row.entity_id,
                entity_name=entity_name,
                entity_type=entity_type,
                year=row.year,
                poverty_headcount_rate=(
                    float(row.poverty_headcount_rate)
                    if row.poverty_headcount_rate
                    else None
                ),
                extreme_poverty_rate=(
                    float(row.extreme_poverty_rate)
                    if row.extreme_poverty_rate
                    else None
                ),
                gini_coefficient=(
                    float(row.gini_coefficient) if row.gini_coefficient else None
                ),
                confidence=float(row.confidence) if row.confidence else None,
                source_document_id=row.source_document_id,
                created_at=row.created_at.isoformat() if row.created_at else "",
            )
        )

    return response


# ===== County Economic Profile Endpoint =====


@router.get(
    "/counties/{county_id}/profile",
    response_model=CountyEconomicProfile,
    summary="Get County Economic Profile",
)
async def get_county_economic_profile(
    county_id: int,
    db: Session = Depends(get_db),
):
    """
    Get comprehensive economic profile for a specific county.

    Returns:
    - Latest population data
    - Latest Gross County Product (GCP)
    - Latest poverty indices
    - Recent economic indicators
    - Calculated per-capita GCP
    - Population growth rate

    This endpoint provides all economic context needed for
    analyzing county budgets and audit findings.
    """
    if not DATABASE_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # Get county entity
        from models import EntityType as _ET

        county = (
            db.query(Entity)
            .filter(and_(Entity.id == county_id, Entity.type == _ET.COUNTY))
            .first()
        )

        if not county:
            raise HTTPException(status_code=404, detail=f"County {county_id} not found")

        # Get latest population
        latest_pop = (
            db.query(PopulationData)
            .filter(PopulationData.entity_id == county_id)
            .order_by(desc(PopulationData.year))
            .first()
        )

        pop_response = None
        if latest_pop:
            pop_response = PopulationResponse(
                id=latest_pop.id,
                entity_id=latest_pop.entity_id,
                entity_name=county.canonical_name,
                entity_type="county",
                year=latest_pop.year,
                total_population=latest_pop.total_population,
                male_population=latest_pop.male_population,
                female_population=latest_pop.female_population,
                urban_population=latest_pop.urban_population,
                rural_population=latest_pop.rural_population,
                population_density=(
                    float(latest_pop.population_density)
                    if latest_pop.population_density
                    else None
                ),
                confidence=(
                    float(latest_pop.confidence) if latest_pop.confidence else None
                ),
                source_document_id=latest_pop.source_document_id,
                created_at=(
                    latest_pop.created_at.isoformat() if latest_pop.created_at else ""
                ),
            )

        # Get latest GCP
        latest_gcp = (
            db.query(GDPData)
            .filter(GDPData.entity_id == county_id)
            .order_by(desc(GDPData.year), desc(GDPData.quarter))
            .first()
        )

        gcp_response = None
        per_capita_gcp = None
        if latest_gcp:
            gcp_response = GDPResponse(
                id=latest_gcp.id,
                entity_id=latest_gcp.entity_id,
                entity_name=county.canonical_name,
                entity_type="county",
                year=latest_gcp.year,
                quarter=latest_gcp.quarter,
                gdp_value=float(latest_gcp.gdp_value),
                gdp_growth_rate=(
                    float(latest_gcp.gdp_growth_rate)
                    if latest_gcp.gdp_growth_rate
                    else None
                ),
                currency=latest_gcp.currency,
                confidence=(
                    float(latest_gcp.confidence) if latest_gcp.confidence else None
                ),
                source_document_id=latest_gcp.source_document_id,
                created_at=(
                    latest_gcp.created_at.isoformat() if latest_gcp.created_at else ""
                ),
            )

            # Calculate per-capita GCP
            if latest_pop and latest_pop.total_population > 0:
                per_capita_gcp = (
                    float(latest_gcp.gdp_value) / latest_pop.total_population
                )

        # Get latest poverty index
        latest_poverty = (
            db.query(PovertyIndex)
            .filter(PovertyIndex.entity_id == county_id)
            .order_by(desc(PovertyIndex.year))
            .first()
        )

        poverty_response = None
        if latest_poverty:
            poverty_response = PovertyIndexResponse(
                id=latest_poverty.id,
                entity_id=latest_poverty.entity_id,
                entity_name=county.canonical_name,
                entity_type="county",
                year=latest_poverty.year,
                poverty_headcount_rate=(
                    float(latest_poverty.poverty_headcount_rate)
                    if latest_poverty.poverty_headcount_rate
                    else None
                ),
                extreme_poverty_rate=(
                    float(latest_poverty.extreme_poverty_rate)
                    if latest_poverty.extreme_poverty_rate
                    else None
                ),
                gini_coefficient=(
                    float(latest_poverty.gini_coefficient)
                    if latest_poverty.gini_coefficient
                    else None
                ),
                confidence=(
                    float(latest_poverty.confidence)
                    if latest_poverty.confidence
                    else None
                ),
                source_document_id=latest_poverty.source_document_id,
                created_at=(
                    latest_poverty.created_at.isoformat()
                    if latest_poverty.created_at
                    else ""
                ),
            )

        # Get recent economic indicators (last 12 months)
        one_year_ago = datetime.now().replace(year=datetime.now().year - 1)
        recent_indicators = (
            db.query(EconomicIndicator)
            .filter(
                and_(
                    EconomicIndicator.entity_id == county_id,
                    EconomicIndicator.indicator_date >= one_year_ago,
                )
            )
            .order_by(desc(EconomicIndicator.indicator_date))
            .limit(20)
            .all()
        )

        indicators_response = []
        for ind in recent_indicators:
            indicators_response.append(
                EconomicIndicatorResponse(
                    id=ind.id,
                    indicator_type=ind.indicator_type,
                    indicator_date=(
                        ind.indicator_date.isoformat() if ind.indicator_date else ""
                    ),
                    value=float(ind.value),
                    entity_id=ind.entity_id,
                    entity_name=county.name,
                    entity_type="county",
                    unit=ind.unit,
                    confidence=float(ind.confidence) if ind.confidence else None,
                    source_document_id=ind.source_document_id,
                    created_at=ind.created_at.isoformat() if ind.created_at else "",
                )
            )

        # Calculate population growth rate (last 2 available years)
        pop_data = (
            db.query(PopulationData)
            .filter(PopulationData.entity_id == county_id)
            .order_by(desc(PopulationData.year))
            .limit(2)
            .all()
        )

        population_growth_rate = None
        if len(pop_data) == 2:
            recent = pop_data[0]
            previous = pop_data[1]
            years_diff = recent.year - previous.year
            if years_diff > 0:
                growth = (
                    recent.total_population - previous.total_population
                ) / previous.total_population
                population_growth_rate = (
                    growth / years_diff
                ) * 100  # Annual percentage

        return CountyEconomicProfile(
            county_id=county_id,
            county_name=county.canonical_name,
            latest_population=pop_response,
            latest_gcp=gcp_response,
            latest_poverty=poverty_response,
            economic_indicators=indicators_response,
            per_capita_gcp=per_capita_gcp,
            population_growth_rate=population_growth_rate,
        )
    except OperationalError as e:
        logger.error(
            "Database connection error on /counties/{county_id}/profile: %s", e
        )
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error on /counties/{county_id}/profile: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")


# ===== National Economic Summary =====


@router.get(
    "/summary",
    response_model=EconomicSummary,
    summary="Get National Economic Summary",
)
async def get_economic_summary(
    db: Session = Depends(get_db),
):
    """
    Get high-level national economic summary.

    Returns latest available data for:
    - Total population
    - Total GDP
    - GDP growth rate
    - Inflation rate
    - Unemployment rate
    - National poverty rate

    This endpoint provides quick overview for dashboards.
    """
    if not DATABASE_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        # Get latest national population (entity_id is NULL for national)
        latest_pop = (
            db.query(PopulationData)
            .filter(PopulationData.entity_id.is_(None))
            .order_by(desc(PopulationData.year))
            .first()
        )

        total_population = latest_pop.total_population if latest_pop else None

        # Get latest national GDP
        latest_gdp = (
            db.query(GDPData)
            .filter(GDPData.entity_id.is_(None))
            .order_by(desc(GDPData.year), desc(GDPData.quarter))
            .first()
        )

        total_gdp = float(latest_gdp.gdp_value) if latest_gdp else None
        gdp_growth_rate = (
            float(latest_gdp.gdp_growth_rate)
            if latest_gdp and latest_gdp.gdp_growth_rate
            else None
        )

        # Get latest inflation rate
        latest_inflation = (
            db.query(EconomicIndicator)
            .filter(
                and_(
                    EconomicIndicator.indicator_type == "inflation_rate",
                    EconomicIndicator.entity_id.is_(None),
                )
            )
            .order_by(desc(EconomicIndicator.indicator_date))
            .first()
        )

        inflation_rate = float(latest_inflation.value) if latest_inflation else None

        # Get latest unemployment rate
        latest_unemployment = (
            db.query(EconomicIndicator)
            .filter(
                and_(
                    EconomicIndicator.indicator_type == "unemployment_rate",
                    EconomicIndicator.entity_id.is_(None),
                )
            )
            .order_by(desc(EconomicIndicator.indicator_date))
            .first()
        )

        unemployment_rate = (
            float(latest_unemployment.value) if latest_unemployment else None
        )

        # Get latest poverty rate
        latest_poverty = (
            db.query(PovertyIndex)
            .filter(PovertyIndex.entity_id.is_(None))
            .order_by(desc(PovertyIndex.year))
            .first()
        )

        poverty_rate = (
            float(latest_poverty.poverty_headcount_rate)
            if latest_poverty and latest_poverty.poverty_headcount_rate
            else None
        )

        return EconomicSummary(
            total_population=total_population,
            total_gdp=total_gdp,
            gdp_growth_rate=gdp_growth_rate,
            inflation_rate=inflation_rate,
            unemployment_rate=unemployment_rate,
            poverty_rate=poverty_rate,
            data_as_of=datetime.now().isoformat(),
        )
    except OperationalError as e:
        logger.error("Database connection error on /summary: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")
    except SQLAlchemyError as e:
        logger.error("Database error on /summary: %s", e)
        raise HTTPException(status_code=500, detail="Database query failed")

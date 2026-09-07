"""
Modernized Data-Driven Government Analytics API
Uses actual extracted data instead of hard-coded values
Automatically updates when new data files are available

WITHDRAWN 2026-09-07 (issue #188): six routes that served typed-in national
figures, together with the ``NationalOverview`` response model that only
``/national/overview`` used.

    GET /national/overview                    total_debt, debt_to_gdp_ratio,
                                              execution_rate=78.5
    GET /national/debt                        11.5T, a 60/40 external split,
                                              70.2% debt-to-GDP, a typed
                                              2020-2024 series — wrapped in a
                                              second "verification" block
                                              claiming manual cross-reference
    GET /national/ministries                  execution rates from
    GET /national/ministries/{ministry_name}  abs(hash(name)) % 25
    GET /national/revenue                     budget * 0.75 * 0.875, split 80/20
    GET /analytics/comprehensive              composed all of the above

Those figures disagree with backend/seeding/real_data/debt_timeline.json, which
carries CBK figures cited to the PDF page — including the direction of the
2023-2024 move and which half of the debt is larger.

The nine routes below served no invented figure and are unchanged. They read
from ``DataDrivenGovernmentAnalytics``, whose five data-source paths do not
resolve in this repo, so several of them currently report absence. That is a
separate defect (issue #188, "the data-driven path is dead, and fails
silently"); a route that returns empty is not a route that asserts a fabricated
number, and it is not withdrawn here.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import uvicorn
from data_driven_analytics import DataDrivenGovernmentAnalytics
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("modernized_api.log")],
)
logger = logging.getLogger(__name__)

# Initialize data-driven analytics
analytics = DataDrivenGovernmentAnalytics()

# FastAPI app
app = FastAPI(
    title="Data-Driven Kenya Government Analytics API",
    description="Modern API using actual extracted data with automatic updates",
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    client_ip = request.client.host
    method = request.method
    url = str(request.url)

    logger.info(f"🔄 {method} {url} from {client_ip} - Processing...")

    try:
        response = await call_next(request)
        process_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"✅ {method} {url} - {response.status_code} - {process_time:.3f}s")
        return response
    except Exception as e:
        process_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"❌ {method} {url} - ERROR: {str(e)} - {process_time:.3f}s")
        raise


# Data Models
class DataSourceStatus(BaseModel):
    source_name: str
    available: bool
    last_updated: str
    record_count: int
    file_path: str


# Startup event
@app.on_event("startup")
async def startup_event():
    """Load and verify data on startup."""
    logger.info("🚀 Starting Data-Driven Government Analytics API...")
    logger.info(f"📍 Working directory: {os.getcwd()}")
    logger.info("📂 Initializing data analytics...")

    try:
        analytics.refresh_all_data()

        # Log data availability
        logger.info("📊 Data sources status:")
        for source, data in analytics.cached_data.items():
            status = "✅ Available" if data else "❌ Missing"
            count = len(data) if isinstance(data, (list, dict)) else 0
            logger.info(f"   {status} {source}: {count} records")

        logger.info("✅ Data-driven API startup complete!")
    except Exception as e:
        logger.error(f"❌ Error during startup: {str(e)}")
        raise


@app.get("/health")
async def health_check(request: Request):
    """API health check with data source status."""
    client_ip = request.client.host
    logger.info(f"🏥 Health check requested from {client_ip}")

    try:
        data_status = {}
        for source_name, data in analytics.cached_data.items():
            data_status[source_name] = {
                "available": bool(data),
                "record_count": len(data) if isinstance(data, (list, dict)) else 0,
                "type": type(data).__name__,
            }

        response = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "data_sources": data_status,
            "api_version": "4.0.0",
        }

        logger.info(
            f"✅ Health check completed - {len(data_status)} data sources checked"
        )
        return response
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@app.get("/data-sources", response_model=List[DataSourceStatus])
async def get_data_sources(request: Request):
    """Get detailed status of all data sources."""
    client_ip = request.client.host
    logger.info(f"📊 Data sources status requested from {client_ip}")

    try:
        sources = []
        for source_name, data in analytics.cached_data.items():
            sources.append(
                DataSourceStatus(
                    source_name=source_name,
                    available=bool(data),
                    last_updated=datetime.now().isoformat(),
                    record_count=len(data) if isinstance(data, (list, dict)) else 0,
                    file_path=f"data/{source_name}.json",
                )
            )

        logger.info(f"✅ Returned status for {len(sources)} data sources")
        return sources
    except Exception as e:
        logger.error(f"❌ Error getting data sources: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving data sources: {str(e)}"
        )

    for source_name, filename in analytics.data_sources.items():
        data = analytics.cached_data.get(source_name, {})

        sources.append(
            DataSourceStatus(
                source_name=source_name,
                available=bool(data),
                last_updated=datetime.now().isoformat(),
                record_count=len(data) if isinstance(data, (list, dict)) else 0,
                file_path=filename,
            )
        )

    return sources


@app.post("/refresh-data")
async def refresh_data(background_tasks: BackgroundTasks):
    """Refresh all data sources."""
    background_tasks.add_task(analytics.refresh_all_data)

    return {
        "status": "refresh_initiated",
        "message": "Data refresh started in background",
        "timestamp": datetime.now().isoformat(),
    }


# County Government Endpoints


@app.get("/counties/statistics")
async def get_county_statistics():
    """Get county statistics from actual extracted data."""
    county_stats = analytics.get_actual_county_statistics()

    return {
        "status": "success",
        "data": county_stats,
        "calculation_note": "Statistics calculated from actual county data files",
    }


@app.get("/counties/{county_name}")
async def get_county_details(county_name: str):
    """Get detailed county information from actual data."""
    county_file_data = analytics.cached_data.get("county_data", {})

    if not county_file_data:
        raise HTTPException(
            status_code=503,
            detail="County data not available. Please check data sources.",
        )

    # Access the nested county_data structure
    county_data = county_file_data.get("county_data", {})

    if not county_data:
        raise HTTPException(
            status_code=503,
            detail="County data structure invalid. Missing county_data key.",
        )

    # Find matching county (case-insensitive)
    matching_county = None
    for county in county_data.keys():
        if county.lower() == county_name.lower():
            matching_county = county
            break

    if not matching_county:
        available_counties = list(county_data.keys())
        raise HTTPException(
            status_code=404,
            detail=f"County '{county_name}' not found. Available: {', '.join(available_counties[:10])}...",
        )

    county_info = county_data[matching_county]

    return {
        "status": "success",
        "data": county_info,
        "data_source": "enhanced_county_data.json",
    }


# Audit Oversight Endpoints


@app.get("/audit/overview")
async def get_audit_overview():
    """Get audit oversight statistics from actual OAG data."""
    audit_stats = analytics.get_actual_audit_statistics()

    return {
        "status": "success",
        "data": audit_stats,
        "note": "Statistics from actual Office of Auditor-General data",
    }


@app.get("/audit/queries")
async def get_audit_queries(
    county: Optional[str] = Query(None, description="Filter by county name"),
    severity: Optional[str] = Query(None, description="Filter by severity level"),
    limit: int = Query(50, description="Maximum number of results"),
):
    """Get audit queries from actual OAG data with filters."""
    oag_data = analytics.cached_data.get("oag_audit", {})

    if not oag_data:
        raise HTTPException(status_code=503, detail="OAG audit data not available")

    queries = oag_data.get("audit_queries", [])

    # Apply filters
    filtered_queries = queries

    if county:
        filtered_queries = [
            q for q in filtered_queries if q.get("county", "").lower() == county.lower()
        ]

    if severity:
        filtered_queries = [
            q
            for q in filtered_queries
            if q.get("severity", "").lower() == severity.lower()
        ]

    # Limit results
    filtered_queries = filtered_queries[:limit]

    return {
        "status": "success",
        "total_queries": len(queries),
        "filtered_count": len(filtered_queries),
        "queries": filtered_queries,
        "filters_applied": {"county": county, "severity": severity, "limit": limit},
        "data_source": "oag_audit_data.json",
    }


# Analytics and Reporting Endpoints


@app.get("/analytics/transparency")
async def get_transparency_metrics():
    """Get transparency metrics based on data availability."""
    transparency_score = analytics._calculate_transparency_score()

    # Additional transparency metrics
    data_freshness = {}
    for source, data in analytics.cached_data.items():
        if data:
            data_freshness[source] = "current"
        else:
            data_freshness[source] = "missing"

    return {
        "status": "success",
        "transparency_score": transparency_score,
        "data_availability": data_freshness,
        "calculation_factors": {
            "data_sources_available": len(
                [k for k, v in analytics.cached_data.items() if v]
            ),
            "total_data_sources": len(analytics.data_sources),
            "quality_bonuses": "Applied for county, audit, and COB data",
        },
        "recommendations": [
            "Ensure regular data updates",
            "Expand data source coverage",
            "Implement automated data validation",
        ],
    }


@app.get("/reports/summary")
async def get_reports_summary():
    """Get summary of all available reports."""
    gov_reports = analytics.cached_data.get("government_reports", {})
    cob_reports = analytics.cached_data.get("cob_reports", {})

    summary = {
        "government_reports": {
            "available": bool(gov_reports),
            "count": (
                len(gov_reports.get("discovered_reports", {})) if gov_reports else 0
            ),
        },
        "cob_reports": {
            "available": bool(cob_reports),
            "count": len(cob_reports.get("reports", [])) if cob_reports else 0,
        },
        "total_reports_tracked": 0,
    }

    summary["total_reports_tracked"] = (
        summary["government_reports"]["count"] + summary["cob_reports"]["count"]
    )

    return {
        "status": "success",
        "data": summary,
        "data_sources": [
            "comprehensive_government_reports.json",
            "comprehensive_cob_reports_database.json",
        ],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)

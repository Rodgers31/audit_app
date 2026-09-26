"""
Enhanced County API - Comprehensive County Analytics
Integrates the 47 county dataset with budgets, loans, audit queries, rankings, and missing funds analysis
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Enhanced County Models
class CountySummary(BaseModel):
    county: str
    population: int
    budget_2025: float
    revenue_2024: float
    debt_outstanding: float
    pending_bills: float
    loans_received: Optional[float] = None  # no record carries it today
    audit_rating: str
    missing_funds: float
    financial_health_score: float
    budget_execution_rate: float


class CountyRanking(BaseModel):
    rank: int
    county: str
    value: float
    metric: str


class CountyAuditQuery(BaseModel):
    county: str
    query_description: str
    amount_questioned: Optional[float]
    severity: str


class CountyIssue(BaseModel):
    county: str
    issue_description: str
    category: str


# FastAPI App
app = FastAPI(
    title="Kenya County Analytics Platform",
    description="Comprehensive API for all 47 Kenya counties with budgets, audit queries, rankings",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#: Why a summary figure is ``None``. A ``0`` here would say the counties' budgets
#: total nothing and no money is missing; the file simply does not say (#207).
SUMMARY_FIGURE_ABSENT = "not_in_county_data_file"

SUMMARY_FIGURES = (
    "total_county_budgets",
    "total_missing_funds",
    "average_financial_health",
)


def _summary_figures(summary: Dict) -> Dict:
    """Each summary figure, or ``None`` and why — ``/budget/national``'s shape."""
    out: Dict = {}
    for key in SUMMARY_FIGURES:
        value = summary.get(key)
        out[key] = value
        out[f"{key}_absent_reason"] = None if value is not None else SUMMARY_FIGURE_ABSENT
    return out


def _insight(label: str, value, fmt: str, unit: str) -> str:
    if value is None:
        return f"{label}: not in the county data file"
    return f"{label}: {value:{fmt}}{unit}"


# Load county data
try:
    with open("enhanced_county_data.json", "r") as f:
        county_data = json.load(f)
    logger.info("✅ County data loaded successfully")
except FileNotFoundError:
    logger.error("❌ County data file not found!")
    county_data = {}


@app.get("/")
async def root():
    """Root endpoint with county analytics overview."""
    if not county_data:
        return {"error": "County data not available"}

    summary = county_data.get("analytics_summary", {})

    return {
        "message": "Kenya County Analytics Platform",
        "description": "Analytics for the counties in the loaded county data file",
        # Counted from the file. It was a literal 47 whatever the file held.
        "total_counties": len(county_data.get("county_data", {})),
        **_summary_figures(summary),
        "endpoints": [
            "/counties/all",
            "/counties/{county_name}",
            "/counties/search",
            "/rankings/{metric}",
            "/audit/queries",
            "/audit/missing-funds",
            "/analytics/summary",
        ],
    }


@app.get("/counties/all", response_model=List[CountySummary])
async def get_all_counties(
    limit: int = Query(47, description="Number of counties to return")
):
    """Get all counties with comprehensive data."""
    if not county_data:
        raise HTTPException(status_code=500, detail="County data not available")

    counties = []
    for county_name, data in list(county_data.get("county_data", {}).items())[:limit]:
        counties.append(
            CountySummary(
                county=county_name,
                population=data["population"],
                budget_2025=data["budget_2025"],
                revenue_2024=data["revenue_2024"],
                debt_outstanding=data["debt_outstanding"],
                pending_bills=data["pending_bills"],
                loans_received=data.get("loans_received"),
                audit_rating=data["audit_rating"],
                missing_funds=data["missing_funds"],
                financial_health_score=data["financial_health_score"],
                budget_execution_rate=data["budget_execution_rate"],
            )
        )

    return counties


@app.get("/counties/{county_name}")
async def get_county_details(county_name: str):
    """Get detailed information for a specific county."""
    if not county_data:
        raise HTTPException(status_code=500, detail="County data not available")

    counties = county_data.get("county_data", {})

    # Find county (case insensitive)
    county_info = None
    for name, data in counties.items():
        if name.lower() == county_name.lower():
            county_info = data
            county_name = name
            break

    if not county_info:
        raise HTTPException(status_code=404, detail=f"County '{county_name}' not found")

    return {
        "county": county_name,
        "basic_info": {
            "population": county_info["population"],
            "budget_2025": county_info["budget_2025"],
            "revenue_2024": county_info["revenue_2024"],
            "per_capita_budget": county_info["per_capita_budget"],
        },
        "financial_metrics": {
            "debt_outstanding": county_info["debt_outstanding"],
            "pending_bills": county_info["pending_bills"],
            "loans_received": county_info.get("loans_received"),
            "missing_funds": county_info["missing_funds"],
            "budget_execution_rate": county_info["budget_execution_rate"],
            "debt_to_budget_ratio": county_info["debt_to_budget_ratio"],
            "financial_health_score": county_info["financial_health_score"],
        },
        "audit_information": {
            "audit_rating": county_info["audit_rating"],
            "audit_queries": county_info.get("audit_queries", []),
            "major_issues": county_info.get("major_issues", []),
        },
    }


@app.get("/counties/search")
async def search_counties(
    query: Optional[str] = Query(None, description="Search county names"),
    min_budget: Optional[float] = Query(None, description="Minimum budget"),
    max_debt_ratio: Optional[float] = Query(None, description="Maximum debt ratio"),
    audit_rating: Optional[str] = Query(None, description="Audit rating filter"),
    limit: int = Query(20, description="Maximum results"),
):
    """Search counties with various filters."""
    if not county_data:
        raise HTTPException(status_code=500, detail="County data not available")

    counties = county_data.get("county_data", {})
    results = []

    for county_name, data in counties.items():
        # Apply filters
        if query and query.lower() not in county_name.lower():
            continue
        if min_budget and data["budget_2025"] < min_budget:
            continue
        if max_debt_ratio and data["debt_to_budget_ratio"] > max_debt_ratio:
            continue
        if audit_rating and data["audit_rating"] != audit_rating:
            continue

        results.append(
            {
                "county": county_name,
                "budget_2025": data["budget_2025"],
                "debt_to_budget_ratio": data["debt_to_budget_ratio"],
                "audit_rating": data["audit_rating"],
                "financial_health_score": data["financial_health_score"],
                "missing_funds": data["missing_funds"],
            }
        )

        if len(results) >= limit:
            break

    return {"total_found": len(results), "counties": results}


@app.get("/rankings/{metric}", response_model=List[CountyRanking])
async def get_county_rankings(
    metric: str,
    order: str = Query(
        "desc", description="'asc' for ascending, 'desc' for descending"
    ),
    limit: int = Query(10, description="Number of counties to return"),
):
    """Get county rankings by various metrics."""
    if not county_data:
        raise HTTPException(status_code=500, detail="County data not available")

    counties = county_data.get("county_data", {})

    # Map metric names to data fields
    metric_mapping = {
        "budget": "budget_2025",
        "debt": "debt_outstanding",
        "missing-funds": "missing_funds",
        "health-score": "financial_health_score",
        "execution-rate": "budget_execution_rate",
        "per-capita": "per_capita_budget",
        "debt-ratio": "debt_to_budget_ratio",
    }

    if metric not in metric_mapping:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metric. Available: {list(metric_mapping.keys())}",
        )

    field = metric_mapping[metric]
    reverse = order == "desc"

    # Sort counties by the metric
    sorted_counties = sorted(
        counties.items(), key=lambda x: x[1][field], reverse=reverse
    )

    rankings = []
    for rank, (county_name, data) in enumerate(sorted_counties[:limit], 1):
        rankings.append(
            CountyRanking(
                rank=rank, county=county_name, value=data[field], metric=metric
            )
        )

    return rankings


@app.get("/audit/queries", response_model=List[CountyAuditQuery])
async def get_audit_queries(
    county: Optional[str] = Query(None, description="Filter by county"),
    limit: int = Query(50, description="Maximum results"),
):
    """Get audit queries across all counties."""
    if not county_data:
        raise HTTPException(status_code=500, detail="County data not available")

    counties = county_data.get("county_data", {})
    audit_queries = []

    for county_name, data in counties.items():
        if county and county.lower() not in county_name.lower():
            continue

        queries = data.get("audit_queries", [])
        for query in queries:
            # Extract amount if mentioned
            amount = None
            if "KES" in query:
                try:
                    # Simple extraction of numbers before 'KES'
                    parts = query.split("KES")[0].strip().split()
                    for part in reversed(parts):
                        if any(c.isdigit() for c in part):
                            # Convert formats like 1.2B, 650M to actual numbers
                            num_str = "".join(
                                c for c in part if c.isdigit() or c in ".BM"
                            )
                            if "B" in num_str:
                                amount = float(num_str.replace("B", "")) * 1000000000
                            elif "M" in num_str:
                                amount = float(num_str.replace("M", "")) * 1000000
                            break
                except:
                    pass

            audit_queries.append(
                CountyAuditQuery(
                    county=county_name,
                    query_description=query,
                    amount_questioned=amount,
                    severity="medium",  # Default severity
                )
            )

    return audit_queries[:limit]


@app.get("/audit/missing-funds")
async def get_missing_funds_analysis():
    """Get comprehensive missing funds analysis."""
    if not county_data:
        raise HTTPException(status_code=500, detail="County data not available")

    counties = county_data.get("county_data", {})

    # Calculate missing funds statistics
    county_missing_funds = []
    total_missing = 0

    for county_name, data in counties.items():
        missing = data["missing_funds"]
        total_missing += missing

        county_missing_funds.append(
            {
                "county": county_name,
                "missing_funds": missing,
                "missing_funds_ratio": data["missing_funds_ratio"],
                "budget_2025": data["budget_2025"],
            }
        )

    # Sort by missing funds amount
    county_missing_funds.sort(key=lambda x: x["missing_funds"], reverse=True)

    return {
        "total_missing_funds": total_missing,
        "counties_affected": len(
            [c for c in county_missing_funds if c["missing_funds"] > 0]
        ),
        "worst_offenders": county_missing_funds[:10],
        "average_missing_ratio": round(
            sum([c["missing_funds_ratio"] for c in county_missing_funds])
            / len(county_missing_funds),
            2,
        ),
        "summary": f"Total of {total_missing:,.0f} KES missing across {len(counties)} counties",
    }


@app.get("/analytics/summary")
async def get_analytics_summary():
    """Get comprehensive county analytics summary."""
    if not county_data:
        raise HTTPException(status_code=500, detail="County data not available")

    summary = county_data.get("analytics_summary", {})
    rankings = county_data.get("county_rankings", {})

    # Get top performers
    top_health = rankings.get("by_financial_health", [])[:5]
    top_budget = rankings.get("by_budget_size", [])[:5]
    worst_debt = rankings.get("worst_debt_ratio", [])[:5]

    return {
        "overall_statistics": summary,
        "top_performers": {
            "financial_health": [
                {"county": county, "score": data["financial_health_score"]}
                for county, data in top_health
            ],
            "largest_budgets": [
                {"county": county, "budget": data["budget_2025"]}
                for county, data in top_budget
            ],
            "highest_debt_ratios": [
                {"county": county, "debt_ratio": data["debt_to_budget_ratio"]}
                for county, data in worst_debt
            ],
        },
        "key_insights": [
            _insight(
                "Total county budgets",
                summary.get("total_county_budgets"),
                ",.0f",
                " KES",
            ),
            _insight(
                "Average financial health",
                summary.get("average_financial_health"),
                "",
                "%",
            ),
            _insight(
                "Total missing funds",
                summary.get("total_missing_funds"),
                ",.0f",
                " KES",
            ),
            f"Counties with debt issues: {len([c for c in worst_debt if c[1]['debt_to_budget_ratio'] > 30])}",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    print("🚀 Starting Kenya County Analytics Platform...")
    print(f"🏛️ Counties in the data file: {len(county_data.get('county_data', {}))}")
    print("💰 Comprehensive budget, audit, and ranking data")
    print("🌐 API Documentation: http://localhost:8002/docs")
    uvicorn.run(app, host="0.0.0.0", port=8002)

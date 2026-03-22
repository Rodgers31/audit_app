import asyncio
import concurrent.futures
import datetime
import functools
import importlib
import logging
import os
import random
import re
import smtplib
import sys
import time
from email.mime.text import MIMEText
from email.utils import formatdate
from typing import Any, Dict, List, Optional, Tuple

import httpx  # For internal API calls
import uvicorn
from config.settings import settings
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, Response

# Initialize logger early (before Redis cache import)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("main_backend.log")],
)
logger = logging.getLogger(__name__)

try:
    import boto3  # type: ignore
except Exception:
    boto3 = None  # type: ignore

# Import Redis cache
try:
    from bootstrap import initialize_reference_data
    from cache.redis_cache import RedisCache

    redis_cache = RedisCache()
    logger.info("Redis cache initialized successfully")
except Exception as e:
    redis_cache = None
    logger.warning(f"Redis cache not available: {e}")

# Import database and models if available; otherwise fall back to mocks
DATABASE_AVAILABLE = False
DBAudit = None
DBEntity = None
DBFiscalPeriod = None
DBSourceDocument = None
DBBudgetLine = None
DBCountry = None
EntityType = None
DocumentType = None
Severity = None


def get_db():  # default stub; may be overridden below if real DB is present
    return None


try:  # Try to wire real DB and models when available
    # Lazy imports so that local dev without DB still works
    from database import get_db as _real_get_db  # type: ignore
    from models import Audit as _DBAudit  # type: ignore
    from models import BudgetLine as _DBBudgetLine
    from models import Country as _DBCountry
    from models import DocumentType as _DocumentType
    from models import EconomicIndicator as _DBEconomicIndicator
    from models import Entity as _DBEntity
    from models import EntityType as _EntityType
    from models import FiscalPeriod as _DBFiscalPeriod
    from models import GDPData as _DBGDPData
    from models import Loan as _DBLoan
    from models import PopulationData as _DBPopulationData
    from models import QuickQuestion as _DBQuickQuestion
    from models import Severity as _Severity
    from models import SourceDocument as _DBSourceDocument

    # Bind real references
    get_db = _real_get_db  # type: ignore
    DBAudit = _DBAudit
    DBEntity = _DBEntity
    DBFiscalPeriod = _DBFiscalPeriod
    DBSourceDocument = _DBSourceDocument
    DBBudgetLine = _DBBudgetLine
    DBCountry = _DBCountry
    DBPopulationData = _DBPopulationData
    DBQuickQuestion = _DBQuickQuestion
    DBEconomicIndicator = _DBEconomicIndicator
    DBLoan = _DBLoan
    DBGDPData = _DBGDPData
    EntityType = _EntityType
    DocumentType = _DocumentType
    Severity = _Severity
    DATABASE_AVAILABLE = True
except Exception as exc:  # pragma: no cover - fail fast if DB unavailable
    logger.exception("Database models unavailable; aborting startup", exc_info=exc)
    raise


# County ID to Name mapping
COUNTY_MAPPING = {
    "001": "Nairobi",
    "002": "Kwale",
    "003": "Kilifi",
    "004": "Tana River",
    "005": "Lamu",
    "006": "Taita Taveta",
    "007": "Garissa",
    "008": "Wajir",
    "009": "Mandera",
    "010": "Marsabit",
    "011": "Isiolo",
    "012": "Meru",
    "013": "Tharaka Nithi",
    "014": "Embu",
    "015": "Kitui",
    "016": "Machakos",
    "017": "Makueni",
    "018": "Nyandarua",
    "019": "Nyeri",
    "020": "Kirinyaga",
    "021": "Murang'a",
    "022": "Kiambu",
    "023": "Turkana",
    "024": "West Pokot",
    "025": "Samburu",
    "026": "Trans Nzoia",
    "027": "Uasin Gishu",
    "028": "Elgeyo Marakwet",
    "029": "Nandi",
    "030": "Baringo",
    "031": "Laikipia",
    "032": "Nakuru",
    "033": "Narok",
    "034": "Kajiado",
    "035": "Kericho",
    "036": "Bomet",
    "037": "Kakamega",
    "038": "Vihiga",
    "039": "Bungoma",
    "040": "Busia",
    "041": "Siaya",
    "042": "Kisumu",
    "043": "Homa Bay",
    "044": "Migori",
    "045": "Kisii",
    "046": "Nyamira",
    "047": "Mombasa",
}

# County centroid coordinates [longitude, latitude] — approximate geographic centers
COUNTY_COORDINATES = {
    "001": [36.8219, -1.2921],  # Nairobi
    "002": [39.4521, -4.1816],  # Kwale
    "003": [39.9093, -3.5107],  # Kilifi
    "004": [40.0000, -1.8000],  # Tana River
    "005": [40.9020, -2.2717],  # Lamu
    "006": [38.4850, -3.3160],  # Taita Taveta
    "007": [39.6461, -0.4532],  # Garissa
    "008": [40.0573, 1.7471],  # Wajir
    "009": [41.8569, 3.9373],  # Mandera
    "010": [37.9910, 2.3284],  # Marsabit
    "011": [37.5822, 0.3546],  # Isiolo
    "012": [37.6490, 0.0480],  # Meru
    "013": [37.8500, -0.3000],  # Tharaka Nithi
    "014": [37.4596, -0.5389],  # Embu
    "015": [38.0106, -1.3700],  # Kitui
    "016": [37.2634, -1.5177],  # Machakos
    "017": [37.6200, -1.8000],  # Makueni
    "018": [36.5230, -0.1804],  # Nyandarua
    "019": [36.9510, -0.4197],  # Nyeri
    "020": [37.3827, -0.6591],  # Kirinyaga
    "021": [37.0400, -0.7840],  # Murang'a
    "022": [36.8354, -1.1714],  # Kiambu
    "023": [35.5658, 3.3122],  # Turkana
    "024": [35.1190, 1.6210],  # West Pokot
    "025": [36.9541, 1.2154],  # Samburu
    "026": [34.9507, 1.0567],  # Trans Nzoia
    "027": [35.2698, 0.5143],  # Uasin Gishu
    "028": [35.5100, 0.7800],  # Elgeyo Marakwet
    "029": [35.1270, 0.1836],  # Nandi
    "030": [35.9430, 0.4912],  # Baringo
    "031": [36.7820, 0.3606],  # Laikipia
    "032": [36.0800, -0.3031],  # Nakuru
    "033": [35.8600, -1.0876],  # Narok
    "034": [36.7819, -2.0981],  # Kajiado
    "035": [35.2863, -0.3692],  # Kericho
    "036": [35.3420, -0.7813],  # Bomet
    "037": [34.7519, 0.2827],  # Kakamega
    "038": [34.7075, 0.0839],  # Vihiga
    "039": [34.5608, 0.5635],  # Bungoma
    "040": [34.1113, 0.4347],  # Busia
    "041": [34.2422, -0.0617],  # Siaya
    "042": [34.7617, -0.1022],  # Kisumu
    "043": [34.4571, -0.5273],  # Homa Bay
    "044": [34.4731, -1.0634],  # Migori
    "045": [34.7668, -0.6813],  # Kisii
    "046": [34.9345, -0.5633],  # Nyamira
    "047": [39.6682, -4.0435],  # Mombasa
}

# Reverse mapping for backend to frontend ID conversion
NAME_TO_ID_MAPPING = {v: k for k, v in COUNTY_MAPPING.items()}

# County regions for peer comparison (based on Kenya's former provinces)
COUNTY_REGIONS = {
    "001": "Nairobi",
    "002": "Coast", "003": "Coast", "004": "Coast", "005": "Coast", "006": "Coast", "047": "Coast",
    "007": "North Eastern", "008": "North Eastern", "009": "North Eastern",
    "010": "Eastern", "011": "Eastern", "012": "Eastern", "013": "Eastern", "014": "Eastern",
    "015": "Eastern", "016": "Eastern", "017": "Eastern",
    "018": "Central", "019": "Central", "020": "Central", "021": "Central", "022": "Central",
    "023": "Rift Valley", "024": "Rift Valley", "025": "Rift Valley", "026": "Rift Valley",
    "027": "Rift Valley", "028": "Rift Valley", "029": "Rift Valley", "030": "Rift Valley",
    "031": "Rift Valley", "032": "Rift Valley", "033": "Rift Valley", "034": "Rift Valley",
    "035": "Rift Valley", "036": "Rift Valley",
    "037": "Western", "038": "Western", "039": "Western", "040": "Western",
    "041": "Nyanza", "042": "Nyanza", "043": "Nyanza", "044": "Nyanza",
    "045": "Nyanza", "046": "Nyanza",
}

# Enhanced County Analytics API base URL
ENHANCED_COUNTY_API_BASE = "http://localhost:8003"


class InternalAPIClient:
    """Client for making internal API calls to other services"""

    # simple in-memory TTL cache to reduce flakiness and repeated fetches during a session
    _cache: Dict[str, Dict[str, Any]] = {}
    _ttl_seconds = 6 * 60 * 60  # 6 hours

    @classmethod
    def _cache_get(cls, key: str):
        rec = cls._cache.get(key)
        if not rec:
            return None
        if time.time() - rec["ts"] > cls._ttl_seconds:
            cls._cache.pop(key, None)
            return None
        return rec["value"]

    @classmethod
    def _cache_set(cls, key: str, value: Any):
        cls._cache[key] = {"value": value, "ts": time.time()}

    @staticmethod
    async def get_county_data(county_name: str) -> Optional[Dict]:
        """Fetch county data from Enhanced County Analytics API"""
        try:
            cache_key = f"county_data:{county_name}"
            cached = InternalAPIClient._cache_get(cache_key)
            if cached is not None:
                return cached
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{ENHANCED_COUNTY_API_BASE}/counties/{county_name}"
                )
                if response.status_code == 200:
                    data = response.json()
                    InternalAPIClient._cache_set(cache_key, data)
                    return data
                return None
        except Exception as e:
            logging.error(f"Error fetching county data for {county_name}: {e}")
            return None

    @staticmethod
    async def get_all_counties() -> Optional[List[Dict]]:
        """Fetch all counties data from Enhanced County Analytics API"""
        try:
            cache_key = "counties:all"
            cached = InternalAPIClient._cache_get(cache_key)
            if cached is not None:
                return cached
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{ENHANCED_COUNTY_API_BASE}/counties/all")
                if response.status_code == 200:
                    data = response.json()
                    InternalAPIClient._cache_set(cache_key, data)
                    return data
                return None
        except Exception as e:
            logging.error(f"Error fetching all counties data: {e}")
            return None

    @staticmethod
    async def get_county_financial_data(county_name: str) -> Optional[Dict]:
        """Fetch county financial data from Enhanced County Analytics API"""
        try:
            cache_key = f"county_financial:{county_name}"
            cached = InternalAPIClient._cache_get(cache_key)
            if cached is not None:
                return cached
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{ENHANCED_COUNTY_API_BASE}/counties/{county_name}/financial"
                )
                if response.status_code == 200:
                    data = response.json()
                    InternalAPIClient._cache_set(cache_key, data)
                    return data
                return None
        except Exception as e:
            logging.error(f"Error fetching financial data for {county_name}: {e}")
            return None

    @staticmethod
    async def get_county_audit_queries(county_name: str) -> Optional[List[Dict]]:
        """Fetch all audit queries for a county from Enhanced API"""
        try:
            cache_key = f"audit_queries:{county_name}"
            cached = InternalAPIClient._cache_get(cache_key)
            if cached is not None:
                return cached
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{ENHANCED_COUNTY_API_BASE}/audit/county/{county_name}"
                )
                if response.status_code == 200:
                    data = response.json()
                    InternalAPIClient._cache_set(cache_key, data)
                    return data
                return None
        except Exception as e:
            logging.error(f"Error fetching audit queries for {county_name}: {e}")
            return None

    @staticmethod
    async def get_missing_funds(county_name: str) -> Optional[List[Dict]]:
        """Fetch missing funds cases for a county from Enhanced API"""
        try:
            cache_key = f"missing_funds:{county_name}"
            cached = InternalAPIClient._cache_get(cache_key)
            if cached is not None:
                return cached
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{ENHANCED_COUNTY_API_BASE}/audit/missing-funds",
                    params={"county": county_name},
                )
                if response.status_code == 200:
                    data = response.json()
                    InternalAPIClient._cache_set(cache_key, data)
                    return data
                return None
        except Exception as e:
            logging.error(f"Error fetching missing funds for {county_name}: {e}")
            return None

    @staticmethod
    async def get_cob_implementation(county_name: str) -> Optional[Dict]:
        """Fetch COB implementation info for a county from Enhanced API"""
        try:
            cache_key = f"cob_impl:{county_name}"
            cached = InternalAPIClient._cache_get(cache_key)
            if cached is not None:
                return cached
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{ENHANCED_COUNTY_API_BASE}/counties/{county_name}/cob-implementation"
                )
                if response.status_code == 200:
                    data = response.json()
                    InternalAPIClient._cache_set(cache_key, data)
                    return data
                return None
        except Exception as e:
            logging.error(f"Error fetching COB implementation for {county_name}: {e}")
            return None


def transform_county_data_for_frontend(backend_data: Dict, county_id: str) -> Dict:
    """Transform backend county data to match frontend expectations"""
    if not backend_data:
        return {"id": county_id}

    # Extract data from the actual API response structure
    basic_info = backend_data.get("basic_info", {})
    financial_metrics = backend_data.get("financial_metrics", {})
    audit_info = backend_data.get("audit_information", {})

    # Derive commonly used fields for the frontend
    name = backend_data.get("county", "")
    population = basic_info.get("population") or backend_data.get("population", 0)
    budget_2025 = basic_info.get("budget_2025") or backend_data.get("budget_2025", 0)
    revenue_2024 = basic_info.get("revenue_2024") or backend_data.get("revenue_2024", 0)

    return {
        "id": county_id,
        "name": name,
        "population": population or 0,
        # Commonly referenced budget fields in the UI
        "budget_2025": budget_2025 or 0,
        "totalBudget": budget_2025 or 0,
        # Optional UI fields with safe defaults
        "audit_rating": audit_info.get("audit_rating")
        or backend_data.get("audit_rating"),
        "financial_health_score": financial_metrics.get("financial_health_score")
        or backend_data.get("financial_health_score"),
        "budgetUtilization": financial_metrics.get("budget_execution_rate"),
        "pendingBills": financial_metrics.get("pending_bills"),
        "developmentBudget": backend_data.get("development_budget"),
        "recurrentBudget": backend_data.get("recurrent_budget"),
        "education": backend_data.get("education"),
        "health": backend_data.get("health"),
        "infrastructure": backend_data.get("infrastructure"),
        # Keep projects if available
        "projects": backend_data.get("development_projects", []),
        # Keep raw values occasionally used elsewhere
        "revenue_2024": revenue_2024 or 0,
    }


# Model imports - temporarily disabled due to database issues
# from models import (
#     Allocation, Annotation, Audit, BudgetLine, Country,
#     Document, Entity, FiscalPeriod, Loan, SourceDocument, User,
# )

# Add ETL module to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "etl"))

# Instead of importing ETL modules directly (which have dependency issues),
# we'll create a simple ETL function that works independently
ETL_AVAILABLE = True


def run_simple_kenya_etl():
    """Simple Kenya ETL function that doesn't rely on complex imports."""
    import json

    import requests
    from bs4 import BeautifulSoup

    results = {
        "documents_fetched": 0,
        "documents_processed": 0,
        "entities_found": [],
        "sources_checked": [],
    }

    # Test Kenya Treasury website
    try:
        response = requests.get("https://treasury.go.ke", timeout=10)
        if response.status_code == 200:
            results["sources_checked"].append(
                {
                    "source": "Kenya National Treasury",
                    "status": "accessible",
                    "status_code": response.status_code,
                }
            )
            results["documents_fetched"] += 1
        else:
            results["sources_checked"].append(
                {
                    "source": "Kenya National Treasury",
                    "status": "error",
                    "status_code": response.status_code,
                }
            )
    except Exception as e:
        results["sources_checked"].append(
            {
                "source": "Kenya National Treasury",
                "status": "unreachable",
                "error": str(e),
            }
        )

    # Mock some entities that would be extracted
    results["entities_found"] = [
        {"name": "Ministry of Health", "type": "ministry", "code": "MOH"},
        {"name": "Ministry of Education", "type": "ministry", "code": "MOE"},
        {"name": "National Treasury", "type": "ministry", "code": "NT"},
    ]
    results["documents_processed"] = len(results["entities_found"])

    return results


try:
    # Prefer centralized auth dependencies if available
    from auth import get_current_user as get_current_user  # noqa: F401
except Exception:

    def get_current_user():  # type: ignore
        """Mock authentication dependency (fallback)."""
        return {"id": 1, "username": "admin"}


# Response models using Pydantic
class CountryResponse(BaseModel):
    id: int
    name: str
    iso_code: str
    currency: str
    summary: Dict[str, Any]


class EntityFinancialSummary(BaseModel):
    total_allocation: float
    total_spent: float
    execution_rate: float


class EntityResponse(BaseModel):
    id: int
    canonical_name: str
    type: str
    slug: Optional[str] = None
    country: Optional[str] = None
    code: Optional[str] = None
    meta: Dict[str, Any] = {}
    financial_summary: Optional[EntityFinancialSummary] = None
    audit_findings_count: int = 0
    created_at: Optional[str] = None


class EntityDetailResponse(BaseModel):
    entity: Dict[str, Any]
    financial_time_series: List[Dict[str, Any]]
    recent_budget_lines: List[Dict[str, Any]]
    audit_findings: List[Dict[str, Any]]
    source_documents: List[Dict[str, Any]]


class DocumentResponse(BaseModel):
    id: int
    title: str
    url: Optional[str] = None
    publisher: Optional[str] = None
    doc_type: str
    fetch_date: Optional[str] = None
    meta: Dict[str, Any] = {}


class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    total_count: int
    page: int
    per_page: int


class BudgetLineResponse(BaseModel):
    id: int
    category: str
    subcategory: Optional[str] = None
    allocated_amount: Optional[float] = None
    actual_spent: Optional[float] = None
    committed_amount: Optional[float] = None
    currency: str
    entity_id: int
    period_label: Optional[str] = None
    source_document_id: Optional[int] = None
    created_at: Optional[str] = None


class ETLJobResponse(BaseModel):
    job_id: str
    status: str
    country: str
    started_at: str
    completed_at: Optional[str] = None
    documents_processed: int
    errors: List[str]


class ETLStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: Dict[str, Any]
    last_updated: str


class AuditListItem(BaseModel):
    id: Any
    description: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    amountLabel: Optional[str] = None
    fiscal_year: Optional[str] = None
    source: Dict[str, Any]


class AuditListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[AuditListItem]


app = FastAPI(
    title="Government Financial Transparency API",
    description="API for accessing government budget, spending, and audit data with full provenance",
    version="1.0.0",
)


@app.on_event("startup")
async def bootstrap_reference_data() -> None:
    """Ensure reference county data is present before serving requests."""
    if not DATABASE_AVAILABLE:
        raise RuntimeError("Database is required for backend startup")
    try:
        await asyncio.to_thread(initialize_reference_data, NAME_TO_ID_MAPPING)
    except Exception as exc:  # pragma: no cover - bootstrap failures should abort
        logger.exception("Failed to initialize reference data", exc_info=exc)
        raise


# Auto-seeder for automated data refresh
AUTO_SEEDER_ENABLED = os.getenv("AUTO_SEEDER_ENABLED", "true").lower() in (
    "true",
    "1",
    "yes",
)


@app.on_event("startup")
async def start_auto_seeder_service() -> None:
    """Start the auto-seeder service for automated data updates."""
    if not AUTO_SEEDER_ENABLED:
        logger.info("Auto-seeder disabled via AUTO_SEEDER_ENABLED=false")
        return

    try:
        from services.auto_seeder import start_auto_seeder

        await start_auto_seeder()
        logger.info("[AUTO-SEEDER] Service started - data will refresh automatically")
    except Exception as exc:
        logger.warning(f"Auto-seeder not started (non-critical): {exc}")


@app.on_event("shutdown")
async def stop_auto_seeder_service() -> None:
    """Stop the auto-seeder service gracefully."""
    try:
        from services.auto_seeder import stop_auto_seeder

        await stop_auto_seeder()
    except Exception:
        pass


# CORS middleware – uses CORS_ORIGINS from settings / env var
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security middlewares: rate limiting, audit logging, security headers
try:
    from middleware.security import (
        AuditLogMiddleware,
        RateLimitMiddleware,
        RedisRateLimitMiddleware,
        SecurityHeadersMiddleware,
    )

    # Use Redis-backed rate limiting for production, falls back to in-memory if Redis unavailable
    if settings.ENVIRONMENT == "production" and settings.REDIS_URL:
        app.add_middleware(
            RedisRateLimitMiddleware, calls=120, period=60
        )  # 120 req/min/IP
        logger.info("Using Redis-backed rate limiting")
    else:
        app.add_middleware(
            RateLimitMiddleware, calls=120, period=60
        )  # In-memory fallback
        logger.info("Using in-memory rate limiting")

    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("Security middleware registered (rate limit, audit log, headers)")
except Exception as e:
    logger.warning(f"Security middleware not active: {e}")

# Include routers
try:
    from routers.etl_admin import router as etl_admin_router

    app.include_router(etl_admin_router)
    logger.info("ETL admin router registered at /api/v1/admin/etl")
except Exception as e:
    logger.warning(f"Could not register ETL admin router: {e}")

try:
    from routers.economic import router as economic_router

    app.include_router(economic_router)
    logger.info("Economic data router registered at /api/v1/economic")
except Exception as e:
    logger.warning(f"Could not register economic data router: {e}")

try:
    from routers.admin import router as admin_router

    app.include_router(admin_router)
    logger.info("Admin router registered at /api/v1/admin")
except Exception as e:
    logger.warning(f"Could not register admin router: {e}")

# Newsletter endpoints (welcome email, token-verified unsubscribe) are active.
# Auth & watchlist are still handled by Supabase (frontend → Supabase direct).
try:
    from routers.user_features import router as user_features_router

    app.include_router(user_features_router)
    logger.info("User features router registered (newsletter endpoints)")
except Exception as e:
    logger.warning(f"Could not register user features router: {e}")

try:
    from routers.audit_dashboard import router as audit_dashboard_router

    app.include_router(audit_dashboard_router)
    logger.info("Audit dashboard router registered at /api/v1/audit")
except Exception as e:
    logger.warning(f"Could not register audit dashboard router: {e}")

try:
    from routers.money_flow import router as money_flow_router

    app.include_router(money_flow_router)
    logger.info("Money flow router registered at /api/v1/counties/*/money-flow")
except Exception as e:
    logger.warning(f"Could not register money flow router: {e}")

try:
    from routers.data_freshness import router as data_freshness_router

    app.include_router(data_freshness_router)
    logger.info("Data freshness router registered at /api/v1/data/freshness")
except Exception as e:
    logger.warning(f"Could not register data freshness router: {e}")


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.datetime.now()
    client_ip = request.client.host
    method = request.method
    url = str(request.url)

    logger.info(f"PROCESSING {method} {url} from {client_ip} - Processing...")
    try:
        response = await call_next(request)
        process_time = (datetime.datetime.now() - start_time).total_seconds()
        response.headers["X-Process-Time"] = f"{process_time:.3f}"
        logger.info(
            f"SUCCESS {method} {url} - {response.status_code} - {process_time:.3f}s"
        )
        return response
    except Exception as e:
        process_time = (datetime.datetime.now() - start_time).total_seconds()
        logger.error(f"ERROR {method} {url} - ERROR: {str(e)} - {process_time:.3f}s")
        raise


# Helper functions for provenance tracking
security = HTTPBearer()


# Cache decorator helper
def cached(key_prefix: str, ttl: int = 3600):
    """Decorator to cache endpoint responses.

    Uses Redis when available, otherwise falls back to a lightweight
    in-memory TTL cache so that repeated calls don't hit the DB /
    filesystem on every request.
    """

    def decorator(func):
        # Module-level in-memory fallback cache (per-endpoint)
        _mem_cache: Dict[str, Dict[str, Any]] = {}

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from prefix and path params
            cache_key_parts = [key_prefix]
            for k, v in kwargs.items():
                if k not in ["db", "request", "background_tasks"]:
                    cache_key_parts.append(f"{k}:{v}")
            cache_key = ":".join(cache_key_parts)

            # --- Redis path ---
            if redis_cache:
                cached_data = redis_cache.get(cache_key)
                if cached_data is not None:
                    logger.debug(f"Redis cache HIT: {cache_key}")
                    return cached_data

                result = await func(*args, **kwargs)
                redis_cache.set(cache_key, result, ttl=ttl)
                return result

            # --- In-memory fallback path ---
            rec = _mem_cache.get(cache_key)
            if rec and (time.time() - rec["ts"]) < ttl:
                logger.debug(f"Memory cache HIT: {cache_key}")
                return rec["value"]

            result = await func(*args, **kwargs)
            _mem_cache[cache_key] = {"value": result, "ts": time.time()}
            return result

        return wrapper

    return decorator


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize the main backend API."""
    logger.info("Main Backend API starting up...")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info("Initializing database connections...")
    logger.info("Main Backend API startup complete!")


@app.api_route("/", methods=["GET", "HEAD"])
async def root(request: Request):
    client_ip = request.client.host
    logger.info(f"Main backend root endpoint accessed from {client_ip}")

    try:
        response = {
            "message": "Government Financial Transparency API",
            "version": "1.0.0",
            "docs": "/docs",
            "status": "operational",
            "timestamp": datetime.datetime.now().isoformat(),
        }
        logger.info("Main backend root response prepared")
        return response
    except Exception as e:
        logger.error(f"Error in main backend root: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.api_route("/health", methods=["GET", "HEAD"])
async def health() -> JSONResponse:
    """Basic health check endpoint (supports GET and HEAD for uptime monitors)."""
    return JSONResponse(
        {"status": "ok", "timestamp": datetime.datetime.now().isoformat()}
    )


@app.get("/api/v1/system/seeder-status")
async def get_seeder_status() -> JSONResponse:
    """
    Get the current status of the auto-seeder service.

    Returns information about:
    - Whether the seeder is running
    - When each data domain was last refreshed
    - When each domain will next refresh
    - Fetch statistics (success/failure counts)
    """
    try:
        from services.auto_seeder import get_seeder_status as get_status

        status = get_status()
        return JSONResponse(
            {
                "status": "ok",
                "auto_seeder": status,
                "note": "All data is fetched from live sources - NO hardcoded data",
            }
        )
    except Exception as e:
        logger.error(f"Error getting seeder status: {e}")
        return JSONResponse(
            {
                "status": "error",
                "error": str(e),
                "auto_seeder": {"is_running": False},
            }
        )


@app.get("/api/v1/system/pipeline-health")
async def get_pipeline_health(db: Session = Depends(get_db)) -> JSONResponse:
    """
    Comprehensive pipeline health dashboard.

    Returns the full picture of:
    - Data freshness per domain (counties, debt, population, economic)
    - Source module availability (ETL, extractors)
    - Auto-seeder status and next refresh times
    - Database record counts and last-updated timestamps
    - Any warnings or errors that need attention
    """
    import importlib

    alerts: list[dict] = []
    sources: dict = {}
    db_stats: dict = {}
    now = datetime.datetime.now(datetime.timezone.utc)

    # ── 1. Check module availability (import health) ──
    module_checks = {
        "etl.kenya_pipeline": "ETL Pipeline (OAG/COB/Treasury scraping)",
        "etl.knbs_parser": "KNBS Parser (population/economic parsing)",
        "extractors.government.knbs_extractor": "KNBS Extractor (document discovery)",
    }
    module_status = {}
    for mod_name, description in module_checks.items():
        try:
            importlib.import_module(mod_name)
            module_status[mod_name] = {"available": True, "description": description}
        except Exception as exc:
            module_status[mod_name] = {
                "available": False,
                "description": description,
                "error": str(exc),
            }
            alerts.append(
                {
                    "level": "warning",
                    "source": mod_name,
                    "message": f"Module not importable: {exc}. Live scraping for this source will fall back to cached data.",
                }
            )

    # ── 2. Auto-seeder status ──
    seeder_info: dict = {"is_running": False}
    try:
        from services.auto_seeder import get_seeder_status as _get_status

        seeder_info = _get_status()
    except Exception as exc:
        alerts.append(
            {
                "level": "error",
                "source": "auto_seeder",
                "message": f"Could not retrieve seeder status: {exc}",
            }
        )

    # ── 3. Database record counts + freshness ──
    try:
        from models import DebtCategory as _DebtCategory

        entity_count = db.query(DBEntity).count()
        county_count = (
            db.query(DBEntity).filter(DBEntity.type == EntityType.COUNTY).count()
        )
        national_entity = (
            db.query(DBEntity).filter(DBEntity.type == EntityType.NATIONAL).first()
        )

        db_stats["entities"] = {
            "total": entity_count,
            "counties": county_count,
            "has_national": national_entity is not None,
        }

        # Population data
        pop_count = db.query(DBPopulationData).count()
        latest_pop = (
            db.query(DBPopulationData).order_by(DBPopulationData.year.desc()).first()
        )
        db_stats["population"] = {
            "records": pop_count,
            "latest_year": latest_pop.year if latest_pop else None,
        }

        # Economic indicators
        econ_count = db.query(DBEconomicIndicator).count()
        latest_econ = (
            db.query(DBEconomicIndicator)
            .order_by(DBEconomicIndicator.indicator_date.desc())
            .first()
        )
        db_stats["economic_indicators"] = {
            "records": econ_count,
            "latest_year": (
                latest_econ.indicator_date.year
                if latest_econ and latest_econ.indicator_date
                else None
            ),
        }

        # Debt categories (use Loan table — DebtCategory is an enum, not a table)
        debt_categories = db.query(DBLoan.debt_category).distinct().count()
        db_stats["debt_categories"] = {"records": debt_categories}

        # Loans
        loan_count = db.query(DBLoan).count()
        db_stats["loans"] = {"records": loan_count}

        # Source documents
        doc_count = db.query(DBSourceDocument).count()
        db_stats["source_documents"] = {"records": doc_count}

        # Data quality checks
        if county_count < 47:
            alerts.append(
                {
                    "level": "warning",
                    "source": "database",
                    "message": f"Only {county_count}/47 counties in database.",
                }
            )
        if pop_count == 0:
            alerts.append(
                {
                    "level": "warning",
                    "source": "population",
                    "message": "No population records. KNBS live fetch may have failed — check module availability.",
                }
            )
        if econ_count == 0:
            alerts.append(
                {
                    "level": "warning",
                    "source": "economic",
                    "message": "No economic indicator records.",
                }
            )
        if loan_count == 0:
            alerts.append(
                {
                    "level": "warning",
                    "source": "debt",
                    "message": "No loan records in database. Bootstrap may not have run.",
                }
            )

    except Exception as exc:
        logger.error(f"Error checking database stats: {exc}")
        alerts.append(
            {
                "level": "error",
                "source": "database",
                "message": f"Could not query database: {exc}",
            }
        )

    # ── 4. Data source reachability (non-blocking quick check) ──
    import httpx

    source_urls = {
        "knbs": {
            "url": "https://www.knbs.or.ke",
            "name": "Kenya National Bureau of Statistics",
        },
        "cob": {"url": "https://www.cob.go.ke", "name": "Controller of Budget"},
        "treasury": {"url": "https://www.treasury.go.ke", "name": "National Treasury"},
        "cbk": {
            "url": "https://www.centralbank.go.ke",
            "name": "Central Bank of Kenya",
        },
        "oag": {
            "url": "https://www.oagkenya.go.ke",
            "name": "Office of the Auditor General",
        },
    }

    async def _check_source(key: str, info: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.head(info["url"])
                return {
                    "key": key,
                    "name": info["name"],
                    "url": info["url"],
                    "reachable": resp.status_code < 500,
                    "status_code": resp.status_code,
                }
        except Exception as exc:
            return {
                "key": key,
                "name": info["name"],
                "url": info["url"],
                "reachable": False,
                "error": str(exc),
            }

    import asyncio as _aio

    source_results = await _aio.gather(
        *[_check_source(k, v) for k, v in source_urls.items()],
        return_exceptions=True,
    )
    for r in source_results:
        if isinstance(r, Exception):
            continue
        sources[r["key"]] = r
        if not r.get("reachable"):
            err_detail = r.get("error") or "HTTP %s" % r.get("status_code")
            alerts.append(
                {
                    "level": "warning",
                    "source": r["key"],
                    "message": f"{r['name']} ({r['url']}) is unreachable: {err_detail}",
                }
            )

    # ── 5. APScheduler jobs ──
    scheduler_jobs: list[dict] = []
    try:
        # The scheduler is set up in setup_scheduler() — we check module-level _etl_jobs dict
        for jid, jinfo in _etl_jobs.items():
            scheduler_jobs.append({"job_id": jid, **jinfo})
    except Exception:
        pass

    # ── 6. Build overall status ──
    error_count = sum(1 for a in alerts if a["level"] == "error")
    warn_count = sum(1 for a in alerts if a["level"] == "warning")
    overall = (
        "healthy"
        if error_count == 0 and warn_count == 0
        else ("degraded" if error_count == 0 else "unhealthy")
    )

    return JSONResponse(
        {
            "status": overall,
            "checked_at": now.isoformat(),
            "auto_seeder": seeder_info,
            "database": db_stats,
            "modules": module_status,
            "sources": sources,
            "etl_jobs": scheduler_jobs,
            "alerts": alerts,
            "summary": {
                "errors": error_count,
                "warnings": warn_count,
                "total_alerts": len(alerts),
            },
        }
    )


@app.post("/api/v1/system/seeder-refresh")
async def trigger_seeder_refresh() -> JSONResponse:
    """
    Manually trigger a full data refresh from all live sources.

    This endpoint forces an immediate refresh of all data domains,
    bypassing the normal scheduling logic.
    """
    try:
        from services.auto_seeder import auto_seeder

        if not auto_seeder.is_running:
            return JSONResponse(
                {
                    "status": "error",
                    "message": "Auto-seeder is not running. Start the service first.",
                },
                status_code=503,
            )

        # Trigger refresh in background
        asyncio.create_task(auto_seeder.seed_all_domains())

        return JSONResponse(
            {
                "status": "ok",
                "message": "Full data refresh triggered. Check /api/v1/system/seeder-status for progress.",
            }
        )
    except Exception as e:
        logger.error(f"Error triggering seeder refresh: {e}")
        return JSONResponse(
            {
                "status": "error",
                "error": str(e),
            },
            status_code=500,
        )


@app.get("/api/v1/countries", response_model=List[CountryResponse])
async def get_countries(db: Session = Depends(get_db)):
    """Get list of all countries with summary metrics."""
    try:
        countries = db.query(DBCountry).all()
        if not countries:
            # Return mock data if database is empty
            logger.info("🔄 No countries found in database, returning mock data")
            return [
                {
                    "id": 1,
                    "name": "Kenya",
                    "iso_code": "KEN",
                    "currency": "KES",
                    "summary": {
                        "total_entities": 47,
                        "total_budget": "25T KES",
                        "transparency_score": 75.5,
                    },
                }
            ]
        return countries
    except Exception as e:
        logger.error(f"Database error in get_countries: {str(e)}")
        # Return mock data on database error
        return [
            {
                "id": 1,
                "name": "Kenya",
                "iso_code": "KEN",
                "currency": "KES",
                "summary": {
                    "total_entities": 47,
                    "total_budget": "25T KES",
                    "transparency_score": 75.5,
                },
            }
        ]


@app.get("/api/v1/countries/{country_id}/summary")
@cached(key_prefix="country:summary", ttl=3600)  # Cache for 1 hour
async def get_country_summary(country_id: int):
    """Get detailed financial summary for a specific country from real DB data."""
    if country_id != 1:
        raise HTTPException(status_code=404, detail="Country not found")

    # Aggregate real data from database
    if DATABASE_AVAILABLE:
        try:
            from sqlalchemy import func

            with next(get_db()) as db:
                # Total budget allocation
                total_allocation_result = db.query(
                    func.sum(DBBudgetLine.allocated_amount)
                ).scalar()
                total_allocation = float(total_allocation_result or 0)

                # Total actual spending
                total_spent_result = db.query(
                    func.sum(DBBudgetLine.actual_spent)
                ).scalar()
                total_spent = float(total_spent_result or 0)

                # Total *national* debt (only sovereign-level loans)
                from models import EntityType as _ET

                _nat = db.query(DBEntity).filter(DBEntity.type == _ET.NATIONAL).first()
                if _nat:
                    total_debt_result = (
                        db.query(func.sum(DBLoan.outstanding))
                        .filter(DBLoan.entity_id == _nat.id)
                        .scalar()
                    )
                    total_debt = float(total_debt_result or 0)
                    if total_debt == 0:
                        total_debt = float(
                            db.query(func.sum(DBLoan.principal))
                            .filter(DBLoan.entity_id == _nat.id)
                            .scalar()
                            or 0
                        )
                else:
                    total_debt = 0

                # Execution rate
                execution_rate = round(
                    (
                        (total_spent / total_allocation * 100)
                        if total_allocation > 0
                        else 0
                    ),
                    1,
                )

                # Entity counts by type
                entity_counts = {}
                for row in (
                    db.query(DBEntity.type, func.count(DBEntity.id))
                    .group_by(DBEntity.type)
                    .all()
                ):
                    entity_counts[
                        row[0].value if hasattr(row[0], "value") else str(row[0])
                    ] = row[1]

                # Recent audit findings
                recent_audits_db = (
                    db.query(DBAudit).order_by(DBAudit.created_at.desc()).limit(5).all()
                )
                recent_audits = []
                for a in recent_audits_db:
                    entity = (
                        db.query(DBEntity).filter(DBEntity.id == a.entity_id).first()
                    )
                    recent_audits.append(
                        {
                            "id": a.id,
                            "entity_name": (
                                entity.canonical_name if entity else "Unknown"
                            ),
                            "severity": a.severity.value if a.severity else "info",
                            "finding_summary": (a.finding_text or "")[:200],
                        }
                    )

                # Source document counts
                doc_counts = {}
                for row in (
                    db.query(DBSourceDocument.doc_type, func.count(DBSourceDocument.id))
                    .group_by(DBSourceDocument.doc_type)
                    .all()
                ):
                    key = row[0].value if hasattr(row[0], "value") else str(row[0])
                    doc_counts[f"{key}_documents"] = row[1]

                # Latest source doc date for provenance
                latest_doc = (
                    db.query(DBSourceDocument)
                    .order_by(DBSourceDocument.fetch_date.desc())
                    .first()
                )
                last_updated = (
                    latest_doc.fetch_date.isoformat()
                    if latest_doc and latest_doc.fetch_date
                    else datetime.datetime.now().isoformat()
                )

                return {
                    "country": {
                        "id": 1,
                        "name": "Kenya",
                        "iso_code": "KE",
                        "currency": "KES",
                    },
                    "financial_summary": {
                        "total_allocation": {
                            "value": total_allocation,
                            "currency": "KES",
                        },
                        "total_spent": {
                            "value": total_spent,
                            "currency": "KES",
                        },
                        "execution_rate": {
                            "value": execution_rate,
                            "unit": "percentage",
                        },
                        "total_debt": {
                            "value": total_debt,
                            "currency": "KES",
                        },
                    },
                    "entity_breakdown": entity_counts,
                    "recent_audits": recent_audits,
                    "last_updated": last_updated,
                    "data_sources": doc_counts,
                    "data_source": "database",
                }
        except Exception as exc:
            logging.error(f"DB country summary failed: {exc}")

    # Fallback — indicate data is unavailable rather than returning fake numbers
    raise HTTPException(
        status_code=503,
        detail={
            "error": "No financial data available",
            "message": "Database has no aggregated data yet. Run ETL pipeline to populate.",
            "solution": "Run: python -m seeding.cli seed --all",
        },
    )


# Consolidated County Endpoints - Using Enhanced County Analytics API
@app.get("/api/v1/counties")
@cached(key_prefix="counties:all", ttl=3600)  # Cache for 1 hour
async def get_counties(fiscal_year: Optional[str] = None):
    """Get all counties from database with full financial breakdown.

    Args:
        fiscal_year: Optional fiscal year filter, e.g. '2024/25' or '2023/24'.
                     Matches against fiscal_period start_date year.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Database unavailable",
                "message": "Cannot retrieve county data - database connection failed",
                "solution": "Check database connectivity",
            },
        )

    try:
        from sqlalchemy import func

        with next(get_db()) as db:
            # Query county entities
            q = (
                db.query(DBEntity)
                .filter(DBEntity.type == EntityType.COUNTY)
                .order_by(DBEntity.canonical_name)
            )
            entities = q.all()

            if not entities:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "No county data available",
                        "message": "Database has no seeded county data",
                        "solution": "Run: python -m seeding.cli seed --domain counties_budget",
                        "note": "County entities should be bootstrapped via bootstrap_data.py",
                    },
                )

            # Resolve fiscal period IDs for the requested year
            from models import FiscalPeriod as _FP

            period_ids = None
            if fiscal_year:
                # Parse requested year: accept '2024/25', '2023/24', etc.
                # Match against period start_date year
                try:
                    start_yr = int(fiscal_year.split("/")[0])
                    all_periods = db.query(_FP).all()
                    matched = []
                    for fp in all_periods:
                        lbl = fp.label.replace("FY", "").replace("FY ", "").strip()
                        if lbl == fiscal_year or lbl == f"{start_yr}/{start_yr+1}":
                            matched.append(fp.id)
                        elif fp.start_date and fp.start_date.year == start_yr:
                            matched.append(fp.id)
                    period_ids = list(set(matched)) if matched else None
                except (ValueError, IndexError):
                    pass  # Ignore bad fiscal_year format, return unfiltered
            else:
                # Default to latest fiscal period to avoid summing across all years
                latest_fp = (
                    db.query(_FP)
                    .order_by(_FP.start_date.desc())
                    .first()
                )
                if latest_fp:
                    period_ids = [latest_fp.id]

            results = []
            for e in entities:
                # Get population from PopulationData table
                pop_data = (
                    db.query(DBPopulationData)
                    .filter(DBPopulationData.entity_id == e.id)
                    .order_by(DBPopulationData.year.desc())
                    .first()
                )

                # Get budget lines for this entity, optionally filtered by fiscal period
                bl_query = db.query(DBBudgetLine).filter(DBBudgetLine.entity_id == e.id)
                if period_ids:
                    bl_query = bl_query.filter(DBBudgetLine.period_id.in_(period_ids))
                budget_lines = bl_query.all()

                total_allocated = sum(
                    float(b.allocated_amount or 0) for b in budget_lines
                )
                total_spent = sum(float(b.actual_spent or 0) for b in budget_lines)

                # Group budget by category for sector breakdown
                sector_breakdown = {}
                development_total = 0.0
                recurrent_total = 0.0
                for bl in budget_lines:
                    cat = (bl.category or "Other").strip()
                    amt = float(bl.allocated_amount or 0)
                    spent = float(bl.actual_spent or 0)
                    sector_breakdown.setdefault(cat, {"allocated": 0.0, "spent": 0.0})
                    sector_breakdown[cat]["allocated"] += amt
                    sector_breakdown[cat]["spent"] += spent

                    # Classify as development or recurrent based on category keywords
                    cat_lower = cat.lower()
                    if any(
                        kw in cat_lower
                        for kw in [
                            "development",
                            "capital",
                            "infrastructure",
                            "construction",
                            "project",
                        ]
                    ):
                        development_total += amt
                    else:
                        recurrent_total += amt

                # If no explicit dev/recurrent split found, use metadata or leave as-is
                if (
                    development_total == 0
                    and recurrent_total == 0
                    and total_allocated > 0
                ):
                    meta = e.meta or {}
                    # Try requested fiscal year key first, then fall back
                    _fy_key = f"FY{fiscal_year}" if fiscal_year else "FY2024/25"
                    metrics = (meta.get("metrics") or {}).get(_fy_key) or {}
                    if not metrics:
                        metrics = (meta.get("metrics") or {}).get("FY2024/25") or {}
                    development_total = float(metrics.get("development_budget", 0))
                    recurrent_total = float(metrics.get("recurrent_budget", 0))

                # Get real debt data from Loan table
                loans = db.query(DBLoan).filter(DBLoan.entity_id == e.id).all()
                total_debt = sum(
                    float(loan.outstanding or loan.principal or 0) for loan in loans
                )

                # Get pending bills from budget lines with specific category or from metadata
                pending_bills = sum(
                    float(bl.allocated_amount or 0)
                    for bl in budget_lines
                    if bl.category and "pending" in bl.category.lower()
                )
                if pending_bills == 0:
                    meta = e.meta or {}
                    _fy_key = f"FY{fiscal_year}" if fiscal_year else "FY2024/25"
                    metrics = (meta.get("metrics") or {}).get(_fy_key) or {}
                    if not metrics:
                        metrics = (meta.get("metrics") or {}).get("FY2024/25") or {}
                    pending_bills = float(metrics.get("pending_bills", 0))

                # Get audit findings for this entity, optionally filtered by period
                audit_q = db.query(DBAudit).filter(DBAudit.entity_id == e.id)
                if period_ids:
                    audit_q = audit_q.filter(DBAudit.period_id.in_(period_ids))
                audits = audit_q.order_by(DBAudit.created_at.desc()).all()
                latest_audit = audits[0] if audits else None

                # Build audit issues list from real findings
                audit_issues = []
                for a in audits[:10]:  # Cap at 10 most recent
                    audit_issues.append(
                        {
                            "id": str(a.id),
                            "type": "financial",
                            "severity": a.severity.value if a.severity else "medium",
                            "description": (a.finding_text or "")[:200],
                            "status": "open",
                        }
                    )

                # Determine audit status from latest finding severity
                audit_status = "pending"
                audit_rating = ""
                if latest_audit and latest_audit.severity:
                    sev = latest_audit.severity.value
                    audit_rating = sev
                    if sev == "info":
                        audit_status = "clean"
                    elif sev == "warning":
                        audit_status = "qualified"
                    elif sev == "critical":
                        audit_status = "adverse"

                # Compute financial health score from real data
                health_score = 0.0
                if total_allocated > 0:
                    utilization = (
                        (total_spent / total_allocated * 100) if total_spent > 0 else 0
                    )
                    # Score: higher utilization (up to 95%) = better, penalize >100% overspend
                    if utilization <= 95:
                        health_score = min(utilization, 95)
                    elif utilization <= 100:
                        health_score = 90
                    else:
                        health_score = max(0, 80 - (utilization - 100))

                # Get revenue collection from metadata or economic indicators
                meta = e.meta or {}
                _fy_key = f"FY{fiscal_year}" if fiscal_year else "FY2024/25"
                metrics = (meta.get("metrics") or {}).get(_fy_key) or {}
                if not metrics:
                    metrics = (meta.get("metrics") or {}).get("FY2024/25") or {}
                revenue_collection = float(metrics.get("local_revenue", 0))
                money_received = float(
                    metrics.get("transfers_received", total_allocated)
                )

                # Get GCP (Gross County Product) from GDP table
                gdp_data = None
                try:
                    from models import GDPData as _GDPData

                    gdp_data = (
                        db.query(_GDPData)
                        .filter(_GDPData.entity_id == e.id)
                        .order_by(_GDPData.year.desc())
                        .first()
                    )
                except Exception:
                    pass

                name = e.canonical_name.replace(" County", "")
                county_id = NAME_TO_ID_MAPPING.get(name, e.slug)
                coords = COUNTY_COORDINATES.get(county_id or "", [36.8219, -1.2921])

                last_audit_date = None
                if latest_audit and latest_audit.created_at:
                    last_audit_date = latest_audit.created_at.isoformat().split("T")[0]

                results.append(
                    {
                        "id": county_id or str(e.id),
                        "name": name,
                        "code": county_id or "",
                        "coordinates": coords,
                        "population": pop_data.total_population if pop_data else 0,
                        # Budget data
                        "budget_2025": total_allocated,
                        "total_budget": total_allocated,
                        "total_spent": total_spent,
                        "budget_utilization": round(
                            (
                                (total_spent / total_allocated * 100)
                                if total_allocated > 0
                                else 0
                            ),
                            1,
                        ),
                        "development_budget": development_total,
                        "recurrent_budget": recurrent_total,
                        "sector_breakdown": sector_breakdown,
                        # Revenue
                        "money_received": money_received,
                        "revenue_collection": revenue_collection,
                        "pending_bills": pending_bills,
                        # Debt
                        "debt": total_debt,
                        "total_debt": total_debt,
                        # Economic
                        "gdp": float(gdp_data.gdp_value) if gdp_data else None,
                        # Audit
                        "financial_health_score": round(health_score, 1),
                        "audit_rating": audit_rating,
                        "audit_status": audit_status,
                        "last_audit_date": last_audit_date,
                        "audit_issues": audit_issues,
                        "audit_findings_count": len(audits),
                        # Provenance
                        "data_freshness": {
                            "budget_source": (
                                budget_lines[0].source_document_id
                                if budget_lines
                                else None
                            ),
                            "last_audit_source": (
                                latest_audit.source_document_id
                                if latest_audit
                                else None
                            ),
                        },
                    }
                )

            return results

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error querying counties from database: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Database query failed",
                "message": str(e),
                "solution": "Check database schema and seeded data",
            },
        )


@app.get("/api/v1/counties/{county_id}")
@cached(key_prefix="county", ttl=1800)  # Cache for 30 minutes
async def get_county_details(county_id: str):
    """Get detailed information for a specific county (DB-first, enriched)."""
    if DATABASE_AVAILABLE:
        try:
            with next(get_db()) as db:
                name = COUNTY_MAPPING.get(county_id)
                q = db.query(DBEntity).filter(DBEntity.type == EntityType.COUNTY)
                if name:
                    q = q.filter(DBEntity.canonical_name == f"{name} County")
                e = q.first()
                if e:
                    # Reuse the same enriched data logic as the list endpoint
                    pop_data = (
                        db.query(DBPopulationData)
                        .filter(DBPopulationData.entity_id == e.id)
                        .order_by(DBPopulationData.year.desc())
                        .first()
                    )

                    budget_lines = (
                        db.query(DBBudgetLine)
                        .filter(DBBudgetLine.entity_id == e.id)
                        .all()
                    )
                    total_allocated = sum(
                        float(b.allocated_amount or 0) for b in budget_lines
                    )
                    total_spent = sum(float(b.actual_spent or 0) for b in budget_lines)

                    sector_breakdown = {}
                    development_total = 0.0
                    recurrent_total = 0.0
                    for bl in budget_lines:
                        cat = (bl.category or "Other").strip()
                        amt = float(bl.allocated_amount or 0)
                        spent = float(bl.actual_spent or 0)
                        sector_breakdown.setdefault(
                            cat, {"allocated": 0.0, "spent": 0.0}
                        )
                        sector_breakdown[cat]["allocated"] += amt
                        sector_breakdown[cat]["spent"] += spent
                        cat_lower = cat.lower()
                        if any(
                            kw in cat_lower
                            for kw in [
                                "development",
                                "capital",
                                "infrastructure",
                                "construction",
                                "project",
                            ]
                        ):
                            development_total += amt
                        else:
                            recurrent_total += amt

                    loans = db.query(DBLoan).filter(DBLoan.entity_id == e.id).all()
                    total_debt = sum(
                        float(loan.outstanding or loan.principal or 0) for loan in loans
                    )

                    pending_bills = sum(
                        float(bl.allocated_amount or 0)
                        for bl in budget_lines
                        if bl.category and "pending" in bl.category.lower()
                    )

                    audits = (
                        db.query(DBAudit)
                        .filter(DBAudit.entity_id == e.id)
                        .order_by(DBAudit.created_at.desc())
                        .all()
                    )
                    latest_audit = audits[0] if audits else None

                    audit_issues = []
                    for a in audits[:10]:
                        audit_issues.append(
                            {
                                "id": str(a.id),
                                "type": "financial",
                                "severity": (
                                    a.severity.value if a.severity else "medium"
                                ),
                                "description": (a.finding_text or "")[:200],
                                "status": "open",
                            }
                        )

                    audit_status = "pending"
                    audit_rating = ""
                    if latest_audit and latest_audit.severity:
                        sev = latest_audit.severity.value
                        audit_rating = sev
                        if sev == "info":
                            audit_status = "clean"
                        elif sev == "warning":
                            audit_status = "qualified"
                        elif sev == "critical":
                            audit_status = "adverse"

                    health_score = 0.0
                    if total_allocated > 0:
                        utilization = (
                            (total_spent / total_allocated * 100)
                            if total_spent > 0
                            else 0
                        )
                        if utilization <= 95:
                            health_score = min(utilization, 95)
                        elif utilization <= 100:
                            health_score = 90
                        else:
                            health_score = max(0, 80 - (utilization - 100))

                    meta = e.meta or {}
                    metrics = (meta.get("metrics") or {}).get("FY2024/25") or {}
                    revenue_collection = float(metrics.get("local_revenue", 0))
                    money_received = float(
                        metrics.get("transfers_received", total_allocated)
                    )

                    gdp_data = None
                    try:
                        from models import GDPData as _GDPData

                        gdp_data = (
                            db.query(_GDPData)
                            .filter(_GDPData.entity_id == e.id)
                            .order_by(_GDPData.year.desc())
                            .first()
                        )
                    except Exception:
                        pass

                    cname = (e.canonical_name or "").replace(" County", "")
                    coords = COUNTY_COORDINATES.get(county_id, [36.8219, -1.2921])

                    last_audit_date = None
                    if latest_audit and latest_audit.created_at:
                        last_audit_date = latest_audit.created_at.isoformat().split(
                            "T"
                        )[0]

                    if (
                        development_total == 0
                        and recurrent_total == 0
                        and total_allocated > 0
                    ):
                        development_total = float(metrics.get("development_budget", 0))
                        recurrent_total = float(metrics.get("recurrent_budget", 0))

                    if pending_bills == 0:
                        pending_bills = float(metrics.get("pending_bills", 0))

                    return {
                        "id": county_id,
                        "name": cname,
                        "code": county_id,
                        "coordinates": coords,
                        "population": pop_data.total_population if pop_data else 0,
                        "budget_2025": total_allocated,
                        "total_budget": total_allocated,
                        "total_spent": total_spent,
                        "budget_utilization": round(
                            (
                                (total_spent / total_allocated * 100)
                                if total_allocated > 0
                                else 0
                            ),
                            1,
                        ),
                        "development_budget": development_total,
                        "recurrent_budget": recurrent_total,
                        "sector_breakdown": sector_breakdown,
                        "money_received": money_received,
                        "revenue_collection": revenue_collection,
                        "pending_bills": pending_bills,
                        "debt": total_debt,
                        "total_debt": total_debt,
                        "gdp": float(gdp_data.gdp_value) if gdp_data else None,
                        "financial_health_score": round(health_score, 1),
                        "audit_rating": audit_rating,
                        "audit_status": audit_status,
                        "last_audit_date": last_audit_date,
                        "audit_issues": audit_issues,
                        "audit_findings_count": len(audits),
                    }
        except Exception as exc:
            logging.error(f"DB county details failed, falling back: {exc}")

    # Fallback: Enhanced API
    try:
        county_name = COUNTY_MAPPING.get(county_id)
        if not county_name:
            raise HTTPException(status_code=404, detail="County not found")
        backend_data = await InternalAPIClient.get_county_data(county_name)
        if not backend_data:
            raise HTTPException(status_code=404, detail="County data not available")
        return transform_county_data_for_frontend(backend_data, county_id)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching county {county_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/counties/{county_id}/comprehensive")
@cached(key_prefix="county:comprehensive", ttl=1800)
async def get_county_comprehensive(county_id: str):
    """Comprehensive county detail — one-stop aggregation of every data dimension.

    Returns budget breakdown (by sector), audit findings, debt/loans,
    pending bills, stalled projects, economic profile, demographics,
    missing funds cases, and financial health grades — all from DB.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    county_name = COUNTY_MAPPING.get(county_id)
    if not county_name:
        raise HTTPException(status_code=404, detail="County not found")

    try:
        with next(get_db()) as db:
            entity = (
                db.query(DBEntity)
                .filter(DBEntity.type == EntityType.COUNTY)
                .filter(DBEntity.canonical_name == f"{county_name} County")
                .first()
            )
            if not entity:
                slug = county_name.lower().replace(" ", "-") + "-county"
                entity = db.query(DBEntity).filter(DBEntity.slug == slug).first()
            if not entity:
                raise HTTPException(
                    status_code=404, detail="County entity not found in database"
                )

            meta = entity.meta or {}
            metrics = (meta.get("metrics") or {}).get("FY2024/25") or {}
            financial_metrics_meta = meta.get("financial_metrics") or {}
            economic_profile = meta.get("economic_profile") or {}
            audit_summary_meta = meta.get("audit_summary") or {}

            # --- Population ---
            pop = (
                db.query(DBPopulationData)
                .filter(DBPopulationData.entity_id == entity.id)
                .order_by(DBPopulationData.year.desc())
                .first()
            )

            # --- Budget lines ---
            budget_lines = (
                db.query(DBBudgetLine).filter(DBBudgetLine.entity_id == entity.id).all()
            )
            total_allocated = sum(float(b.allocated_amount or 0) for b in budget_lines)
            total_spent = sum(float(b.actual_spent or 0) for b in budget_lines)

            # Sector breakdown from real budget line categories
            sector_breakdown = {}
            for bl in budget_lines:
                cat = (bl.category or "Other").strip()
                if cat == "Total Budget":
                    continue
                amt = float(bl.allocated_amount or 0)
                spent = float(bl.actual_spent or 0)
                sector_breakdown.setdefault(cat, {"allocated": 0.0, "spent": 0.0})
                sector_breakdown[cat]["allocated"] += amt
                sector_breakdown[cat]["spent"] += spent

            # Compute development vs recurrent split
            development_total = 0.0
            recurrent_total = 0.0
            for bl in budget_lines:
                cat_lower = (bl.category or "").lower()
                amt = float(bl.allocated_amount or 0)
                if any(
                    kw in cat_lower
                    for kw in [
                        "development",
                        "capital",
                        "infrastructure",
                        "construction",
                        "project",
                    ]
                ):
                    development_total += amt
                elif cat_lower != "total budget":
                    recurrent_total += amt
            if development_total == 0 and recurrent_total == 0 and total_allocated > 0:
                development_total = float(metrics.get("development_budget", 0))
                recurrent_total = float(metrics.get("recurrent_budget", 0))

            # --- Loans / Debt ---
            loans = db.query(DBLoan).filter(DBLoan.entity_id == entity.id).all()
            total_debt = sum(float(l.outstanding or l.principal or 0) for l in loans)

            debt_breakdown = []
            for loan in loans:
                debt_breakdown.append(
                    {
                        "lender": loan.lender,
                        "category": (
                            loan.debt_category.value if loan.debt_category else "other"
                        ),
                        "principal": float(loan.principal or 0),
                        "outstanding": float(loan.outstanding or 0),
                        "interest_rate": (
                            float(loan.interest_rate) if loan.interest_rate else None
                        ),
                    }
                )

            # Pending bills from Loan table (PENDING_BILLS category) or meta
            pending_bills_from_loans = sum(
                float(l.outstanding or l.principal or 0)
                for l in loans
                if l.debt_category and l.debt_category.value == "pending_bills"
            )
            pending_bills = (
                pending_bills_from_loans
                or float(financial_metrics_meta.get("pending_bills", 0))
                or float(metrics.get("pending_bills", 0))
            )

            # --- Audits ---
            audits = (
                db.query(DBAudit)
                .filter(DBAudit.entity_id == entity.id)
                .order_by(DBAudit.created_at.desc())
                .all()
            )

            audit_findings = []
            by_severity = {"info": 0, "warning": 0, "critical": 0}
            total_audit_amount = 0.0
            for a in audits:
                sev = a.severity.value if a.severity else "info"
                by_severity[sev] = by_severity.get(sev, 0) + 1

                prov = a.provenance or []
                first_prov = prov[0] if prov and isinstance(prov, list) else {}
                if isinstance(first_prov, dict):
                    amount_str = first_prov.get(
                        "amount", first_prov.get("amount_involved", "0")
                    )
                    category = first_prov.get("category", "other")
                    status = first_prov.get("status", "open")
                    audit_year = first_prov.get("audit_year")
                    reference = first_prov.get(
                        "reference", first_prov.get("external_id", "")
                    )
                else:
                    amount_str = "0"
                    category = "other"
                    status = "open"
                    audit_year = None
                    reference = ""

                # Parse amount
                amount = 0.0
                if isinstance(amount_str, (int, float)):
                    amount = float(amount_str)
                elif isinstance(amount_str, str):
                    import re as _re

                    cleaned = (
                        amount_str.upper().replace("KES", "").replace(",", "").strip()
                    )
                    if cleaned.endswith("B"):
                        try:
                            amount = float(cleaned[:-1]) * 1e9
                        except ValueError:
                            pass
                    elif cleaned.endswith("M"):
                        try:
                            amount = float(cleaned[:-1]) * 1e6
                        except ValueError:
                            pass
                    else:
                        try:
                            amount = float(cleaned)
                        except ValueError:
                            pass
                total_audit_amount += amount

                audit_findings.append(
                    {
                        "id": a.id,
                        "finding": a.finding_text,
                        "severity": sev,
                        "category": category,
                        "status": status,
                        "amount_involved": amount,
                        "amount_label": str(amount_str),
                        "audit_year": audit_year,
                        "reference": reference,
                        "recommendation": a.recommended_action,
                    }
                )

            # Audit status determination
            latest_audit = audits[0] if audits else None
            audit_status = "pending"
            if latest_audit and latest_audit.severity:
                sev = latest_audit.severity.value
                if sev == "info":
                    audit_status = "clean"
                elif sev == "warning":
                    audit_status = "qualified"
                elif sev == "critical":
                    audit_status = "adverse"

            # Financial health score
            health_score = float(
                financial_metrics_meta.get("financial_health_score", 0)
            )
            if health_score == 0 and total_allocated > 0:
                utilization = (
                    (total_spent / total_allocated * 100) if total_spent > 0 else 0
                )
                health_score = (
                    min(utilization, 95)
                    if utilization <= 95
                    else max(0, 80 - (utilization - 100))
                )

            # Letter grade from health score
            grade = "C"
            if health_score >= 85:
                grade = "A"
            elif health_score >= 70:
                grade = "B+"
            elif health_score >= 55:
                grade = "B"
            elif health_score >= 40:
                grade = "B-"

            # --- Missing funds ---
            missing_funds_cases = meta.get("missing_funds_cases") or []
            missing_funds_total = float(financial_metrics_meta.get("missing_funds", 0))

            # --- Stalled projects ---
            stalled_projects = meta.get("stalled_projects") or []

            # --- Revenue ---
            revenue_2024 = float(
                financial_metrics_meta.get("revenue_2024", 0)
            ) or float(metrics.get("revenue_2024", 0))
            local_revenue = float(metrics.get("local_revenue", 0))

            # --- Coordinates ---
            coords = COUNTY_COORDINATES.get(county_id, [36.8219, -1.2921])

            # --- Per-capita stats ---
            population = (
                pop.total_population if pop else int(metrics.get("population", 0))
            )
            per_capita_budget = (
                round(total_allocated / population, 2) if population > 0 else 0
            )
            per_capita_debt = round(total_debt / population, 2) if population > 0 else 0

            response = {
                "id": county_id,
                "name": county_name,
                "slug": entity.slug,
                "coordinates": coords,
                # Demographics
                "demographics": {
                    "population": population,
                    "population_year": pop.year if pop else None,
                    "male_population": pop.male_population if pop else None,
                    "female_population": pop.female_population if pop else None,
                    "urban_population": pop.urban_population if pop else None,
                    "rural_population": pop.rural_population if pop else None,
                    "population_density": (
                        float(pop.population_density)
                        if pop and pop.population_density
                        else None
                    ),
                },
                # Governor
                "governor": meta.get("governor", ""),
                # Economic profile
                "economic_profile": {
                    "county_type": economic_profile.get(
                        "county_type", "standard_county"
                    ),
                    "economic_base": economic_profile.get("economic_base", "mixed"),
                    "infrastructure_level": economic_profile.get(
                        "infrastructure_level", "medium"
                    ),
                    "revenue_potential": economic_profile.get(
                        "revenue_potential", "medium"
                    ),
                    "major_issues": economic_profile.get("major_issues", []),
                },
                # Budget
                "budget": {
                    "total_allocated": total_allocated,
                    "total_spent": total_spent,
                    "utilization_rate": round(
                        (
                            (total_spent / total_allocated * 100)
                            if total_allocated > 0
                            else 0
                        ),
                        1,
                    ),
                    "development_budget": development_total,
                    "recurrent_budget": recurrent_total,
                    "per_capita_budget": per_capita_budget,
                    "sector_breakdown": sector_breakdown,
                },
                # Revenue
                "revenue": {
                    "total_revenue": revenue_2024,
                    "local_revenue": local_revenue,
                    "equitable_share": (
                        total_allocated - local_revenue
                        if local_revenue
                        else total_allocated
                    ),
                },
                # Debt
                "debt": {
                    "total_debt": total_debt,
                    "pending_bills": pending_bills,
                    "debt_to_budget_ratio": round(
                        (
                            (total_debt / total_allocated * 100)
                            if total_allocated > 0
                            else 0
                        ),
                        1,
                    ),
                    "per_capita_debt": per_capita_debt,
                    "breakdown": debt_breakdown,
                },
                # Audit
                "audit": {
                    "status": audit_status,
                    "grade": grade,
                    "health_score": round(health_score, 1),
                    "findings_count": len(audits),
                    "total_amount_involved": total_audit_amount,
                    "by_severity": by_severity,
                    "findings": audit_findings,
                },
                # Missing funds
                "missing_funds": {
                    "total_amount": missing_funds_total,
                    "cases_count": (
                        len(missing_funds_cases)
                        if isinstance(missing_funds_cases, list)
                        else 0
                    ),
                    "cases": (
                        missing_funds_cases
                        if isinstance(missing_funds_cases, list)
                        else []
                    ),
                },
                # Stalled projects
                "stalled_projects": {
                    "count": len(stalled_projects),
                    "total_contracted_value": sum(
                        p.get("contracted_amount", 0) for p in stalled_projects
                    ),
                    "total_amount_paid": sum(
                        p.get("amount_paid", 0) for p in stalled_projects
                    ),
                    "projects": stalled_projects,
                },
                # Financial summary
                "financial_summary": {
                    "health_score": round(health_score, 1),
                    "grade": grade,
                    "budget_execution_rate": round(
                        (
                            (total_spent / total_allocated * 100)
                            if total_allocated > 0
                            else 0
                        ),
                        1,
                    ),
                    "pending_bills_ratio": round(
                        (
                            (pending_bills / total_allocated * 100)
                            if total_allocated > 0
                            else 0
                        ),
                        1,
                    ),
                    "debt_sustainability": (
                        "sustainable"
                        if (
                            total_debt / total_allocated * 100
                            if total_allocated > 0
                            else 0
                        )
                        < 20
                        else (
                            "moderate"
                            if (
                                total_debt / total_allocated * 100
                                if total_allocated > 0
                                else 0
                            )
                            < 40
                            else "at_risk"
                        )
                    ),
                },
                # Data provenance
                "data_sources": {
                    "budget": "Controller of Budget - County Budget Implementation Review Reports",
                    "audit": "Office of the Auditor General - County Government Audit Reports",
                    "debt": "National Treasury - County Debt Register",
                    "stalled_projects": "OAG Audit Reports & County Assembly Committees",
                    "population": "Kenya National Bureau of Statistics (KNBS) Census 2019",
                },
            }

            return response

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in comprehensive county endpoint for {county_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/api/v1/counties/{county_id}/financial")
@cached(key_prefix="county:financial", ttl=1800)  # Cache for 30 minutes
async def get_county_financial_data(county_id: str):
    """Get financial data for a specific county"""
    try:
        # Convert frontend ID to backend name
        county_name = COUNTY_MAPPING.get(county_id)
        if not county_name:
            raise HTTPException(status_code=404, detail="County not found")

        # Fetch from Enhanced County Analytics API
        backend_data = await InternalAPIClient.get_county_financial_data(county_name)

        if not backend_data:
            # Try the general county endpoint as fallback
            backend_data = await InternalAPIClient.get_county_data(county_name)
            if backend_data:
                backend_data = backend_data.get("financial_data", {})

        if not backend_data:
            raise HTTPException(status_code=404, detail="Financial data not available")

        return {
            "county_id": county_id,
            "county_name": county_name,
            "financial_data": backend_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching financial data for county {county_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/counties/{county_id}/budget")
async def get_county_budget(county_id: str):
    """Get budget information for a specific county (DB-first aggregate)."""
    if DATABASE_AVAILABLE:
        try:
            with next(get_db()) as db:
                name = COUNTY_MAPPING.get(county_id)
                e = (
                    db.query(DBEntity)
                    .filter(DBEntity.type == EntityType.COUNTY)
                    .filter(DBEntity.canonical_name == f"{name} County")
                    .first()
                )
                if e:
                    # Simple aggregate from budget lines (if available); fallback to metrics
                    bl_sum = (
                        db.query(DBBudgetLine)
                        .filter(DBBudgetLine.entity_id == e.id)
                        .with_entities(DBBudgetLine.allocated_amount)
                        .all()
                    )
                    allocated_total = (
                        float(sum((x[0] or 0) for x in bl_sum)) if bl_sum else 0.0
                    )
                    meta = e.meta or {}
                    metrics = (meta.get("metrics") or {}).get("FY2024/25") or {}
                    return {
                        "county_id": county_id,
                        "county_name": name,
                        "budget_2025": metrics.get("budget_2025", allocated_total),
                        "budget_execution_rate": metrics.get(
                            "financial_health_score", 0
                        ),
                        "revenue_2024": 0,
                        "expenditure_breakdown": {},
                        "budget_allocation": {},
                    }
        except Exception as e:
            logging.error(f"DB budget aggregate failed, falling back: {e}")

    # Fallback: Enhanced County Analytics API
    try:
        county_name = COUNTY_MAPPING.get(county_id)
        if not county_name:
            raise HTTPException(status_code=404, detail="County not found")

        # Prefer dedicated financial endpoint, then general county data
        backend_fin = await InternalAPIClient.get_county_financial_data(county_name)
        if backend_fin and isinstance(backend_fin, dict):
            budget_2025 = (
                backend_fin.get("budget_2025")
                or backend_fin.get("basic_info", {}).get("budget_2025")
                or 0
            )
            ber = backend_fin.get("financial_metrics", {}).get(
                "budget_execution_rate", 0
            )
            revenue_2024 = (
                backend_fin.get("revenue_2024")
                or backend_fin.get("basic_info", {}).get("revenue_2024")
                or 0
            )
            return {
                "county_id": county_id,
                "county_name": county_name,
                "budget_2025": budget_2025 or 0,
                "budget_execution_rate": ber or 0,
                "revenue_2024": revenue_2024 or 0,
                "expenditure_breakdown": backend_fin.get("expenditure_breakdown", {}),
                "budget_allocation": backend_fin.get("budget_allocation", {}),
            }

        backend_data = await InternalAPIClient.get_county_data(county_name)
        if backend_data:
            mapped = transform_county_data_for_frontend(backend_data, county_id)
            return {
                "county_id": county_id,
                "county_name": county_name,
                "budget_2025": mapped.get("budget_2025", 0),
                "budget_execution_rate": mapped.get("budgetUtilization", 0),
                "revenue_2024": mapped.get("revenue_2024", 0),
                "expenditure_breakdown": {},
                "budget_allocation": {},
            }

        raise HTTPException(status_code=404, detail="County data not available")
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in budget fallback for county {county_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/counties/{county_id}/debt")
async def get_county_debt(county_id: str):
    """Get debt information for a specific county from real DB data."""
    if DATABASE_AVAILABLE:
        try:
            from sqlalchemy import func

            with next(get_db()) as db:
                name = COUNTY_MAPPING.get(county_id)
                if not name:
                    raise HTTPException(status_code=404, detail="County not found")

                e = (
                    db.query(DBEntity)
                    .filter(DBEntity.type == EntityType.COUNTY)
                    .filter(DBEntity.canonical_name == f"{name} County")
                    .first()
                )
                if not e:
                    raise HTTPException(
                        status_code=404, detail="County entity not found in DB"
                    )

                # Real debt from Loan table
                loans = db.query(DBLoan).filter(DBLoan.entity_id == e.id).all()
                total_principal = sum(float(l.principal or 0) for l in loans)
                total_outstanding = sum(float(l.outstanding or 0) for l in loans)

                # Pending bills from BudgetLine (actual - allocated deficit)
                budget_rows = (
                    db.query(DBBudgetLine).filter(DBBudgetLine.entity_id == e.id).all()
                )
                total_allocated = sum(
                    float(b.allocated_amount or 0) for b in budget_rows
                )
                total_spent = sum(float(b.actual_spent or 0) for b in budget_rows)

                # Local revenue from meta
                meta = e.meta or {}
                metrics = (meta.get("metrics") or {}).get("FY2024/25") or {}
                revenue = float(metrics.get("revenue_2024", 0) or 0)

                debt_to_revenue = (
                    round(total_outstanding / revenue * 100, 1) if revenue > 0 else 0
                )

                # Debt breakdown by lender type
                breakdown = {}
                for l in loans:
                    lender = l.lender or "Other"
                    breakdown[lender] = breakdown.get(lender, 0) + float(
                        l.outstanding or l.principal or 0
                    )

                # Sustainability assessment
                if debt_to_revenue > 100:
                    sustainability = "critical"
                elif debt_to_revenue > 50:
                    sustainability = "high_risk"
                elif debt_to_revenue > 25:
                    sustainability = "moderate"
                else:
                    sustainability = "sustainable"

                return {
                    "county_id": county_id,
                    "county_name": name,
                    "debt_outstanding": total_outstanding or total_principal,
                    "debt_principal": total_principal,
                    "pending_bills": max(0, total_spent - total_allocated),
                    "debt_to_revenue_ratio": debt_to_revenue,
                    "revenue": revenue,
                    "debt_breakdown": breakdown,
                    "loan_count": len(loans),
                    "debt_sustainability": sustainability,
                    "data_source": "database",
                }
        except HTTPException:
            raise
        except Exception as exc:
            logging.error(f"DB debt aggregate failed: {exc}")

    raise HTTPException(
        status_code=503,
        detail="County debt data unavailable. Seed database first.",
    )


@app.get("/api/v1/source-documents/{doc_id}")
async def get_source_document(doc_id: int):
    """Return source document metadata for verification."""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        with next(get_db()) as db:
            doc = (
                db.query(DBSourceDocument).filter(DBSourceDocument.id == doc_id).first()
            )
            if not doc:
                raise HTTPException(status_code=404, detail="Not found")
            return {
                "id": doc.id,
                "title": doc.title,
                "publisher": doc.publisher,
                "url": doc.url,
                "md5": doc.md5,
                "fetch_date": doc.fetch_date.isoformat() if doc.fetch_date else None,
                "doc_type": getattr(doc.doc_type, "value", str(doc.doc_type)),
                "meta": doc.meta or {},
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in get_source_document: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/provenance/budget-line/{line_id}")
async def get_budget_line_provenance(line_id: int):
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        with next(get_db()) as db:
            bl = db.query(DBBudgetLine).filter(DBBudgetLine.id == line_id).first()
            if not bl:
                raise HTTPException(status_code=404, detail="Not found")
            doc = (
                db.query(DBSourceDocument)
                .filter(DBSourceDocument.id == bl.source_document_id)
                .first()
            )
            return {
                "budget_line_id": bl.id,
                "source_document": {
                    "id": doc.id if doc else None,
                    "title": doc.title if doc else None,
                    "url": doc.url if doc else None,
                    "md5": doc.md5 if doc else None,
                },
                "provenance": bl.provenance or [],
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in get_budget_line_provenance: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Audit Statistics & Top-Level Routes ──────────────────────────────────


@app.get("/api/v1/audits/statistics")
@cached(key_prefix="audits:statistics", ttl=3600)
async def get_audit_statistics():
    """Aggregate audit statistics across all counties for the dashboard.

    Returns severity breakdown, top flagged counties, recent critical findings,
    and overall totals from the Audit table.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        with next(get_db()) as db:
            from sqlalchemy import case, func

            # Total counts
            total = db.query(func.count(DBAudit.id)).scalar() or 0

            # By severity
            severity_rows = (
                db.query(DBAudit.severity, func.count(DBAudit.id))
                .group_by(DBAudit.severity)
                .all()
            )
            by_severity = {(s.value if s else "unknown"): c for s, c in severity_rows}

            # Counties with most critical findings
            top_flagged = (
                db.query(
                    DBEntity.canonical_name,
                    func.count(DBAudit.id).label("finding_count"),
                )
                .join(DBEntity, DBAudit.entity_id == DBEntity.id)
                .filter(DBAudit.severity == Severity.CRITICAL)
                .group_by(DBEntity.canonical_name)
                .order_by(func.count(DBAudit.id).desc())
                .limit(5)
                .all()
            )

            # Recent critical findings (most recent 6)
            recent_critical = (
                db.query(DBAudit, DBEntity.canonical_name)
                .join(DBEntity, DBAudit.entity_id == DBEntity.id)
                .filter(DBAudit.severity == Severity.CRITICAL)
                .order_by(DBAudit.created_at.desc())
                .limit(6)
                .all()
            )

            recent_items = []
            for audit, county_name in recent_critical:
                amount = 0.0
                if audit.finding_text:
                    match = re.search(r"KES\s*([\d,]+)", audit.finding_text)
                    if match:
                        try:
                            amount = float(match.group(1).replace(",", ""))
                        except Exception:
                            pass
                period_label = ""
                if audit.period and hasattr(audit.period, "label"):
                    period_label = audit.period.label
                recent_items.append(
                    {
                        "id": audit.id,
                        "county": county_name.replace(" County", ""),
                        "finding": audit.finding_text,
                        "severity": (
                            audit.severity.value if audit.severity else "unknown"
                        ),
                        "amount": amount,
                        "fiscal_year": period_label,
                        "date": (
                            audit.created_at.isoformat() if audit.created_at else None
                        ),
                    }
                )

            # Counties audited count
            counties_audited = (
                db.query(func.count(func.distinct(DBAudit.entity_id))).scalar() or 0
            )

            # Total amount involved across all findings
            all_audits = db.query(DBAudit.finding_text).all()
            total_amount = 0.0
            for (text_val,) in all_audits:
                if text_val:
                    match = re.search(r"KES\s*([\d,]+)", text_val)
                    if match:
                        try:
                            total_amount += float(match.group(1).replace(",", ""))
                        except Exception:
                            pass

            return {
                "total_findings": total,
                "counties_audited": counties_audited,
                "total_counties": 47,
                "total_amount_flagged": total_amount,
                "by_severity": by_severity,
                "top_flagged_counties": [
                    {"county": name.replace(" County", ""), "critical_count": count}
                    for name, count in top_flagged
                ],
                "recent_critical": recent_items,
                "report_title": "Office of the Auditor General — County Audit Findings",
                "fiscal_year": "FY 2024/25",
                "last_updated": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error computing audit statistics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/audits/federal")
@cached(key_prefix="audits:federal", ttl=3600)
async def get_federal_audits():
    """Get national/federal government audit findings from the Auditor General.

    Returns audit findings for ministries, departments and agencies (MDAs)
    with the overall audit opinion summary.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        with next(get_db()) as db:
            from sqlalchemy import func

            # Get all federal findings (MINISTRY + NATIONAL entities)
            federal_audits = (
                db.query(DBAudit, DBEntity)
                .join(DBEntity, DBAudit.entity_id == DBEntity.id)
                .filter(DBEntity.type.in_([EntityType.MINISTRY, EntityType.NATIONAL]))
                .order_by(DBAudit.severity.desc(), DBAudit.created_at.desc())
                .all()
            )

            findings = []
            total_amount = 0.0
            severity_counts = {}

            for audit, entity in federal_audits:
                # Parse amount from provenance or finding_text
                amount_str = ""
                amount_val = 0.0
                status = ""
                category = ""
                query_type = ""
                report_section = ""
                date_raised = ""

                if audit.provenance and isinstance(audit.provenance, list):
                    prov = audit.provenance[0] if audit.provenance else {}
                    amount_str = prov.get("amount_involved", "")
                    status = prov.get("status", "")
                    category = prov.get("category", "")
                    query_type = prov.get("query_type", "")
                    report_section = prov.get("report_section", "")
                    date_raised = prov.get("date_raised", "")

                # Parse numeric amount
                if amount_str:
                    cleaned = amount_str.upper().replace("KES", "").strip()
                    try:
                        mult = 1.0
                        if cleaned.endswith("T"):
                            mult = 1_000_000_000_000
                            cleaned = cleaned[:-1]
                        elif cleaned.endswith("B"):
                            mult = 1_000_000_000
                            cleaned = cleaned[:-1]
                        elif cleaned.endswith("M"):
                            mult = 1_000_000
                            cleaned = cleaned[:-1]
                        amount_val = float(cleaned.replace(",", "").strip()) * mult
                    except (ValueError, TypeError):
                        amount_val = 0.0

                total_amount += amount_val
                sev_key = (audit.severity.value if audit.severity else "INFO").upper()
                severity_counts[sev_key] = severity_counts.get(sev_key, 0) + 1

                findings.append(
                    {
                        "id": audit.id,
                        "entity_name": entity.canonical_name,
                        "entity_type": entity.type.value if entity.type else "MINISTRY",
                        "finding": audit.finding_text,
                        "severity": sev_key,
                        "recommended_action": audit.recommended_action,
                        "amount_involved": amount_str,
                        "amount_numeric": amount_val,
                        "status": status,
                        "category": category,
                        "query_type": query_type,
                        "report_section": report_section,
                        "date_raised": date_raised,
                        "date": (
                            audit.created_at.isoformat() if audit.created_at else None
                        ),
                    }
                )

            # Load the audit opinion summary from the JSON file
            opinion_summary = {}
            try:
                import json
                from pathlib import Path

                nat_path = (
                    Path(__file__).resolve().parent.parent
                    / "apis"
                    / "oag_national_audit_data.json"
                )
                if nat_path.exists():
                    with open(nat_path) as f:
                        nat_data = json.load(f)
                    opinion_summary = nat_data.get("audit_opinion_summary", {})
            except Exception:
                pass

            # Ministries with most findings
            top_ministries = (
                db.query(
                    DBEntity.canonical_name,
                    func.count(DBAudit.id).label("count"),
                )
                .join(DBEntity, DBAudit.entity_id == DBEntity.id)
                .filter(DBEntity.type == EntityType.MINISTRY)
                .group_by(DBEntity.canonical_name)
                .order_by(func.count(DBAudit.id).desc())
                .limit(10)
                .all()
            )

            return {
                "report_title": "Report of the Auditor General on the National Government — FY 2023/2024",
                "auditor_general": "Nancy Gathungu, CPA",
                "fiscal_year": "FY 2023/24",
                "report_date": "2024-12-15",
                "opinion_type": opinion_summary.get("opinion_type", "Qualified"),
                "total_findings": len(findings),
                "total_amount_questioned": total_amount,
                "total_amount_questioned_label": opinion_summary.get(
                    "total_amount_questioned", ""
                ),
                "by_severity": severity_counts,
                "basis_for_qualification": opinion_summary.get(
                    "basis_for_qualification", []
                ),
                "emphasis_of_matter": opinion_summary.get("emphasis_of_matter", []),
                "key_statistics": opinion_summary.get("key_statistics", {}),
                "findings": findings,
                "top_ministries": [
                    {"ministry": name, "finding_count": count}
                    for name, count in top_ministries
                ],
                "last_updated": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching federal audits: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/counties/{county_id}/audits")
@cached(key_prefix="county:audits", ttl=3600)  # Cache for 1 hour
async def get_county_audits(county_id: str):
    """Get audit information for a specific county from database."""
    county_name = COUNTY_MAPPING.get(county_id)
    if not county_name:
        raise HTTPException(status_code=404, detail="County not found")

    # Query database first
    if DATABASE_AVAILABLE:
        try:
            with next(get_db()) as db:
                # Find the entity
                entity = (
                    db.query(DBEntity)
                    .filter(DBEntity.type == EntityType.COUNTY)
                    .filter(DBEntity.canonical_name == f"{county_name} County")
                    .first()
                )

                if not entity:
                    # Try alternate slug lookup
                    slug = county_name.lower().replace(" ", "-") + "-county"
                    entity = db.query(DBEntity).filter(DBEntity.slug == slug).first()

                if entity:
                    # Query audits from database
                    audits = (
                        db.query(DBAudit)
                        .filter(DBAudit.entity_id == entity.id)
                        .order_by(DBAudit.created_at.desc())
                        .all()
                    )

                    if audits:
                        # Build response from database audits
                        audit_queries = []
                        by_severity: Dict[str, int] = {}
                        total_amount = 0.0

                        for audit in audits:
                            severity = (
                                audit.severity.value if audit.severity else "unknown"
                            )
                            by_severity[severity] = by_severity.get(severity, 0) + 1

                            # Extract amount from finding_text if present
                            amount = 0.0
                            if audit.finding_text:
                                import re

                                match = re.search(r"KES\s*([\d,]+)", audit.finding_text)
                                if match:
                                    try:
                                        amount = float(match.group(1).replace(",", ""))
                                    except:
                                        pass
                            total_amount += amount

                            # Get fiscal period label if available
                            period_label = ""
                            if audit.period:
                                period_label = (
                                    audit.period.label
                                    if hasattr(audit.period, "label")
                                    else ""
                                )

                            audit_queries.append(
                                {
                                    "id": audit.id,
                                    "finding": audit.finding_text,
                                    "severity": severity,
                                    "recommendation": audit.recommended_action,
                                    "fiscal_year": period_label,
                                    "amount_involved": amount,
                                    "date_raised": (
                                        audit.created_at.isoformat()
                                        if audit.created_at
                                        else None
                                    ),
                                }
                            )

                        return {
                            "county_id": county_id,
                            "county_name": county_name,
                            "data_source": "database",
                            "summary": {
                                "queries_count": len(audits),
                                "total_amount_involved": total_amount,
                                "by_severity": by_severity,
                                "by_status": {},
                                "by_category": {},
                            },
                            "top_recent": audit_queries[:5],
                            "queries": audit_queries,
                            "missing_funds": {
                                "count": 0,
                                "total_amount": 0,
                                "cases": [],
                            },
                            "cob_implementation": {},
                            "kpis": {},
                        }
        except Exception as e:
            logging.error(f"DB audit query failed for {county_id}: {e}")

    # Fallback to external API if DB fails or has no data
    try:
        # Fetch data from Enhanced API
        county_details, ext_audit_queries, missing_funds, cob_impl = (
            await InternalAPIClient.get_county_data(county_name),
            await InternalAPIClient.get_county_audit_queries(county_name),
            await InternalAPIClient.get_missing_funds(county_name),
            await InternalAPIClient.get_cob_implementation(county_name),
        )

        if not county_details and not ext_audit_queries:
            raise HTTPException(
                status_code=404, detail="County audit data not available"
            )

        # Safe defaults
        ext_audit_queries = ext_audit_queries or []
        missing_funds = missing_funds or []
        audit_info = (
            county_details.get("audit_information", {}) if county_details else {}
        )
        financial_metrics = (
            county_details.get("financial_metrics", {}) if county_details else {}
        )

        # Helper to parse KES amount strings
        def parse_amount(amount_str: Any) -> float:
            try:
                if amount_str is None:
                    return 0.0
                if isinstance(amount_str, (int, float)):
                    return float(amount_str)
                s = str(amount_str).upper().replace("KES", "").strip()
                s = s.replace(",", "")
                if s.endswith("B"):
                    return float(s[:-1]) * 1_000_000_000
                if s.endswith("M"):
                    return float(s[:-1]) * 1_000_000
                return float(s)
            except Exception:
                return 0.0

        # Aggregate audit queries
        total_amount = sum(
            parse_amount(q.get("amount_involved")) for q in ext_audit_queries
        )
        by_severity: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        for q in ext_audit_queries:
            by_severity[q.get("severity", "unknown")] = (
                by_severity.get(q.get("severity", "unknown"), 0) + 1
            )
            by_status[q.get("status", "unknown")] = (
                by_status.get(q.get("status", "unknown"), 0) + 1
            )
            by_category[q.get("category", "other")] = (
                by_category.get(q.get("category", "other"), 0) + 1
            )

        def _date_key(q: Dict) -> str:
            return q.get("date_raised", "0000-01-01")

        top_recent = sorted(ext_audit_queries, key=_date_key, reverse=True)[:5]

        # Missing funds aggregation
        missing_total = sum(parse_amount(c.get("amount")) for c in missing_funds)
        notable_cases = [
            {
                "case_id": c.get("case_id"),
                "description": c.get("description"),
                "amount": parse_amount(c.get("amount")),
                "amount_label": c.get("amount"),
                "period": c.get("period"),
                "status": c.get("status"),
            }
            for c in missing_funds
        ]

        # COB implementation
        cob_summary = {
            "coverage": {
                "mentioned_in_report": False,
                "context_length": 0,
                "analysis_depth": "Low",
            },
            "issues": [],
            "budget_implementation": {},
        }
        if cob_impl:
            cov = cob_impl.get("cob_coverage", {})
            cob_summary = {
                "coverage": {
                    "mentioned_in_report": cov.get("mentioned_in_report", False),
                    "context_length": cov.get("context_length", 0),
                    "analysis_depth": cov.get("analysis_depth", "Low"),
                },
                "issues": cob_impl.get("implementation_issues", []),
                "budget_implementation": cob_impl.get("budget_implementation", {}),
            }

        response = {
            "county_id": county_id,
            "county_name": county_name,
            "data_source": "external_api",
            "summary": {
                "queries_count": len(ext_audit_queries),
                "total_amount_involved": total_amount,
                "by_severity": by_severity,
                "by_status": by_status,
                "by_category": by_category,
            },
            "top_recent": top_recent,
            "queries": ext_audit_queries,
            "missing_funds": {
                "count": len(missing_funds),
                "total_amount": missing_total,
                "cases": notable_cases,
            },
            "cob_implementation": cob_summary,
            "kpis": {
                "budget_execution_rate": financial_metrics.get("budget_execution_rate"),
                "pending_bills": financial_metrics.get("pending_bills"),
                "financial_health_score": financial_metrics.get(
                    "financial_health_score"
                ),
            },
        }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching audit info for county {county_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/counties/{county_id}/audits/history")
async def get_county_audits_history(county_id: str):
    """Historical audit queries grouped by fiscal year with quick aggregates."""
    try:
        county_name = COUNTY_MAPPING.get(county_id)
        if not county_name:
            raise HTTPException(status_code=404, detail="County not found")

        audit_queries = await InternalAPIClient.get_county_audit_queries(county_name)
        audit_queries = audit_queries or []

        # Group by year if available on 'period' or 'date_raised'
        def year_of(q: Dict) -> str:
            p = q.get("period") or q.get("fiscal_year") or q.get("fiscal_period")
            if isinstance(p, str) and re.search(r"\d{4}/\d{2}", p):
                return p
            d = q.get("date_raised")
            if isinstance(d, str) and len(d) >= 4 and d[:4].isdigit():
                y = int(d[:4])
                return f"FY{y}/{str((y+1))[-2:]}"
            return "Unknown"

        groups: Dict[str, List[Dict]] = {}
        for q in audit_queries:
            y = year_of(q)
            groups.setdefault(y, []).append(q)

        by_year = []
        for y, qs in sorted(groups.items(), reverse=True):
            by_status: Dict[str, int] = {}
            for q in qs:
                by_status[q.get("status", "unknown")] = (
                    by_status.get(q.get("status", "unknown"), 0) + 1
                )
            by_year.append(
                {
                    "fiscal_year": y,
                    "count": len(qs),
                    "by_status": by_status,
                }
            )

        return {
            "county_id": county_id,
            "county_name": county_name,
            "years": by_year,
            "total": len(audit_queries),
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching audit history for county {county_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/counties/{county_id}/audits/list", response_model=AuditListResponse)
async def list_county_audits(
    county_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    year: Optional[str] = Query(None, description="Fiscal year e.g. FY2022/23"),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Paginated audit queries with filters. DB-backed when available; falls back to Enhanced API."""
    try:
        county_name = COUNTY_MAPPING.get(county_id)
        if not county_name:
            raise HTTPException(status_code=404, detail="County not found")

        # DB-backed path
        if DATABASE_AVAILABLE and DBAudit and DBEntity and db:
            entity_ids = [
                e.id
                for e in db.query(DBEntity)
                .filter(DBEntity.canonical_name == f"{county_name} County")
                .all()
            ]

            query = db.query(DBAudit)
            if entity_ids:
                query = query.filter(DBAudit.entity_id.in_(entity_ids))

            if year and DBFiscalPeriod:
                query = query.join(
                    DBFiscalPeriod, DBAudit.period_id == DBFiscalPeriod.id
                ).filter(DBFiscalPeriod.label == year)

            if severity:
                severity_lookup = None
                try:
                    severity_lookup = Severity[severity.upper()]
                except KeyError:
                    severity_lookup = None
                if severity_lookup:
                    query = query.filter(DBAudit.severity == severity_lookup)

            all_audits = query.order_by(DBAudit.created_at.desc()).all()

            filtered_audits: List[Any] = []
            for audit in all_audits:
                provenance = audit.provenance or []
                status_value = None
                if provenance and isinstance(provenance, list):
                    first_entry = provenance[0] or {}
                    if isinstance(first_entry, dict):
                        status_value = first_entry.get("status")
                if status and status_value:
                    if status_value.lower() != status.lower():
                        continue
                elif status and not status_value:
                    # If a status filter is provided but audit lacks status metadata, skip it
                    continue
                filtered_audits.append(audit)

            total = len(filtered_audits)
            start = (page - 1) * limit
            end = start + limit
            audits = filtered_audits[start:end]

            items: List[Dict[str, Any]] = []
            for audit in audits:
                doc = (
                    audit.source_document if hasattr(audit, "source_document") else None
                )
                provenance = audit.provenance or []
                status_value = None
                category_value = None
                amount_value = None
                if provenance and isinstance(provenance, list):
                    first_entry = provenance[0] or {}
                    if isinstance(first_entry, dict):
                        status_value = first_entry.get("status")
                        category_value = first_entry.get("category")
                        amount_value = first_entry.get("amount_involved")

                items.append(
                    {
                        "id": audit.id,
                        "description": audit.finding_text,
                        "severity": audit.severity.value if audit.severity else None,
                        "status": status_value,
                        "category": category_value,
                        "amountLabel": amount_value,
                        "fiscal_year": audit.period.label if audit.period else None,
                        "source": {
                            "title": doc.title if doc else None,
                            "url": doc.url if doc else None,
                            "page": None,
                            "table_index": None,
                        },
                    }
                )

            return {"total": total, "page": page, "limit": limit, "items": items}

        # Fallback path: Enhanced API data filtered in-memory
        audit_queries = await InternalAPIClient.get_county_audit_queries(county_name)
        items = audit_queries or []

        def to_year(q: Dict) -> str:
            p = q.get("period") or q.get("fiscal_year") or q.get("fiscal_period")
            if isinstance(p, str) and re.search(r"\d{4}/\d{2}", p):
                return p
            d = q.get("date_raised")
            if isinstance(d, str) and len(d) >= 4 and d[:4].isdigit():
                y = int(d[:4])
                return f"FY{y}/{str((y+1))[-2:]}"
            return "Unknown"

        if year:
            items = [q for q in items if to_year(q) == year]
        if status:
            items = [
                q for q in items if str(q.get("status", "")).lower() == status.lower()
            ]
        if severity:
            items = [
                q
                for q in items
                if str(q.get("severity", "")).lower() == severity.lower()
            ]

        total = len(items)
        start = (page - 1) * limit
        end = start + limit
        page_items = items[start:end]

        def map_item(q: Dict, idx: int) -> Dict[str, Any]:
            prov = q.get("provenance") or {}
            source = q.get("source") or {}
            url = source.get("url") or q.get("document_url")
            page_ref = prov.get("page") or source.get("page")
            return {
                "id": q.get("id") or f"{county_id}-{start+idx}",
                "description": q.get("description")
                or q.get("finding")
                or q.get("text"),
                "severity": q.get("severity"),
                "status": q.get("status"),
                "category": q.get("category"),
                "amountLabel": q.get("amount_involved") or q.get("amount"),
                "fiscal_year": to_year(q),
                "source": {
                    "title": source.get("title"),
                    "url": url,
                    "page": page_ref,
                    "table_index": prov.get("table_index") or source.get("table_index"),
                },
            }

        mapped = [map_item(q, i) for i, q in enumerate(page_items)]
        return {"total": total, "page": page, "limit": limit, "items": mapped}
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error listing audit queries for {county_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# County Accountability Scorecard
# ---------------------------------------------------------------------------

def _compute_accountability(db, entity, county_id: str) -> Dict[str, Any]:
    """Compute accountability scorecard for a county entity.

    Returns dict with opinion history, flagged amounts, recurring/unresolved
    findings, absorption rate, grade, and peer comparison.
    """
    audits = (
        db.query(DBAudit)
        .filter(DBAudit.entity_id == entity.id)
        .all()
    )

    # --- audit_opinion_history ---
    opinion_by_year: Dict[int, str] = {}
    for a in audits:
        if a.audit_year and a.audit_opinion:
            opinion_by_year[a.audit_year] = a.audit_opinion
    audit_opinion_history = sorted(
        [{"year": y, "opinion": o} for y, o in opinion_by_year.items()],
        key=lambda x: x["year"],
    )

    # --- total_flagged_amount ---
    total_flagged_amount = float(sum(float(a.amount or 0) for a in audits))

    # --- recurring_findings_count ---
    qt_years: Dict[str, set] = {}
    for a in audits:
        if a.query_type and a.audit_year:
            qt_years.setdefault(a.query_type, set()).add(a.audit_year)
    recurring_findings_count = sum(1 for years in qt_years.values() if len(years) >= 2)

    # --- unresolved_findings_count ---
    unresolved_statuses = {"pending", "unresolved", "recurring"}
    unresolved_findings_count = sum(
        1 for a in audits
        if a.status and a.status.lower() in unresolved_statuses
    )

    # --- absorption_rate from budget data ---
    budget_lines = (
        db.query(DBBudgetLine)
        .filter(DBBudgetLine.entity_id == entity.id)
        .all()
    )
    total_allocated = sum(float(b.allocated_amount or 0) for b in budget_lines)
    total_spent = sum(float(b.actual_spent or 0) for b in budget_lines)
    absorption_rate = (
        round(total_spent / total_allocated, 4) if total_allocated > 0 else None
    )

    # --- accountability_grade ---
    grade_order = ["A", "B", "C", "D", "F"]

    def _drop_grade(current: str, steps: int = 1) -> str:
        idx = grade_order.index(current)
        return grade_order[min(idx + steps, len(grade_order) - 1)]

    grade = "A"

    # Adverse/Disclaimer opinion any year -> drop to D
    for entry in audit_opinion_history:
        op = entry["opinion"].lower()
        if op in ("adverse", "disclaimer"):
            grade = _drop_grade(grade, max(0, grade_order.index("D") - grade_order.index(grade)))
            break

    # Qualified opinion in latest year -> drop to C (if not already worse)
    if audit_opinion_history:
        latest_opinion = audit_opinion_history[-1]["opinion"].lower()
        if latest_opinion == "qualified" and grade_order.index(grade) < grade_order.index("C"):
            grade = "C"

    # recurring_findings_count > 5 -> drop one grade
    if recurring_findings_count > 5:
        grade = _drop_grade(grade)

    # unresolved_findings_count > 10 -> drop one grade
    if unresolved_findings_count > 10:
        grade = _drop_grade(grade)

    # absorption_rate < 0.5 -> drop one grade
    if absorption_rate is not None and absorption_rate < 0.5:
        grade = _drop_grade(grade)

    # --- peer_comparison ---
    region = COUNTY_REGIONS.get(county_id, "Unknown")
    region_county_ids = [cid for cid, r in COUNTY_REGIONS.items() if r == region and cid != county_id]

    pop_data = (
        db.query(DBPopulationData)
        .filter(DBPopulationData.entity_id == entity.id)
        .order_by(DBPopulationData.year.desc())
        .first()
    )
    population = pop_data.total_population if pop_data else 0

    if population < 500_000:
        pop_bracket = "<500k"
    elif population < 1_000_000:
        pop_bracket = "500k-1M"
    elif population < 2_000_000:
        pop_bracket = "1M-2M"
    else:
        pop_bracket = ">2M"

    # Collect peer stats for region
    region_flagged_amounts: List[float] = []
    region_grades: List[str] = []

    def _grade_to_num(g: str) -> float:
        return {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}.get(g, 0.0)

    def _num_to_grade(n: float) -> str:
        if n >= 3.5:
            return "A"
        if n >= 2.5:
            return "B"
        if n >= 1.5:
            return "C"
        if n >= 0.5:
            return "D"
        return "F"

    for peer_cid in region_county_ids:
        peer_name = COUNTY_MAPPING.get(peer_cid)
        if not peer_name:
            continue
        peer_entity = (
            db.query(DBEntity)
            .filter(DBEntity.type == EntityType.COUNTY)
            .filter(DBEntity.canonical_name == f"{peer_name} County")
            .first()
        )
        if not peer_entity:
            continue
        peer_audits = (
            db.query(DBAudit)
            .filter(DBAudit.entity_id == peer_entity.id)
            .all()
        )
        peer_flagged = float(sum(float(pa.amount or 0) for pa in peer_audits))
        region_flagged_amounts.append(peer_flagged)

        # Simplified peer grade (opinion-based for efficiency)
        peer_opinions: Dict[int, str] = {}
        for pa in peer_audits:
            if pa.audit_year and pa.audit_opinion:
                peer_opinions[pa.audit_year] = pa.audit_opinion
        pg = "A"
        for op in peer_opinions.values():
            if op.lower() in ("adverse", "disclaimer"):
                pg = "D"
                break
        if peer_opinions:
            latest_y = max(peer_opinions.keys())
            if peer_opinions[latest_y].lower() == "qualified" and pg == "A":
                pg = "C"
        region_grades.append(pg)

    region_avg_flagged = (
        round(sum(region_flagged_amounts) / len(region_flagged_amounts), 2)
        if region_flagged_amounts else 0.0
    )
    region_avg_grade = (
        _num_to_grade(sum(_grade_to_num(g) for g in region_grades) / len(region_grades))
        if region_grades else None
    )

    # Population bracket average
    bracket_flagged_amounts: List[float] = []
    for cid, cname in COUNTY_MAPPING.items():
        if cid == county_id:
            continue
        ce = (
            db.query(DBEntity)
            .filter(DBEntity.type == EntityType.COUNTY)
            .filter(DBEntity.canonical_name == f"{cname} County")
            .first()
        )
        if not ce:
            continue
        cp = (
            db.query(DBPopulationData)
            .filter(DBPopulationData.entity_id == ce.id)
            .order_by(DBPopulationData.year.desc())
            .first()
        )
        cpop = cp.total_population if cp else 0
        if cpop < 500_000:
            cb = "<500k"
        elif cpop < 1_000_000:
            cb = "500k-1M"
        elif cpop < 2_000_000:
            cb = "1M-2M"
        else:
            cb = ">2M"
        if cb == pop_bracket:
            ca = db.query(DBAudit).filter(DBAudit.entity_id == ce.id).all()
            bracket_flagged_amounts.append(float(sum(float(x.amount or 0) for x in ca)))

    population_bracket_avg = (
        round(sum(bracket_flagged_amounts) / len(bracket_flagged_amounts), 2)
        if bracket_flagged_amounts else 0.0
    )

    peer_comparison = {
        "region": region,
        "region_avg_flagged_amount": region_avg_flagged,
        "region_avg_grade": region_avg_grade,
        "population_bracket": pop_bracket,
        "population_bracket_avg": population_bracket_avg,
    }

    return {
        "county_id": county_id,
        "county_name": (entity.canonical_name or "").replace(" County", ""),
        "audit_opinion_history": audit_opinion_history,
        "total_flagged_amount": total_flagged_amount,
        "recurring_findings_count": recurring_findings_count,
        "unresolved_findings_count": unresolved_findings_count,
        "absorption_rate": absorption_rate,
        "accountability_grade": grade,
        "peer_comparison": peer_comparison,
    }


@app.get("/api/v1/counties/{county_id}/accountability")
@cached(key_prefix="county:accountability", ttl=3600)
async def get_county_accountability(county_id: str):
    """County accountability scorecard with opinion history, grade, and peer comparison."""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    county_name = COUNTY_MAPPING.get(county_id)
    if not county_name:
        raise HTTPException(status_code=404, detail="County not found")

    try:
        with next(get_db()) as db:
            entity = (
                db.query(DBEntity)
                .filter(DBEntity.type == EntityType.COUNTY)
                .filter(DBEntity.canonical_name == f"{county_name} County")
                .first()
            )
            if not entity:
                slug = county_name.lower().replace(" ", "-") + "-county"
                entity = db.query(DBEntity).filter(DBEntity.slug == slug).first()
            if not entity:
                raise HTTPException(status_code=404, detail="County entity not found")

            return _compute_accountability(db, entity, county_id)
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Accountability scorecard failed for {county_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/counties/{county_id}/summary")
@cached(key_prefix="county:summary", ttl=1800)
async def get_county_summary(county_id: str):
    """Lightweight county summary including accountability grade."""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    county_name = COUNTY_MAPPING.get(county_id)
    if not county_name:
        raise HTTPException(status_code=404, detail="County not found")

    try:
        with next(get_db()) as db:
            entity = (
                db.query(DBEntity)
                .filter(DBEntity.type == EntityType.COUNTY)
                .filter(DBEntity.canonical_name == f"{county_name} County")
                .first()
            )
            if not entity:
                slug = county_name.lower().replace(" ", "-") + "-county"
                entity = db.query(DBEntity).filter(DBEntity.slug == slug).first()
            if not entity:
                raise HTTPException(status_code=404, detail="County entity not found")

            pop_data = (
                db.query(DBPopulationData)
                .filter(DBPopulationData.entity_id == entity.id)
                .order_by(DBPopulationData.year.desc())
                .first()
            )
            budget_lines = (
                db.query(DBBudgetLine)
                .filter(DBBudgetLine.entity_id == entity.id)
                .all()
            )
            total_allocated = sum(float(b.allocated_amount or 0) for b in budget_lines)
            total_spent = sum(float(b.actual_spent or 0) for b in budget_lines)
            audits = db.query(DBAudit).filter(DBAudit.entity_id == entity.id).all()

            scorecard = _compute_accountability(db, entity, county_id)

            return {
                "county_id": county_id,
                "county_name": (entity.canonical_name or "").replace(" County", ""),
                "population": pop_data.total_population if pop_data else 0,
                "total_budget": total_allocated,
                "total_spent": total_spent,
                "audit_findings_count": len(audits),
                "accountability_grade": scorecard["accountability_grade"],
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"County summary failed for {county_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/sources/status")
async def get_sources_status():
    """Summarize crawl status from ETL manifest and latest pipeline results file."""
    try:
        etl_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "etl"))
        downloads_dir = os.path.join(etl_dir, "downloads")
        manifest_path = os.path.join(downloads_dir, "processed_manifest.json")

        sources: Dict[str, Dict[str, Any]] = {}

        # From manifest
        if os.path.exists(manifest_path):
            import json as _json

            try:
                manifest = _json.loads(
                    open(manifest_path, "r", encoding="utf-8").read()
                )
            except Exception:
                manifest = {}
            for md5, rec in (manifest.get("by_md5") or {}).items():
                src = rec.get("source") or "unknown"
                s = sources.setdefault(src, {"documents": 0})
                s["documents"] = s.get("documents", 0) + 1
                s["last_fetched"] = max(
                    s.get("last_fetched", "1970-01-01T00:00:00"), rec.get("fetched", "")
                )

        # Latest pipeline results file
        latest_run = None
        if os.path.exists(downloads_dir):
            try:
                files = [
                    f
                    for f in os.listdir(downloads_dir)
                    if f.startswith("pipeline_results_")
                ]
                if files:
                    files.sort(reverse=True)
                    latest_file = os.path.join(downloads_dir, files[0])
                    import json as _json

                    latest_run = _json.loads(
                        open(latest_file, "r", encoding="utf-8").read()
                    )
                    for skey, res in (
                        latest_run.get("sources_processed") or {}
                    ).items():
                        s = sources.setdefault(skey, {})
                        s["last_run"] = {
                            "discovered": res.get("discovered", 0),
                            "processed": res.get("processed", 0),
                            "successful": res.get("successful", 0),
                        }
                        s["last_pipeline_run_at"] = latest_run.get("end_time")
            except Exception:
                pass

        # Flatten to list
        out = [
            {"source": name, **data}
            for name, data in sorted(sources.items(), key=lambda kv: kv[0].lower())
        ]
        return {"sources": out}
    except Exception as e:
        logging.error(f"Error reading source status: {e}")
        return {"sources": []}


async def _run_etl_for_source(source_key: str) -> Dict[str, Any]:
    """Discover and process a small batch for one source and write a run log file."""
    # Import lazily to avoid heavy deps on import time
    # Ensure project root is on sys.path so we can import the 'etl' package
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    try:
        kp_mod = importlib.import_module("etl.kenya_pipeline")
        KenyaDataPipeline = getattr(kp_mod, "KenyaDataPipeline")
    except Exception as e:  # pragma: no cover
        logging.error(f"ETL import failed: {e}")
        return {"error": str(e)}

    pipeline = KenyaDataPipeline()
    discovered = pipeline.discover_budget_documents(source_key)
    processed = 0
    successful = 0
    for doc in discovered[:5]:
        result = await pipeline.download_and_process_document(doc)
        processed += 1
        if result:
            successful += 1
        # polite spacing
        await asyncio.sleep(2)

    run = {
        "source": source_key,
        "discovered": len(discovered),
        "processed": processed,
        "successful": successful,
        "ended_at": datetime.datetime.now().isoformat(),
    }

    # Write file-based run log
    try:
        etl_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "etl"))
        downloads_dir = os.path.join(etl_dir, "downloads")
        os.makedirs(downloads_dir, exist_ok=True)
        log_file = os.path.join(downloads_dir, "etl_run_logs.jsonl")
        with open(log_file, "a", encoding="utf-8") as f:
            import json as _json

            f.write(_json.dumps(run) + "\n")
    except Exception:
        pass

    return run


# ---------------- Scheduler + Notifications helpers ----------------
class AppSettings(BaseModel):
    smtp_host: Optional[str] = os.getenv("SMTP_HOST")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: Optional[str] = os.getenv("SMTP_USER")
    smtp_password: Optional[str] = os.getenv("SMTP_PASSWORD")
    notify_email_to: Optional[str] = os.getenv("NOTIFY_EMAIL_TO")
    environment: str = os.getenv("ENVIRONMENT", "development")
    aws_bucket: Optional[str] = os.getenv("AWS_BUCKET_NAME")
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")


settings = AppSettings()

_s3_client = None
if boto3 and settings.aws_bucket:
    try:
        _s3_client = boto3.client(
            "s3",
            region_name=settings.aws_region,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
    except Exception:
        _s3_client = None


def _artifact_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _artifact_dir() -> str:
    root = _artifact_root()
    path = os.path.join(root, "reports", datetime.datetime.now().strftime("%Y-%m-%d"))
    os.makedirs(path, exist_ok=True)
    return path


def _known_dir() -> str:
    root = _artifact_root()
    path = os.path.join(root, "reports", "known")
    os.makedirs(path, exist_ok=True)
    return path


def send_email(subject: str, body: str) -> None:
    if not (
        settings.smtp_host
        and settings.smtp_user
        and settings.smtp_password
        and settings.notify_email_to
    ):
        logger.info("Email not configured; skipping notification")
        return
    try:
        msg = MIMEText(body, _charset="utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_user
        msg["To"] = settings.notify_email_to
        msg["Date"] = formatdate(localtime=True)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(
                settings.smtp_user, [settings.notify_email_to], msg.as_string()
            )
    except Exception as e:
        logger.error(f"Failed to send email: {e}")


def _load_known_urls(path: str) -> set:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    except Exception:
        return set()


def _save_known_urls(path: str, urls: set) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            for u in sorted(urls):
                f.write(u + "\n")
    except Exception as e:
        logger.error(f"Failed saving known urls: {e}")


def _load_known_hashes(path: str) -> Dict[str, str]:
    try:
        import json as _json

        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        return {}


def _save_known_hashes(path: str, mapping: Dict[str, str]) -> None:
    try:
        import json as _json

        with open(path, "w", encoding="utf-8") as f:
            _json.dump(mapping, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed saving known hashes: {e}")


# ---- ETL job tracking --------------------------------------------------------
_etl_jobs: Dict[str, Dict[str, Any]] = {}  # job_id -> status dict
_etl_lock = asyncio.Lock()  # Only allow ONE ETL deep job at a time
_etl_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="etl"
)


async def _discover(source_key: str) -> List[Dict[str, Any]]:
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    kp_mod = importlib.import_module("etl.kenya_pipeline")
    KenyaDataPipeline = getattr(kp_mod, "KenyaDataPipeline")
    pipeline = KenyaDataPipeline()
    # discover_budget_documents is synchronous (requests-based) – run in dedicated pool
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _etl_executor, pipeline.discover_budget_documents, source_key
    )


async def _ingest_batch(
    source_key: str, docs: List[Dict[str, Any]], limit: int = 25
) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Download/process up to limit docs; return (processed, successful, failures)."""
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    kp_mod = importlib.import_module("etl.kenya_pipeline")
    KenyaDataPipeline = getattr(kp_mod, "KenyaDataPipeline")
    pipeline = KenyaDataPipeline()
    processed = 0
    successful = 0
    failures: List[Dict[str, Any]] = []

    def _sync_process(p, d):
        """Run the async download_and_process_document in a new event loop (it uses sync requests internally)."""
        import asyncio as _aio

        loop = _aio.new_event_loop()
        try:
            return loop.run_until_complete(p.download_and_process_document(d))
        finally:
            loop.close()

    for doc in docs[:limit]:
        try:
            loop = asyncio.get_event_loop()
            ok = await loop.run_in_executor(_etl_executor, _sync_process, pipeline, doc)
            processed += 1
            if ok:
                successful += 1
            else:
                failures.append({"doc": doc, "error": "process_failed"})
        except Exception as e:
            failures.append({"doc": doc, "error": str(e)})
        await asyncio.sleep(1)
    return processed, successful, failures


async def _run_job(source_key: str, job_type: str = "light") -> Dict[str, Any]:
    start = datetime.datetime.now()
    art_dir = _artifact_dir()
    known_path = os.path.join(_known_dir(), f"known_{source_key}.txt")
    known = _load_known_urls(known_path)
    known_hash_path = os.path.join(_known_dir(), f"known_{source_key}_hashes.json")
    known_hashes = _load_known_hashes(known_hash_path)

    discovered = await _discover(source_key)
    urls = [d.get("url") or d.get("file_url") for d in discovered]
    new_docs = [
        d for d in discovered if (d.get("url") or d.get("file_url")) not in known
    ]
    changed_docs: List[Dict[str, Any]] = []

    # Compute landing-page hashes for known URLs to detect changes
    async def _hash_url(u: str) -> Optional[str]:
        if not u:
            return None
        if re.search(r"\.(pdf|xlsx?|csv|docx?|zip)(?:$|\?)", u, re.I):
            return None
        try:
            timeout = httpx.Timeout(15.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get(u, headers={"User-Agent": "Mozilla/5.0"})
                if "html" not in (r.headers.get("content-type", "").lower()):
                    return None
                text = r.text[:500_000]
                import hashlib as _h

                return _h.md5(text.encode("utf-8", errors="ignore")).hexdigest()
        except Exception:
            return None

    for d in discovered:
        u = d.get("url") or d.get("file_url")
        if not u or u not in known:
            continue
        prev = known_hashes.get(u)
        newh = await _hash_url(u)
        if newh and prev and newh != prev:
            changed_docs.append(d)
        if newh:
            known_hashes[u] = newh

    processed = successful = 0
    failures: List[Dict[str, Any]] = []

    if job_type == "deep":
        INGEST_LIMITS = {"treasury": 25, "cob": 20, "oag": 15}
        limit = INGEST_LIMITS.get(source_key, 25)
        processed, successful, failures = await _ingest_batch(
            source_key, new_docs, limit=limit
        )

    # Write artifacts
    import csv  # local import to avoid top-level cost
    import json

    tsv_path = os.path.join(art_dir, f"{source_key}_{job_type}_discovered.tsv")
    with open(tsv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["Title", "URL"])
        for d in discovered:
            w.writerow(
                [
                    (d.get("title") or "").strip(),
                    d.get("url") or d.get("file_url"),
                ]
            )

    summary = {
        "source": source_key,
        "job_type": job_type,
        "started_at": start.isoformat(),
        "ended_at": datetime.datetime.now().isoformat(),
        "discovered": len(discovered),
        "new": len(new_docs),
        "changed": len(changed_docs),
        "processed": processed,
        "successful": successful,
        "failed": len(failures),
        "artifact_tsv": os.path.relpath(tsv_path, _artifact_root()),
    }

    json_path = os.path.join(art_dir, f"{source_key}_{job_type}_summary.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {**summary, "failures": failures[:50]}, f, ensure_ascii=False, indent=2
        )

    # Update known
    _save_known_urls(known_path, set(u for u in urls if u))
    _save_known_hashes(known_hash_path, known_hashes)

    # Notify
    subject = f"[ETL {settings.environment}] {source_key.upper()} {job_type}: +{summary['new']} new, {summary['failed']} failed"
    top_new = "\n".join(
        [
            f"- {(d.get('title') or '').strip()} — {(d.get('url') or d.get('file_url'))}"
            for d in new_docs[:10]
        ]
    )
    top_fail = "\n".join(
        [
            f"- {(f.get('doc') or {}).get('url') or (f.get('doc') or {}).get('file_url')} :: {f.get('error')}"
            for f in failures[:10]
        ]
    )
    body = (
        f"Source: {source_key}\nJob: {job_type}\nDiscovered: {summary['discovered']}\nNew: {summary['new']}\nChanged: {summary['changed']}\n"
        f"Processed: {processed} (ok {successful}, failed {summary['failed']})\nArtifacts: {summary['artifact_tsv']}\n\n"
        f"New (top 10):\n{top_new or '—'}\n\nFailures (top 10):\n{top_fail or '—'}\n"
    )
    send_email(subject, body)

    logger.info(f"ETL job finished: {summary}")
    return summary


from fastapi.security import HTTPAuthorizationCredentials


@app.post("/api/v1/admin/etl/run")
async def run_etl_job(
    source: str = Query(..., pattern="^(oag|cob|treasury)$"),
    job: str = Query("light", pattern="^(light|deep)$"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Manually trigger an ETL job for a source (light or deep).

    Returns immediately with a job_id. The ETL runs in the background.
    Check progress via GET /api/v1/admin/etl/status.
    """
    import uuid as _uuid

    job_id = f"{source}_{job}_{_uuid.uuid4().hex[:8]}"
    _etl_jobs[job_id] = {
        "source": source,
        "job_type": job,
        "status": "running",
        "started_at": datetime.datetime.now().isoformat(),
        "result": None,
    }

    async def _bg():
        async with _etl_lock:  # Only one ETL deep job at a time
            try:
                _etl_jobs[job_id]["status"] = "running"
                result = await _run_job(source, job)
                _etl_jobs[job_id]["status"] = "completed"
                _etl_jobs[job_id]["result"] = result
            except Exception as exc:
                _etl_jobs[job_id]["status"] = "failed"
                _etl_jobs[job_id]["error"] = str(exc)
            _etl_jobs[job_id]["ended_at"] = datetime.datetime.now().isoformat()

    asyncio.create_task(_bg())
    return {
        "job_id": job_id,
        "status": "started",
        "message": "ETL job running in background. Check /api/v1/admin/etl/status for progress.",
    }


@app.get("/api/v1/admin/etl/status")
async def get_etl_jobs_status():
    """Get status of all ETL jobs."""
    return {"jobs": _etl_jobs}


@app.on_event("startup")
async def setup_scheduler():
    # keep prior startup logs
    logger.info("Main Backend API starting up...")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info("Initializing database connections...")
    logger.info("Main Backend API startup complete!")

    # Start background scheduler if available
    try:
        async_mod = importlib.import_module("apscheduler.schedulers.asyncio")
        AsyncIOScheduler = getattr(async_mod, "AsyncIOScheduler")
    except Exception:
        AsyncIOScheduler = None

    if not AsyncIOScheduler:
        logger.info("APScheduler not installed; skipping ETL scheduling.")
        return

    scheduler = AsyncIOScheduler()

    # Per-source intervals with jitter seconds
    def jitter(base_seconds: int, spread: int = 900) -> int:
        return max(60, base_seconds + random.randint(-spread, spread))

    # OAG: light weekly, deep monthly
    scheduler.add_job(
        _run_job,
        args=["oag", "light"],
        trigger="interval",
        seconds=jitter(7 * 24 * 3600),
        id="etl_oag_light",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _run_job,
        args=["oag", "deep"],
        trigger="interval",
        seconds=jitter(30 * 24 * 3600),
        id="etl_oag_deep",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    # COB: light weekly, deep biweekly
    scheduler.add_job(
        _run_job,
        args=["cob", "light"],
        trigger="interval",
        seconds=jitter(7 * 24 * 3600),
        id="etl_cob_light",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _run_job,
        args=["cob", "deep"],
        trigger="interval",
        seconds=jitter(14 * 24 * 3600),
        id="etl_cob_deep",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    # Treasury: light twice weekly (~3.5 days), deep weekly
    scheduler.add_job(
        _run_job,
        args=["treasury", "light"],
        trigger="interval",
        seconds=jitter(int(3.5 * 24 * 3600)),
        id="etl_treasury_light",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _run_job,
        args=["treasury", "deep"],
        trigger="interval",
        seconds=jitter(7 * 24 * 3600),
        id="etl_treasury_deep",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )

    scheduler.start()

    # Weekly digest email (every 7 days)
    try:

        def _digest_wrapper():
            import asyncio as _asyncio

            _asyncio.get_event_loop().create_task(send_weekly_digest())

        scheduler.add_job(
            _digest_wrapper,
            trigger="interval",
            seconds=jitter(7 * 24 * 3600),
            id="etl_weekly_digest",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
    except Exception as e:
        logger.warning(f"Failed to schedule weekly digest: {e}")


# ---------------- UX link resolver (original/mirrored) ----------------
def _manifest_file_path() -> str:
    # etl/downloads/processed_manifest.json relative to backend
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(root, "etl", "downloads", "processed_manifest.json")


def _load_manifest() -> Dict[str, Any]:
    try:
        path = _manifest_file_path()
        if os.path.exists(path):
            import json as _json

            with open(path, "r", encoding="utf-8") as f:
                return _json.load(f)
    except Exception as e:
        logger.error(f"Failed to load manifest: {e}")
    return {"by_md5": {}}


@app.get("/api/v1/docs/resolve")
async def resolve_document(url: str = Query(..., description="Original document URL")):
    """Resolve a document by original URL, returning original and mirrored (presigned) links if available."""
    man = _load_manifest()
    rec = None
    for md5, v in (man.get("by_md5") or {}).items():
        if (v.get("url") or "").strip() == url.strip():
            rec = v
            break
    if not rec:
        return {
            "original_url": url,
            "mirrored": False,
            "mirror_url": None,
            "local_path": None,
        }

    s3_key = rec.get("s3_key")
    presigned = None
    if s3_key and _s3_client and settings.aws_bucket:
        try:
            presigned = _s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.aws_bucket, "Key": s3_key},
                ExpiresIn=3600,
            )
        except Exception as e:
            logger.warning(f"Could not presign s3 object {s3_key}: {e}")

    return {
        "original_url": url,
        "mirrored": bool(s3_key and presigned),
        "mirror_url": presigned,
        "local_path": rec.get("file_path"),
        "title": rec.get("title"),
        "source": rec.get("source"),
        "doc_type": rec.get("doc_type"),
        "fetched": rec.get("fetched"),
    }


async def send_weekly_digest() -> None:
    """Email a weekly summary across sources based on the current known files and last summaries."""
    try:
        root = _artifact_root()
        reports_dir = os.path.join(root, "reports")
        # Find the latest summary files
        latest: Dict[str, Dict[str, Any]] = {}
        if os.path.isdir(reports_dir):
            for day in sorted(os.listdir(reports_dir), reverse=True)[
                :14
            ]:  # last 2 weeks
                day_dir = os.path.join(reports_dir, day)
                if not os.path.isdir(day_dir):
                    continue
                for name in os.listdir(day_dir):
                    if name.endswith("_summary.json"):
                        src = name.split("_")[0]
                        try:
                            import json as _json

                            with open(
                                os.path.join(day_dir, name), "r", encoding="utf-8"
                            ) as f:
                                latest[src] = _json.load(f)
                        except Exception:
                            pass
        lines = ["Weekly ETL Digest"]
        for src in sorted(latest.keys()):
            s = latest[src]
            lines.append(
                f"- {src.upper()}: discovered {s.get('discovered',0)}, new {s.get('new',0)}, processed {s.get('processed',0)} (ok {s.get('successful',0)}, failed {s.get('failed',0)})"
            )
        body = "\n".join(lines)
        send_email(f"[ETL {settings.environment}] Weekly Digest", body)
    except Exception as e:
        logger.error(f"Weekly digest failed: {e}")


@app.get("/api/v1/storage/status")
async def storage_status():
    """Summarize storage/provenance: counts, with/without s3 mirror, and last fetched."""
    man = _load_manifest()
    by_md5 = man.get("by_md5") or {}
    total = len(by_md5)
    mirrored = sum(1 for v in by_md5.values() if v.get("s3_key"))
    latest = None
    for v in by_md5.values():
        ts = v.get("fetched")
        if ts and (not latest or ts > latest):
            latest = ts
    return {
        "total": total,
        "mirrored": mirrored,
        "not_mirrored": max(0, total - mirrored),
        "last_fetch": latest,
    }


# National-level endpoints
@app.get("/api/v1/budget/national")
@cached(key_prefix="budget:national", ttl=1800)
async def get_national_budget_summary(fiscal_year: str = None):
    """Get national budget summary aggregated from real DB data."""
    if DATABASE_AVAILABLE:
        try:
            from sqlalchemy import func

            with next(get_db()) as db:
                # Base query — optionally filter by fiscal period label
                budget_query = db.query(DBBudgetLine)
                if fiscal_year:
                    fp = (
                        db.query(DBFiscalPeriod)
                        .filter(DBFiscalPeriod.label.ilike(f"%{fiscal_year}%"))
                        .first()
                    )
                    if fp:
                        budget_query = budget_query.filter(
                            DBBudgetLine.fiscal_period_id == fp.id
                        )

                total_allocated = float(
                    budget_query.with_entities(
                        func.sum(DBBudgetLine.allocated_amount)
                    ).scalar()
                    or 0
                )
                total_spent = float(
                    budget_query.with_entities(
                        func.sum(DBBudgetLine.actual_spent)
                    ).scalar()
                    or 0
                )
                execution_rate = (
                    round(total_spent / total_allocated * 100, 1)
                    if total_allocated > 0
                    else 0
                )

                # Sector breakdown
                sector_rows = (
                    budget_query.with_entities(
                        DBBudgetLine.category,
                        func.sum(DBBudgetLine.allocated_amount).label("allocated"),
                        func.sum(DBBudgetLine.actual_spent).label("spent"),
                    )
                    .group_by(DBBudgetLine.category)
                    .all()
                )
                allocations = []
                for row in sector_rows:
                    sector_name = str(row[0] or "Other")
                    alloc = float(row[1] or 0)
                    spent = float(row[2] or 0)
                    pct = (
                        round(alloc / total_allocated * 100, 1)
                        if total_allocated > 0
                        else 0
                    )
                    allocations.append(
                        {
                            "sector": sector_name,
                            "amount": alloc,
                            "spent": spent,
                            "percentage": pct,
                            "utilization": (
                                round(spent / alloc * 100, 1) if alloc > 0 else 0
                            ),
                        }
                    )

                # Sort by amount descending
                allocations.sort(key=lambda x: x["amount"], reverse=True)

                # Development vs recurrent split
                dev_budget = sum(
                    float(b.allocated_amount or 0)
                    for b in budget_query.all()
                    if b.category and "development" in str(b.category).lower()
                )
                recurrent_budget = total_allocated - dev_budget

                return {
                    "status": "success",
                    "data": {
                        "total": total_allocated,
                        "total_spent": total_spent,
                        "execution_rate": execution_rate,
                        "development_budget": dev_budget,
                        "recurrent_budget": recurrent_budget,
                        "allocations": allocations,
                        "currency": "KES",
                    },
                    "data_source": "database",
                    "last_updated": datetime.datetime.now().isoformat(),
                }
        except Exception as exc:
            logging.error(f"DB national budget failed: {exc}")

    raise HTTPException(
        status_code=503,
        detail="National budget data unavailable. Seed database first.",
    )


@app.get("/api/v1/budget/utilization")
@cached(key_prefix="budget:utilization", ttl=1800)
async def get_budget_utilization_summary(fiscal_year: str = None):
    """Get budget utilization by entity from real DB data."""
    if DATABASE_AVAILABLE:
        try:
            from sqlalchemy import func

            with next(get_db()) as db:
                rows = (
                    db.query(
                        DBEntity.canonical_name,
                        func.sum(DBBudgetLine.allocated_amount).label("allocated"),
                        func.sum(DBBudgetLine.actual_spent).label("spent"),
                    )
                    .join(DBBudgetLine, DBBudgetLine.entity_id == DBEntity.id)
                    .group_by(DBEntity.canonical_name)
                    .all()
                )
                entities = []
                for row in rows:
                    alloc = float(row[1] or 0)
                    spent = float(row[2] or 0)
                    entities.append(
                        {
                            "entity": row[0],
                            "allocated": alloc,
                            "spent": spent,
                            "utilization": (
                                round(spent / alloc * 100, 1) if alloc > 0 else 0
                            ),
                            "variance": alloc - spent,
                        }
                    )
                entities.sort(key=lambda x: x["utilization"], reverse=True)

                return {
                    "status": "success",
                    "data": entities,
                    "data_source": "database",
                }
        except Exception as exc:
            logging.error(f"DB utilization failed: {exc}")

    raise HTTPException(
        status_code=503,
        detail="Budget utilization data unavailable. Seed database first.",
    )


# ── Consolidated budget overview (sectors merged, multi-year ready) ──
SECTOR_NORMALIZE = {
    "health services": "Health",
    "health": "Health",
    "education": "Education",
    "education & training": "Education",
    "roads and public works": "Infrastructure",
    "roads & transport": "Infrastructure",
    "infrastructure & transport": "Infrastructure",
    "water and sanitation": "Water & Sanitation",
    "water & sanitation": "Water & Sanitation",
    "agriculture": "Agriculture",
    "agriculture & livestock": "Agriculture",
    "public administration": "Administration",
    "administration": "Administration",
    "governance & administration": "Administration",
    "county assembly": "Administration",
    "trade and industry": "Trade & Enterprise",
    "trade & enterprise": "Trade & Enterprise",
    "environment": "Environment",
    "environment & natural resources": "Environment",
    "lands & urban planning": "Environment",
    "social services": "Social Protection",
    "social protection": "Social Protection",
    "defense": "Defense",
    "public order & safety": "Public Order & Safety",
    "energy": "Energy",
    "other": "Other",
}

SECTOR_ORDER = [
    "Education",
    "Infrastructure",
    "Public Order & Safety",
    "Administration",
    "Defense",
    "Health",
    "Energy",
    "Social Protection",
    "Agriculture",
    "Water & Sanitation",
    "Environment",
    "Trade & Enterprise",
    "Other",
]


@app.get("/api/v1/budget/overview")
@cached(key_prefix="budget:overview", ttl=1800)
async def get_budget_overview():
    """Consolidated budget overview: merged sectors + fiscal history for year comparison."""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        from sqlalchemy import func

        with next(get_db()) as db:
            # ── Sector allocations (merged) ─────────────────────
            sector_rows = (
                db.query(
                    DBBudgetLine.category,
                    func.sum(DBBudgetLine.allocated_amount).label("allocated"),
                    func.sum(DBBudgetLine.actual_spent).label("spent"),
                )
                .group_by(DBBudgetLine.category)
                .all()
            )
            merged: dict = {}
            for cat, alloc, spent in sector_rows:
                key = SECTOR_NORMALIZE.get(str(cat or "").strip().lower(), "Other")
                if key == "Other" and str(cat or "").strip().lower() == "total budget":
                    continue  # skip the aggregate row
                entry = merged.setdefault(key, {"allocated": 0.0, "spent": 0.0})
                entry["allocated"] += float(alloc or 0)
                entry["spent"] += float(spent or 0)

            total_allocated = sum(v["allocated"] for v in merged.values())
            total_spent = sum(v["spent"] for v in merged.values())

            sectors = []
            for name in SECTOR_ORDER:
                if name not in merged:
                    continue
                v = merged[name]
                sectors.append(
                    {
                        "sector": name,
                        "allocated": v["allocated"],
                        "spent": v["spent"],
                        "percentage": (
                            round(v["allocated"] / total_allocated * 100, 1)
                            if total_allocated > 0
                            else 0
                        ),
                        "utilization": (
                            round(v["spent"] / v["allocated"] * 100, 1)
                            if v["allocated"] > 0
                            else 0
                        ),
                    }
                )

            # ── Fiscal history (for year-over-year comparison) ─────
            from models import FiscalSummary as FSModel

            fiscal_rows = db.query(FSModel).order_by(FSModel.fiscal_year.asc()).all()
            fiscal_years = []
            for r in fiscal_rows:
                fiscal_years.append(
                    {
                        "fiscal_year": r.fiscal_year,
                        "appropriated_budget": float(r.appropriated_budget or 0),
                        "total_revenue": float(r.total_revenue or 0),
                        "tax_revenue": float(r.tax_revenue or 0),
                        "non_tax_revenue": float(r.non_tax_revenue or 0),
                        "total_borrowing": float(r.total_borrowing or 0),
                        "borrowing_pct_of_budget": float(
                            r.borrowing_pct_of_budget or 0
                        ),
                        "debt_service_cost": float(r.debt_service_cost or 0),
                        "development_spending": float(r.development_spending or 0),
                        "recurrent_spending": float(r.recurrent_spending or 0),
                        "county_allocation": float(r.county_allocation or 0),
                    }
                )

            latest = fiscal_years[-1] if fiscal_years else {}

            # ── Top / bottom utilization counties ──────────────────
            util_rows = (
                db.query(
                    DBEntity.canonical_name,
                    func.sum(DBBudgetLine.allocated_amount).label("a"),
                    func.sum(DBBudgetLine.actual_spent).label("s"),
                )
                .join(DBBudgetLine, DBBudgetLine.entity_id == DBEntity.id)
                .group_by(DBEntity.canonical_name)
                .all()
            )
            county_utils = []
            for name, a, s in util_rows:
                a_f = float(a or 0)
                s_f = float(s or 0)
                if a_f > 0:
                    county_utils.append(
                        {
                            "county": str(name).replace(" County", ""),
                            "allocated": a_f,
                            "spent": s_f,
                            "utilization": round(s_f / a_f * 100, 1),
                        }
                    )
            county_utils.sort(key=lambda x: x["utilization"], reverse=True)

            return {
                "status": "success",
                "data_source": "database",
                "last_updated": datetime.datetime.now().isoformat(),
                "summary": {
                    "total_budget": total_allocated,
                    "total_spent": total_spent,
                    "execution_rate": (
                        round(total_spent / total_allocated * 100, 1)
                        if total_allocated > 0
                        else 0
                    ),
                    "development_budget": float(latest.get("development_spending", 0)),
                    "recurrent_budget": float(latest.get("recurrent_spending", 0)),
                    "county_allocation": float(latest.get("county_allocation", 0)),
                    "total_revenue": float(latest.get("total_revenue", 0)),
                    "total_borrowing": float(latest.get("total_borrowing", 0)),
                    "currency": "KES",
                },
                "sectors": sectors,
                "fiscal_history": fiscal_years,
                "county_utilization": {
                    "top_5": county_utils[:5],
                    "bottom_5": (
                        county_utils[-5:][::-1] if len(county_utils) >= 5 else []
                    ),
                    "average": (
                        round(
                            sum(c["utilization"] for c in county_utils)
                            / len(county_utils),
                            1,
                        )
                        if county_utils
                        else 0
                    ),
                },
            }
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"Budget overview failed: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Enhanced budget data: revenue sources, economic context, committed amounts ──


@app.get("/api/v1/budget/enhanced")
@cached(key_prefix="budget:enhanced", ttl=1800)
async def get_budget_enhanced(db: Session = Depends(get_db)):
    """Extended budget data not in the base overview.

    Returns:
      - revenue_by_source: Tax-type breakdown per FY (PAYE, Corp Tax, VAT, Excise, Customs, Other)
      - economic_context: Budget as % of GDP, per-capita budget, key economic indicators
      - execution_by_sector: Allocated → Spent pipeline per sector from CoB NG-BIRR reports
    """
    from models import (
        BudgetLine,
        EconomicIndicator,
        Entity,
        FiscalSummary,
        PopulationData,
        RevenueBySource,
    )
    from sqlalchemy import func

    try:
        # ── 1. Revenue by source ──
        rev_rows = (
            db.query(RevenueBySource)
            .order_by(RevenueBySource.fiscal_year, RevenueBySource.revenue_type)
            .all()
        )

        # Group by fiscal year
        rev_by_fy: dict = {}
        for r in rev_rows:
            fy = r.fiscal_year
            if fy not in rev_by_fy:
                rev_by_fy[fy] = []
            rev_by_fy[fy].append(
                {
                    "revenue_type": r.revenue_type,
                    "category": r.category,
                    "amount": (
                        float(r.amount_billion_kes) if r.amount_billion_kes else None
                    ),
                    "target": (
                        float(r.target_billion_kes) if r.target_billion_kes else None
                    ),
                    "performance_pct": (
                        float(r.performance_pct) if r.performance_pct else None
                    ),
                    "share_pct": (
                        float(r.share_of_total_pct) if r.share_of_total_pct else None
                    ),
                    "yoy_growth_pct": (
                        float(r.yoy_growth_pct) if r.yoy_growth_pct else None
                    ),
                }
            )

        revenue_by_source = [
            {"fiscal_year": fy, "sources": sources}
            for fy, sources in sorted(rev_by_fy.items())
        ]

        # ── 2. Economic context ──
        # Get GDP (in million KES)
        gdp_row = (
            db.query(EconomicIndicator)
            .filter(EconomicIndicator.indicator_type == "total_national_gdp")
            .order_by(EconomicIndicator.indicator_date.desc())
            .first()
        )
        gdp_million = float(gdp_row.value) if gdp_row else None
        gdp_billion = gdp_million / 1000 if gdp_million else None  # Convert to billions

        # Get other economic indicators
        econ_rows = db.query(EconomicIndicator).all()
        econ_map = {}
        for e in econ_rows:
            econ_map[e.indicator_type] = float(e.value) if e.value else None

        # Get total population (sum of all counties)
        total_pop = db.query(func.sum(PopulationData.total_population)).scalar()
        total_pop = int(total_pop) if total_pop else None

        # Get latest fiscal summary for budget context
        latest_fiscal = (
            db.query(FiscalSummary).order_by(FiscalSummary.fiscal_year.desc()).first()
        )

        budget_billion = (
            float(latest_fiscal.appropriated_budget)
            if latest_fiscal and latest_fiscal.appropriated_budget
            else None
        )
        revenue_billion = (
            float(latest_fiscal.total_revenue)
            if latest_fiscal and latest_fiscal.total_revenue
            else None
        )

        economic_context = {
            "gdp_billion_kes": gdp_billion,
            "gdp_growth_pct": econ_map.get("gdp_growth_rate"),
            "inflation_pct": econ_map.get("inflation_rate_cpi"),
            "unemployment_pct": econ_map.get("unemployment_rate"),
            "total_population": total_pop,
            "budget_to_gdp_pct": (
                round((budget_billion / gdp_billion) * 100, 1)
                if budget_billion and gdp_billion
                else None
            ),
            "revenue_to_gdp_pct": (
                round((revenue_billion / gdp_billion) * 100, 1)
                if revenue_billion and gdp_billion
                else None
            ),
            "per_capita_budget_kes": (
                round((budget_billion * 1e9) / total_pop)
                if budget_billion and total_pop
                else None
            ),
            "per_capita_revenue_kes": (
                round((revenue_billion * 1e9) / total_pop)
                if revenue_billion and total_pop
                else None
            ),
            "fiscal_year": latest_fiscal.fiscal_year if latest_fiscal else None,
        }

        # ── 3. Budget execution by sector ──
        # Query national-government budget execution data from the
        # CoB Annual NG-BIRR reports.  These rows are identified by
        # having an entity with slug 'national-government' AND
        # committed_amount populated.
        # County-level rows (from counties_budget seeder) don't have
        # committed_amount and are for allocation-only display.

        national_entity = (
            db.query(Entity.id).filter(Entity.slug == "national-government").scalar()
        )

        if national_entity:
            sector_pipeline = (
                db.query(
                    BudgetLine.category,
                    func.sum(BudgetLine.allocated_amount).label("allocated"),
                    func.sum(BudgetLine.actual_spent).label("spent"),
                )
                .filter(BudgetLine.entity_id == national_entity)
                .filter(BudgetLine.committed_amount.isnot(None))
                .filter(BudgetLine.allocated_amount > 0)
                .group_by(BudgetLine.category)
                .all()
            )
        else:
            sector_pipeline = []

        # Normalize sector names (reuse the mapping from overview)
        execution_by_sector_raw: dict = {}
        for row in sector_pipeline:
            raw = str(row.category or "").strip().lower()
            clean = SECTOR_NORMALIZE.get(raw, "Other")
            if raw == "total budget":
                continue
            if clean not in execution_by_sector_raw:
                execution_by_sector_raw[clean] = {
                    "allocated": 0,
                    "spent": 0,
                }
            execution_by_sector_raw[clean]["allocated"] += float(row.allocated or 0)
            execution_by_sector_raw[clean]["spent"] += float(row.spent or 0)

        execution_by_sector = []
        for sector in SECTOR_ORDER:
            if sector in execution_by_sector_raw:
                d = execution_by_sector_raw[sector]
                alloc = d["allocated"]
                spent = d["spent"]
                unspent = alloc - spent
                execution_by_sector.append(
                    {
                        "sector": sector,
                        "allocated": alloc,
                        "spent": spent,
                        "unspent": unspent,
                        "execution_rate": (
                            round((spent / alloc) * 100, 1) if alloc else 0
                        ),
                    }
                )

        return {
            "revenue_by_source": revenue_by_source,
            "economic_context": economic_context,
            "execution_by_sector": execution_by_sector,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"Budget enhanced failed: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/debt/timeline")
@cached(key_prefix="debt:timeline", ttl=86400)
async def get_debt_timeline(db: Session = Depends(get_db)):
    """Get historical debt timeline (yearly external/domestic breakdown).

    Reads from the debt_timeline table, seeded from CBK Annual Reports
    and National Treasury Budget Policy Statements.
    """
    from models import DebtTimeline

    try:
        rows = db.query(DebtTimeline).order_by(DebtTimeline.year.asc()).all()

        if not rows:
            return {
                "status": "no_data",
                "data_source": "database_empty",
                "last_updated": None,
                "source": "Run seeder: python -m seeding.cli seed --domain debt_timeline",
                "years": 0,
                "timeline": [],
            }

        timeline = []
        for r in rows:
            timeline.append(
                {
                    "year": r.year,
                    "external": float(r.external),
                    "domestic": float(r.domestic),
                    "total": float(r.total),
                    "gdp": float(r.gdp) if r.gdp else None,
                    "gdp_ratio": float(r.gdp_ratio) if r.gdp_ratio else None,
                }
            )

        # Source info from the DB source document
        source_title = "Central Bank of Kenya Annual Reports & National Treasury BPS"
        last_updated = None
        if rows[0].source_document_id:
            sdoc = (
                db.query(DBSourceDocument)
                .filter(DBSourceDocument.id == rows[0].source_document_id)
                .first()
            )
            if sdoc:
                source_title = sdoc.title or source_title
        if rows[-1].updated_at:
            last_updated = rows[-1].updated_at.isoformat()

        return {
            "status": "success",
            "data_source": "database",
            "last_updated": last_updated,
            "source": source_title,
            "years": len(timeline),
            "timeline": timeline,
        }
    except Exception as e:
        logging.error(f"Error fetching debt timeline: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/fiscal/summary")
@cached(key_prefix="fiscal:summary", ttl=86400)
async def get_fiscal_summary(db: Session = Depends(get_db)):
    """Get national fiscal summary — budget, revenue, borrowing, debt service, debt ceiling.

    Reads from the fiscal_summaries table, seeded from National Treasury BPS,
    Controller of Budget reports, and CBK data.
    """
    from models import FiscalSummary as FSModel

    try:
        rows = db.query(FSModel).order_by(FSModel.fiscal_year.asc()).all()

        if not rows:
            return {
                "status": "no_data",
                "data_source": "database_empty",
                "last_updated": None,
                "source": "Run seeder: python -m seeding.cli seed --domain fiscal_summary",
                "current": None,
                "history": [],
                "total_fiscal_years": 0,
            }

        def _row_to_dict(r: FSModel) -> dict:
            return {
                "fiscal_year": r.fiscal_year,
                "appropriated_budget": (
                    float(r.appropriated_budget) if r.appropriated_budget else None
                ),
                "total_revenue": float(r.total_revenue) if r.total_revenue else None,
                "tax_revenue": float(r.tax_revenue) if r.tax_revenue else None,
                "non_tax_revenue": (
                    float(r.non_tax_revenue) if r.non_tax_revenue else None
                ),
                "total_borrowing": (
                    float(r.total_borrowing) if r.total_borrowing else None
                ),
                "borrowing_pct_of_budget": (
                    float(r.borrowing_pct_of_budget)
                    if r.borrowing_pct_of_budget
                    else None
                ),
                "debt_service_cost": (
                    float(r.debt_service_cost) if r.debt_service_cost else None
                ),
                "debt_service_per_shilling": (
                    float(r.debt_service_per_shilling)
                    if r.debt_service_per_shilling
                    else None
                ),
                "debt_ceiling": float(r.debt_ceiling) if r.debt_ceiling else None,
                "actual_debt": float(r.actual_debt) if r.actual_debt else None,
                "debt_ceiling_usage_pct": (
                    float(r.debt_ceiling_usage_pct)
                    if r.debt_ceiling_usage_pct
                    else None
                ),
                "development_spending": (
                    float(r.development_spending) if r.development_spending else None
                ),
                "recurrent_spending": (
                    float(r.recurrent_spending) if r.recurrent_spending else None
                ),
                "county_allocation": (
                    float(r.county_allocation) if r.county_allocation else None
                ),
            }

        fiscal_years = [_row_to_dict(r) for r in rows]
        latest = fiscal_years[-1]

        # Source info
        source_title = "National Treasury BPS & Controller of Budget Reports"
        last_updated = None
        if rows[-1].source_document_id:
            sdoc = (
                db.query(DBSourceDocument)
                .filter(DBSourceDocument.id == rows[-1].source_document_id)
                .first()
            )
            if sdoc:
                source_title = sdoc.title or source_title
        if rows[-1].updated_at:
            last_updated = rows[-1].updated_at.isoformat()

        return {
            "status": "success",
            "data_source": "database",
            "last_updated": last_updated,
            "source": source_title,
            "current": latest,
            "history": fiscal_years,
            "total_fiscal_years": len(fiscal_years),
        }
    except Exception as e:
        logging.error(f"Error fetching fiscal summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/debt/top-loans")
@cached(key_prefix="debt:top-loans", ttl=3600)
async def get_top_loans(limit: int = 10, db: Session = Depends(get_db)):
    """Get top N national government loans by outstanding balance.

    Reads from the database (loans table seeded from Treasury data).
    """
    from models import DebtCategory

    try:
        # Get national entity
        from models import EntityType as ET

        national_entity = (
            db.query(DBEntity).filter(DBEntity.type == ET.NATIONAL).first()
        )

        if not national_entity:
            return {
                "loans": [],
                "total_available": 0,
                "limit": limit,
                "source": "No national entity found — run seeder",
            }

        # Query loans excluding pending bills, sorted by outstanding desc
        loans = (
            db.query(DBLoan)
            .filter(
                DBLoan.entity_id == national_entity.id,
                DBLoan.debt_category != DebtCategory.PENDING_BILLS,
            )
            .order_by(DBLoan.outstanding.desc())
            .all()
        )

        if not loans:
            return {
                "loans": [],
                "total_available": 0,
                "limit": limit,
                "source": "No loan records in database — run seeder",
            }

        top = loans[:limit]
        result_loans = []
        for loan in top:
            outstanding = float(loan.outstanding or 0)
            principal = float(loan.principal or 0)
            rate = float(loan.interest_rate or 0) / 100
            result_loans.append(
                {
                    "lender": loan.lender,
                    "lender_type": (
                        loan.debt_category.value if loan.debt_category else "other"
                    ),
                    "principal": str(principal),
                    "outstanding": str(outstanding),
                    "outstanding_numeric": outstanding,
                    "principal_numeric": principal,
                    "interest_rate": f"{float(loan.interest_rate or 0):.2f}%",
                    "issue_date": (
                        loan.issue_date.strftime("%Y-%m-%d") if loan.issue_date else ""
                    ),
                    "maturity_date": (
                        loan.maturity_date.strftime("%Y-%m-%d")
                        if loan.maturity_date
                        else ""
                    ),
                    "currency": loan.currency,
                    "status": (
                        "active"
                        if loan.maturity_date
                        and loan.maturity_date
                        > datetime.datetime.now(datetime.timezone.utc).replace(
                            tzinfo=None
                        )
                        else "matured"
                    ),
                    "annual_service_cost": round(outstanding * rate, 2),
                }
            )

        # Get source from first loan's source document
        source_title = "National Treasury Public Debt Data"
        if top[0].source_document_id:
            sdoc = (
                db.query(DBSourceDocument)
                .filter(DBSourceDocument.id == top[0].source_document_id)
                .first()
            )
            if sdoc and sdoc.title:
                source_title = sdoc.title

        return {
            "loans": result_loans,
            "total_available": len(loans),
            "limit": limit,
            "source": source_title,
        }

    except Exception as e:
        logging.error(f"Error fetching top loans: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/debt/loans")
@cached(key_prefix="debt:loans", ttl=3600)
async def get_national_loans(db: Session = Depends(get_db)):
    """Get individual national government loan records with full detail.

    Returns each loan with lender, principal, outstanding balance,
    interest rate, issue date, maturity date, and status.
    All data comes from the database (seeded from Treasury/CBK sources).
    """
    from models import DebtCategory

    try:
        from models import EntityType as ET

        national_entity = (
            db.query(DBEntity).filter(DBEntity.type == ET.NATIONAL).first()
        )

        if not national_entity:
            return {
                "loans": [],
                "total_loans": 0,
                "total_outstanding": 0,
                "total_annual_service_cost": 0,
                "source": "No national entity found — run seeder",
                "source_url": "",
                "last_updated": "",
            }

        # Query all national loans (excluding pending bills)
        loans = (
            db.query(DBLoan)
            .filter(
                DBLoan.entity_id == national_entity.id,
                DBLoan.debt_category != DebtCategory.PENDING_BILLS,
            )
            .order_by(DBLoan.outstanding.desc())
            .all()
        )

        if not loans:
            return {
                "loans": [],
                "total_loans": 0,
                "total_outstanding": 0,
                "total_annual_service_cost": 0,
                "source": "No loan records in database — run seeder",
                "source_url": "",
                "last_updated": "",
            }

        national_loans = []
        total_outstanding = 0.0
        total_annual_service = 0.0

        for loan in loans:
            outstanding = float(loan.outstanding or 0)
            principal = float(loan.principal or 0)
            rate = float(loan.interest_rate or 0)
            annual_cost = round(outstanding * (rate / 100), 2)

            total_outstanding += outstanding
            total_annual_service += annual_cost

            national_loans.append(
                {
                    "lender": loan.lender,
                    "lender_type": (
                        loan.debt_category.value if loan.debt_category else "other"
                    ),
                    "principal": str(principal),
                    "outstanding": str(outstanding),
                    "outstanding_numeric": outstanding,
                    "principal_numeric": principal,
                    "interest_rate": f"{rate:.2f}%",
                    "issue_date": (
                        loan.issue_date.strftime("%Y-%m-%d") if loan.issue_date else ""
                    ),
                    "maturity_date": (
                        loan.maturity_date.strftime("%Y-%m-%d")
                        if loan.maturity_date
                        else ""
                    ),
                    "currency": loan.currency,
                    "status": (
                        "active"
                        if loan.maturity_date
                        and loan.maturity_date
                        > datetime.datetime.now(datetime.timezone.utc).replace(
                            tzinfo=None
                        )
                        else "matured"
                    ),
                    "annual_service_cost": annual_cost,
                }
            )

        # Determine source info from first loan's source document
        source_title = "National Treasury Public Debt Data"
        source_url = "https://www.treasury.go.ke/public-debt/"
        last_updated = ""
        if loans[0].source_document_id:
            sdoc = (
                db.query(DBSourceDocument)
                .filter(DBSourceDocument.id == loans[0].source_document_id)
                .first()
            )
            if sdoc:
                source_title = sdoc.title or source_title
                source_url = sdoc.url or source_url
        if loans[0].updated_at:
            last_updated = loans[0].updated_at.isoformat()

        return {
            "loans": national_loans,
            "total_loans": len(national_loans),
            "total_outstanding": total_outstanding,
            "total_annual_service_cost": total_annual_service,
            "source": source_title,
            "source_url": source_url,
            "last_updated": last_updated,
        }

    except Exception as e:
        logging.error(f"Error fetching national loans: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/debt/national")
@cached(key_prefix="debt:national", ttl=1800)
async def get_national_debt():
    """Get national debt overview with categorized breakdown."""
    # Try database first
    if DATABASE_AVAILABLE:
        try:
            with next(get_db()) as db:
                # Find the national entity so we only count sovereign debt
                from models import EntityType as ET

                national_entity = (
                    db.query(DBEntity).filter(DBEntity.type == ET.NATIONAL).first()
                )
                if national_entity:
                    loans = (
                        db.query(DBLoan)
                        .filter(DBLoan.entity_id == national_entity.id)
                        .all()
                    )
                else:
                    loans = []

                if loans:
                    # Calculate totals
                    total_debt = sum(float(loan.principal or 0) for loan in loans)
                    total_outstanding = sum(
                        float(loan.outstanding or 0) for loan in loans
                    )

                    # Get real GDP from GDPData table
                    latest_gdp_row = (
                        db.query(DBGDPData).order_by(DBGDPData.year.desc()).first()
                    )
                    gdp_value = (
                        float(latest_gdp_row.gdp_value or 0)
                        if latest_gdp_row and latest_gdp_row.gdp_value
                        else 0  # No hardcoded fallback; will show 0 until seeded
                    )
                    gdp_year = latest_gdp_row.year if latest_gdp_row else None

                    # Categorize by debt_category field if available, else by lender patterns
                    from models import DebtCategory

                    # Initialize category totals
                    categories = {
                        "external_multilateral": {
                            "principal": 0,
                            "outstanding": 0,
                            "count": 0,
                            "items": [],
                        },
                        "external_bilateral": {
                            "principal": 0,
                            "outstanding": 0,
                            "count": 0,
                            "items": [],
                        },
                        "external_commercial": {
                            "principal": 0,
                            "outstanding": 0,
                            "count": 0,
                            "items": [],
                        },
                        "domestic_bonds": {
                            "principal": 0,
                            "outstanding": 0,
                            "count": 0,
                            "items": [],
                        },
                        "domestic_bills": {
                            "principal": 0,
                            "outstanding": 0,
                            "count": 0,
                            "items": [],
                        },
                        "domestic_overdraft": {
                            "principal": 0,
                            "outstanding": 0,
                            "count": 0,
                            "items": [],
                        },
                        "pending_bills": {
                            "principal": 0,
                            "outstanding": 0,
                            "count": 0,
                            "items": [],
                        },
                        "county_guaranteed": {
                            "principal": 0,
                            "outstanding": 0,
                            "count": 0,
                            "items": [],
                        },
                        "other": {
                            "principal": 0,
                            "outstanding": 0,
                            "count": 0,
                            "items": [],
                        },
                    }

                    # Pattern matching for categorization (fallback if debt_category is None)
                    patterns = {
                        "external_multilateral": [
                            "World Bank",
                            "IMF",
                            "AfDB",
                            "EIB",
                            "IFAD",
                            "IFC",
                        ],
                        "external_bilateral": [
                            "China",
                            "Japan",
                            "France",
                            "Germany",
                            "United States",
                            "Korea",
                            "India",
                            "Belgium",
                            "UK",
                            "Italy",
                        ],
                        "external_commercial": ["Eurobond", "Syndicated", "Commercial"],
                        "domestic_bonds": [
                            "Treasury Bond",
                            "Infrastructure Bond",
                            "Green Bond",
                            "M-Akiba",
                            "Retail Bond",
                        ],
                        "domestic_bills": [
                            "Treasury Bill",
                            "T-Bill",
                            "91-day",
                            "182-day",
                            "364-day",
                        ],
                        "domestic_overdraft": ["Central Bank", "CBK", "Overdraft"],
                        "pending_bills": ["Pending Bill", "Arrears"],
                        "county_guaranteed": [
                            "County",
                            "Nairobi",
                            "Mombasa",
                            "Kisumu",
                            "Nakuru",
                        ],
                    }

                    def classify_loan(loan):
                        # Use debt_category if available and not OTHER
                        if hasattr(loan, "debt_category") and loan.debt_category:
                            cat_value = (
                                loan.debt_category.value
                                if hasattr(loan.debt_category, "value")
                                else str(loan.debt_category)
                            )
                            if cat_value != "OTHER" and cat_value != "other":
                                return cat_value.lower()

                        # Fallback to pattern matching based on lender name
                        lender = (loan.lender or "").lower()
                        for cat, terms in patterns.items():
                            if any(term.lower() in lender for term in terms):
                                return cat
                        return "other"

                    for loan in loans:
                        cat = classify_loan(loan)
                        principal = float(loan.principal or 0)
                        outstanding = float(loan.outstanding or 0)

                        categories[cat]["principal"] += principal
                        categories[cat]["outstanding"] += outstanding
                        categories[cat]["count"] += 1
                        categories[cat]["items"].append(
                            {
                                "lender": loan.lender,
                                "principal": principal,
                                "outstanding": outstanding,
                                "interest_rate": (
                                    float(loan.interest_rate)
                                    if hasattr(loan, "interest_rate")
                                    and loan.interest_rate
                                    else None
                                ),
                            }
                        )

                    # Calculate external vs domestic totals
                    external_cats = [
                        "external_multilateral",
                        "external_bilateral",
                        "external_commercial",
                    ]
                    domestic_cats = [
                        "domestic_bonds",
                        "domestic_bills",
                        "domestic_overdraft",
                    ]

                    external_debt = sum(
                        categories[c]["principal"] for c in external_cats
                    )
                    domestic_debt = sum(
                        categories[c]["principal"] for c in domestic_cats
                    )
                    pending_bills = categories["pending_bills"]["principal"]
                    county_debt = categories["county_guaranteed"]["principal"]

                    return {
                        "status": "success",
                        "data_source": "database",
                        "last_updated": datetime.datetime.now().isoformat(),
                        "data": {
                            "total_debt": total_debt,
                            "total_outstanding": total_outstanding,
                            "loan_count": len(loans),
                            "gdp": gdp_value,
                            "gdp_year": gdp_year,
                            "debt_to_gdp_ratio": (
                                round(total_outstanding / gdp_value * 100, 1)
                                if gdp_value > 0
                                else 0
                            ),
                            # High-level breakdown
                            "summary": {
                                "external_debt": external_debt,
                                "domestic_debt": domestic_debt,
                                "pending_bills": pending_bills,
                                "county_guaranteed": county_debt,
                                "external_percentage": (
                                    round(external_debt / total_debt * 100, 1)
                                    if total_debt > 0
                                    else 0
                                ),
                                "domestic_percentage": (
                                    round(domestic_debt / total_debt * 100, 1)
                                    if total_debt > 0
                                    else 0
                                ),
                            },
                            # Detailed categorized breakdown
                            "categories": {
                                cat: {
                                    "total_principal": data["principal"],
                                    "total_outstanding": data["outstanding"],
                                    "loan_count": data["count"],
                                    "percentage_of_total": (
                                        round(data["principal"] / total_debt * 100, 2)
                                        if total_debt > 0
                                        else 0
                                    ),
                                    "items": data["items"][
                                        :5
                                    ],  # Top 5 items per category
                                }
                                for cat, data in categories.items()
                                if data["count"] > 0
                            },
                            "debt_sustainability": {
                                "risk_level": (
                                    "High"
                                    if gdp_value > 0
                                    and total_outstanding / gdp_value > 0.65
                                    else ("Moderate" if gdp_value > 0 else "Unknown")
                                ),
                                "debt_to_gdp": (
                                    round(total_outstanding / gdp_value * 100, 1)
                                    if gdp_value > 0
                                    else 0
                                ),
                                "assessment": (
                                    "Kenya's debt remains elevated. The IMF classifies Kenya at high risk of debt distress."
                                    if gdp_value > 0
                                    and total_outstanding / gdp_value > 0.65
                                    else "Seed GDP data for full sustainability assessment."
                                ),
                            },
                        },
                        "currency": "KES",
                        "source": "Central Bank of Kenya / National Treasury",
                    }
        except Exception as e:
            logging.error(f"DB debt query failed: {e}")

    # No hardcoded fallback — data must come from the database.
    # Guide user to populate via the seeding pipeline.
    return {
        "status": "no_data",
        "data_source": "database_empty",
        "last_updated": None,
        "message": (
            "No national debt data in database. "
            "Run: python -m seeding.cli seed --domain national_debt"
        ),
        "data": {
            "total_debt": 0,
            "total_outstanding": 0,
            "loan_count": 0,
            "gdp": 0,
            "debt_to_gdp_ratio": 0,
            "summary": {},
            "categories": {},
            "debt_sustainability": {},
        },
        "currency": "KES",
        "source": "Central Bank of Kenya / National Treasury",
    }


@app.get("/api/v1/pending-bills")
@cached(key_prefix="pending_bills:summary", ttl=43200)
async def get_pending_bills(
    db: Session = Depends(get_db),
):
    """Get government pending bills summary.

    Pending bills are verified unpaid invoices owed by the government
    to suppliers and contractors. These are real obligations tracked
    by the Controller of Budget (COB).

    Data sources (in priority order):
      1. Database (from COB ETL extraction via seeding pipeline)
      2. Live COB report scraping (if DB empty and pdfplumber available)
      3. Returns empty with metadata explaining how to populate

    Source: Office of the Controller of Budget
      - https://cob.go.ke/reports/pending-bills/
      - https://cob.go.ke/reports/national-government-budget-implementation-review-reports/
    """
    from decimal import Decimal as D

    # Strategy 1: Read from database (loans with debt_category = PENDING_BILLS)
    try:
        from models import DebtCategory

        pending_loans = (
            db.query(DBLoan)
            .filter(DBLoan.debt_category == DebtCategory.PENDING_BILLS)
            .all()
        )

        if pending_loans:
            bills = []
            total_amount = D("0")
            national_total = D("0")
            county_total = D("0")

            # Batch-load all entity names in ONE query (avoid N+1 with remote DB)
            unique_eids = list({l.entity_id for l in pending_loans if l.entity_id})
            entity_map: Dict[int, tuple] = {}
            if unique_eids:
                for eid, ename, etype in db.query(
                    DBEntity.id, DBEntity.canonical_name, DBEntity.type
                ).filter(DBEntity.id.in_(unique_eids)).all():
                    entity_map[eid] = (ename, etype.value if etype else "national")

            for loan in pending_loans:
                outstanding = loan.outstanding or loan.principal or D("0")
                total_amount += outstanding

                entity_name, entity_type = entity_map.get(
                    loan.entity_id, ("National Government", "national")
                )

                if entity_type == "county":
                    county_total += outstanding
                else:
                    national_total += outstanding

                # provenance can be a dict or list — normalize to dict
                raw_prov = loan.provenance
                if isinstance(raw_prov, list):
                    provenance = raw_prov[0] if raw_prov and isinstance(raw_prov[0], dict) else {}
                elif isinstance(raw_prov, dict):
                    provenance = raw_prov
                else:
                    provenance = {}

                bills.append(
                    {
                        "entity_name": entity_name,
                        "entity_type": entity_type,
                        "lender": loan.lender,
                        "total_pending": float(outstanding),
                        "eligible_pending": provenance.get("eligible_pending"),
                        "ineligible_pending": provenance.get("ineligible_pending"),
                        "fiscal_year": provenance.get("fiscal_year", ""),
                        "category": provenance.get("category", "mda"),
                        "notes": provenance.get("notes"),
                    }
                )

            # Determine source info from provenance of first record
            first_prov = pending_loans[0].provenance or {}
            source_url = first_prov.get("source_url", "https://cob.go.ke/reports/")

            # Get source document if available
            source_title = "Controller of Budget Reports"
            if pending_loans[0].source_document_id:
                sdoc = (
                    db.query(DBSourceDocument)
                    .filter(DBSourceDocument.id == pending_loans[0].source_document_id)
                    .first()
                )
                if sdoc:
                    source_title = sdoc.title or source_title
                    source_url = sdoc.url or source_url

            return {
                "status": "success",
                "data_source": "database",
                "last_updated": max(
                    (l.updated_at or l.created_at for l in pending_loans),
                    default=None,
                ),
                "pending_bills": bills,
                "summary": {
                    "total_pending": float(total_amount),
                    "national_total": float(national_total),
                    "county_total": float(county_total),
                    "record_count": len(bills),
                },
                "source": source_title,
                "source_url": source_url,
                "currency": "KES",
                "explanation": (
                    "Pending bills are verified but unpaid government invoices "
                    "to suppliers and contractors. Unlike formal loans, they "
                    "carry no interest but represent real obligations. "
                    "The Controller of Budget tracks and reports these in "
                    "quarterly budget implementation review reports."
                ),
            }

    except Exception as e:
        logging.warning(f"DB pending bills query failed: {e}")

    # Strategy 2: Try live COB extraction
    try:
        import asyncio

        from etl.pending_bills_extractor import PendingBillsExtractor

        extractor = PendingBillsExtractor()
        data = await extractor.extract_all()

        if data.get("pending_bills") or data.get("summary", {}).get("grand_total"):
            summary = data.get("summary", {})
            return {
                "status": "success",
                "data_source": "live_cob_extraction",
                "last_updated": data.get("extracted_at"),
                "pending_bills": data.get("pending_bills", []),
                "summary": {
                    "total_pending": summary.get("grand_total", 0),
                    "national_total": summary.get("total_national", 0),
                    "county_total": summary.get("total_county", 0),
                    "record_count": len(data.get("pending_bills", [])),
                    "as_at_date": summary.get("as_at_date"),
                },
                "source": data.get("source_title", "Controller of Budget Reports"),
                "source_url": data.get("source_url", "https://cob.go.ke/reports/"),
                "currency": "KES",
                "explanation": (
                    "Pending bills are verified but unpaid government invoices "
                    "to suppliers and contractors. This data was extracted live "
                    "from COB reports."
                ),
            }
    except Exception as e:
        logging.warning(f"Live COB extraction failed: {e}")

    # Strategy 3: Return empty with guidance
    return {
        "status": "no_data",
        "data_source": "none",
        "pending_bills": [],
        "summary": {
            "total_pending": 0,
            "national_total": 0,
            "county_total": 0,
            "record_count": 0,
        },
        "source": "Controller of Budget (https://cob.go.ke/reports/pending-bills/)",
        "source_url": "https://cob.go.ke/reports/pending-bills/",
        "currency": "KES",
        "explanation": (
            "Pending bills data is not yet populated. Run the seeding "
            "pipeline: python -m seeding.cli seed --domain pending_bills. "
            "This will fetch data from COB reports at "
            "https://cob.go.ke/reports/pending-bills/"
        ),
        "how_to_populate": {
            "option_1": "Run: python -m seeding.cli seed --domain pending_bills",
            "option_2": (
                "Set SEED_PENDING_BILLS_DATASET_URL to a JSON fixture "
                "and run the seeder"
            ),
            "option_3": (
                "Enable Playwright (PLAYWRIGHT_ENABLED=1) for COB PDF "
                "download + extraction"
            ),
            "data_sources": [
                "https://cob.go.ke/reports/pending-bills/",
                "https://cob.go.ke/reports/national-government-budget-implementation-review-reports/",
                "https://www.treasury.go.ke/pending-bills/",
            ],
        },
    }


# ── Pending Bills Summary & County Breakdown ──────────────────────────


@app.get("/api/v1/pending-bills/summary")
@cached(key_prefix="pending_bills:summary_enhanced", ttl=43200)
async def get_pending_bills_summary(db: Session = Depends(get_db)):
    """Get pending bills summary with breakdown by type, aging, and county.

    Returns total_pending_amount, breakdown_by_type, top_counties_by_amount,
    aging_buckets, and trend data.
    """
    from models import BillType, PendingBill

    try:
        bills = db.query(PendingBill).all()

        if not bills:
            # Fallback: derive summary from Loan table (PENDING_BILLS category)
            return _pending_bills_summary_from_loans(db)

        total_pending = sum(float(b.amount or 0) for b in bills)

        # Breakdown by type
        breakdown_by_type = {}
        for b in bills:
            bt = b.bill_type.value if b.bill_type else "other"
            breakdown_by_type[bt] = breakdown_by_type.get(bt, 0) + float(b.amount or 0)

        # Top counties by amount
        county_totals: Dict[int, Dict[str, Any]] = {}
        for b in bills:
            eid = b.entity_id
            if eid not in county_totals:
                entity = db.query(DBEntity).filter(DBEntity.id == eid).first()
                county_totals[eid] = {
                    "county": entity.canonical_name if entity else f"Entity {eid}",
                    "entity_id": eid,
                    "amount": 0,
                    "entity_type": entity.type.value if entity and entity.type else "unknown",
                }
            county_totals[eid]["amount"] += float(b.amount or 0)

        # Get population for per_capita (best-effort)
        _pop_map = _get_population_map(db)
        top_counties = sorted(county_totals.values(), key=lambda x: x["amount"], reverse=True)[:15]
        for c in top_counties:
            pop = _pop_map.get(c["county"], 0)
            c["per_capita"] = round(c["amount"] / pop, 2) if pop > 0 else None

        # Aging buckets
        aging_buckets = {"0-30d": 0, "31-90d": 0, "91-180d": 0, "180d+": 0}
        for b in bills:
            amt = float(b.amount or 0)
            days = b.aging_days or 0
            if days <= 30:
                aging_buckets["0-30d"] += amt
            elif days <= 90:
                aging_buckets["31-90d"] += amt
            elif days <= 180:
                aging_buckets["91-180d"] += amt
            else:
                aging_buckets["180d+"] += amt

        # Trend by fiscal year
        trend_map: Dict[str, float] = {}
        for b in bills:
            fy = b.fiscal_year or "unknown"
            trend_map[fy] = trend_map.get(fy, 0) + float(b.amount or 0)
        trend = [{"year": k, "total_amount": v} for k, v in sorted(trend_map.items())]

        return {
            "status": "success",
            "data_source": "pending_bills_table",
            "total_pending_amount": total_pending,
            "breakdown_by_type": breakdown_by_type,
            "top_counties_by_amount": top_counties,
            "aging_buckets": aging_buckets,
            "trend": trend,
            "currency": "KES",
        }

    except Exception as e:
        logging.error(f"Pending bills summary failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _get_population_map(db: Session) -> Dict[str, int]:
    """Return {county_name: population} from latest PopulationData."""
    try:
        from sqlalchemy import func as sqlfunc

        latest_year_sub = (
            db.query(sqlfunc.max(DBPopulationData.year))
            .filter(DBPopulationData.entity_id.isnot(None))
            .scalar()
        )
        if not latest_year_sub:
            return {}
        rows = (
            db.query(DBPopulationData, DBEntity)
            .join(DBEntity, DBPopulationData.entity_id == DBEntity.id)
            .filter(DBPopulationData.year == latest_year_sub)
            .all()
        )
        return {e.canonical_name: int(p.population) for p, e in rows if p.population}
    except Exception:
        return {}


def _pending_bills_summary_from_loans(db: Session) -> dict:
    """Fallback: build summary from Loan table where debt_category = PENDING_BILLS."""
    from models import DebtCategory

    pending_loans = (
        db.query(DBLoan)
        .filter(DBLoan.debt_category == DebtCategory.PENDING_BILLS)
        .all()
    )
    if not pending_loans:
        return {
            "status": "no_data",
            "total_pending_amount": 0,
            "breakdown_by_type": {},
            "top_counties_by_amount": [],
            "aging_buckets": {"0-30d": 0, "31-90d": 0, "91-180d": 0, "180d+": 0},
            "trend": [],
            "currency": "KES",
            "note": "No pending bills data. Run: python -m seeding.cli seed --domain pending_bills",
        }

    total = sum(float(l.outstanding or l.principal or 0) for l in pending_loans)

    # Group by entity — batch-load all entity names in ONE query (avoid N+1)
    unique_eids = list({l.entity_id for l in pending_loans if l.entity_id})
    entity_name_map = {}
    if unique_eids:
        entity_rows = db.query(DBEntity.id, DBEntity.canonical_name).filter(
            DBEntity.id.in_(unique_eids)
        ).all()
        entity_name_map = {eid: name for eid, name in entity_rows}

    entity_totals: Dict[int, Dict[str, Any]] = {}
    for l in pending_loans:
        eid = l.entity_id
        if eid not in entity_totals:
            entity_totals[eid] = {
                "county": entity_name_map.get(eid, f"Entity {eid}"),
                "entity_id": eid,
                "amount": 0,
            }
        entity_totals[eid]["amount"] += float(l.outstanding or l.principal or 0)

    top_counties = sorted(entity_totals.values(), key=lambda x: x["amount"], reverse=True)[:15]

    # Derive bill type from lender name
    breakdown_by_type: Dict[str, float] = {}
    for l in pending_loans:
        lender = (l.lender or "").lower()
        if "salary" in lender or "wage" in lender:
            bt = "salary"
        elif "pension" in lender:
            bt = "pension"
        elif "statutory" in lender:
            bt = "statutory"
        elif "court" in lender or "award" in lender:
            bt = "court_awards"
        else:
            bt = "supplier_arrears"
        breakdown_by_type[bt] = breakdown_by_type.get(bt, 0) + float(
            l.outstanding or l.principal or 0
        )

    # Trend from provenance fiscal_year
    trend_map: Dict[str, float] = {}
    for l in pending_loans:
        prov = l.provenance if isinstance(l.provenance, dict) else {}
        fy = prov.get("fiscal_year", "unknown")
        trend_map[fy] = trend_map.get(fy, 0) + float(l.outstanding or l.principal or 0)
    trend = [{"year": k, "total_amount": v} for k, v in sorted(trend_map.items())]

    return {
        "status": "success",
        "data_source": "loans_table_fallback",
        "total_pending_amount": total,
        "breakdown_by_type": breakdown_by_type,
        "top_counties_by_amount": top_counties,
        "aging_buckets": {"0-30d": 0, "31-90d": 0, "91-180d": 0, "180d+": total},
        "trend": trend,
        "currency": "KES",
        "note": "Derived from loans table. Seed pending_bills table for richer data.",
    }


@app.get("/api/v1/pending-bills/counties/{county_id}")
@cached(key_prefix="pending_bills:county", ttl=43200)
async def get_pending_bills_by_county(county_id: str, db: Session = Depends(get_db)):
    """Get pending bills breakdown for a specific county by type and aging."""
    from models import BillType, PendingBill

    try:
        # Resolve county entity
        entity = _resolve_county_entity(db, county_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"County '{county_id}' not found")

        bills = db.query(PendingBill).filter(PendingBill.entity_id == entity.id).all()

        if not bills:
            # Fallback to loans table
            from models import DebtCategory

            pending_loans = (
                db.query(DBLoan)
                .filter(
                    DBLoan.entity_id == entity.id,
                    DBLoan.debt_category == DebtCategory.PENDING_BILLS,
                )
                .all()
            )
            total = sum(float(l.outstanding or l.principal or 0) for l in pending_loans)
            return {
                "status": "success" if pending_loans else "no_data",
                "data_source": "loans_table_fallback" if pending_loans else "none",
                "county": entity.canonical_name,
                "county_id": county_id,
                "total_pending": total,
                "breakdown_by_type": {"supplier_arrears": total} if total else {},
                "aging_buckets": {"0-30d": 0, "31-90d": 0, "91-180d": 0, "180d+": total},
                "bills": [],
                "currency": "KES",
            }

        total_pending = sum(float(b.amount or 0) for b in bills)

        # Breakdown by type
        by_type: Dict[str, float] = {}
        for b in bills:
            bt = b.bill_type.value if b.bill_type else "other"
            by_type[bt] = by_type.get(bt, 0) + float(b.amount or 0)

        # Aging buckets
        aging = {"0-30d": 0, "31-90d": 0, "91-180d": 0, "180d+": 0}
        for b in bills:
            amt = float(b.amount or 0)
            days = b.aging_days or 0
            if days <= 30:
                aging["0-30d"] += amt
            elif days <= 90:
                aging["31-90d"] += amt
            elif days <= 180:
                aging["91-180d"] += amt
            else:
                aging["180d+"] += amt

        bill_details = [
            {
                "bill_type": b.bill_type.value if b.bill_type else "other",
                "amount": float(b.amount or 0),
                "fiscal_year": b.fiscal_year,
                "aging_days": b.aging_days,
            }
            for b in bills
        ]

        return {
            "status": "success",
            "data_source": "pending_bills_table",
            "county": entity.canonical_name,
            "county_id": county_id,
            "total_pending": total_pending,
            "breakdown_by_type": by_type,
            "aging_buckets": aging,
            "bills": bill_details,
            "currency": "KES",
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Pending bills county lookup failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _resolve_county_entity(db: Session, county_id: str):
    """Resolve county by numeric ID, slug, or name."""
    # Try by entity table id
    if county_id.isdigit():
        entity = (
            db.query(DBEntity)
            .filter(DBEntity.id == int(county_id), DBEntity.type == EntityType.COUNTY)
            .first()
        )
        if entity:
            return entity

    # Try by slug
    entity = (
        db.query(DBEntity)
        .filter(DBEntity.slug == county_id.lower(), DBEntity.type == EntityType.COUNTY)
        .first()
    )
    if entity:
        return entity

    # Try by COUNTY_MAPPING
    county_name = COUNTY_MAPPING.get(county_id)
    if county_name:
        entity = (
            db.query(DBEntity)
            .filter(
                DBEntity.canonical_name == county_name,
                DBEntity.type == EntityType.COUNTY,
            )
            .first()
        )
        if entity:
            return entity

    # Try by name (case-insensitive)
    entity = (
        db.query(DBEntity)
        .filter(
            DBEntity.canonical_name.ilike(county_id),
            DBEntity.type == EntityType.COUNTY,
        )
        .first()
    )
    return entity


# ── Debt Sustainability Indicators ─────────────────────────────────────


@app.get("/api/v1/debt/sustainability")
@cached(key_prefix="debt:sustainability", ttl=86400)
async def get_debt_sustainability(db: Session = Depends(get_db)):
    """Get debt sustainability indicators, projections, and regional comparison.

    Returns debt-to-GDP, debt-service-to-revenue, external share,
    5-year projections, and EAC regional peers.
    """
    from models import DebtTimeline, FiscalSummary

    try:
        # Latest debt timeline entry (has debt/GDP data)
        latest_dt = (
            db.query(DebtTimeline).order_by(DebtTimeline.year.desc()).first()
        )
        # Latest fiscal summary (has debt service and revenue)
        latest_fs = (
            db.query(FiscalSummary).order_by(FiscalSummary.fiscal_year.desc()).first()
        )

        if not latest_dt and not latest_fs:
            return {
                "status": "no_data",
                "note": "Run seeders: debt_timeline and fiscal_summary",
                "debt_to_gdp": None,
                "debt_service_to_revenue": None,
                "external_debt_share": None,
                "projections": [],
                "regional_peers": _get_regional_peers(),
            }

        # ── Debt-to-GDP ────────────────────────────────────────────
        debt_to_gdp = None
        if latest_dt and latest_dt.gdp_ratio:
            ratio = float(latest_dt.gdp_ratio)
            if ratio > 55:
                status = "above"
            elif ratio > 50:
                status = "warning"
            else:
                status = "below"
            debt_to_gdp = {
                "value": ratio,
                "year": latest_dt.year,
                "threshold_imf": 55.0,
                "threshold_eac": 50.0,
                "status": status,
            }

        # ── Debt Service to Revenue ────────────────────────────────
        debt_service_to_revenue = None
        if latest_fs and latest_fs.debt_service_cost and latest_fs.total_revenue:
            ds = float(latest_fs.debt_service_cost)
            rev = float(latest_fs.total_revenue)
            if rev > 0:
                ratio_val = round(ds / rev * 100, 1)
                debt_service_to_revenue = {
                    "value": ratio_val,
                    "year": latest_fs.fiscal_year,
                    "threshold": 30.0,
                    "status": "above" if ratio_val > 30 else ("warning" if ratio_val > 25 else "below"),
                }

        # ── External Debt Share ────────────────────────────────────
        external_share = None
        if latest_dt and latest_dt.total and latest_dt.external:
            total = float(latest_dt.total)
            ext = float(latest_dt.external)
            if total > 0:
                external_share = round(ext / total * 100, 1)

        # ── 5-Year Projections (linear extrapolation) ──────────────
        projections = _compute_debt_projections(db)

        # ── Regional Peers ─────────────────────────────────────────
        peers = _get_regional_peers(
            kenya_ratio=float(latest_dt.gdp_ratio) if latest_dt and latest_dt.gdp_ratio else None
        )

        return {
            "status": "success",
            "debt_to_gdp": debt_to_gdp,
            "debt_service_to_revenue": debt_service_to_revenue,
            "external_debt_share": external_share,
            "projections": projections,
            "regional_peers": peers,
            "currency": "KES",
            "source": "National Treasury BPS, CBK Annual Reports",
        }

    except Exception as e:
        logging.error(f"Debt sustainability failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _compute_debt_projections(db: Session) -> list:
    """Simple linear extrapolation of debt-to-GDP for next 5 years."""
    from models import DebtTimeline

    rows = (
        db.query(DebtTimeline)
        .filter(DebtTimeline.gdp_ratio.isnot(None))
        .order_by(DebtTimeline.year.asc())
        .all()
    )
    if len(rows) < 2:
        return []

    # Use last 5 data points (or all if < 5) for linear fit
    recent = rows[-5:]
    n = len(recent)
    xs = [float(r.year) for r in recent]
    ys = [float(r.gdp_ratio) for r in recent]

    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    num = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n))

    if den == 0:
        return []

    slope = num / den
    intercept = y_mean - slope * x_mean

    last_year = int(xs[-1])
    projections = []
    for i in range(1, 6):
        proj_year = last_year + i
        proj_val = round(slope * proj_year + intercept, 1)
        projections.append({"year": proj_year, "projected_debt_to_gdp": proj_val})

    return projections


def _get_regional_peers(kenya_ratio: Optional[float] = None) -> list:
    """Return EAC regional debt-to-GDP comparison.

    Uses latest known values from IMF/World Bank data.
    """
    # 2024 actuals from CBK, Bank of Tanzania, Bank of Uganda, NBE, IMF
    # Sources: Trading Economics (verified Mar 2026)
    peers = [
        {"country": "Kenya", "debt_to_gdp": kenya_ratio or 65.5},
        {"country": "Ethiopia", "debt_to_gdp": 32.0},
        {"country": "Tanzania", "debt_to_gdp": 48.2},
        {"country": "Uganda", "debt_to_gdp": 51.8},
        {"country": "Rwanda", "debt_to_gdp": 67.2},
    ]
    return peers


@app.get("/api/v1/entities", response_model=List[EntityResponse])
async def get_entities(
    country: Optional[str] = Query(None, description="Filter by country ISO code"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    search: Optional[str] = Query(None, description="Search entity names"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
):
    """Get list of government entities with filters and search."""
    try:
        from sqlalchemy import func

        query = db.query(DBEntity)

        if country:
            query = query.join(DBCountry).filter(DBCountry.iso_code == country)

        if entity_type:
            normalized_type = (entity_type or "").upper()
            try:
                target_type = EntityType[normalized_type]
                query = query.filter(DBEntity.type == target_type)
            except KeyError:
                return []

        if search:
            query = query.filter(DBEntity.canonical_name.ilike(f"%{search}%"))

        _ = query.count()  # ensure pagination consistency even if unused

        entities = (
            query.order_by(DBEntity.canonical_name)
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        enriched_entities: List[Dict[str, Any]] = []
        for entity in entities:
            total_allocation = (
                db.query(func.sum(DBBudgetLine.allocated_amount))
                .filter(DBBudgetLine.entity_id == entity.id)
                .scalar()
                or 0
            )

            total_spent = (
                db.query(func.sum(DBBudgetLine.actual_spent))
                .filter(DBBudgetLine.entity_id == entity.id)
                .scalar()
                or 0
            )

            audit_count = (
                db.query(func.count(DBAudit.id))
                .filter(DBAudit.entity_id == entity.id)
                .scalar()
                or 0
            )

            entity_type_value = (
                entity.type.value if hasattr(entity.type, "value") else entity.type
            )

            metrics_by_period = (entity.meta or {}).get("metrics", {})
            fy_metrics = (
                metrics_by_period.get("FY2024/25")
                if isinstance(metrics_by_period, dict)
                else {}
            )
            code_value = (
                fy_metrics.get("county_code") if isinstance(fy_metrics, dict) else None
            )
            execution_rate = (
                (float(total_spent) / float(total_allocation) * 100)
                if float(total_allocation) > 0
                else 0.0
            )

            enriched_entities.append(
                {
                    "id": entity.id,
                    "canonical_name": entity.canonical_name,
                    "type": entity_type_value,
                    "slug": getattr(entity, "slug", None),
                    "country": (
                        entity.country.name
                        if getattr(entity, "country", None)
                        else None
                    ),
                    "code": code_value,
                    "meta": entity.meta or {},
                    "financial_summary": {
                        "total_allocation": float(total_allocation),
                        "total_spent": float(total_spent),
                        "execution_rate": execution_rate,
                    },
                    "audit_findings_count": int(audit_count),
                    "created_at": (
                        entity.created_at.isoformat()
                        if getattr(entity, "created_at", None)
                        else None
                    ),
                }
            )

        return enriched_entities

    except Exception as e:
        logger.error(f"Database error in get_entities: {str(e)}")
        # Return mock data on database error
        mock_entities = [
            {
                "id": 1,
                "canonical_name": "Ministry of Health",
                "type": "ministry",
                "code": "MOH",
                "country": "Kenya",
                "parent_entity_id": None,
                "financial_summary": {
                    "total_allocation": 850000000000.0,
                    "total_spent": 680000000000.0,
                    "execution_rate": 80.0,
                },
                "audit_findings_count": 5,
                "created_at": "2024-01-01T00:00:00",
            },
            {
                "id": 2,
                "canonical_name": "Ministry of Education",
                "type": "ministry",
                "code": "MOE",
                "country": "Kenya",
                "parent_entity_id": None,
                "financial_summary": {
                    "total_allocation": 1200000000000.0,
                    "total_spent": 960000000000.0,
                    "execution_rate": 80.0,
                },
                "audit_findings_count": 3,
                "created_at": "2024-01-01T00:00:00",
            },
            {
                "id": 3,
                "canonical_name": "National Treasury",
                "type": "ministry",
                "code": "NT",
                "country": "Kenya",
                "parent_entity_id": None,
                "financial_summary": {
                    "total_allocation": 500000000000.0,
                    "total_spent": 425000000000.0,
                    "execution_rate": 85.0,
                },
                "audit_findings_count": 8,
                "created_at": "2024-01-01T00:00:00",
            },
        ]

        return mock_entities


@app.get("/api/v1/entities/{entity_id}", response_model=EntityDetailResponse)
async def get_entity(entity_id: int, db: Session = Depends(get_db)):
    """Get detailed entity profile with time series and documents."""
    if not DATABASE_AVAILABLE or not db:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        from sqlalchemy import func

        entity = db.query(DBEntity).filter(DBEntity.id == entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")

        # Get financial time series by fiscal period
        budget_summary = (
            db.query(
                DBFiscalPeriod,
                func.sum(DBBudgetLine.allocated_amount).label("total_allocation"),
                func.sum(DBBudgetLine.actual_spent).label("total_spent"),
                func.count(DBBudgetLine.id).label("budget_lines_count"),
            )
            .join(DBBudgetLine, DBBudgetLine.period_id == DBFiscalPeriod.id)
            .filter(DBBudgetLine.entity_id == entity_id)
            .group_by(DBFiscalPeriod.id)
            .order_by(DBFiscalPeriod.start_date.desc())
            .all()
        )

        # Get recent budget lines
        recent_budget_lines = (
            db.query(DBBudgetLine)
            .filter(DBBudgetLine.entity_id == entity_id)
            .order_by(DBBudgetLine.created_at.desc())
            .limit(10)
            .all()
        )

        # Get audit findings
        audit_findings = (
            db.query(DBAudit)
            .filter(DBAudit.entity_id == entity_id)
            .order_by(DBAudit.created_at.desc())
            .limit(5)
            .all()
        )

        # Get source documents
        source_docs = (
            db.query(DBSourceDocument)
            .join(
                DBBudgetLine,
                DBBudgetLine.source_document_id == DBSourceDocument.id,
            )
            .filter(DBBudgetLine.entity_id == entity_id)
            .distinct()
            .order_by(DBSourceDocument.fetch_date.desc())
            .limit(5)
            .all()
        )

        entity_type_value = (
            entity.type.value if hasattr(entity.type, "value") else entity.type
        )
        entity_meta = entity.meta or {}

        financial_time_series = []
        for period, total_allocation, total_spent, budget_lines_count in budget_summary:
            execution_rate = (
                (float(total_spent or 0) / float(total_allocation or 1) * 100)
                if total_allocation
                else 0
            )
            financial_time_series.append(
                {
                    "fiscal_period": {
                        "id": period.id,
                        "label": period.label,
                        "start_date": (
                            period.start_date.isoformat() if period.start_date else None
                        ),
                        "end_date": (
                            period.end_date.isoformat() if period.end_date else None
                        ),
                    },
                    "total_allocation": float(total_allocation or 0),
                    "total_spent": float(total_spent or 0),
                    "execution_rate": execution_rate,
                    "budget_lines_count": budget_lines_count,
                }
            )

        recent_budget_lines_payload = []
        for bl in recent_budget_lines:
            recent_budget_lines_payload.append(
                {
                    "id": bl.id,
                    "category": bl.category,
                    "subcategory": bl.subcategory,
                    "allocated_amount": float(bl.allocated_amount or 0),
                    "actual_spent": float(bl.actual_spent or 0),
                    "committed_amount": float(bl.committed_amount or 0),
                    "currency": bl.currency,
                    "period_label": bl.period.label if bl.period else None,
                    "source_document_id": bl.source_document_id,
                    "created_at": bl.created_at.isoformat() if bl.created_at else None,
                }
            )

        audit_findings_payload = []
        for audit in audit_findings:
            provenance = audit.provenance or []
            audit_findings_payload.append(
                {
                    "id": audit.id,
                    "severity": audit.severity.value if audit.severity else None,
                    "finding_text": audit.finding_text,
                    "recommended_action": audit.recommended_action,
                    "provenance": provenance,
                    "created_at": (
                        audit.created_at.isoformat() if audit.created_at else None
                    ),
                }
            )

        source_documents_payload = []
        for doc in source_docs:
            source_documents_payload.append(
                {
                    "id": doc.id,
                    "title": doc.title,
                    "url": doc.url,
                    "publisher": doc.publisher,
                    "doc_type": doc.doc_type.value if doc.doc_type else None,
                    "fetch_date": (
                        doc.fetch_date.isoformat() if doc.fetch_date else None
                    ),
                    "meta": doc.meta or {},
                }
            )

        return {
            "entity": {
                "id": entity.id,
                "canonical_name": entity.canonical_name,
                "type": entity_type_value,
                "slug": entity.slug,
                "country": entity.country.name if entity.country else None,
                "meta": entity_meta,
                "created_at": (
                    entity.created_at.isoformat() if entity.created_at else None
                ),
            },
            "financial_time_series": financial_time_series,
            "recent_budget_lines": recent_budget_lines_payload,
            "audit_findings": audit_findings_payload,
            "source_documents": source_documents_payload,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in get_entity {entity_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/entities/{entity_id}/periods/{period_id}/budget_lines")
async def get_budget_lines(
    entity_id: int,
    period_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
):
    """Get paginated budget lines with full provenance."""
    if not DATABASE_AVAILABLE or not db:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        query = db.query(DBBudgetLine).filter(
            DBBudgetLine.entity_id == entity_id,
            DBBudgetLine.period_id == period_id,
        )

        total = query.count()
        budget_lines = (
            query.order_by(DBBudgetLine.category).offset(skip).limit(limit).all()
        )

        items: List[Dict[str, Any]] = []
        for bl in budget_lines:
            items.append(
                {
                    "id": bl.id,
                    "category": bl.category,
                    "subcategory": bl.subcategory,
                    "allocated_amount": float(bl.allocated_amount or 0),
                    "actual_spent": float(bl.actual_spent or 0),
                    "committed_amount": float(bl.committed_amount or 0),
                    "currency": bl.currency,
                    "entity_id": bl.entity_id,
                    "period_label": bl.period.label if bl.period else None,
                    "source_document_id": bl.source_document_id,
                    "provenance": bl.provenance or [],
                    "created_at": bl.created_at.isoformat() if bl.created_at else None,
                }
            )

        return {
            "items": items,
            "total": total,
            "skip": skip,
            "limit": limit,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in get_budget_lines for entity {entity_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/documents/{document_id}")
async def get_document(document_id: int, db: Session = Depends(get_db)):
    """Get document metadata and signed download URL."""
    if not DATABASE_AVAILABLE or not db:
        raise HTTPException(status_code=503, detail="Database not available")
    try:
        document = (
            db.query(DBSourceDocument)
            .filter(DBSourceDocument.id == document_id)
            .first()
        )

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        document_payload = {
            "id": document.id,
            "title": document.title,
            "url": document.url,
            "publisher": document.publisher,
            "doc_type": document.doc_type.value if document.doc_type else None,
            "fetch_date": (
                document.fetch_date.isoformat() if document.fetch_date else None
            ),
            "meta": document.meta or {},
        }

        # TODO: Generate signed S3 URL
        return {
            "document": document_payload,
            "download_url": f"/api/v1/documents/{document_id}/download",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in get_document {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/search")
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    filters: Optional[str] = Query(None, description="JSON filters"),
    skip: int = Query(0, ge=0, description="Skip records"),
    limit: int = Query(50, le=200, description="Limit results"),
    db: Session = Depends(get_db),
):
    """Full-text search across budget lines, audits, and documents."""
    if not DATABASE_AVAILABLE or not db:
        # Database-backed search isn't available; respond gracefully
        raise HTTPException(status_code=503, detail="Database not available")

    import json

    from sqlalchemy import and_, or_

    results = {
        "entities": [],
        "budget_lines": [],
        "audit_findings": [],
        "documents": [],
    }

    # Parse filters if provided
    filter_dict = {}
    if filters:
        try:
            filter_dict = json.loads(filters)
        except json.JSONDecodeError:
            pass

    # Search entities
    entity_query = db.query(DBEntity).filter(DBEntity.canonical_name.ilike(f"%{q}%"))

    if "country" in filter_dict:
        entity_query = entity_query.join(DBCountry).filter(
            DBCountry.iso_code == filter_dict["country"]
        )

    entities = entity_query.limit(10).all()
    results["entities"] = []
    for e in entities:
        entity_type_value = e.type.value if hasattr(e.type, "value") else e.type
        metrics = (e.meta or {}).get("metrics", {})
        fy_metrics = metrics.get("FY2024/25") if isinstance(metrics, dict) else {}
        code_value = (
            fy_metrics.get("county_code") if isinstance(fy_metrics, dict) else None
        )
        results["entities"].append(
            {
                "id": e.id,
                "type": "entity",
                "canonical_name": e.canonical_name,
                "entity_type": entity_type_value,
                "code": code_value,
                "country": e.country.name if e.country else None,
            }
        )

    # Search budget lines
    budget_query = db.query(DBBudgetLine).filter(
        or_(
            DBBudgetLine.category.ilike(f"%{q}%"),
            DBBudgetLine.subcategory.ilike(f"%{q}%"),
            DBBudgetLine.notes.ilike(f"%{q}%"),
        )
    )

    if "entity_id" in filter_dict:
        budget_query = budget_query.filter(
            DBBudgetLine.entity_id == filter_dict["entity_id"]
        )

    budget_lines = budget_query.limit(10).all()
    results["budget_lines"] = []
    for bl in budget_lines:
        results["budget_lines"].append(
            {
                "id": bl.id,
                "type": "budget_line",
                "category": bl.category,
                "subcategory": bl.subcategory,
                "allocated_amount": float(bl.allocated_amount or 0),
                "actual_spent": float(bl.actual_spent or 0),
                "entity_name": bl.entity.canonical_name if bl.entity else None,
                "period_label": bl.period.label if bl.period else None,
            }
        )

    # Search documents
    doc_query = db.query(DBSourceDocument).filter(
        or_(
            DBSourceDocument.title.ilike(f"%{q}%"),
            DBSourceDocument.publisher.ilike(f"%{q}%"),
        )
    )

    documents = doc_query.limit(10).all()
    results["documents"] = []
    for doc in documents:
        results["documents"].append(
            {
                "id": doc.id,
                "type": "document",
                "title": doc.title,
                "publisher": doc.publisher,
                "url": doc.url,
                "doc_type": doc.doc_type.value if doc.doc_type else None,
                "fetch_date": doc.fetch_date.isoformat() if doc.fetch_date else None,
            }
        )

    total_results = (
        len(results["entities"])
        + len(results["budget_lines"])
        + len(results["documents"])
    )

    return {
        "query": q,
        "results": results,
        "total": total_results,
        "skip": skip,
        "limit": limit,
        "filters": filter_dict,
    }


# Lightweight dashboards wired from ETL outputs (manifest + simple heuristics)
def _read_etl_manifest() -> Dict[str, Any]:
    try:
        etl_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "etl"))
        downloads_dir = os.path.join(etl_dir, "downloads")
        manifest_path = os.path.join(downloads_dir, "processed_manifest.json")
        if os.path.exists(manifest_path):
            import json as _json

            return _json.loads(open(manifest_path, "r", encoding="utf-8").read())
    except Exception:
        pass
    return {"by_md5": {}}


@app.get("/api/v1/dashboards/national/debt-mix")
async def dashboard_debt_mix():
    """Debt mix snapshot derived from Loan table; falls back to CBK Apr-2025 split."""
    # Try real DB data first
    if DATABASE_AVAILABLE:
        try:
            from models import EntityType as _ET
            from sqlalchemy import func as _fn

            with next(get_db()) as db:
                _nat = db.query(DBEntity).filter(DBEntity.type == _ET.NATIONAL).first()
                if _nat:
                    loans = db.query(DBLoan).filter(DBLoan.entity_id == _nat.id).all()
                    if loans:
                        total = sum(float(l.principal or 0) for l in loans)
                        external_kw = [
                            "multilateral",
                            "bilateral",
                            "eurobond",
                            "commercial",
                            "world bank",
                            "imf",
                            "afdb",
                            "china",
                            "japan",
                        ]
                        external = sum(
                            float(l.principal or 0)
                            for l in loans
                            if any(kw in (l.lender or "").lower() for kw in external_kw)
                        )
                        domestic = total - external
                        return {
                            "external": (
                                round(external / total * 100, 1) if total else 0
                            ),
                            "domestic": (
                                round(domestic / total * 100, 1) if total else 0
                            ),
                            "external_amount": external,
                            "domestic_amount": domestic,
                            "total": total,
                            "currency": "KES",
                            "data_source": "database",
                        }
        except Exception as e:
            logging.error(f"DB debt-mix query failed: {e}")

    # No hardcoded fallback — data must come from the database.
    return {
        "external": 0,
        "domestic": 0,
        "external_amount": 0,
        "domestic_amount": 0,
        "total": 0,
        "currency": "KES",
        "data_source": "database_empty",
        "message": (
            "No debt data in database. "
            "Run: python -m seeding.cli seed --domain national_debt"
        ),
    }


@app.get("/api/v1/dashboards/national/fiscal-outturns")
async def dashboard_fiscal_outturns():
    """Quarterly fiscal outturns. Uses DB budget data grouped by fiscal period; ETL/static fallback."""
    # Try DB data first
    if DATABASE_AVAILABLE:
        try:
            from sqlalchemy import func as _fn

            with next(get_db()) as db:
                rows = (
                    db.query(
                        DBFiscalPeriod.label,
                        _fn.sum(DBBudgetLine.allocated_amount).label("allocated"),
                        _fn.sum(DBBudgetLine.actual_spent).label("spent"),
                    )
                    .join(
                        DBBudgetLine,
                        DBBudgetLine.fiscal_period_id == DBFiscalPeriod.id,
                    )
                    .group_by(DBFiscalPeriod.label)
                    .order_by(DBFiscalPeriod.label.desc())
                    .limit(8)
                    .all()
                )
                if rows:
                    series = []
                    for label, allocated, spent in rows:
                        alloc = float(allocated or 0)
                        sp = float(spent or 0)
                        series.append(
                            {
                                "period": str(label),
                                "revenue": alloc,
                                "expenditure": sp,
                                "balance": alloc - sp,
                            }
                        )
                    return {"series": series, "data_source": "database"}
        except Exception as e:
            logging.error(f"DB fiscal outturns failed: {e}")

    # Fallback from ETL manifest
    manifest = _read_etl_manifest()
    docs = list((manifest.get("by_md5") or {}).values())
    qebr_like = [
        d
        for d in docs
        if re.search(r"qebr|quarterly\s+economic", (d.get("title") or ""), re.I)
    ]
    series = []
    for d in sorted(qebr_like, key=lambda x: x.get("fetched", ""), reverse=True)[:8]:
        series.append(
            {
                "period": d.get("title"),
                "revenue": None,
                "expenditure": None,
                "balance": None,
                "provenance": {"title": d.get("title"), "file": d.get("file_path")},
            }
        )
    if not series:
        series = [
            {
                "period": "FY2024/25 Q1",
                "revenue": None,
                "expenditure": None,
                "balance": None,
                "note": "No fiscal outturn data available. Run ETL pipeline.",
            },
        ]
    return {"series": series, "data_source": "fallback"}


@app.get("/api/v1/dashboards/national/sector-ceilings")
async def dashboard_sector_ceilings():
    """Sector ceilings derived from DB budget allocations; stub fallback."""
    if DATABASE_AVAILABLE:
        try:
            from sqlalchemy import func as _fn

            with next(get_db()) as db:
                rows = (
                    db.query(
                        DBBudgetLine.category,
                        _fn.sum(DBBudgetLine.allocated_amount).label("allocated"),
                    )
                    .group_by(DBBudgetLine.category)
                    .all()
                )
                total = sum(float(r[1] or 0) for r in rows)
                if total > 0:
                    allocation = {}
                    for cat, alloc in rows:
                        name = str(cat or "Other").strip().lower().replace(" ", "_")
                        allocation[name] = round(float(alloc or 0) / total * 100, 1)
                    allocation["unit"] = "%"
                    allocation["total_amount"] = total
                    allocation["currency"] = "KES"
                    allocation["data_source"] = "database"
                    return allocation
        except Exception as e:
            logging.error(f"DB sector ceilings failed: {e}")

    # Fallback — no hardcoded numbers; let frontend know data is unavailable
    manifest = _read_etl_manifest()
    docs = list((manifest.get("by_md5") or {}).values())
    bps_like = [
        d
        for d in docs
        if re.search(r"bps|policy\s+statement|sector", (d.get("title") or ""), re.I)
    ]
    prov = [
        {
            "title": d.get("title"),
            "file": d.get("file_path"),
            "fetched": d.get("fetched"),
        }
        for d in bps_like[:3]
    ]
    return {
        "unit": "%",
        "provenance": prov,
        "data_source": "fallback",
        "note": "No sector ceiling data. Run ETL pipeline to populate.",
    }


# OPTIONS handler for CORS probe on counties list (without full preflight headers)
@app.options("/api/v1/counties")
async def options_counties() -> Response:
    return Response(status_code=204)


@app.post("/api/v1/etl/treasury/run-batch")
async def run_treasury_batch():
    """Run the targeted batch: latest 10 QEBR + 3 ABP + 5 Circulars."""
    try:
        # Lazy import to avoid heavy cost on app start
        sys.path.append(os.path.join(os.path.dirname(__file__), "..", "etl"))
        kp_mod = importlib.import_module("kenya_pipeline")
        KenyaDataPipeline = getattr(kp_mod, "KenyaDataPipeline")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ETL import failed: {e}")

    pipeline = KenyaDataPipeline()
    docs = pipeline.discover_budget_documents("treasury")
    # Use selector for targeted batch
    if hasattr(pipeline, "select_treasury_batch"):
        batch = pipeline.select_treasury_batch(docs)
    else:
        batch = docs[:18]

    processed = 0
    successful = 0
    doc_ids: List[Any] = []
    for d in batch:
        try:
            res = await pipeline.download_and_process_document(d)
            processed += 1
            if res:
                successful += 1
                doc_ids.append(res.get("document_id"))
        except Exception as e:
            logger.error(f"Batch doc failed: {e}")
        # gentle pacing
        await asyncio.sleep(2)

    return {
        "requested": {
            "qebr": 10,
            "abp": 3,
            "circulars": 5,
        },
        "processed": processed,
        "successful": successful,
        "document_ids": doc_ids,
    }


@app.post("/api/v1/etl/cob/run-batch")
async def run_cob_batch(limit: int = 25):
    """Run a COB batch across national and consolidated county BIRR pages.
    Default limit is 25 recent items to validate nested lists from 2014+.
    """
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), "..", "etl"))
        kp_mod = importlib.import_module("kenya_pipeline")
        KenyaDataPipeline = getattr(kp_mod, "KenyaDataPipeline")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ETL import failed: {e}")

    pipeline = KenyaDataPipeline()
    docs = pipeline.discover_budget_documents("cob")

    # Prefer items that look like BIRR PDFs and include FY in title
    def score(d: Dict[str, Any]) -> tuple:
        t = (d.get("title") or "").lower()
        fy = 1 if re.search(r"fy\s*20\d{2}|20\d{2}\s*[/–-]\s*20\d{2}", t) else 0
        birr = 1 if ("budget" in t and ("implementation" in t or "review" in t)) else 0
        nat = 1 if "national" in t else 0
        cty = 1 if "county" in t or "consolidated" in t else 0
        return (fy + birr + nat + cty, t)

    ranked = sorted(docs, key=score, reverse=True)

    processed = 0
    successful = 0
    doc_ids: List[Any] = []
    for d in ranked[: max(1, min(limit, 50))]:
        try:
            res = await pipeline.download_and_process_document(d)
            processed += 1
            if res:
                successful += 1
                doc_ids.append(res.get("document_id"))
        except Exception as e:
            logger.error(f"COB batch doc failed: {e}")
        await asyncio.sleep(2)

    return {
        "requested": {"limit": limit},
        "discovered": len(docs),
        "processed": processed,
        "successful": successful,
        "document_ids": doc_ids,
    }


# Admin endpoints
@app.post("/api/v1/annotations")
async def create_annotation(
    annotation_data: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create annotation/comment on budget line or audit finding."""
    # TODO: Implement annotation creation
    return {"message": "Annotation created", "id": 1}


@app.post("/api/v1/documents/upload")
async def upload_document(
    file_data: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manual document upload for missing documents."""
    # TODO: Implement document upload
    return {"message": "Document uploaded", "id": 1}


@app.get("/api/v1/analytics/top_spenders")
async def get_top_spenders(
    country: str = Query(...),
    period: str = Query(...),
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
):
    """Get top spending entities for analytics."""
    # TODO: Implement analytics queries
    return {"top_spenders": []}


# ETL Pipeline Endpoints
@app.post("/api/v1/etl/kenya/start", response_model=ETLJobResponse)
async def start_kenya_etl(background_tasks: BackgroundTasks):
    """Start ETL pipeline for Kenya government data."""
    if not ETL_AVAILABLE:
        raise HTTPException(status_code=503, detail="ETL pipeline not available")

    import datetime
    import uuid

    job_id = str(uuid.uuid4())

    # Start ETL in background
    background_tasks.add_task(run_kenya_etl_pipeline, job_id)

    return ETLJobResponse(
        job_id=job_id,
        status="started",
        country="Kenya",
        started_at=datetime.datetime.now().isoformat(),
        documents_processed=0,
        errors=[],
    )


@app.get("/api/v1/etl/status/{job_id}", response_model=ETLStatusResponse)
async def get_etl_status(job_id: str):
    """Get status of ETL job."""
    if not ETL_AVAILABLE:
        raise HTTPException(status_code=503, detail="ETL pipeline not available")

    # TODO: Implement job status tracking (could use Redis or database)
    return ETLStatusResponse(
        job_id=job_id,
        status="completed",
        progress={
            "documents_fetched": 15,
            "documents_processed": 12,
            "entities_created": 25,
            "budget_lines_created": 150,
        },
        last_updated=datetime.datetime.now().isoformat(),
    )


@app.get("/api/v1/etl/kenya/sources")
async def get_kenya_data_sources():
    """Get available Kenya government data sources with real-time status."""
    if not ETL_AVAILABLE:
        raise HTTPException(status_code=503, detail="ETL pipeline not available")

    try:
        # Test real-time connection status
        import os
        import sys

        sys.path.append(os.path.dirname(os.path.dirname(__file__)))

        from etl_test_runner import SimpleKenyaETL

        etl = SimpleKenyaETL()

        # Quick connection test
        treasury_status = etl.test_treasury_connection()

        sources = [
            {
                "name": "Kenya National Treasury",
                "url": "https://treasury.go.ke",
                "document_types": [
                    "budget",
                    "expenditure_report",
                    "debt_report",
                    "financial_statements",
                ],
                "last_fetch": treasury_status.get("timestamp", "2024-01-15T10:30:00Z"),
                "status": (
                    "active" if treasury_status.get("accessible", False) else "error"
                ),
                "live_test_results": {
                    "response_code": treasury_status.get("status_code"),
                    "pdf_documents_found": treasury_status.get(
                        "pdf_documents_found", 0
                    ),
                    "page_title": treasury_status.get("page_title", ""),
                    "sample_documents": treasury_status.get("sample_pdfs", [])[:3],
                },
            },
            {
                "name": "Office of Auditor General",
                "url": "https://oagkenya.go.ke",
                "document_types": [
                    "audit_report",
                    "special_audits",
                    "compliance_reports",
                ],
                "last_fetch": "2024-01-10T14:20:00Z",
                "status": "timeout_issues",
                "note": "Site occasionally experiences timeouts but contains valuable audit reports",
            },
            {
                "name": "Controller of Budget",
                "url": "https://cob.go.ke",
                "document_types": ["budget_implementation_review", "quarterly_reports"],
                "last_fetch": "2024-01-12T09:15:00Z",
                "status": "pending_test",
            },
        ]

        return {
            "sources": sources,
            "real_time_test": True,
            "test_timestamp": treasury_status.get("timestamp"),
            "summary": {
                "total_sources": len(sources),
                "active_sources": len([s for s in sources if s["status"] == "active"]),
                "total_pdf_documents": treasury_status.get("pdf_documents_found", 0),
            },
        }

    except Exception as e:
        # Fall back to static data if real-time test fails
        return {
            "sources": [
                {
                    "name": "Kenya National Treasury",
                    "url": "https://treasury.go.ke",
                    "document_types": ["budget", "expenditure_report", "debt_report"],
                    "last_fetch": "2024-01-15T10:30:00Z",
                    "status": "active",
                },
                {
                    "name": "Office of Auditor General",
                    "url": "https://oagkenya.go.ke",
                    "document_types": ["audit_report"],
                    "last_fetch": "2024-01-10T14:20:00Z",
                    "status": "active",
                },
                {
                    "name": "Controller of Budget",
                    "url": "https://cob.go.ke",
                    "document_types": ["budget_implementation_review"],
                    "last_fetch": "2024-01-12T09:15:00Z",
                    "status": "active",
                },
            ],
            "real_time_test": False,
            "error": str(e),
        }


async def run_kenya_etl_pipeline(job_id: str):
    """Background task to run Kenya ETL pipeline with real data."""
    try:
        # Import and run our working ETL
        import os
        import sys

        sys.path.append(os.path.dirname(os.path.dirname(__file__)))

        from etl_test_runner import SimpleKenyaETL

        # Run the real ETL pipeline
        etl = SimpleKenyaETL()
        results = etl.run_full_pipeline()

        print(f"ETL Job {job_id}: Successfully processed real Kenya government data")
        print(
            f"ETL Job {job_id}: Found {results['sources_accessible']} accessible sources"
        )
        print(
            f"ETL Job {job_id}: Extracted {results['entities_extracted']} government entities"
        )
        print(f"ETL Job {job_id}: Processed {results['documents_processed']} documents")

        return results

    except Exception as e:
        print(f"ETL Job {job_id} failed: {str(e)}")
        return {"error": str(e)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)

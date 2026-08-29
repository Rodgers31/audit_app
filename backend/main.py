import asyncio
import concurrent.futures
import contextlib
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
from services.publication_gate import (
    count_withheld_audits,
    file_source_provenance_failure,
    log_withheld_audits,
    missing_funds_provenance_failure,
    publishable_audit_criterion,
)
from seeding.source_registry import next_expected_window
from services.trust_guards import (
    check_budget_sectors,
    check_coverage_staleness,
    check_debt_composition,
    check_period_nonempty,
    check_plausible_total,
    reconcile_debt_totals,
)
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from sqlalchemy import or_, text
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, Response

# Initialize logger early (before Redis cache import).
#
# Stream handler (stdout) is always on — that's what Render / Docker
# capture and what shows up in the platform's log viewer.
#
# File handler is best-effort: write to ``logs/main_backend.log`` if
# the directory exists and is writable, otherwise skip silently. The
# previous default (``FileHandler("main_backend.log")``) wrote to the
# CWD, which on Render is ``/app`` — a root-owned directory the
# non-root ``appuser`` can't create files in, so the worker crashed
# at import time with PermissionError. Writing under ``logs/`` (which
# the Dockerfile chowns to ``appuser``) keeps the file log working
# locally without breaking container starts.
_log_handlers: list[logging.Handler] = [logging.StreamHandler()]
try:
    _log_handlers.append(logging.FileHandler("logs/main_backend.log"))
except (OSError, PermissionError):
    # No writable log dir (read-only FS, missing dir, etc.). Stream
    # handler alone is fine — the platform captures stdout anyway.
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=_log_handlers,
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


def get_current_fiscal_year() -> str:
    """Return the current Kenyan fiscal year key (e.g. 'FY2024/25').

    Kenyan fiscal years run July 1 – June 30.  Before July the
    current FY started the *previous* calendar year.
    """
    today = datetime.date.today()
    start = today.year if today.month >= 7 else today.year - 1
    return f"FY{start}/{(start + 1) % 100:02d}"


def _fy_metrics_key(fiscal_year: Optional[str] = None) -> str:
    """Build the metrics dict key for a given fiscal year, defaulting to current."""
    if not fiscal_year:
        return get_current_fiscal_year()
    return fiscal_year if fiscal_year.startswith("FY") else f"FY{fiscal_year}"


def _resolve_fy_metrics(meta: dict, fiscal_year: Optional[str] = None) -> dict:
    """Get metrics for the requested FY, falling back to the latest available FY.

    When the current fiscal year has no data yet (e.g. early in FY2025/26 when
    only FY2024/25 was ingested), we return the most recent FY's metrics rather
    than returning empty values.
    """
    all_metrics = (meta or {}).get("metrics") or {}
    if not isinstance(all_metrics, dict):
        return {}
    key = _fy_metrics_key(fiscal_year)
    result = all_metrics.get(key)
    if result:
        return result
    # Fallback: latest available FY (sorted descending)
    sorted_keys = sorted(all_metrics.keys(), reverse=True)
    for k in sorted_keys:
        v = all_metrics.get(k)
        if isinstance(v, dict) and v:
            return v
    return {}


# ── Unit & plausibility metadata ──────────────────────────────────────


def _response_meta(
    *,
    unit: str,
    entity_scope: str,
    fiscal_period: str | None = None,
    scope_detail: str | None = None,
    generated_at: str | datetime.datetime | None = None,
    source_updated_at: str | datetime.datetime | None = None,
    covers_through: str | None = None,
    cache_ttl_seconds: int | None = None,
    data_quality: str | None = None,
    quality_notes: list[str] | None = None,
) -> dict:
    """Build a standard ``_meta`` envelope for finance endpoints.

    Core fields
    -----------
    unit: "kes" | "billion_kes" | "percentage" | "mixed"
    entity_scope: "national" | "county" | "all"
    scope_detail: free-text clarification of what the endpoint actually
        measures — e.g. "National-government execution only; excludes
        county equitable share". Surface verbatim in the UI.

    Freshness fields (added April 2026)
    -----------------------------------
    generated_at: ISO-8601 timestamp of when *this response* was built
        (not when data was last refreshed). If omitted, set to now().
    source_updated_at: ISO-8601 timestamp of the most recent row that
        contributed to this response — MAX(created_at) or
        MAX(updated_at) across the tables queried. Tells clients how
        fresh the underlying data is, independent of cache age.
    covers_through: human-readable coverage label (e.g. "FY2024/25" or
        "Q2 2025"). Distinct from *fiscal_period* only when the
        endpoint spans multiple periods and the latest one is what
        clients should show.
    cache_ttl_seconds: the @cached TTL, so clients know the maximum
        staleness they might see. Omit for uncached endpoints.
    data_quality: one of {"official", "estimated", "projected",
        "historical", "mixed"}. Derived from joined SourceDocument
        rows or hardcoded when the endpoint has known provenance.
    quality_notes: list of human-readable caveats surfaced to the UI
        (missing categories, uniform-absorption warnings, divergence
        between sources, etc.). Produced by ``trust_guards`` helpers.
    """
    meta: dict = {"unit": unit, "entity_scope": entity_scope}
    if fiscal_period:
        meta["fiscal_period"] = fiscal_period
    if scope_detail:
        meta["scope_detail"] = scope_detail
    # Always stamp generated_at so the frontend can render a relative
    # "Updated X ago" badge without guessing. Naive-UTC (tzinfo stripped)
    # so the ``isoformat() + "Z"`` below stays correct — utcnow() itself
    # is deprecated on Python 3.12 and removed in 3.13.
    if generated_at is None:
        generated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    if isinstance(generated_at, datetime.datetime):
        meta["generated_at"] = generated_at.isoformat() + "Z"
    else:
        meta["generated_at"] = str(generated_at)
    if source_updated_at is not None:
        if isinstance(source_updated_at, datetime.datetime):
            meta["source_updated_at"] = source_updated_at.isoformat() + "Z"
        else:
            meta["source_updated_at"] = str(source_updated_at)
    if covers_through:
        meta["covers_through"] = covers_through
    if cache_ttl_seconds is not None:
        meta["cache_ttl_seconds"] = int(cache_ttl_seconds)
    if data_quality:
        meta["data_quality"] = data_quality
    if quality_notes:
        # Defensive copy so callers can't mutate meta post-hoc.
        meta["quality_notes"] = list(quality_notes)
    return meta


# Plausibility bounds (order-of-magnitude sanity checks)
_MAX_COUNTY_BUDGET_KES = 50_000_000_000  # 50 B KES – largest county ≈ Nairobi 10B
_MAX_NATIONAL_BUDGET_KES = 10_000_000_000_000  # 10 T KES
_MAX_NATIONAL_BUDGET_BILLION = 10_000  # 10 T KES expressed in billions
_MAX_SINGLE_LOAN_KES = 5_000_000_000_000  # 5 T KES


def _check_plausibility(
    value: float,
    ceiling: float,
    label: str,
    *,
    allow_negative: bool = False,
) -> None:
    """Log a WARNING if *value* exceeds *ceiling* or is unexpectedly negative."""
    if value > ceiling:
        logging.warning(
            "PLAUSIBILITY FAIL: %s = %s exceeds ceiling %s",
            label,
            f"{value:,.0f}",
            f"{ceiling:,.0f}",
        )
    if not allow_negative and value < 0:
        logging.warning(
            "PLAUSIBILITY FAIL: %s = %s is negative",
            label,
            f"{value:,.0f}",
        )


def _latest_county_period(db) -> Optional[int]:
    """Return the period_id of the latest FiscalPeriod that has county BudgetLines.

    This ensures sector/budget queries are scoped to a single fiscal year and
    only include county-level data — never national budget lines or aggregate rows.
    Returns None if no county budget lines exist.
    """
    from sqlalchemy import func as _fn

    row = (
        db.query(DBBudgetLine.period_id)
        .join(DBEntity, DBBudgetLine.entity_id == DBEntity.id)
        .join(DBFiscalPeriod, DBBudgetLine.period_id == DBFiscalPeriod.id)
        .filter(DBEntity.type == EntityType.COUNTY)
        .filter(DBBudgetLine.category != "Total Budget")
        .order_by(DBFiscalPeriod.start_date.desc())
        .limit(1)
        .first()
    )
    return row[0] if row else None


def _latest_national_period(db) -> Optional[int]:
    """Return the period_id of the latest FiscalPeriod that has national BudgetLines."""
    from sqlalchemy import func as _fn

    row = (
        db.query(DBBudgetLine.period_id)
        .join(DBEntity, DBBudgetLine.entity_id == DBEntity.id)
        .join(DBFiscalPeriod, DBBudgetLine.period_id == DBFiscalPeriod.id)
        .filter(DBEntity.type == EntityType.NATIONAL)
        .order_by(DBFiscalPeriod.start_date.desc())
        .limit(1)
        .first()
    )
    return row[0] if row else None


def _is_debt_loan(loan) -> bool:
    """True when a Loan row counts as DEBT for total-debt aggregations.

    The single piece of business logic this encodes: ``PENDING_BILLS``
    rows live in the ``loans`` table for storage convenience but are
    NOT borrowed money — they're unpaid obligations and must NOT be
    summed into "total national debt" or any "debt-to-GDP" ratio.
    Use this predicate (or :func:`_debt_loans_query`) every time you
    iterate ``loans`` to compute a debt total, so a future endpoint
    can't silently inflate the displayed debt by 700B+ the way
    ``/api/v1/debt/national`` did before this helper landed (the
    pending-bills records from PR #84 started writing to the
    ``loans`` table successfully and immediately broke the headline
    Total Debt KPI on the frontend).

    Loans with no ``debt_category`` set count as debt — that matches
    every existing aggregator's pre-fix behaviour.
    """
    from models import DebtCategory as _DC

    if loan.debt_category is None:
        return True
    return loan.debt_category != _DC.PENDING_BILLS


def _debt_loans_query(db, entity_filter):
    """SQLAlchemy query for Loan rows that count as debt.

    Companion to :func:`_is_debt_loan` for the case where the caller
    only needs debt-only loans and never iterates the pending-bills
    rows for any other purpose. Pass ``entity_filter`` as a SQL
    expression — single entity (``DBLoan.entity_id == eid``) or a set
    (``DBLoan.entity_id.in_(eids)``).

    NULL handling matters here: ``loans.debt_category`` is nullable
    (the model has a Python-side default of ``OTHER`` but the writer
    can pass ``debt_category=None`` which overrides the default, and
    older rows seeded before that default existed may also be NULL).
    A naive ``debt_category != PENDING_BILLS`` filter silently drops
    those rows — SQL's three-valued logic makes ``NULL != value``
    evaluate to ``UNKNOWN``, treated as ``FALSE`` in WHERE. Mirror
    :func:`_is_debt_loan`'s "NULL counts as debt" rule by explicitly
    OR-ing in the ``IS NULL`` branch (Copilot review on PR #90
    flagged this on the inline filter sites; baking it into the
    helper keeps every future caller correct by default).
    """
    from models import DebtCategory as _DC

    return db.query(DBLoan).filter(
        entity_filter,
        or_(
            DBLoan.debt_category.is_(None),
            DBLoan.debt_category != _DC.PENDING_BILLS,
        ),
    )


def _entity_period_budget_query(db, entity_id: int, period_id: Optional[int] = None):
    """Return BudgetLine query scoped to a single entity and (optionally) period.

    If period_id is None, auto-resolves to the latest period that has *actual
    execution* data for the entity (sum of ``actual_spent`` > 0). This avoids
    the pathological case where the current fiscal year has been seeded with
    allocations but hasn't yet accumulated spending, which was rendering as
    "0% execution" on county pages.

    Falls back to the latest period by ``start_date`` when no period has
    execution data (e.g. first-year county, seed data issues).

    Excludes 'Total Budget' aggregate rows.
    """
    q = db.query(DBBudgetLine).filter(
        DBBudgetLine.entity_id == entity_id,
        DBBudgetLine.category != "Total Budget",
    )
    if period_id:
        q = q.filter(DBBudgetLine.period_id == period_id)
    else:
        # Prefer the latest period that actually has spending (an executed FY)
        from sqlalchemy import func as _sqlfunc

        latest_executed = (
            db.query(DBBudgetLine.period_id)
            .join(DBFiscalPeriod, DBBudgetLine.period_id == DBFiscalPeriod.id)
            .filter(
                DBBudgetLine.entity_id == entity_id,
                DBBudgetLine.category != "Total Budget",
            )
            .group_by(DBBudgetLine.period_id, DBFiscalPeriod.start_date)
            .having(_sqlfunc.coalesce(_sqlfunc.sum(DBBudgetLine.actual_spent), 0) > 0)
            .order_by(DBFiscalPeriod.start_date.desc())
            .limit(1)
            .scalar()
        )
        # Fallback: latest period by date (first-year county / missing actuals)
        latest = latest_executed or (
            db.query(DBBudgetLine.period_id)
            .join(DBFiscalPeriod, DBBudgetLine.period_id == DBFiscalPeriod.id)
            .filter(
                DBBudgetLine.entity_id == entity_id,
                DBBudgetLine.category != "Total Budget",
            )
            .order_by(DBFiscalPeriod.start_date.desc())
            .limit(1)
            .scalar()
        )
        if latest:
            q = q.filter(DBBudgetLine.period_id == latest)
    return q


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
    "002": "Coast",
    "003": "Coast",
    "004": "Coast",
    "005": "Coast",
    "006": "Coast",
    "047": "Coast",
    "007": "North Eastern",
    "008": "North Eastern",
    "009": "North Eastern",
    "010": "Eastern",
    "011": "Eastern",
    "012": "Eastern",
    "013": "Eastern",
    "014": "Eastern",
    "015": "Eastern",
    "016": "Eastern",
    "017": "Eastern",
    "018": "Central",
    "019": "Central",
    "020": "Central",
    "021": "Central",
    "022": "Central",
    "023": "Rift Valley",
    "024": "Rift Valley",
    "025": "Rift Valley",
    "026": "Rift Valley",
    "027": "Rift Valley",
    "028": "Rift Valley",
    "029": "Rift Valley",
    "030": "Rift Valley",
    "031": "Rift Valley",
    "032": "Rift Valley",
    "033": "Rift Valley",
    "034": "Rift Valley",
    "035": "Rift Valley",
    "036": "Rift Valley",
    "037": "Western",
    "038": "Western",
    "039": "Western",
    "040": "Western",
    "041": "Nyanza",
    "042": "Nyanza",
    "043": "Nyanza",
    "044": "Nyanza",
    "045": "Nyanza",
    "046": "Nyanza",
}

# Enhanced County Analytics API base URL
ENHANCED_COUNTY_API_BASE = os.getenv(
    "ENHANCED_COUNTY_API_BASE", "http://localhost:8003"
)


class InternalAPIClient:
    """Client for making internal API calls to other services"""

    # simple in-memory TTL cache to reduce flakiness and repeated fetches during a session
    _cache: Dict[str, Dict[str, Any]] = {}
    _ttl_seconds = 6 * 60 * 60  # 6 hours
    # Hard cap so the cache can't grow unbounded under traffic that hits
    # many distinct keys (e.g. all 47 county detail endpoints in one
    # session). Mirrors the bound used by RedisCache._memory_cache_max_size
    # in cache/redis_cache.py.
    _max_size = 1024

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
        # Evict expired entries first; if still at cap, drop the oldest
        # by insertion order (Py 3.7+ dicts preserve it). This matches
        # the eviction behaviour in cache/redis_cache.py.
        if len(cls._cache) >= cls._max_size:
            now = time.time()
            for k in [
                k for k, rec in cls._cache.items()
                if now - rec["ts"] > cls._ttl_seconds
            ]:
                cls._cache.pop(k, None)
            while len(cls._cache) >= cls._max_size:
                oldest = next(iter(cls._cache))
                cls._cache.pop(oldest, None)
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


# Supabase-verified auth dependency (legacy HS256 auth.py was removed —
# it validated against a local SECRET_KEY with a hardcoded fallback and
# could never verify real Supabase tokens).
from supabase_auth import get_current_db_user as get_current_user  # noqa: F401


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


# ── Application lifecycle ─────────────────────────────────────────────
# Readiness flag: /health/ready reports 503 until reference data exists.
# /health (used by the uptime pinger) and /health/live answer immediately.
_app_ready = asyncio.Event()


@contextlib.asynccontextmanager
async def _app_lifespan(app_: "FastAPI"):
    """Application lifespan — replaces the deprecated @app.on_event hooks.

    The old startup hook awaited initialize_reference_data() BEFORE the
    server accepted traffic (~3 min on a cold DB), so every deploy /
    process restart served nothing until bootstrap finished. The whole
    startup sequence now runs as a background task: the server binds
    immediately, /health/live answers at once, and /health/ready flips
    to 200 once reference data is confirmed.
    """
    if not DATABASE_AVAILABLE:
        # Config error — fail fast, nothing can work without a DB.
        raise RuntimeError("Database is required for backend startup")

    startup_task = asyncio.create_task(_startup_sequence())
    try:
        yield
    finally:
        startup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await startup_task
        try:
            from services.auto_seeder import stop_auto_seeder

            await stop_auto_seeder()
        except Exception:
            pass


async def _startup_sequence() -> None:
    """Ordered background startup: DB pre-warm → reference data →
    readiness → auto-seeder → cache warmup. Runs off the request path."""
    logger.info("Main Backend API starting up...")
    logger.info(f"Working directory: {os.getcwd()}")

    # Pre-warm the connection pool so the first real query isn't slow.
    try:
        # SessionLocal directly rather than the get_db() FastAPI
        # dependency: `next(get_db())` outside DI leaves the generator
        # suspended, so its finally-close never runs promptly. The
        # Session context manager owns the full lifecycle here.
        from database import SessionLocal as _SessionLocal

        with _SessionLocal() as db:
            db.execute(text("SELECT 1"))
        logger.info("Database connection pool warmed up successfully")
    except Exception as e:
        logger.warning(f"Database pre-warm failed (non-fatal): {e}")

    # Reference county data. Failure leaves the service NOT-ready —
    # visible on /health/ready — instead of crash-looping the process.
    try:
        await asyncio.to_thread(initialize_reference_data, NAME_TO_ID_MAPPING)
    except Exception:  # pragma: no cover - surfaced via readiness + logs
        logger.exception("Failed to initialize reference data")
        return
    _app_ready.set()
    logger.info("Main Backend API startup complete!")

    # Auto-seeder (its initial seed is itself a background task).
    if AUTO_SEEDER_ENABLED:
        try:
            from services.auto_seeder import start_auto_seeder

            await start_auto_seeder()
            logger.info("[AUTO-SEEDER] Service started - data will refresh automatically")
        except Exception as exc:
            logger.warning(f"Auto-seeder not started (non-critical): {exc}")
    else:
        logger.info("Auto-seeder disabled via AUTO_SEEDER_ENABLED=false")

    # ETL scheduler (APScheduler; no-op if the package isn't installed).
    try:
        await _setup_etl_scheduler()
    except Exception as exc:
        logger.warning(f"ETL scheduler not started (non-critical): {exc}")

    # Response-cache warmup (self-HTTP, concurrency-capped).
    if _WARMUP_ENABLED:
        await _warm_cache()
    else:
        logger.info("Cache warmup disabled via AUTO_WARMUP_ENABLED=false")


app = FastAPI(
    title="Government Financial Transparency API",
    description="API for accessing government budget, spending, and audit data with full provenance",
    version="1.0.0",
    lifespan=_app_lifespan,
)


# Auto-seeder for automated data refresh.
# Default OFF in development (it blocks startup and fires on every
# uvicorn --reload) and ON in production (the scheduled refresh job
# actually needs it). Override with AUTO_SEEDER_ENABLED=true/false.
_default_seeder = "true" if getattr(settings, "ENVIRONMENT", "") == "production" else "false"
AUTO_SEEDER_ENABLED = os.getenv("AUTO_SEEDER_ENABLED", _default_seeder).lower() in (
    "true",
    "1",
    "yes",
)


# NOTE: auto-seeder start/stop and cache warmup are driven from
# _startup_sequence / _app_lifespan above (the deprecated
# @app.on_event hooks were consolidated there).


# Hot endpoints that are expensive on cold cache — we pre-warm them on
# startup so the first real user never sees the 3-5 s cold path. List is
# in priority order; later entries depend on prior endpoints' data.
# Disable via AUTO_WARMUP_ENABLED=false (useful for lightweight dev boots).
_WARMUP_ENABLED = os.getenv("AUTO_WARMUP_ENABLED", "true").lower() in ("true", "1", "yes")
# Cap on simultaneous in-flight warm-up requests. Firing all paths at
# once pinned a DB result set in memory per request and pushed the
# 512 MB Render container over its limit during boot. Tunable via
# AUTO_WARMUP_CONCURRENCY; the default of 3 keeps peak memory bounded
# while still finishing the full batch in under a minute.
_WARMUP_CONCURRENCY = max(1, int(os.getenv("AUTO_WARMUP_CONCURRENCY", "3")))
_WARMUP_PATHS: List[str] = [
    # Fiscal & budget
    "/api/v1/fiscal/summary",
    "/api/v1/budget/national",
    "/api/v1/budget/overview",
    "/api/v1/budget/enhanced",
    "/api/v1/budget/utilization",
    # Debt
    "/api/v1/debt/national",
    "/api/v1/debt/national-loans",
    "/api/v1/debt/timeline",
    "/api/v1/debt/sustainability",
    "/api/v1/debt/loans",
    # Audits
    "/api/v1/audits/federal",
    "/api/v1/audits/statistics",
    "/api/v1/audits/fiscal-years",
    "/api/v1/audit/summary",
    # Counties & spending
    "/api/v1/counties",
    "/api/v1/sectors/spending",
    "/api/v1/accountability/missing-funds",
    "/api/v1/sources/summary",
    # Pending bills
    "/api/v1/pending-bills",
    "/api/v1/pending-bills/summary",
    # Economic & freshness
    "/api/v1/economic/population/latest",
    "/api/v1/data/freshness",
    # Money flow (default fiscal year)
    "/api/v1/audit/money-flow/national?year=2024/25",
    "/api/v1/money-flow/all-counties?year=2024/25",
]


async def _warm_cache() -> None:
    """Pre-warm the response cache for high-traffic endpoints.

    Without this, the first user after a deploy pays the full cold-path
    latency on each endpoint they hit. Requests are gated by a
    semaphore (AUTO_WARMUP_CONCURRENCY, default 3) so the boot never
    pins more than N DB result sets in memory at once — without the
    cap the full list ran the 512 MB container out of memory.

    Awaited at the tail of _startup_sequence, which itself runs as a
    background task — the server is already serving while this runs.
    """
    # Delay slightly so the app is fully initialised (routers mounted,
    # DB engine ready) before we self-call.
    await asyncio.sleep(2.0)
    import httpx

    # Use the same port uvicorn is bound to — read from env set by
    # the launch script, default to 8000.
    port = int(os.getenv("PORT", "8000"))
    base = f"http://127.0.0.1:{port}"
    sem = asyncio.Semaphore(_WARMUP_CONCURRENCY)

    async def _hit(client: "httpx.AsyncClient", path: str) -> None:
        async with sem:
            try:
                r = await client.get(f"{base}{path}", timeout=30.0)
                logger.info(
                    f"[WARMUP] {path} → {r.status_code} ({r.elapsed.total_seconds():.2f}s)"
                )
            except Exception as exc:
                logger.warning(f"[WARMUP] {path} failed: {exc}")

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*[_hit(client, p) for p in _WARMUP_PATHS])
    logger.info("[WARMUP] Cache pre-warm complete")


# Gzip responses ≥1 KB so list/detail JSON payloads ship 3-8× smaller
# over the wire. Applied before other middleware so every downstream
# response benefits.
app.add_middleware(GZipMiddleware, minimum_size=1024)


# Cache-Control middleware: attach HTTP caching headers to GET /api/v1/*
# responses. The frontend uses React Query (which already has in-memory
# cache), but without HTTP cache headers the browser still pays full
# payload cost on back/forward nav and hard reloads. We set a short
# max-age (60s) with a long stale-while-revalidate window so pages feel
# instant on navigation while revalidating in the background.
@app.middleware("http")
async def add_cache_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if (
        request.method == "GET"
        and path.startswith("/api/v1/")
        and response.status_code == 200
        # Skip auth-scoped or mutation-adjacent endpoints
        and not path.startswith("/api/v1/auth/")
        and not path.startswith("/api/v1/account/")
        and not path.startswith("/api/v1/watchlist")
        and "cache-control" not in {k.lower() for k in response.headers.keys()}
    ):
        response.headers["Cache-Control"] = (
            "public, max-age=60, stale-while-revalidate=3600"
        )
    return response


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

try:
    from routers.admin_users import router as admin_users_router

    app.include_router(admin_users_router)
    logger.info("Admin users router registered at /api/v1/admin/users")
except Exception as e:
    logger.warning(f"Could not register admin users router: {e}")

try:
    from routers.admin_audit_log import router as admin_audit_log_router

    app.include_router(admin_audit_log_router)
    logger.info("Admin audit-log router registered at /api/v1/admin/audit-log")
except Exception as e:
    logger.warning(f"Could not register admin audit-log router: {e}")

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

try:
    from routers.data_provenance import router as data_provenance_router

    app.include_router(data_provenance_router)
    logger.info("Data provenance router registered at /api/v1/provenance")
except Exception as e:
    logger.warning(f"Could not register data provenance router: {e}")


# Request logging middleware.
# We only log completions (not the "PROCESSING" pre-event), and we
# downgrade fast healthy responses to DEBUG so production logs show just
# errors and slow requests — the signal engineers actually scan for.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.datetime.now()
    method = request.method
    url = str(request.url)

    try:
        response = await call_next(request)
        process_time = (datetime.datetime.now() - start_time).total_seconds()
        response.headers["X-Process-Time"] = f"{process_time:.3f}"
        # Escalate severity for slow or non-2xx responses so scanning logs
        # highlights real problems without drowning them in noise.
        if process_time > 0.5 or response.status_code >= 400:
            logger.warning(
                f"{method} {url} - {response.status_code} - {process_time:.3f}s"
            )
        else:
            logger.debug(
                f"{method} {url} - {response.status_code} - {process_time:.3f}s"
            )
        return response
    except Exception as e:
        process_time = (datetime.datetime.now() - start_time).total_seconds()
        logger.error(f"ERROR {method} {url} - {str(e)} - {process_time:.3f}s")
        raise


# Helper functions for provenance tracking
security = HTTPBearer()


# Cache decorator helper
_all_mem_caches: list = []  # registry for test cleanup


def clear_all_caches():
    """Clear every in-memory endpoint cache.  Called between tests."""
    for c in _all_mem_caches:
        c.clear()
    # Clear both RedisCache instances (main.redis_cache and cache.redis_cache.cache)
    for rc in _redis_cache_instances():
        rc._memory_cache.clear()
        if rc.client is not None:
            try:
                rc.client.flushdb()
            except Exception:
                pass


def _redis_cache_instances():
    """Yield all known RedisCache singletons."""
    if redis_cache is not None:
        yield redis_cache
    try:
        from cache.redis_cache import cache as _router_cache

        if _router_cache is not None and _router_cache is not redis_cache:
            yield _router_cache
    except Exception:
        pass


def cached(key_prefix: str, ttl: int = 3600):
    """Decorator to cache endpoint responses.

    Uses Redis when available, otherwise falls back to a lightweight
    in-memory TTL cache so that repeated calls don't hit the DB /
    filesystem on every request.
    """

    def decorator(func):
        # Module-level in-memory fallback cache (per-endpoint)
        _mem_cache: Dict[str, Dict[str, Any]] = {}
        _all_mem_caches.append(_mem_cache)

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


# Startup logging + DB pool pre-warm live in _startup_sequence (lifespan).


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


@app.api_route("/health/live", methods=["GET", "HEAD"])
async def health_live() -> JSONResponse:
    """Liveness: the process is up and serving. Answers immediately even
    while the startup sequence (reference-data bootstrap) is running."""
    return JSONResponse({"status": "alive"})


@app.api_route("/health/ready", methods=["GET", "HEAD"])
async def health_ready() -> JSONResponse:
    """Readiness: reference data is bootstrapped and endpoints can serve
    real responses. 503 while the background startup sequence runs (or
    if bootstrap failed — check logs for 'Failed to initialize')."""
    if not _app_ready.is_set():
        return JSONResponse({"status": "starting"}, status_code=503)
    return JSONResponse({"status": "ready"})


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
            logger.warning("No countries found in database — run bootstrap seeding")
            return []
        return countries
    except Exception as e:
        logger.error(f"Database error in get_countries: {str(e)}")
        return []


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
                # Scope to latest county fiscal period
                _county_pid = _latest_county_period(db)

                # Total budget allocation (county-only, latest FY)
                alloc_q = (
                    db.query(func.sum(DBBudgetLine.allocated_amount))
                    .join(DBEntity, DBBudgetLine.entity_id == DBEntity.id)
                    .filter(
                        DBEntity.type == EntityType.COUNTY,
                        DBBudgetLine.category != "Total Budget",
                    )
                )
                if _county_pid:
                    alloc_q = alloc_q.filter(DBBudgetLine.period_id == _county_pid)
                total_allocation = float(alloc_q.scalar() or 0)

                # Total actual spending (same scope)
                spent_q = (
                    db.query(func.sum(DBBudgetLine.actual_spent))
                    .join(DBEntity, DBBudgetLine.entity_id == DBEntity.id)
                    .filter(
                        DBEntity.type == EntityType.COUNTY,
                        DBBudgetLine.category != "Total Budget",
                    )
                )
                if _county_pid:
                    spent_q = spent_q.filter(DBBudgetLine.period_id == _county_pid)
                total_spent = float(spent_q.scalar() or 0)

                # Total *national* debt (only sovereign-level loans)
                from models import EntityType as _ET

                _nat = db.query(DBEntity).filter(DBEntity.type == _ET.NATIONAL).first()
                if _nat:
                    # Exclude PENDING_BILLS — see ``_is_debt_loan``.
                    # NULL ``debt_category`` rows must still count as
                    # debt (predicate's contract); see _debt_loans_query
                    # for why a naive ``!=`` would silently drop them.
                    from models import DebtCategory as _DC

                    _debt_category_filter = or_(
                        DBLoan.debt_category.is_(None),
                        DBLoan.debt_category != _DC.PENDING_BILLS,
                    )
                    total_debt_result = (
                        db.query(func.sum(DBLoan.outstanding))
                        .filter(
                            DBLoan.entity_id == _nat.id,
                            _debt_category_filter,
                        )
                        .scalar()
                    )
                    total_debt = float(total_debt_result or 0)
                    if total_debt == 0:
                        total_debt = float(
                            db.query(func.sum(DBLoan.principal))
                            .filter(
                                DBLoan.entity_id == _nat.id,
                                _debt_category_filter,
                            )
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
                    db.query(DBAudit).filter(publishable_audit_criterion()).order_by(DBAudit.created_at.desc()).limit(5).all()
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


# ── County data-honesty helpers ──────────────────────────────────────

# Dataset-id prefixes of KNOWN-FABRICATED audit fixtures. The legacy
# generator (removed) produced 512 template findings ("Ghost workers
# detected - KES …") tagged oag-audit-aq#### and labelled "official".
# Rows carrying these ids must never surface as audit opinions, even if
# they are re-seeded from an old fixture.
_FABRICATED_AUDIT_DATASET_PREFIXES = ("oag-audit-aq",)

# data_quality values that mark a row as modelled/demo rather than real.
_NON_OFFICIAL_QUALITIES = {"modelled", "modeled", "synthetic", "demo", "fixture"}


def _audit_is_display_grade(audit) -> bool:
    """True when an audit row is real ingested OAG data — safe to display
    and to derive a county's audit_status from. Fabricated or modelled
    rows (identified via provenance) are excluded so a transparency site
    never renders a synthetic finding as an audit opinion."""
    provenance = audit.provenance
    if isinstance(provenance, dict):
        # JSONB provenance is dict-shaped for some writers/older rows
        # (the pending-bills loans needed the same normalisation).
        # Iterating a dict yields its string KEYS, which would skip the
        # checks below and fail this honesty gate OPEN.
        provenance = [provenance]
    elif not isinstance(provenance, list):
        provenance = []
    for entry in provenance:
        if not isinstance(entry, dict):
            continue
        dataset_id = str(entry.get("dataset_id") or "")
        if dataset_id.startswith(_FABRICATED_AUDIT_DATASET_PREFIXES):
            return False
        quality = str(entry.get("data_quality") or "").lower()
        if quality in _NON_OFFICIAL_QUALITIES:
            return False
    return True


# Categories used by the CoB BIRR live parse as CLASSIFICATION rows
# (whole-budget economic classification), not additive sectors. They
# must be excluded from sector/total sums — adding Development +
# Recurrent + Total to the sector lines would triple-count the budget.
_CLASSIFICATION_CATEGORIES = {"total", "development", "recurrent"}


def _latest_county_actuals_period_ids(db) -> Optional[List[int]]:
    """Period ids for the newest fiscal period with REAL county execution
    data. Preference order:

    1. Newest period carrying CoB BIRR classification rows (Total /
       Development / Recurrent) — those only exist where the live CoB
       parse landed, i.e. real published implementation-review data.
    2. Newest period with any county spend recorded. (Weaker: modelled
       fixture periods — including forward projections — were seeded
       with estimated spend, so this can't distinguish real from
       modelled on its own.)
    3. Newest period outright.

    The original default — newest period by start_date — landed on the
    FY2025/26 equitable-share projection period, which surfaced
    formula-split sector data and (via the audit period filter) turned
    every county's audit status into "pending"."""
    from sqlalchemy import func as _f

    from models import FiscalPeriod as _FP

    row = (
        db.query(_FP.id)
        .join(DBBudgetLine, DBBudgetLine.period_id == _FP.id)
        .join(DBEntity, DBEntity.id == DBBudgetLine.entity_id)
        .filter(
            DBEntity.type == EntityType.COUNTY,
            _f.lower(DBBudgetLine.category).in_(list(_CLASSIFICATION_CATEGORIES)),
        )
        .order_by(_FP.start_date.desc())
        .first()
    )
    if row:
        return [row[0]]

    row = (
        db.query(_FP.id)
        .join(DBBudgetLine, DBBudgetLine.period_id == _FP.id)
        .join(DBEntity, DBEntity.id == DBBudgetLine.entity_id)
        .filter(
            DBEntity.type == EntityType.COUNTY,
            DBBudgetLine.actual_spent.isnot(None),
            DBBudgetLine.actual_spent > 0,
        )
        .order_by(_FP.start_date.desc())
        .first()
    )
    if row:
        return [row[0]]
    latest = db.query(_FP).order_by(_FP.start_date.desc()).first()
    return [latest.id] if latest else None


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

            from seeding.utils import normalize_fiscal_label as _nlbl

            period_ids = None
            if fiscal_year:
                try:
                    canonical = _nlbl(fiscal_year)
                    period_ids = [
                        fp.id for fp in db.query(_FP).all() if fp.label == canonical
                    ] or None
                except (ValueError, IndexError):
                    pass  # Ignore bad fiscal_year format, return unfiltered
            else:
                # Default to the latest fiscal period WITH COUNTY ACTUALS
                # (not merely the newest period — that picked projection
                # periods with no spend and no audits).
                period_ids = _latest_county_actuals_period_ids(db)

            # ── BATCH LOAD all related data in 5 queries (not 47×6) ──
            entity_ids = [e.id for e in entities]

            # 1. Population: latest per entity
            from sqlalchemy import func as _fn

            _pop_sub = (
                db.query(
                    DBPopulationData.entity_id,
                    _fn.max(DBPopulationData.year).label("max_year"),
                )
                .filter(DBPopulationData.entity_id.in_(entity_ids))
                .group_by(DBPopulationData.entity_id)
                .subquery()
            )
            pop_rows = (
                db.query(DBPopulationData)
                .join(
                    _pop_sub,
                    (DBPopulationData.entity_id == _pop_sub.c.entity_id)
                    & (DBPopulationData.year == _pop_sub.c.max_year),
                )
                .all()
            )
            pop_map = {p.entity_id: p for p in pop_rows}

            # 2. Budget lines (all at once, optionally filtered by period)
            bl_query = db.query(DBBudgetLine).filter(
                DBBudgetLine.entity_id.in_(entity_ids)
            )
            if period_ids:
                bl_query = bl_query.filter(DBBudgetLine.period_id.in_(period_ids))
            all_budget_lines = bl_query.all()
            bl_by_entity: dict = {}
            for bl in all_budget_lines:
                bl_by_entity.setdefault(bl.entity_id, []).append(bl)

            # 3. Loans (all county loans at once)
            all_loans = db.query(DBLoan).filter(DBLoan.entity_id.in_(entity_ids)).all()
            loans_by_entity: dict = {}
            for loan in all_loans:
                loans_by_entity.setdefault(loan.entity_id, []).append(loan)

            # 4. Audits — deliberately NOT filtered by the budget period:
            # an audit opinion is issued for its own FY and users want the
            # most recent one regardless of which budget year is shown.
            # (The old period filter pinned audits to the projections
            # period, which has none, so every county read as "pending".)
            # Fabricated/modelled rows are gated out — display-grade only.
            all_audits = (
                db.query(DBAudit)
                .filter(publishable_audit_criterion())
                .filter(DBAudit.entity_id.in_(entity_ids))
                .order_by(DBAudit.entity_id, DBAudit.created_at.desc())
                .all()
            )
            audits_by_entity: dict = {}
            for a in all_audits:
                if not _audit_is_display_grade(a):
                    continue
                audits_by_entity.setdefault(a.entity_id, []).append(a)

            # 5. GDP data: latest per entity
            from models import GDPData as _GDPData

            _gdp_sub = (
                db.query(
                    _GDPData.entity_id,
                    _fn.max(_GDPData.year).label("max_year"),
                )
                .filter(_GDPData.entity_id.in_(entity_ids))
                .group_by(_GDPData.entity_id)
                .subquery()
            )
            gdp_rows = (
                db.query(_GDPData)
                .join(
                    _gdp_sub,
                    (_GDPData.entity_id == _gdp_sub.c.entity_id)
                    & (_GDPData.year == _gdp_sub.c.max_year),
                )
                .all()
            )
            gdp_map = {g.entity_id: g for g in gdp_rows}

            # ── BUILD RESULTS from pre-loaded data ──
            results = []
            for e in entities:
                pop_data = pop_map.get(e.id)
                budget_lines = bl_by_entity.get(e.id, [])
                loans = loans_by_entity.get(e.id, [])
                audits = audits_by_entity.get(e.id, [])
                gdp_data = gdp_map.get(e.id)

                # Split lines: CoB BIRR classification rows (Total /
                # Development / Recurrent — whole-budget economic
                # classification, REAL parsed data) vs additive sector
                # lines (currently modelled splits). Summing both would
                # triple-count the budget.
                sector_lines = []
                class_by_cat: dict = {}
                for bl in budget_lines:
                    cat_key = (bl.category or "").strip().lower()
                    if cat_key in _CLASSIFICATION_CATEGORIES:
                        # Sub-rows (e.g. Personnel Emoluments under
                        # Recurrent) aren't the aggregate — skip those.
                        if not bl.subcategory:
                            agg = class_by_cat.setdefault(
                                cat_key, {"allocated": 0.0, "spent": 0.0}
                            )
                            agg["allocated"] += float(bl.allocated_amount or 0)
                            agg["spent"] += float(bl.actual_spent or 0)
                        continue
                    sector_lines.append(bl)

                # Headline totals: prefer the CoB "Total" aggregate (real
                # BIRR data) over summing the modelled sector split.
                if class_by_cat.get("total", {}).get("allocated"):
                    total_allocated = class_by_cat["total"]["allocated"]
                    total_spent = class_by_cat["total"]["spent"]
                else:
                    total_allocated = sum(
                        float(b.allocated_amount or 0) for b in sector_lines
                    )
                    total_spent = sum(float(b.actual_spent or 0) for b in sector_lines)

                # Sector breakdown from sector lines only
                sector_breakdown = {}
                development_total = class_by_cat.get("development", {}).get(
                    "allocated", 0.0
                )
                recurrent_total = class_by_cat.get("recurrent", {}).get(
                    "allocated", 0.0
                )
                keyword_dev = 0.0
                keyword_rec = 0.0
                for bl in sector_lines:
                    cat = (bl.category or "Other").strip()
                    amt = float(bl.allocated_amount or 0)
                    spent = float(bl.actual_spent or 0)
                    sector_breakdown.setdefault(cat, {"allocated": 0.0, "spent": 0.0})
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
                        keyword_dev += amt
                    else:
                        keyword_rec += amt

                # Fallback chain when no real CoB classification rows:
                # sector-keyword heuristic, then entity-meta metrics.
                if development_total == 0:
                    development_total = keyword_dev
                    if recurrent_total == 0:
                        recurrent_total = keyword_rec
                if development_total == 0 and total_allocated > 0:
                    meta = e.meta or {}
                    metrics = _resolve_fy_metrics(meta, fiscal_year)
                    dev_from_meta = float(metrics.get("development_budget", 0))
                    if dev_from_meta > 0:
                        development_total = dev_from_meta
                        recurrent_total = float(
                            metrics.get(
                                "recurrent_budget", total_allocated - dev_from_meta
                            )
                        )

                total_debt = sum(
                    float(loan.outstanding or loan.principal or 0)
                    for loan in loans
                    if _is_debt_loan(loan)
                )

                pending_bills = sum(
                    float(bl.allocated_amount or 0)
                    for bl in budget_lines
                    if bl.category and "pending" in bl.category.lower()
                )
                if pending_bills == 0:
                    meta = e.meta or {}
                    metrics = _resolve_fy_metrics(meta, fiscal_year)
                    pending_bills = float(metrics.get("pending_bills", 0))

                latest_audit = audits[0] if audits else None

                audit_issues = []
                for a in audits[:10]:
                    audit_issues.append(
                        {
                            "id": str(a.id),
                            "type": "financial",
                            "severity": a.severity.value if a.severity else "medium",
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
                        (total_spent / total_allocated * 100) if total_spent > 0 else 0
                    )
                    if utilization <= 95:
                        health_score = min(utilization, 95)
                    elif utilization <= 100:
                        health_score = 90
                    else:
                        health_score = max(0, 80 - (utilization - 100))

                meta = e.meta or {}
                metrics = _resolve_fy_metrics(meta, fiscal_year)
                revenue_collection = float(
                    metrics.get("local_revenue") or metrics.get("revenue_2024", 0)
                )
                money_received = float(
                    metrics.get("transfers_received", total_allocated)
                )

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
async def get_county_details(county_id: str, fiscal_year: Optional[str] = None):
    """Get detailed information for a specific county (DB-first, enriched)."""
    if DATABASE_AVAILABLE:
        try:
            with next(get_db()) as db:
                name = _resolve_county_name(county_id, db=db)
                # Unknown id → 404. Previously an unresolvable id skipped
                # the name filter and q.first() served the FIRST county's
                # data (Mombasa) under any garbage id with a 200.
                if not name:
                    raise HTTPException(
                        status_code=404,
                        detail=f"County '{county_id}' not found",
                    )
                e = (
                    db.query(DBEntity)
                    .filter(
                        DBEntity.type == EntityType.COUNTY,
                        DBEntity.canonical_name == f"{name} County",
                    )
                    .first()
                )
                if e:
                    # Resolve fiscal period — same logic as list endpoint
                    from models import FiscalPeriod as _FP

                    from seeding.utils import normalize_fiscal_label as _nlbl

                    period_ids = None
                    if fiscal_year:
                        try:
                            canonical = _nlbl(fiscal_year)
                            period_ids = [
                                fp.id
                                for fp in db.query(_FP).all()
                                if fp.label == canonical
                            ] or None
                        except (ValueError, IndexError):
                            pass
                    else:
                        # Latest fiscal period WITH county actuals — same
                        # honesty rule as the list endpoint (newest-by-
                        # start-date picked spend-less projection periods).
                        period_ids = _latest_county_actuals_period_ids(db)

                    pop_data = (
                        db.query(DBPopulationData)
                        .filter(DBPopulationData.entity_id == e.id)
                        .order_by(DBPopulationData.year.desc())
                        .first()
                    )

                    bl_query = db.query(DBBudgetLine).filter(
                        DBBudgetLine.entity_id == e.id
                    )
                    if period_ids:
                        bl_query = bl_query.filter(
                            DBBudgetLine.period_id.in_(period_ids)
                        )
                    budget_lines = bl_query.all()

                    # Same classification-vs-sector split as the list
                    # endpoint: CoB BIRR Total/Development/Recurrent rows
                    # are whole-budget aggregates (real data), sector
                    # lines are the additive (modelled) split — summing
                    # both triple-counts the budget.
                    sector_lines = []
                    class_by_cat: dict = {}
                    for bl in budget_lines:
                        cat_key = (bl.category or "").strip().lower()
                        if cat_key in _CLASSIFICATION_CATEGORIES:
                            if not bl.subcategory:
                                agg = class_by_cat.setdefault(
                                    cat_key, {"allocated": 0.0, "spent": 0.0}
                                )
                                agg["allocated"] += float(bl.allocated_amount or 0)
                                agg["spent"] += float(bl.actual_spent or 0)
                            continue
                        sector_lines.append(bl)

                    if class_by_cat.get("total", {}).get("allocated"):
                        total_allocated = class_by_cat["total"]["allocated"]
                        total_spent = class_by_cat["total"]["spent"]
                    else:
                        total_allocated = sum(
                            float(b.allocated_amount or 0) for b in sector_lines
                        )
                        total_spent = sum(
                            float(b.actual_spent or 0) for b in sector_lines
                        )

                    sector_breakdown = {}
                    development_total = class_by_cat.get("development", {}).get(
                        "allocated", 0.0
                    )
                    recurrent_total = class_by_cat.get("recurrent", {}).get(
                        "allocated", 0.0
                    )
                    keyword_dev = 0.0
                    keyword_rec = 0.0
                    for bl in sector_lines:
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
                            keyword_dev += amt
                        else:
                            keyword_rec += amt

                    if development_total == 0:
                        development_total = keyword_dev
                        if recurrent_total == 0:
                            recurrent_total = keyword_rec

                    loans = db.query(DBLoan).filter(DBLoan.entity_id == e.id).all()
                    total_debt = sum(
                        float(loan.outstanding or loan.principal or 0)
                        for loan in loans
                        if _is_debt_loan(loan)
                    )

                    pending_bills = sum(
                        float(bl.allocated_amount or 0)
                        for bl in budget_lines
                        if bl.category and "pending" in bl.category.lower()
                    )

                    # Display-grade audits only — this endpoint previously
                    # served the fabricated fixture findings (template
                    # text, dataset oag-audit-aq*) as real OAG data on
                    # county detail pages.
                    audits = [
                        a
                        for a in (
                            db.query(DBAudit)
                            .filter(publishable_audit_criterion())
                            .filter(DBAudit.entity_id == e.id)
                            .order_by(DBAudit.created_at.desc())
                            .all()
                        )
                        if _audit_is_display_grade(a)
                    ]
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
                    metrics = _resolve_fy_metrics(meta, fiscal_year)
                    revenue_collection = float(
                        metrics.get("local_revenue") or metrics.get("revenue_2024", 0)
                    )
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

                    if development_total == 0 and total_allocated > 0:
                        dev_from_meta = float(metrics.get("development_budget", 0))
                        if dev_from_meta > 0:
                            development_total = dev_from_meta
                            recurrent_total = float(
                                metrics.get(
                                    "recurrent_budget", total_allocated - dev_from_meta
                                )
                            )

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
        except HTTPException:
            # Deliberate 404s (unknown county id) must reach the client,
            # not be swallowed into the fallback path below.
            raise
        except Exception as exc:
            logging.error(f"DB county details failed, falling back: {exc}")

    # Fallback: Enhanced API
    try:
        county_name = _resolve_county_name(county_id)
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
async def get_county_comprehensive(
    county_id: str,
    fiscal_year: Optional[str] = None,
):
    """Comprehensive county detail — one-stop aggregation of every data dimension.

    Returns budget breakdown (by sector), audit findings, debt/loans,
    pending bills, stalled projects, economic profile, demographics,
    missing funds cases, and financial health grades — all from DB.

    ``fiscal_year``: optional filter (e.g. "2024/25"). When omitted, falls
    back to the latest period that has actual spending. The frontend
    listing passes the selected FY through so the detail hero's HEALTH
    badge matches the Health column the user just clicked from.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    # Accept any reasonable id form: raw numeric ("4"), zero-padded code
    # ("004"), slug ("tana-river-county"), or name ("Tana River"). The
    # money-flow and counties-list endpoints return different shapes, so
    # this page gets linked with all of them.
    try:
        with next(get_db()) as db:
            entity = _resolve_county_entity(db, county_id)
            if not entity:
                raise HTTPException(status_code=404, detail="County not found")
            county_name = (entity.canonical_name or "").replace(" County", "").strip()
            if not county_name:
                county_name = COUNTY_MAPPING.get(county_id, "")

            meta = entity.meta or {}
            metrics = _resolve_fy_metrics(meta)
            financial_metrics_meta = meta.get("financial_metrics") or {}
            economic_profile = meta.get("economic_profile") or {}

            # --- Population ---
            pop = (
                db.query(DBPopulationData)
                .filter(DBPopulationData.entity_id == entity.id)
                .order_by(DBPopulationData.year.desc())
                .first()
            )

            # --- Budget lines (scoped to requested FY, or latest executed) ---
            requested_period_id: Optional[int] = None
            if fiscal_year:
                try:
                    from seeding.utils import normalize_fiscal_label as _nlbl
                    canonical = _nlbl(fiscal_year)
                    fp_match = (
                        db.query(DBFiscalPeriod)
                        .filter(DBFiscalPeriod.label == canonical)
                        .first()
                    )
                    if fp_match:
                        requested_period_id = fp_match.id
                except (ValueError, IndexError, ImportError):
                    pass  # Bad format — fall through to auto-resolve
            budget_lines = _entity_period_budget_query(
                db, entity.id, period_id=requested_period_id
            ).all()
            total_allocated = sum(float(b.allocated_amount or 0) for b in budget_lines)
            total_spent = sum(float(b.actual_spent or 0) for b in budget_lines)

            # Resolve the fiscal year label so the frontend can display
            # "Budget FY2024/25" (e.g. if we selected the latest executed FY
            # because the current one has no spending yet).
            budget_fy_label: Optional[str] = None
            if budget_lines:
                _fp = (
                    db.query(DBFiscalPeriod)
                    .filter(DBFiscalPeriod.id == budget_lines[0].period_id)
                    .first()
                )
                if _fp:
                    budget_fy_label = _fp.label

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
            # Keep ALL loans in the local list — the per-loan
            # ``debt_breakdown`` and ``pending_bills_from_loans``
            # blocks below both iterate it. Only the total filters out
            # PENDING_BILLS (see ``_is_debt_loan`` for why).
            loans = db.query(DBLoan).filter(DBLoan.entity_id == entity.id).all()
            total_debt = sum(
                float(l.outstanding or l.principal or 0)
                for l in loans
                if _is_debt_loan(l)
            )

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

            # --- Audits --- (display-grade only: fabricated/modelled
            # rows must never render as OAG findings)
            audits = [
                a
                for a in (
                    db.query(DBAudit)
                    .filter(publishable_audit_criterion())
                    .filter(DBAudit.entity_id == entity.id)
                    .order_by(DBAudit.created_at.desc())
                    .all()
                )
                if _audit_is_display_grade(a)
            ]

            audit_findings = []
            by_severity = {"info": 0, "warning": 0, "critical": 0}
            # `0.0` here reads as "the Auditor-General questioned nothing".
            # Track whether any published finding actually carried an amount.
            total_audit_amount = 0.0
            any_audit_amount = False
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
                if amount:
                    any_audit_amount = True
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

            # Financial health score — computed live from the same budget_lines
            # the /counties list endpoint uses, so the listing's Health column
            # and the detail-page HEALTH badge always show the same letter for
            # the same county/FY. Do NOT fall back to the cached
            # `financial_metrics_meta.financial_health_score`; it's stale and
            # desynced from the current fiscal-year filter.
            health_score = 0.0
            if total_allocated > 0:
                utilization = (
                    (total_spent / total_allocated * 100) if total_spent > 0 else 0
                )
                if utilization <= 95:
                    health_score = min(utilization, 95)
                elif utilization <= 100:
                    health_score = 90
                else:
                    health_score = max(0, 80 - (utilization - 100))

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
            # Same publication gate as /accountability/missing-funds: a case
            # that names a county but resolves to no source document is not
            # served here either (AUDIT_FINDINGS F5.3). The stored rows are
            # retained; they are withheld from the response with a reason.
            _raw_missing_cases = meta.get("missing_funds_cases") or []
            if not isinstance(_raw_missing_cases, list):
                _raw_missing_cases = []
            _missing_doc_ids = set()
            for _c in _raw_missing_cases:
                if isinstance(_c, dict) and _c.get("source_document_id") not in (None, ""):
                    try:
                        _missing_doc_ids.add(int(_c["source_document_id"]))
                    except (TypeError, ValueError):
                        continue
            _missing_docs = {}
            if _missing_doc_ids:
                _missing_docs = {
                    d.id: d
                    for d in db.query(DBSourceDocument)
                    .filter(DBSourceDocument.id.in_(_missing_doc_ids))
                    .all()
                }
            missing_funds_cases = []
            missing_funds_withheld = {}
            for _c in _raw_missing_cases:
                if not isinstance(_c, dict):
                    continue
                _fail = missing_funds_provenance_failure(_c, _missing_docs)
                if _fail:
                    missing_funds_withheld[_fail] = (
                        missing_funds_withheld.get(_fail, 0) + 1
                    )
                    continue
                missing_funds_cases.append(_c)

            # The stored ``missing_funds`` metric is a modelled figure with no
            # extraction behind it, and it disagreed with its own case list by
            # 8.2x. Publish a total only when it is the sum of sourced cases.
            missing_funds_total = (
                sum(
                    _parse_kes_amount_str(_c.get("amount")) or 0.0
                    for _c in missing_funds_cases
                )
                if missing_funds_cases
                else None
            )
            if missing_funds_withheld:
                logger.warning(
                    "county %s: withheld %d unsourced missing-funds case(s) (%s)",
                    county_id,
                    sum(missing_funds_withheld.values()),
                    ", ".join(f"{k}={v}" for k, v in sorted(missing_funds_withheld.items())),
                )

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

            # --- Health history (last ~6 completed FYs, oldest → newest) ---
            # Aggregates allocated + spent per fiscal period and applies the same
            # scoring formula used for the current-FY health_score, so sparklines
            # stay consistent with the hero badge. Excludes in-progress periods —
            # plotting a mid-year partial execution would paint a misleading crash.
            from sqlalchemy import func as _sqlfunc2
            from datetime import datetime as _dt
            _now = _dt.utcnow()
            fy_rows = (
                db.query(
                    DBFiscalPeriod.label,
                    DBFiscalPeriod.start_date,
                    _sqlfunc2.coalesce(_sqlfunc2.sum(DBBudgetLine.allocated_amount), 0),
                    _sqlfunc2.coalesce(_sqlfunc2.sum(DBBudgetLine.actual_spent), 0),
                )
                .join(DBBudgetLine, DBBudgetLine.period_id == DBFiscalPeriod.id)
                .filter(
                    DBBudgetLine.entity_id == entity.id,
                    DBBudgetLine.category != "Total Budget",
                    DBFiscalPeriod.end_date < _now,
                )
                .group_by(DBFiscalPeriod.id, DBFiscalPeriod.label, DBFiscalPeriod.start_date)
                .order_by(DBFiscalPeriod.start_date.desc())
                .limit(6)
                .all()
            )

            def _grade_for(score: float) -> str:
                if score >= 85: return "A"
                if score >= 70: return "B+"
                if score >= 55: return "B"
                if score >= 40: return "B-"
                return "C"

            health_history = []
            for label, _sd, alloc, spent in reversed(fy_rows):
                alloc_f = float(alloc or 0)
                spent_f = float(spent or 0)
                if alloc_f <= 0 or spent_f <= 0:
                    # Skip periods with no execution — they'd plot as 0 and
                    # distort the trend. Allocated-only years aren't "graded".
                    continue
                util = spent_f / alloc_f * 100
                if util <= 95:
                    hs = min(util, 95)
                elif util <= 100:
                    hs = 90
                else:
                    hs = max(0.0, 80 - (util - 100))
                health_history.append(
                    {
                        "fy": label,
                        "score": round(hs, 1),
                        "grade": _grade_for(hs),
                    }
                )

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
                    "fiscal_year": budget_fy_label,
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
                # Audit — findings array is always included so downstream
                # tab components can iterate safely. An earlier experiment
                # gated this behind `?include_findings=true` for a ~5KB
                # payload saving; that broke the Audit tab (iterated
                # `audit.findings` directly) so the saving wasn't worth
                # the correctness cost. Kept shipping the full list.
                "audit": {
                    "status": audit_status,
                    "grade": grade,
                    "health_score": round(health_score, 1),
                    "findings_count": len(audits),
                    "total_amount_involved": (
                        total_audit_amount if any_audit_amount else None
                    ),
                    "total_amount_involved_reason": (
                        None if any_audit_amount else "awaiting_sourced_data"
                    ),
                    "by_severity": by_severity,
                    "findings": audit_findings,
                },
                # Health score over time (oldest → newest)
                "health_history": health_history,
                # Missing funds
                "missing_funds": {
                    "total_amount": missing_funds_total,
                    "cases_count": len(missing_funds_cases),
                    "cases": missing_funds_cases,
                    "reason": None if missing_funds_cases else "awaiting_sourced_data",
                    "withheld": {
                        "count": sum(missing_funds_withheld.values()),
                        "by_reason": missing_funds_withheld,
                    },
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
        county_name = _resolve_county_name(county_id)
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
                name = _resolve_county_name(county_id, db=db)
                e = (
                    db.query(DBEntity)
                    .filter(DBEntity.type == EntityType.COUNTY)
                    .filter(DBEntity.canonical_name == f"{name} County")
                    .first()
                )
                if e:
                    # Simple aggregate from budget lines (latest FY); fallback to metrics
                    bl_sum = (
                        _entity_period_budget_query(db, e.id)
                        .with_entities(DBBudgetLine.allocated_amount)
                        .all()
                    )
                    allocated_total = (
                        float(sum((x[0] or 0) for x in bl_sum)) if bl_sum else 0.0
                    )
                    meta = e.meta or {}
                    metrics = _resolve_fy_metrics(meta)
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
        county_name = _resolve_county_name(county_id)
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
                name = _resolve_county_name(county_id, db=db)
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

                # Real debt from Loan table — exclude PENDING_BILLS
                # so the total reflects borrowed money, not unpaid
                # obligations. Pending bills land in this same table
                # via the seeding writer; see ``_is_debt_loan``.
                loans = _debt_loans_query(db, DBLoan.entity_id == e.id).all()
                total_principal = sum(float(l.principal or 0) for l in loans)
                total_outstanding = sum(float(l.outstanding or 0) for l in loans)

                # Pending bills from BudgetLine (latest FY deficit)
                budget_rows = _entity_period_budget_query(db, e.id).all()
                total_allocated = sum(
                    float(b.allocated_amount or 0) for b in budget_rows
                )
                total_spent = sum(float(b.actual_spent or 0) for b in budget_rows)

                # Local revenue from meta
                meta = e.meta or {}
                metrics = _resolve_fy_metrics(meta)
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
            total = db.query(func.count(DBAudit.id)).filter(publishable_audit_criterion()).scalar() or 0

            # By severity
            severity_rows = (
                db.query(DBAudit.severity, func.count(DBAudit.id))
                .filter(publishable_audit_criterion())
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
                .filter(publishable_audit_criterion())
                .filter(DBAudit.severity == Severity.CRITICAL)
                .group_by(DBEntity.canonical_name)
                .order_by(func.count(DBAudit.id).desc())
                .limit(5)
                .all()
            )

            # Recent critical findings (most recent 6)
            recent_critical = (
                db.query(DBAudit, DBEntity.canonical_name)
                .filter(publishable_audit_criterion())
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
                db.query(func.count(func.distinct(DBAudit.entity_id))).filter(publishable_audit_criterion()).scalar() or 0
            )

            # Total amount involved across all findings — prefer the
            # structured `amount` column (populated from OAG parsers).
            # Fall back to regex over `finding_text` only for rows that
            # lack an `amount` value, so we don't lose data but also don't
            # pull the entire text column across the wire when unnecessary.
            amount_from_col = (
                db.query(func.coalesce(func.sum(DBAudit.amount), 0))
                .filter(publishable_audit_criterion())
                .filter(DBAudit.amount.isnot(None))
                .scalar()
                or 0.0
            )
            # Regex fallback only over rows where amount is NULL.
            fallback_amount = 0.0
            for (text_val,) in (
                db.query(DBAudit.finding_text)
                .filter(publishable_audit_criterion())
                .filter(DBAudit.amount.is_(None))
                .all()
            ):
                if text_val:
                    match = re.search(r"KES\s*([\d,]+)", text_val)
                    if match:
                        try:
                            fallback_amount += float(match.group(1).replace(",", ""))
                        except Exception:
                            pass
            total_amount = float(amount_from_col) + fallback_amount

            _withheld_stats = count_withheld_audits(db)
            log_withheld_audits("/audits/statistics", _withheld_stats, total)

            # Latest fiscal year covered by the Audit table (derived, NOT hardcoded)
            latest_period_label = (
                db.query(DBFiscalPeriod.label)
                .join(DBAudit, DBAudit.period_id == DBFiscalPeriod.id)
                .filter(publishable_audit_criterion())
                .order_by(DBFiscalPeriod.start_date.desc())
                .limit(1)
                .scalar()
            )
            # Fall back: look at any period_label carried on findings text
            fiscal_years_covered = sorted(
                {
                    row[0]
                    for row in db.query(DBFiscalPeriod.label)
                    .join(DBAudit, DBAudit.period_id == DBFiscalPeriod.id)
                    .filter(publishable_audit_criterion())
                    .distinct()
                    .all()
                    if row[0]
                },
                reverse=True,
            )

            # Honest data vintage from the contributing source documents — never
            # datetime.now() (audit §2.9). Mirrors /audits/federal.
            from provenance import vintage_iso

            _audit_doc_ids = [
                row[0]
                for row in db.query(DBAudit.source_document_id).filter(publishable_audit_criterion()).distinct().all()
                if row[0]
            ]

            return {
                "total_findings": total,
                "withheld_findings": _withheld_stats,
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
                # NOTE: derived from the latest period actually present in the
                # Audit table. Returns None when the table is empty so the UI
                # can show an honest "no audit data yet" state instead of a
                # stale hardcoded label.
                "fiscal_year": latest_period_label,
                "fiscal_years_covered": fiscal_years_covered,
                "_meta": _response_meta(
                    unit="kes",
                    entity_scope="county",
                    fiscal_period=latest_period_label,
                    covers_through=latest_period_label,
                    cache_ttl_seconds=3600,
                    data_quality="official" if latest_period_label else "unknown",
                    quality_notes=(
                        check_period_nonempty(
                            total,
                            endpoint="/audits/statistics",
                            period_label=latest_period_label,
                        )
                        or None
                    ),
                ),
                "last_updated": vintage_iso(db, _audit_doc_ids),
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error computing audit statistics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/audits/fiscal-years")
@cached(key_prefix="audits:fiscal_years", ttl=86400)
async def get_available_fiscal_years(db: Session = Depends(get_db)):
    """Return a sorted list of fiscal-year strings available in the database.

    Used by the transparency and county money-flow selectors.
    """
    try:
        periods = (
            db.query(DBFiscalPeriod.label)
            .order_by(DBFiscalPeriod.start_date.desc())
            .all()
        )
        years = [p.label for p in periods if p.label]
        if not years:
            # Fallback: derive from fiscal_summaries table
            from models import FiscalSummary

            summaries = (
                db.query(FiscalSummary.fiscal_year)
                .order_by(FiscalSummary.fiscal_year.desc())
                .all()
            )
            years = [s.fiscal_year for s in summaries if s.fiscal_year]
        return {"status": "success", "data": years}
    except Exception as e:
        logger.error(f"Error fetching fiscal years: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _parse_kes_amount_str(value) -> "float | None":
    """Parse 'KES 981.3B' / '1.2T' / '500M' / '5K' into a number, else None.

    Used for the OAG report's authoritative questioned total so the headline
    is the report's own figure rather than a naive sum of finding amounts.
    """
    if not value:
        return None
    cleaned = str(value).upper().replace("KES", "").strip()
    mult = 1.0
    if cleaned.endswith("T"):
        mult, cleaned = 1_000_000_000_000, cleaned[:-1]
    elif cleaned.endswith("B"):
        mult, cleaned = 1_000_000_000, cleaned[:-1]
    elif cleaned.endswith("M"):
        mult, cleaned = 1_000_000, cleaned[:-1]
    elif cleaned.endswith("K"):
        mult, cleaned = 1_000, cleaned[:-1]
    try:
        return float(cleaned.replace(",", "").strip()) * mult
    except (ValueError, TypeError):
        return None


# The Blue Book covers ministries, state departments, commissions and
# independent offices (Article 229). The federal panel must show all of
# them; "Top Ministries" below stays MINISTRY-only by design.
FEDERAL_AUDIT_ENTITY_TYPES = [
    EntityType.MINISTRY,
    EntityType.NATIONAL,
    EntityType.COMMISSION,
    EntityType.AGENCY,
]


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
                .filter(publishable_audit_criterion())
                .join(DBEntity, DBAudit.entity_id == DBEntity.id)
                .filter(DBEntity.type.in_(FEDERAL_AUDIT_ENTITY_TYPES))
                .order_by(DBAudit.severity.desc(), DBAudit.created_at.desc())
                .all()
            )

            from provenance import vintage_iso

            findings = []
            total_amount = 0.0
            # "no publishable finding carries an amount" is not "the amount is
            # zero". Track whether anything was actually parsed so the response
            # can say null instead of 0.0 (AUDIT_FINDINGS P1).
            any_amount_parsed = False
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

                prov = {}
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

                # Extraction-backed rows (Stage 2) carry the figure in the
                # `amount` column — set only when the paragraph cites exactly
                # one Kshs figure. Prefer it over the legacy provenance
                # string; never invent one when both are absent.
                if audit.amount is not None:
                    amount_val = float(audit.amount)
                    if not amount_str:
                        amount_str = f"KES {amount_val:,.0f}"

                if amount_str and amount_val:
                    any_amount_parsed = True
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
                        # Provenance a reader can follow: the page of the
                        # source PDF this finding was extracted from.
                        "title": prov.get("title") or None,
                        "page_ref": audit.page_ref,
                        "source_url": prov.get("source_url") or None,
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

            # Load the audit opinion summary + report metadata from the JSON.
            opinion_summary = {}
            report_meta = {}
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
                    report_meta = nat_data.get("metadata", {})
            except Exception:
                logging.exception(
                    "could not read %s; its figures are withheld", nat_path
                )
                opinion_summary, report_meta = {}, {}

            # Provenance-or-nothing applies to a file exactly as it does to a
            # row. This file holds the same 24 amounts as the quarantined
            # audits rows (sum KES 3,313,000,000,000, 22 of 24 identical) and
            # cites only "https://www.oagkenya.go.ke" — a homepage, not a
            # document. Gating the database while serving this would leave the
            # same fabricated dataset reachable through its second copy.
            _file_failure = file_source_provenance_failure(report_meta)
            if _file_failure:
                logger.warning(
                    "/audits/federal: withholding every figure from "
                    "oag_national_audit_data.json — %s",
                    _file_failure,
                )
                opinion_summary = {}
                report_meta = {}

            _withheld_federal = count_withheld_audits(
                db, entity_types=FEDERAL_AUDIT_ENTITY_TYPES
            )
            log_withheld_audits("/audits/federal", _withheld_federal, len(findings))

            # Ministries with most findings
            top_ministries = (
                db.query(
                    DBEntity.canonical_name,
                    func.count(DBAudit.id).label("count"),
                )
                .join(DBEntity, DBAudit.entity_id == DBEntity.id)
                .filter(publishable_audit_criterion())
                .filter(DBEntity.type == EntityType.MINISTRY)
                .group_by(DBEntity.canonical_name)
                .order_by(func.count(DBAudit.id).desc())
                .limit(10)
                .all()
            )

            # ── Derive report metadata from the database (NOT hardcoded) ──
            # Latest fiscal period actually present in the national-audit data.
            latest_period_label = (
                db.query(DBFiscalPeriod.label)
                .join(DBAudit, DBAudit.period_id == DBFiscalPeriod.id)
                .join(DBEntity, DBAudit.entity_id == DBEntity.id)
                .filter(publishable_audit_criterion())
                .filter(
                    DBEntity.type.in_(FEDERAL_AUDIT_ENTITY_TYPES)
                )
                .order_by(DBFiscalPeriod.start_date.desc())
                .limit(1)
                .scalar()
            )
            fiscal_years_covered = sorted(
                {
                    row[0]
                    for row in (
                        db.query(DBFiscalPeriod.label)
                        .join(DBAudit, DBAudit.period_id == DBFiscalPeriod.id)
                        .join(DBEntity, DBAudit.entity_id == DBEntity.id)
                        .filter(publishable_audit_criterion())
                        .filter(
                            DBEntity.type.in_(
                                FEDERAL_AUDIT_ENTITY_TYPES
                            )
                        )
                        .distinct()
                        .all()
                    )
                    if row[0]
                },
                reverse=True,
            )

            # Derive report title + publication date from the most recent
            # SourceDocument attached to national/ministry audits (if any).
            latest_source = None
            if DBSourceDocument is not None:
                latest_source = (
                    db.query(DBSourceDocument)
                    .join(DBAudit, DBAudit.source_document_id == DBSourceDocument.id)
                    .join(DBEntity, DBAudit.entity_id == DBEntity.id)
                    .filter(publishable_audit_criterion())
                    .filter(
                        DBEntity.type.in_(
                            FEDERAL_AUDIT_ENTITY_TYPES
                        )
                    )
                    .order_by(DBSourceDocument.fetch_date.desc())
                    .first()
                )

            # The OAG report's own metadata (from the source JSON) is the
            # authoritative fiscal year + title + date for the federal report
            # — NOT the global FISCAL_LABEL the audits happen to be attached
            # to in the DB (audit §3.8). Fall back to DB-derived values.
            report_fy = report_meta.get("fiscal_year") or latest_period_label
            # No literal fallback: naming a report when nothing resolves to
            # one asserts a document exists that a reader cannot reach.
            derived_report_title = (
                report_meta.get("report_title")
                or (latest_source.title if latest_source and latest_source.title else None)
                or opinion_summary.get("report_title")
                or None
            )
            derived_report_date = report_meta.get("report_date") or (
                latest_source.fetch_date.date().isoformat()
                if latest_source and latest_source.fetch_date
                else None
            )
            derived_fiscal_years_covered = (
                [report_fy] if report_meta.get("fiscal_year") else fiscal_years_covered
            )
            # The sitting Auditor-General is a public officeholder, not a
            # computed figure. Prefer the publisher name from the latest
            # source document so the value follows the data; fall back to
            # the office name (never a specific person's name) when no
            # source document is available.
            derived_auditor_general = (
                latest_source.publisher
                if latest_source and latest_source.publisher
                else "Office of the Auditor General of Kenya"
            )
            # Severity distribution must describe the findings this response
            # actually publishes. It previously preferred the JSON's own counts,
            # which summed to 25 beside a total_findings of 1 — a histogram
            # describing rows the same response said were withheld.
            by_severity = severity_counts

            return {
                "report_title": derived_report_title,
                "auditor_general": derived_auditor_general,
                "fiscal_year": report_fy,
                "fiscal_years_covered": derived_fiscal_years_covered,
                "report_date": derived_report_date,
                # "Qualified" is an audit opinion attributed to the
                # Auditor-General. Defaulting it made the page assert one even
                # when the file was unreadable.
                "opinion_type": opinion_summary.get("opinion_type") or None,
                "total_findings": len(findings),
                # Headline "Amount Questioned" = the OAG report's own
                # authoritative questioned total, NOT a naive sum of every
                # finding's amount (which conflated debt-service stock, asset
                # valuations etc. and produced the misleading ~3.3T).
                "total_amount_questioned": _parse_kes_amount_str(
                    opinion_summary.get("total_amount_questioned", "")
                ),
                # The label is a second copy of the same figure. Nulling only
                # the number would leave "KES 981.3B" rendering from here —
                # the frontend falls back to it (AuditReportsSection:205-207).
                "total_amount_questioned_label": (
                    opinion_summary.get("total_amount_questioned") or None
                ),
                "total_amount_questioned_reason": _file_failure or None,
                # Transparency only: the raw sum across all finding amounts.
                # NOT the questioned headline (see above).
                "total_amount_in_findings": (
                    total_amount if any_amount_parsed else None
                ),
                "total_amount_in_findings_reason": (
                    None
                    if any_amount_parsed
                    else (
                        "awaiting_sourced_data"
                        if _withheld_federal
                        else "no_amounts_recorded"
                    )
                ),
                # Findings excluded because their source document has no URL a
                # reader could open. Retained in the database, not served here.
                "withheld_findings": _withheld_federal,
                "by_severity": by_severity,
                # When the gate leaves nothing to publish, say why and when
                # the next OAG publication is expected — both machine-readable
                # so the frontend renders a real empty state instead of a
                # blank panel (or a hand-written schedule that drifts). The
                # window comes from the Layer-1 source registry.
                "findings_reason": (
                    None
                    if findings
                    else (
                        "awaiting_sourced_data"
                        if _withheld_federal
                        else "no_findings_recorded"
                    )
                ),
                "next_expected": (
                    None
                    if findings
                    else next_expected_window(
                        "oag_national_audits",
                        datetime.datetime.now(datetime.timezone.utc).date(),
                    )
                ),
                # Prose, but it quotes the quarantined figures: "Unexplained
                # Consolidated Fund balance differences of KES 156.8 billion".
                # Dropping the numeric fields alone leaves the numbers on the
                # page.
                "basis_for_qualification": opinion_summary.get(
                    "basis_for_qualification"
                )
                or [],
                "emphasis_of_matter": opinion_summary.get("emphasis_of_matter") or [],
                "key_statistics": opinion_summary.get("key_statistics") or {},
                "ministries_with_adverse_findings": opinion_summary.get(
                    "ministries_with_adverse_findings"
                ),
                "ministries_with_clean_findings": opinion_summary.get(
                    "ministries_with_clean_findings"
                ),
                # Why the block above is empty, when it is.
                "opinion_summary_reason": _file_failure or None,
                "findings": findings,
                "top_ministries": [
                    {"ministry": name, "finding_count": count}
                    for name, count in top_ministries
                ],
                "_meta": _response_meta(
                    unit="kes",
                    entity_scope="national",
                    fiscal_period=report_fy,
                    covers_through=report_fy,
                    cache_ttl_seconds=3600,
                    data_quality="official" if report_fy else "unknown",
                    quality_notes=(
                        check_period_nonempty(
                            len(findings),
                            endpoint="/audits/federal",
                            period_label=report_fy,
                        )
                        or None
                    ),
                ),
                "last_updated": vintage_iso(
                    db, [a.source_document_id for a, _ in federal_audits]
                ),
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
    county_name = _resolve_county_name(county_id)
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
                        .filter(publishable_audit_criterion())
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
        county_name = _resolve_county_name(county_id)
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
        county_name = _resolve_county_name(county_id)
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

            query = db.query(DBAudit).filter(publishable_audit_criterion())
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
        .filter(publishable_audit_criterion())
        .filter(DBAudit.entity_id == entity.id)
        .all()
    )
    # Findings held back for this county because their source document has no
    # URL a reader could open. Counted so the omission is visible in the
    # response rather than inferred from a suspiciously clean scorecard.
    withheld_findings = count_withheld_audits(db, entity_id=entity.id)

    # --- audit_opinion_history ---
    opinion_by_year: Dict[int, str] = {}
    for a in audits:
        if a.audit_year and a.audit_opinion:
            opinion_by_year[a.audit_year] = a.audit_opinion
    audit_opinion_history = sorted(
        [{"year": y, "opinion": o} for y, o in opinion_by_year.items()],
        key=lambda x: x["year"],
    )

    # --- audit_severity_history (for sparklines) ---
    # Separate from opinion_history: tracks findings severity per year as a
    # 0-100 "audit health" proxy. Used only for visual trend — does NOT feed
    # the accountability scoring rubric (opinions there must stay OAG-sourced).
    # Year resolves from audit_year, else the linked fiscal period's start year.
    period_year_cache: Dict[int, Optional[int]] = {}
    findings_by_year: Dict[int, Dict[str, int]] = {}
    for a in audits:
        year = a.audit_year
        if not year and a.period_id:
            if a.period_id not in period_year_cache:
                fp = (
                    db.query(DBFiscalPeriod)
                    .filter(DBFiscalPeriod.id == a.period_id)
                    .first()
                )
                period_year_cache[a.period_id] = fp.start_date.year if fp else None
            year = period_year_cache[a.period_id]
        if not year:
            continue
        bucket = findings_by_year.setdefault(
            year, {"info": 0, "warning": 0, "critical": 0}
        )
        sev = a.severity.value if a.severity else "info"
        bucket[sev] = bucket.get(sev, 0) + 1

    audit_severity_history = []
    for year in sorted(findings_by_year.keys()):
        b = findings_by_year[year]
        # Score: start at 100, -5 per warning, -20 per critical. Floor at 0.
        score = max(0.0, 100.0 - (b.get("warning", 0) * 5 + b.get("critical", 0) * 20))
        audit_severity_history.append(
            {
                "year": year,
                "score": round(score, 1),
                "info": b.get("info", 0),
                "warning": b.get("warning", 0),
                "critical": b.get("critical", 0),
            }
        )

    # --- total_flagged_amount ---
    # `0.0` reads as "the OAG flagged nothing", which is itself a finding. When
    # no publishable audit carries an amount we do not know the figure, so the
    # answer is null plus a reason (AUDIT_FINDINGS P1).
    _amounts = [float(a.amount) for a in audits if a.amount is not None]
    total_flagged_amount = float(sum(_amounts)) if _amounts else None
    total_flagged_amount_reason = (
        None
        if _amounts
        else ("awaiting_sourced_data" if withheld_findings else "no_findings_recorded")
    )

    # --- recurring_findings_count ---
    qt_years: Dict[str, set] = {}
    for a in audits:
        if a.query_type and a.audit_year:
            qt_years.setdefault(a.query_type, set()).add(a.audit_year)
    recurring_findings_count = sum(1 for years in qt_years.values() if len(years) >= 2)

    # --- unresolved_findings_count ---
    # Any status that is NOT a terminal resolution counts as unresolved.
    # This includes intermediate states ("Under Review", "Escalated")
    # that the previous implementation missed — making counties with
    # many pending investigations appear "accountable" when they aren't.
    resolved_statuses = {"resolved", "closed", "dismissed", "settled"}
    unresolved_findings_count = sum(
        1
        for a in audits
        if not a.status or a.status.strip().lower() not in resolved_statuses
    )

    # --- severity + amount context (used for grade) ---
    total_findings = len(audits)
    critical_findings = sum(
        1 for a in audits if a.severity and a.severity.value == "critical"
    )
    warning_findings = sum(
        1 for a in audits if a.severity and a.severity.value == "warning"
    )

    # --- absorption_rate from budget data (latest FY) ---
    budget_lines = _entity_period_budget_query(db, entity.id).all()
    total_allocated = sum(float(b.allocated_amount or 0) for b in budget_lines)
    total_spent = sum(float(b.actual_spent or 0) for b in budget_lines)
    absorption_rate = (
        round(total_spent / total_allocated, 4) if total_allocated > 0 else None
    )

    # Flagged amount as % of current-FY budget (signal of audit severity).
    # None when either side is unknown — never a 0% that reads as "clean".
    flagged_pct_of_budget = (
        (total_flagged_amount / total_allocated * 100.0)
        if (total_flagged_amount is not None and total_allocated > 0)
        else None
    )

    # --- accountability_score (0-100 point system) ---
    #
    # Starts at 100 and subtracts points for each concern. The grade is
    # then derived from the final score. A point system is clearer than
    # cascading letter drops because (a) penalties of different severity
    # map to different point costs, (b) the UI can show the exact math.
    score = 100.0
    grade_factors: List[Dict[str, Any]] = []

    def _penalise(points: float, impact: str, label: str, detail: str) -> None:
        nonlocal score
        score -= points
        grade_factors.append(
            {
                "impact": impact,
                "label": label,
                "detail": detail,
                "points": -round(points, 1),
            }
        )

    # --- Opinion-based penalties (only fire if we have opinions) ---
    if audit_opinion_history:
        adverse_years = sorted(
            e["year"]
            for e in audit_opinion_history
            if e["opinion"].lower() in ("adverse", "disclaimer")
        )
        if adverse_years:
            _penalise(
                40,
                "major",
                f"Adverse / disclaimer opinion ({adverse_years[0]})",
                "OAG rejected the financial statements",
            )

        latest_opinion = audit_opinion_history[-1]["opinion"].lower()
        if latest_opinion == "qualified":
            _penalise(
                15,
                "major",
                "Qualified opinion (latest FY)",
                "OAG flagged material concerns",
            )

    # --- Finding-volume penalties ---
    if total_findings > 20:
        _penalise(15, "major", f"{total_findings} audit findings (>20)", "High volume")
    elif total_findings > 10:
        _penalise(8, "moderate", f"{total_findings} audit findings (>10)", "Elevated volume")
    elif total_findings > 5:
        _penalise(4, "minor", f"{total_findings} audit findings", "Some findings present")

    # Critical findings = any is serious (cap at -15)
    if critical_findings > 0:
        pts = min(critical_findings * 5, 15)
        _penalise(
            pts,
            "major" if critical_findings >= 3 else "moderate",
            f"{critical_findings} critical finding{'s' if critical_findings != 1 else ''}",
            "Serious irregularity flagged",
        )

    # Recurring query types (same issue across multiple years)
    if recurring_findings_count >= 5:
        _penalise(
            15,
            "major",
            f"{recurring_findings_count} recurring query types",
            "Systemic, year-over-year issues",
        )
    elif recurring_findings_count >= 3:
        _penalise(
            8,
            "moderate",
            f"{recurring_findings_count} recurring query types",
            "Repeated across fiscal years",
        )

    # Unresolved backlog (includes "Under Review", "Escalated", etc.)
    if unresolved_findings_count > 15:
        _penalise(
            20,
            "major",
            f"{unresolved_findings_count} unresolved findings",
            "Large backlog of open issues",
        )
    elif unresolved_findings_count > 5:
        _penalise(
            10,
            "moderate",
            f"{unresolved_findings_count} unresolved findings",
            "Pending / under-review items",
        )

    # Flagged amount material to budget
    if flagged_pct_of_budget is not None and flagged_pct_of_budget > 10:
        _penalise(
            10,
            "moderate",
            f"{flagged_pct_of_budget:.1f}% of budget flagged",
            ">10% of current-FY allocation",
        )
    elif flagged_pct_of_budget is not None and flagged_pct_of_budget > 5:
        _penalise(
            5,
            "minor",
            f"{flagged_pct_of_budget:.1f}% of budget flagged",
            ">5% of current-FY allocation",
        )

    # Low absorption = wasted fiscal capacity
    if absorption_rate is not None and absorption_rate < 0.5:
        _penalise(
            10,
            "moderate",
            f"{absorption_rate * 100:.0f}% budget absorption",
            "Under half of budget was spent",
        )

    # Positive factor — acknowledge when we penalised nothing
    if not grade_factors:
        grade_factors.append(
            {
                "impact": "positive",
                "label": "No penalty triggers",
                "detail": (
                    f"{total_findings} finding"
                    f"{'s' if total_findings != 1 else ''}, "
                    f"{unresolved_findings_count} unresolved"
                ),
                "points": 0,
            }
        )

    score = max(0.0, min(100.0, score))
    # Grade thresholds matched to familiar academic scale
    if score >= 85:
        grade = "A"
    elif score >= 70:
        grade = "B"
    elif score >= 55:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    # The score starts at 100 and subtracts penalties, so a county whose every
    # finding was withheld triggers no penalty and lands on 100/"A". That is
    # absence rendered as a clean bill of health — the exact defect the
    # publication gate exists to prevent, arriving through the back door.
    # With no publishable finding to reason from, there is no grade to give.
    # The score starts at 100 and subtracts penalties, so a county with no
    # findings triggers nothing and lands on 100/"A" — absence rendered as a
    # clean bill of health, which is more misleading than a wrong number
    # because a citizen reads it as their county passing an audit.
    #
    # 46 of 47 counties have zero audit rows (only Homa Bay has one), so this
    # is the normal case, not an edge case. There is no grade to give.
    evidence_basis = "publishable_findings"
    accountability_reason = None
    if total_findings == 0:
        score = None
        grade = None
        if withheld_findings:
            evidence_basis = "no_publishable_findings"
            accountability_reason = "awaiting_sourced_data"
            _detail = (
                f"{withheld_findings} finding"
                f"{'s' if withheld_findings != 1 else ''} withheld: the source "
                "document has no URL a reader could open"
            )
        else:
            # Distinguish "audited and clean" from "never audited here". This
            # dataset holds no finding for this county either way, so it can
            # support neither claim.
            evidence_basis = "no_findings_recorded"
            accountability_reason = "not_yet_audited_in_this_dataset"
            _detail = (
                "No Auditor-General finding for this county has been ingested "
                "yet. This is not a finding that the county is clean."
            )
        grade_factors = [
            {
                "impact": "unknown",
                "label": "Not enough sourced evidence to grade",
                "detail": _detail,
                "points": 0,
            }
        ]

    # --- peer_comparison ---
    region = COUNTY_REGIONS.get(county_id, "Unknown")
    region_county_ids = [
        cid for cid, r in COUNTY_REGIONS.items() if r == region and cid != county_id
    ]

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

    # ─── Peer comparison — batch-loaded to avoid N+1 ────────────────
    # Previously this section issued ~141 queries per request (one
    # DBEntity.first() + DBAudit.all() per region-peer + one DBEntity +
    # DBPopulationData + DBAudit per county in COUNTY_MAPPING). That
    # pushed cold-cache latency to ~43 s on a 47-county dataset.
    #
    # We now do the whole peer roll-up in three bounded queries:
    #   1. All county entities (1 row per county, ~47).
    #   2. All audits for peers (DBAudit.entity_id IN (...)).
    #   3. Latest DBPopulationData per entity (DISTINCT ON / MAX year).
    # Peer stats are then computed in Python, reusing the same logic.
    all_peer_entities = (
        db.query(DBEntity).filter(DBEntity.type == EntityType.COUNTY).all()
    )
    # Map canonical_name ("Nairobi County") → entity for the lookup below.
    peers_by_name: Dict[str, Any] = {
        (e.canonical_name or ""): e for e in all_peer_entities
    }
    peer_entity_ids = [e.id for e in all_peer_entities if e.id != entity.id]

    # Pull all audits for every peer in a single IN(...) query, then
    # group by entity_id in Python. For 47 counties × ~20 audits this
    # is <1000 rows.
    from collections import defaultdict
    from sqlalchemy import func as _sqlfunc3

    peer_audits_by_entity: Dict[int, List[Any]] = defaultdict(list)
    if peer_entity_ids:
        for pa in (
            db.query(DBAudit).filter(publishable_audit_criterion()).filter(DBAudit.entity_id.in_(peer_entity_ids)).all()
        ):
            peer_audits_by_entity[pa.entity_id].append(pa)

    # Latest population per entity via a correlated subquery (one round-trip).
    # (entity_id, MAX(year)) → join back to get the row; but a straight
    # "select all, keep max per entity in Python" is simpler and bounded.
    peer_pop_by_entity: Dict[int, int] = {}
    if peer_entity_ids:
        pop_rows = (
            db.query(
                DBPopulationData.entity_id,
                DBPopulationData.total_population,
                DBPopulationData.year,
            )
            .filter(DBPopulationData.entity_id.in_(peer_entity_ids))
            .all()
        )
        # Keep the max-year row per entity (total_population snapshot).
        latest_year_by_entity: Dict[int, int] = {}
        for eid, total_pop, yr in pop_rows:
            cur = latest_year_by_entity.get(eid, -1)
            if yr > cur:
                latest_year_by_entity[eid] = yr
                peer_pop_by_entity[eid] = int(total_pop or 0)

    def _bracket_for(pop: int) -> str:
        if pop < 500_000:
            return "<500k"
        if pop < 1_000_000:
            return "500k-1M"
        if pop < 2_000_000:
            return "1M-2M"
        return ">2M"

    # Region peers: those in the same region as this county.
    region_flagged_amounts: List[float] = []
    region_grades: List[str] = []
    bracket_flagged_amounts: List[float] = []

    for peer_cid in region_county_ids:
        peer_name = COUNTY_MAPPING.get(peer_cid)
        if not peer_name:
            continue
        peer_entity = peers_by_name.get(f"{peer_name} County")
        if not peer_entity:
            continue
        peer_audits = peer_audits_by_entity.get(peer_entity.id, [])
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

    # Population-bracket peers: iterate every county and keep same-bracket ones.
    for cid, cname in COUNTY_MAPPING.items():
        if cid == county_id:
            continue
        ce = peers_by_name.get(f"{cname} County")
        if not ce:
            continue
        cpop = peer_pop_by_entity.get(ce.id, 0)
        if _bracket_for(cpop) == pop_bracket:
            ca = peer_audits_by_entity.get(ce.id, [])
            _peer_amounts = [float(x.amount) for x in ca if x.amount is not None]
            if _peer_amounts:  # a peer with no recorded amount is unknown, not 0
                bracket_flagged_amounts.append(float(sum(_peer_amounts)))

    region_avg_flagged = (
        round(sum(region_flagged_amounts) / len(region_flagged_amounts), 2)
        if region_flagged_amounts
        else None  # no peer data is not "peers flagged nothing"
    )
    region_avg_grade = (
        _num_to_grade(sum(_grade_to_num(g) for g in region_grades) / len(region_grades))
        if region_grades
        else None
    )
    population_bracket_avg = (
        round(sum(bracket_flagged_amounts) / len(bracket_flagged_amounts), 2)
        if bracket_flagged_amounts
        else None  # no peer data is not "peers flagged nothing"
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
        "audit_severity_history": audit_severity_history,
        "total_flagged_amount": total_flagged_amount,
        "total_flagged_amount_reason": total_flagged_amount_reason,
        "total_findings": total_findings,
        "critical_findings": critical_findings,
        "warning_findings": warning_findings,
        "recurring_findings_count": recurring_findings_count,
        "unresolved_findings_count": unresolved_findings_count,
        "absorption_rate": absorption_rate,
        "flagged_pct_of_budget": (
            round(flagged_pct_of_budget, 2) if flagged_pct_of_budget is not None else None
        ),
        "accountability_grade": grade,
        "accountability_score": round(score, 1) if score is not None else None,
        "evidence_basis": evidence_basis,
        "accountability_reason": accountability_reason,
        "withheld": {
            "count": withheld_findings,
            "reason": "source_document_has_no_url" if withheld_findings else None,
        },
        "grade_factors": grade_factors,
        "peer_comparison": peer_comparison,
    }


@app.get("/api/v1/counties/{county_id}/accountability")
@cached(key_prefix="county:accountability", ttl=3600)
async def get_county_accountability(county_id: str):
    """County accountability scorecard with opinion history, grade, and peer comparison."""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    county_name = _resolve_county_name(county_id)
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

    county_name = _resolve_county_name(county_id)
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
            budget_lines = _entity_period_budget_query(db, entity.id).all()
            total_allocated = sum(float(b.allocated_amount or 0) for b in budget_lines)
            total_spent = sum(float(b.actual_spent or 0) for b in budget_lines)
            audits = db.query(DBAudit).filter(publishable_audit_criterion()).filter(DBAudit.entity_id == entity.id).all()

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


@app.get("/api/v1/accountability/missing-funds")
@cached(key_prefix="accountability:missing-funds", ttl=600)
async def get_national_missing_funds():
    """National roll-up of missing-funds cases across all counties.

    A case is served only if it resolves to a *(source document, page)*
    pair whose document has a URL a reader can open. A case that names a
    county but cannot be traced to a published report is withheld — it is
    counted and reported under ``withheld``, never silently dropped, and
    never rendered as a zero.

    When nothing qualifies, ``total_amount`` is ``None`` (not ``0``) and
    ``reason`` says why, so the page can say "not yet published" instead of
    showing an unaccounted-for total of zero.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    def _parse_amount(raw: Any) -> float:
        if isinstance(raw, (int, float)):
            return float(raw)
        if not isinstance(raw, str):
            return 0.0
        s = raw.upper().replace("KES", "").replace(",", "").strip()
        mult = 1.0
        if s.endswith("B"):
            mult = 1e9
            s = s[:-1]
        elif s.endswith("M"):
            mult = 1e6
            s = s[:-1]
        elif s.endswith("K"):
            mult = 1e3
            s = s[:-1]
        try:
            return float(s) * mult
        except ValueError:
            return 0.0

    published: List[Dict[str, Any]] = []
    withheld_by_reason: Dict[str, int] = {}
    county_totals: Dict[str, Dict[str, Any]] = {}
    status_totals: Dict[str, float] = {}

    with next(get_db()) as db:
        counties = (
            db.query(DBEntity).filter(DBEntity.type == EntityType.COUNTY).all()
        )

        # Resolve every referenced document once, so the gate checks the real
        # row rather than trusting an id that may point at nothing.
        referenced_ids = set()
        for county in counties:
            for case in (county.meta or {}).get("missing_funds_cases") or []:
                if isinstance(case, dict) and case.get("source_document_id") not in (None, ""):
                    try:
                        referenced_ids.add(int(case["source_document_id"]))
                    except (TypeError, ValueError):
                        continue
        docs: Dict[int, Any] = {}
        if referenced_ids:
            docs = {
                d.id: d
                for d in db.query(DBSourceDocument)
                .filter(DBSourceDocument.id.in_(referenced_ids))
                .all()
            }

        for county in counties:
            meta = county.meta or {}
            cases = meta.get("missing_funds_cases") or []
            if not isinstance(cases, list):
                continue
            county_name = (county.canonical_name or "").replace(" County", "").strip()
            county_amount = 0.0
            county_published = 0

            for case in cases:
                if not isinstance(case, dict):
                    withheld_by_reason["malformed_case"] = (
                        withheld_by_reason.get("malformed_case", 0) + 1
                    )
                    continue

                failure = missing_funds_provenance_failure(case, docs)
                if failure is not None:
                    withheld_by_reason[failure] = withheld_by_reason.get(failure, 0) + 1
                    continue

                doc = docs[int(case["source_document_id"])]
                amount = _parse_amount(case.get("amount"))
                status = (case.get("status") or "unknown").lower()
                published.append(
                    {
                        "case_id": case.get("case_id"),
                        "county": case.get("county") or county_name,
                        "county_id": meta.get("county_code"),
                        "amount": amount,
                        "amount_label": case.get("amount"),
                        "period": case.get("period"),
                        "status": status,
                        "description": case.get("description", ""),
                        "source": {
                            "document_id": doc.id,
                            "title": doc.title,
                            "publisher": doc.publisher,
                            "url": doc.url,
                            "page": case.get("page_ref") or case.get("page_number"),
                        },
                    }
                )
                county_amount += amount
                county_published += 1
                status_totals[status] = status_totals.get(status, 0.0) + amount

            if county_published:
                county_totals[county_name] = {
                    "county": county_name,
                    "cases": county_published,
                    "amount": county_amount,
                }

    withheld_total = sum(withheld_by_reason.values())
    if withheld_total:
        # Fail loud: an omission this large must be visible in the log, not
        # inferred from a page that renders nothing.
        logger.warning(
            "missing-funds: withheld %d unsourced case(s) from the public "
            "response (%s); %d published",
            withheld_total,
            ", ".join(f"{k}={v}" for k, v in sorted(withheld_by_reason.items())),
            len(published),
        )

    published.sort(key=lambda c: c["amount"], reverse=True)
    top_counties = sorted(
        county_totals.values(), key=lambda c: c["amount"], reverse=True
    )[:10]

    return {
        "total_amount": (sum(c["amount"] for c in published) if published else None),
        "total_cases": len(published),
        "affected_counties": len(county_totals),
        "by_status": status_totals,
        "top_counties": top_counties,
        "cases": published,
        "reason": None if published else "awaiting_sourced_data",
        "withheld": {"count": withheld_total, "by_reason": withheld_by_reason},
    }


# Canonical sector buckets — keys are lowercase substrings tested against
# raw budget-line categories, so naming variations across counties collapse
# into a consistent set of 7 sectors for the national view.
_SECTOR_BUCKETS: List[Tuple[str, str]] = [
    ("health", "Health"),
    ("education", "Education"),
    ("road", "Roads & Infrastructure"),
    ("infrastructure", "Roads & Infrastructure"),
    ("water", "Water & Sanitation"),
    ("sanitation", "Water & Sanitation"),
    ("agricultur", "Agriculture"),
    ("environment", "Environment"),
    ("trade", "Trade & Industry"),
    ("industry", "Trade & Industry"),
    ("social", "Social Services"),
    ("admin", "Administration"),
    ("governance", "Administration"),
]


def _sector_bucket(raw: str) -> str:
    s = (raw or "").lower()
    for needle, label in _SECTOR_BUCKETS:
        if needle in s:
            return label
    return "Other"


@app.get("/api/v1/sectors/spending")
@cached(key_prefix="sectors:spending", ttl=600)
async def get_sector_spending():
    """National sector spending roll-up across all 47 counties.

    For each county, we take the latest fiscal period that has actual
    execution data and aggregate budget lines into a canonical set of
    sectors (Health, Education, Roads, Water, etc.). Returns per-sector
    totals, execution rates, and the counties spending most in each
    sector. Powers the public /sectors page so citizens can see where
    public money is flowing across the whole devolved government.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    from collections import defaultdict
    from sqlalchemy import func as _sqlfunc4

    with next(get_db()) as db:
        counties = (
            db.query(DBEntity).filter(DBEntity.type == EntityType.COUNTY).all()
        )
        if not counties:
            return {
                "total_allocated": 0.0,
                "total_spent": 0.0,
                "counties_reporting": 0,
                "sectors": [],
            }

        entity_id_to_name: Dict[int, str] = {
            c.id: (c.canonical_name or "").replace(" County", "").strip()
            for c in counties
        }
        entity_ids = list(entity_id_to_name.keys())

        # Resolve the "latest executed period" per entity in one query.
        # Preference: max(period.start_date) WHERE sum(actual_spent) > 0.
        # Fallback: max(period.start_date) overall when nothing executed.
        # Both are expressed as window-free GROUP BY aggregates so we can
        # replace the per-entity loop that used to fire two sub-queries
        # each time (~141 queries for 47 counties).
        executed_periods = (
            db.query(
                DBBudgetLine.entity_id,
                _sqlfunc4.max(DBFiscalPeriod.start_date).label("start_date"),
            )
            .join(DBFiscalPeriod, DBBudgetLine.period_id == DBFiscalPeriod.id)
            .filter(
                DBBudgetLine.entity_id.in_(entity_ids),
                DBBudgetLine.category != "Total Budget",
            )
            .group_by(DBBudgetLine.entity_id, DBFiscalPeriod.id, DBFiscalPeriod.start_date)
            .having(_sqlfunc4.coalesce(_sqlfunc4.sum(DBBudgetLine.actual_spent), 0) > 0)
            .all()
        )
        # Keep only the max start_date per entity.
        latest_executed_date: Dict[int, Any] = {}
        for eid, sd in executed_periods:
            cur = latest_executed_date.get(eid)
            if cur is None or sd > cur:
                latest_executed_date[eid] = sd

        # Entities with no execution: fall back to their latest period by date.
        fallback_ids = [e for e in entity_ids if e not in latest_executed_date]
        if fallback_ids:
            fallback_rows = (
                db.query(
                    DBBudgetLine.entity_id,
                    _sqlfunc4.max(DBFiscalPeriod.start_date).label("start_date"),
                )
                .join(DBFiscalPeriod, DBBudgetLine.period_id == DBFiscalPeriod.id)
                .filter(
                    DBBudgetLine.entity_id.in_(fallback_ids),
                    DBBudgetLine.category != "Total Budget",
                )
                .group_by(DBBudgetLine.entity_id)
                .all()
            )
            for eid, sd in fallback_rows:
                latest_executed_date[eid] = sd

        # Resolve start_date → period_id per entity. One round-trip via
        # tuple-IN: (entity_id, start_date) pairs, which SQLite doesn't
        # support natively; fall back to a simple filter on the distinct
        # start_dates plus a Python lookup.
        if not latest_executed_date:
            return {
                "total_allocated": 0.0,
                "total_spent": 0.0,
                "counties_reporting": 0,
                "sectors": [],
            }

        unique_dates = list({d for d in latest_executed_date.values() if d is not None})
        period_rows = (
            db.query(DBFiscalPeriod.id, DBFiscalPeriod.start_date)
            .filter(DBFiscalPeriod.start_date.in_(unique_dates))
            .all()
        )
        date_to_period_ids: Dict[Any, List[int]] = defaultdict(list)
        for pid, sd in period_rows:
            date_to_period_ids[sd].append(pid)

        # Build (entity_id, period_id) filter set.
        entity_period_pairs: List[Tuple[int, int]] = []
        for eid, sd in latest_executed_date.items():
            for pid in date_to_period_ids.get(sd, []):
                entity_period_pairs.append((eid, pid))

        if not entity_period_pairs:
            return {
                "total_allocated": 0.0,
                "total_spent": 0.0,
                "counties_reporting": 0,
                "sectors": [],
            }

        # One final query: pull every budget line in those (entity, period)
        # pairs. This is bounded by "47 counties × ~15 categories" ≈ 700
        # rows — tiny compared to the 141 queries we used to issue.
        eids_for_filter = list({p[0] for p in entity_period_pairs})
        pids_for_filter = list({p[1] for p in entity_period_pairs})
        valid_pairs = set(entity_period_pairs)

        # Resolve the dominant fiscal period (for the page label) and whether
        # that FY is still in progress — if so, the execution figures are
        # projected/partial, NOT final actuals (audit §2.10).
        import datetime as _dt_sectors

        _period_meta = {}  # pid -> (label, end_date)
        if pids_for_filter:
            for _pid, _lbl, _end in (
                db.query(
                    DBFiscalPeriod.id,
                    DBFiscalPeriod.label,
                    DBFiscalPeriod.end_date,
                )
                .filter(DBFiscalPeriod.id.in_(pids_for_filter))
                .all()
            ):
                _period_meta[_pid] = (_lbl, _end)
        _label_counts = {}
        for _eid, _pid in valid_pairs:
            _lbl = _period_meta.get(_pid, (None, None))[0]
            if _lbl:
                _label_counts[_lbl] = _label_counts.get(_lbl, 0) + 1
        dominant_fy = (
            max(_label_counts, key=_label_counts.get) if _label_counts else None
        )
        _today_sectors = _dt_sectors.date.today()

        def _period_in_progress(_end) -> bool:
            if _end is None:
                return False
            _d = _end.date() if hasattr(_end, "date") else _end
            return _d >= _today_sectors

        is_partial_year = any(
            _period_in_progress(_period_meta.get(pid, (None, None))[1])
            for pid in pids_for_filter
        )

        all_lines = (
            db.query(
                DBBudgetLine.entity_id,
                DBBudgetLine.period_id,
                DBBudgetLine.category,
                DBBudgetLine.allocated_amount,
                DBBudgetLine.actual_spent,
            )
            .filter(
                DBBudgetLine.entity_id.in_(eids_for_filter),
                DBBudgetLine.period_id.in_(pids_for_filter),
                DBBudgetLine.category != "Total Budget",
            )
            .all()
        )

        sectors: Dict[str, Dict[str, Any]] = {}
        counties_seen_set: set = set()
        total_allocated = 0.0
        total_spent = 0.0

        for eid, pid, category, alloc_raw, spent_raw in all_lines:
            if (eid, pid) not in valid_pairs:
                continue
            counties_seen_set.add(eid)
            county_name = entity_id_to_name.get(eid, "")
            bucket = _sector_bucket(category or "")
            alloc = float(alloc_raw or 0)
            spent = float(spent_raw or 0)
            total_allocated += alloc
            total_spent += spent
            s = sectors.setdefault(
                bucket,
                {
                    "sector": bucket,
                    "allocated": 0.0,
                    "spent": 0.0,
                    "counties": {},
                },
            )
            s["allocated"] += alloc
            s["spent"] += spent
            cs = s["counties"].setdefault(
                county_name, {"county": county_name, "allocated": 0.0, "spent": 0.0}
            )
            cs["allocated"] += alloc
            cs["spent"] += spent

        counties_seen = len(counties_seen_set)

    out = []
    for label, s in sectors.items():
        top = sorted(
            s["counties"].values(), key=lambda c: c["spent"], reverse=True
        )[:5]
        util = (s["spent"] / s["allocated"] * 100) if s["allocated"] else 0.0
        out.append(
            {
                "sector": label,
                "allocated": round(s["allocated"], 2),
                "spent": round(s["spent"], 2),
                "utilization_pct": round(util, 1),
                "county_count": len(s["counties"]),
                "top_counties": [
                    {
                        "county": t["county"],
                        "allocated": round(t["allocated"], 2),
                        "spent": round(t["spent"], 2),
                    }
                    for t in top
                ],
            }
        )
    out.sort(key=lambda x: x["spent"], reverse=True)

    return {
        "fiscal_year": dominant_fy,
        "is_partial_year": is_partial_year,
        "is_projected": is_partial_year,
        "source": (
            "County budget allocations modelled from CRA equitable-share data; "
            "figures for an in-progress fiscal year are projected (National "
            "Treasury BPS), not final Controller-of-Budget actuals"
        ),
        "total_allocated": round(total_allocated, 2),
        "total_spent": round(total_spent, 2),
        "counties_reporting": counties_seen,
        "sectors": out,
    }


@app.get("/api/v1/sources/summary")
@cached(key_prefix="sources:summary", ttl=600)
async def get_sources_summary():
    """Summary of every agency/publisher feeding the platform.

    Aggregates directly from source_documents (authoritative — everything the
    app renders traces back through this table). Returns one entry per
    publisher with document counts, last-fetched timestamp, and doc-type
    breakdown. Used by the public /sources page so citizens can see where
    the numbers come from and when each feed was last refreshed.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    from sqlalchemy import func as _fn
    with next(get_db()) as db:
        rows = (
            db.query(
                DBSourceDocument.publisher,
                _fn.count(DBSourceDocument.id).label("doc_count"),
                _fn.max(DBSourceDocument.fetch_date).label("last_fetched"),
                _fn.max(DBSourceDocument.last_seen_at).label("last_seen_at"),
            )
            .group_by(DBSourceDocument.publisher)
            .order_by(_fn.count(DBSourceDocument.id).desc())
            .all()
        )

        # Doc-type breakdown per publisher
        breakdown_rows = (
            db.query(
                DBSourceDocument.publisher,
                DBSourceDocument.doc_type,
                _fn.count(DBSourceDocument.id),
            )
            .group_by(DBSourceDocument.publisher, DBSourceDocument.doc_type)
            .all()
        )
        by_pub: Dict[str, Dict[str, int]] = {}
        for pub, dt, n in breakdown_rows:
            dt_val = dt.value if hasattr(dt, "value") else str(dt)
            by_pub.setdefault(pub, {})[dt_val] = int(n)

    # Human-readable mapping for publishers we recognize. Keys are lowercase
    # substrings tested against the publisher string — handles the many
    # variations ("National Treasury", "National Treasury Kenya",
    # "National Treasury of Kenya", "Office of the Auditor-General", etc.).
    AGENCY_META: List[Tuple[str, Dict[str, str]]] = [
        (
            "controller of budget",
            {
                "short": "COB",
                "role": "Tracks how counties and national MDAs spend their budgets each quarter.",
                "website": "https://cob.go.ke",
            },
        ),
        (
            "auditor",
            {
                "short": "OAG",
                "role": "Independently audits government accounts and reports findings to Parliament.",
                "website": "https://www.oagkenya.go.ke",
            },
        ),
        (
            "bureau of statistics",
            {
                "short": "KNBS",
                "role": "Publishes population census, economic surveys and county statistical abstracts.",
                "website": "https://www.knbs.or.ke",
            },
        ),
        (
            "revenue allocation",
            {
                "short": "CRA",
                "role": "Recommends how revenue is divided between national and county governments.",
                "website": "https://www.crakenya.org",
            },
        ),
        (
            "revenue authority",
            {
                "short": "KRA",
                "role": "Collects national taxes — income tax, VAT, customs duty.",
                "website": "https://www.kra.go.ke",
            },
        ),
        (
            "central bank",
            {
                "short": "CBK",
                "role": "Monetary authority — publishes debt, reserves, and inflation statistics.",
                "website": "https://www.centralbank.go.ke",
            },
        ),
        (
            "parliament",
            {
                "short": "Parliament",
                "role": "National Assembly and Senate — publishes budget papers, hansards, and committee reports.",
                "website": "https://www.parliament.go.ke",
            },
        ),
        (
            "county treasury",
            {
                "short": "County Treasury",
                "role": "Each county's own finance office — publishes county budgets and programme-based estimates.",
                "website": None,
            },
        ),
        (
            "national treasury",
            {
                "short": "NT",
                "role": "Manages national finances — revenue, expenditure, debt issuance, and county transfers.",
                "website": "https://www.treasury.go.ke",
            },
        ),
        (
            "judiciary",
            {
                "short": "Judiciary",
                "role": "Publishes case filings and rulings on public-finance disputes.",
                "website": "https://judiciary.go.ke",
            },
        ),
    ]

    def _meta_for(pub: str) -> Dict[str, Any]:
        p = (pub or "").lower()
        for needle, m in AGENCY_META:
            if needle in p:
                return m
        return {}

    out = []
    for pub, count, fetched, seen in rows:
        meta = _meta_for(pub)
        out.append(
            {
                "publisher": pub,
                "short": meta.get("short", ""),
                "role": meta.get("role", ""),
                "website": meta.get("website"),
                "document_count": int(count or 0),
                "last_fetched": fetched.isoformat() if fetched else None,
                "last_seen_at": seen.isoformat() if seen else None,
                "doc_types": by_pub.get(pub, {}),
            }
        )
    return {"sources": out, "total_documents": sum(o["document_count"] for o in out)}


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


# ``require_admin`` is shared with the routers in ``backend/routers/`` —
# importing here lets us put the etl-jobs endpoint defined directly on
# ``app`` behind the same auth gate as the rest of /admin.
from supabase_auth import require_admin as _require_admin


@app.get("/api/v1/admin/etl/status")
async def get_etl_jobs_status(_actor=Depends(_require_admin)):
    """Get status of all ETL jobs.

    Gated on ``require_admin`` so the in-memory job map (queue size,
    source identifiers, error messages) isn't readable by
    unauthenticated callers — matches the rest of ``/admin/*``.
    """
    return {"jobs": _etl_jobs}


async def _setup_etl_scheduler():
    """Start the APScheduler ETL jobs (called from _startup_sequence).

    Was an @app.on_event("startup") hook — those are silently IGNORED
    once the app is constructed with a lifespan, so this had stopped
    running entirely after the lifespan migration.
    """
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

    # ------------------------------------------------------------------
    # Parliament ETL automation (daily ingest + weekly reconcile)
    # ------------------------------------------------------------------
    # Parliament jobs run via subprocess to avoid import shadowing between
    # backend/etl/ (normalizer) and the top-level etl/ package.
    if os.getenv("PARLIAMENT_PIPELINE_ENABLED", "0") == "1":
        logger.info("Parliament pipeline enabled — scheduling ingest & reconcile jobs")
        _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        def _sync_parliament_ingest():
            """Run Parliament ingest + validate as a subprocess."""
            import subprocess

            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "etl.parliament_orchestrator",
                        "--commit",
                        "--ingest-only",
                    ],
                    cwd=_project_root,
                    capture_output=True,
                    text=True,
                    timeout=3600,
                    env={**os.environ, "PARLIAMENT_PIPELINE_ENABLED": "1"},
                )
                if result.returncode != 0:
                    logger.error(
                        "Parliament ingest failed (rc=%d): %s",
                        result.returncode,
                        result.stderr[-1000:],
                    )
                else:
                    logger.info(
                        "Parliament ingest completed:\n%s", result.stdout[-1000:]
                    )
                return {"returncode": result.returncode}
            except subprocess.TimeoutExpired:
                logger.error("Parliament ingest timed out after 3600s")
                return {"returncode": -1, "error": "timeout"}
            except Exception as e:
                logger.exception("Parliament ingest failed: %s", e)
                return {"returncode": -1, "error": str(e)}

        def _sync_parliament_reconcile():
            """Run Parliament reconcile + validate as a subprocess."""
            import subprocess

            if os.getenv("PARLIAMENT_RECONCILE_ENABLED", "1") == "0":
                logger.info(
                    "Parliament reconcile disabled via PARLIAMENT_RECONCILE_ENABLED=0"
                )
                return {"status": "skipped"}
            try:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "etl.parliament_orchestrator",
                        "--commit",
                        "--reconcile-only",
                    ],
                    cwd=_project_root,
                    capture_output=True,
                    text=True,
                    timeout=3600,
                    env={**os.environ, "PARLIAMENT_PIPELINE_ENABLED": "1"},
                )
                if result.returncode != 0:
                    logger.error(
                        "Parliament reconcile failed (rc=%d): %s",
                        result.returncode,
                        result.stderr[-1000:],
                    )
                else:
                    logger.info(
                        "Parliament reconcile completed:\n%s", result.stdout[-1000:]
                    )
                return {"returncode": result.returncode}
            except subprocess.TimeoutExpired:
                logger.error("Parliament reconcile timed out after 3600s")
                return {"returncode": -1, "error": "timeout"}
            except Exception as e:
                logger.exception("Parliament reconcile failed: %s", e)
                return {"returncode": -1, "error": str(e)}

        async def _parliament_ingest_async():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(_etl_executor, _sync_parliament_ingest)

        async def _parliament_reconcile_async():
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(_etl_executor, _sync_parliament_reconcile)

        # Daily ingest: discover and insert new items (every 24h ± jitter)
        scheduler.add_job(
            _parliament_ingest_async,
            trigger="interval",
            seconds=jitter(24 * 3600),
            id="etl_parliament_ingest",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

        # Weekly reconcile: re-resolve entity metadata (every 7 days ± jitter)
        scheduler.add_job(
            _parliament_reconcile_async,
            trigger="interval",
            seconds=jitter(7 * 24 * 3600),
            id="etl_parliament_reconcile",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

        logger.info("Parliament scheduled: daily ingest + weekly reconcile")
    else:
        logger.info("Parliament pipeline disabled (PARLIAMENT_PIPELINE_ENABLED != 1)")

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
                # Base query — scoped to NATIONAL entities only
                budget_query = (
                    db.query(DBBudgetLine)
                    .join(DBEntity, DBBudgetLine.entity_id == DBEntity.id)
                    .filter(DBEntity.type == EntityType.NATIONAL)
                )
                from provenance import vintage_iso

                if fiscal_year:
                    fp = (
                        db.query(DBFiscalPeriod)
                        .filter(DBFiscalPeriod.label.ilike(f"%{fiscal_year}%"))
                        .first()
                    )
                    if fp:
                        budget_query = budget_query.filter(
                            DBBudgetLine.period_id == fp.id
                        )
                else:
                    # Default to latest national FY
                    _nat_pid = _latest_national_period(db)
                    if _nat_pid:
                        budget_query = budget_query.filter(
                            DBBudgetLine.period_id == _nat_pid
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

                # Resolve fiscal-period label for the response
                period_label = None
                resolved_pid = None
                if fiscal_year:
                    resolved_pid = (
                        db.query(DBFiscalPeriod.id, DBFiscalPeriod.label)
                        .filter(DBFiscalPeriod.label.ilike(f"%{fiscal_year}%"))
                        .first()
                    )
                    if resolved_pid:
                        period_label = resolved_pid.label
                else:
                    _nat_pid = _latest_national_period(db)
                    if _nat_pid:
                        period_label = (
                            db.query(DBFiscalPeriod.label)
                            .filter(DBFiscalPeriod.id == _nat_pid)
                            .scalar()
                        )

                # Honest scope label — this endpoint sums BudgetLine rows for
                # EntityType=NATIONAL only (CoB NG-BIRR records). It represents
                # National-Government execution, NOT the full consolidated
                # national budget (which additionally includes the county
                # equitable share transfer, ~400B+ KES for recent years).
                # Surfaced in BOTH _meta and data so the frontend (which reads
                # only ``data``) can render it next to the figure.
                scope_detail = (
                    "National-Government execution only (CoB NG-BIRR); "
                    "excludes county equitable share transfers."
                )
                return {
                    "status": "success",
                    "_meta": _response_meta(
                        unit="kes",
                        entity_scope="national",
                        fiscal_period=period_label,
                        scope_detail=scope_detail,
                        covers_through=period_label,
                        cache_ttl_seconds=1800,
                        data_quality="official",
                        quality_notes=(
                            check_period_nonempty(
                                len(allocations),
                                endpoint="/budget/national",
                                period_label=period_label,
                            )
                            or None
                        ),
                    ),
                    "data": {
                        "total": total_allocated,
                        "total_label": "National-Government allocation (CoB NG-BIRR)",
                        "scope_detail": scope_detail,
                        "total_spent": total_spent,
                        "execution_rate": execution_rate,
                        "development_budget": dev_budget,
                        "recurrent_budget": recurrent_budget,
                        "allocations": allocations,
                        "currency": "KES",
                    },
                    "data_source": "database",
                    "last_updated": vintage_iso(
                        db,
                        [
                            r[0]
                            for r in budget_query.with_entities(
                                DBBudgetLine.source_document_id
                            )
                            .distinct()
                            .all()
                        ],
                    ),
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
                # Resolve fiscal period
                period_id = None
                if fiscal_year:
                    fp = (
                        db.query(DBFiscalPeriod)
                        .filter(DBFiscalPeriod.label.ilike(f"%{fiscal_year}%"))
                        .first()
                    )
                    if fp:
                        period_id = fp.id
                else:
                    period_id = _latest_county_period(db)

                util_q = (
                    db.query(
                        DBEntity.canonical_name,
                        func.sum(DBBudgetLine.allocated_amount).label("allocated"),
                        func.sum(DBBudgetLine.actual_spent).label("spent"),
                    )
                    .join(DBBudgetLine, DBBudgetLine.entity_id == DBEntity.id)
                    .filter(DBEntity.type == EntityType.COUNTY)
                    .filter(DBBudgetLine.category != "Total Budget")
                )
                if period_id:
                    util_q = util_q.filter(DBBudgetLine.period_id == period_id)
                rows = util_q.group_by(DBEntity.canonical_name).all()
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
                    "_meta": _response_meta(unit="kes", entity_scope="county"),
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
            # ── Resolve latest county fiscal period ─────────────
            county_period_id = _latest_county_period(db)
            period_label = None
            if county_period_id:
                _fp = db.query(DBFiscalPeriod).get(county_period_id)
                period_label = _fp.label if _fp else None

            # ── Sector allocations (county-only, latest FY) ─────
            sector_q = (
                db.query(
                    DBBudgetLine.category,
                    func.sum(DBBudgetLine.allocated_amount).label("allocated"),
                    func.sum(DBBudgetLine.actual_spent).label("spent"),
                )
                .join(DBEntity, DBBudgetLine.entity_id == DBEntity.id)
                .filter(DBEntity.type == EntityType.COUNTY)
                .filter(DBBudgetLine.category != "Total Budget")
            )
            if county_period_id:
                sector_q = sector_q.filter(DBBudgetLine.period_id == county_period_id)
            sector_rows = sector_q.group_by(DBBudgetLine.category).all()
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

            # This response declares fiscal_history_unit = "billion_kes";
            # the table stores raw KES since the stage1 3a migration, so
            # convert here to keep the declared unit truthful.
            def _b(v) -> float:
                return float(v or 0) / 1e9

            for r in fiscal_rows:
                entry = {
                    "fiscal_year": r.fiscal_year,
                    "appropriated_budget": _b(r.appropriated_budget),
                    "total_revenue": _b(r.total_revenue),
                    "tax_revenue": _b(r.tax_revenue),
                    "non_tax_revenue": _b(r.non_tax_revenue),
                    "total_borrowing": _b(r.total_borrowing),
                    "borrowing_pct_of_budget": float(r.borrowing_pct_of_budget or 0),
                    "debt_service_cost": _b(r.debt_service_cost),
                    "development_spending": _b(r.development_spending),
                    "recurrent_spending": _b(r.recurrent_spending),
                    "county_allocation": _b(r.county_allocation),
                }
                # Only include years with substantially complete data —
                # World Bank back-fill years often only have 1-2 fields.
                key_fields = [
                    entry["appropriated_budget"],
                    entry["total_revenue"],
                    entry["total_borrowing"],
                    entry["county_allocation"],
                ]
                if sum(1 for v in key_fields if v > 0) >= 3:
                    fiscal_years.append(entry)

            latest = fiscal_years[-1] if fiscal_years else {}

            # ── Top / bottom utilization counties (same FY scope) ──
            util_q = (
                db.query(
                    DBEntity.canonical_name,
                    func.sum(DBBudgetLine.allocated_amount).label("a"),
                    func.sum(DBBudgetLine.actual_spent).label("s"),
                )
                .join(DBBudgetLine, DBBudgetLine.entity_id == DBEntity.id)
                .filter(DBEntity.type == EntityType.COUNTY)
                .filter(DBBudgetLine.category != "Total Budget")
            )
            if county_period_id:
                util_q = util_q.filter(DBBudgetLine.period_id == county_period_id)
            util_rows = util_q.group_by(DBEntity.canonical_name).all()
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

            # Plausibility checks
            _check_plausibility(
                total_allocated,
                _MAX_NATIONAL_BUDGET_KES,
                "budget/overview total_budget",
            )
            for s in sectors:
                _check_plausibility(
                    float(s.get("amount", 0)),
                    _MAX_NATIONAL_BUDGET_KES,
                    f"budget/overview sector {s.get('name')}",
                )

            # ── Trust-guard quality notes ───────────────────────────
            # These surface known credibility risks for this endpoint
            # so the UI can show a single "data quality" badge.
            #   1. Missing Personnel Emoluments category (real county
            #      data has this as ~50% of spend).
            #   2. Suspiciously uniform utilization (modeled data).
            #   3. Stale coverage relative to the current FY.
            #   4. Divergence between summed sectors and the seed
            #      total (caught by _check_plausibility above).
            quality_notes: list[str] = []
            sector_notes = check_budget_sectors(sectors)
            quality_notes.extend(sector_notes)
            quality_notes.extend(
                check_period_nonempty(
                    len(sectors),
                    endpoint="/budget/overview",
                    period_label=period_label,
                )
            )
            # If the sector-check found Personnel Emoluments missing OR
            # utilization uniformity, the data is demonstrably modeled
            # regardless of whether SourceDocument.description admits
            # it. Downgrade the default so the UI badge tints amber.
            _sector_flagged_modeling = any(
                "personnel emoluments" in n.lower()
                or "suspiciously uniform" in n.lower()
                for n in sector_notes
            )
            # Resolve the app's "current" FY from app settings so the
            # staleness check uses a deploy-time truth rather than
            # wall-clock-derived guesses.
            from models import FiscalPeriod as _FPModel
            _current_fp = (
                db.query(_FPModel.label)
                .order_by(_FPModel.start_date.desc())
                .limit(1)
                .scalar()
            )
            if _current_fp:
                quality_notes.extend(
                    check_coverage_staleness(
                        period_label,
                        current_fy_label=_current_fp,
                        max_stale_fys=1,
                    )
                )

            # ── Data-quality provenance ─────────────────────────────
            # The writer (backend/seeding/domains/counties_budget/
            # writer.py) persists data_quality into TWO places so we
            # can probe without joining a free-text description column:
            #   1. SourceDocument.meta["data_quality"] — authoritative
            #      (one per source; always reflects the latest seed).
            #   2. BudgetLine.provenance[].data_quality — per-line audit
            #      trail, surfaced here as a tiebreaker when the source
            #      is shared by a mix of fixture + real rows.
            # If any county line still reports "estimated" / "projected",
            # we downgrade the overall badge — one modeled sector taints
            # the aggregate.
            data_quality = "official"
            src_updated_at: datetime.datetime | None = None
            try:
                from models import BudgetLine as _BL, SourceDocument as _SD

                quality_q = (
                    db.query(
                        _SD.meta,
                        _SD.last_seen_at,
                        _SD.fetch_date,
                        _SD.created_at,
                        _BL.provenance,
                    )
                    .join(_BL, _BL.source_document_id == _SD.id)
                    .join(DBEntity, _BL.entity_id == DBEntity.id)
                    .filter(DBEntity.type == EntityType.COUNTY)
                )
                if county_period_id:
                    quality_q = quality_q.filter(_BL.period_id == county_period_id)
                quality_rows = quality_q.all()
                if quality_rows:
                    # Collect every data_quality token we see, from both
                    # source meta and per-line provenance entries.
                    tokens: set[str] = set()
                    for src_meta, _ls, _fd, _cr, prov in quality_rows:
                        if isinstance(src_meta, dict):
                            t = src_meta.get("data_quality")
                            if isinstance(t, str) and t:
                                tokens.add(t.lower())
                        if isinstance(prov, list):
                            for entry in prov:
                                if isinstance(entry, dict):
                                    t = entry.get("data_quality")
                                    if isinstance(t, str) and t:
                                        tokens.add(t.lower())

                    # Badge hierarchy: any "estimated"/"projected" taints
                    # the aggregate. "official" wins only if *every* row
                    # is official-or-unknown-but-at-least-one-official.
                    if "estimated" in tokens or "modeled" in tokens:
                        data_quality = "estimated"
                        quality_notes.insert(
                            0,
                            "County allocations shown here are modeled on "
                            "the CRA equitable-share formula, not sourced "
                            "from Controller of Budget execution reports. "
                            "Expect divergence from actual absorption.",
                        )
                    elif "projected" in tokens or "forecast" in tokens:
                        data_quality = "projected"
                    elif "official" in tokens:
                        data_quality = "official"
                    elif tokens:
                        # Only "unknown"/"historical"/"mixed" surfaced.
                        data_quality = "mixed" if len(tokens) > 1 else next(iter(tokens))

                    # source_updated_at = newest timestamp we can find
                    # across last_seen_at / fetch_date / created_at.
                    ts_values = [
                        t
                        for r in quality_rows
                        for t in (r[1], r[2], r[3])
                        if t is not None
                    ]
                    if ts_values:
                        src_updated_at = max(ts_values)
            except Exception as _e:
                logging.debug("budget/overview data_quality probe failed: %s", _e)

            # If trust-guard sector checks flagged the data as modeled
            # (no Personnel Emoluments, or σ<1.0 uniformity), honour
            # that signal even if the SourceDocument probe said otherwise.
            if _sector_flagged_modeling and data_quality == "official":
                data_quality = "estimated"

            # ── Post-activation trust checks (April-2026) ───────────
            # These fire once the live COB ingestion path is running
            # so we catch: stale feed (pipeline broken), Total-only
            # extraction (scraper heuristic drift), and repeated
            # ingestion failures (COB site outage).
            #
            # Conservative rule: any of these downgrades the badge
            # from "official" → "estimated". Badge only goes green
            # when freshness, category coverage, AND sector sanity
            # all pass.
            try:
                from services.trust_guards import (
                    check_category_coverage,
                    check_consecutive_fetch_failures,
                    check_source_freshness,
                )

                # Freshness: newest fetch_date across county-scope
                # SourceDocuments. Missing = no successful fetch ever.
                freshness_notes = check_source_freshness(
                    src_updated_at,
                    label="County budget feed (COB)",
                    max_age_days=120,
                )
                quality_notes.extend(freshness_notes)

                # Category coverage: if the DB carries only "Total"
                # rows for counties, the scraper didn't find the
                # sub-aggregate tables in the source PDF.
                try:
                    from models import BudgetLine as _BL2

                    cat_rows = (
                        db.query(_BL2.category)
                        .join(DBEntity, _BL2.entity_id == DBEntity.id)
                        .filter(DBEntity.type == EntityType.COUNTY)
                    )
                    if county_period_id:
                        cat_rows = cat_rows.filter(_BL2.period_id == county_period_id)
                    raw_categories = [r[0] for r in cat_rows.distinct().all()]
                except Exception:
                    raw_categories = []

                coverage_notes = check_category_coverage(
                    raw_categories,
                    require_pe=True,
                    require_recurrent_dev_split=False,
                )
                quality_notes.extend(coverage_notes)

                # Consecutive failures: scan the recent IngestionJob
                # history for the counties_budget domain.
                try:
                    from models import IngestionJob as _IJ

                    recent = (
                        db.query(_IJ.status)
                        .filter(_IJ.domain == "counties_budget")
                        .order_by(_IJ.started_at.desc())
                        .limit(5)
                        .all()
                    )
                    # Reverse to chronological order for the checker.
                    statuses = [
                        getattr(r[0], "value", str(r[0])).lower()
                        for r in reversed(recent)
                    ]
                except Exception:
                    statuses = []

                failure_notes = check_consecutive_fetch_failures(
                    statuses,
                    domain="counties_budget",
                    threshold=3,
                )
                quality_notes.extend(failure_notes)

                # If any of the three guards fired, the badge cannot
                # honestly remain "official".
                if (
                    (freshness_notes or coverage_notes or failure_notes)
                    and data_quality == "official"
                ):
                    data_quality = "estimated"
            except Exception as _e:
                logging.debug(
                    "budget/overview post-activation trust checks failed: %s", _e
                )

            scope_detail = (
                "Sector allocations are aggregated from county-level "
                "BudgetLine rows for the latest fiscal period with data. "
                "Personnel Emoluments — typically ~50% of county spending "
                "— is not broken out unless the source fixture includes "
                "it as a category. Figures therefore reflect non-wage "
                "allocations when the seed is CRA-formula based."
            )

            # /budget/overview returns mixed units (sectors in KES,
            # fiscal_history in billion KES, county_utilization in KES),
            # so extend the standard _meta envelope with per-section unit
            # keys — tests in test_unit_safety assert these exact fields.
            _budget_overview_meta = _response_meta(
                unit="mixed",
                entity_scope="all",
                fiscal_period=period_label,
                scope_detail=scope_detail,
                covers_through=period_label,
                cache_ttl_seconds=1800,
                source_updated_at=src_updated_at,
                data_quality=data_quality,
                quality_notes=quality_notes or None,
            )
            _budget_overview_meta["summary_unit"] = "kes"
            _budget_overview_meta["sectors_unit"] = "kes"
            _budget_overview_meta["fiscal_history_unit"] = "billion_kes"
            _budget_overview_meta["county_utilization_unit"] = "kes"
            return {
                "status": "success",
                "data_source": "database",
                "fiscal_period": period_label,
                "last_updated": (
                    src_updated_at.isoformat() if src_updated_at else None
                ),
                "_meta": _budget_overview_meta,
                "summary": {
                    "total_budget": total_allocated,
                    "total_spent": total_spent,
                    "execution_rate": (
                        round(total_spent / total_allocated * 100, 1)
                        if total_allocated > 0
                        else 0
                    ),
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

        # Inflation (CPI): read the CANONICAL ``inflation_rate`` series — the
        # same maintained series /economic/summary uses (seeded by bootstrap,
        # the economic_indicators domain, and auto_seeder) — taking the latest
        # observation by date. The legacy ``inflation_rate_cpi`` key was written
        # ONLY by the hardcoded MVP seeder and was frozen at Jan-2024 = 6.3%, so
        # the budget page contradicted the rest of the site with a stale figure
        # (audit §3.10). Reading the maintained series makes this self-update and
        # stay consistent; the legacy key is a fallback only if the series is
        # absent. Kenyan CPI is published by KNBS, not CBK.
        inflation_row = (
            db.query(EconomicIndicator)
            .filter(EconomicIndicator.indicator_type == "inflation_rate")
            .order_by(EconomicIndicator.indicator_date.desc())
            .first()
        ) or (
            db.query(EconomicIndicator)
            .filter(EconomicIndicator.indicator_type == "inflation_rate_cpi")
            .order_by(EconomicIndicator.indicator_date.desc())
            .first()
        )
        inflation_pct = (
            float(inflation_row.value)
            if inflation_row and inflation_row.value is not None
            else econ_map.get("inflation_rate") or econ_map.get("inflation_rate_cpi")
        )
        inflation_as_of = (
            inflation_row.indicator_date.isoformat()
            if inflation_row and inflation_row.indicator_date
            else None
        )

        # Get total population (sum of all counties)
        total_pop = db.query(func.sum(PopulationData.total_population)).scalar()
        total_pop = int(total_pop) if total_pop else None

        # Get latest fiscal summary for budget context
        latest_fiscal = (
            db.query(FiscalSummary).order_by(FiscalSummary.fiscal_year.desc()).first()
        )

        # fiscal_summaries stores raw KES (stage1 3a migration).
        budget_raw_kes = (
            float(latest_fiscal.appropriated_budget)
            if latest_fiscal and latest_fiscal.appropriated_budget
            else None
        )
        revenue_raw_kes = (
            float(latest_fiscal.total_revenue)
            if latest_fiscal and latest_fiscal.total_revenue
            else None
        )

        economic_context = {
            "gdp_billion_kes": gdp_billion,
            "gdp_growth_pct": econ_map.get("gdp_growth_rate"),
            "inflation_pct": inflation_pct,
            "inflation_as_of": inflation_as_of,
            "inflation_source": "KNBS Consumer Price Index",
            "unemployment_pct": econ_map.get("unemployment_rate"),
            "total_population": total_pop,
            "budget_to_gdp_pct": (
                round((budget_raw_kes / (gdp_billion * 1e9)) * 100, 1)
                if budget_raw_kes and gdp_billion
                else None
            ),
            "revenue_to_gdp_pct": (
                round((revenue_raw_kes / (gdp_billion * 1e9)) * 100, 1)
                if revenue_raw_kes and gdp_billion
                else None
            ),
            "per_capita_budget_kes": (
                round(budget_raw_kes / total_pop)
                if budget_raw_kes and total_pop
                else None
            ),
            "per_capita_revenue_kes": (
                round(revenue_raw_kes / total_pop)
                if revenue_raw_kes and total_pop
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

        # The execution pipeline below is scoped to ONE national period; surface
        # its fiscal-year label so the UI can show which FY the execution figures
        # cover. CoB NG-BIRR execution lags the page's selected FY (audit §2.3),
        # so it must be labelled with its own FY, not the page's.
        execution_fiscal_year = None
        if national_entity:
            # Scope to latest national FY to avoid summing across all periods
            _nat_pid = _latest_national_period(db)
            if _nat_pid:
                execution_fiscal_year = (
                    db.query(DBFiscalPeriod.label)
                    .filter(DBFiscalPeriod.id == _nat_pid)
                    .scalar()
                )
            sector_q = (
                db.query(
                    BudgetLine.category,
                    func.sum(BudgetLine.allocated_amount).label("allocated"),
                    func.sum(BudgetLine.actual_spent).label("spent"),
                )
                .filter(BudgetLine.entity_id == national_entity)
                .filter(BudgetLine.committed_amount.isnot(None))
                .filter(BudgetLine.allocated_amount > 0)
            )
            if _nat_pid:
                sector_q = sector_q.filter(BudgetLine.period_id == _nat_pid)
            sector_pipeline = sector_q.group_by(BudgetLine.category).all()
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
            "_meta": {
                "revenue_by_source_unit": "billion_kes",
                "execution_by_sector_unit": "kes",
                "economic_context_units": "field_name_suffixed",
                "entity_scope": "national",
            },
            "revenue_by_source": revenue_by_source,
            "economic_context": economic_context,
            "execution_by_sector": execution_by_sector,
            "execution_fiscal_year": execution_fiscal_year,
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
    from sqlalchemy import func  # noqa: F401 — used for reconciliation sum

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
                    # The row's declared unit (stage1 3a): "KES" = raw KES.
                    # Consumers convert on this field, never by guessing
                    # magnitude — see F5.5.
                    "unit": r.unit,
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

        # ── Cross-check against /debt/national (Loan sum) ──
        # Same rationale as the reciprocal check on /debt/national:
        # surface any divergence so callers can display an honest badge.
        reconciliation: dict = {
            "primary_source": "debt_timeline_table",
            # debt_timeline stores raw KES with a declared unit column
            # (stage1 3a migration) — no scale factor.
            "primary_value_kes": (
                float(rows[-1].total) if rows and rows[-1].total else None
            ),
            "secondary_source": "loans_table",
            "secondary_value_kes": None,
            "percent_diff": None,
            "status": "unchecked",
            "note": "",
        }
        try:
            from models import EntityType as _ET

            national_entity = (
                db.query(DBEntity).filter(DBEntity.type == _ET.NATIONAL).first()
            )
            if national_entity:
                # Reconcile against /debt/national, which excludes
                # PENDING_BILLS — match that filter (including the
                # NULL-counts-as-debt rule from ``_is_debt_loan``) so
                # the diff_pct below isn't dominated by a category
                # mismatch.
                from models import DebtCategory as _DC

                loan_sum = (
                    db.query(func.sum(DBLoan.outstanding))
                    .filter(
                        DBLoan.entity_id == national_entity.id,
                        or_(
                            DBLoan.debt_category.is_(None),
                            DBLoan.debt_category != _DC.PENDING_BILLS,
                        ),
                    )
                    .scalar()
                    or 0
                )
                loan_sum_f = float(loan_sum)
                reconciliation["secondary_value_kes"] = loan_sum_f
                primary_kes = reconciliation["primary_value_kes"]
                if primary_kes and loan_sum_f > 0:
                    diff_pct = abs(primary_kes - loan_sum_f) / primary_kes * 100
                    reconciliation["percent_diff"] = round(diff_pct, 2)
                    if diff_pct > 5.0:
                        reconciliation["status"] = "divergent"
                        reconciliation["note"] = (
                            "DebtTimeline and loans_table disagree by more "
                            "than 5%. These are independent sources."
                        )
                        logging.warning(
                            "/debt/timeline reconciliation divergent: "
                            "timeline=%.0f KES, loans=%.0f KES, diff=%.2f%%",
                            primary_kes,
                            loan_sum_f,
                            diff_pct,
                        )
                    else:
                        reconciliation["status"] = "consistent"
        except Exception as exc:  # pragma: no cover
            logger.warning("timeline reconciliation failed: %s", exc)

        # ── Freshness + trust metadata ──────────────────────────────
        covers_through_label = f"{rows[-1].year}" if rows else None
        timeline_quality_notes: list[str] = []
        if reconciliation.get("status") == "divergent":
            timeline_quality_notes.append(
                reconciliation.get("note")
                or "Debt sources diverge beyond reconciliation threshold."
            )
        src_updated = rows[-1].updated_at if rows and rows[-1].updated_at else None

        return {
            "status": "success",
            "data_source": "database",
            "_meta": _response_meta(
                unit="billion_kes",
                entity_scope="national",
                covers_through=covers_through_label,
                cache_ttl_seconds=86400,
                source_updated_at=src_updated,
                data_quality=(
                    "mixed" if reconciliation.get("status") == "divergent"
                    else "official"
                ),
                quality_notes=timeline_quality_notes or None,
            ),
            "last_updated": last_updated,
            "source": source_title,
            "years": len(timeline),
            "timeline": timeline,
            "reconciliation": reconciliation,
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
                # The row's declared unit (stage1 3a): "KES" = raw KES.
                "unit": r.unit,
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

        all_fiscal_years = [_row_to_dict(r) for r in rows]
        # Only include years with substantially complete data —
        # World Bank back-fill years often only have 1-2 fields.
        fiscal_years = [
            fy
            for fy in all_fiscal_years
            if sum(
                1
                for k in (
                    "appropriated_budget",
                    "total_revenue",
                    "total_borrowing",
                    "county_allocation",
                )
                if (fy.get(k) or 0) > 0
            )
            >= 3
        ]
        latest = fiscal_years[-1] if fiscal_years else all_fiscal_years[-1]

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

        # Fiscal anchor: the KES 10T NUMERIC debt ceiling was REPEALED by the
        # PFM (Amendment) Act 2023, which replaced it with a debt anchor of
        # 55% of GDP in present-value terms (target 2028). The debt_ceiling /
        # debt_ceiling_usage_pct fields are retained only for historical
        # context — they are no longer the binding fiscal rule.
        _imf_d2g = _latest_imf_debt_to_gdp(db)
        debt_anchor = {
            "anchor_pct_gdp": 55.0,
            "basis": (
                "PFM (Amendment) Act 2023 — 55% of GDP in present-value terms "
                "(target 2028); replaced the repealed KES 10T numeric ceiling"
            ),
            "debt_to_gdp_pct": _imf_d2g[0] if _imf_d2g else None,
            "debt_to_gdp_year": _imf_d2g[1] if _imf_d2g else None,
            "debt_to_gdp_basis": (
                "IMF General Government Gross Debt, % of GDP (nominal); compared "
                "to the 55% present-value anchor this is indicative, not exact"
            ),
            "above_anchor": (_imf_d2g[0] > 55.0) if _imf_d2g else None,
            "former_numeric_ceiling_kes_billion": 10000,
            "former_ceiling_repealed": True,
        }

        # Surface objective plausibility/reconciliation caveats on the headline
        # year (same guard that quarantines bad rows at seed time), so an
        # implausible figure shows a data-quality note rather than passing as
        # fact. Empty for clean data.
        from services.trust_guards import check_fiscal_summary

        _fiscal_quality_notes = check_fiscal_summary(latest) if latest else []

        return {
            "status": "success",
            "data_source": "database",
            "_meta": _response_meta(
                unit="billion_kes",
                entity_scope="national",
                quality_notes=_fiscal_quality_notes or None,
            ),
            "last_updated": last_updated,
            "source": source_title,
            "current": latest,
            "history": fiscal_years,
            "total_fiscal_years": len(fiscal_years),
            "debt_anchor": debt_anchor,
        }
    except Exception as e:
        logging.error(f"Error fetching fiscal summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/learn/civic-figures")
@cached(key_prefix="learn:civic_figures", ttl=3600)
async def get_civic_figures(db: Session = Depends(get_db)):
    """Live civic figures for the Learn glossary (audit §2.7; design §5.9).

    Every fiscal magnitude the glossary cites — nominal GDP, the national
    budget, public debt, the county equitable share — is resolved HERE from
    its one canonical DB source, with the period it refers to and its
    provenance, so the glossary renders current numbers and self-updates as
    new data is seeded instead of carrying hardcoded literals that silently
    go stale (the exact failure mode behind the 14.6T→15.0T→16.2T GDP drift).

    A figure that was never seeded (or has no period) returns
    ``available=False``; the UI then shows a dated last-known example
    rather than a fabricated current number (DESIGN §1, decision 1:
    last-known-good, dated).

    There is intentionally NO hardcoded magnitude in this endpoint.
    """
    from provenance import vintage_iso

    def _figure(value, period, source, as_of, data_quality="official"):
        val = float(value) if value not in (None, 0) else None
        return {
            "available": val is not None and val > 0 and bool(period),
            "value": val,
            "unit": "kes",
            "period": period,
            "source": source,
            "as_of": as_of,
            "data_quality": data_quality,
        }

    def _fs_to_kes(value):
        """FiscalSummary stores billion-KES (see `_response_meta(unit='billion_kes')`
        and seeding/real_data/fiscal_summary.json), whereas GDPData and Loan
        store RAW KES. Normalise the fiscal figures to raw KES so every figure
        this endpoint emits shares one unit and the UI formats them uniformly.
        The < 1e7 guard scales the billions convention (~3e3-5e3) but leaves an
        already-raw value (~1e12) untouched, so a future unit change can't
        silently 1e9× the budget."""
        if value in (None, 0):
            return None
        v = float(value)
        if v <= 0:
            return None
        return v * 1e9 if v < 1e7 else v

    figures: dict[str, dict] = {}

    try:
        # ── Nominal GDP — the national series (entity_id NULL) seeded by the
        #    `national_gdp` domain from World Bank NY.GDP.MKTP.CN; fall back to
        #    any latest GDP row. The period is the GDP *data* year. ──────────
        gdp_row = (
            db.query(DBGDPData)
            .filter(DBGDPData.entity_id.is_(None))
            .order_by(DBGDPData.year.desc())
            .first()
        ) or db.query(DBGDPData).order_by(DBGDPData.year.desc()).first()
        figures["nominal_gdp"] = _figure(
            value=gdp_row.gdp_value if gdp_row else None,
            period=str(gdp_row.year) if gdp_row else None,
            source="World Bank / KNBS",
            as_of=(
                vintage_iso(db, [getattr(gdp_row, "source_document_id", None)])
                if gdp_row
                else None
            ),
        )

        # ── National budget + county equitable share — latest FiscalSummary
        #    row that actually carries each field. Period is the fiscal year. ─
        from models import FiscalSummary as _FS

        fs_rows = db.query(_FS).order_by(_FS.fiscal_year.asc()).all()

        def _latest_fs(attr):
            for r in reversed(fs_rows):
                v = getattr(r, attr, None)
                if v and float(v) > 0:
                    return r
            return None

        budget_row = _latest_fs("appropriated_budget")
        share_row = _latest_fs("county_allocation")
        figures["national_budget"] = _figure(
            value=_fs_to_kes(budget_row.appropriated_budget) if budget_row else None,
            period=budget_row.fiscal_year if budget_row else None,
            source="National Treasury / Controller of Budget",
            as_of=(
                vintage_iso(db, [getattr(budget_row, "source_document_id", None)])
                if budget_row
                else None
            ),
        )
        figures["equitable_share"] = _figure(
            value=_fs_to_kes(share_row.county_allocation) if share_row else None,
            period=share_row.fiscal_year if share_row else None,
            source="Division of Revenue Act / CRA",
            as_of=(
                vintage_iso(db, [getattr(share_row, "source_document_id", None)])
                if share_row
                else None
            ),
        )

        # ── Public debt — outstanding stock of national debt loans, excluding
        #    pending bills (the `_is_debt_loan` rule used by /debt/national so
        #    the two never diverge). Period is the source vintage year. ───────
        from models import EntityType as _ET

        national_entity = (
            db.query(DBEntity).filter(DBEntity.type == _ET.NATIONAL).first()
        )
        debt_value = None
        debt_as_of = None
        if national_entity:
            debt_loans = [
                ln
                for ln in db.query(DBLoan)
                .filter(DBLoan.entity_id == national_entity.id)
                .all()
                if _is_debt_loan(ln)
            ]
            if debt_loans:
                debt_value = sum(float(ln.outstanding or 0) for ln in debt_loans)
                debt_as_of = vintage_iso(
                    db,
                    [getattr(ln, "source_document_id", None) for ln in debt_loans],
                )
        figures["public_debt"] = _figure(
            value=debt_value,
            period=debt_as_of[:4] if debt_as_of else None,
            source="Central Bank of Kenya / National Treasury",
            as_of=debt_as_of,
        )
    except Exception as e:  # pragma: no cover - defensive
        logging.error("Error building civic figures: %s", e)
        # Degrade to "nothing available" rather than 500 — the glossary then
        # shows its dated fallbacks, never a fabricated number.
        return {"status": "error", "data_source": "database", "figures": figures}

    return {"status": "success", "data_source": "database", "figures": figures}


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

        # Query loans excluding pending bills, sorted by outstanding desc.
        # NULL ``debt_category`` rows still count as debt (matches the
        # ``_is_debt_loan`` predicate); a bare ``!=`` would silently
        # drop them via SQL three-valued logic.
        loans = (
            db.query(DBLoan)
            .filter(
                DBLoan.entity_id == national_entity.id,
                or_(
                    DBLoan.debt_category.is_(None),
                    DBLoan.debt_category != DebtCategory.PENDING_BILLS,
                ),
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
            "_meta": _response_meta(unit="kes", entity_scope="national"),
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

        # Query all national loans (excluding pending bills). NULL
        # ``debt_category`` rows still count as debt — see the
        # ``_is_debt_loan`` predicate; a bare ``!=`` would silently
        # drop them via SQL three-valued logic.
        loans = (
            db.query(DBLoan)
            .filter(
                DBLoan.entity_id == national_entity.id,
                or_(
                    DBLoan.debt_category.is_(None),
                    DBLoan.debt_category != DebtCategory.PENDING_BILLS,
                ),
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

        # Plausibility
        _check_plausibility(
            total_outstanding,
            _MAX_NATIONAL_BUDGET_KES * 3,
            "debt/loans total_outstanding",
        )

        return {
            "_meta": _response_meta(unit="kes", entity_scope="national"),
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


def _latest_imf_debt_to_gdp(db):
    """Latest IMF GGXWDG_NGDP (general-government gross debt, % of GDP) for Kenya.

    Returns ``(ratio_pct, year, vintage_iso)`` for the most recent ACTUAL
    (non-projection) year in the newest WEO vintage, or ``None`` if the IMF
    table is not seeded. This is the vintage-consistent headline
    debt-to-GDP measure (same-year debt and GDP) and avoids the prior bug
    of dividing a current debt stock by a stale/low nominal-GDP year.
    """
    try:
        from models import ImfWeoObservation
        from sqlalchemy import func as _func

        latest_vintage = (
            db.query(_func.max(ImfWeoObservation.vintage))
            .filter(ImfWeoObservation.country_code == "KEN")
            .scalar()
        )
        if latest_vintage is None:
            return None
        rows = (
            db.query(ImfWeoObservation)
            .filter(
                ImfWeoObservation.country_code == "KEN",
                ImfWeoObservation.indicator == "GGXWDG_NGDP",
                ImfWeoObservation.vintage == latest_vintage,
            )
            .order_by(ImfWeoObservation.year)
            .all()
        )
        usable = [r for r in rows if r.value is not None]
        if not usable:
            return None
        actuals = [r for r in usable if not r.is_projection]
        chosen = (actuals or usable)[-1]
        return (round(float(chosen.value), 1), chosen.year, latest_vintage.isoformat())
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning("IMF debt-to-GDP lookup failed: %s", exc)
        return None


@app.get("/api/v1/debt/national")
@cached(
    key_prefix="debt:national", ttl=43200
)  # 12 hours — national debt data changes infrequently
async def get_national_debt():
    """Get national debt overview with categorized breakdown."""
    # Distinguish "the database said there is nothing" from "we could not ask
    # the database". Both used to return zeros, so an outage rendered as
    # "Kenya owes KES 0.00T, LOW RISK" on the homepage.
    _db_unreachable = False
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
                    # Calculate totals — exclude PENDING_BILLS so the
                    # headline "Total Debt" KPI doesn't inflate by the
                    # ~702B of pending bills that PR #84 started landing
                    # in the loans table. The per-category breakdown
                    # below still reports pending_bills as its own line
                    # via ``categories["pending_bills"]``, so no data
                    # is lost — only the misleading top-level sum is
                    # corrected.
                    total_debt = sum(
                        float(loan.principal or 0)
                        for loan in loans
                        if _is_debt_loan(loan)
                    )
                    total_outstanding = sum(
                        float(loan.outstanding or 0)
                        for loan in loans
                        if _is_debt_loan(loan)
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

                    # ── Cross-check against DebtTimeline (aggregate series) ──
                    # The Loan table and DebtTimeline table are populated from
                    # different source documents (Treasury QEDR / CBK vs CBK
                    # Annual Report / BPS). They should agree within a few
                    # percent. If they disagree substantially we log a warning
                    # and surface the diff in the response so the UI can show
                    # an honest "data sources disagree" badge.
                    from models import DebtTimeline as _DT

                    latest_timeline_row = (
                        db.query(_DT).order_by(_DT.year.desc()).first()
                    )

                    # Correct the external-vs-domestic DIRECTION using the
                    # authoritative CBK aggregate (DebtTimeline). The loan register
                    # individually tracks external loans but under-represents
                    # domestic instruments (T-bonds/bills), which inverted the split
                    # (audit §3.3 — domestic has led external since ~2024). Keep the
                    # loan-register total as the base and apply the CBK split
                    # proportion, so the parts still sum to the total.
                    if (
                        latest_timeline_row
                        and latest_timeline_row.external
                        and latest_timeline_row.domestic
                    ):
                        _tl_ext = float(latest_timeline_row.external)
                        _tl_dom = float(latest_timeline_row.domestic)
                        _tl_split = _tl_ext + _tl_dom
                        _base = external_debt + domestic_debt
                        if _tl_split > 0 and _base > 0:
                            external_debt = _base * (_tl_ext / _tl_split)
                            domestic_debt = _base * (_tl_dom / _tl_split)

                    reconciliation: dict = {
                        "primary_source": "loans_table",
                        "primary_value_kes": total_outstanding,
                        "secondary_source": "debt_timeline_table",
                        "secondary_value_kes": None,
                        "secondary_year": None,
                        "percent_diff": None,
                        "status": "unchecked",
                        "note": "",
                    }
                    if latest_timeline_row and latest_timeline_row.total:
                        # DebtTimeline stores raw KES (stage1 3a migration).
                        secondary_kes = float(latest_timeline_row.total)
                        reconciliation["secondary_value_kes"] = secondary_kes
                        reconciliation["secondary_year"] = latest_timeline_row.year
                        if total_outstanding > 0:
                            diff_pct = (
                                abs(total_outstanding - secondary_kes)
                                / total_outstanding
                                * 100
                            )
                            reconciliation["percent_diff"] = round(diff_pct, 2)
                            if diff_pct > 5.0:
                                reconciliation["status"] = "divergent"
                                reconciliation["note"] = (
                                    "Loan-sum and DebtTimeline disagree by more "
                                    "than 5%. The two tables are seeded from "
                                    "different source documents; the loan-level "
                                    "sum is the authoritative value for this "
                                    "endpoint."
                                )
                                logging.warning(
                                    "/debt/national reconciliation divergent: "
                                    "loans=%.0f KES, timeline=%.0f KES, diff=%.2f%%",
                                    total_outstanding,
                                    secondary_kes,
                                    diff_pct,
                                )
                            else:
                                reconciliation["status"] = "consistent"

                    # Headline debt-to-GDP: prefer the IMF published ratio
                    # (GGXWDG_NGDP), which is vintage-consistent (same-year
                    # debt and GDP). Fall back to central-government debt /
                    # nominal GDP (World Bank) with the GDP year labelled.
                    # This replaces the old bug of dividing current debt by a
                    # stale/low hardcoded GDP (which produced 82% vs ~68%).
                    _computed_ratio = (
                        round(total_outstanding / gdp_value * 100, 1)
                        if gdp_value > 0
                        else 0
                    )
                    _imf = _latest_imf_debt_to_gdp(db)
                    if _imf is not None:
                        debt_to_gdp_ratio = _imf[0]
                        debt_to_gdp_year = _imf[1]
                        debt_to_gdp_basis = (
                            "IMF General Government Gross Debt, % of GDP "
                            "(GGXWDG_NGDP) — vintage-consistent"
                        )
                        debt_to_gdp_source = "IMF World Economic Outlook"
                    else:
                        debt_to_gdp_ratio = _computed_ratio
                        debt_to_gdp_year = gdp_year
                        debt_to_gdp_basis = (
                            "Central government debt (CBK) / nominal GDP "
                            f"(World Bank, {gdp_year}) — approximate"
                        )
                        debt_to_gdp_source = "CBK / World Bank"

                    # Real data vintage from source-document provenance —
                    # NOT the request time. Stops the card claiming it was
                    # "updated just now" for data that is months old.
                    from provenance import resolve_data_vintage

                    _vintage = resolve_data_vintage(
                        db,
                        [getattr(loan, "source_document_id", None) for loan in loans]
                        + [getattr(latest_gdp_row, "source_document_id", None)],
                    )
                    _vintage_iso = _vintage.isoformat() if _vintage else None

                    # Surface objective composition plausibility (0.4) so an
                    # implausible split/ratio is flagged, not shown as fact.
                    _composition_notes = check_debt_composition(
                        total=total_outstanding,
                        external=external_debt,
                        domestic=domestic_debt,
                        debt_to_gdp=debt_to_gdp_ratio,
                    )

                    return {
                        "status": "success",
                        "data_source": "database",
                        "last_updated": _vintage_iso,
                        "data": {
                            "total_debt": total_debt,
                            "total_outstanding": total_outstanding,
                            "loan_count": len(loans),
                            "gdp": gdp_value,
                            "gdp_year": gdp_year,
                            "debt_to_gdp_ratio": debt_to_gdp_ratio,
                            "debt_to_gdp_year": debt_to_gdp_year,
                            "debt_to_gdp_basis": debt_to_gdp_basis,
                            "debt_to_gdp_source": debt_to_gdp_source,
                            "debt_to_gdp_computed_central_gov": _computed_ratio,
                            "reconciliation": reconciliation,
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
                                    if debt_to_gdp_ratio > 65
                                    else (
                                        "Moderate"
                                        if debt_to_gdp_ratio > 0
                                        else "Unknown"
                                    )
                                ),
                                "debt_to_gdp": debt_to_gdp_ratio,
                                "assessment": (
                                    "Kenya's debt remains elevated. The IMF classifies Kenya at high risk of debt distress."
                                    if debt_to_gdp_ratio > 65
                                    else "Seed GDP data for full sustainability assessment."
                                ),
                            },
                        },
                        "currency": "KES",
                        "source": "Central Bank of Kenya / National Treasury",
                        "_meta": _response_meta(
                            unit="kes",
                            entity_scope="national",
                            quality_notes=_composition_notes or None,
                        ),
                    }
        except Exception as e:
            logging.error(f"DB debt query failed: {e}")
            _db_unreachable = True

    # Absent is not zero. Returning 0 here rendered a database outage as a
    # headline claim that Kenya has no national debt and is at LOW risk
    # (classifyDebtRisk(0) -> "Low"). Every money field is null with a
    # machine-readable reason so no client can turn a failure into a figure.
    _reason = "source_unavailable" if _db_unreachable else "not_yet_seeded"
    logging.warning(
        "/debt/national returning no figures — reason=%s", _reason
    )
    return {
        "status": "no_data",
        "data_source": (
            "database_unavailable" if _db_unreachable else "database_empty"
        ),
        "reason": _reason,
        "last_updated": None,
        "message": (
            "National debt figures are unavailable because the data source "
            "could not be read. This is not a finding that debt is zero."
            if _db_unreachable
            else "No national debt data in database. "
            "Run: python -m seeding.cli seed --domain national_debt"
        ),
        "data": {
            "total_debt": None,
            "total_outstanding": None,
            "loan_count": None,
            "gdp": None,
            "debt_to_gdp_ratio": None,
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
      - https://cob.go.ke/publications/pending-bills/
      - https://cob.go.ke/publications/national-government-budget-implementation-review-reports/
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
                for eid, ename, etype in (
                    db.query(DBEntity.id, DBEntity.canonical_name, DBEntity.type)
                    .filter(DBEntity.id.in_(unique_eids))
                    .all()
                ):
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
                    provenance = (
                        raw_prov[0]
                        if raw_prov and isinstance(raw_prov[0], dict)
                        else {}
                    )
                elif isinstance(raw_prov, dict):
                    provenance = raw_prov
                else:
                    provenance = {}

                # Use a more descriptive name for national entities.
                # provenance may have an "entity_name" or "mda_name" from the
                # COB report; fall back to the lender field, then entity table.
                display_name = (
                    provenance.get("entity_name")
                    or provenance.get("mda_name")
                    or loan.lender
                    or entity_name
                )

                bills.append(
                    {
                        "entity_name": display_name,
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

            # Determine source info from provenance of first record.
            # provenance is JSONB and can be a dict OR a list of dicts —
            # the per-loan loop above normalizes it, but this summary
            # lookup didn't, so a list here raised "'list' object has no
            # attribute 'get'" and dumped the whole DB strategy into the
            # (much slower) live-extraction fallback on every request.
            raw_first = pending_loans[0].provenance
            if isinstance(raw_first, list):
                first_prov = raw_first[0] if raw_first and isinstance(raw_first[0], dict) else {}
            elif isinstance(raw_first, dict):
                first_prov = raw_first
            else:
                first_prov = {}
            source_url = first_prov.get("source_url", "https://cob.go.ke/publications/")

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
                "_meta": _response_meta(unit="kes", entity_scope="all"),
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
                "source_url": data.get("source_url", "https://cob.go.ke/publications/"),
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
        "source": "Controller of Budget (https://cob.go.ke/publications/pending-bills/)",
        "source_url": "https://cob.go.ke/publications/pending-bills/",
        "currency": "KES",
        "explanation": (
            "Pending bills data is not yet populated. Run the seeding "
            "pipeline: python -m seeding.cli seed --domain pending_bills. "
            "This will fetch data from COB reports at "
            "https://cob.go.ke/publications/pending-bills/"
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
                "https://cob.go.ke/publications/pending-bills/",
                "https://cob.go.ke/publications/national-government-budget-implementation-review-reports/",
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

        # Top counties by amount — batch-load entities to avoid N+1
        unique_eids = list({b.entity_id for b in bills if b.entity_id})
        entity_map: Dict[int, tuple] = {}
        if unique_eids:
            for eid, ename, etype in (
                db.query(DBEntity.id, DBEntity.canonical_name, DBEntity.type)
                .filter(DBEntity.id.in_(unique_eids))
                .all()
            ):
                entity_map[eid] = (ename, etype.value if etype else "unknown")

        county_totals: Dict[int, Dict[str, Any]] = {}
        for b in bills:
            eid = b.entity_id
            if eid not in county_totals:
                ename, etype = entity_map.get(eid, (f"Entity {eid}", "unknown"))
                county_totals[eid] = {
                    "county": ename,
                    "entity_id": eid,
                    "amount": 0,
                    "entity_type": etype,
                }
            county_totals[eid]["amount"] += float(b.amount or 0)

        # Get population for per_capita (best-effort)
        _pop_map = _get_population_map(db)
        top_counties = sorted(
            county_totals.values(), key=lambda x: x["amount"], reverse=True
        )[:15]
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

        # Trend by fiscal year (filter out unknown)
        trend_map: Dict[str, float] = {}
        for b in bills:
            fy = b.fiscal_year or ""
            if not fy or fy.lower() == "unknown":
                continue
            trend_map[fy] = trend_map.get(fy, 0) + float(b.amount or 0)
        trend = [{"year": k, "total_amount": v} for k, v in sorted(trend_map.items())]

        # Eligible / Ineligible totals
        eligible_total = sum(float(b.eligible_amount or 0) for b in bills)
        ineligible_total = sum(float(b.ineligible_amount or 0) for b in bills)

        return {
            "status": "success",
            "data_source": "pending_bills_table",
            "_meta": _response_meta(unit="kes", entity_scope="all"),
            "total_pending_amount": total_pending,
            "eligible_total": eligible_total,
            "ineligible_total": ineligible_total,
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
        entity_rows = (
            db.query(DBEntity.id, DBEntity.canonical_name)
            .filter(DBEntity.id.in_(unique_eids))
            .all()
        )
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

    top_counties = sorted(
        entity_totals.values(), key=lambda x: x["amount"], reverse=True
    )[:15]

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

    # Trend from provenance fiscal_year (filter out "unknown")
    trend_map: Dict[str, float] = {}
    for l in pending_loans:
        prov = l.provenance if isinstance(l.provenance, dict) else {}
        fy = prov.get("fiscal_year", "")
        if not fy or fy.lower() == "unknown":
            continue
        trend_map[fy] = trend_map.get(fy, 0) + float(l.outstanding or l.principal or 0)
    trend = [{"year": k, "total_amount": v} for k, v in sorted(trend_map.items())]

    # Eligible / Ineligible totals from provenance
    eligible_total = 0.0
    ineligible_total = 0.0
    for l in pending_loans:
        prov = l.provenance if isinstance(l.provenance, dict) else {}
        eligible_total += float(prov.get("eligible_pending") or 0)
        ineligible_total += float(prov.get("ineligible_pending") or 0)

    return {
        "status": "success",
        "data_source": "loans_table_fallback",
        "total_pending_amount": total,
        "eligible_total": eligible_total,
        "ineligible_total": ineligible_total,
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
            raise HTTPException(
                status_code=404, detail=f"County '{county_id}' not found"
            )

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
                "aging_buckets": {
                    "0-30d": 0,
                    "31-90d": 0,
                    "91-180d": 0,
                    "180d+": total,
                },
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


def _resolve_county_name(county_id: str, db: "Optional[Session]" = None) -> Optional[str]:
    """Resolve any ID shape to a short county name (e.g. "Mombasa").

    Endpoints that only need a name (to call downstream InternalAPIClient
    or build a canonical_name filter) use this helper. It tries the fast
    COUNTY_MAPPING dict first, then falls back to a quick DB lookup for
    raw row ids / slugs. Returns None if the id cannot be resolved.

    When called from within an endpoint that already holds an open
    ``with next(get_db())`` session, pass ``db=<that session>`` so we
    reuse it instead of opening (and leaking) a second connection.
    """
    if not county_id:
        return None

    # Fast path: direct COUNTY_MAPPING lookup (zero-padded codes)
    direct = COUNTY_MAPPING.get(county_id)
    if direct:
        return direct

    # Numeric shapes: try zero-padding to match COUNTY_MAPPING keys
    cid = str(county_id).strip()
    if cid.isdigit():
        padded = cid.zfill(3)
        if padded in COUNTY_MAPPING:
            return COUNTY_MAPPING[padded]

    # Fallback to DB for raw DB ids / slugs / names
    if not DATABASE_AVAILABLE:
        return None
    try:
        if db is not None:
            entity = _resolve_county_entity(db, county_id)
            if entity:
                name = (entity.canonical_name or "").replace(" County", "").strip()
                return name or None
            return None
        with next(get_db()) as _db:
            entity = _resolve_county_entity(_db, county_id)
            if entity:
                name = (entity.canonical_name or "").replace(" County", "").strip()
                return name or None
    except Exception as e:
        logging.warning(f"_resolve_county_name fallback failed for {county_id}: {e}")
    return None


def _resolve_county_entity(db: Session, county_id: str):
    """Resolve a county by numeric ID, zero-padded code, slug, or name.

    The codebase exposes three ID shapes for counties:
      * raw DB row id (``4``)
      * 3-digit county code (``001``..``047``) used in COUNTY_MAPPING
      * slug (``nairobi-county``) or short name (``Nairobi``)

    Different endpoints return different shapes, so we normalise here.
    """
    if not county_id:
        return None
    cid = str(county_id).strip()

    # 1. 3-digit county code via COUNTY_MAPPING (e.g. "047" → "Mombasa").
    #    Must precede the raw-DB-id branch: the /counties list endpoint
    #    returns these zero-padded codes as `id`, and if we treated "047"
    #    as DB row id=47 we'd resolve to a completely different county.
    code_candidate = cid.zfill(3) if cid.isdigit() else cid
    mapped = COUNTY_MAPPING.get(code_candidate) or COUNTY_MAPPING.get(cid)
    if mapped:
        entity = (
            db.query(DBEntity)
            .filter(
                DBEntity.type == EntityType.COUNTY,
                or_(
                    DBEntity.canonical_name == mapped,
                    DBEntity.canonical_name == f"{mapped} County",
                    DBEntity.slug == f"{mapped.lower().replace(' ', '-')}-county",
                ),
            )
            .first()
        )
        if entity:
            return entity

    # 2. Raw numeric DB id (falls through only when the code didn't match,
    #    so long-form ids like "123" for a non-county row still resolve).
    if cid.isdigit():
        entity = (
            db.query(DBEntity)
            .filter(DBEntity.id == int(cid), DBEntity.type == EntityType.COUNTY)
            .first()
        )
        if entity:
            return entity

    # 3. Slug
    entity = (
        db.query(DBEntity)
        .filter(DBEntity.slug == cid.lower(), DBEntity.type == EntityType.COUNTY)
        .first()
    )
    if entity:
        return entity

    # 4. 3-digit code via COUNTY_MAPPING → resolve to either
    #    "Nairobi" or "Nairobi County" in the DB
    code = cid.zfill(3) if cid.isdigit() else cid
    mapped = COUNTY_MAPPING.get(code) or COUNTY_MAPPING.get(cid)
    if mapped:
        entity = (
            db.query(DBEntity)
            .filter(
                DBEntity.type == EntityType.COUNTY,
                or_(
                    DBEntity.canonical_name == mapped,
                    DBEntity.canonical_name == f"{mapped} County",
                    DBEntity.slug == f"{mapped.lower().replace(' ', '-')}-county",
                ),
            )
            .first()
        )
        if entity:
            return entity

    # 4. Case-insensitive name match
    entity = (
        db.query(DBEntity)
        .filter(
            or_(
                DBEntity.canonical_name.ilike(cid),
                DBEntity.canonical_name.ilike(f"{cid} County"),
            ),
            DBEntity.type == EntityType.COUNTY,
        )
        .first()
    )
    return entity


# ── Debt — Broader (IMF General Government) ────────────────────────────


# Default KES/USD rate used to convert IMF's USD-denominated nominal GDP
# (`NGDPD`) into KES so we can display the debt figure in trillions of
# shillings. The actual rate fluctuates; callers who want tighter
# accuracy can override via env. This is documented in the response
# payload (`fx_rate_used`) so readers can reproduce the math.
IMF_BROADER_USD_KES = float(os.environ.get("IMF_BROADER_USD_KES", "130"))


@app.get("/api/v1/debt/broader")
async def get_debt_broader(db: Session = Depends(get_db)):
    """IMF's General-Government Gross Debt for Kenya.

    Companion to ``/api/v1/debt/national`` (which returns CBK's
    Central-Government figure). The two measures differ by ~400-600B
    KES — the gap is county-government debt, SOE guarantees, pension
    arrears, and pending bills that Treasury's headline number leaves
    out. The debt page renders both side-by-side so readers can see
    the gap and we can later surface its components (Phase 2).

    Returns a timeseries with each year's debt-to-GDP ratio and an
    absolute KES estimate derived from IMF's USD GDP projection times
    ``IMF_BROADER_USD_KES``. The last-fetched vintage is included so
    the frontend can mark the value "stale" when the seeder has not
    run recently.

    **Caching**: the "unavailable" branch is NOT cached, so the first
    hit after the seeder finishes will see fresh data without waiting
    for a TTL to expire. Successful payloads are cached 24h since IMF
    WEO only publishes twice a year.
    """
    if not DATABASE_AVAILABLE:
        return {"status": "unavailable", "reason": "database_not_configured"}

    from sqlalchemy import func  # local — main.py uses local imports for sqla

    from models import ImfWeoObservation  # local import — avoids circular

    # Latest vintage per indicator. IMF publishes new vintages twice a
    # year; within a vintage, the same year can have different values
    # across indicators, but we want the NEWEST snapshot we've seen.
    latest_vintage_subq = (
        db.query(func.max(ImfWeoObservation.vintage))
        .filter(ImfWeoObservation.country_code == "KEN")
        .scalar()
    )
    if latest_vintage_subq is None:
        # Seeder has never populated the table. Frontend hides the card.
        # Do NOT cache — otherwise the first seeder run leaves users
        # stuck with "unavailable" for up to 24h.
        return {"status": "unavailable", "reason": "not_seeded_yet"}
    # Pass vintage as kwarg so @cached bakes it into the key —
    # a new vintage invalidates the cache automatically.
    return await _get_debt_broader_cached(
        db=db, vintage=latest_vintage_subq.isoformat()
    )


@cached(key_prefix="debt:broader", ttl=86400)  # IMF WEO updates twice a year
async def _get_debt_broader_cached(db: Session, vintage: str):
    from models import ImfWeoObservation  # local — avoids circular import

    latest_vintage_subq = datetime.datetime.fromisoformat(vintage)

    rows = (
        db.query(ImfWeoObservation)
        .filter(
            ImfWeoObservation.country_code == "KEN",
            ImfWeoObservation.vintage == latest_vintage_subq,
        )
        .order_by(
            ImfWeoObservation.indicator, ImfWeoObservation.year
        )
        .all()
    )

    by_indicator: Dict[str, Dict[int, Any]] = {}
    for row in rows:
        bucket = by_indicator.setdefault(row.indicator, {})
        bucket[row.year] = {
            "value": float(row.value) if row.value is not None else None,
            "is_projection": row.is_projection,
        }

    debt_pct = by_indicator.get("GGXWDG_NGDP", {})
    gdp_usd = by_indicator.get("NGDPD", {})  # billions USD

    fx = IMF_BROADER_USD_KES
    timeseries = []
    for year in sorted(set(debt_pct.keys()) | set(gdp_usd.keys())):
        pct = debt_pct.get(year, {}).get("value")
        gdp_b = gdp_usd.get(year, {}).get("value")
        value_kes: float | None = None
        gdp_kes: float | None = None
        if pct is not None and gdp_b is not None:
            # NGDPD is in USD billions → KES absolute
            gdp_kes = gdp_b * 1e9 * fx
            value_kes = gdp_kes * (pct / 100.0)
        timeseries.append(
            {
                "year": year,
                "debt_to_gdp": pct,
                "gdp_kes": gdp_kes,
                "value_kes": value_kes,
                "is_projection": debt_pct.get(year, {}).get("is_projection", False),
            }
        )

    # "Latest" = most recent ACTUAL (non-projection) year that has both
    # debt% and GDP. The timeseries includes IMF forecasts out to 2030;
    # picking the furthest year would show a 5-6 year projection as the
    # "current" figure, which overstates debt (debt and USD GDP both
    # grow over time) and confuses readers comparing against CBK's
    # "as-of-today" total. Fall back to the latest projection only when
    # no non-projection rows exist (i.e. a very old vintage or brand-new
    # country with only forecasts available).
    complete = [t for t in timeseries if t["value_kes"] is not None]
    actuals = [t for t in complete if not t.get("is_projection")]
    latest = (actuals or complete)[-1] if complete else None

    # Stale = vintage > 60 days old. IMF WEO publishes twice a year
    # (April/October) — 60 days after either release is a reasonable
    # "something is probably wrong" threshold.
    age_days = (
        datetime.datetime.now(datetime.timezone.utc) - latest_vintage_subq
    ).days
    stale = age_days > 60

    return {
        "status": "success",
        "source": {
            "name": "IMF World Economic Outlook",
            "indicator": "General Government Gross Debt",
            "code": "GGXWDG",
            "dataset_url": "https://www.imf.org/external/datamapper/GGXWDG_NGDP@WEO/KEN",
        },
        "latest": latest,
        "timeseries": timeseries,
        "fx_rate_used": fx,
        "vintage": latest_vintage_subq.isoformat(),
        "vintage_age_days": age_days,
        "stale": stale,
        "as_of": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


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
        latest_dt = db.query(DebtTimeline).order_by(DebtTimeline.year.desc()).first()
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
                    "status": (
                        "above"
                        if ratio_val > 30
                        else ("warning" if ratio_val > 25 else "below")
                    ),
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
            kenya_ratio=(
                float(latest_dt.gdp_ratio)
                if latest_dt and latest_dt.gdp_ratio
                else None
            )
        )

        return {
            "status": "success",
            "_meta": _response_meta(unit="percentage", entity_scope="national"),
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

    # Fetch only the last 5 data points directly from DB (not all rows)
    recent = (
        db.query(DebtTimeline)
        .filter(DebtTimeline.gdp_ratio.isnot(None))
        .order_by(DebtTimeline.year.desc())
        .limit(5)
        .all()
    )
    if len(recent) < 2:
        return []

    # Reverse so oldest-first for the linear fit
    recent = list(reversed(recent))
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
    """Return EAC regional debt comparison with multiple indicators.

    Fetches three indicators from World Bank + IMF APIs (cached 12 hours):
      - Debt-to-GDP (%)
      - Debt service to revenue (%)
      - External debt share (%)

    Falls back to verified static values when APIs are unreachable.
    """
    return _get_regional_peers_cached(kenya_ratio)


# ── EAC peer data with multi-indicator support ────────────────────
_EAC_COUNTRIES = {
    "KEN": "Kenya",
    "ETH": "Ethiopia",
    "TZA": "Tanzania",
    "UGA": "Uganda",
    "RWA": "Rwanda",
}

# World Bank indicator codes
_WB_INDICATORS = {
    "debt_to_gdp": "GC.DOD.TOTL.GD.ZS",  # Central govt debt (% GDP)
    "debt_service_to_revenue": "GC.XPN.INTP.RV.ZS",  # Interest payments (% revenue)
    "external_debt_pct": "DT.DOD.DECT.GN.ZS",  # External debt stocks (% GNI)
}

# IMF DataMapper indicator codes (WEO dataset)
_IMF_INDICATORS = {
    "debt_to_gdp": "GGXWDG_NGDP",  # General govt gross debt (% GDP)
}

# Simple TTL cache: (timestamp, data)
_peers_cache: Dict[str, Any] = {"ts": 0.0, "data": None}
_PEERS_CACHE_TTL = 12 * 3600  # 12 hours

_logger_peers = logging.getLogger("audit_app.regional_peers")


def _wb_fetch_indicator(indicator_code: str, country_codes: str) -> Dict[str, float]:
    """Fetch latest value per country for a single World Bank indicator.

    Returns {ISO3: value} for countries that have data.
    """
    url = (
        f"https://api.worldbank.org/v2/country/{country_codes}"
        f"/indicator/{indicator_code}?format=json&per_page=100&date=2015:2026"
    )
    resp = httpx.get(url, timeout=8)
    resp.raise_for_status()
    wb_data = resp.json()

    if not isinstance(wb_data, list) or len(wb_data) < 2 or not wb_data[1]:
        return {}

    # Keep the most recent non-null value per country
    latest: Dict[str, Dict[str, Any]] = {}
    for item in wb_data[1]:
        if item.get("value") is not None:
            iso = item["countryiso3code"]
            year = int(item["date"])
            if iso not in latest or year > latest[iso]["year"]:
                latest[iso] = {"year": year, "value": float(item["value"])}

    return {iso: d["value"] for iso, d in latest.items()}


def _imf_fetch_debt_to_gdp() -> Dict[str, float]:
    """Fetch debt-to-GDP from the IMF DataMapper API (WEO dataset).

    Endpoint: /api/v1/GGXWDG_NGDP/{countries}?periods=2020,2021,...,2026
    Returns {ISO3: value} for countries that have data.
    """
    countries = "/".join(_EAC_COUNTRIES.keys())
    periods = ",".join(str(y) for y in range(2018, 2027))
    url = (
        f"https://www.imf.org/external/datamapper/api/v1"
        f"/GGXWDG_NGDP/{countries}?periods={periods}"
    )
    resp = httpx.get(url, timeout=8)
    resp.raise_for_status()
    data = resp.json()

    # IMF response: {"values": {"GGXWDG_NGDP": {"KEN": {"2023": 68.1, ...}, ...}}}
    indicator_data = data.get("values", {}).get("GGXWDG_NGDP", {})
    result: Dict[str, float] = {}
    for iso, year_vals in indicator_data.items():
        if not year_vals:
            continue
        # Get the most recent year with a value
        latest_year = max(year_vals.keys())
        val = year_vals[latest_year]
        if val is not None:
            result[iso] = round(float(val), 1)

    return result


def _get_regional_peers_cached(kenya_ratio: Optional[float] = None) -> list:
    """Fetch EAC peers from World Bank + IMF APIs with 12-hour TTL cache."""
    now = time.time()

    # Check cache
    if (
        _peers_cache["data"] is not None
        and (now - _peers_cache["ts"]) < _PEERS_CACHE_TTL
    ):
        cached = [dict(p) for p in _peers_cache["data"]]  # shallow copy
        if kenya_ratio is not None:
            for p in cached:
                if p["country"] == "Kenya":
                    p["debt_to_gdp"] = round(kenya_ratio, 1)
        return cached

    # ── Fetch all indicators ──────────────────────────────────────
    codes_str = ";".join(_EAC_COUNTRIES.keys())
    debt_gdp: Dict[str, float] = {}
    service_rev: Dict[str, float] = {}
    external_pct: Dict[str, float] = {}

    # 1. Try IMF for debt-to-GDP (often more current than World Bank)
    try:
        debt_gdp = _imf_fetch_debt_to_gdp()
        _logger_peers.info("IMF debt-to-GDP: got data for %d countries", len(debt_gdp))
    except Exception as exc:
        _logger_peers.debug("IMF API unavailable: %s", exc)

    # 2. World Bank: debt-to-GDP (fallback if IMF missed countries)
    try:
        wb_debt_gdp = _wb_fetch_indicator(_WB_INDICATORS["debt_to_gdp"], codes_str)
        for iso, val in wb_debt_gdp.items():
            if iso not in debt_gdp:
                debt_gdp[iso] = round(val, 1)
        _logger_peers.info(
            "WB debt-to-GDP: got data for %d countries", len(wb_debt_gdp)
        )
    except Exception as exc:
        _logger_peers.debug("WB debt-to-GDP unavailable: %s", exc)

    # 3. World Bank: debt service to revenue
    try:
        service_rev = _wb_fetch_indicator(
            _WB_INDICATORS["debt_service_to_revenue"], codes_str
        )
        _logger_peers.info(
            "WB debt-service/revenue: got data for %d countries", len(service_rev)
        )
    except Exception as exc:
        _logger_peers.debug("WB debt-service/revenue unavailable: %s", exc)

    # 4. World Bank: external debt as % of GNI
    try:
        external_pct = _wb_fetch_indicator(
            _WB_INDICATORS["external_debt_pct"], codes_str
        )
        _logger_peers.info(
            "WB external-debt%%: got data for %d countries", len(external_pct)
        )
    except Exception as exc:
        _logger_peers.debug("WB external-debt%% unavailable: %s", exc)

    # ── Verified fallback values (updated Mar 2026) ───────────────
    # Used ONLY when both APIs are unreachable for a given indicator.
    _fallback = {
        "KEN": {
            "debt_to_gdp": 68.0,
            "debt_service_to_revenue": 57.6,
            "external_debt_share": 52.3,
        },
        "ETH": {
            "debt_to_gdp": 31.4,
            "debt_service_to_revenue": 22.8,
            "external_debt_share": 58.1,
        },
        "TZA": {
            "debt_to_gdp": 48.2,
            "debt_service_to_revenue": 15.3,
            "external_debt_share": 61.5,
        },
        "UGA": {
            "debt_to_gdp": 53.1,
            "debt_service_to_revenue": 19.7,
            "external_debt_share": 55.8,
        },
        "RWA": {
            "debt_to_gdp": 67.2,
            "debt_service_to_revenue": 13.5,
            "external_debt_share": 68.4,
        },
    }

    # ── Assemble peers ────────────────────────────────────────────
    peers = []
    for iso, name in _EAC_COUNTRIES.items():
        fb = _fallback.get(iso, {})

        # Debt-to-GDP: Kenya uses our CBK data; others prefer IMF/WB then fallback
        if iso == "KEN" and kenya_ratio is not None:
            d2g = kenya_ratio
        else:
            d2g = debt_gdp.get(iso) or fb.get("debt_to_gdp")

        # Debt service to revenue
        dsr = service_rev.get(iso) or fb.get("debt_service_to_revenue")

        # External debt share
        ext = external_pct.get(iso) or fb.get("external_debt_share")

        peers.append(
            {
                "country": name,
                "debt_to_gdp": round(d2g, 1) if d2g else None,
                "debt_service_to_revenue": round(dsr, 1) if dsr else None,
                "external_debt_share": round(ext, 1) if ext else None,
            }
        )

    _peers_cache["ts"] = now
    _peers_cache["data"] = peers
    _logger_peers.info(
        "Regional peers updated: %d/%d countries have full data",
        sum(
            1
            for p in peers
            if all(v is not None for k, v in p.items() if k != "country")
        ),
        len(peers),
    )
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
                .filter(publishable_audit_criterion())
                .filter(DBAudit.entity_id == entity.id)
                .scalar()
                or 0
            )

            entity_type_value = (
                entity.type.value if hasattr(entity.type, "value") else entity.type
            )

            fy_metrics = _resolve_fy_metrics(entity.meta or {})
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
        # Return empty list on database error — never serve hardcoded data
        return []


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
            .filter(publishable_audit_criterion())
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
        fy_metrics = _resolve_fy_metrics(e.meta or {})
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
    _db_unreachable = False
    # Try real DB data first
    if DATABASE_AVAILABLE:
        try:
            from models import EntityType as _ET
            from sqlalchemy import func as _fn

            with next(get_db()) as db:
                _nat = db.query(DBEntity).filter(DBEntity.type == _ET.NATIONAL).first()
                if _nat:
                    # Exclude PENDING_BILLS — see ``_is_debt_loan``.
                    loans = _debt_loans_query(db, DBLoan.entity_id == _nat.id).all()
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
                            "_meta": _response_meta(
                                unit="percentage", entity_scope="national"
                            ),
                        }
        except Exception as e:
            logging.error(f"DB debt-mix query failed: {e}")
            _db_unreachable = True

    # Absent is not zero — see /api/v1/debt/national. A 0/0 external/domestic
    # split is a readable, plausible-looking claim about the composition of
    # public debt; nulls cannot be mistaken for one.
    _reason = "source_unavailable" if _db_unreachable else "not_yet_seeded"
    logging.warning("/dashboards/national/debt-mix returning no figures — reason=%s", _reason)
    return {
        "external": None,
        "domestic": None,
        "external_amount": None,
        "domestic_amount": None,
        "total": None,
        "currency": "KES",
        "data_source": (
            "database_unavailable" if _db_unreachable else "database_empty"
        ),
        "reason": _reason,
        "message": (
            "Debt composition is unavailable because the data source could "
            "not be read. This is not a finding that debt is zero."
            if _db_unreachable
            else "No debt data in database. "
            "Run: python -m seeding.cli seed --domain national_debt"
        ),
    }


@app.get("/api/v1/dashboards/national/fiscal-outturns")
async def dashboard_fiscal_outturns():
    """National fiscal outturns per fiscal year.

    Uses the FiscalSummary table (national-scope by design) to avoid
    mixing county and national BudgetLine data.
    """
    # Try DB data first — use FiscalSummary (national-scope, has real revenue/expenditure)
    if DATABASE_AVAILABLE:
        try:
            from models import FiscalSummary as FSModel

            with next(get_db()) as db:
                rows = (
                    db.query(FSModel)
                    .order_by(FSModel.fiscal_year.desc())
                    .limit(12)
                    .all()
                )
                if rows:
                    series = []
                    for r in rows:
                        # fiscal_summaries stores raw KES (stage1 3a);
                        # this endpoint's declared unit is billion_kes,
                        # so convert here to keep the label truthful.
                        rev = float(r.total_revenue or 0) / 1e9
                        # expenditure = recurrent + development if available
                        recurrent = float(r.recurrent_spending or 0) / 1e9
                        development = float(r.development_spending or 0) / 1e9
                        expenditure = (
                            (recurrent + development)
                            if (recurrent + development) > 0
                            else 0
                        )
                        # Skip years with no revenue AND no expenditure (incomplete backfill)
                        if rev == 0 or expenditure == 0:
                            continue
                        series.append(
                            {
                                "period": str(r.fiscal_year),
                                "revenue": rev,
                                "expenditure": expenditure,
                                "balance": rev - expenditure,
                            }
                        )
                    series = series[:8]  # cap to 8 most recent complete years
                    if series:
                        return {
                            "series": series,
                            "data_source": "database",
                            "unit": "billion_kes",
                            "_meta": _response_meta(
                                unit="billion_kes", entity_scope="national"
                            ),
                        }
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
                "period": f"{get_current_fiscal_year()} Q1",
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
                # Scope to latest national FY; fall back to county if no national data.
                # Also filter by entity type to avoid mixing county + national categories.
                _nat_pid = _latest_national_period(db)
                _pid = _nat_pid or _latest_county_period(db)
                _entity_type = EntityType.NATIONAL if _nat_pid else EntityType.COUNTY
                q = (
                    db.query(
                        DBBudgetLine.category,
                        _fn.sum(DBBudgetLine.allocated_amount).label("allocated"),
                    )
                    .join(DBEntity, DBBudgetLine.entity_id == DBEntity.id)
                    .filter(
                        DBBudgetLine.category != "Total Budget",
                        DBEntity.type == _entity_type,
                    )
                )
                if _pid:
                    q = q.filter(DBBudgetLine.period_id == _pid)
                rows = q.group_by(DBBudgetLine.category).all()
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
                    allocation["_meta"] = _response_meta(
                        unit="percentage",
                        entity_scope="national" if _nat_pid else "county",
                    )
                    # Plausibility: total_amount is raw KES
                    _check_plausibility(
                        total, _MAX_NATIONAL_BUDGET_KES, "sector-ceilings total_amount"
                    )
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

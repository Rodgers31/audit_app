import asyncio
import concurrent.futures
import contextlib
import datetime
import functools
import importlib
import json
import logging
import math
import os
import random
import re
import smtplib
import sys
import threading
import time
from decimal import Decimal
from email.mime.text import MIMEText
from email.utils import formatdate
from typing import Any, Dict, List, Optional, Tuple

import httpx
import uvicorn
from config.settings import settings
from services.audit_derived import derive_unaccounted_cases
from services.imf_dsa import kenya_dsa_rating
from services.publication_gate import (
    count_withheld_audits,
    count_withheld_by_reason,
    county_debt_instrument_failure,
    county_pending_bills,
    county_pending_bills_details,
    select_county_pending_bills,
    county_pending_reporting_date,
    county_loans_at_reporting_date,
    pending_budget_compatible,
    county_pending_bills_row_is_published,
    pending_bills_row_as_at,
    pending_bills_row_amount,
    pending_bills_row_is_published,
    file_source_provenance_failure,
    loan_is_modelled_fixture,
    log_withheld_audits,
    publishable_audit_criterion,
)
from seeding.source_registry import next_expected_window
from services.stalled_projects import (
    build_stalled_projects_block,
    stalled_oag_findings,
)
from services.county_budget import (
    REVENUE_RECEIPTS_CATEGORY,
    REVENUE_RECEIPTS_TOTAL,
    county_cash_refusal,
)
from services.audit_citations import audited_institution, citation_page, extraction_payload, report_page_url
from services.audit_derived import derive_federal_headline, derive_unaccounted_cases
from services.trust_guards import (
    check_budget_sectors,
    check_coverage_staleness,
    check_debt_composition,
    check_period_nonempty,
    check_plausible_total,
    reconcile_debt_totals,
)
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, field_validator
from services.entity_publication import public_entity_metadata
from sqlalchemy import or_, text
from sqlalchemy.exc import SQLAlchemyError
from services.county_financial_health import county_audit_signals
from sqlalchemy.orm import Session, joinedload
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
# httpx INFO records include full URLs, including query strings. Request
# summaries below emit bounded route templates instead.
logging.getLogger("httpx").setLevel(logging.WARNING)

try:
    import boto3  # type: ignore
except Exception:
    boto3 = None  # type: ignore

# Import Redis cache
from cache.redis_cache import cached as response_cached

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
    all_metrics = public_entity_metadata(meta).get("metrics", {})
    if not isinstance(all_metrics, dict):
        return {}
    key = _fy_metrics_key(fiscal_year)
    result = all_metrics.get(key)
    if isinstance(result, dict) and result:
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


def _latest_county_period(db, *, official_counties_only=False) -> Optional[int]:
    """Return the period_id of the latest FiscalPeriod that has county BudgetLines.

    This ensures sector/budget queries are scoped to a single fiscal year and
    only include county-level data — never national budget lines or aggregate rows.
    The overview requests the same Kenyan official-county scope as its totals.
    Returns None if no county budget lines exist.
    """
    query = (
        db.query(DBBudgetLine.period_id)
        .join(DBEntity, DBBudgetLine.entity_id == DBEntity.id)
        .join(DBFiscalPeriod, DBBudgetLine.period_id == DBFiscalPeriod.id)
        .filter(DBEntity.type == EntityType.COUNTY)
        .filter(DBBudgetLine.category != "Total Budget")
        # A full year and its part-year report ("FY2025/26" and "FY2025/26
        # 9M") share a start date. Ordering on start_date alone left the
        # choice to the planner; the later end date — the full year — wins.
        .order_by(
            DBFiscalPeriod.start_date.desc(),
            DBFiscalPeriod.end_date.desc(),
            DBFiscalPeriod.id.desc(),
        )
    )
    if official_counties_only:
        query = query.join(DBCountry, DBEntity.country_id == DBCountry.id).filter(DBCountry.iso_code == "KEN")
        rows = query.with_entities(DBBudgetLine.period_id, DBEntity.canonical_name).all()
        return next((period_id for period_id, name in rows if official_county_code(name)), None)
    row = query.limit(1).first()
    return row[0] if row else None


def _county_period_rollup(db, period_id: Optional[int], *, reject_incomplete=False):
    """Every county's budget in one period, each through the shared split rule.

    Returns ``(per_county, sector_lines)``: ``per_county`` maps entity id to
    ``(canonical_name, allocated, spent)``, and ``sector_lines`` are the
    additive sector rows across all counties.

    The overview opts into refusal of incomplete/invalid consumed amounts;
    a successful complete aggregate cannot silently substitute missing money.

    ``/budget/overview`` and ``/countries/{id}/summary`` summed every county
    row in the period except the literal category "Total Budget". A period
    holding the Controller of Budget's CBIRR aggregates carries Total,
    Recurrent, Development and Own Source Revenue side by side — one budget
    described three ways plus the county's own revenue — so that sum was
    633.30 + 398.97 + 234.33 + 100.13 = KSh 1,366.7B against a published
    633.30B. Going through ``split_classification_and_sector_lines`` per
    county is the rule ``GET /counties`` and money-flow already use, so all
    three now publish the same total for the same period.
    """
    if not period_id:
        # No period is not "every period": summed across years, one county
        # would carry several budgets as one.
        return {}, []
    q = (
        db.query(DBBudgetLine, DBEntity.canonical_name)
        .join(DBEntity, DBBudgetLine.entity_id == DBEntity.id)
        .filter(DBEntity.type == EntityType.COUNTY)
        .filter(DBBudgetLine.period_id == period_id)
    )
    if reject_incomplete:
        q = q.join(DBCountry, DBEntity.country_id == DBCountry.id).filter(DBCountry.iso_code == "KEN")
    lines_by_entity: Dict[int, List[Any]] = {}
    names: Dict[int, str] = {}
    for line, name in q.all():
        if reject_incomplete:
            if official_county_code(name) is None:
                continue
            category = (line.category or "").strip().lower()
            consumed = category not in _NON_SECTOR_CATEGORIES and not (
                category in _CLASSIFICATION_CATEGORIES and line.subcategory
            )
            if consumed:
                for field in ("allocated_amount", "actual_spent"):
                    value = getattr(line, field)
                    try:
                        number = float(value) if value is not None and not isinstance(value, bool) else None
                    except (TypeError, ValueError, OverflowError):
                        number = None
                    if number is None or not math.isfinite(number) or number < 0:
                        raise HTTPException(status_code=503, detail={
                            "reason": "incomplete_or_invalid_county_amount",
                            "entity_id": line.entity_id,
                            "field": field,
                        })
        lines_by_entity.setdefault(line.entity_id, []).append(line)
        names[line.entity_id] = name
    per_county: Dict[int, Tuple[str, float, float]] = {}
    sector_lines: List[Any] = []
    for entity_id, lines in lines_by_entity.items():
        allocated, spent, sectors, _cls = _split_classification_and_sector_lines(lines)
        per_county[entity_id] = (names[entity_id], allocated, spent)
        sector_lines.extend(sectors)
    return per_county, sector_lines


def _latest_national_period(db) -> Optional[int]:
    """Return the period_id of the latest FiscalPeriod that has national BudgetLines."""
    row = (
        db.query(DBBudgetLine.period_id)
        .join(DBEntity, DBBudgetLine.entity_id == DBEntity.id)
        .join(DBFiscalPeriod, DBBudgetLine.period_id == DBFiscalPeriod.id)
        .filter(DBEntity.type == EntityType.NATIONAL)
        .order_by(
            DBFiscalPeriod.start_date.desc(),
            DBFiscalPeriod.end_date.desc().nullslast(),
            DBFiscalPeriod.id.desc(),
        )
        .limit(1)
        .first()
    )
    return row[0] if row else None


def _is_undefined_table(exc: Exception) -> bool:
    """True only for "relation/table does not exist".

    Postgres raises SQLSTATE 42P01 (psycopg2 exposes it as ``pgcode``); SQLite
    raises ``OperationalError: no such table: ...``. Anything else — a dropped
    connection, a timeout, a permission error — is a real failure and must not
    be reported to the caller as "run the migration".
    """
    orig = getattr(exc, "orig", None)
    if getattr(orig, "pgcode", None) == "42P01":
        return True
    text = str(orig or exc).lower()
    return "no such table" in text or "does not exist" in text


#: How many individual lenders each debt category returns before the rest are
#: folded into an explicit remainder. Matches the treemap's own fold (NAMED).
_CATEGORY_NAMED_LENDERS = 8


def _category_items_with_remainder(data: dict) -> dict:
    """The largest lenders in a category, plus an explicit remainder.

    Returning an arbitrary five of them left the caller unable to tell a
    complete list from a truncated one, so shares computed over `items` did not
    sum to `total_outstanding`. The remainder makes the gap explicit and
    quantified instead.
    """
    items = sorted(
        data.get("items") or [],
        key=lambda i: float(i.get("outstanding") or i.get("principal") or 0),
        reverse=True,
    )
    named = items[: _CATEGORY_NAMED_LENDERS]
    rest = items[_CATEGORY_NAMED_LENDERS :]
    return {
        "items": named,
        "items_truncated": bool(rest),
        "other_lender_count": len(rest),
        "other_principal": sum(float(i.get("principal") or 0) for i in rest),
        "other_outstanding": sum(float(i.get("outstanding") or 0) for i in rest),
    }


def _category_share_of_total(data: dict, total_outstanding: float) -> dict:
    """A category's share of the published debt total — or why there isn't one.

    ``total_outstanding`` excludes ``PENDING_BILLS`` (:func:`_is_debt_loan`),
    because arrears are not borrowed money. Dividing every category by it
    regardless handed ``pending_bills`` a 7.86% share of a total it is not in,
    so production's shares summed to **107.86%** and every share on the page
    was wrong by that factor against the whole a reader adds them to.

    Numerator is ``outstanding_in_total`` — the part of the category the
    denominator actually contains — so the published shares sum to 100 by
    construction. A category with nothing in the denominator gets ``None`` and
    a reason, the shape ``/budget/national`` uses for
    ``budget_split_absent_reason``. ``0`` would say the category is empty; the
    ``total_principal`` beside it says otherwise.
    """
    if total_outstanding <= 0:
        return {
            "percentage_of_total": None,
            "percentage_absent_reason": "no_published_total_to_divide_by",
        }
    if not data.get("rows_in_total"):
        return {
            "percentage_of_total": None,
            "percentage_absent_reason": (
                "category_excluded_from_total_debt_denominator"
            ),
        }
    return {
        "percentage_of_total": round(
            data["outstanding_in_total"] / total_outstanding * 100, 2
        ),
        "percentage_absent_reason": None,
    }


#: Response-cache TTL for endpoints whose data is refreshed by the nightly
#: seed.
#:
#: These were 12-24 hours. The seeder writes the database in one process and
#: the API reads it in another, so nothing invalidates the response cache when
#: a seed lands: a nightly run that corrected every fiscal year stayed
#: invisible for a further day. The site's own header says "updated nightly
#: from official sources", and a TTL longer than the refresh cadence makes that
#: false for most of the day.
#:
#: One hour still absorbs the traffic these queries are cached for, while
#: bounding how long a corrected figure can remain hidden.
NIGHTLY_REFRESH_TTL = 3600


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


def county_debt_total(loans) -> Optional[float]:
    """Selected instruments' outstanding balances; incomplete accounts are absent."""
    from services.financial_publication import county_debt_summary

    return county_debt_summary(loans)["total_debt"]


#: The category the CBIRR own-source revenue rows are written under.
OWN_SOURCE_REVENUE_CATEGORY = "own source revenue"


def _revenue_amount(value):
    from decimal import Decimal
    import math

    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


def _county_own_source_summary(budget_lines) -> Optional[float]:
    """The summary's 'Actual Realised' measure, not necessarily cash."""
    rows = [
        line
        for line in budget_lines or []
        if (line.category or "").strip().lower() == OWN_SOURCE_REVENUE_CATEGORY
    ]
    return _revenue_amount(rows[0].actual_spent) if len(rows) == 1 else None


def county_own_source_revenue(budget_lines) -> Optional[float]:
    """Cash receipts where the chapter states them; keep the basis in the block."""
    return _county_revenue_for_lines(budget_lines)["local_revenue"]


def county_own_source_target(budget_lines) -> Optional[float]:
    """The target from the same table and streams as the published amount."""
    return _county_revenue_for_lines(budget_lines)["own_source_target"]


def _county_revenue_for_lines(budget_lines):
    cash = [
        line
        for line in budget_lines or []
        if line.category == REVENUE_RECEIPTS_CATEGORY
    ]
    summaries = [
        line
        for line in budget_lines or []
        if (line.category or "").strip().lower() == OWN_SOURCE_REVENUE_CATEGORY
    ]

    def context(line):
        return tuple(
            getattr(line, key, None)
            for key in ("entity_id", "period_id", "currency", "source_document_id")
        )

    reason = None
    if cash and (
        len({context(line) for line in cash}) != 1
        or len({line.subcategory for line in cash}) != len(cash)
    ):
        reason = "ambiguous_revenue_receipt_rows"
    # Cash sets the publication period. A summary from another document or
    # period cannot be presented as a disagreement within that same report.
    comparable = [
        line for line in summaries if not cash or context(line) == context(cash[0])
    ]
    if len(comparable) != 1:
        comparable = []
    publication_rows = cash if cash else comparable
    period = getattr(publication_rows[0], "period", None) if publication_rows else None
    block = county_revenue_block(
        None if reason else county_revenue_receipts(cash),
        local_revenue=_county_own_source_summary(comparable),
        own_source_target=_county_own_source_target_summary(comparable),
        fiscal_year=period.label if period else None,
    )
    if reason:
        block["total_revenue_absent_reason"] = reason
    # Refused chapters have no cash rows. Their named reason is retained on
    # the budget Total; never use it to replace a current cash validation error
    # or attach it to a summary from another period/document.
    refusal = county_cash_refusal(budget_lines) if not cash else None
    block["total_revenue_absence_source"] = None
    if refusal and (not comparable or context(comparable[0]) == refusal["context"]):
        block["total_revenue_absent_reason"] = refusal["reason"]
        block["total_revenue_absence_source"] = refusal["source"]
        block["fiscal_year"] = refusal["fiscal_year"]
    block["sources"] = [
        {
            "id": getattr(line, "source_document_id", None),
            "url": getattr(getattr(line, "source_document", None), "url", None),
            "page_ref": getattr(line, "page_ref", None),
            "measure": "cash_receipts"
            if line.category == REVENUE_RECEIPTS_CATEGORY
            else "summary_table_actual_realised",
        }
        for line in [*(cash if not reason else []), *comparable]
        if line.category != REVENUE_RECEIPTS_CATEGORY
        or line.subcategory == REVENUE_RECEIPTS_TOTAL
    ]
    return block


def county_revenue_receipts(budget_lines) -> Optional[Dict[str, Dict[str, float]]]:
    """``{stream: {"target", "actual"}}`` from the CBIRR revenue table, or None.

    Only counties whose Chapter 3 "Revenue Performance" table reconciled to its
    own Grand Total have these rows at all (``seeding.pdf_parsers
    .county_revenue_receipts``), so the presence of ``"Total"`` is the proof
    that the streams add up to it. None without it: a county with a partial
    set of streams is not a county with a smaller revenue.
    """
    out: Dict[str, Dict[str, float]] = {}
    for line in budget_lines or []:
        if (line.category or "") != REVENUE_RECEIPTS_CATEGORY or not line.subcategory:
            continue
        out[line.subcategory] = {
            "target": _revenue_amount(line.allocated_amount),
            "actual": _revenue_amount(line.actual_spent),
        }
    return out if REVENUE_RECEIPTS_TOTAL in out else None


#: The order the CBIRR prints its revenue streams in.
_REVENUE_STREAM_ORDER = (
    "Balance Brought Forward",
    "Equitable Share",
    "Equalisation Fund",
    "Additional Allocations",
    "Own Source Revenue",
    "Facility Improvement Financing",
    "Appropriations in Aid",
    "Other Revenue",
)


#: The revenue streams that are own-source revenue in the CBIRR's county
#: tables — what Table 2.1 reports as "Total OSR" (ordinary + FIF/AiA).
_OWN_SOURCE_STREAMS = (
    "Own Source Revenue",
    "Facility Improvement Financing",
    "Appropriations in Aid",
)
#: The parser's own reconciliation tolerance (seeding.pdf_parsers
#: ._REVENUE_TOLERANCE_KES), re-checked on the rows as stored.
_REVENUE_STREAMS_TOLERANCE = 1000

#: Flag a material difference between independently labelled measures.
#: Agreement is not evidence that both tables use the same accounting basis.
_OWN_SOURCE_AGREEMENT = 0.01


def county_revenue_block(
    receipts: Optional[Dict[str, Dict[str, float]]],
    *,
    local_revenue: Optional[float],
    own_source_target: Optional[float],
    fiscal_year: Optional[str],
) -> Dict[str, Any]:
    """Publish reconciled cash receipts and retain the summary measure.

    The chapter's Grand Total includes the opening balance. Its own-source
    components and targets share that table's basis. A differing summary
    measure is disclosed separately, never added to these cash streams.
    """
    # Table 2.1's "FIF/AiA" column carries a county's A-i-A stream for some
    # counties and not others (Nairobi's is FIF alone: 9,440.57M ordinary +
    # 1,348.85M FIF = its 10,789.42M exactly, with the 206.51M liquor A-i-A
    # left out), so agreement with or without that stream counts.
    import math

    def _figure(v) -> bool:
        return (
            isinstance(v, (int, float))
            and not isinstance(v, bool)
            and math.isfinite(v)
            and v >= 0
        )

    local_revenue = local_revenue if _figure(local_revenue) else None
    own_source_target = own_source_target if _figure(own_source_target) else None
    # Missing cells are absent; a printed, reconciled zero remains zero.
    withheld_reason = None
    if receipts:
        if not isinstance(receipts, dict) or not all(
            isinstance(v, dict) for v in receipts.values()
        ):
            receipts, withheld_reason = None, "invalid_revenue_rows"
    if receipts:
        total = receipts.get(REVENUE_RECEIPTS_TOTAL, {}).get("actual")
        streams_actual = [
            v.get("actual") for k, v in receipts.items() if k != REVENUE_RECEIPTS_TOTAL
        ]
        if (
            not _figure(total)
            or total < 0
            or not streams_actual
            or not all(_figure(v) for v in streams_actual)
            or abs(sum(streams_actual) - total) > _REVENUE_STREAMS_TOLERANCE
        ):
            receipts, withheld_reason = None, "cbirr_revenue_streams_do_not_sum_to_total"

    disagreement = None
    if receipts and local_revenue is not None:
        def _sum(names) -> float:
            return sum(receipts[n]["actual"] for n in names if n in receipts)

        with_aia = _sum(_OWN_SOURCE_STREAMS)
        without_aia = _sum(_OWN_SOURCE_STREAMS[:2])
        tolerance = max(abs(local_revenue) * _OWN_SOURCE_AGREEMENT, 1_000_000)
        if all(abs(c - local_revenue) > tolerance for c in (with_aia, without_aia)):
            disagreement = {
                "summary_table": local_revenue,
                "county_revenue_table": with_aia,
            }
            # The chapter explicitly labels cash receipts. Preserve those
            # supported amounts and disclose the competing summary measure.

    summary_own_source = local_revenue
    summary_own_source_target = own_source_target
    if receipts:
        own_streams = [
            receipts[name]["actual"] for name in _OWN_SOURCE_STREAMS if name in receipts
        ]
        local_revenue = sum(own_streams) if own_streams else None
        own_targets = [
            receipts[name].get("target")
            for name in _OWN_SOURCE_STREAMS
            if name in receipts
        ]
        own_source_target = (
            _revenue_amount(sum(own_targets))
            if own_targets and all(_figure(v) for v in own_targets)
            else None
        )

    def _stream(name: str, key: str) -> Optional[float]:
        value = (receipts or {}).get(name, {}).get(key)
        return value if _figure(value) else None

    streams = [
        {"stream": name, "target": _stream(name, "target"), "actual": vals["actual"]}
        for name, vals in sorted(
            (
                (k, v)
                for k, v in (receipts or {}).items()
                if k != REVENUE_RECEIPTS_TOTAL
            ),
            key=lambda kv: (
                _REVENUE_STREAM_ORDER.index(kv[0])
                if kv[0] in _REVENUE_STREAM_ORDER
                else len(_REVENUE_STREAM_ORDER)
            ),
        )
    ]
    return {
        "total_revenue": _stream(REVENUE_RECEIPTS_TOTAL, "actual"),
        "total_revenue_target": _stream(REVENUE_RECEIPTS_TOTAL, "target"),
        "equitable_share": _stream("Equitable Share", "actual"),
        "equitable_share_target": _stream("Equitable Share", "target"),
        "additional_allocations": _stream("Additional Allocations", "actual"),
        "local_revenue": local_revenue,
        "local_revenue_basis": "cash_receipts"
        if receipts
        else "summary_table_actual_realised"
        if local_revenue is not None
        else None,
        "summary_table_own_source_revenue": summary_own_source,
        "summary_table_own_source_target": summary_own_source_target,
        "summary_table_basis": "publisher_label_actual_realised"
        if summary_own_source is not None
        else None,
        "total_revenue_basis": "cash_receipts_including_opening_balance"
        if receipts
        else None,
        "own_source_target": own_source_target,
        "streams": streams,
        "fiscal_year": fiscal_year,
        "source": (
            "Controller of Budget — County Budget Implementation Review Report, "
            "county revenue performance table (actual receipts)"
            if receipts
            else None
        ),
        "total_revenue_absent_reason": (
            None
            if receipts
            else (withheld_reason or "no_reconciled_cbirr_revenue_table")
        ),
        "own_source_disagreement": disagreement,
    }


def _county_pending_bills_absence(db: Session, entity) -> Optional[Dict[str, Any]]:
    """Why a county has no pending-bills figure, when the report says why.

    The newest CoB year-end report the published county rows came from lists
    the counties it states no figure for (``not_reported`` — Nandi at 30 June
    2026) and the rows the parser withheld. That list is kept on the report's
    source document, since a county with no figure has no row. None — a bare
    absence — for a county the report says nothing about, or when no county
    figure is published at all.
    """
    from models import DebtCategory

    doc_ids = {
        loan.source_document_id
        for loan in db.query(DBLoan)
        .options(joinedload(DBLoan.entity))
        .filter(DBLoan.debt_category == DebtCategory.PENDING_BILLS)
        .all()
        if loan.source_document_id
        and county_pending_bills_row_is_published(loan)
        and _pending_bills_provenance(loan).get("category") == "county"
    }
    if not doc_ids:
        return None
    tables = []
    for doc in db.query(DBSourceDocument).filter(DBSourceDocument.id.in_(doc_ids)).all():
        meta = doc.meta if isinstance(doc.meta, dict) else {}
        table = meta.get("county_payables")
        if isinstance(table, dict) and isinstance(table.get("as_at"), str):
            tables.append(table)
    if not tables:
        return None
    newest = max(tables, key=lambda t: t["as_at"])
    name = (getattr(entity, "canonical_name", "") or "").removesuffix(" County").strip()
    if name in (newest.get("not_reported") or []):
        reason = "not_reported"
    elif name in (newest.get("withheld") or {}):
        reason = "withheld"
    else:
        return None
    return {"reason": reason, "as_at": newest["as_at"], "table": newest.get("table")}


def _county_pending_bills_fields(
    loans,
    pending_bills: Optional[float],
    absence: Optional[Dict[str, Any]] = None,
    reporting_date=None,
) -> Dict[str, Any]:
    """``pending_bills_as_at`` / ``_source`` / ``_notes`` / ``_absence``.

    Read from the same published rows as the figure, so a date is never shown
    beside an absent figure or the other way round. ``_absence`` is the
    report's own reason for NO figure (see
    :func:`_county_pending_bills_absence`), and only ever set when there is
    none.
    """
    selection = select_county_pending_bills(loans, as_at=reporting_date)
    if pending_bills is None:
        return {
            "pending_bills_selection": {
                k: v for k, v in selection.items() if k != "rows"
            },
            "pending_bills_as_at": None,
            "pending_bills_source": None,
            "pending_bills_notes": [],
            "pending_bills_absence": absence,
        }
    details = county_pending_bills_details(loans)
    return {
        "pending_bills_selection": {k: v for k, v in selection.items() if k != "rows"},
        "pending_bills_as_at": details["as_at"],
        "pending_bills_source": {
            "publisher": "Controller of Budget",
            "title": (
                "County Governments Budget Implementation Review Report"
                + (f", {details['fiscal_year']}" if details["fiscal_year"] else "")
            ),
            "table": details["table"],
            "url": details["source_url"],
            "source_document_id": details["sources"][0]["source_document_id"],
            "page_ref": details["sources"][0]["page_ref"],
            "page": details["sources"][0]["page"],
            "publication_batch": details["sources"][0]["publication_batch"],
        },
        "pending_bills_notes": details["notes"],
        "pending_bills_absence": None,
    }


def county_debt_provenance_label(loans, total_debt: Optional[float]) -> str:
    """``data_sources.debt`` for a county, from the rows actually published.

    Keyed on each row's declared publication, never on a document's title or
    publisher column — the BROP's source document carried the Controller of
    Budget as publisher for months.
    """
    details = county_pending_bills_details(loans)
    if county_pending_bills(loans) is not None:
        pending = (
            "Pending bills: Controller of Budget — County Governments Budget "
            "Implementation Review Report"
            + (f" ({details['fiscal_year']})" if details["fiscal_year"] else "")
            + (f", {details['table']}" if details["table"] else "")
            + (f", trade payables as at {details['as_at']}" if details["as_at"] else "")
        )
    else:
        pending = (
            "Pending bills: no Controller of Budget year-end figure is published "
            "for this county"
        )
    debt = (
        "County debt: selected outstanding balances are unavailable or incomplete"
        if total_debt is None
        else "County debt: loan rows with a source document"
    )
    return f"{pending}. {debt}."


#: Grade bands for the financial-health index. Ours, not a publisher's, and
#: reported alongside the score so a reader can see where a letter came from.
_HEALTH_GRADE_BANDS = ((85, "A"), (70, "B+"), (55, "B"), (40, "B-"), (0, "C"))

#: Pending bills at or above this share of a county's budget scores zero on
#: that component. County pending bills are a first charge on the next year's
#: budget, so a quarter of a budget already committed to last year's unpaid
#: invoices is the point at which the component stops discriminating.
_PENDING_BILLS_SEVERE_SHARE = 25.0

#: Site-chosen mapping of an audit status onto 0-100. County detail derives
#: that status from the latest executive fiscal period maximum finding severity;
#: it is not an official Auditor-General rating.
_AUDIT_OPINION_SCORES = {
    "clean": 100.0,
    "qualified": 60.0,
    "adverse": 20.0,
    "disclaimer": 0.0,
}

#: Fewer components than this and no score is published. One component is not
#: a composite — which is exactly what the previous score was.
_MIN_HEALTH_COMPONENTS = 2

#: Relative weights, renormalised over whichever components a county has.
#:
#: The audit signal carries as much as the three financial components put
#: together when all four are available. Under equal weighting a county with
#: perfect absorption and revenue performance still scored 50.0 (B-) on an
#: explicit disclaimer; with this weighting it scores 33.3 (C).
#:
#: These are a CHOSEN weighting, not a measured one — no publisher ranks these
#: four against each other. Integers rather than fractions so the ratio is
#: legible, and both the weight and its effective share are reported with the
#: score so a reader can re-weight the components themselves.
_HEALTH_COMPONENT_WEIGHTS: Dict[str, int] = {
    "audit_opinion": 3,
    "budget_absorption": 1,
    "own_source_revenue": 1,
    "pending_bills": 1,
}
_DEFAULT_HEALTH_WEIGHT = 1


def county_financial_health(
    *,
    total_allocated: Optional[float],
    total_spent: Optional[float],
    pending_bills: Optional[float],
    audit_status: Optional[str],
    own_source_target: Optional[float] = None,
    own_source_actual: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """A county's financial-health index, its grade, and what went into it.

    WHAT THIS REPLACES
    ------------------
    The previous score was::

        health_score = utilization              if utilization <= 95
                     = 90                       if 95 < utilization <= 100
                     = max(0, 80 - (util-100))  if utilization > 100

    — a piecewise transform of ONE input. A county that had spent 42.9% of its
    budget was shown "42.9/100" and a grade of B-, beside a Budget Utilisation
    figure of 42.9%: the same number twice, the second time wearing the word
    "health". And ``total_allocated == 0`` gave a score of 0.0, which graded a
    county with no budget data a C.

    WHAT IT IS NOW
    --------------
    A weighted mean of available components, each derived from a published
    figure. The audit signal has weight 3; each financial measure has weight 1.

    ``budget_absorption``  spent vs allocated (Controller of Budget). Scored
        symmetrically about 100 — under-spending is a failure to deliver and
        over-spending is a failure to budget, so both cost the same.
    ``own_source_revenue`` amount vs target from the same CBIRR table. Capped at
        100 so a lowballed target cannot buy a high score.
    ``pending_bills``      pending bills as a share of budget, inverted.
    ``audit_opinion``      audit status supplied by the caller. The county
        detail currently maps its latest executive fiscal period maximum finding
        severity to this status; the label is retained for compatibility,
        not an OAG rating.

    The audit signal carries as much weight as the other three combined —
    see ``_HEALTH_COMPONENT_WEIGHTS`` for why, and note that the ratio is a
    chosen one, reported in the payload so a reader can re-weight it.

    Returns None when fewer than two components can be computed. A composite
    of one component is not a composite, and absence must not read as zero.
    """
    components: List[Dict[str, Any]] = []

    if total_allocated and total_allocated > 0 and total_spent is not None:
        absorption = total_spent / total_allocated * 100
        components.append(
            {
                "name": "budget_absorption",
                "score": round(max(0.0, 100.0 - abs(100.0 - absorption)), 1),
                "observed": round(absorption, 1),
                "basis": (
                    "spent vs allocated, Controller of Budget; scored "
                    "symmetrically about 100%"
                ),
            }
        )

    if own_source_target and own_source_target > 0 and own_source_actual is not None:
        performance = own_source_actual / own_source_target * 100
        components.append(
            {
                "name": "own_source_revenue",
                "score": round(min(100.0, max(0.0, performance)), 1),
                "observed": round(performance, 1),
                "basis": "own-source revenue vs target from the same CBIRR table",
            }
        )

    if total_allocated and total_allocated > 0 and pending_bills is not None:
        share = pending_bills / total_allocated * 100
        components.append(
            {
                "name": "pending_bills",
                "score": round(
                    max(0.0, 100.0 * (1 - share / _PENDING_BILLS_SEVERE_SHARE)), 1
                ),
                "observed": round(share, 1),
                "basis": (
                    f"pending bills as a share of budget, Controller of Budget "
                    f"year-end report; zero "
                    f"at {_PENDING_BILLS_SEVERE_SHARE:.0f}% or above"
                ),
            }
        )

    opinion_score = _AUDIT_OPINION_SCORES.get((audit_status or "").lower())
    if opinion_score is not None:
        components.append(
            {
                "name": "audit_opinion",
                "score": opinion_score,
                "observed": audit_status,
                "basis": "audit status supplied by caller; severity-derived site signal, not an official OAG opinion; latest executive fiscal period maximum finding severity",
            }
        )

    if len(components) < _MIN_HEALTH_COMPONENTS:
        return None

    # Renormalised over the components this county actually has, so a missing
    # one neither penalises nor flatters it.
    total_weight = sum(
        _HEALTH_COMPONENT_WEIGHTS.get(c["name"], _DEFAULT_HEALTH_WEIGHT)
        for c in components
    )
    for component in components:
        weight = _HEALTH_COMPONENT_WEIGHTS.get(
            component["name"], _DEFAULT_HEALTH_WEIGHT
        )
        component["weight"] = weight
        component["share_pct"] = round(weight / total_weight * 100, 1)

    score = round(
        sum(c["score"] * c["weight"] for c in components) / total_weight, 1
    )
    grade = next(letter for floor, letter in _HEALTH_GRADE_BANDS if score >= floor)
    return {
        "score": score,
        "grade": grade,
        "weighting": "audit_opinion_weighted",
        "weights": dict(_HEALTH_COMPONENT_WEIGHTS),
        "components": components,
    }


def _county_own_source_target_summary(budget_lines) -> Optional[float]:
    """Target from the single unambiguous summary row, if reported."""
    rows = [
        line
        for line in budget_lines or []
        if (line.category or "").strip().lower() == OWN_SOURCE_REVENUE_CATEGORY
    ]
    return _revenue_amount(rows[0].allocated_amount) if len(rows) == 1 else None


#: How many of a county's audit findings to surface as its key challenges.
_MAJOR_ISSUES_LIMIT = 4


def _county_major_issues(audits, titles: Optional[Dict[int, str]] = None) -> List[str]:
    """A county's actual audit findings, worst first, as short labels.

    Replaces four strings that were identical for all 47 counties. These are
    the Auditor-General's findings for THIS county, already filtered to
    publishable and display-grade rows by the caller, so a county with none
    gets an empty list rather than somebody else's problems.

    ``titles`` maps extraction id -> the finding's own heading, which the
    extractor captured ("Use of Goods and Services", "Irregular Award of
    Tenders"). ``finding_text`` runs that heading straight into the paragraph
    beneath it with no punctuation between, so trimming the text gives
    "Unsupported Accounts Receivables The statement of assets and liabil…"
    where the heading alone is the label.
    """
    order = {"critical": 0, "warning": 1, "info": 2}
    ranked = sorted(
        audits,
        key=lambda a: order.get(
            getattr(getattr(a, "severity", None), "value", ""), 3
        ),
    )
    issues: List[str] = []
    for audit in ranked:
        label = (titles or {}).get(getattr(audit, "extraction_id", None) or -1)
        if not label:
            # No captured heading (a fixture-era row, or an older extractor).
            text = " ".join((audit.finding_text or "").split())
            if not text:
                continue
            label = re.split(r"(?<=[a-z])\.\s", text)[0].strip(" .")
        label = " ".join(label.split())
        if len(label) > 90:
            label = label[:87].rstrip() + "…"
        if label not in issues:
            issues.append(label)
        if len(issues) >= _MAJOR_ISSUES_LIMIT:
            break
    return issues


def _debt_sustainability(
    total_debt: Optional[float], total_allocated: float
) -> Optional[str]:
    """"sustainable" / "moderate" / "at_risk", or None when unknown.

    None where either input is missing. The label is a judgement about a
    county's finances, and one made from an absent numerator is not a
    cautious judgement — it is a confident wrong one.
    """
    if total_debt is None or not total_allocated or total_allocated <= 0:
        return None
    ratio = total_debt / total_allocated * 100
    if ratio < 20:
        return "sustainable"
    if ratio < 40:
        return "moderate"
    return "at_risk"


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

        # FIRST preference: a period carrying CoB BIRR classification rows
        # (Total / Development / Recurrent). Those exist only where the live
        # Controller of Budget parse landed — i.e. real published
        # implementation data.
        #
        # This selector previously started at "any period with actual_spent > 0",
        # which cannot tell real execution from a modelled one: the
        # equitable-share PROJECTION periods were seeded with estimated spend
        # too. So this endpoint resolved to the FY2025/26 projection while
        # GET /counties — which already applies the preference below via
        # _latest_county_actuals_period_ids — resolved to the newest period with
        # real CoB rows. Same county, same site, two budgets: Mombasa
        # KES 9.42B here against KES 14.63B there, utilisation 32.0% against
        # 49.8%, and Nairobi's pending bills differing 23-fold
        # (credibility audit F7). The two now use the same preference order.
        # Resolve the GLOBAL newest CoB period — the same one GET /counties
        # pins every county to — not this entity's own newest.
        #
        # Picking per-entity reopened the same two-budgets defect through a
        # different door: when a CoB report is only partially ingested, the list
        # filters every county to the global period (so a county missing from
        # that report shows no budget) while the detail page silently fell back
        # to that county's older period and printed one. Same county, same site,
        # two budgets again. If the newest report has no rows for this county,
        # this endpoint now reports nothing for it too.
        _global_cob = _latest_county_actuals_period_ids(db)
        latest_cob = _global_cob[0] if _global_cob else None
        if latest_cob is None:
            latest_cob = (
                db.query(DBBudgetLine.period_id)
                .join(DBFiscalPeriod, DBBudgetLine.period_id == DBFiscalPeriod.id)
                .filter(
                    DBBudgetLine.entity_id == entity_id,
                    _sqlfunc.lower(DBBudgetLine.category).in_(
                        list(_CLASSIFICATION_CATEGORIES)
                    ),
                )
                .order_by(DBFiscalPeriod.start_date.desc())
                .limit(1)
                .scalar()
            )

        latest_executed = latest_cob or (
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


from services.county_identity import official_county_code, legacy_county_route_id

# Historical route IDs: retain bookmarks. Use official_county_code for a code.
# These identifiers must NEVER be passed to a writer as official county codes.
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

# Model imports - temporarily disabled due to database issues
# from models import (
#     Allocation, Annotation, Audit, BudgetLine, Country,
#     Document, Entity, FiscalPeriod, Loan, SourceDocument, User,
# )

# Add ETL module to path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "etl"))

# Only GET /api/v1/etl/kenya/sources still reads this flag.
ETL_AVAILABLE = True


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
    total_allocation: Optional[float] = None
    total_spent: Optional[float] = None
    execution_rate: Optional[float] = None
    fiscal_period: Optional[Dict[str, Any]] = None
    accounting_basis: Optional[str] = None
    currency: Optional[str] = None
    sources: List[Dict[str, Any]] = []
    absent_reasons: Dict[str, str] = {}
    budget_lines_count: int = 0


class EntityProfileResponse(BaseModel):
    id: int
    canonical_name: str
    type: str
    slug: Optional[str] = None
    country: Optional[str] = None
    meta: Dict[str, Any] = {}
    created_at: Optional[str] = None

    @field_validator("meta", mode="before")
    @classmethod
    def publish_metadata(cls, value):
        return public_entity_metadata(value)


class EntityResponse(EntityProfileResponse):
    code: Optional[str] = None
    financial_summary: Optional[EntityFinancialSummary] = None
    audit_findings_count: int = 0


class EntityDetailResponse(BaseModel):
    entity: EntityProfileResponse
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


class AuditListItem(BaseModel):
    id: Any
    description: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    amountLabel: Optional[str] = None
    amount: Optional[float] = None
    amount_unavailable_reason: Optional[str] = None
    audited_entity_name: Optional[str] = None
    fiscal_year: Optional[str] = None
    source: Dict[str, Any]


class AuditListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[AuditListItem]
    findings_reason: Optional[str] = None
    withheld_findings: int = 0


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
        await asyncio.to_thread(initialize_reference_data)
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


# HTTP caches are not part of signed invalidation. Do not let a browser or
# intermediary reuse an old public API body after the server caches clear.
# Backend response caches still provide the normal performance benefit.
@app.middleware("http")
async def add_cache_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if (
        request.method == "GET"
        and path.startswith("/api/v1/")
        # Skip auth-scoped or mutation-adjacent endpoints
        and not path.startswith("/api/v1/auth/")
        and not path.startswith("/api/v1/account/")
        and not path.startswith("/api/v1/watchlist")
        and "cache-control" not in {k.lower() for k in response.headers.keys()}
    ):
        response.headers["Cache-Control"] = "no-store"
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
    from routers.health import router as health_router

    app.include_router(health_router)
    logger.info("Detailed health router registered at /health/detailed")
except Exception as e:
    logger.warning(f"Could not register detailed health router: {e}")

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
    from routers.cache_invalidation import router as cache_invalidation_router

    app.include_router(cache_invalidation_router)
    logger.info("Cache invalidation registered at /api/v1/system/cache/invalidate")
except Exception as e:
    # ERROR, not warning: without this route the nightly's call 404s and the
    # job fails, and this line is where to look.
    logger.error(f"Could not register cache invalidation router: {e}")

try:
    from routers.data_provenance import router as data_provenance_router

    app.include_router(data_provenance_router)
    logger.info("Data provenance router registered at /api/v1/provenance")
except Exception as e:
    logger.warning(f"Could not register data provenance router: {e}")


# Cross-worker cache invalidation (issue #231). The nightly's signed call
# lands on one gunicorn worker and bumps a marker file; every other worker
# clears its own in-process caches on the next request it serves. One
# os.stat per request. See cache/invalidation.py.
@app.middleware("http")
async def sync_cache_generation(request: Request, call_next):
    try:
        from cache.invalidation import sync_generation

        sync_generation()
    except Exception as e:  # never fail a request over a freshness signal
        logger.error(f"cache generation sync failed: {e}")
    return await call_next(request)


# Request logging middleware.
# We only log completions (not the "PROCESSING" pre-event), and we
# downgrade fast healthy responses to DEBUG so production logs show just
# errors and slow requests — the signal engineers actually scan for.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()
    method = request.method

    try:
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.3f}"
        # Route templates are bounded labels; raw URLs can expose query text.
        route = getattr(request.scope.get("route"), "path", "unmatched")
        event = {
            "event": "http_request",
            "method": method,
            "route": route,
            "status": response.status_code,
            "duration_ms": round(process_time * 1000, 1),
        }
        # Escalate severity for slow or non-2xx responses so scanning logs
        # highlights real problems without drowning them in noise.
        if process_time > 0.5 or response.status_code >= 400:
            logger.warning("%s", json.dumps(event, separators=(",", ":")))
        else:
            logger.debug("%s", json.dumps(event, separators=(",", ":")))
        return response
    except Exception as exc:
        process_time = time.perf_counter() - start_time
        logger.error(
            "%s",
            json.dumps(
                {
                    "event": "http_request_failed",
                    "method": method,
                    "route": getattr(request.scope.get("route"), "path", "unmatched"),
                    "error_type": type(exc).__name__,
                    "duration_ms": round(process_time * 1000, 1),
                },
                separators=(",", ":"),
            ),
        )
        raise


# Cache decorator helper
_all_mem_caches: list = []  # registry for test cleanup


def clear_all_caches():
    """Clear every in-memory endpoint cache.  Called between tests."""
    for c in _all_mem_caches:
        c.clear()
    # 12-hour TTL — one warm-up would otherwise freeze peers for the whole run.
    _peers_cache["ts"] = 0.0
    _peers_cache["data"] = None
    # Clear every RedisCache instance's in-memory fallback (and Redis if live).
    for rc in _redis_cache_instances():
        rc._memory_cache.clear()
        if rc.client is not None:
            try:
                rc.client.flushdb()
            except Exception:
                pass


def _clear_endpoint_mem_caches() -> int:
    dropped = sum(len(c) for c in _all_mem_caches)
    for c in _all_mem_caches:
        c.clear()
    return dropped


# The nightly's signed invalidation call (issue #231) clears these in every
# worker. _peers_cache is deliberately absent: it holds live World Bank / IMF
# figures, not anything the seed writes. See cache/invalidation.py.
try:
    from cache.invalidation import register_local_cache

    register_local_cache("main.endpoint_memory", _clear_endpoint_mem_caches)
except Exception as e:  # pragma: no cover - import-time wiring
    logger.error(f"Cache invalidation registry unavailable: {e}")


def _redis_cache_instances():
    """Yield every RedisCache ever constructed.

    Enumerating them by name missed routers/money_flow.py's private instance,
    whose 1800 s entries then survived between tests.  RedisCache registers
    each instance at construction, so this can no longer fall behind.
    """
    try:
        from cache.redis_cache import RedisCache

        seen = set()
        for rc in RedisCache._instances:
            if id(rc) not in seen:
                seen.add(id(rc))
                yield rc
    except Exception:
        # Fall back to the named singletons rather than clearing nothing.
        if redis_cache is not None:
            yield redis_cache


def _declared_row_unit(rows, default: str = "billion_kes") -> str:
    """Response-level unit DERIVED from the rows, never hardcoded.

    Reported by review on PR #136: ``/fiscal/summary`` and ``/debt/timeline``
    returned rows carrying ``unit="KES"`` (raw KES, since the stage1 3a
    migration) inside a response whose ``_meta.unit`` still said
    ``"billion_kes"``. A client that trusts the response metadata — the field
    that exists precisely to be trusted — scales by 1e9 the wrong way. That is
    the same units hazard that forced the 2026-08-30 production migration to be
    rolled back, in a second place.

    Derived rather than flipped to a new constant, because the same code runs
    against an un-migrated database (rows with ``unit`` NULL are bare billions)
    and must keep telling the truth there too. Mixed rows report the
    conservative default so nothing is silently rescaled mid-series.
    """
    units = {getattr(r, "unit", None) for r in rows}
    return "KES" if units == {"KES"} else default


def _effective_ttl(result: object, ttl: int) -> int:
    """Cache lifetime for ``result`` — shortened when it reports an unreadable
    source, so a recovered source is visible in seconds rather than hours.
    See cache/redis_cache.py::is_transient_failure and issue #141."""
    from cache.redis_cache import TRANSIENT_FAILURE_TTL, is_transient_failure

    return min(ttl, TRANSIENT_FAILURE_TTL) if is_transient_failure(result) else ttl


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
            # Capture the marker before loading. A response completed after
            # invalidation may fill only its old-generation key, so the next
            # request cannot read stale data from an in-flight cache fill.
            from cache.invalidation import generation_identity

            cache_key_parts = [key_prefix, f"generation:{generation_identity()}"]
            for k, v in kwargs.items():
                if k not in ["db", "request", "background_tasks"]:
                    cache_key_parts.append(f"{k}:{v}")
            cache_key = ":".join(cache_key_parts)

            # --- Redis path ---
            if redis_cache:
                cached_data = redis_cache.get(cache_key)
                if cached_data is not None:
                    logger.debug("Redis cache HIT: %s", key_prefix)
                    return cached_data

                result = await func(*args, **kwargs)
                redis_cache.set(cache_key, result, ttl=_effective_ttl(result, ttl))
                return result

            # --- In-memory fallback path ---
            rec = _mem_cache.get(cache_key)
            # Honour the TTL the entry was STORED with, not the decorator's.
            # A transient failure is kept for seconds; reading it back against
            # the full TTL would defeat that.
            if rec and (time.time() - rec["ts"]) < rec.get("ttl", ttl):
                logger.debug("Memory cache HIT: %s", key_prefix)
                return rec["value"]

            result = await func(*args, **kwargs)
            _mem_cache[cache_key] = {
                "value": result,
                "ts": time.time(),
                "ttl": _effective_ttl(result, ttl),
            }
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
                "note": (
                    "Web reference refreshes run here. economic_indicators, national_debt "
                    "and debt_timeline are owned by the dedicated seeding runner; "
                    "its job health is not reported here."
                ),
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


# One synchronous snapshot per process, including cancelled requests whose
# worker is still running. The response cache coalesces normal identical misses;
# this guard also bounds bypasses, new invalidation generations and event loops.
_pipeline_health_worker_slot = threading.BoundedSemaphore(1)
_pipeline_health_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="pipeline-health"
)


def _pipeline_health_snapshot() -> dict:
    """Read plain snapshot values with a session owned entirely by this thread."""
    import copy

    alerts: list[dict] = []
    db_stats: dict = {}

    # ── 1. Check the web worker's ETL dependency ──
    # The root KNBS extractor/parser belong to no active web economic path.
    # Their absence from the backend image must not imply a cached fallback.
    module_checks = {
        "etl.kenya_pipeline": "ETL Pipeline (OAG/COB/Treasury scraping)",
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
                    "message": f"Module not importable: {exc}. Web ETL discovery is unavailable.",
                }
            )

    # ── 2. Auto-seeder status ──
    seeder_info: dict = {"is_running": False}
    try:
        from services.auto_seeder import get_seeder_status as _get_status

        seeder_info = copy.deepcopy(_get_status())
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
        from database import SessionLocal

        with SessionLocal() as db:
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
                        "message": "No population records; check the dedicated population seeding job.",
                    }
                )
            if econ_count == 0:
                alerts.append(
                    {
                        "level": "warning",
                        "source": "economic",
                        "message": "No economic indicator records; check the dedicated economic_indicators seeding job.",
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
        db_stats.clear()
        logger.error(f"Error checking database stats: {exc}")
        alerts.append(
            {
                "level": "error",
                "source": "database",
                "message": f"Could not query database: {exc}",
            }
        )

    return {
        "alerts": alerts,
        "database": db_stats,
        "modules": module_status,
        "auto_seeder": seeder_info,
    }


def _pipeline_health_snapshot_done(future: concurrent.futures.Future) -> None:
    # Observe the physical worker completion, including queued-work cancellation.
    # Cancelling an asyncio waiter cannot release capacity while SQL still runs.
    _pipeline_health_worker_slot.release()
    if not future.cancelled():
        exc = future.exception()
        if exc is not None:
            logger.error(
                "Pipeline health snapshot failed",
                exc_info=(type(exc), exc, exc.__traceback__),
            )


def _observe_pipeline_health_waiter(future: asyncio.Future) -> None:
    # shield() lets the worker finish after a caller cancels. Retrieve the
    # asyncio wrapper's exception too; the physical completion callback logs it.
    if not future.cancelled():
        future.exception()


@app.get("/api/v1/system/pipeline-health")
@response_cached(ttl=30, key_prefix="pipeline_health")
async def get_pipeline_health() -> dict:
    """Report database, web ETL and source health without blocking the event loop."""
    now = datetime.datetime.now(datetime.timezone.utc)
    if not _pipeline_health_worker_slot.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail="Pipeline health snapshot is still running; retry shortly.",
            headers={"Retry-After": "1"},
        )
    try:
        future = _pipeline_health_executor.submit(_pipeline_health_snapshot)
    except BaseException:
        _pipeline_health_worker_slot.release()
        raise
    future.add_done_callback(_pipeline_health_snapshot_done)
    waiter = asyncio.wrap_future(future)
    waiter.add_done_callback(_observe_pipeline_health_waiter)
    snapshot = await asyncio.shield(waiter)
    alerts = snapshot["alerts"]
    db_stats = snapshot["database"]
    module_status = snapshot["modules"]
    seeder_info = snapshot["auto_seeder"]
    sources: dict = {}

    # ── 4. Data source reachability (non-blocking quick check) ──
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

    source_results = await asyncio.gather(
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

    return {
        "status": overall,
        "checked_at": now.isoformat(),
        "auto_seeder": seeder_info,
        "economic_ingestion": {
            "owner": "dedicated seeding runner",
            "domain": "economic_indicators",
            "web_refresh": "retired",
            "job_health": "not_checked_here",
        },
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


# POST /api/v1/system/seeder-refresh was removed: it started a full in-app
# seed for any anonymous caller and nothing in the repo called it. The
# admin-gated trigger is POST /api/v1/admin/etl/trigger/{source}; see
# tests/test_system_routes_are_read_only.py before adding a write route here.


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

                # County budgets in the latest period, one rule for all
                # (see _county_period_rollup for the double count this was).
                _per_county, _ = _county_period_rollup(db, _county_pid)
                total_allocation = sum(a for _n, a, _s in _per_county.values())
                total_spent = sum(sp for _n, _a, sp in _per_county.values())

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
    from services.publication_gate import normalize_audit_identity

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
        dataset_id = normalize_audit_identity(entry.get("dataset_id"))
        if dataset_id.startswith(_FABRICATED_AUDIT_DATASET_PREFIXES):
            return False
        quality = normalize_audit_identity(entry.get("data_quality")).lower()
        if quality in _NON_OFFICIAL_QUALITIES:
            return False
    return True


# Categories used by the CoB BIRR live parse as CLASSIFICATION rows
# (whole-budget economic classification), not additive sectors. They
# must be excluded from sector/total sums — adding Development +
# Recurrent + Total to the sector lines would triple-count the budget.
# County budget aggregation rules live in services/county_budget.py so the
# money-flow router can apply the SAME split — it cannot import from main
# (main imports it), and its own naive sum over every row published Baringo's
# budget as KES 26.55B against the Controller of Budget's 9.54B.
from services.county_budget import (  # noqa: E402
    BUDGET_PROVENANCE_LABELS as _BUDGET_PROVENANCE_LABELS,
)
from services.county_budget import (  # noqa: E402
    BUDGET_SOURCE_COB_CBIRR,
    BUDGET_SOURCE_CRA_MODEL,
)
from services.county_budget import (  # noqa: E402
    CLASSIFICATION_CATEGORIES as _CLASSIFICATION_CATEGORIES,
)
from services.county_budget import (  # noqa: E402
    NON_SECTOR_CATEGORIES as _NON_SECTOR_CATEGORIES,
)
from services.county_budget import budget_provenance as _budget_provenance  # noqa: E402
from services.county_budget import (  # noqa: E402
    split_classification_and_sector_lines as _split_classification_and_sector_lines,
)


def _county_budget_period_rows(db):
    """Fiscal periods that actually carry county budget rows, newest first.

    One definition, shared by the year picker (``GET /counties/fiscal-years``)
    and by the guard that rejects a requested year outside this set — so the
    years the API offers and the years it accepts cannot drift apart.

    Each row carries ``classification_rows`` (> 0 where the Controller of
    Budget's Total/Development/Recurrent rows landed) and ``counties``.
    """
    from sqlalchemy import case
    from sqlalchemy import func as _f

    return (
        db.query(
            DBFiscalPeriod.id,
            DBFiscalPeriod.label,
            _f.sum(
                case(
                    (
                        _f.lower(DBBudgetLine.category).in_(
                            list(_CLASSIFICATION_CATEGORIES)
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("classification_rows"),
            _f.count(_f.distinct(DBBudgetLine.entity_id)).label("counties"),
        )
        .join(DBBudgetLine, DBBudgetLine.period_id == DBFiscalPeriod.id)
        .join(DBEntity, DBEntity.id == DBBudgetLine.entity_id)
        .filter(DBEntity.type == EntityType.COUNTY)
        .group_by(DBFiscalPeriod.id, DBFiscalPeriod.label, DBFiscalPeriod.start_date)
        .order_by(DBFiscalPeriod.start_date.desc())
        .all()
    )


def _resolve_requested_county_period_ids(db, fiscal_year: str) -> List[int]:
    """Period ids for an EXPLICITLY requested county fiscal year.

    Raises 404 when the label names no period that holds county budget data.

    The three county endpoints used to resolve this inline and swallow the
    miss::

        period_ids = None
        if fiscal_year:
            try:
                canonical = _nlbl(fiscal_year)
                period_ids = [fp.id for fp in db.query(_FP).all()
                              if fp.label == canonical] or None
            except (ValueError, IndexError):
                pass  # Ignore bad fiscal_year format, return unfiltered
        ...
        if period_ids:
            bl_query = bl_query.filter(DBBudgetLine.period_id.in_(period_ids))

    A typo, a stale bookmark or a year not yet ingested left ``period_ids`` at
    None, the period filter was skipped, and EVERY period was summed into one
    row — published as that year's budget, under no label. With two CBIRR years
    ingested a county's budget reads as the sum of both.

    ``/comprehensive`` was milder: it fell through to auto-resolve and served a
    different period than the caller asked for, correctly labelled. Silently
    ignoring the parameter is the same defect, just harder to see.

    Periods with no county budget rows are not servable either: filtering to
    one returns zeros for all 47 counties, which states that every county was
    allocated nothing.
    """
    from seeding.utils import normalize_fiscal_label as _nlbl

    rows = _county_budget_period_rows(db)
    available = [r.label for r in rows if r.label]

    try:
        canonical = _nlbl(fiscal_year)
    except (ValueError, IndexError):
        canonical = None

    ids = [r.id for r in rows if canonical and r.label == canonical]
    if not ids:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Fiscal year not available",
                "message": (
                    f"No county budget data for fiscal year {fiscal_year!r}."
                    if canonical
                    else f"{fiscal_year!r} is not a fiscal year label."
                ),
                "requested": fiscal_year,
                "available_fiscal_years": available,
                "solution": "Call GET /api/v1/counties/fiscal-years for the years that can be served, or omit fiscal_year to get the latest reported one.",
            },
        )
    return ids


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

    from models import FigureBasis as _FigureBasis, FiscalPeriod as _FP
    from services.entity_financials import budget_evidence_is_unreported

    possible_reported_basis = or_(
        DBBudgetLine.basis.is_(None),
        DBBudgetLine.basis.notin_((_FigureBasis.MODELLED, _FigureBasis.PROJECTED)),
    )
    not_quarantined = or_(
        DBBudgetLine.quarantine_reason.is_(None),
        DBBudgetLine.quarantine_reason == "",
    )
    periods = (
        db.query(_FP.id, _FP.start_date, _FP.end_date)
        .select_from(DBBudgetLine)
        .join(_FP, DBBudgetLine.period_id == _FP.id)
        .join(DBEntity, DBEntity.id == DBBudgetLine.entity_id)
        .filter(
            DBEntity.type == EntityType.COUNTY,
            _f.lower(_f.trim(DBBudgetLine.category)).in_(list(_CLASSIFICATION_CATEGORIES)),
            possible_reported_basis,
            not_quarantined,
        )
        .distinct()
        .order_by(_FP.start_date.desc(), _FP.end_date.desc(), _FP.id.desc())
        .all()
    )
    source_metadata = {}
    for period_id, _, _ in periods:
        last_line_id = 0
        while True:
            # Page only the fields the shared evidence predicate needs. Source
            # metadata is fetched separately and cached across pages/periods.
            rows = (
                db.query(
                    DBBudgetLine.id,
                    DBBudgetLine.quarantine_reason,
                    DBBudgetLine.basis,
                    DBBudgetLine.provenance,
                    DBBudgetLine.source_document_id,
                )
                .join(DBEntity, DBEntity.id == DBBudgetLine.entity_id)
                .filter(
                    DBEntity.type == EntityType.COUNTY,
                    DBBudgetLine.period_id == period_id,
                    DBBudgetLine.id > last_line_id,
                    _f.lower(_f.trim(DBBudgetLine.category)).in_(
                        list(_CLASSIFICATION_CATEGORIES)
                    ),
                    possible_reported_basis,
                    not_quarantined,
                )
                .order_by(DBBudgetLine.id)
                .limit(32)
                .all()
            )
            if not rows:
                break
            candidates = [
                row for row in rows
                if not budget_evidence_is_unreported(
                    row.quarantine_reason, row.basis, row.provenance, None
                )
            ]
            uncached_source_ids = {
                row.source_document_id for row in candidates
                if row.source_document_id not in source_metadata
            }
            if uncached_source_ids:
                source_metadata.update({
                    doc_id: meta
                    for doc_id, meta in db.query(
                        DBSourceDocument.id, DBSourceDocument.meta
                    ).filter(DBSourceDocument.id.in_(uncached_source_ids)).all()
                })
                for doc_id in uncached_source_ids:
                    source_metadata.setdefault(doc_id, None)
            for row in candidates:
                if not budget_evidence_is_unreported(
                    row.quarantine_reason,
                    row.basis,
                    row.provenance,
                    source_metadata[row.source_document_id],
                ):
                    return [period_id]
            last_line_id = rows[-1].id

    row = (
        db.query(_FP.id)
        .join(DBBudgetLine, DBBudgetLine.period_id == _FP.id)
        .join(DBEntity, DBEntity.id == DBBudgetLine.entity_id)
        .filter(
            DBEntity.type == EntityType.COUNTY,
            DBBudgetLine.actual_spent.isnot(None),
            DBBudgetLine.actual_spent > 0,
        )
        .order_by(_FP.start_date.desc(), _FP.end_date.desc(), _FP.id.desc())
        .first()
    )
    if row:
        return [row[0]]
    latest = db.query(_FP).order_by(
        _FP.start_date.desc(), _FP.end_date.desc(), _FP.id.desc()
    ).first()
    return [latest.id] if latest else None


def county_database_required(function):
    """Reject a known DB outage before reading a cached county response."""
    @functools.wraps(function)
    async def checked(*args, **kwargs):
        if not DATABASE_AVAILABLE:
            raise HTTPException(status_code=503, detail="Database unavailable")
        return await function(*args, **kwargs)
    return checked


# County endpoints publish the shared database account.
@app.get("/api/v1/counties")
@county_database_required
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
                .join(DBCountry, DBEntity.country_id == DBCountry.id)
                .filter(DBEntity.type == EntityType.COUNTY, DBCountry.iso_code == "KEN")
                .order_by(DBEntity.canonical_name)
            )
            entities = [e for e in q.all() if official_county_code(e.canonical_name)]

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
            period_ids = None
            if fiscal_year:
                # A year the API cannot serve is refused, not silently widened:
                # leaving period_ids at None here skipped the filter below and
                # summed EVERY period into one row.
                period_ids = _resolve_requested_county_period_ids(db, fiscal_year)
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
            _pending_reporting_day = county_pending_reporting_date(db)
            from services.county_debt import county_debt_rows

            all_loans = county_loans_at_reporting_date(
                county_debt_rows(db, entity_ids),
                _pending_reporting_day,
            )
            _audit_signals = county_audit_signals(
                db, entity_ids, display_grade=_audit_is_display_grade
            )
            loans_by_entity: dict = {}
            for loan in all_loans:
                loans_by_entity.setdefault(loan.entity_id, []).append(loan)

            # 4. Audits — deliberately NOT filtered by the budget period:
            # an audit opinion is issued for its own FY and users want the
            # most recent one regardless of which budget year is shown.
            # (The old period filter pinned audits to the projections
            # period, which has none, so every county read as "pending".)
            # Fabricated/modelled rows are gated out — display-grade only.
            # Scan the publication metadata before picking a latest row or
            # limiting issue summaries. The Python display-grade check can
            # reject a newer publishable row, so a SQL LIMIT here would change
            # both the latest opinion and the count.
            all_audits = (
                db.query(
                    DBAudit.id,
                    DBAudit.entity_id,
                    DBAudit.created_at,
                    DBAudit.severity,
                    DBAudit.source_document_id,
                    DBAudit.provenance,
                )
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

            # Only the first ten display-grade findings per county are shown,
            # and only their first 200 characters leave the database. Fetch
            # these after the Python gate, in one batch for all counties.
            issue_ids = [a.id for rows in audits_by_entity.values() for a in rows[:10]]
            issue_text_by_id = {}
            if issue_ids:
                issue_text_by_id = dict(
                    db.query(
                        DBAudit.id,
                        _fn.substr(DBAudit.finding_text, 1, 200),
                    )
                    .filter(DBAudit.id.in_(issue_ids))
                    .all()
                )

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

            from services.entity_financials import (
                financial_summary,
                publish_county_budget,
            )

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
                # One rule, shared with /counties/{id}/comprehensive, so the
                # two endpoints cannot publish different budgets for the same
                # county again (credibility audit F7).
                (
                    total_allocated,
                    total_spent,
                    sector_lines,
                    class_by_cat,
                ) = _split_classification_and_sector_lines(budget_lines)

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

                from services.financial_publication import county_debt_summary

                debt_summary = county_debt_summary(loans)
                total_debt = debt_summary["total_debt"]

                # The CoB year-end per-county figure, through the one reader
                # every endpoint shares (services/publication_gate.py). A rung
                # summing any budget line whose category mentioned "pending"
                # used to sit in front of it here and nowhere else, so the list
                # and the detail page could answer differently for one county.
                pending_bills = county_pending_bills(loans)

                latest_audit = audits[0] if audits else None

                audit_issues = []
                for a in audits[:10]:
                    audit_issues.append(
                        {
                            "id": str(a.id),
                            "type": "financial",
                            "severity": a.severity.value if a.severity else "medium",
                            "description": issue_text_by_id.get(a.id) or "",
                            "status": "open",
                        }
                    )

                _audit_signal = _audit_signals[e.id]
                audit_status = _audit_signal["status"]
                audit_rating = _audit_signal["severity"] or ""

                # One disclosed composite, shared by all three endpoints — see
                # county_financial_health. The formula this replaces was a piecewise
                # transform of utilisation alone, so the "health" score printed the
                # Budget Utilisation figure a second time.
                from services.entity_financials import financial_summary

                _published_budget = financial_summary(
                    budget_lines, budget_lines[0].period if budget_lines else None
                )
                _health = county_financial_health(
                    total_allocated=_published_budget["total_allocation"],
                    total_spent=_published_budget["total_spent"],
                    pending_bills=pending_bills
                    if pending_budget_compatible(
                        loans,
                        _published_budget["fiscal_period"],
                        budget_currency=_published_budget["currency"],
                    )
                    else None,
                    audit_status=audit_status,
                    own_source_target=county_own_source_target(budget_lines),
                    own_source_actual=county_own_source_revenue(budget_lines),
                )
                health_score = _health["score"] if _health else None

                meta = e.meta or {}
                metrics = _resolve_fy_metrics(meta, fiscal_year)
                # Own-source revenue as the Controller of Budget reports it.
                # The meta rungs behind it were a flat 0.85 x budget.
                revenue_collection = county_own_source_revenue(budget_lines)
                # Withheld. This was ``metrics["transfers_received"]`` falling
                # back to ``total_allocated`` — the budget, published as money
                # received — and bootstrap no longer writes that metric, so it
                # was the budget for all 47. What a county received is on the
                # detail page as ``revenue.total_revenue``, with its period; a
                # nine-month receipts figure here would be read against the
                # annual budget as a "funding gap".
                money_received = None

                name = e.canonical_name.replace(" County", "")
                county_id = legacy_county_route_id(e.canonical_name) or e.slug
                coords = COUNTY_COORDINATES.get(county_id or "", [36.8219, -1.2921])

                last_audit_date = None
                last_audit_date = _audit_signal.get("period_end")

                results.append(
                    {
                        "id": county_id or str(e.id),
                        "name": name,
                        "code": official_county_code(e.canonical_name),
                        "coordinates": coords,
                        # The census, or nothing. A 0 here is not a
                        # smaller number than Lamu's 143,920 — it is the
                        # statement that nobody lives in the county, and
                        # this payload is what the Explorer table, the map
                        # and the compare page all read. Absent sorts last
                        # and renders as an em dash; a zero sorted first
                        # and divided into per-capita budget.
                        "population": (pop_data.total_population if pop_data else None),
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
                        # Whether this row's budget is the Controller of
                        # Budget's own CBIRR aggregate or the CRA model. The
                        # list and compare pages carry the same standing
                        # provenance note the detail page does, so they need
                        # the same answer from the same rule. null when
                        # nothing was published — absence has no source.
                        "budget_source": _budget_provenance(
                            class_by_cat, total_allocated
                        ),
                        "development_budget": development_total,
                        "recurrent_budget": recurrent_total,
                        "sector_breakdown": sector_breakdown,
                        "money_received": money_received,
                        "revenue_collection": revenue_collection,
                        "revenue": _county_revenue_for_lines(budget_lines),
                        "pending_bills": pending_bills,
                        **_county_pending_bills_fields(
                            loans, pending_bills, reporting_date=_pending_reporting_day
                        ),
                        "debt": total_debt,
                        **debt_summary,
                        "gdp": float(gdp_data.gdp_value) if gdp_data else None,
                        "financial_health_score": health_score,
                        "financial_health": _health,
                        "audit_rating": audit_rating,
                        "audit_status": audit_status,
                        "audit_signal": _audit_signal,
                        "last_audit_date": last_audit_date,
                        "last_audit_date_basis": "audited_period_end",
                        "audit_issues": audit_issues,
                        "audit_findings_count": len(audits),
                        "data_freshness": {
                            "budget_source": (
                                budget_lines[0].source_document_id
                                if budget_lines
                                else None
                            ),
                            "last_audit_source": (
                                _audit_signal["sources"][0]["source_document_id"]
                                if len(_audit_signal["sources"]) == 1
                                else None
                            ),
                        },
                    }
                )

                rows = bl_by_entity.get(e.id, [])
                period = rows[0].period if rows else None
                publish_county_budget(results[-1], financial_summary(rows, period))

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


# NOTE: must stay ABOVE /api/v1/counties/{county_id} — FastAPI matches in
# declaration order, and the parameterised route would otherwise capture
# "fiscal-years" as a county id. tests/test_county_fiscal_years.py pins this.
@app.get("/api/v1/counties/fiscal-years")
@cached(key_prefix="counties:fiscal_years", ttl=1800)
async def get_county_fiscal_years():
    """Fiscal years county budget data exists for, and the one to show first.

    The county explorer seeded its year picker from
    ``getLatestReportedFiscalYear()`` — a label derived from ``new Date()``
    with no reference to what the database holds. In September 2026 that is
    "2025/26", the CRA equitable-share projection, so the explorer published
    Baringo at KES 7.13B while the county's own page — which sends no year and
    lets this API resolve the period — published KES 9.54B from the CBIRR.
    Same county, same site, two budgets (credibility audit F7 again, this time
    through the frontend's explicit ``fiscal_year``).

    ``default`` is resolved by the SAME rule ``GET /counties`` applies when no
    ``fiscal_year`` is passed, so the label the explorer prints and the figures
    it fetched cannot describe different periods.

    ``years`` lists only periods that actually carry county budget rows, each
    with the provenance of that year's figures, so the picker never offers a
    year with nothing behind it.

    Both are ``None``/empty when no county budget data exists at all. Returning
    a calendar-derived label there would reproduce the original defect.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Database unavailable",
                "message": "Cannot resolve county fiscal years",
                "solution": "Check database connectivity",
            },
        )

    try:
        with next(get_db()) as db:
            # Same query the requested-year guard uses, so the years the
            # picker offers and the years the API accepts are one set.
            rows = _county_budget_period_rows(db)

            default_ids = _latest_county_actuals_period_ids(db)
            default_id = default_ids[0] if default_ids else None

            years = [
                {
                    "label": r.label,
                    # A year is CBIRR-reported when the Controller of Budget's
                    # classification rows landed for it; otherwise its figures
                    # are the CRA model. Same vocabulary as budget_source on
                    # the county rows.
                    "source": (
                        BUDGET_SOURCE_COB_CBIRR
                        if (r.classification_rows or 0) > 0
                        else BUDGET_SOURCE_CRA_MODEL
                    ),
                    "counties": r.counties,
                }
                for r in rows
                if r.label
            ]
            offered = {y["label"] for y in years}
            default_label = next(
                (r.label for r in rows if r.id == default_id and r.label), None
            )
            # Never name a default the picker does not offer.
            if default_label not in offered:
                default_label = None

            return {"years": years, "default": default_label}
    except Exception as e:
        logging.error(f"Error fetching county fiscal years: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/counties/code/{code}")
async def get_county_by_official_code(code: str, fiscal_year: Optional[str] = None):
    """Official KNBS/constitutional code; historical numeric URLs stay stable."""
    return await get_county_details(county_id=f"code:{code}", fiscal_year=fiscal_year)


@app.get("/api/v1/counties/{county_id}")
@county_database_required
@cached(key_prefix="county", ttl=1800)  # Cache for 30 minutes
async def get_county_details(county_id: str, fiscal_year: Optional[str] = None):
    """Get detailed information for a specific county (DB-first, enriched)."""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        with next(get_db()) as db:
            e = _resolve_county_entity(db, county_id)
            # Unknown id → 404. Previously an unresolvable id skipped
            # the name filter and q.first() served the FIRST county's
            # data (Mombasa) under any garbage id with a 200.
            if not e or official_county_code(e.canonical_name) is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"County '{county_id}' not found",
                )
            if e:
                name = e.canonical_name.removesuffix(" County")
                # Resolve fiscal period — same logic as list endpoint
                period_ids = None
                if fiscal_year:
                    # Same guard as the list endpoint — this block carried
                    # the same silent widen-to-all-periods fallback.
                    period_ids = _resolve_requested_county_period_ids(
                        db, fiscal_year
                    )
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

                _pending_reporting_day = county_pending_reporting_date(db)
                from services.county_debt import county_debt_rows

                loans = county_loans_at_reporting_date(
                    county_debt_rows(db, [e.id]),
                    _pending_reporting_day,
                )
                from services.financial_publication import county_debt_summary

                debt_summary = county_debt_summary(loans)
                total_debt = debt_summary["total_debt"]

                # Same reader as the list and /comprehensive.
                pending_bills = county_pending_bills(loans)

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

                _audit_signal = county_audit_signals(
                    db, [e.id], display_grade=_audit_is_display_grade
                )[e.id]
                audit_status = _audit_signal["status"]
                audit_rating = _audit_signal["severity"] or ""

                # One disclosed composite, shared by all three endpoints — see
                # county_financial_health. The formula this replaces was a piecewise
                # transform of utilisation alone, so the "health" score printed the
                # Budget Utilisation figure a second time.
                from services.entity_financials import financial_summary

                _published_budget = financial_summary(
                    budget_lines, budget_lines[0].period if budget_lines else None
                )
                _health = county_financial_health(
                    total_allocated=_published_budget["total_allocation"],
                    total_spent=_published_budget["total_spent"],
                    pending_bills=pending_bills
                    if pending_budget_compatible(
                        loans,
                        _published_budget["fiscal_period"],
                        budget_currency=_published_budget["currency"],
                    )
                    else None,
                    audit_status=audit_status,
                    own_source_target=county_own_source_target(budget_lines),
                    own_source_actual=county_own_source_revenue(budget_lines),
                )
                health_score = _health["score"] if _health else None

                meta = e.meta or {}
                metrics = _resolve_fy_metrics(meta, fiscal_year)
                # Absent stays absent — see county_own_source_revenue.
                revenue_collection = county_own_source_revenue(budget_lines)
                # Withheld — see the same field in GET /counties.
                money_received = None

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
                coords = COUNTY_COORDINATES.get(
                    legacy_county_route_id(e.canonical_name)
                )

                last_audit_date = None
                last_audit_date = _audit_signal.get("period_end")

                if development_total == 0 and total_allocated > 0:
                    dev_from_meta = float(metrics.get("development_budget", 0))
                    if dev_from_meta > 0:
                        development_total = dev_from_meta
                        recurrent_total = float(
                            metrics.get(
                                "recurrent_budget", total_allocated - dev_from_meta
                            )
                        )

                payload = {
                    "id": county_id,
                    "name": cname,
                    "code": official_county_code(e.canonical_name),
                    "coordinates": coords,
                    # Absent stays absent — same rule as the list
                    # endpoint above and the comprehensive one below.
                    "population": (pop_data.total_population if pop_data else None),
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
                    # Whether this row's budget is the Controller of
                    # Budget's own CBIRR aggregate or the CRA model —
                    # same rule as the list and /comprehensive, so a
                    # caller cannot get three answers for one county.
                    # null when nothing was published: absence has no
                    # source, and naming one would describe no figure.
                    "budget_source": _budget_provenance(
                        class_by_cat, total_allocated
                    ),
                    "development_budget": development_total,
                    "recurrent_budget": recurrent_total,
                    "sector_breakdown": sector_breakdown,
                    "money_received": money_received,
                    "revenue_collection": revenue_collection,
                    "revenue": _county_revenue_for_lines(budget_lines),
                    "pending_bills": pending_bills,
                    **_county_pending_bills_fields(
                        loans, pending_bills, reporting_date=_pending_reporting_day
                    ),
                    "debt": total_debt,
                    **debt_summary,
                    "gdp": float(gdp_data.gdp_value) if gdp_data else None,
                    "financial_health_score": health_score,
                    "financial_health": _health,
                    "audit_rating": audit_rating,
                    "audit_status": audit_status,
                    "audit_signal": _audit_signal,
                    "last_audit_date": last_audit_date,
                    "last_audit_date_basis": "audited_period_end",
                    "audit_issues": audit_issues,
                    "audit_findings_count": len(audits),
                }
                from services.entity_financials import (
                    financial_summary,
                    publish_county_budget,
                )

                return publish_county_budget(
                    payload,
                    financial_summary(
                        budget_lines,
                        budget_lines[0].period if budget_lines else None,
                    ),
                )
    except HTTPException:
        # Deliberate 404s (unknown county id) must reach the client,
        # not be swallowed into the fallback path below.
        raise
    except Exception as exc:
        logging.exception("DB county details failed for %s", county_id)
        raise HTTPException(status_code=500, detail="Internal server error")


def _official_source(meta: Dict[str, Any], role: str) -> Optional[Dict[str, Any]]:
    """Where ``role``'s name came from, or None when nothing says."""
    prov = meta.get(f"{role}_provenance")
    if not isinstance(prov, dict) or not prov.get("source_url"):
        return None
    return {
        "publisher": prov.get("source"),
        "source_url": prov.get("source_url"),
        "fetched_at": prov.get("fetched_at"),
    }


def _sourced_official(meta: Dict[str, Any], role: str) -> Optional[str]:
    name = meta.get(role)
    if not name or _official_source(meta, role) is None:
        return None
    return name


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

            meta = public_entity_metadata(entity.meta)
            metrics = _resolve_fy_metrics(meta)

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
                # This used to fall through to auto-resolve on a miss, serving
                # a different period than the caller asked for. Same guard as
                # the list endpoints, so all three answer a given year alike.
                requested_period_id = _resolve_requested_county_period_ids(
                    db, fiscal_year
                )[0]
            budget_lines = _entity_period_budget_query(
                db, entity.id, period_id=requested_period_id
            ).all()
            (
                total_allocated,
                total_spent,
                _sector_lines,
                _class_by_cat,
            ) = _split_classification_and_sector_lines(budget_lines)

            # Provenance for the headline budget: does it come from parsed CoB
            # BIRR classification rows, or from the modelled sector/projection
            # split? The frontend renders both of these — the prose under the
            # figure and, from the code, the standing provenance note at the
            # top of the page — so they must track the rows this response
            # actually used.
            _budget_source = _budget_provenance(_class_by_cat, total_allocated)
            _budget_provenance_label = _BUDGET_PROVENANCE_LABELS.get(_budget_source)

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
            for bl in _sector_lines:
                cat = (bl.category or "Other").strip()
                amt = float(bl.allocated_amount or 0)
                spent = float(bl.actual_spent or 0)
                sector_breakdown.setdefault(cat, {"allocated": 0.0, "spent": 0.0})
                sector_breakdown[cat]["allocated"] += amt
                sector_breakdown[cat]["spent"] += spent

            # Development vs recurrent — same rule as GET /counties.
            #
            # This used to re-derive the split by keyword over EVERY row, which
            # counted the CoB aggregates and the sector rows that restate them,
            # and dropped the CoB "Total" row into recurrent (the guard tested
            # for "total budget", but the BIRR row is labelled "Total"). On a
            # KES 20B county that produced development 6B + recurrent 51B.
            #
            # Prefer the authoritative classification aggregates the helper
            # already extracted; fall back to the sector-keyword heuristic only
            # when a period carries no classification rows at all.
            development_total = _class_by_cat.get("development", {}).get(
                "allocated", 0.0
            )
            recurrent_total = _class_by_cat.get("recurrent", {}).get("allocated", 0.0)

            if development_total == 0 and recurrent_total == 0:
                keyword_dev = 0.0
                keyword_rec = 0.0
                for bl in _sector_lines:
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
                        keyword_dev += amt
                    else:
                        keyword_rec += amt
                development_total = keyword_dev
                recurrent_total = keyword_rec

            if development_total == 0 and recurrent_total == 0 and total_allocated > 0:
                development_total = float(metrics.get("development_budget", 0))
                recurrent_total = float(metrics.get("recurrent_budget", 0))

            # --- Loans / Debt ---
            # Keep ALL loans in the local list — the per-loan
            # ``debt_breakdown`` and ``pending_bills_from_loans``
            # blocks below both iterate it. Only the total filters out
            # PENDING_BILLS (see ``_is_debt_loan`` for why).
            # joinedload: the publication gate below reads each loan's source
            # document, so resolve them in one query rather than N+1.
            from services.county_debt import county_debt_rows

            loans = county_debt_rows(db, [entity.id])

            # Publication gate. A county row naming a creditor that only lends
            # to sovereigns, with no source document behind it, is withheld —
            # from the breakdown AND from the total, so the parts still sum to
            # the whole. See publication_gate.county_debt_instrument_failure.
            from services.publication_gate import county_debt_instrument_failure

            _withheld_debt: dict = {}
            _publishable_loans = []
            for _l in loans:
                _reason = county_debt_instrument_failure(_l)
                if _reason:
                    _withheld_debt[_reason] = _withheld_debt.get(_reason, 0) + 1
                    logging.warning(
                        "county debt row withheld (%s): entity=%s lender=%r "
                        "outstanding=%s",
                        _reason,
                        entity.id,
                        _l.lender,
                        _l.outstanding,
                    )
                    continue
                _publishable_loans.append(_l)
            _pending_reporting_day = county_pending_reporting_date(db)
            loans = county_loans_at_reporting_date(
                _publishable_loans, _pending_reporting_day
            )

            from services.financial_publication import (
                county_debt_summary, county_debt_instrument_fields, eligible_county_debt_rows,
            )

            debt_summary = county_debt_summary(loans)
            total_debt = debt_summary["total_debt"]

            # Same filter as total_debt above: pending bills are an arrears
            # balance, not borrowing, and they already have their own panel via
            # ``pending_bills``. Including them here made the breakdown sum to
            # more than the total the page prints beside it.
            debt_breakdown = []
            for loan in eligible_county_debt_rows(loans):
                debt_breakdown.append(
                    {
                        "lender": loan.lender,
                        "category": (
                            loan.debt_category.value if loan.debt_category else "other"
                        ),
                        **county_debt_instrument_fields(loan),
                        "currency": loan.currency,
                        "source_document_id": loan.source_document_id,
                        "page_ref": loan.page_ref,
                        "basis": loan.basis.value if loan.basis else None,
                        "provenance": loan.provenance,
                    }
                )

            # Pending bills from SOURCED Loan rows only. The two meta rungs
            # that used to follow were both the same modelled figure, so the
            # chain could never fail to produce a number — including for a
            # county that told the Treasury nothing.
            pending_bills = county_pending_bills(loans)

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

            # The finding's own heading, for the "key challenges" labels.
            _finding_titles: Dict[int, str] = {}
            _extracted: Dict[int, dict] = {}
            _extraction_records = {}
            _ext_ids = [a.extraction_id for a in audits if a.extraction_id]
            if _ext_ids:
                from models import Extraction as _DBExtraction

                for _ext in db.query(_DBExtraction).filter(
                    _DBExtraction.id.in_(_ext_ids)
                ):
                    _extraction_records[_ext.id] = _ext
                    _extracted[_ext.id] = extraction_payload(_ext.extracted_json)
                    _title = _extracted[_ext.id].get("title")
                    if _title:
                        _finding_titles[_ext.id] = str(_title)

            _audit_docs = {
                d.id: d for d in db.query(DBSourceDocument).filter(
                    DBSourceDocument.id.in_({a.source_document_id for a in audits})
                )
            }
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
                        "audited_entity_name": audited_institution(
                            _extracted.get(a.extraction_id), county_name=entity.canonical_name,
                            document_meta=_audit_docs[a.source_document_id].meta if a.source_document_id in _audit_docs else None,
                        ),
                        "page_ref": a.page_ref,
                        "source_url": report_page_url(
                            _audit_docs[a.source_document_id].url if a.source_document_id in _audit_docs else None, a.page_ref,
                        ),
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

            _audit_signal = county_audit_signals(
                db, [entity.id], display_grade=_audit_is_display_grade
            )[entity.id]
            audit_status = _audit_signal["status"]

            # Financial health — one disclosed composite, shared with the
            # /counties list endpoint so the listing's Health column and this
            # page's HEALTH badge cannot disagree. There is no cached score to
            # fall back to any more: entity.meta["financial_metrics"] held a
            # constant 75.0 for 40 of the 47 counties and has been deleted.
            #
            # The formula this replaces was a piecewise transform of
            # utilisation alone, and returned 0.0 — grade "C" — for a county
            # with no budget data at all.
            from services.entity_financials import financial_summary

            _published_budget = financial_summary(
                budget_lines, budget_lines[0].period if budget_lines else None
            )
            _health_revenue = _county_revenue_for_lines(budget_lines)
            _health = county_financial_health(
                total_allocated=_published_budget["total_allocation"],
                total_spent=_published_budget["total_spent"],
                pending_bills=pending_bills
                if pending_budget_compatible(
                    loans,
                    _published_budget["fiscal_period"],
                    budget_currency=_published_budget["currency"],
                )
                else None,
                audit_status=audit_status,
                own_source_target=_health_revenue["own_source_target"],
                own_source_actual=_health_revenue["local_revenue"],
            )
            health_score = _health["score"] if _health else None
            grade = _health["grade"] if _health else None

            # Disclose the actual numerator and denominator of this site's
            # index. Absent components have no effective weight; a reported
            # zero remains an included component.
            _own_source_target = _health_revenue["own_source_target"]
            _own_source_actual = _health_revenue["local_revenue"]
            _available = {
                "budget_absorption": _published_budget["total_allocation"] is not None
                and _published_budget["total_allocation"] > 0
                and _published_budget["total_spent"] is not None,
                "own_source_revenue": _own_source_target is not None
                and _own_source_target > 0
                and _own_source_actual is not None,
                "pending_bills": _published_budget["total_allocation"] is not None
                and _published_budget["total_allocation"] > 0
                and pending_bills is not None
                and pending_budget_compatible(
                    loans,
                    _published_budget["fiscal_period"],
                    budget_currency=_published_budget["currency"],
                ),
                "audit_opinion": audit_status in _AUDIT_OPINION_SCORES,
            }
            _unavailable_reasons = {
                "budget_absorption": (
                    _published_budget["absent_reasons"].get("total_allocation")
                    or _published_budget["absent_reasons"].get("total_spent")
                    or "no_positive_allocation"
                ),
                "own_source_revenue": (
                    "target_not_reported"
                    if _own_source_target is None
                    else "no_positive_target"
                    if _own_source_target <= 0
                    else "actual_not_reported"
                ),
                "pending_bills": (
                    "budget_unavailable"
                    if _published_budget["total_allocation"] is None
                    or _published_budget["total_allocation"] <= 0
                    else "pending_budget_period_mismatch"
                    if pending_bills is not None
                    else (
                        county_pending_bills_details(loans).get("absent_reason")
                        if loans
                        else None
                    )
                    or "pending_bills_not_reported"
                ),
                "audit_opinion": _audit_signal["absent_reason"],
            }
            _unavailable = [
                {"name": name, "reason": _unavailable_reasons[name]}
                for name in _HEALTH_COMPONENT_WEIGHTS if not _available[name]
            ]
            _budget_doc = (
                _published_budget["sources"][0]
                if len(_published_budget["sources"]) == 1 else None
            )
            _osr_sources = [
                source for source in _health_revenue["sources"]
                if source["measure"] == _health_revenue["local_revenue_basis"]
            ]
            _osr_source = _osr_sources[0] if len(_osr_sources) == 1 else None
            _pending_details = (
                county_pending_bills_details(loans) if pending_bills is not None else {}
            )
            _pending_rows = select_county_pending_bills(loans)["rows"]
            _pending_periods = sorted({
                str(_pending_bills_provenance(loan).get("fiscal_year"))
                for loan in _pending_rows
                if _pending_bills_provenance(loan).get("fiscal_year")
            })
            _pending_dates = sorted({
                date for loan in _pending_rows
                if (date := pending_bills_row_as_at(loan))
            })
            _pending_urls = {
                url if isinstance(url, str) else None
                for loan in _pending_rows
                for url in [_pending_bills_provenance(loan).get("source_url")]
            }
            _pending_warning = (
                "mixed_pending_periods"
                if len(_pending_periods) > 1 or len(_pending_dates) > 1
                else "mixed_pending_sources" if len(_pending_urls) > 1 else None
            )
            _component_source = {
                "budget_absorption": (
                    budget_fy_label,
                    _budget_doc.get("url") if _budget_doc else None,
                    None,
                ),
                "own_source_revenue": (
                    _health_revenue["fiscal_year"],
                    _osr_source["url"] if _osr_source else None,
                    None,
                ),
                "pending_bills": (
                    _pending_details.get("fiscal_year")
                    if not _pending_warning
                    else None,
                    _pending_details.get("source_url")
                    if not _pending_warning
                    else None,
                    _pending_details.get("as_at") if not _pending_warning else None,
                ),
                "audit_opinion": (
                    _audit_signal["source_period"],
                    _audit_signal["source_url"],
                    None,
                ),
            }
            _health_components = [
                {
                    **component,
                    "source_period": _component_source[component["name"]][0],
                    "source_url": _component_source[component["name"]][1],
                    "as_at": _component_source[component["name"]][2],
                    "measurement_basis": (
                        _health_revenue["local_revenue_basis"]
                        if component["name"] == "own_source_revenue"
                        else "finding_severity"
                        if component["name"] == "audit_opinion"
                        else None
                    ),
                    "source_periods": (
                        _pending_periods
                        if component["name"] == "pending_bills" and _pending_warning
                        else []
                    ),
                    "source_dates": (
                        _pending_dates
                        if component["name"] == "pending_bills" and _pending_warning
                        else []
                    ),
                    "source_warning": (
                        _pending_warning
                        if component["name"] == "pending_bills"
                        else None
                    ),
                }
                for component in (_health["components"] if _health else [])
            ]
            _health_disclosure = {
                "score": health_score,
                "grade": grade,
                "audit_signal": _audit_signal,
                "selection_policy": "latest_common_pending_date_and_latest_executive_audit_period",
                "weighting": "audit_opinion_weighted",
                "weights": dict(_HEALTH_COMPONENT_WEIGHTS),
                "effective_weight": sum(c["weight"] for c in _health_components),
                "components": _health_components,
                "available_inputs": [
                    name for name in _HEALTH_COMPONENT_WEIGHTS if _available[name]
                ],
                "unavailable_inputs": _unavailable,
                "minimum_components": _MIN_HEALTH_COMPONENTS,
                "absent_reason": None if _health else "fewer_than_two_components",
            }

            # --- Missing funds ---
            # The same derivation as /accountability/missing-funds (issue
            # #233): findings the Auditor-General titled "Unaccounted …" or
            # "Loss of Funds", with their page. These used to be hand-written
            # cases on entity.meta that cited no document and were withheld
            # on every request. No total: no matched finding carries an
            # extracted amount, and a stored one may be the account balance.
            _unaccounted = derive_unaccounted_cases(db, entity_ids=[entity.id])
            missing_funds_cases = _unaccounted["cases"]
            missing_funds_withheld = _unaccounted["withheld"]

            # --- Stalled projects ---
            # Evidence-gated: only rows that name their document, page, as-of
            # date and reporter are published (issue #230).
            # OAG findings about unfinished projects corroborate COB's rows
            # (or stand alone), in the Auditor-General's own words.
            _stored_meta = entity.meta if isinstance(entity.meta, dict) else {}
            stalled_block = build_stalled_projects_block(
                _stored_meta.get("stalled_projects"),
                oag_findings=stalled_oag_findings(
                    audits, _extracted, extraction_records=_extraction_records,
                    documents=_audit_docs, county_name=entity.canonical_name,
                ),
                historical_audits=audits, historical_extractions=_extraction_records,
                historical_documents=_audit_docs,
                county_name=entity.canonical_name,
            )

            # --- Revenue ---
            # Own-source revenue as the Controller of Budget reports it. Both
            # meta rungs this replaces were the same figure: 0.85 x a modelled
            # budget, four times what the 47 counties actually collect.
            local_revenue = county_own_source_revenue(budget_lines)
            # What the county RECEIVED, stream by stream, from the same
            # report's Chapter 3 revenue table. total_revenue used to be the
            # own-source figure above under another name, and equitable_share
            # the budget minus it — a residual nobody published.
            revenue_receipts = county_revenue_receipts(budget_lines)

            # --- Coordinates ---
            coords = COUNTY_COORDINATES.get(
                legacy_county_route_id(entity.canonical_name)
            )

            # --- Per-capita stats ---
            # The census row, or nothing — the rule the four sibling county
            # endpoints already follow. The second rung this replaces read
            # entity.meta.metrics[FY]["population"], bootstrap's copy of the
            # same KNBS 2019 count out of enhanced_county_data.json. The count
            # is real; what it lacks is everything that makes it citable. It
            # arrives with no source document and no year, so it would print
            # beside the population_year, sex split and density directly below
            # — all of which correctly report absence — and the same county
            # would answer 866,820 here and null on /counties, /counties/{id},
            # /summary and its accountability bracket. And when even the meta
            # copy was missing, `, 0)` published the claim that nobody lives
            # there. 2760328 verified against production that all 47 counties
            # have a PopulationData row, so this rung is unreachable today.
            population = pop.total_population if pop else None
            # A share of a budget cannot be computed without a denominator,
            # and 0 is not the answer to "what is each resident's share?" —
            # it is the answer to a question nobody asked.
            per_capita_budget = (
                round(total_allocated / population, 2)
                if population
                else None
            )
            per_capita_debt = (
                round(total_debt / population, 2)
                if total_debt is not None and population
                else None
            )

            # A budget execution rate alone is not a historical health index.
            # Dated audit/OSR/pending-bill components are not assembled here.
            # Keep the health sparkline absent and publish the budget history
            # under its own measure, using the same dated accounting contract.
            from services.entity_financials import entity_financial_series

            today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
            completed_budgets = [
                summary
                for summary in entity_financial_series(db, [entity.id]).get(entity.id, [])
                if summary["fiscal_period"]
                and summary["fiscal_period"]["end_date"]
                and summary["fiscal_period"]["end_date"][:10] < today
            ]
            budget_execution_history = list(reversed(completed_budgets[:6]))
            health_history = []

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
                # Officials: published only with a publisher behind them
                # (issue #231). bootstrap writes a governor from
                # enhanced_county_data.json with no provenance; the
                # county_officials domain writes both roles from the
                # Council of Governors with provenance. A name without
                # provenance is one nobody can check, and an election can
                # have made it wrong, so it is withheld.
                "governor": _sourced_official(meta, "governor"),
                "deputy_governor": _sourced_official(meta, "deputy_governor"),
                "officials_source": {
                    role: _official_source(meta, role)
                    for role in ("governor", "deputy_governor")
                },
                # Economic profile
                #
                # county_type, infrastructure_level and revenue_potential are
                # gone. They came from enhanced_county_data.json — typed
                # classifications with no publisher behind them, defaulted
                # here to "standard_county" / "medium" / "medium" for anything
                # missing — and nothing in the UI rendered any of the three.
                #
                # economic_base is withheld for the same reason: "agriculture"
                # for 42 of the 47 counties is somebody's judgement, not a
                # figure anyone published. KNBS's Gross County Product would
                # support it; the fixture does not.
                #
                # major_issues was the same four strings for ALL 47 counties
                # ("Budget execution delays", "Revenue collection challenges",
                # "Infrastructure maintenance needs", "Service delivery
                # gaps"), rendered under "Key Challenges" beside a note
                # admitting they were not this county's. The Auditor-General's
                # own findings for this county are right here in `audits`, so
                # they are what gets served.
                "economic_profile": {
                    "economic_base": None,
                    "major_issues": _county_major_issues(audits, _finding_titles),
                    "major_issues_source": (
                        "Office of the Auditor-General" if audits else None
                    ),
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
                    # "cob_cbirr" | "cra_model" | null. The page's provenance
                    # note is rendered from this, so a period showing the
                    # Controller of Budget's own aggregates stops being
                    # described to the reader as a CRA model.
                    "source": _budget_source,
                },
                # Revenue — see county_revenue_block.
                "revenue": _county_revenue_for_lines(budget_lines),
                # Debt
                "debt": {
                    **debt_summary,
                    "pending_bills": pending_bills,
                    # The day the figure is a stock on and what the report
                    # says about it, both from the rows behind it; null / []
                    # when no figure is published (#238).
                    **_county_pending_bills_fields(
                        loans,
                        pending_bills,
                        reporting_date=_pending_reporting_day,
                        absence=(
                            _county_pending_bills_absence(db, entity)
                            if pending_bills is None
                            else None
                        ),
                    ),
                    # Final budget publication computes this against the supported
                    # account's exact period/currency, not the legacy rollup.
                    "debt_to_budget_ratio": None,
                    "debt_to_budget_ratio_absent_reason": "awaiting_budget_compatibility",
                    "per_capita_debt": per_capita_debt,
                    "breakdown": debt_breakdown,
                    # How many instrument rows the publication gate held back,
                    # and why. Never silently dropped: a reader (or a caller)
                    # can tell "this county has no external debt" from "we are
                    # not willing to publish the row we hold".
                    "withheld": _withheld_debt or None,
                },
                # Audit — findings array is always included so downstream
                # tab components can iterate safely. An earlier experiment
                # gated this behind `?include_findings=true` for a ~5KB
                # payload saving; that broke the Audit tab (iterated
                # `audit.findings` directly) so the saving wasn't worth
                # the correctness cost. Kept shipping the full list.
                "audit": {
                    "status": audit_status,
                    "signal": _audit_signal,
                    "grade": grade,
                    "health_score": health_score,
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
                "health_history_absent_reason": "dated_health_components_unavailable",
                "budget_execution_history": budget_execution_history,
                # Missing funds
                "missing_funds": {
                    "basis": "oag_finding_title",
                    "total_amount": None,
                    "total_amount_reason": "no_amount_extracted",
                    "cases_count": len(missing_funds_cases),
                    "cases": missing_funds_cases,
                    "reason": None if missing_funds_cases else "no_matching_findings",
                    "withheld": {
                        "count": sum(missing_funds_withheld.values()),
                        "by_reason": missing_funds_withheld,
                    },
                },
                # Stalled projects
                "stalled_projects": stalled_block,
                # Financial summary
                "financial_summary": {
                    "health_score": health_score,
                    "grade": grade,
                    "budget_execution_rate": round(
                        (
                            (total_spent / total_allocated * 100)
                            if total_allocated > 0
                            else 0
                        ),
                        1,
                    ),
                    # A ratio needs both its inputs. When no publisher has
                    # reported this county's pending bills the share of budget
                    # they represent is unknown, not 0.0 — the same rule the
                    # debt-service series follows.
                    "pending_bills_ratio": (
                        round(pending_bills / total_allocated * 100, 1)
                        if pending_bills is not None
                        and total_allocated > 0
                        and pending_budget_compatible(
                            loans,
                            _published_budget["fiscal_period"],
                            budget_currency=_published_budget["currency"],
                        )
                        else None
                    ),
                    # An assessment needs a debt figure. With no published
                    # one this used to read the absent value as 0 and return
                    # "sustainable" — the most reassuring of the three labels,
                    # asserted about a county nobody has measured.
                    "debt_sustainability": _debt_sustainability(
                        total_debt, total_allocated
                    ),
                },
                "financial_health": _health_disclosure,
                # Data provenance
                # Provenance labels, not aspirations. Three of these named a
                # publisher who did not publish the figure underneath: county
                # budget lines are modelled from the CRA equitable-share
                # formula (the page's own disclaimer says so, while this field
                # said CoB); county debt rows carry no source document at all;
                # and the stalled-projects fixture was never read from an OAG
                # report — it was deleted in #230; the block now carries COB's
                # own tables with per-row provenance, and the Projects tab
                # stays withdrawn until that is reviewed. Credibility audit
                # F7/F15/F6.
                "data_sources": {
                    # Derived from the rows actually selected, not asserted.
                    # This field used to hardcode "modelled from CRA", which
                    # became wrong once the endpoint started preferring real CoB
                    # classification rows for the headline: it denied the
                    # provenance of figures that DO come from a published BIRR.
                    # Only the sector split and projection periods are modelled.
                    "budget": _budget_provenance_label,
                    "audit": "Office of the Auditor General - County Government Audit Reports",
                    # From the rows this response published, not asserted.
                    # It read "Modelled — … not traced to a county or National
                    # Treasury publication" for every county while the pending
                    # bills beside it were a publication's own figures.
                    "debt": county_debt_provenance_label(loans, total_debt),
                    "population": "Kenya National Bureau of Statistics (KNBS) Census 2019",
                },
            }

            from services.entity_financials import (
                financial_summary,
                publish_county_budget,
            )

            publish_county_budget(
                response,
                financial_summary(
                    budget_lines, budget_lines[0].period if budget_lines else None
                ),
                comprehensive=True,
            )
            return response

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in comprehensive county endpoint for {county_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/api/v1/counties/{county_id}/financial")
@county_database_required
@cached(key_prefix="county:financial", ttl=1800)
async def get_county_financial_data(county_id: str):
    """The selected source-supported county account, including explained absence.

    Like /budget, this selects the supported period and does not interpret an
    optional fiscal_year query as a requested account. No analytics proxy runs.
    """
    account = await get_county_budget(county_id)
    return {
        "county_id": county_id,
        "county_name": account["county_name"],
        "financial_data": account["financial_summary"],
    }


@app.get("/api/v1/counties/{county_id}/budget")
async def get_county_budget(county_id: str):
    """Publish the same dated, source-supported account as county list/detail.

    Historical field names are retained as aliases; the financial summary
    carries the actual period, source, accounting basis and absence reasons.
    The retired analytics proxy cannot supply a reported budget.
    This route selects the supported period; fiscal_year query parameters are
    not interpreted. Read fiscal_period for the actual selected account.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    from services.entity_financials import financial_summary, publish_county_budget

    try:
        with next(get_db()) as db:
            entity = _resolve_county_entity(db, county_id)
            if entity is None or official_county_code(entity.canonical_name) is None:
                raise HTTPException(status_code=404, detail="County not found")
            budget_lines = _entity_period_budget_query(db, entity.id).all()
            summary = financial_summary(
                budget_lines, budget_lines[0].period if budget_lines else None
            )
            response = {
                "county_id": county_id,
                "county_name": entity.canonical_name.removesuffix(" County"),
                "budget_execution_rate": summary["execution_rate"],
                "revenue_2024": county_own_source_revenue(budget_lines),
                "expenditure_breakdown": {},
                "budget_allocation": {},
                "fiscal_period": summary["fiscal_period"],
                "sources": summary["sources"],
                "accounting_basis": summary["accounting_basis"],
                "currency": summary["currency"],
                "absent_reasons": summary["absent_reasons"],
            }
            return publish_county_budget(response, summary)
    except HTTPException:
        raise
    except Exception:
        logging.exception("Error fetching budget for county %s", county_id)
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

                from services.county_debt import county_debt_rows
                from services.financial_publication import (
                    county_debt_summary, county_debt_instrument_fields, eligible_county_debt_rows,
                )

                all_loans = county_debt_rows(db, [e.id])
                loans = eligible_county_debt_rows(all_loans)
                debt_summary = county_debt_summary(loans)
                total_outstanding = debt_summary["total_debt"]
                principals = [county_debt_instrument_fields(l)["principal"] for l in loans]
                total_principal = (
                    sum(principals) if principals and all(v is not None for v in principals)
                    and total_outstanding is not None else None
                )

                budget_rows = _entity_period_budget_query(db, e.id).all()
                revenue = county_own_source_revenue(budget_rows)

                debt_to_revenue = (
                    round(total_outstanding / revenue * 100, 1)
                    if total_outstanding is not None and revenue is not None and revenue > 0
                    else None
                )

                # A withheld cohort cannot produce a contradictory numeric breakdown.
                breakdown = {}
                if total_outstanding is not None:
                    for loan in loans:
                        lender = loan.lender or "Other"
                        amount = county_debt_instrument_fields(loan)["outstanding"]
                        if amount is not None:
                            breakdown[lender] = breakdown.get(lender, 0) + amount

                sustainability = None
                if debt_to_revenue is not None:
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
                    **debt_summary,
                    "debt_outstanding": total_outstanding,
                    "debt_principal": total_principal,
                    "pending_bills": county_pending_bills(all_loans),
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


def _plain_kes_amount_in_audit_text(
    finding_text: Optional[str],
) -> Tuple[Optional[Decimal], bool]:
    """Read a whole plain KES integer, or report ambiguous amount text.

    A value is accepted only when the full plain integer ends the text. The
    second result marks a mentioned figure needing source review, keeping it
    distinct from a finding that states no amount at all.
    """
    if not finding_text:
        return None, False
    mentions = list(re.finditer(r"\bKES(?P<gap>\s*)(?=\d)", finding_text, re.I))
    if not mentions:
        return None, False
    if (
        len(mentions) != 1
        or mentions[0].group()[:3] != "KES"
        or not re.fullmatch(r"[ \t]+", mentions[0].group("gap"))
    ):
        return None, True
    tail = finding_text[mentions[0].end():]
    # Consume the *whole* number-shaped span. A regex for only the allowed
    # prefix would turn "1 200" into 1 and "50 M" into 50.
    match = re.match(r"\d[\d,.\s\u200b]*", tail)
    if not match:
        return None, True
    number_text = match.group().strip()
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", number_text):
        return None, True
    # Any continuation can qualify the unit, as in "KES 50 in millions".
    # Do not certify a numeric prefix without source review.
    if tail[match.end():]:
        return None, True
    return Decimal(number_text.replace(",", "")), False


@app.get("/api/v1/audits/statistics")
@cached(key_prefix="audits:statistics", ttl=3600)
async def get_audit_statistics():
    """Aggregate institution-wide audit findings for the dashboard.

    County coverage and ranking count eligible Kenyan counties only; severity
    and amount totals retain all eligible institutions from the Audit table.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        with next(get_db()) as db:
            from sqlalchemy import String, case, cast, func

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
                .join(DBCountry, DBEntity.country_id == DBCountry.id)
                .filter(
                    DBAudit.severity == Severity.CRITICAL,
                    DBEntity.type == EntityType.COUNTY,
                    DBCountry.iso_code == "KEN",
                )
                .group_by(DBEntity.id, DBEntity.canonical_name)
                .order_by(func.count(DBAudit.id).desc(), DBEntity.id.asc())
                .limit(5)
                .all()
            )

            # Recent critical findings (most recent 6)
            recent_critical = (
                db.query(DBAudit, DBEntity.canonical_name, DBFiscalPeriod.label)
                .filter(publishable_audit_criterion())
                .join(DBEntity, DBAudit.entity_id == DBEntity.id)
                .outerjoin(DBFiscalPeriod, DBAudit.period_id == DBFiscalPeriod.id)
                .filter(DBAudit.severity == Severity.CRITICAL)
                .order_by(DBAudit.created_at.desc(), DBAudit.id.desc())
                .limit(6)
                .all()
            )

            recent_items = []
            for audit, entity_name, period_label in recent_critical:
                amount = None
                amount_unavailable_reason = None
                if audit.amount is not None:
                    try:
                        candidate = float(audit.amount)
                    except (TypeError, ValueError, OverflowError):
                        candidate = math.inf
                    if math.isfinite(candidate):
                        amount = candidate
                    else:
                        amount_unavailable_reason = "invalid_stored_amount"
                else:
                    legacy_amount, ambiguous_text = _plain_kes_amount_in_audit_text(
                        audit.finding_text
                    )
                    if legacy_amount is not None:
                        try:
                            candidate = float(legacy_amount)
                        except (OverflowError, ValueError):
                            candidate = math.inf
                        if math.isfinite(candidate):
                            amount = candidate
                        else:
                            amount_unavailable_reason = "non_finite_text_amount"
                    elif ambiguous_text:
                        amount_unavailable_reason = "ambiguous_text_amount"
                recent_items.append(
                    {
                        "id": audit.id,
                        # Keep the legacy key for existing readers; the neutral
                        # name preserves institution identity for new consumers.
                        "county": entity_name.replace(" County", ""),
                        "entity_name": entity_name,
                        "finding": audit.finding_text,
                        "severity": (
                            audit.severity.value if audit.severity else "unknown"
                        ),
                        "amount": amount,
                        "amount_unavailable_reason": amount_unavailable_reason,
                        "fiscal_year": period_label or "",
                        "date": (
                            audit.created_at.isoformat() if audit.created_at else None
                        ),
                    }
                )

            # Coverage has a Kenyan county denominator; institution-wide
            # finding and money totals above/below keep their broader scope.
            counties_audited = (
                db.query(func.count(func.distinct(DBAudit.entity_id)))
                .join(DBEntity, DBAudit.entity_id == DBEntity.id)
                .join(DBCountry, DBEntity.country_id == DBCountry.id)
                .filter(
                    publishable_audit_criterion(),
                    DBEntity.type == EntityType.COUNTY,
                    DBCountry.iso_code == "KEN",
                )
                .scalar() or 0
            )

            # PostgreSQL numeric accepts NaN. One such row poisons SUM, so
            # exclude non-finite stored values *inside* the aggregate. Count
            # them separately rather than hiding their missing coverage.
            from services.audit_amounts import finite_audit_amount

            finite_amount = finite_audit_amount(DBAudit.amount)
            amount_from_col, structured_count, stored_count = (
                db.query(
                    func.sum(finite_amount),
                    func.count(finite_amount),
                    func.count(DBAudit.amount),
                )
                .filter(publishable_audit_criterion())
                .one()
            )
            invalid_count = stored_count - structured_count
            if invalid_count:
                logger.warning(
                    "Withholding invalid stored amounts from /audits/statistics: %s findings",
                    invalid_count,
                )
            # Regex fallback only over rows where amount is NULL.
            fallback_amount = Decimal(0)
            fallback_count = 0
            ambiguous_text_count = 0
            for (text_val,) in (
                db.query(DBAudit.finding_text)
                .filter(publishable_audit_criterion())
                .filter(DBAudit.amount.is_(None))
                .yield_per(500)
            ):
                legacy_amount, ambiguous_text = _plain_kes_amount_in_audit_text(text_val)
                if legacy_amount is not None:
                    fallback_amount += legacy_amount
                    fallback_count += 1
                elif ambiguous_text:
                    ambiguous_text_count += 1
            findings_with_amount = structured_count + fallback_count
            total_amount = None
            total_amount_reason = None
            if findings_with_amount:
                amount_decimal = (amount_from_col or Decimal(0)) + fallback_amount
                try:
                    candidate = float(amount_decimal)
                except (OverflowError, ValueError):
                    candidate = math.inf
                if math.isfinite(candidate):
                    total_amount = candidate
                else:
                    logger.warning("Withholding non-finite audit statistics total")
                    total_amount_reason = "non_finite_total"
            else:
                total_amount_reason = (
                    "invalid_stored_amount"
                    if invalid_count
                    else "ambiguous_text_amount"
                    if ambiguous_text_count
                    else "no_amounts_recorded"
                )
            # This is the number without a usable numeric amount; ambiguous
            # KES text is a disclosed subset, not evidence that no sum was stated.
            findings_without_amount = total - findings_with_amount - invalid_count

            _withheld_stats = count_withheld_audits(db)
            # Not just how many, but why. The breakdown existed and had no
            # caller, so the API published a withheld count a reader could do
            # nothing with — and the three causes want fixes from three
            # different people: a URL for the document, an OCR pass, a page.
            _withheld_reasons = count_withheld_by_reason(db)
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
                "withheld_findings_by_reason": _withheld_reasons,
                "counties_audited": counties_audited,
                "total_counties": 47,
                "total_amount_flagged": total_amount,
                "total_amount_flagged_reason": total_amount_reason,
                "findings_with_amount": findings_with_amount,
                "findings_with_invalid_amount": invalid_count,
                "findings_with_ambiguous_text_amount": ambiguous_text_count,
                "findings_without_amount": findings_without_amount,
                "by_severity": by_severity,
                "top_flagged_counties": [
                    {"county": name.replace(" County", ""), "critical_count": count}
                    for name, count in top_flagged
                ],
                "recent_critical": recent_items,
                "report_title": "Office of the Auditor General — Institution-wide Audit Findings",
                # NOTE: derived from the latest period actually present in the
                # Audit table. Returns None when the table is empty so the UI
                # can show an honest "no audit data yet" state instead of a
                # stale hardcoded label.
                "fiscal_year": latest_period_label,
                "fiscal_years_covered": fiscal_years_covered,
                "_meta": _response_meta(
                    unit="kes",
                    entity_scope="all",
                    scope_detail=(
                        "Findings, severity, finite amount totals and recent critical items "
                        "include all institution types and all countries across all covered fiscal periods. "
                        "County coverage and top_flagged_counties include eligible Kenyan COUNTY entities only. "
                        "Fiscal year identifies the latest covered period; amount coverage is reported separately."
                    ),
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
@cached(key_prefix="audits:fiscal_years", ttl=NIGHTLY_REFRESH_TTL)
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
            from services.publication_gate import publishable_fiscal_summaries

            # page_ref is selected because the gate reads it. Offering a year
            # in the selector whose figures are then withheld is its own small
            # dishonesty — the reader picks it and gets nothing.
            summaries = (
                db.query(FiscalSummary.fiscal_year, FiscalSummary.page_ref)
                .order_by(FiscalSummary.fiscal_year.desc())
                .all()
            )
            years = [
                row.fiscal_year
                for row in publishable_fiscal_summaries(summaries)
                if row.fiscal_year
            ]
        return {"status": "success", "data": years}
    except Exception as e:
        logger.error(f"Error fetching fiscal years: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# The Blue Book covers ministries, state departments, commissions and
# independent offices (Article 229). The federal panel must show all of
# them; "Top Ministries" below stays MINISTRY-only by design.
FEDERAL_AUDIT_ENTITY_TYPES = [
    EntityType.MINISTRY,
    EntityType.NATIONAL,
    EntityType.COMMISSION,
    EntityType.AGENCY,
]


def select_top_stated_findings(findings: List[dict], n: int) -> List[dict]:
    """The findings the homepage lists: the ``n`` largest STATED amounts.

    The same rule as the frontend's ``trimFederalAuditsForHome``
    (``frontend/lib/react-query/useAudits.ts``), and pinned to it by one cases
    file both test suites read
    (``frontend/__tests__/fixtures/federalTopStatedFindings.cases.json``):

    - a finding states an amount unless ``amount_numeric`` is null or
      ``amount_involved`` is exactly ``"KES 0"`` (what this endpoint writes for
      a stored zero). Unstated findings are left out, never sorted as 0;
    - largest first; ``sorted`` is stable, so ties keep the API's order, as
      ``Array.prototype.sort`` does;
    - if nothing is stated but findings exist, the first one is kept, so the
      list is not empty. An empty list switches the section to "no findings
      can be published yet", which would be false.

    Returns a new list and leaves ``findings`` (the cached payload's list) as
    it was.
    """
    stated = [
        f
        for f in findings
        if f.get("amount_involved") != "KES 0" and f.get("amount_numeric") is not None
    ]
    top = sorted(stated, key=lambda f: f["amount_numeric"], reverse=True)[:n]
    if not top and findings:
        return findings[:1]
    return top


_FEDERAL_PROVENANCE_TEXT_FIELDS = (
    "amount_involved", "status", "category", "query_type",
    "report_section", "date_raised", "title", "source_url",
)
# A provenance-only figure above 100 times the modeled Audit.amount column's
# range is not safely publishable as a numeric amount. Keep its linked finding
# available, but mark the metadata invalid for review against the source PDF.
_MAX_FEDERAL_PROVENANCE_KES = 1_000_000_000_000_000


def _federal_audit_metadata(value) -> Tuple[dict, str, Optional[float]]:
    """Read optional legacy finding metadata without promoting malformed JSON.

    The linked SourceDocument and Audit.page_ref remain the citation authority.
    A malformed metadata container or claimed field invalidates the whole
    metadata entry, but never removes an otherwise publishable finding.
    """
    if value is None or value == [] or value == {}:
        return {}, "absent", None
    if isinstance(value, dict):
        entries = [value]
    elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        entries = value
    else:
        return {}, "invalid", None

    metadata = entries[0]
    if any(
        entry.get(field) is not None and not isinstance(entry[field], str)
        for entry in entries
        for field in _FEDERAL_PROVENANCE_TEXT_FIELDS
        if field in entry
    ):
        return {}, "invalid", None

    selected_amount = None
    for index, entry in enumerate(entries):
        date_text = entry.get("date_raised")
        if date_text:
            try:
                # Legacy finding metadata gives an ISO calendar date. Treat
                # an impossible date as invalid rather than publishing it.
                datetime.date.fromisoformat(date_text)
            except ValueError:
                return {}, "invalid", None

        amount_text = entry.get("amount_involved") or ""
        if not amount_text:
            continue
        # The public amount range is bounded above. A megabyte-long numeric
        # string can overflow Decimal's exponent while parsing stored JSON.
        if len(amount_text) > 64:
            return {}, "invalid", None
        match = re.fullmatch(
            r"(?:KES\s*)?([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*([TBM]?)",
            amount_text.strip(), re.IGNORECASE,
        )
        if match is None:
            return {}, "invalid", None
        multiplier = {
            "": 1, "M": 1_000_000, "B": 1_000_000_000,
            "T": 1_000_000_000_000,
        }[match.group(2).upper()]
        exact_amount = Decimal(match.group(1).replace(",", "")) * multiplier
        if abs(exact_amount) > _MAX_FEDERAL_PROVENANCE_KES:
            return {}, "invalid", None
        amount = float(exact_amount)
        if not math.isfinite(amount) or (exact_amount != 0 and amount == 0):
            return {}, "invalid", None
        if index == 0:
            selected_amount = amount
    return metadata, "valid" if metadata else "absent", selected_amount


@app.get("/api/v1/audits/federal")
async def get_federal_audits(
    top_findings: Optional[int] = Query(
        None,
        ge=1,
        le=100,
        description=(
            "Return only the N largest findings that state an amount "
            "(see select_top_stated_findings). Every other field still "
            "describes all findings: total_findings is the report's count, "
            "not the number of rows returned. Omit for every finding."
        ),
    ),
):
    """Get national/federal government audit findings from the Auditor General.

    Returns audit findings for ministries, departments and agencies (MDAs),
    plus a ``headline`` derived from the latest report's extracted findings.

    ``?top_findings=N`` is for the homepage, which renders 4 of ~800 findings:
    its client refetch downloaded the whole ~886KB list to throw most of it
    away (#221). The full payload is computed and cached once under the same
    key either way, and the trim is applied to a copy on the way out.
    """
    payload = await _federal_audits_payload()
    if top_findings is None or not isinstance(payload, dict):
        return payload
    return {
        **payload,
        "findings": select_top_stated_findings(payload.get("findings") or [], top_findings),
    }


@cached(key_prefix="audits:federal", ttl=3600)
async def _federal_audits_payload():
    """The full ``/audits/federal`` response: every publishable finding."""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        with next(get_db()) as db:
            from sqlalchemy import func

            # Get all federal findings (MINISTRY + NATIONAL entities)
            # The unparameterized API and aggregation need every published
            # finding. Project their public inputs instead of hydrating every
            # Audit and repeating the Entity's metadata on each joined row.
            federal_audits = (
                db.query(
                    DBAudit.id,
                    DBAudit.finding_text,
                    DBAudit.severity,
                    DBAudit.recommended_action,
                    DBAudit.amount,
                    DBAudit.provenance,
                    DBAudit.page_ref,
                    DBAudit.created_at,
                    DBAudit.source_document_id,
                    DBEntity.canonical_name.label("entity_name"),
                    DBEntity.type.label("entity_type"),
                )
                .filter(publishable_audit_criterion())
                .join(DBEntity, DBAudit.entity_id == DBEntity.id)
                .filter(DBEntity.type.in_(FEDERAL_AUDIT_ENTITY_TYPES))
                .order_by(DBAudit.severity.desc(), DBAudit.created_at.desc())
                .all()
            )

            # A finding's linked document is its citation. Load the URL for
            # every selected document in one batch; provenance may contain a
            # different URL and cannot silently replace that relationship.
            source_document_ids = {a.source_document_id for a in federal_audits}
            source_urls_by_document_id = (
                dict(
                    db.query(DBSourceDocument.id, DBSourceDocument.url)
                    .filter(DBSourceDocument.id.in_(source_document_ids))
                    .all()
                )
                if source_document_ids else {}
            )

            from provenance import vintage_iso

            findings = []
            total_amount = 0.0
            # "no publishable finding carries an amount" is not "the amount is
            # zero". Count recorded amounts so the response can say null
            # instead of 0.0 when coverage is absent (AUDIT_FINDINGS P1).
            findings_with_amount = 0
            findings_with_invalid_amount = 0
            severity_counts = {}

            for audit in federal_audits:
                # Parse amount from provenance or finding_text.
                #
                # amount_val starts as None, not 0.0. Most findings state no
                # figure at all — 764 of production's 813 — and publishing 0.0
                # for those made "the report states no amount here"
                # indistinguishable from "nothing was questioned here", on a
                # SOURCED finding. That is the manufactured zero PR #135
                # existed to remove, in the one field a client is most likely
                # to sum.
                amount_str = ""
                amount_val: Optional[float] = None
                amount_unavailable_reason = None
                status = ""
                category = ""
                query_type = ""
                report_section = ""
                date_raised = ""

                prov, metadata_status, amount_val = _federal_audit_metadata(audit.provenance)
                amount_str = prov.get("amount_involved") or ""
                status = prov.get("status") or ""
                category = prov.get("category") or ""
                query_type = prov.get("query_type") or ""
                report_section = prov.get("report_section") or ""
                date_raised = prov.get("date_raised") or ""

                # Extraction-backed rows (Stage 2) carry the figure in the
                # `amount` column — set only when the paragraph cites exactly
                # one Kshs figure. Prefer it over the legacy provenance
                # string; never invent one when both are absent.
                if audit.amount is not None:
                    try:
                        stored_amount = float(audit.amount)
                    except (TypeError, ValueError, OverflowError):
                        stored_amount = math.nan
                    if math.isfinite(stored_amount):
                        amount_val = stored_amount
                        amount_str = f"KES {audit.amount:,.2f}".rstrip("0").rstrip(".")
                    else:
                        # A corrupt stored figure takes precedence over legacy
                        # metadata too: using that string would silently
                        # replace one conflicting amount with another. Keep
                        # the source-linked finding, but withhold its figure.
                        logger.warning(
                            "Withholding invalid stored amount on federal audit %s",
                            audit.id,
                        )
                        amount_val = None
                        amount_str = ""
                        amount_unavailable_reason = "invalid_stored_amount"
                        findings_with_invalid_amount += 1

                if amount_val is not None:
                    total_amount += amount_val
                    findings_with_amount += 1
                sev_key = (audit.severity.value if audit.severity else "INFO").upper()
                severity_counts[sev_key] = severity_counts.get(sev_key, 0) + 1

                source_url = report_page_url(
                    source_urls_by_document_id.get(audit.source_document_id),
                    None,
                    clear_stale_page=True,
                )
                source_page = citation_page(audit.page_ref)

                findings.append(
                    {
                        "id": audit.id,
                        "entity_name": audit.entity_name,
                        "entity_type": audit.entity_type.value if audit.entity_type else "MINISTRY",
                        "finding": audit.finding_text,
                        "severity": sev_key,
                        "recommended_action": audit.recommended_action,
                        "amount_involved": amount_str,
                        "amount_numeric": amount_val,
                        "amount_unavailable_reason": amount_unavailable_reason,
                        # Provenance a reader can follow: the page of the
                        # source PDF this finding was extracted from.
                        "title": prov.get("title") or None,
                        "provenance_metadata_status": metadata_status,
                        "page_ref": audit.page_ref,
                        "source_url": source_url,
                        "source_page": source_page,
                        "source_page_url": (
                            report_page_url(
                                source_url, source_page, clear_stale_page=True
                            )
                            if source_page is not None else None
                        ),
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

            _withheld_federal = count_withheld_audits(
                db, entity_types=FEDERAL_AUDIT_ENTITY_TYPES
            )
            # Scoped exactly like the count it explains — a federal endpoint
            # explaining itself with global figures would state numbers that
            # do not mean what the field name says.
            _withheld_federal_reasons = count_withheld_by_reason(
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
                    db.query(
                        DBSourceDocument.id,
                        DBSourceDocument.title,
                        DBSourceDocument.publisher,
                        DBSourceDocument.fetch_date,
                    )
                    .join(DBAudit, DBAudit.source_document_id == DBSourceDocument.id)
                    .join(DBEntity, DBAudit.entity_id == DBEntity.id)
                    .filter(publishable_audit_criterion())
                    .filter(
                        DBEntity.type.in_(
                            FEDERAL_AUDIT_ENTITY_TYPES
                        )
                    )
                    .join(DBFiscalPeriod, DBAudit.period_id == DBFiscalPeriod.id)
                    .filter(DBFiscalPeriod.label == latest_period_label)
                    .order_by(DBFiscalPeriod.start_date.desc(), DBSourceDocument.fetch_date.desc(), DBSourceDocument.id.desc())
                    .first()
                )

            # Report metadata comes from the database alone. It used to prefer
            # `backend/data/reference/oag_national_audit_data.json`, which the
            # publication gate withheld on every request for citing the OAG
            # homepage rather than a document (issue #233).
            report_fy = latest_period_label
            # No literal fallback: naming a report when nothing resolves to
            # one asserts a document exists that a reader cannot reach.
            derived_report_title = (
                latest_source.title if latest_source and latest_source.title else None
            )
            derived_report_date = (
                latest_source.fetch_date.date().isoformat()
                if latest_source and latest_source.fetch_date
                else None
            )
            derived_fiscal_years_covered = fiscal_years_covered
            # Opinion, recurring-issue and emphasis counts, derived from the
            # extracted findings of the SAME report named above, each with the
            # page it came from. None when that report has no extraction-backed
            # finding — the page then says so instead of rendering zeros.
            headline = (
                derive_federal_headline(
                    db,
                    source_document_id=latest_source.id,
                    entity_types=FEDERAL_AUDIT_ENTITY_TYPES,
                )
                if latest_source is not None
                else None
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
                "total_findings": len(findings),
                # The report's own questioned total. Nothing extracts it: the
                # figure used to come from a hand-written file citing only the
                # OAG homepage, withheld on every request (issue #233). Null
                # with a reason; the coverage-stated partial below is the only
                # money figure this response offers.
                "total_amount_questioned": None,
                "total_amount_questioned_reason": "not_extracted",
                # Transparency only: the raw sum across all finding amounts.
                # NOT the questioned headline (see above).
                "total_amount_in_findings": (
                    total_amount if findings_with_amount > 0 else None
                ),
                # The denominator that makes the partial safe to render. The
                # OAG's own questioned total is not extracted for FY2024/25,
                # so `total_amount_in_findings` is the only money figure this
                # response can offer — and a sum with no coverage cannot be
                # told apart from a total. Publishing both lets the page say
                # "KES 73.4B across 49 of 813 findings" instead of either an
                # em-dash (hiding a real sourced number) or a bare figure
                # (implying it is the total).
                "findings_with_amount": findings_with_amount,
                "findings_with_invalid_amount": findings_with_invalid_amount,
                "total_amount_in_findings_reason": (
                    None
                    if findings_with_amount > 0
                    else (
                        "invalid_stored_amount"
                        if findings_with_invalid_amount
                        else (
                            "awaiting_sourced_data"
                            if _withheld_federal
                            else "no_amounts_recorded"
                        )
                    )
                ),
                # Findings excluded by publication checks. Retained in the
                # database, not served here.
                "withheld_findings": _withheld_federal,
                "withheld_findings_by_reason": _withheld_federal_reasons,
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
                # Opinion distribution and headline counts derived from the
                # extracted findings (services/audit_derived.py). Every count
                # is a floor, stated beside the number of votes it could be
                # read for; no vote is ever called clean.
                "headline": headline,
                "headline_reason": (
                    None if headline else "no_extraction_backed_findings"
                ),
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
                    db, [a.source_document_id for a in federal_audits]
                ),
            }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching federal audits: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _county_audit_scope(db, county_id):
    """Resolve one Kenyan county; absence of findings is not a missing identity."""
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")
    entity = _resolve_county_entity(db, county_id)
    if entity is None or official_county_code(entity.canonical_name) is None:
        raise HTTPException(status_code=404, detail="County not found")
    query = db.query(DBAudit).filter(DBAudit.entity_id == entity.id)
    return entity, query


def _county_audit_item(audit, county_name):
    """Preserve report identity and citation; never infer money from prose."""
    from services.audit_citations import audited_institution

    provenance = audit.provenance
    first = provenance[0] if isinstance(provenance, list) and provenance else provenance
    meta = first if isinstance(first, dict) else {}
    doc = audit.source_document
    page = citation_page(audit.page_ref)
    invalid = isinstance(audit.amount, bool)
    value = float(audit.amount) if audit.amount is not None and not invalid else None
    invalid = invalid or (value is not None and not math.isfinite(value))
    amount = None if invalid else value
    # These facets are labels, not numeric evidence. Unexpected JSON shapes
    # remain absent rather than becoming truthy statuses or classifications.
    def label(key):
        value = meta.get(key)
        return value if isinstance(value, str) and value.strip() else None

    return {
        "id": audit.id,
        "description": audit.finding_text,
        "severity": audit.severity.value if audit.severity else None,
        "status": audit.status or label("status"),
        "category": label("category"),
        "amountLabel": str(amount) if amount is not None else None,
        "amount": amount,
        "amount_unavailable_reason": "invalid_stored_amount" if invalid else "no_amount_recorded" if amount is None else None,
        "fiscal_year": audit.period.label if audit.period else None,
        "audited_entity_name": audited_institution(meta, county_name=county_name, document_meta=doc.meta if doc else None),
        "source": {
            "id": doc.id if doc else None,
            "title": doc.title if doc else None,
            "publisher": doc.publisher if doc else None,
            "url": doc.url if doc else None,
            "page": page,
            "page_url": report_page_url(doc.url if doc else None, page, clear_stale_page=True),
            "table_index": None,
        },
    }


def _county_audit_rows(query):
    return query.options(joinedload(DBAudit.source_document), joinedload(DBAudit.period)).filter(
        publishable_audit_criterion()
    ).order_by(DBAudit.created_at.desc(), DBAudit.id.desc()).all()


def _county_findings_reason(published, withheld):
    return None if published else "awaiting_sourced_data" if withheld else "no_findings_recorded"


@app.get("/api/v1/counties/{county_id}/audits")
@county_database_required
@cached(key_prefix="county:audits", ttl=3600)
async def get_county_audits(county_id: str):
    """Published findings for this county, with bounded stored-amount coverage.

    A finding amount can describe a balance or an unsupported payment. It is
    not a claim of theft or proven loss. Missing-funds/COB analytics from the
    retired service remain explicitly unavailable.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")
    from services.audit_amounts import audit_amount_columns, audit_amount_result
    from services.publication_gate import retired_audit_fixture_criterion

    try:
        with next(get_db()) as db:
            entity, query = _county_audit_scope(db, county_id)
            county_name = entity.canonical_name.removesuffix(" County")
            audits = _county_audit_rows(query)
            total_amount, coverage = audit_amount_result(
                db.query(*audit_amount_columns(scope_criterion=~retired_audit_fixture_criterion())).filter(DBAudit.entity_id == entity.id).one()
            )
            queries = []
            by_severity, by_status, by_category = {}, {}, {}
            for audit in audits:
                item = _county_audit_item(audit, county_name)
                for counts, key in ((by_severity, "severity"), (by_status, "status"), (by_category, "category")):
                    facet = item[key] or "unknown"
                    counts[facet] = counts.get(facet, 0) + 1
                queries.append({
                    **item,
                    "finding": item["description"],
                    "recommendation": audit.recommended_action,
                    "amount_involved": item["amount"],
                    "date_raised": audit.created_at.isoformat() if audit.created_at else None,
                })
            withheld = coverage["withheld_findings"]
            return {
                "county_id": county_id,
                "county_name": county_name,
                "country": "KEN",
                "currency": "KES",
                "data_source": "database",
                "summary": {
                    "queries_count": len(queries),
                    "total_amount_involved": total_amount,
                    "amount_coverage": coverage,
                    "by_severity": by_severity,
                    "by_status": by_status,
                    "by_category": by_category,
                },
                "top_recent": queries[:5],
                "queries": queries,
                "withheld_findings": withheld,
                "findings_reason": _county_findings_reason(queries, withheld),
                "fiscal_years_covered": sorted({q["fiscal_year"] for q in queries if q["fiscal_year"]}),
                "missing_funds": {"count": None, "total_amount": None, "cases": [], "absent_reason": "not_published_by_this_account"},
                "cob_implementation": {"absent_reason": "not_published_by_this_account"},
                "kpis": {},
            }
    except HTTPException:
        raise
    except Exception:
        logging.exception("Error fetching audit info for county %s", county_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/counties/{county_id}/audits/history")
async def get_county_audits_history(county_id: str):
    """Group the same publishable county findings by their stored fiscal period.

    Import timestamps never stand in for an audited fiscal year.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        with next(get_db()) as db:
            entity, query = _county_audit_scope(db, county_id)
            county_name = entity.canonical_name.removesuffix(" County")
            audits = _county_audit_rows(query)
            groups = {}
            for audit in audits:
                item = _county_audit_item(audit, county_name)
                period = item["fiscal_year"] or "Unknown"
                group = groups.setdefault(period, {"fiscal_year": period, "count": 0, "by_status": {}})
                group["count"] += 1
                status = item["status"] or "unknown"
                group["by_status"][status] = group["by_status"].get(status, 0) + 1
            withheld = count_withheld_audits(db, entity_id=entity.id)
            return {
                "county_id": county_id,
                "county_name": county_name,
                "years": [groups[key] for key in sorted(groups, reverse=True)],
                "total": len(audits),
                "withheld_findings": withheld,
                "findings_reason": _county_findings_reason(audits, withheld),
            }
    except HTTPException:
        raise
    except Exception:
        logging.exception("Error fetching audit history for county %s", county_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/counties/{county_id}/audits/list", response_model=AuditListResponse)
async def list_county_audits(
    county_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    year: Optional[str] = Query(None, description="Stored fiscal year label e.g. FY2022/23"),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Paginated county findings; same publication and identity scope as history."""
    try:
        entity, query = _county_audit_scope(db, county_id)
        if year:
            query = query.join(DBFiscalPeriod, DBAudit.period_id == DBFiscalPeriod.id).filter(DBFiscalPeriod.label == year)
        if severity:
            try:
                severity_value = Severity[severity.upper()]
            except KeyError:
                raise HTTPException(status_code=422, detail="Unknown audit severity")
            query = query.filter(DBAudit.severity == severity_value)
        county_name = entity.canonical_name.removesuffix(" County")
        items = [_county_audit_item(a, county_name) for a in _county_audit_rows(query)]
        if status:
            items = [item for item in items if (item["status"] or "").casefold() == status.casefold()]
        # Withheld count belongs to the entity/period/severity scope, before
        # the status facet (withheld metadata is not a publishable status).
        from services.publication_gate import retired_audit_fixture_criterion

        withheld = query.filter(~publishable_audit_criterion(), ~retired_audit_fixture_criterion()).count()
        start = (page - 1) * limit
        return {
            "total": len(items), "page": page, "limit": limit,
            "items": items[start:start + limit],
            "withheld_findings": withheld,
            "findings_reason": _county_findings_reason(items, withheld),
        }
    except HTTPException:
        raise
    except Exception:
        logging.exception("Error listing audit queries for %s", county_id)
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
    # Findings held back by the publication checks. Counted so the omission
    # is visible rather than inferred from a suspiciously clean scorecard.
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
                f"{'s' if withheld_findings != 1 else ''} withheld because "
                "the audit publication requirements are not met"
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
    from services.county_identity import legacy_county_route_id

    peer_route_id = legacy_county_route_id(entity.canonical_name)
    region = COUNTY_REGIONS.get(peer_route_id, "Unknown")
    region_county_ids = [
        cid for cid, r in COUNTY_REGIONS.items() if r == region and cid != peer_route_id
    ]

    pop_data = (
        db.query(DBPopulationData)
        .filter(DBPopulationData.entity_id == entity.id)
        .order_by(DBPopulationData.year.desc())
        .first()
    )
    population = pop_data.total_population if pop_data else None

    # No census row, no bracket. Bucketing an uncounted county on 0 filed it
    # under "<500k" — Kenya's smallest bracket — and the county page then
    # printed "vs <500k Average" over an Above/Below verdict against a peer
    # group the county was never shown to belong to. The frontend's
    # `peer.population_bracket || t('...bracket_fallback')` rung labels the
    # card "vs Population Bracket Average" when this is None, and its null
    # check on population_bracket_avg renders an em dash with "Not enough
    # sourced data to compare" — which is what we know.
    if population is None:
        pop_bracket = None
    elif population < 500_000:
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
        db.query(DBEntity)
        .join(DBCountry, DBEntity.country_id == DBCountry.id)
        .filter(DBEntity.type == EntityType.COUNTY, DBCountry.iso_code == "KEN")
        .all()
    )
    # Map canonical_name ("Nairobi County") → entity for the lookup below.
    peers_by_name: Dict[str, Any] = {
        (e.canonical_name or ""): e for e in all_peer_entities
    }
    peer_entity_ids = [e.id for e in all_peer_entities if e.id != entity.id]

    # Pull only the peer fields used by the two comparisons in one query.
    # Full finding text, provenance, and responses are not needed here.
    from collections import defaultdict

    peer_audits_by_entity: Dict[int, List[Any]] = defaultdict(list)
    if peer_entity_ids:
        for pa in (
            db.query(
                DBAudit.entity_id,
                DBAudit.amount,
                DBAudit.audit_year,
                DBAudit.audit_opinion,
            )
            .filter(publishable_audit_criterion())
            .filter(DBAudit.entity_id.in_(peer_entity_ids))
            .all()
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
        # A peer with no recorded amount is UNKNOWN, not zero — the same rule
        # the population-bracket path below already applies. Reported by
        # review on PR #135: this appended 0 for every peer with no
        # publishable amount (and `pa.amount or 0` coerced None to 0), so
        # region_avg_flagged_amount was dragged toward zero by peers about
        # which nothing is known, in the PR that exists to stop exactly that.
        _peer_amounts = [float(pa.amount) for pa in peer_audits if pa.amount is not None]
        if _peer_amounts:
            region_flagged_amounts.append(float(sum(_peer_amounts)))

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
            # Only a peer with a RECORDED opinion contributes a grade. The
            # default "A" above is the starting point of the scan, not a
            # verdict — appending it for a peer with no opinions graded
            # absence as excellence and pulled region_avg_grade upward
            # (PR #135 review).
            region_grades.append(pg)

    # Population-bracket peers: iterate every county and keep same-bracket ones.
    # Skipped entirely when this county has no census row: "the counties in the
    # same bracket as this one" is not a set that can be formed without knowing
    # the bracket, so population_bracket_avg goes absent with the bracket.
    if pop_bracket is not None:
        for cid, cname in COUNTY_MAPPING.items():
            if cid == peer_route_id:
                continue
            ce = peers_by_name.get(f"{cname} County")
            if not ce:
                continue
            cpop = peer_pop_by_entity.get(ce.id)
            if cpop is None:
                # An uncounted PEER has no bracket either. Defaulting it to 0
                # put counties of unknown size into "<500k", so the average a
                # genuinely small county is measured against was computed over
                # peers that may not be small at all.
                continue
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
            "reason": "publication_requirements_not_met" if withheld_findings else None,
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

    try:
        with next(get_db()) as db:
            entity = _resolve_county_entity(db, county_id)
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

    try:
        with next(get_db()) as db:
            entity = _resolve_county_entity(db, county_id)
            if not entity:
                raise HTTPException(status_code=404, detail="County entity not found")

            pop_data = (
                db.query(DBPopulationData)
                .filter(DBPopulationData.entity_id == entity.id)
                .order_by(DBPopulationData.year.desc())
                .first()
            )
            budget_lines = _entity_period_budget_query(db, entity.id).all()
            from services.entity_financials import financial_summary

            budget_account = financial_summary(
                budget_lines, budget_lines[0].period if budget_lines else None
            )
            audits = db.query(DBAudit).filter(publishable_audit_criterion()).filter(DBAudit.entity_id == entity.id).all()

            scorecard = _compute_accountability(db, entity, county_id)

            return {
                "county_id": county_id,
                "county_name": (entity.canonical_name or "").replace(" County", ""),
                # The census, or nothing — same rule as the list and detail
                # endpoints. A 0 here is not a small population; it is the
                # claim that nobody lives in the county.
                "population": (
                    pop_data.total_population if pop_data else None
                ),
                "total_budget": budget_account["total_allocation"],
                "total_spent": budget_account["total_spent"],
                "budget_fiscal_period": budget_account["fiscal_period"],
                "budget_accounting_basis": budget_account["accounting_basis"],
                "budget_currency": budget_account["currency"],
                "budget_sources": budget_account["sources"],
                "budget_absent_reasons": budget_account["absent_reasons"],
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
    """Findings the Auditor-General titled "Unaccounted …" or "Loss of Funds".

    Derived from extracted OAG findings (issue #233), in the report's own
    words and with the page each came from. This used to read hand-written
    cases off ``entity.meta["missing_funds_cases"]`` (from
    ``oag_audit_data.json``), none of which cited a document, so the page was
    permanently empty.

    ``total_amount`` is always ``None`` with ``total_amount_reason``: no
    matched finding carries an extracted amount, and where the loader does
    store one it is the paragraph's only KES figure — often the balance under
    discussion, not the sum unaccounted for. The match is on titles only, so
    the list is a floor; ``basis`` says so machine-readably.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    with next(get_db()) as db:
        derived = derive_unaccounted_cases(db)

    cases = derived["cases"]
    withheld_by_reason = derived["withheld"]
    withheld_total = sum(withheld_by_reason.values())
    if withheld_total:
        logger.warning(
            "missing-funds: withheld %d matching finding(s) (%s); %d published",
            withheld_total,
            ", ".join(f"{k}={v}" for k, v in sorted(withheld_by_reason.items())),
            len(cases),
        )
    county_cases = [c for c in cases if c["entity_type"] == "county"]
    return {
        "basis": "oag_finding_title",
        "total_amount": None,
        "total_amount_reason": "no_amount_extracted",
        "total_cases": len(cases),
        "affected_counties": len({c["entity_id"] for c in county_cases}),
        "affected_national_entities": len(
            {c["entity_id"] for c in cases if c["entity_type"] != "county"}
        ),
        "fiscal_years": sorted({c["fiscal_year"] for c in cases if c["fiscal_year"]}, reverse=True),
        "cases": cases,
        "reason": None if cases else "no_matching_findings",
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
            # Sector rows only. The CBIRR's Total / Recurrent / Development
            # restate the whole budget and its revenue rows are money
            # received; bucketed as sectors they landed in "Other" and were
            # added to the total three or four times over.
            _cat_key = (category or "").strip().lower()
            if _cat_key in _CLASSIFICATION_CATEGORIES or _cat_key in _NON_SECTOR_CATEGORIES:
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

    Aggregates publisher registrations from source_documents, excluding
    declared app fixtures and generated estimates. Returns one entry per
    publisher with document counts, last-fetched timestamp, and doc-type
    breakdown. Used by the public /sources page so citizens can see where
    the numbers come from and when each feed was last refreshed.
    """
    if not DATABASE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database unavailable")

    from sqlalchemy import func as _fn, case
    from services.source_evidence import (
        downloaded_document_criterion,
        publisher_inventory_criterion,
    )
    from models import Extraction

    with next(get_db()) as db:
        rows = (
            db.query(
                DBSourceDocument.publisher,
                _fn.count(DBSourceDocument.id).label("doc_count"),
                _fn.max(
                    case((downloaded_document_criterion(), DBSourceDocument.last_verified_at))
                ).label("last_fetched"),
                _fn.sum(
                    case((downloaded_document_criterion(), 1), else_=0)
                ).label("downloaded"),
                _fn.max(DBSourceDocument.last_seen_at).label("last_seen_at"),
            )
            .filter(publisher_inventory_criterion())
            .group_by(DBSourceDocument.publisher)
            .order_by(_fn.count(DBSourceDocument.id).desc())
            .all()
        )

        extracted = dict(
            db.query(
                DBSourceDocument.publisher,
                _fn.count(_fn.distinct(Extraction.source_document_id)),
            )
            .join(Extraction, Extraction.source_document_id == DBSourceDocument.id)
            .filter(publisher_inventory_criterion())
            .group_by(DBSourceDocument.publisher)
            .all()
        )

        # Doc-type breakdown per publisher
        breakdown_rows = (
            db.query(
                DBSourceDocument.publisher,
                DBSourceDocument.doc_type,
                _fn.count(DBSourceDocument.id),
            )
            .filter(publisher_inventory_criterion())
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
    for pub, count, fetched, downloaded, seen in rows:
        meta = _meta_for(pub)
        out.append(
            {
                "publisher": pub,
                "short": meta.get("short", ""),
                "role": meta.get("role", ""),
                "website": meta.get("website"),
                "document_count": int(count),  # SQL COUNT(id) for an existing publisher group.
                "downloaded_documents": int(downloaded or 0),
                "extracted_documents": int(extracted.get(pub, 0)),
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
_etl_lock = asyncio.Lock()  # Serialize web discovery jobs
_etl_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="etl"
)


def _discovery_pipeline_class():
    """Resolve the capability from this process's actual import path.

    Backend-only images intentionally omit the root legacy ETL package. The
    dedicated seed runner discovers sources through its own domain fetchers.
    """
    try:
        module = importlib.import_module("etl.kenya_pipeline")
        pipeline = getattr(module, "KenyaDataPipeline")
        if not callable(pipeline) or not callable(getattr(pipeline, "discover_budget_documents", None)):
            raise TypeError("Missing discovery entry point")
        return pipeline
    except (ImportError, AttributeError, TypeError) as exc:
        raise RuntimeError("Legacy discovery unavailable in this deployment; use the dedicated seeding runner.") from exc


async def _discover(source_key: str) -> List[Dict[str, Any]]:
    KenyaDataPipeline = _discovery_pipeline_class()
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
    if job_type != "light":
        raise ValueError("Deep ingestion is owned by the dedicated seeding runner")
    _discovery_pipeline_class()  # Refuse before artifacts or network side effects.
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


# ``require_admin`` is shared with the routers in ``backend/routers/`` —
# importing here lets us put the etl endpoints defined directly on
# ``app`` behind the same auth gate as the rest of /admin.
from supabase_auth import require_admin as _require_admin


@app.post("/api/v1/admin/etl/run")
async def run_etl_job(
    source: str = Query(..., pattern="^(oag|cob|treasury)$"),
    job: str = Query("light", pattern="^(light|deep)$"),
    _actor=Depends(_require_admin),
):
    """Manually trigger lightweight discovery; deep ingestion returns 409.

    Returns immediately with a job_id. The ETL runs in the background.
    Check progress via GET /api/v1/admin/etl/status.

    Gated on ``require_admin``. It used to depend on a bare ``HTTPBearer()``,
    which only checks that an ``Authorization: Bearer <anything>`` header
    is present and never verifies it (#252).
    """
    if job != "light":
        raise HTTPException(
            status_code=409,
            detail="Deep ingestion is owned by the dedicated seeding runner (.github/workflows/seed.yml).",
        )
    try:
        _discovery_pipeline_class()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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
        async with _etl_lock:  # Serialize web discovery jobs
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
        # nondeterminism-ok: scheduler jitter spreads job start times; never published
        return max(60, base_seconds + random.randint(-spread, spread))

    try:
        _discovery_pipeline_class()
    except RuntimeError as exc:
        logger.info("%s Skipping legacy discovery schedules.", exc)
    else:
        # Discovery only. Deep PDF ingestion belongs to seed.yml, outside the web worker.
        # OAG: light weekly
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

        # COB: lightweight discovery weekly
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

        # Treasury: lightweight discovery twice weekly (~3.5 days)
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

                # Development vs recurrent split — WITHHELD, not guessed.
                #
                # The rows this endpoint sums are SECTOR allocations (Education,
                # Health, National Security ...). They carry no economic
                # classification, so a development/recurrent split cannot be
                # derived from them. The previous rule was
                # `"development" in category.lower()`, which matched exactly one
                # sector — "Agriculture, Rural and Urban DEVELOPMENT" — and
                # published its 59.13B as the national development budget, with
                # everything else counted as recurrent. The Controller of Budget
                # states 744.84B of ministerial development spending for
                # FY2025/26: the substring match was out by a factor of 12.6
                # (credibility audit F30).
                #
                # Publish the split only where the rows actually classify it.
                _class_rows = {
                    (b.category or "").strip().lower(): float(b.allocated_amount or 0)
                    for b in budget_query.all()
                    if (b.category or "").strip().lower() in _CLASSIFICATION_CATEGORIES
                }
                dev_budget = _class_rows.get("development")
                recurrent_budget = _class_rows.get("recurrent")
                budget_split_absent_reason = (
                    None
                    if dev_budget is not None or recurrent_budget is not None
                    else "sector_rows_carry_no_economic_classification"
                )

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
                        "budget_split_absent_reason": budget_split_absent_reason,
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

                # One rule per county — see _county_period_rollup.
                per_county, _ = _county_period_rollup(db, period_id)
                entities = []
                for name, alloc, spent in per_county.values():
                    alloc = float(alloc or 0)
                    spent = float(spent or 0)
                    entities.append(
                        {
                            "entity": name,
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
            county_period_id = _latest_county_period(db, official_counties_only=True)
            period_label = None
            if county_period_id:
                _fp = db.query(DBFiscalPeriod).get(county_period_id)
                period_label = _fp.label if _fp else None

            # ── County totals and sectors (county-only, latest FY) ─────
            # Totals per county through the shared split rule, sectors from
            # the additive sector rows only — see _county_period_rollup.
            per_county, sector_lines = _county_period_rollup(db, county_period_id, reject_incomplete=True)
            merged: dict = {}
            for bl in sector_lines:
                cat = bl.category
                key = SECTOR_NORMALIZE.get(str(cat or "").strip().lower(), "Other")
                entry = merged.setdefault(key, {"allocated": 0.0, "spent": 0.0})
                entry["allocated"] += float(bl.allocated_amount or 0)
                entry["spent"] += float(bl.actual_spent or 0)

            total_allocated = sum(a for _n, a, _s in per_county.values())
            total_spent = sum(sp for _n, _a, sp in per_county.values())
            # Shares are of the sector rows' own sum: where a period carries
            # both the CBIRR total and a modelled sector split, the two need
            # not agree, and percentages of the wrong base would not add to 100.
            sector_total = sum(v["allocated"] for v in merged.values())
            aggregates = [total_allocated, total_spent, sector_total]
            aggregates.extend(value for entry in merged.values() for value in entry.values())
            aggregates.extend(value for _name, allocated, spent in per_county.values() for value in (allocated, spent))
            if any(not math.isfinite(value) or value < 0 for value in aggregates):
                raise HTTPException(status_code=503, detail={"reason": "invalid_county_aggregate"})

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
                            round(v["allocated"] / sector_total * 100, 1)
                            if sector_total > 0
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
            from services.publication_gate import publishable_fiscal_summaries

            fiscal_rows = publishable_fiscal_summaries(
                db.query(FSModel).order_by(FSModel.fiscal_year.asc()).all()
            )
            fiscal_years = []
            fiscal_history_withheld = []

            from services.financial_publication import fiscal_history_entry

            for r in fiscal_rows:
                entry = fiscal_history_entry(r)
                # Keep the existing coverage threshold; zero is reported data.
                key_fields = [entry[k] for k in (
                    "appropriated_budget", "total_revenue", "total_borrowing",
                    "county_allocation",
                )]
                if sum(v is not None for v in key_fields) >= 3:
                    fiscal_years.append(entry)
                else:
                    fiscal_history_withheld.append({
                        "fiscal_year": r.fiscal_year,
                        "reason": "unsupported_unit" if r.unit != "KES" else "insufficient_reported_fields",
                        "source_unit": r.unit,
                        "absent_reasons": entry["absent_reasons"],
                    })

            latest = next(
                (e for e in reversed(fiscal_years)
                 if e["appropriated_budget"] is not None and e["appropriated_budget"] > 0),
                fiscal_years[-1] if fiscal_years else {},
            )

            # ── Top / bottom utilization counties (same FY scope) ──
            county_utils = []
            for name, a, s in per_county.values():
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
                "fiscal_history_withheld": fiscal_history_withheld,
                "fiscal_history_absent_reason": "no_supported_fiscal_history" if not fiscal_years else None,
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
      - revenue_by_source: separately sourced collections per FY; incompatible residuals withheld
      - economic_context: Budget as % of GDP, per-capita budget, key economic indicators
      - execution_by_sector: revised gross estimates vs actual expenditure per
        sector, from the newest annual CoB NG-BIRR (declared rows only)
    """
    from models import (
        EconomicIndicator,
        FiscalSummary,
        PopulationData,
        RevenueBySource,
    )
    from services.revenue_publication import revenue_source_row

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
            rev_by_fy[fy].append(revenue_source_row(r))

        revenue_by_source = [
            {"fiscal_year": fy, "sources": sources}
            for fy, sources in sorted(rev_by_fy.items())
        ]

        # ── 2. Economic context ──
        # Every figure is the NEWEST NATIONAL row of its series, and every
        # caption comes from that row's own declared provenance. Until #232
        # growth and unemployment were read out of
        # `db.query(EconomicIndicator).all()` — no ORDER BY, no entity scope,
        # last write wins — so the year shown was whatever the planner
        # returned last (production served unemployment 5.7, a 2021/2022
        # value, against a newest observation of 5.4), and the inflation
        # caption was the literal "KNBS Consumer Price Index" under a World
        # Bank annual average.
        def _latest_national(indicator_type: str):
            return (
                db.query(EconomicIndicator)
                .filter(
                    EconomicIndicator.indicator_type == indicator_type,
                    EconomicIndicator.entity_id.is_(None),
                    EconomicIndicator.value.isnot(None),
                )
                .order_by(
                    EconomicIndicator.indicator_date.desc(),
                    EconomicIndicator.id.desc(),
                )
                .first()
            )

        def _provenance(row) -> dict:
            # `source_label` is DECLARED by the writer, never inferred. A row
            # without one gets no caption rather than a guessed one: losing a
            # credit is the safe direction, manufacturing one is not.
            meta = row.meta if row is not None and isinstance(row.meta, dict) else {}
            return {
                "value": float(row.value) if row is not None else None,
                "as_of": (
                    row.indicator_date.isoformat()
                    if row is not None and row.indicator_date
                    else None
                ),
                "source": meta.get("source_label") or None,
                "measure": meta.get("measure") or None,
            }

        gdp = _provenance(_latest_national("total_national_gdp"))
        gdp_million = gdp["value"]
        gdp_billion = gdp_million / 1000 if gdp_million else None  # Convert to billions
        growth = _provenance(_latest_national("gdp_growth_rate"))
        unemployment = _provenance(_latest_national("unemployment_rate"))

        # Inflation: KNBS's headline is the 12-month rate, published monthly
        # (CBK table, `inflation_rate_12m`). The World Bank's `inflation_rate`
        # is an annual AVERAGE a year behind. Take whichever is newer — on a
        # tie the monthly headline — and caption it with its own measure, so
        # a fallback to the annual series reads as what it is. The legacy
        # `inflation_rate_cpi` key is the last resort only.
        monthly = _latest_national("inflation_rate_12m")
        annual = _latest_national("inflation_rate")
        if monthly is not None and (
            annual is None or monthly.indicator_date >= annual.indicator_date
        ):
            inflation_row = monthly
        else:
            inflation_row = annual or _latest_national("inflation_rate_cpi")
        inflation = _provenance(inflation_row)

        # Kenya's population, not the sum of every row in the table. This was
        # `func.sum(PopulationData.total_population)` over the whole table —
        # 47 counties across every seeded year plus the national rows — which
        # reported 907,025,674 and dragged per_capita_budget_kes down to
        # KES 6,048 (credibility audit F29).
        from services.population import latest_national_population

        total_pop, total_pop_year = latest_national_population(db)

        # Get latest fiscal summary for budget context — the newest row that
        # cites a page, not simply the newest row.
        from services.publication_gate import latest_publishable_fiscal_summary

        latest_fiscal = latest_publishable_fiscal_summary(db)

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
            "gdp_as_of": gdp["as_of"],
            "gdp_source": gdp["source"],
            "gdp_growth_pct": growth["value"],
            "gdp_growth_as_of": growth["as_of"],
            "gdp_growth_source": growth["source"],
            "inflation_pct": inflation["value"],
            "inflation_as_of": inflation["as_of"],
            "inflation_source": inflation["source"],
            "inflation_measure": inflation["measure"],
            "unemployment_pct": unemployment["value"],
            "unemployment_as_of": unemployment["as_of"],
            "unemployment_source": unemployment["source"],
            "total_population": total_pop,
            # Say which year the population describes, so a per-capita figure
            # can be checked rather than assumed current.
            "total_population_year": total_pop_year,
            # And say why it is missing when it is. `latest_national_population`
            # no longer substitutes a county sum for the national series
            # (issue #190), so absence here is absence of the series itself —
            # which is a reseed, not a code fix. Both per-capita figures below
            # go null with it rather than resting on a guess.
            "total_population_absent_reason": (
                None if total_pop else "no_national_population_series"
            ),
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
        # Declared-expenditure rows from the newest ANNUAL COB NG-BIRR — see
        # services/budget_execution.py for why rows are selected by what they
        # declare, not by which column happens to be filled (#241).
        from services.budget_execution import execution_by_sector as _exec

        execution = _exec(db)
        execution_by_sector = execution["rows"]
        execution_fiscal_year = execution["fiscal_year"]

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
            # Where the execution figures come from, what they measure, how
            # much of the ministerial budget they cover, and what they leave
            # out — each null when there is nothing to publish.
            "execution_source": execution["source"],
            "execution_measure": execution["measure"],
            "execution_coverage": execution["coverage"],
            "execution_excludes": execution["excludes"],
        }

    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"Budget enhanced failed: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/v1/debt/timeline")
@cached(key_prefix="debt:timeline", ttl=NIGHTLY_REFRESH_TTL)
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
                    "gdp": float(r.gdp) if r.gdp is not None else None,
                    "gdp_ratio": float(r.gdp_ratio) if r.gdp_ratio is not None else None,
                    # The row's declared unit (stage1 3a): "KES" = raw KES.
                    # Consumers convert on this field, never by guessing
                    # magnitude — see F5.5.
                    "unit": r.unit,
                }
            )

        # ── Source: the document behind the figure this response leads with ──
        #
        # This read ``rows[0]`` — the OLDEST row, the series being ordered
        # year.asc() — while ``last_updated`` and
        # ``reconciliation.primary_value_kes`` both describe ``rows[-1]``. The
        # series runs 2013-2025, so production credited "CBK public debt table,
        # December 2013" for a 2025 figure, and
        # /provenance/verify/debt_timeline?year=2025 named a different document
        # for that same number (audit 2026-09-06 §P2-10).
        #
        # The series genuinely spans many documents, so there is no single
        # honest series-wide title. Attribute the row the response leads with,
        # name its year so the claim is checkable, and say plainly whether the
        # earlier years came from elsewhere.
        source_title = "Central Bank of Kenya Annual Reports & National Treasury BPS"
        last_updated = None
        source_year = None
        source_covers_full_series = False
        latest_row = rows[-1]
        if latest_row.source_document_id:
            sdoc = (
                db.query(DBSourceDocument)
                .filter(DBSourceDocument.id == latest_row.source_document_id)
                .first()
            )
            if sdoc and sdoc.title:
                source_title = sdoc.title
                source_year = latest_row.year
                source_covers_full_series = all(
                    r.source_document_id == latest_row.source_document_id
                    for r in rows
                )
        if latest_row.updated_at:
            last_updated = latest_row.updated_at.isoformat()

        # ── Cross-check against /debt/national (Loan sum) ──
        # Same rationale as the reciprocal check on /debt/national:
        # surface any divergence so callers can display an honest badge.
        reconciliation: dict = {
            "primary_source": "debt_timeline_table",
            # debt_timeline stores raw KES with a declared unit column
            # (stage1 3a migration) — no scale factor.
            "primary_value_kes": (
                float(rows[-1].total) if rows[-1].total is not None else None
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
                unit=_declared_row_unit(rows),
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
            # Which year ``source`` is the document for, and whether it covers
            # the rest of the series. Without these a document title beside a
            # 13-year series reads as if it had produced all 13 years.
            "source_year": source_year,
            "source_covers_full_series": source_covers_full_series,
            "years": len(timeline),
            "timeline": timeline,
            "reconciliation": reconciliation,
        }
    except Exception as e:
        logging.error(f"Error fetching debt timeline: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _fiscal_row_to_dict(r) -> dict:
    return {
        "fiscal_year": r.fiscal_year,
        # The row's declared unit (stage1 3a): "KES" = raw KES.
        "unit": r.unit,
        "appropriated_budget": (
            float(r.appropriated_budget) if r.appropriated_budget is not None else None
        ),
        "total_revenue": float(r.total_revenue) if r.total_revenue is not None else None,
        "tax_revenue": float(r.tax_revenue) if r.tax_revenue is not None else None,
        "non_tax_revenue": (
            float(r.non_tax_revenue) if r.non_tax_revenue is not None else None
        ),
        "total_borrowing": (
            float(r.total_borrowing) if r.total_borrowing is not None else None
        ),
        "borrowing_pct_of_budget": (
            float(r.borrowing_pct_of_budget)
            if r.borrowing_pct_of_budget is not None
            else None
        ),
        "debt_service_cost": (
            float(r.debt_service_cost) if r.debt_service_cost is not None else None
        ),
        "debt_service_per_shilling": (
            float(r.debt_service_per_shilling)
            if r.debt_service_per_shilling is not None
            else None
        ),
        "debt_ceiling": float(r.debt_ceiling) if r.debt_ceiling is not None else None,
        "actual_debt": float(r.actual_debt) if r.actual_debt is not None else None,
        "debt_ceiling_usage_pct": (
            float(r.debt_ceiling_usage_pct)
            if r.debt_ceiling_usage_pct is not None
            else None
        ),
        "development_spending": (
            float(r.development_spending) if r.development_spending is not None else None
        ),
        "recurrent_spending": (
            float(r.recurrent_spending) if r.recurrent_spending is not None else None
        ),
        "county_allocation": (
            float(r.county_allocation) if r.county_allocation is not None else None
        ),
        # WHICH measure the budget is: "cob_gross" (gross ministerial
        # + Consolidated Fund Services) vs the Budget Policy Statement
        # figure the series used to carry. Two legitimate numbers 12%
        # apart, so the basis travels with the value.
        "budget_basis": (r.meta or {}).get("budget_basis"),
        "budget_basis_source": (r.meta or {}).get("budget_basis_source"),
        # The document debt_service_cost was read from — which can differ
        # from budget_basis_source's, so it travels separately (issue #235).
        "debt_service_source": (r.meta or {}).get("debt_service_source"),
        "revenue_source": (r.meta or {}).get("revenue_source"),
        # Billions KES of the gross budget that is redemption of
        # maturing debt. Lets the page say why the gross figure and the
        # enacted headline differ, instead of just asserting they do.
        "debt_redemption_billion": (r.meta or {}).get("debt_redemption_billion"),
        # The split and the total it reconciles to, on ONE basis
        # (Treasury's fiscal framework, "Expenditure and Net
        # Lending"). NOT appropriated_budget: that is COB gross, which
        # counts principal redemption and excludes county transfers,
        # so a split drawn against it does not add up. Money in KSh
        # billion, as the key names say. See fiscal_framework.py.
        "fiscal_framework": (r.meta or {}).get("fiscal_framework"),
        "split_basis": (r.meta or {}).get("split_basis"),
        "fiscal_framework_absent_reason": (r.meta or {}).get(
            "fiscal_framework_absent_reason"
        ),
        "tax_split_absent_reason": (r.meta or {}).get("tax_split_absent_reason"),
        "page_ref": r.page_ref,
    }


def _fiscal_has_enacted_budget(fy: dict) -> bool:
    """A budget read from an enacted Budget Estimates document.

    Distinguishes a fiscal year that has genuinely begun and whose
    budget Parliament has approved from a World Bank back-fill stub.
    Both may carry a single populated field; only one of them is the
    most authoritative figure we hold.
    """
    source = fy.get("budget_basis_source") or {}
    return bool(
        (fy.get("appropriated_budget") or 0) > 0
        and fy.get("budget_basis")
        and source.get("url")
        and fy.get("page_ref")
    )

def _select_fiscal_years(all_fiscal_years: List[dict]) -> List[dict]:
    """The fiscal years /fiscal/summary publishes, oldest first.

    Shared with /debt/loans, whose annual debt-service figure must be the SAME
    year and value the fiscal summary calls current.
    """
    # Only include years with substantially complete data —
    # World Bank back-fill years often only have 1-2 fields.
    #
    # ...with one exception, added 2026-08-29. A fiscal year that has just
    # STARTED has an enacted budget and no actuals: no revenue outturn, no
    # debt-service outturn, no execution. Requiring three populated fields
    # therefore hid FY2026/27 behind FY2025/26 from 1 July until COB's
    # first quarterly report in mid-November — every year, by construction.
    # The exception is deliberately narrow: the row must carry a declared
    # budget basis, a source URL and a page reference, i.e. it must be
    # traceable to the Budget Estimates document it came from. A World Bank
    # stub has none of those and is still excluded.
    return [
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
        or _fiscal_has_enacted_budget(fy)
    ]


def _current_fiscal_year(fiscal_years: List[dict]) -> Optional[dict]:
    """The year /fiscal/summary calls current: the latest published year that
    carries an appropriated (enacted) budget, else the latest published year.

    Treasury's Budget Summary for NEXT year appears in June, before the next
    budget book is read. The row it produces (revenue, borrowing, county
    transfers, a page reference; no appropriated budget or debt service)
    passes the three-of-four rule and is published in the history, but it
    must not become current: the homepage's budget and debt-service cards and
    the /debt loans card would read "Not published" for the weeks until the
    budget book lands. Shared with /debt/loans so both name the same year.
    """
    for fy in reversed(fiscal_years):
        if (fy.get("appropriated_budget") or 0) > 0:
            return fy
    return fiscal_years[-1] if fiscal_years else None


@app.get("/api/v1/fiscal/summary")
@cached(key_prefix="fiscal:summary", ttl=NIGHTLY_REFRESH_TTL)
async def get_fiscal_summary(db: Session = Depends(get_db)):
    """Get national fiscal summary — budget, revenue, borrowing, debt service, debt ceiling.

    Reads from the fiscal_summaries table, seeded from National Treasury BPS,
    Controller of Budget reports, and CBK data.
    """
    from models import FiscalSummary as FSModel
    from services.publication_gate import (
        fiscal_summary_withheld_disclosure,
        publishable_fiscal_summaries,
    )

    try:
        stored_rows = db.query(FSModel).order_by(FSModel.fiscal_year.asc()).all()

        # Tier B (issue #137): a fiscal year is published only if its row cites
        # a page of the document it came from. The disclosure is computed over
        # the STORED rows, before the gate, because it has to describe what was
        # taken away — computed after, it would always report zero.
        withheld = fiscal_summary_withheld_disclosure(stored_rows)
        rows = publishable_fiscal_summaries(stored_rows)

        if not rows:
            # Two different causes, two different remedies. Gating created the
            # second: rows are present and every one of them cites no page.
            # Answering "database_empty" there sends an operator to re-run a
            # seeder that will not help, because the seeder is not the problem.
            if stored_rows:
                return {
                    "status": "no_data",
                    "data_source": "all_rows_withheld",
                    "last_updated": None,
                    "source": (
                        f"{len(stored_rows)} fiscal year(s) are stored and none "
                        "cites a page of its source document, so none can be "
                        "published. Backfill fiscal_summaries.page_ref."
                    ),
                    "current": None,
                    "history": [],
                    "total_fiscal_years": 0,
                    "withheld": withheld,
                }
            return {
                "status": "no_data",
                "data_source": "database_empty",
                "last_updated": None,
                "source": "Run seeder: python -m seeding.cli seed --domain fiscal_summary",
                "current": None,
                "history": [],
                "total_fiscal_years": 0,
                "withheld": withheld,
            }

        all_fiscal_years = [_fiscal_row_to_dict(r) for r in rows]
        fiscal_years = _select_fiscal_years(all_fiscal_years)
        latest = _current_fiscal_year(fiscal_years) or all_fiscal_years[-1]

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
                "IMF General Government Gross Debt, % of GDP (nominal); not "
                "comparable to the present-value anchor"
            ),
            "above_anchor": None,
            "comparison_absent_reason": "A comparable present-value debt ratio is not available.",
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
                unit=_declared_row_unit(rows),
                entity_scope="national",
                quality_notes=_fiscal_quality_notes or None,
            ),
            "last_updated": last_updated,
            "source": source_title,
            "current": latest,
            "history": fiscal_years,
            "total_fiscal_years": len(fiscal_years),
            # What is NOT here, and why. A history that silently loses
            # FY2017/18..FY2021/22 asserts by omission that Kenya's budget
            # series begins in 2022.
            "withheld": withheld,
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
        """FiscalSummary rows may be EITHER raw KES (post stage1 3a, where the
        row declares unit="KES") or the older bare-billions convention, while
        GDPData and Loan are always RAW KES. Normalise the fiscal figures to raw KES so every figure
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
        from services.publication_gate import publishable_fiscal_summaries

        fs_rows = publishable_fiscal_summaries(
            db.query(_FS).order_by(_FS.fiscal_year.asc()).all()
        )

        def _latest_fs(attr):
            for r in reversed(fs_rows):
                v = getattr(r, attr, None)
                if v and float(v) > 0:
                    return r
            return None

        budget_row = _latest_fs("appropriated_budget")

        def _equitable_share_billion(r):
            """The row's county EQUITABLE SHARE in KSh bn, or None.

            Since #237 a row with a fiscal-framework split stores ALL county
            transfers in ``county_allocation`` (FY2026/27: 495.5B), and the
            equitable share on its own line of the framework (420.0B). Rows
            without a split (``split_basis`` unset) still hold the equitable
            share in ``county_allocation``. Transfers are never published under
            the equitable-share label.
            """
            meta = r.meta or {}
            framework = meta.get("fiscal_framework") or {}
            share = framework.get("county_equitable_share_billion")
            if share is not None:
                return float(share) if float(share) > 0 else None
            if meta.get("split_basis"):
                return None
            v = r.county_allocation
            return float(v) if v and float(v) > 0 else None

        share_row = next(
            (r for r in reversed(fs_rows) if _equitable_share_billion(r) is not None),
            None,
        )
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
            value=_fs_to_kes(_equitable_share_billion(share_row)) if share_row else None,
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


#: Why the register publishes no single "annual service" total. The rows are
#: on different bases — World Bank interest actually PAID in a calendar year
#: for external creditors, balance x a CBK rate (modelled) for two domestic
#: rows, nothing for the rest — so their sum is not a figure any publisher
#: states. It used to be 1,022.4Bn: three April-2025 fixture rates times three
#: balances, beside 45 rows of manufactured zeros (issue #235).
LOANS_TOTAL_SERVICE_ABSENT_REASON = (
    "The register's rows are on different bases (interest paid in a calendar "
    "year, modelled cost, or none published), so their sum is not a published "
    "figure. See annual_debt_service for the published debt-service total."
)


def _loan_interest_fields(loan) -> Dict[str, Any]:
    """Rate and annual cost for one register row — only what it DECLARES.

    Read from the interest declaration on the row's newest provenance entry,
    never from ``Loan.interest_rate``: that column held the fixture's 2025
    rates and the writer's manufactured zeros, and cannot say where its value
    came from. A row with no valid declaration publishes neither figure, with
    the reason. See seeding/domains/national_debt/interest_terms.py.
    """
    from seeding.domains.national_debt.interest_terms import terms_from_provenance

    t = terms_from_provenance(loan.provenance)
    rate = t["rate_pct"]
    return {
        # Kept a "12.34%" string for existing readers; null when absent.
        "interest_rate": f"{rate:.2f}%" if rate is not None else None,
        "interest_rate_pct": rate,
        "interest_rate_basis": t["rate_basis"],
        "interest_rate_label": t["rate_label"],
        "interest_rate_source": t["rate_source"],
        "interest_rate_absent_reason": t["rate_absent_reason"],
        "annual_service_cost": t["annual_cost_kes"],
        "annual_service_basis": t["annual_cost_basis"],
        "annual_service_label": t["annual_cost_label"],
        "annual_service_source": t["annual_cost_source"],
        "annual_service_absent_reason": t["annual_cost_absent_reason"],
    }


def _loan_status(loan) -> Optional[str]:
    """"active"/"matured" from a maturity date, or None when there is none.

    Every row without a maturity date — the aggregate buckets and all 45 IDS
    creditors — used to be reported "matured", i.e. repaid.
    """
    if not loan.maturity_date:
        return None
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return "active" if loan.maturity_date > now else "matured"


def _published_annual_debt_service(db) -> Dict[str, Any]:
    """The current fiscal year's published debt service, as /fiscal/summary has it.

    Same gate and same year-selection as that endpoint (the helpers are
    shared), so the homepage loans card and the /debt revenue card cannot name
    different years or different numbers for one thing.
    """
    from models import FiscalSummary as FSModel
    from services.publication_gate import publishable_fiscal_summaries

    rows = publishable_fiscal_summaries(
        db.query(FSModel).order_by(FSModel.fiscal_year.asc()).all()
    )
    years = _select_fiscal_years([_fiscal_row_to_dict(r) for r in rows])
    current = _current_fiscal_year(years)
    # The debt-service figure's OWN source. Not budget_basis_source: that is
    # where the budget came from, and for some years it is a different
    # document from the one the debt service was read off.
    source = (current or {}).get("debt_service_source") or {}
    if not current or current.get("debt_service_cost") is None or not source.get("url"):
        return {
            "value_kes": None,
            "absent_reason": (
                "No published fiscal year carries a debt-service figure."
                if not current
                else (
                    f"{current['fiscal_year']} has no debt-service figure."
                    if current.get("debt_service_cost") is None
                    else f"{current['fiscal_year']}'s debt-service figure does "
                    "not record the document it came from, so it is not published here."
                )
            ),
        }
    return {
        "value_kes": current["debt_service_cost"],
        "fiscal_year": current["fiscal_year"],
        "measure": (
            "Total debt service: interest plus principal redemptions, "
            "domestic and external"
        ),
        "source": {
            "publisher": source.get("publisher"),
            "title": source.get("title"),
            "url": source.get("url"),
            "page": source.get("page"),
        },
        "absent_reason": None,
    }


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
                    "issue_date": (
                        loan.issue_date.strftime("%Y-%m-%d") if loan.issue_date else ""
                    ),
                    "maturity_date": (
                        loan.maturity_date.strftime("%Y-%m-%d")
                        if loan.maturity_date
                        else ""
                    ),
                    "currency": loan.currency,
                    "status": _loan_status(loan),
                    **_loan_interest_fields(loan),
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
                # null, not 0: an empty register has no total, and a KES 0
                # debt figure is a claim about Kenya, not about our database.
                "total_outstanding": None,
                "total_annual_service_cost": None,
                "total_annual_service_cost_absent_reason": "No national entity found — run seeder",
                "annual_debt_service": _published_annual_debt_service(db),
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
                # null, not 0: an empty register has no total, and a KES 0
                # debt figure is a claim about Kenya, not about our database.
                "total_outstanding": None,
                "total_annual_service_cost": None,
                "total_annual_service_cost_absent_reason": "No loan records in database — run seeder",
                "annual_debt_service": _published_annual_debt_service(db),
                "source": "No loan records in database — run seeder",
                "source_url": "",
                "last_updated": "",
            }

        national_loans = []
        total_outstanding = 0.0

        for loan in loans:
            outstanding = float(loan.outstanding or 0)
            principal = float(loan.principal or 0)
            total_outstanding += outstanding

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
                    "issue_date": (
                        loan.issue_date.strftime("%Y-%m-%d") if loan.issue_date else ""
                    ),
                    "maturity_date": (
                        loan.maturity_date.strftime("%Y-%m-%d")
                        if loan.maturity_date
                        else ""
                    ),
                    "currency": loan.currency,
                    "status": _loan_status(loan),
                    **_loan_interest_fields(loan),
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
            "total_loans": len(national_loans),  # legacy key: counts register lines
            "count_basis": "creditor_and_instrument_lines",
            "total_outstanding": total_outstanding,
            "total_annual_service_cost": None,
            "total_annual_service_cost_absent_reason": LOANS_TOTAL_SERVICE_ABSENT_REASON,
            "annual_debt_service": _published_annual_debt_service(db),
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


@app.get("/api/v1/debt/annual-reports")
async def get_annual_debt_reports():
    """Treasury's Annual Public Debt Reports, read off Treasury's own listing.

    Replaces four literal links in the budget page, all of which 404'd once
    Treasury moved to Drupal (issue #235). Unavailable means unavailable: the
    response then carries the listing URL, never a remembered list.
    """
    from services.treasury_debt_reports import fetch_annual_debt_reports

    return {
        "_meta": _response_meta(unit="none", entity_scope="national"),
        **(await fetch_annual_debt_reports()),
    }


@app.get("/api/v1/debt/instruments")
async def get_debt_instruments(db: Session = Depends(get_db)):
    """The Treasury bond register: when debt falls due, and at what coupon.

    NOT a debt total, and the response says so in three places rather than
    trusting a reader to know. The register covers roughly 60% of CBK's
    published Treasury-bond stock — it sees bonds sold at auction since 2007
    and cannot see pre-2007 paper, non-auction issuance or amortisation.

    This exists because the maturity ladder was withdrawn before launch: the
    site had 3 of 28 debt rows carrying a maturity date, five separate Eurobond
    issues collapsed onto one 2034 date, and a single assumed 14.5% coupon
    applied to the whole bond book (credibility audit F24/F42). Every figure
    here is read off CBK's own table.
    """
    if not DATABASE_AVAILABLE or db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    from models import DebtInstrument as _DI

    # The table may not exist yet. Production is still on the orphaned
    # `k1f2a3b4c5d6` revision, so this code will deploy ahead of its own
    # migration — and a route-smoke test caught this endpoint 500ing with
    # `relation "debt_instruments" does not exist` rather than reporting that
    # it has nothing. Deploy order must not decide whether a page renders.
    from services.publication_gate import (
        bond_register_withheld_disclosure,
        publishable_bond_register_rows,
    )

    try:
        # Read the whole register, then partition. The filter used to be
        # `.filter(_DI.publishable.is_(True))` on the stored column — which the
        # writer set to the literal True for every row, so it selected
        # everything and meant nothing. Applying the rule here and computing
        # the disclosure from the SAME function makes the two agree by
        # construction; the column remains the writer's persisted record of the
        # same verdict.
        stored = db.query(_DI).order_by(_DI.maturity_date.asc()).all()
    except SQLAlchemyError as exc:
        db.rollback()
        # ONLY the missing-table case. Catching every SQLAlchemyError turned
        # connection loss, timeouts, permission errors and unrelated query
        # failures into an HTTP 200 carrying a false remediation message, which
        # also hid them from 5xx monitoring.
        if not _is_undefined_table(exc):
            logging.error("debt_instruments query failed: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="debt instrument register is temporarily unavailable",
            )
        logging.warning("debt_instruments unavailable: %s", exc)
        return {
            "status": "unavailable",
            "reason": "table_not_migrated",
            "message": (
                "The instrument register table has not been created in this "
                "database yet. This is not a finding that no government debt "
                "falls due."
            ),
            "instruments": [],
            "ladder": [],
        }

    withheld_by_gate = bond_register_withheld_disclosure(stored)
    rows = publishable_bond_register_rows(stored)

    if not rows:
        # Absent, with the reason — never an empty ladder that reads as
        # "no debt falls due". Two causes, two remedies: nothing was ingested,
        # or rows are present and every one of them failed the gate. Answering
        # the first when it is the second sends a reader at the wrong problem.
        if stored:
            return {
                "status": "unavailable",
                "reason": "all_rows_withheld_by_gate",
                "message": (
                    f"{len(stored)} Treasury bond rows are stored and none can "
                    "be published: see withheld_by_gate. This is not a finding "
                    "that no government debt falls due."
                ),
                "withheld_by_gate": withheld_by_gate,
                "instruments": [],
                "ladder": [],
            }
        return {
            "status": "unavailable",
            "reason": "no_instrument_register_ingested",
            "withheld_by_gate": withheld_by_gate,
            "message": (
                "No Treasury bond register has been ingested. This is not a "
                "finding that no government debt falls due."
            ),
            "instruments": [],
            "ladder": [],
        }

    doc = rows[0].source_document
    doc_meta = (doc.meta if doc is not None else None) or {}
    coverage = doc_meta.get("coverage") or {}
    withheld = doc_meta.get("withheld_isins") or {}

    instruments = [
        {
            "isin": r.isin,
            "issue_no": r.issue_no,
            "instrument_type": r.instrument_type,
            "face_value": float(r.face_value),
            "unit": r.unit,
            "coupon_rate": float(r.coupon_rate) if r.coupon_rate is not None else None,
            "tenor_years": float(r.tenor_years) if r.tenor_years is not None else None,
            "first_issued": r.first_issued.date().isoformat() if r.first_issued else None,
            "maturity_date": r.maturity_date.date().isoformat(),
            "tranches": r.tranches,
        }
        for r in rows
    ]

    # The maturity ladder, aggregated server-side so every consumer draws the
    # same bars from the same rule.
    ladder: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        year = r.maturity_date.year
        bucket = ladder.setdefault(
            year, {"year": year, "face_value": 0.0, "instruments": 0}
        )
        bucket["face_value"] += float(r.face_value)
        bucket["instruments"] += 1

    return {
        "status": "success",
        "_meta": _response_meta(unit="kes", entity_scope="national"),
        "source": {
            "publisher": "Central Bank of Kenya",
            "title": doc.title if doc is not None else None,
            "url": doc.url if doc is not None else None,
            "as_of": doc_meta.get("as_of"),
        },
        # Said plainly, at the top level, because the sum of `instruments` is
        # the number a careless consumer would reach for.
        "is_debt_total": False,
        "not_a_stock_measure": doc_meta.get("not_a_stock_measure"),
        "coverage": coverage,
        # Two different withholdings, kept apart. `withheld_isins` is the six
        # securities the EXTRACTOR could not settle (ambiguous maturities),
        # recorded on the source document. `withheld_by_gate` is rows that
        # reached the database and cannot be published. Different facts,
        # different remedies; one count covering both would hide the newer one.
        "withheld_isins": withheld,
        "withheld_count": len(withheld),
        "withheld_by_gate": withheld_by_gate,
        "instrument_count": len(instruments),
        "instruments": instruments,
        "ladder": [ladder[y] for y in sorted(ladder)],
    }


@app.get("/api/v1/debt/national")
@cached(
    key_prefix="debt:national", ttl=NIGHTLY_REFRESH_TTL
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
                    # ``outstanding_in_total`` is the slice of a category that
                    # ``_is_debt_loan`` lets into ``total_outstanding``. It is the
                    # only honest numerator for a "share of the total" — see the
                    # percentage block near the end of this handler.
                    def _empty_category() -> dict:
                        return {
                            "principal": 0,
                            "outstanding": 0,
                            "outstanding_in_total": 0,
                            "rows_in_total": 0,
                            "count": 0,
                            "items": [],
                        }

                    categories = {
                        "external_multilateral": _empty_category(),
                        "external_bilateral": _empty_category(),
                        "external_commercial": _empty_category(),
                        "domestic_bonds": _empty_category(),
                        "domestic_bills": _empty_category(),
                        "domestic_overdraft": _empty_category(),
                        "pending_bills": _empty_category(),
                        "county_guaranteed": _empty_category(),
                        "other": _empty_category(),
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
                        # counties-literal-ok: lender-name keywords for classify_loan below, not a verdict on these counties; "County" is the catch-all term
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
                        if _is_debt_loan(loan):
                            categories[cat]["outstanding_in_total"] += outstanding
                            categories[cat]["rows_in_total"] += 1
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

                    # ONE basis for every derived figure in this response:
                    # ``outstanding``, which is what ``total_outstanding`` (the
                    # published headline) and ``check_debt_composition`` below
                    # both use. These sums read ``["principal"]`` until
                    # 2026-09-06 while being compared against an outstanding
                    # total — invisible only because every current row has
                    # principal == outstanding.
                    external_debt = sum(
                        categories[c]["outstanding"] for c in external_cats
                    )
                    domestic_debt = sum(
                        categories[c]["outstanding"] for c in domestic_cats
                    )
                    pending_bills = categories["pending_bills"]["outstanding"]
                    county_debt = categories["county_guaranteed"]["outstanding"]

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

                    # The external/domestic split is the register's OWN sum,
                    # and nothing else. It used to be the register's *total*
                    # re-divided by DebtTimeline's proportion:
                    #
                    #     external_debt = _base * (_tl_ext / _tl_split)
                    #     domestic_debt = _base * (_tl_dom / _tl_split)
                    #
                    # which put two contradictory splits in one response — the
                    # summary card said 5,265.0 / 6,591.0 while the category
                    # block below it said 4,797.3 / 7,058.7, a 467.7Bn
                    # disagreement on one page (audit 2026-09-06 §P1-3).
                    #
                    # The comment that justified it said the register
                    # "under-represents domestic instruments (T-bonds/bills),
                    # which inverted the split". That was true when written and
                    # is not true now: the domestic side carries the CBK
                    # bulletin overlay at 7,058.7Bn — MORE than CBK's own
                    # Dec-2025 domestic figure of 6,837.5Bn — and already leads
                    # the external side unaided. The correction had begun
                    # producing the error it was added to prevent, moving
                    # domestic 467.7Bn away from the register that measured it.
                    #
                    # ``latest_timeline_row`` is still read below, for the
                    # reconciliation block: DebtTimeline is an independent
                    # source to CHECK this endpoint against, not an input to it.

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
                                # Which of the two money columns these are. The
                                # split was read off ``principal`` while being
                                # published beside an ``outstanding`` headline,
                                # and nothing in the payload said so.
                                "basis": "outstanding",
                                "external_debt": external_debt,
                                "domestic_debt": domestic_debt,
                                "pending_bills": pending_bills,
                                "county_guaranteed": county_debt,
                                # Denominator is ``total_outstanding`` — the same
                                # figure the numerators come from, so the two
                                # percentages sum to 100 of the published total.
                                "external_percentage": (
                                    round(external_debt / total_outstanding * 100, 1)
                                    if total_outstanding > 0
                                    else None
                                ),
                                "domestic_percentage": (
                                    round(domestic_debt / total_outstanding * 100, 1)
                                    if total_outstanding > 0
                                    else None
                                ),
                            },
                            # Detailed categorized breakdown
                            "categories": {
                                cat: {
                                    "total_principal": data["principal"],
                                    "total_outstanding": data["outstanding"],
                                    "loan_count": data["count"],
                                    # Share of ``total_outstanding``, computed
                                    # from the part of this category that is
                                    # actually IN that total.
                                    #
                                    # Every category used to be divided by this
                                    # denominator including ``pending_bills``,
                                    # which ``_is_debt_loan`` deliberately keeps
                                    # OUT of it — so production's seven shares
                                    # summed to 107.86%, the excess being exactly
                                    # the row that does not belong (audit
                                    # 2026-09-06 §P2-9). There is no correct
                                    # share to publish for a category outside the
                                    # denominator, so it is withheld with a
                                    # reason rather than filled with a number
                                    # that adds up to nothing.
                                    **_category_share_of_total(
                                        data, total_outstanding
                                    ),
                                    # The named lenders the treemap draws,
                                    # plus what is left over.
                                    #
                                    # This used to be `items[:5]` in query
                                    # order: not the largest five, and no way
                                    # to know anything had been dropped. The
                                    # treemap's long-tail fold could therefore
                                    # never fire, and its drill-down did not
                                    # add up to the category total beside it.
                                    **_category_items_with_remainder(data),
                                }
                                for cat, data in categories.items()
                                if data["count"] > 0
                            },
                            # The risk rating is the joint Bank-Fund DSA's,
                            # verbatim and cited. It used to be "High" above
                            # an unsourced 65% debt-to-GDP, with a sentence
                            # attributing that to the IMF (issue #269). No
                            # figure computed here feeds it.
                            "debt_sustainability": {
                                "debt_to_gdp": debt_to_gdp_ratio,
                                "imf_dsa": kenya_dsa_rating(),
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
            # Not our figure, so an empty register does not withhold it.
            "debt_sustainability": {"imf_dsa": kenya_dsa_rating()},
        },
        "currency": "KES",
        "source": "Central Bank of Kenya / National Treasury",
    }


def _pending_bills_provenance(loan) -> Dict[str, Any]:
    """A pending-bills row's provenance as a dict, whichever shape it is stored in."""
    raw = loan.provenance
    if isinstance(raw, list):
        return raw[0] if raw and isinstance(raw[0], dict) else {}
    return raw if isinstance(raw, dict) else {}


def _published_pending_bills(db: Session) -> Tuple[List[tuple], Dict[str, Any]]:
    """The pending-bills rows a reader may publish, and the totals they make.

    One rule for every row: it declares the publication for its side — the
    Treasury BROP for a national line, the Controller of Budget's year-end
    report for a county (:func:`pending_bills_row_is_published`) — and carries
    a real amount (:func:`pending_bills_row_amount`). ``/pending-bills`` and the debt page's
    ``/pending-bills/summary`` both read through here, so they cannot disagree.

    National rows used to be summed whatever wrote them. Production served
    ``national_total`` 931.3B: the BROP's two para-18 lines (404.3B State
    Corporations + 121.6B MDAs = the 525.9B it prints) plus eleven ministry and
    state-corporation rows from the git fixture (405.4B) — members of those two
    lines, counted a second time (#265).

    Returns ``(rows, totals)``. Each row is ``(loan, entity_name, entity_type,
    amount)``. ``totals`` holds ``national``, ``county`` and ``total``, each
    None unless its population is complete: the two national categories or
    all 47 distinct counties, each side from one writer publication batch.
    ``reported_county_sum`` labels the available rows without certifying a
    complete county total. ``unpublished`` counts rows present but withheld.
    ``total`` adds the complete halves only when every row states the same
    as-at date. Different publication batches, partial updates and stocks
    stated a year apart cannot produce a combined total.
    """
    from models import DebtCategory

    loans = (
        db.query(DBLoan)
        .options(joinedload(DBLoan.entity))
        .filter(DBLoan.debt_category == DebtCategory.PENDING_BILLS)
        .order_by(DBLoan.id)
        .all()
    )
    # Batch-load all entity names in ONE query (avoid N+1 with remote DB)
    entity_map: Dict[int, tuple] = {}
    unique_eids = list({l.entity_id for l in loans if l.entity_id})
    if unique_eids:
        for eid, ename, etype in (
            db.query(DBEntity.id, DBEntity.canonical_name, DBEntity.type)
            .filter(DBEntity.id.in_(unique_eids))
            .all()
        ):
            entity_map[eid] = (ename, etype.value if etype else "national")

    rows = []
    county_candidates = []
    for loan in loans:
        entity_info = entity_map.get(loan.entity_id)
        if entity_info is None:
            continue
        entity_name, entity_type = entity_info
        if not pending_bills_row_is_published(loan, entity_type=entity_type):
            continue
        if entity_type == "county":
            county_candidates.append(loan)
            continue
        amount = pending_bills_row_amount(loan)
        if amount is None:
            continue
        rows.append((loan, entity_name, entity_type, amount))
    common_date = max(
        (pending_bills_row_as_at(l) for l in county_candidates), default=None
    )
    by_county = {}
    for loan in county_candidates:
        by_county.setdefault(loan.entity_id, []).append(loan)
    county_absence = {}
    for eid, observations in by_county.items():
        selection = select_county_pending_bills(observations, as_at=common_date)
        if selection["amount"] is None:
            county_absence[entity_map[eid][0]] = selection["absent_reason"]
        else:
            loan = selection["rows"][0]
            rows.append((loan, entity_map[eid][0], "county", selection["amount"]))

    from services.county_identity import OFFICIAL_COUNTY_CODES, official_county_code

    national_rows = [r for r in rows if r[2] != "county"]
    county_rows = [r for r in rows if r[2] == "county"]

    def one_edition(side_rows):
        # A same-title source document can be updated in place to another
        # artifact URL. Its ID alone cannot prove these rows came together.
        editions = [
            (loan.source_document_id, _pending_bills_provenance(loan).get("source_url"),
             pending_bills_row_as_at(loan), _pending_bills_provenance(loan).get("publication_batch"))
            for loan, *_ in side_rows
        ]
        return bool(editions) and all(
            item[0] is not None
            and all(isinstance(v, str) and v.strip() for v in item[1:])
            and re.fullmatch(r"[0-9a-f]{64}", item[3]) is not None
            and item == editions[0] for item in editions
        )

    national_complete = (
        len(national_rows) == 2
        and {_pending_bills_provenance(r[0]).get("category") for r in national_rows}
        == {"mda", "state_corporation"}
        and one_edition(national_rows)
    )
    county_codes = {official_county_code(name) for _loan, name, _type, _amount in county_rows}
    qualified_counties = [
        name for loan, name, _type, _amount in county_rows
        if _pending_bills_provenance(loan).get("reader_notes")
    ]
    county_complete = (
        len(county_rows) == len(OFFICIAL_COUNTY_CODES)
        and county_codes == set(OFFICIAL_COUNTY_CODES)
        and one_edition(county_rows)
        and not qualified_counties
    )
    national_total = sum(r[3] for r in national_rows) if national_complete else None
    county_total = sum(r[3] for r in county_rows) if county_complete else None
    as_at_dates = {pending_bills_row_as_at(loan) for loan, *_rest in rows}
    one_day = len(as_at_dates) == 1 and None not in as_at_dates
    total = (
        national_total + county_total
        if national_total is not None and county_total is not None and one_day
        else None
    )
    total_absent_reason = (
        "incomplete_national_publication" if not national_complete
        else "incomplete_county_publication" if not county_complete
        else "national_and_county_stated_at_different_dates" if not one_day
        else None
    )
    return rows, {
        "national": national_total,
        "county": county_total,
        "total": total,
        "total_absent_reason": total_absent_reason,
        "coverage": {
            "national_components": len(national_rows),
            "national_expected": 2,
            "national_complete": national_complete,
            "county_count": len(county_rows),
            "county_expected": len(OFFICIAL_COUNTY_CODES),
            "county_complete": county_complete,
            "missing_counties": [
                name
                for code, name in OFFICIAL_COUNTY_CODES.items()
                if code not in county_codes
            ],
            "qualified_counties": qualified_counties,
            "county_absent_reasons": county_absence,
            "county_reporting_date": common_date,
            "county_selection_policy": "latest_common_reporting_date",
        },
        "reported_county_sum": sum(r[3] for r in county_rows) if county_rows else None,
        "as_at": next(iter(as_at_dates)) if one_day else None,
        "national_as_at": _one_as_at(
            loan for loan, _n, etype, _a in rows if etype != "county"
        ),
        "county_as_at": common_date,
        "unpublished": len(loans) - len(rows),
    }


def _one_as_at(loans) -> Optional[str]:
    """The as-at date a set of rows shares, or None when they differ or omit it."""
    dates = {pending_bills_row_as_at(loan) for loan in loans}
    return next(iter(dates)) if len(dates) == 1 and None not in dates else None


@app.get("/api/v1/pending-bills")
@cached(key_prefix="pending_bills:summary", ttl=NIGHTLY_REFRESH_TTL)
async def get_pending_bills(
    db: Session = Depends(get_db),
):
    """Government pending bills, each half from the publication that first prints it.

    Pending bills are verified unpaid invoices owed by the government to
    suppliers and contractors. The National Government's (State Corporations
    and MDAs) are read from the Treasury's annual Budget Review and Outlook
    Paper; the counties' from the Controller of Budget's full-year County
    Governments Budget Implementation Review Report, stated at 30 June — the
    table the BROP itself reprints (#238). A row is served only when it
    declares the publication for its side — see
    :func:`_published_pending_bills`.

    There used to be a second strategy: with no rows in the database, scrape
    the Controller of Budget live, on the request path, and serve its national
    rows ungated. It was a second publication for the same figure (#265) and is
    gone; an empty table answers ``no_data``.
    """
    try:
        rows, totals = _published_pending_bills(db)
    except SQLAlchemyError:
        # A failed read is not "nothing published". This used to catch every
        # exception and fall through to the no-data answer, so a dead database
        # and an empty table looked the same.
        logging.exception("pending-bills: database read failed")
        raise HTTPException(status_code=503, detail="Pending bills are unavailable")

    if rows:
        bills = []
        for loan, entity_name, entity_type, amount in rows:
            provenance = _pending_bills_provenance(loan)
            # A more descriptive name than the entity: the provenance's own
            # name if it carries one, else the lender field.
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
                    "total_pending": amount,
                    "eligible_pending": provenance.get("eligible_pending"),
                    "ineligible_pending": provenance.get("ineligible_pending"),
                    "fiscal_year": provenance.get("fiscal_year", ""),
                    "as_at": pending_bills_row_as_at(loan),
                    "category": provenance.get("category", "mda"),
                    "notes": provenance.get("notes"),
                    "reader_notes": provenance.get("reader_notes") or [],
                    "source_document_id": loan.source_document_id,
                    "source_url": provenance.get("source_url"),
                    "table": provenance.get("table"),
                    "page_ref": loan.page_ref or provenance.get("page_ref"),
                    "page": provenance.get("page"),
                    "publication_batch": provenance.get("publication_batch"),
                }
            )

        # The sources are the published rows' documents, never an unpublished
        # row's — the fixture's cited a COB URL that resolves to a template.
        # One per side, because since #238 the two halves are two publications.
        sources = []
        docs = {
            doc.id: doc
            for doc in db.query(DBSourceDocument).filter(
                DBSourceDocument.id.in_({loan.source_document_id for loan, *_ in rows})
            )
        }
        seen_sources = set()
        for loan, _name, entity_type, _amount in rows:
            side = "county" if entity_type == "county" else "national"
            prov = _pending_bills_provenance(loan)
            key = (
                side,
                loan.source_document_id,
                prov.get("source_url"),
                pending_bills_row_as_at(loan),
            )
            if key in seen_sources:
                continue
            seen_sources.add(key)
            doc = docs.get(loan.source_document_id)
            sources.append(
                {
                    "side": side,
                    "source_document_id": loan.source_document_id,
                    "title": doc.title if doc else side,
                    "url": prov.get("source_url"),
                    "as_at": pending_bills_row_as_at(loan),
                }
            )
        source_title = "; ".join(src["title"] for src in sources)
        source_url = sources[0]["url"] if sources else None

        last_updated = max(
            (l.updated_at or l.created_at for l, *_rest in rows if l.updated_at or l.created_at),
            default=None,
        )
        return {
            "status": "success",
            "data_source": "database",
            # A string: a datetime here made the whole response unserialisable
            # for the cache, so every request re-ran the query.
            "last_updated": last_updated.isoformat() if last_updated else None,
            "pending_bills": bills,
            "summary": {
                # Each null, not 0, when nothing is published for it — and the
                # total null unless both halves are (see _published_pending_bills).
                "total_pending": totals["total"],
                "national_total": totals["national"],
                "county_total": totals["county"],
                "total_absent_reason": totals["total_absent_reason"],
                "coverage": totals["coverage"],
                "reported_county_sum": totals["reported_county_sum"],
                # The day each figure is a stock on; ``as_at`` only when both
                # halves share one, which is also when ``total_pending`` is set.
                "as_at": totals["as_at"],
                "national_as_at": totals["national_as_at"],
                "county_as_at": totals["county_as_at"],
                "record_count": len(bills),
            },
            "source": source_title,
            "source_url": source_url,
            "sources": sources,
            "currency": "KES",
            "_meta": _response_meta(unit="kes", entity_scope="all"),
            "explanation": (
                "Pending bills are verified but unpaid government invoices "
                "to suppliers and contractors. Unlike formal loans, they "
                "carry no interest but represent real obligations. "
                "The National Treasury publishes the National Government's "
                "each year in the Budget Review and Outlook Paper; the "
                "Controller of Budget publishes each county's at 30 June in "
                "its County Governments Budget Implementation Review Report."
            ),
        }

    return {
        "status": "no_data",
        "data_source": "none",
        "pending_bills": [],
        "summary": {
            # Absent, not zero: nothing has been published here.
            "total_pending": None,
            "national_total": None,
            "county_total": None,
            "total_absent_reason": totals["total_absent_reason"],
            "coverage": totals["coverage"],
            "reported_county_sum": totals["reported_county_sum"],
            "county_as_at": totals["county_as_at"],
            "record_count": 0,
        },
        # Rows that exist but do not declare their side's publication —
        # written before the declaration existed, from the fixture, or a BROP
        # county row from before #238. Not a figure; a count.
        "unpublished_row_count": totals["unpublished"],
        "source": (
            "National Treasury — Budget Review and Outlook Paper; Controller "
            "of Budget — County Governments Budget Implementation Review Report"
        ),
        "source_url": "https://www.treasury.go.ke/budget-review-and-outlook-paper/",
        "currency": "KES",
        "explanation": (
            "No current pending-bills balance is eligible for publication. "
            "Coverage and absence reasons distinguish missing observations "
            "from conflicting source evidence."
        ),
    }


# ── Pending Bills Summary & County Breakdown ──────────────────────────


@app.get("/api/v1/pending-bills/summary")
@cached(key_prefix="pending_bills:summary_enhanced", ttl=NIGHTLY_REFRESH_TTL)
async def get_pending_bills_summary(db: Session = Depends(get_db)):
    """Get pending bills summary: total, breakdown by type, top counties, trend.

    Pending bills are ``Loan`` rows with ``debt_category = PENDING_BILLS``,
    written by ``seeding/domains/pending_bills/writer.py``. There used to be a
    ``pending_bills`` table read first, with this path as its fallback; nothing
    ever wrote that table, so production always served this path and the
    table branch ran only under test fixtures (issue #137 P6).
    """
    try:
        return _pending_bills_summary_from_loans(db)
    except Exception as e:
        logging.error(f"Pending bills summary failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


#: Bill-type keywords, matched against a lender string. Weak evidence, but not
#: no evidence — a row reading "Pending Bills — Salary Arrears" does say what
#: it is.
_BILL_TYPE_KEYWORDS = (
    ("salary", ("salary", "wage")),
    ("pension", ("pension",)),
    ("statutory", ("statutory",)),
    ("court_awards", ("court", "award")),
)

#: Where a row goes when the lender string says nothing about its type.
#:
#: This used to be ``supplier_arrears``, unconditionally. Nothing in the
#: register's lender strings matches any keyword above, so production reported
#: 100% supplier arrears — presented as a finding about the composition of
#: Kenya's arrears, actually a statement about a dictionary having no matches
#: (audit 2026-09-06 §P1-7).
_BILL_TYPE_UNCLASSIFIED = "unclassified"


def _bill_type_from_lender(lender: Optional[str]) -> str:
    text = (lender or "").lower()
    for bill_type, terms in _BILL_TYPE_KEYWORDS:
        if any(term in text for term in terms):
            return bill_type
    return _BILL_TYPE_UNCLASSIFIED


def _normalised_fiscal_year(raw: Optional[str]) -> Optional[str]:
    """Canonical ``FY{YYYY}/{YY}``, or None when the label is not one.

    Trend keys were taken verbatim from provenance, so ``"FY 2024/25"`` and
    ``"FY2024/25"`` drew one fiscal year as two points — 702.8Bn and 405.4Bn,
    a year that appeared to have halved, whose two halves sum to the total
    printed above the chart (audit 2026-09-06 §P2-13).

    ``normalize_fiscal_label`` keeps sub-period markers distinct, so
    ``"FY2025/26 Q1"`` does not fold into ``"FY2025/26"`` — a quarter and a
    year are different quantities and adding them would be a new version of
    the same bug.
    """
    from seeding.utils import normalize_fiscal_label

    label = (raw or "").strip()
    if not label or label.lower() == "unknown":
        return None
    try:
        return normalize_fiscal_label(label)
    except (ValueError, IndexError):
        logging.warning("pending-bills trend: unparseable fiscal label %r", label)
        return None


def _pending_bills_summary_from_loans(db: Session) -> dict:
    """Build the summary from the published PENDING_BILLS loan rows.

    Every figure here is built from :func:`_published_pending_bills` — the
    same rows, and the same total, ``/pending-bills`` serves.
    """
    rows, totals = _published_pending_bills(db)
    if not rows:
        reason = (
            "no_available_current_county_stock"
            if totals["coverage"]["county_absent_reasons"]
            else "no_row_declares_its_publication"
            if totals["unpublished"]
            else "no_pending_bills_rows"
        )
        return {
            "status": "no_data",
            # Absent, not zero: withheld rows are not a total of nothing.
            "total_pending_amount": None,
            "total_absent_reason": totals["total_absent_reason"],
            "coverage": totals["coverage"],
            "reported_county_sum": totals["reported_county_sum"],
            "county_as_at": totals["county_as_at"],
            "eligible_total": None,
            "ineligible_total": None,
            "breakdown_by_type": {},
            "breakdown_by_type_absent_reason": reason,
            "top_counties_by_amount": [],
            "aging_buckets": None,
            "aging_buckets_absent_reason": reason,
            "trend": [],
            "trend_unattributed_amount": 0,
            "currency": "KES",
            "note": "No current pending-bills balance is eligible; see coverage and absence reasons.",
        }

    # Counties only. This ranked every entity with a pending-bills row under
    # the key ``top_counties_by_amount`` — the national government's two
    # aggregates and eleven ministries sat above Nairobi on the debt page's
    # "top counties" list.
    county_totals: Dict[int, Dict[str, Any]] = {}
    for loan, entity_name, entity_type, amount in rows:
        if entity_type != "county":
            continue
        eid = loan.entity_id
        if eid not in county_totals:
            county_totals[eid] = {
                "county": entity_name,
                "entity_id": eid,
                "amount": 0,
            }
        county_totals[eid]["amount"] += amount

    top_counties = sorted(
        county_totals.values(), key=lambda x: x["amount"], reverse=True
    )[:15]

    # Bill type, inferred from the lender string where the lender string
    # actually says something. Rows it does not are ``unclassified``, not
    # ``supplier_arrears`` — see :data:`_BILL_TYPE_UNCLASSIFIED`.
    breakdown_by_type: Dict[str, float] = {}
    for loan, _name, _type, amount in rows:
        bt = _bill_type_from_lender(loan.lender)
        breakdown_by_type[bt] = breakdown_by_type.get(bt, 0) + amount
    breakdown_by_type_absent_reason = (
        "loans_table_carries_no_bill_type"
        if set(breakdown_by_type) <= {_BILL_TYPE_UNCLASSIFIED}
        else None
    )

    # Trend by fiscal year, on CANONICAL labels — see
    # :func:`_normalised_fiscal_year`. Money whose row names no usable fiscal
    # year is reported as a total rather than dropped in silence: the chart's
    # bars used not to sum to the figure printed above them, and nothing said
    # why.
    #
    # Not across the two halves on two days. Since #238 the national lines
    # (BROP) and the county lines (CoB) can be stated a year apart, and
    # bucketing them by fiscal year drew two bars — national at 30 June 2025,
    # counties at 30 June 2026 — that read as a fall from 525.9B to 172.5B.
    # Both halves must also contain a complete population from one edition.
    trend_map: Dict[str, float] = {}
    trend_unattributed = 0.0
    trend_absent_reason = None
    if totals["total_absent_reason"]:
        trend_absent_reason = totals["total_absent_reason"]
    else:
        for loan, _name, _type, amount in rows:
            fy = _normalised_fiscal_year(_pending_bills_provenance(loan).get("fiscal_year"))
            if fy is None:
                trend_unattributed += amount
                continue
            trend_map[fy] = trend_map.get(fy, 0) + amount
    trend = [{"year": k, "total_amount": v} for k, v in sorted(trend_map.items())]

    # Eligible / Ineligible totals from provenance — null, not 0, when no
    # published row carries the split. The BROP prints none; the 308.1B /
    # 97.3B production served was the fixture's alone (#265).
    def _split_total(key: str) -> Optional[float]:
        from services.fiscal_outturns import finite_number

        if totals["total"] is None:
            return None
        values = [
            finite_number(_pending_bills_provenance(loan).get(key))
            for loan, *_rest in rows
        ]
        return sum(values) if all(value is not None for value in values) else None

    return {
        "status": "success",
        "data_source": "loans_table_fallback",
        # Null unless national and county are both published and stated at
        # one date — the same figure /pending-bills prints.
        "total_pending_amount": totals["total"],
        "total_absent_reason": totals["total_absent_reason"],
        "coverage": totals["coverage"],
        "reported_county_sum": totals["reported_county_sum"],
        "as_at": totals["as_at"],
        "national_as_at": totals["national_as_at"],
        "county_as_at": totals["county_as_at"],
        "eligible_total": _split_total("eligible_pending"),
        "ineligible_total": _split_total("ineligible_pending"),
        "breakdown_by_type": breakdown_by_type,
        "breakdown_by_type_absent_reason": breakdown_by_type_absent_reason,
        "top_counties_by_amount": top_counties,
        # Withheld, not asserted.
        #
        # This was ``{"0-30d": 0, "31-90d": 0, "91-180d": 0, "180d+": total}``:
        # a claim that 100% of KSh 1.108 TRILLION is more than 180 days
        # overdue, made by a code path reading a table that has no aging
        # column at all (audit 2026-09-06 §P1-4). The difference between a
        # bill 20 days old and one 400 days old is the difference between
        # routine and default, and this asserted the second for all of it.
        "aging_buckets": None,
        "aging_buckets_absent_reason": "loans_table_carries_no_aging_data",
        "trend": trend,
        "trend_absent_reason": trend_absent_reason,
        "trend_unattributed_amount": trend_unattributed,
        "currency": "KES",
        "note": "Derived from loans table (debt_category = PENDING_BILLS).",
    }


@app.get("/api/v1/pending-bills/counties/{county_id}")
@cached(key_prefix="pending_bills:county", ttl=NIGHTLY_REFRESH_TTL)
async def get_pending_bills_by_county(county_id: str, db: Session = Depends(get_db)):
    """Get pending bills breakdown for a specific county by type and aging."""
    try:
        # Resolve county entity
        entity = _resolve_county_entity(db, county_id)
        if not entity:
            raise HTTPException(
                status_code=404, detail=f"County '{county_id}' not found"
            )

        # Pending bills are Loan rows in the PENDING_BILLS category; see
        # get_pending_bills_summary for why there is no pending_bills table.
        from models import DebtCategory

        pending_loans = [
            l
            for l in (
                db.query(DBLoan)
                .filter(
                    DBLoan.entity_id == entity.id,
                    DBLoan.debt_category == DebtCategory.PENDING_BILLS,
                )
                .all()
            )
            if county_pending_bills_row_is_published(l)
        ]
        # The same figure the county page prints beside this card, and
        # null — not 0 — for a county the CoB year-end report has no
        # figure for.
        reporting_date = county_pending_reporting_date(db)
        selection = select_county_pending_bills(pending_loans, as_at=reporting_date)
        pending_observations = pending_loans
        pending_loans = selection["rows"]
        total = selection["amount"]
        # The same two assertions the national fallback used to make, on
        # the page that never carried the debt page's disclaimer: 100% of
        # this county's arrears declared over 180 days old, and 100%
        # declared supplier arrears, from a table holding neither fact.
        by_type: Dict[str, float] = {}
        for l in pending_loans:
            bt = _bill_type_from_lender(l.lender)
            by_type[bt] = by_type.get(bt, 0) + (pending_bills_row_amount(l) or 0.0)
        return {
            "status": "success" if pending_loans else "no_data",
            "data_source": "loans_table_fallback" if pending_loans else "none",
            "county": entity.canonical_name,
            "county_id": county_id,
            "total_pending": total,
            **_county_pending_bills_fields(
                pending_observations, total, reporting_date=reporting_date
            ),
            "selection": {k: v for k, v in selection.items() if k != "rows"},
            "breakdown_by_type": by_type,
            "breakdown_by_type_absent_reason": (
                "loans_table_carries_no_bill_type"
                if by_type and set(by_type) <= {_BILL_TYPE_UNCLASSIFIED}
                else None
            ),
            "aging_buckets": None,
            "aging_buckets_absent_reason": (
                "loans_table_carries_no_aging_data"
                if pending_loans
                else "no_pending_bills_rows"
            ),
            "bills": [],
            "currency": "KES",
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Pending bills county lookup failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _resolve_county_name(county_id: str, db: "Optional[Session]" = None) -> Optional[str]:
    """Resolve a legacy route, explicit official code, entity PK or slug."""
    cid = str(county_id or "").strip()
    if cid in COUNTY_MAPPING:
        return COUNTY_MAPPING[cid]
    if not DATABASE_AVAILABLE:
        return None
    if db is not None:
        entity = _resolve_county_entity(db, cid)
        return entity.canonical_name.removesuffix(" County") if entity else None
    with next(get_db()) as session:
        entity = _resolve_county_entity(session, cid)
        return entity.canonical_name.removesuffix(" County") if entity else None


def _resolve_county_entity(db: Session, county_id: str):
    """Resolve identifiers without interchanging their namespaces.

    ``001`` is the legacy Nairobi URL, ``code:001`` is official Mombasa,
    unpadded ``4`` is an Entity primary key, and slugs keep their identity.
    """
    from services.county_identity import resolve_official_county_entity

    cid = str(county_id or "").strip()
    if cid.startswith("code:"):
        return resolve_official_county_entity(db, cid[5:])
    if cid in COUNTY_MAPPING:
        return resolve_official_county_entity(
            db, official_county_code(COUNTY_MAPPING[cid])
        )
    if cid.isdigit():
        return (
            db.query(DBEntity)
            .join(DBCountry, DBEntity.country_id == DBCountry.id)
            .filter(
                DBEntity.id == int(cid),
                DBEntity.type == EntityType.COUNTY,
                DBCountry.iso_code == "KEN",
            )
            .first()
        )
    entity = (
        db.query(DBEntity)
        .join(DBCountry, DBEntity.country_id == DBCountry.id)
        .filter(
            DBEntity.slug == cid.lower(),
            DBEntity.type == EntityType.COUNTY,
            DBCountry.iso_code == "KEN",
        )
        .first()
    )
    if entity is not None:
        return entity
    return resolve_official_county_entity(db, official_county_code(cid))


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
async def get_debt_sustainability(db: Session = Depends(get_db)):
    """Get debt sustainability indicators, projections, and regional comparison.

    Returns debt-to-GDP, debt-service-to-revenue, external share,
    5-year projections, and EAC regional peers.
    """
    from models import DebtTimeline, FiscalSummary
    from services.fiscal_outturns import finite_number, has_source_locator

    try:
        # Latest debt timeline entry (has debt/GDP data)
        latest_dt = db.query(DebtTimeline).order_by(DebtTimeline.year.desc()).first()
        # Latest fiscal summary (has debt service and revenue) — the newest
        # row that cites a page.
        from services.publication_gate import latest_publishable_fiscal_summary

        latest_fs = latest_publishable_fiscal_summary(db)

        _imf_headline = _latest_imf_debt_to_gdp(db)
        if not latest_dt and not latest_fs and _imf_headline is None:
            return {
                "status": "no_data",
                "note": "Run seeders: debt_timeline and fiscal_summary",
                "imf_dsa": kenya_dsa_rating(),
                "debt_to_gdp": None,
                "debt_service_to_revenue": None,
                "debt_service_to_revenue_absent_reason": "No fiscal inputs with separate source locators are available.",
                "external_debt_share": None,
                "projections": [],
                "projections_source": None,
                "projections_absent_reason": "no_published_projection_seeded",
                "regional_peers": _get_regional_peers(),
                "regional_peers_basis": _peer_column_basis(None),
            }

        # ── Debt-to-GDP ────────────────────────────────────────────
        #
        # Same helper, same measure and same declared basis as
        # /debt/national's headline. This read DebtTimeline.gdp_ratio, so the
        # site published TWO debt-to-GDP figures for one year under one label:
        # 69.3 on the homepage (IMF GGXWDG_NGDP, basis declared) and 70.0 here
        # (basis undeclared). DebtTimeline remains a legitimate fallback; an
        # undeclared basis was the defect, not the series.
        ratio = None
        ratio_year = None
        ratio_basis = None
        ratio_source = None
        if _imf_headline is not None:
            ratio, ratio_year = finite_number(_imf_headline[0]), _imf_headline[1]
            ratio_basis = (
                "IMF General Government Gross Debt, % of GDP (GGXWDG_NGDP) "
                "— vintage-consistent"
            )
            ratio_source = "IMF World Economic Outlook"
        elif latest_dt and latest_dt.gdp_ratio is not None:
            ratio = finite_number(latest_dt.gdp_ratio)
            ratio_year = latest_dt.year
            ratio_basis = (
                "Central government debt / nominal GDP (CBK debt timeline) "
                "— not the IMF general-government measure"
            )
            ratio_source = "CBK Annual Reports / National Treasury BPS"

        debt_to_gdp = None
        if ratio is not None:
            debt_to_gdp = {
                "value": ratio,
                "year": ratio_year,
                "basis": ratio_basis,
                "source": ratio_source,
                "vintage": _imf_headline[2] if _imf_headline else None,
                "source_document_id": latest_dt.source_document_id if latest_dt and not _imf_headline else None,
                "assessment": "Nominal debt ratio; not comparable to present-value debt benchmarks. See the separately cited DSA assessment.",
            }

        # ── Debt Service to Revenue ────────────────────────────────
        debt_service_to_revenue = None
        debt_service_absent_reason = "Finite debt-service and positive revenue inputs with separate source locators are required."
        if latest_fs and latest_fs.debt_service_cost is not None and latest_fs.total_revenue is not None:
            ds = finite_number(latest_fs.debt_service_cost)
            rev = finite_number(latest_fs.total_revenue)
            meta = latest_fs.meta if isinstance(latest_fs.meta, dict) else {}
            framework = meta.get("fiscal_framework")
            framework = framework if isinstance(framework, dict) else {}
            source = framework.get("source")
            source = source if isinstance(source, dict) else {}
            if (ds is not None and rev is not None and rev > 0
                    and has_source_locator(meta.get("debt_service_source"))
                    and has_source_locator(meta.get("revenue_source"))):
                ratio_val = round(ds / rev * 100, 1)
                debt_service_to_revenue = {
                    "value": ratio_val,
                    "year": latest_fs.fiscal_year,
                    "basis": "App calculation: total debt service (interest and principal) / fiscal revenue × 100; no risk threshold applied.",
                    "source_document_id": latest_fs.source_document_id,
                    "page_ref": latest_fs.page_ref,
                    "debt_service_source": meta.get("debt_service_source"),
                    "revenue_source": meta.get("revenue_source"),
                    "source_column": source.get("column"),
                }
                debt_service_absent_reason = None

        # ── External Debt Share ────────────────────────────────────
        external_share = None
        if latest_dt and latest_dt.total is not None and latest_dt.external is not None:
            total = finite_number(latest_dt.total)
            ext = finite_number(latest_dt.external)
            if total is not None and total > 0 and ext is not None and ext <= total:
                external_share = round(ext / total * 100, 1)

        # ── Projections: published, or absent ──────────────────────
        projections, projections_source, projections_absent_reason = (
            _published_debt_projections(db)
        )

        # ── Regional Peers ─────────────────────────────────────────
        #
        # Kenya's cell used to be overwritten with DebtTimeline.gdp_ratio,
        # which made Kenya the one country in its own comparison measured
        # differently from its four comparators — and did not even match the
        # site's declared headline. It is now the same figure, basis and year
        # as the headline above it, and the whole column is pinned to that
        # year (see :func:`_imf_fetch_debt_to_gdp`). Where no IMF reference
        # year exists, no country is special-cased.
        _peer_reference_year = ratio_year if _imf_headline is not None else None
        peers = _get_regional_peers(
            kenya_debt_to_gdp=(ratio if _imf_headline is not None else None),
            reference_year=_peer_reference_year,
        )

        return {
            "status": "success",
            "_meta": _response_meta(unit="percentage", entity_scope="national"),
            "debt_to_gdp": debt_to_gdp,
            "imf_dsa": kenya_dsa_rating(),
            "debt_service_to_revenue": debt_service_to_revenue,
            "debt_service_to_revenue_absent_reason": debt_service_absent_reason,
            "external_debt_share": external_share,
            "projections": projections,
            "projections_source": projections_source,
            "projections_absent_reason": projections_absent_reason,
            "regional_peers": peers,
            # What each peer column measures. The peer table repeats Kenya
            # beside the headline above it, so an undeclared basis here is a
            # contradiction on one page rather than a footnote.
            "regional_peers_basis": _peer_column_basis(_peer_reference_year),
            "currency": "KES",
            "source": "National Treasury BPS, CBK Annual Reports",
        }

    except Exception as e:
        logging.error(f"Debt sustainability failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


#: The projection series that already exists in this database, seeded nightly
#: by ``backend.seeding.domains.imf_weo`` and already served by
#: ``/api/v1/debt/broader``.
_PROJECTION_INDICATOR = "GGXWDG_NGDP"
_PROJECTION_SOURCE_LABEL = "IMF World Economic Outlook (GGXWDG_NGDP)"


def _published_debt_projections(db: Session) -> tuple:
    """Kenya's PUBLISHED debt-to-GDP projection, or nothing and a reason.

    Returns ``(projections, source_label, absent_reason)``.

    This was a least-squares fit over the last five ``DebtTimeline`` points,
    emitted as ``projected_debt_to_gdp``: 70.4 / 70.7 / 71.0 / 71.3 / 71.6 —
    +0.3 every year, to 2030. Nobody published that. It was a straight line
    drawn through five historical observations and given a forecast's name
    (audit 2026-09-06 §P2-12).

    It was also wrong in a checkable way. The IMF's actual projection for
    Kenya sits in ``imf_weo_observations`` in the same database — 71.6 / 72.4 /
    73.3 / 73.6 / 74.2 — so the fitted line understated the one published
    forecast available by 2.6 points of GDP at 2030.

    It is also a basis fix, not only an accuracy one. The fit ran over
    ``DebtTimeline.gdp_ratio``, so the projection chart did not even start
    from the figure the page states above it: the headline is IMF
    GGXWDG_NGDP (69.3 for 2025 — see the debt-to-GDP block in
    :func:`get_debt_sustainability`), while the line began at DebtTimeline's
    70.0. These rows continue the headline's own series.

    Read the newest vintage only. IMF publishes twice a year and every
    snapshot is kept, so mixing vintages would splice two forecasts into one
    curve. When nothing is seeded the answer is no projection and a reason —
    an extrapolation is not a fallback for a forecast.
    """
    from sqlalchemy import func as _func  # local — main.py imports sqla locally

    from models import ImfWeoObservation

    latest_vintage = (
        db.query(_func.max(ImfWeoObservation.vintage))
        .filter(
            ImfWeoObservation.country_code == "KEN",
            ImfWeoObservation.indicator == _PROJECTION_INDICATOR,
        )
        .scalar()
    )
    if latest_vintage is None:
        return [], None, "no_published_projection_seeded"

    rows = (
        db.query(ImfWeoObservation)
        .filter(
            ImfWeoObservation.country_code == "KEN",
            ImfWeoObservation.indicator == _PROJECTION_INDICATOR,
            ImfWeoObservation.vintage == latest_vintage,
            ImfWeoObservation.is_projection.is_(True),
            ImfWeoObservation.value.isnot(None),
        )
        .order_by(ImfWeoObservation.year.asc())
        .all()
    )
    if not rows:
        return [], None, "vintage_carries_no_projection_years"

    return (
        [
            {
                "year": r.year,
                "projected_debt_to_gdp": round(float(r.value), 1),
                "is_published_projection": True,
            }
            for r in rows
        ],
        _PROJECTION_SOURCE_LABEL,
        None,
    )


def _get_regional_peers(
    kenya_debt_to_gdp: Optional[float] = None,
    reference_year: Optional[int] = None,
) -> list:
    """Return EAC regional debt comparison with multiple indicators.

    Successful provider reads are cached for 12 hours. Each published cell
    carries its observation year and source, or an explicit absence reason.
    The debt column uses IMF general-government debt at one reference year;
    World Bank interest/revenue and external debt/GNI remain separate measures.
    """
    return _get_regional_peers_cached(kenya_debt_to_gdp, reference_year)


# ── EAC peer data with multi-indicator support ────────────────────
_EAC_COUNTRIES = {
    "KEN": "Kenya",
    "ETH": "Ethiopia",
    "TZA": "Tanzania",
    "UGA": "Uganda",
    "RWA": "Rwanda",
}

# World Bank indicator codes, keyed by WHAT THEY MEASURE.
#
# Two of these used to be keyed by the headline field they were poured into —
# ``debt_service_to_revenue`` and ``external_debt_pct`` — which is how the
# regional-peer table came to state Kenya's debt service as 24.3% on a page
# whose headline says 77.6%, and Kenya's external share as 35.0% beside a
# headline of 44.4% (audit 2026-09-06 §P2-11). Neither peer number was wrong;
# both were a different measure wearing the headline's name:
#
#   GC.XPN.INTP.RV.ZS   INTEREST payments only, no principal, % of revenue
#   DT.DOD.DECT.GN.ZS   external debt over GNI — not over total public debt
#
# Rwanda's 93.9 in that second column is the tell: no country holds 93.9% of
# its public debt externally, but 93.9% of GNI is unremarkable.
_WB_INDICATORS = {
    "interest_payments_pct_revenue": "GC.XPN.INTP.RV.ZS",
    "external_debt_pct_gni": "DT.DOD.DECT.GN.ZS",
}

#: What each regional-peer column is, published with the data so no reader has
#: to infer a measure from a field name.
_PEER_COLUMN_BASIS = {
    "debt_to_gdp": {
        "measure": "General government gross debt, % of GDP",
        "indicator": "GGXWDG_NGDP",
        "publisher": "IMF World Economic Outlook",
        # Filled per response — the whole column is pinned to one year so the
        # five countries are comparable. See _imf_fetch_debt_to_gdp.
        "reference_year": None,
    },
    "interest_payments_pct_revenue": {
        "measure": "Interest payments, % of revenue (excludes principal)",
        "indicator": "GC.XPN.INTP.RV.ZS",
        "publisher": "World Bank",
    },
    "external_debt_pct_gni": {
        "measure": "External debt stocks, % of GNI (denominator is GNI, not debt)",
        "indicator": "DT.DOD.DECT.GN.ZS",
        "publisher": "World Bank",
    },
}

def _peer_column_basis(reference_year: Optional[int]) -> Dict[str, Any]:
    """:data:`_PEER_COLUMN_BASIS` with this response's reference year stamped."""
    basis = {k: dict(v) for k, v in _PEER_COLUMN_BASIS.items()}
    basis["debt_to_gdp"]["reference_year"] = reference_year
    return basis


#: Why the two headline measures have no peer column. Kenya's 77.6% is total
#: debt service (principal + interest) over revenue, from ``fiscal_summaries``;
#: 44.4% is external debt over TOTAL PUBLIC DEBT. Neither has a cross-country
#: series behind it here, and the nearest-looking World Bank series is a
#: different measure — which is what produced the contradiction.
_PEER_ABSENT_REASONS = {
    "debt_service_to_revenue": "no_comparable_total_debt_service_series_for_peers",
    "external_debt_share": (
        "no_comparable_share_of_total_public_debt_series_for_peers"
    ),
}

# IMF DataMapper indicator codes (WEO dataset)
_IMF_INDICATORS = {
    "debt_to_gdp": "GGXWDG_NGDP",  # General govt gross debt (% GDP)
}

# TTL cache of provider observations (never request anchors). The reference year is
# part of the entry's identity — a cached column from last year's WEO vintage
# must not be served against this year's.
_peers_cache: Dict[str, Any] = {"ts": 0.0, "data": None, "reference_year": None}
_PEERS_CACHE_TTL = 12 * 3600  # 12 hours

_logger_peers = logging.getLogger("audit_app.regional_peers")


def _wb_fetch_indicator(indicator_code: str, country_codes: str) -> Dict[str, dict]:
    """Latest non-null World Bank observation per peer, retaining its year.

    Values are validated when assembling cells, so a malformed numeric value
    remains distinguishable from a country with no observation.
    """
    url = (
        f"https://api.worldbank.org/v2/country/{country_codes}"
        f"/indicator/{indicator_code}?format=json&per_page=100&date=2015:2026"
    )
    resp = httpx.get(url, timeout=8)
    resp.raise_for_status()
    wb_data = resp.json()
    if not isinstance(wb_data, list) or len(wb_data) != 2:
        raise ValueError("Invalid World Bank observation response")
    if wb_data[1] is None:
        return {}
    if not isinstance(wb_data[1], list):
        raise ValueError("Invalid World Bank observation rows")
    latest: Dict[str, dict] = {}
    for item in wb_data[1]:
        if not isinstance(item, dict):
            raise ValueError("Invalid World Bank observation row")
        indicator = item.get("indicator")
        if not isinstance(indicator, dict) or indicator.get("id") != indicator_code:
            raise ValueError("World Bank observation has the wrong indicator")
        iso = item.get("countryiso3code")
        if not isinstance(iso, str) or not iso or "value" not in item:
            raise ValueError("World Bank observation is missing a required field")
        if iso not in _EAC_COUNTRIES or item["value"] is None:
            continue
        date = item.get("date")
        if not isinstance(date, str) or not date.isdigit():
            raise ValueError("Invalid World Bank observation year")
        year = int(date)
        # Enforce the requested window even if the provider ignores it.
        if not 2015 <= year <= 2026:
            continue
        if iso not in latest or year > latest[iso]["year"]:
            latest[iso] = {"year": year, "value": item["value"]}
    return latest


def _imf_fetch_debt_to_gdp(reference_year: int) -> Dict[str, float]:
    """Debt-to-GDP for the EAC peers at ONE year, from the IMF DataMapper.

    Returns ``{ISO3: value}`` for countries that publish a value for exactly
    ``reference_year``. Countries that do not are omitted, so the caller can
    show absence rather than a value from some other year.

    The DataMapper honours neither filter in the URL. Asked for five countries
    over ``periods=2018,...,2026`` it answers with **226** country and
    aggregate codes (WEOWORLD, EURO, ADVEC ...) covering **1998-2031**. The
    previous ``max(year_vals.keys())`` therefore selected the furthest
    PROJECTION in the file for every country, under a column a reader takes
    for a current debt level::

        country   max(year)=2031    2025 actual
        KEN            75.1             69.3
        ETH            27.0             43.1
        RWA            61.6             64.6

    Ethiopia would have read 27.0 — a 2031 forecast, 16 points below its
    actual. Bound the year here, where it can be enforced, rather than in a
    query string the server discards.
    """
    countries = "/".join(_EAC_COUNTRIES.keys())
    url = (
        f"https://www.imf.org/external/datamapper/api/v1"
        f"/GGXWDG_NGDP/{countries}?periods={reference_year}"
    )
    resp = httpx.get(url, timeout=8)
    resp.raise_for_status()
    data = resp.json()

    # IMF response: {"values": {"GGXWDG_NGDP": {"KEN": {"2023": 68.1, ...}, ...}}}
    if not isinstance(data, dict) or not isinstance(data.get("values"), dict):
        raise ValueError("Invalid IMF observation response")
    indicator_data = data["values"].get("GGXWDG_NGDP")
    if not isinstance(indicator_data, dict):
        raise ValueError("Missing IMF debt indicator observations")
    result: Dict[str, float] = {}
    for iso, year_vals in indicator_data.items():
        # The response carries every country and every aggregate, asked for or
        # not. Keep only the peers this table compares.
        if iso not in _EAC_COUNTRIES:
            continue
        if not isinstance(year_vals, dict):
            raise ValueError("Invalid IMF country observations")
        val = year_vals.get(str(reference_year))
        if val is not None:
            result[iso] = val

    return result


def _get_regional_peers_cached(
    kenya_debt_to_gdp: Optional[float] = None,
    reference_year: Optional[int] = None,
) -> list:
    """Source-backed regional cells, with no substitution of another measure.

    Cache provider observations only. A request's accepted Kenya WEO anchor
    overlays a copy and cannot leak into a later request without that anchor.
    Failed or invalid provider reads are not cached; expired success is never
    served as a replacement for a failed fresh read.
    """
    import copy
    import math

    def number(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        try:
            return round(value, 1) if math.isfinite(value) and value >= 0 else None
        except OverflowError:
            return None

    if reference_year is not None and (
        type(reference_year) is not int or reference_year <= 0
    ):
        raise ValueError("A peer reference year must be a positive integer")

    def overlay(rows):
        rows = copy.deepcopy(rows)
        if kenya_debt_to_gdp is not None and reference_year is not None:
            kenya = rows[0]
            value = number(kenya_debt_to_gdp)
            kenya["debt_to_gdp"] = value
            kenya["debt_to_gdp_year"] = reference_year if value is not None else None
            kenya["debt_to_gdp_absent_reason"] = (
                None if value is not None else "invalid_observation"
            )
            kenya["debt_to_gdp_source"] = (
                source("KEN", "debt_to_gdp", "accepted_kenya_anchor")
                if value is not None
                else None
            )
        return rows

    def source(iso, column, origin):
        basis = _PEER_COLUMN_BASIS[column]
        url = (
            f"https://www.imf.org/external/datamapper/GGXWDG_NGDP@WEO/{iso}"
            if column == "debt_to_gdp"
            else f"https://api.worldbank.org/v2/country/{iso}/indicator/{basis['indicator']}?format=json"
        )
        return {
            "publisher": basis["publisher"],
            "indicator": basis["indicator"],
            "url": url,
            "origin": origin,
        }

    now = time.time()
    if (
        _peers_cache.get("contract") == "source_observations_v1"
        and _peers_cache["data"] is not None
        and _peers_cache.get("reference_year") == reference_year
        and 0 <= now - _peers_cache["ts"] < _PEERS_CACHE_TTL
    ):
        return overlay(_peers_cache["data"])

    observations = {}
    failures = {}
    if reference_year is None:
        observations["debt_to_gdp"] = {}
        failures["debt_to_gdp"] = "no_reference_year"
    else:
        try:
            observations["debt_to_gdp"] = {
                iso: {"value": value, "year": reference_year}
                for iso, value in _imf_fetch_debt_to_gdp(reference_year).items()
            }
        except ValueError as exc:
            observations["debt_to_gdp"] = {}
            failures["debt_to_gdp"] = "invalid_provider_response"
            _logger_peers.warning("Invalid IMF peer observations: %s", exc)
        except Exception as exc:
            observations["debt_to_gdp"] = {}
            failures["debt_to_gdp"] = "provider_unavailable"
            _logger_peers.warning("IMF peer observations unavailable: %s", exc)

    # WB central-government debt is not IMF general-government gross debt.
    # It cannot fill the IMF column, even when the numbers happen to agree.
    codes = ";".join(_EAC_COUNTRIES)
    for column, indicator in _WB_INDICATORS.items():
        try:
            observations[column] = _wb_fetch_indicator(indicator, codes)
        except ValueError as exc:
            observations[column] = {}
            failures[column] = "invalid_provider_response"
            _logger_peers.warning("Invalid World Bank peer %s: %s", indicator, exc)
        except Exception as exc:
            observations[column] = {}
            failures[column] = "provider_unavailable"
            _logger_peers.warning("World Bank peer %s unavailable: %s", indicator, exc)

    peers = []
    invalid = False
    for iso, name in _EAC_COUNTRIES.items():
        row = {
            "country": name,
            "debt_service_to_revenue": None,
            "debt_service_to_revenue_absent_reason": _PEER_ABSENT_REASONS[
                "debt_service_to_revenue"
            ],
            "external_debt_share": None,
            "external_debt_share_absent_reason": _PEER_ABSENT_REASONS[
                "external_debt_share"
            ],
        }
        for column in _PEER_COLUMN_BASIS:
            observation = observations[column].get(iso)
            value = number(observation["value"]) if observation is not None else None
            reason = (
                failures.get(column, "no_observation") if observation is None else None
            )
            if observation is not None and value is None:
                reason = "invalid_observation"
                invalid = True
            row[column] = value
            row[column + "_year"] = observation["year"] if value is not None else None
            row[column + "_absent_reason"] = reason
            row[column + "_source"] = (
                source(iso, column, "provider") if value is not None else None
            )
        peers.append(row)

    if (
        all(reason == "no_reference_year" for reason in failures.values())
        and not invalid
    ):
        _peers_cache.update(
            ts=now,
            data=copy.deepcopy(peers),
            reference_year=reference_year,
            contract="source_observations_v1",
        )
    else:
        # Clear an expired or other-vintage success so recovery must be read.
        _peers_cache.update(ts=0.0, data=None, reference_year=None)
    return overlay(peers)


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

        from services.entity_financials import (
            entity_financial_series,
            financial_summary,
        )

        series_by_entity = entity_financial_series(
            db, [entity.id for entity in entities]
        )
        county_period_ids = _latest_county_actuals_period_ids(db) or []
        enriched_entities: List[Dict[str, Any]] = []
        for entity in entities:
            series = series_by_entity.get(entity.id, [])
            if entity.type == EntityType.COUNTY:
                summary = next(
                    (
                        item
                        for item in series
                        if item["fiscal_period"]["id"] in county_period_ids
                    ),
                    financial_summary([]),
                )
            else:
                summary = series[0] if series else financial_summary([])

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

            fy_metrics = _resolve_fy_metrics(public_entity_metadata(entity.meta))
            code_value = (
                official_county_code(entity.canonical_name)
                if entity.type == EntityType.COUNTY
                else None
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
                    "meta": public_entity_metadata(entity.meta),
                    "financial_summary": summary,
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

        from services.entity_financials import entity_financial_series

        financial_time_series = entity_financial_series(db, [entity_id]).get(
            entity_id, []
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
        entity_meta = public_entity_metadata(entity.meta)

        recent_budget_lines_payload = []
        for bl in recent_budget_lines:
            recent_budget_lines_payload.append(
                {
                    "id": bl.id,
                    "category": bl.category,
                    "subcategory": bl.subcategory,
                    "allocated_amount": float(bl.allocated_amount)
                    if bl.allocated_amount is not None
                    else None,
                    "actual_spent": float(bl.actual_spent)
                    if bl.actual_spent is not None
                    else None,
                    "committed_amount": float(bl.committed_amount)
                    if bl.committed_amount is not None
                    else None,
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

        from services.financial_publication import monetary_fields

        items: List[Dict[str, Any]] = []
        for bl in budget_lines:
            items.append(
                {
                    "id": bl.id,
                    "category": bl.category,
                    "subcategory": bl.subcategory,
                    **monetary_fields(
                        bl, ("allocated_amount", "actual_spent", "committed_amount")
                    ),
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
            official_county_code(e.canonical_name)
            if e.type == EntityType.COUNTY
            else None
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

    from services.financial_publication import monetary_fields

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
                **monetary_fields(bl, ("allocated_amount", "actual_spent")),
                "currency": bl.currency,
                "entity_id": bl.entity_id,
                "period_id": bl.period_id,
                "source_document_id": bl.source_document_id,
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
    from services.publication_gate import fiscal_summary_withheld_disclosure

    # Bound before the try, because the fallback below reads it and the
    # fallback runs when there is no database at all — an unbound name there is
    # a 500, outside the `except` that would have caught it. The empty shape
    # comes from the same function that builds the populated one so the two
    # cannot drift.
    _fiscal_withheld = fiscal_summary_withheld_disclosure([])

    # Try DB data first — use FiscalSummary (national-scope, has real revenue/expenditure)
    if DATABASE_AVAILABLE:
        try:
            from models import FiscalSummary as FSModel

            with next(get_db()) as db:
                # Gate BEFORE the limit. Taking 12 rows and then withholding
                # some of them returns a short series and calls it twelve
                # years; gating first returns twelve publishable years.
                from services.publication_gate import (
                    publishable_fiscal_summaries,
                )

                stored = db.query(FSModel).order_by(FSModel.fiscal_year.desc()).all()
                _fiscal_withheld = fiscal_summary_withheld_disclosure(stored)
                rows = publishable_fiscal_summaries(stored)[:12]
                if rows:
                    from services.fiscal_outturns import fiscal_outturn

                    series = [fiscal_outturn(r) for r in rows]
                    series = series[:8]  # retain explicit gaps within recent years
                    if series:
                        return {
                            "withheld": _fiscal_withheld,
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
        # Two causes, two remedies. If fiscal rows are present and every one of
        # them was withheld for want of a page reference, re-running the ETL
        # adds nothing — the rows are already there. Saying "Run ETL pipeline"
        # there sends a reader at the wrong problem.
        note = "No fiscal outturn data available. Run ETL pipeline."
        if _fiscal_withheld["count"]:
            note = (
                f"{_fiscal_withheld['count']} fiscal year(s) are stored but "
                "cite no page of their source document, so none can be "
                "published. Backfill fiscal_summaries.page_ref."
            )
        series = [
            {
                "period": f"{get_current_fiscal_year()} Q1",
                "revenue": None,
                "expenditure": None,
                "balance": None,
                "note": note,
            },
        ]
    return {
        "series": series,
        "data_source": "fallback",
        "withheld": _fiscal_withheld,
    }


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


# POST /api/v1/etl/treasury/run-batch and /api/v1/etl/cob/run-batch were
# removed (#252): anyone could start a document download batch with no
# credentials, and nothing in the repo called them. The admin-gated trigger
# is POST /api/v1/admin/etl/trigger/{source}; see
# tests/test_write_routes_require_auth.py before adding a write route.


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


# POST /api/v1/etl/kenya/start was removed (#252) for the same reason, with
# GET /api/v1/etl/status/{job_id}: that only polled jobs kenya/start made,
# and answered "completed" with invented counts for any job_id.


@app.get("/api/v1/etl/kenya/sources")
async def get_kenya_data_sources():
    """Source catalogue; no live checker is installed in the serving image.

    This route used an unshipped developer script and fabricated success when
    it failed. Absence of a measurement stays unknown. The persisted pipeline
    observations are available separately through /data/freshness; reachability
    and the time a document was fetched are different measurements.
    """
    catalogue = (
        (
            "Kenya National Treasury",
            "https://treasury.go.ke",
            ["budget", "expenditure_report", "debt_report"],
        ),
        ("Office of Auditor General", "https://oagkenya.go.ke", ["audit_report"]),
        ("Controller of Budget", "https://cob.go.ke", ["budget_implementation_review"]),
    )
    return {
        "sources": [
            {
                "name": name,
                "url": url,
                "document_types": document_types,
                "status": "unknown",
                "last_fetch": None,
                "checked_at": None,
            }
            for name, url, document_types in catalogue
        ],
        "real_time_test": False,
        "error": "live_check_unavailable",
        "freshness_url": "/api/v1/data/freshness",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)

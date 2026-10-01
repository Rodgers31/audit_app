"""
Data Provenance Router — registry, stored lineage and qualified citations.

A supported publisher is not evidence that an observation was checked.
These endpoints do not fetch or validate source-document bytes.

GET /api/v1/provenance/sources       — list all data sources with URLs
GET /api/v1/provenance/verify/{table} — verify a specific data point
GET /api/v1/provenance/health        — overall data health check
"""

import logging
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import parse_qs, unquote, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from services.audit_citations import safe_source_url
from services.publication_gate import (
    loan_is_modelled_fixture,
    publishable_audit_criterion,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from database import get_db
    from models import (
        Audit,
        BudgetLine,
        Country,
        DebtCategory,
        DebtTimeline,
        EconomicIndicator,
        Entity,
        EntityType,
        Extraction,
        FiscalPeriod,
        FiscalSummary,
        GDPData,
        IngestionJob,
        IngestionStatus,
        Loan,
        PopulationData,
        PovertyIndex,
        RevenueBySource,
        SourceDocument,
    )

    DATABASE_AVAILABLE = True
except Exception:
    DATABASE_AVAILABLE = False

    def get_db():
        return None


router = APIRouter(prefix="/api/v1/provenance", tags=["Data Provenance"])
logger = logging.getLogger(__name__)


# ── Supported publisher registry (not active use or verification) ──
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
                "covers": "GDP, population, poverty rates, Gini coefficient",
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
    scope: Literal["supported_publisher_registry"] = "supported_publisher_registry"
    document_bytes_checked: Literal[False] = False


class RepresentedPublisher(BaseModel):
    source_id: str
    name: str
    row_count: int


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
    attribution_status: Literal[
        "empty", "single_publisher", "mixed_publishers", "partial", "unresolved"
    ] = "unresolved"
    attribution_basis: Literal[
        "coherent_observation_identity", "stored_document_links", "unavailable"
    ] = "unavailable"
    represented_publishers: List[RepresentedPublisher] = Field(default_factory=list)
    unresolved_source_rows: int = 0
    attribution_reasons: Dict[str, int] = Field(default_factory=dict)
    document_bytes_checked: Literal[False] = False


class ProvenanceHealthResponse(BaseModel):
    overall_status: str  # "healthy" | "degraded" | "critical"
    tables: List[TableHealth]
    total_source_documents: int
    last_ingestion: Optional[str] = None
    sources_cited: int  # distinct supported publishers represented in health cohorts
    supported_publisher_count: int
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


def _attach_source_document(verification, db, source_document_id) -> None:
    """Resolve a ``source_document_id`` onto the verification, or say nothing.

    Written once for the four branches added here rather than copied four
    times. The older branches still carry their own inline copy, and the drift
    that produces is already visible: ``population_data`` and ``budget_lines``
    set ``fetch_date``, ``gdp_data`` and ``loans`` do not, for no reason but
    the copies falling out of step. Folding them in is a separate change.
    """
    if not source_document_id:
        return
    doc = (
        db.query(SourceDocument)
        .filter(SourceDocument.id == source_document_id)
        .first()
    )
    if doc is None:
        return
    verification.source_document = doc.title
    verification.source_url = doc.url
    verification.publisher = doc.publisher
    verification.fetch_date = doc.fetch_date.isoformat() if doc.fetch_date else None


def _population_publisher_family(label):
    """Recognize population writer labels only for detecting contradictions."""
    if not isinstance(label, str):
        return None
    label = label.strip().casefold()
    if label.startswith("world bank"):
        return "worldbank"
    if label.startswith(("knbs", "kenya national bureau of statistics", "kenya census")):
        return "knbs"
    return None


def _attach_population_evidence(verification, db, record) -> None:
    """Cite only the selected observation's evidence; metadata is a hint.

    World Bank's JSON writer deliberately clears document/extraction fields.
    Its internally consistent publisher/dataset/URL identity can be shown in
    the chain, but must not become a source_document or upgrade the grade.
    """
    meta = record.meta
    identity = {
        "record_id": record.id,
        "year": record.year,
        "entity_id": record.entity_id,
    }
    if record.source_document_id:
        doc = db.query(SourceDocument).filter(
            SourceDocument.id == record.source_document_id
        ).first()
        if (
            doc is None or not safe_source_url(doc.url)
            or not doc.publisher.strip() or not doc.title.strip()
        ):
            verification.reason = "no resolvable source document"
            return
        if meta is not None and not isinstance(meta, dict):
            verification.reason = "malformed population source metadata"
            return
        meta = meta or {}
        source = meta.get("source")
        source_url = meta.get("source_url")
        census_year = meta.get("census_year")
        source_family = _population_publisher_family(source)
        document_family = _population_publisher_family(doc.publisher)
        publisher_conflict = source is not None and (
            not isinstance(source, str) or not source.strip()
            or (source_family != document_family if source_family and document_family
                else source.strip().casefold() != doc.publisher.strip().casefold())
        )
        supported_datasets = set()
        if document_family == "worldbank" and record.entity_id is None:
            supported_datasets.add("SP.POP.TOTL")
        if document_family == "knbs":
            supported_datasets.add(f"knbs_census_{record.year}")
        document_meta = doc.meta if isinstance(doc.meta, dict) else {}
        declared_datasets = [meta.get("dataset_id"),
                             document_meta.get("dataset_id"),
                             document_meta.get("indicator")]
        document_url = urlsplit(doc.url)
        document_path = unquote(document_url.path)
        if (document_family == "worldbank"
            and document_url.hostname in {"api.worldbank.org", "data.worldbank.org"}
            and "/indicator/" in document_path):
            declared_datasets.append(document_path.rsplit("/indicator/", 1)[1].rstrip("/"))
        dataset_conflict = any(
            value is not None and (
                not isinstance(value, str) or value not in supported_datasets
            ) for value in declared_datasets
        )
        if (
            (source_url is not None and source_url != doc.url)
            or publisher_conflict or dataset_conflict
            or (census_year is not None and
                (type(census_year) is not int or census_year != record.year))
        ):
            verification.reason = "conflicting population source identity"
            return
        if record.extraction_id is not None:
            extraction = db.query(Extraction).filter(
                Extraction.id == record.extraction_id
            ).first()
            if (
                extraction is None or extraction.source_document_id != doc.id
                or (record.source_page is not None
                    and extraction.page_number != record.source_page)
            ):
                verification.reason = "conflicting population extraction identity"
                return
        _attach_source_document(verification, db, doc.id)
        hint = {
            **identity, "source": doc.publisher, "dataset": doc.title,
            "url": doc.url, "source_document_id": doc.id,
        }
        # These are stored locators, not a claim this endpoint checked a page.
        for field in ("source_page", "page_ref", "source_hash", "extraction_id"):
            value = getattr(record, field)
            if value is not None:
                hint[field] = value
        verification.provenance_chain = [hint]
        return

    if not isinstance(meta, dict):
        verification.reason = (
            "missing or malformed population source identity; "
            "no resolvable source document"
        )
        return
    source = meta.get("source")
    url = meta.get("source_url")
    # Accept the identity emitted by the current publisher JSON writer, with
    # the year in the source label tied to this row. Do not infer a dataset
    # from a publisher name alone, or borrow a national indicator for a county.
    source_matches = source == f"World Bank Development Indicators ({record.year})"
    urls = {
        "https://data.worldbank.org/indicator/SP.POP.TOTL?locations=KE",
        f"https://api.worldbank.org/v2/country/KEN/indicator/SP.POP.TOTL?format=json&date={record.year}",
    }
    if (
        record.entity_id is None and source_matches
        and meta.get("dataset_id") == "SP.POP.TOTL"
        and isinstance(url, str) and url in urls
        and meta.get("census_year") is None
        and all(getattr(record, field) is None for field in
                ("source_page", "page_ref", "source_hash", "extraction_id"))
    ):
        verification.provenance_chain = [
            {**identity, "source": source, "dataset": meta["dataset_id"], "url": url}
        ]
    else:
        verification.reason = (
            "missing or conflicting population source identity; "
            "no resolvable source document"
        )


_GDP_INDICATOR = "NY.GDP.MKTP.CN"
_GDP_MEASURES = {
    "gdp, current kes",
    "gdp, current lcu",
    "nominal gdp",
    "gross domestic product, current prices",
}
_GCP_MEASURES = {
    "gross county product, current kes",
    "gross county product, current prices",
}


def _gdp_publisher_identity(label):
    """Resolve supported writer aliases; unfamiliar publishers compare exactly."""
    if not isinstance(label, str) or not label.strip():
        return None
    label = label.strip().casefold()
    if label in {"world bank", "world bank open data"} or re.fullmatch(
        r"world bank (?:development indicators \(\d{4}\)|ny\.gdp\.mktp\.cn(?: \(fixture\))?)",
        label,
    ):
        return "worldbank"
    if label in {
        "knbs",
        "kenya national bureau of statistics",
        "kenya national bureau of statistics (knbs)",
    }:
        return "knbs"
    return label


def _gdp_url_identity(url, year):
    """Read declared indicator/country/year identity, never fetch or verify it.

    A publisher homepage is not a GDP measure. World Bank URLs must identify
    Kenya's nominal local-currency series; other safe URLs carry no measure.
    """
    if not safe_source_url(url):
        return None, False, "invalid GDP source URL"
    parts = urlsplit(url)
    host = parts.hostname
    path = unquote(parts.path).rstrip("/")
    query = parse_qs(parts.query, keep_blank_values=True)
    if host in {"api.worldbank.org", "data.worldbank.org"}:
        expected = (
            f"/v2/country/KEN/indicator/{_GDP_INDICATOR}"
            if host == "api.worldbank.org"
            else f"/indicator/{_GDP_INDICATOR}"
        )
        allowed = (
            {"format", "date", "per_page", "page"}
            if host == "api.worldbank.org"
            else {"locations"}
        )
        if path != expected or set(query) - allowed or parts.fragment:
            return "worldbank", False, "conflicting GDP indicator URL identity"
        if (
            host == "data.worldbank.org"
            and query.get("locations") != ["KE"]
            or "format" in query
            and query["format"] != ["json"]
            or "date" in query
            and query["date"] != [str(year)]
        ):
            return "worldbank", False, "conflicting GDP country or year URL identity"
        return "worldbank", True, None
    if host == "knbs.or.ke" or host.endswith(".knbs.or.ke"):
        return "knbs", False, None
    return None, False, None


def _attach_gdp_evidence(verification, db, record) -> None:
    """Attach only coherent evidence for the selected GDP/GCP observation.

    Dataset/measure declarations are hints, not a performed reconciliation.
    Metadata-only JSON never manufactures a document or upgrades its grade.
    A linked document must also agree with explicit row/extraction identity.
    """
    try:
        amount = float(record.gdp_value)
    except (TypeError, ValueError, OverflowError):
        verification.reason = "invalid nominal GDP value"
        return
    if type(record.gdp_value) is bool or not math.isfinite(amount) or amount < 0:
        verification.reason = (
            "invalid nominal GDP value; expected a finite nonnegative amount"
        )
        return
    meta = record.meta
    if meta is not None and not isinstance(meta, dict):
        verification.reason = "malformed GDP source metadata"
        return
    meta = meta or {}
    doc = None
    if record.source_document_id is not None:
        doc = (
            db.query(SourceDocument)
            .filter(SourceDocument.id == record.source_document_id)
            .first()
        )
        if doc is None:
            verification.reason = "no resolvable GDP source document"
            return
        if (
            not isinstance(doc.title, str)
            or not doc.title.strip()
            or _gdp_publisher_identity(doc.publisher) is None
            or doc.meta is not None
            and not isinstance(doc.meta, dict)
        ):
            verification.reason = "missing or malformed GDP document identity"
            return
    entity = (
        db.query(Entity).filter(Entity.id == record.entity_id).first()
        if record.entity_id is not None
        else None
    )
    if record.entity_id is not None and entity is None:
        verification.reason = "missing GDP entity identity"
        return
    if entity is not None and entity.type not in {
        EntityType.NATIONAL,
        EntityType.COUNTY,
    }:
        verification.reason = "unsupported GDP entity type"
        return
    national = entity is None or entity.type == EntityType.NATIONAL
    country_id = (
        entity.country_id if entity is not None else (doc.country_id if doc else None)
    )
    country = (
        db.query(Country).filter(Country.id == country_id).first()
        if country_id is not None
        else None
    )
    if (
        country is not None
        and country.iso_code != "KEN"
        or doc is not None
        and (country is None or doc.country_id != country.id)
    ):
        verification.reason = "conflicting or missing GDP country identity"
        return
    if record.currency != "KES":
        verification.reason = "unsupported GDP currency; expected current KES evidence"
        return
    evidence = [meta]
    if doc is not None:
        evidence.append(doc.meta or {})
    url = doc.url if doc else meta.get("source_url")
    publisher = doc.publisher if doc else meta.get("source")
    family = _gdp_publisher_identity(publisher)
    url_family, wb_measure, url_error = _gdp_url_identity(url, record.year)
    if family is None or url_error or url_family is not None and url_family != family:
        verification.reason = (
            url_error or "missing or conflicting GDP publisher identity"
        )
        return
    if record.extraction_id is not None:
        extraction = (
            db.query(Extraction).filter(Extraction.id == record.extraction_id).first()
        )
        if (
            doc is None
            or extraction is None
            or extraction.source_document_id != doc.id
            or record.source_page is not None
            and extraction.page_number != record.source_page
            or not isinstance(extraction.extracted_json, dict)
        ):
            verification.reason = "conflicting or malformed GDP extraction identity"
            return
        evidence.append(extraction.extracted_json)
    # The World Bank indicator is annual national JSON, including when a
    # writer represents its API endpoint as a SourceDocument REPORT row.
    if family == "worldbank" and (
        not wb_measure
        or not national
        or record.quarter is not None
        or any(
            getattr(record, field) is not None
            for field in ("source_page", "page_ref", "source_hash", "extraction_id")
        )
    ):
        verification.reason = "conflicting GDP scope or JSON locator identity"
        return
    if record.quarter not in {None, "Q1", "Q2", "Q3", "Q4"} or (
        record.quarter is not None
        and not any(item.get("quarter") == record.quarter for item in evidence)
    ):
        verification.reason = "missing or conflicting GDP quarter identity"
        return
    label_year = re.fullmatch(
        r"World Bank Development Indicators \((\d{4})\)", publisher.strip(), re.I
    )
    if label_year and int(label_year[1]) != record.year:
        verification.reason = "conflicting GDP publisher-label year"
        return
    measures = _GDP_MEASURES if national else _GCP_MEASURES
    measure_known = wb_measure
    datasets = []
    for item in evidence:
        # Enumerate plural declaration shapes instead of silently ignoring
        # conflicts in JSONB lists or malformed containers.
        declarations = []
        for plural, singular in (
            ("indicators", "indicator"),
            ("datasets", "dataset_id"),
            ("measures", "measure"),
        ):
            if plural in item:
                values = item[plural]
                if (
                    not isinstance(values, list)
                    or not values
                    or any(not isinstance(v, str) for v in values)
                ):
                    verification.reason = "malformed GDP evidence declarations"
                    return
                declarations.extend({singular: v} for v in values)
        for key in ("gdp_value", "value"):
            if key in item and (
                type(item[key]) not in {int, float}
                or not math.isfinite(item[key])
                or item[key] != amount
            ):
                verification.reason = "conflicting GDP amount identity"
                return
        for key, expected in (
            ("year", record.year),
            ("entity_id", record.entity_id),
            ("quarter", record.quarter),
            ("currency", record.currency),
            ("country_code", "KEN"),
            ("scope", "national" if national else "county"),
        ):
            if key in item and (
                type(item[key]) is not type(expected) or item[key] != expected
            ):
                verification.reason = "conflicting GDP observation identity"
                return
        if "units" in item and (
            not isinstance(item["units"], str) or item["units"].casefold() != "kes"
        ):
            verification.reason = "conflicting GDP units identity"
            return
        if "source" in item and _gdp_publisher_identity(item["source"]) != family:
            verification.reason = "conflicting GDP publisher identity"
            return
        if "source_url" in item and item["source_url"] != url:
            verification.reason = "conflicting GDP source URL identity"
            return
        for declaration in [item, *declarations]:
            if "measure" in declaration:
                measure = declaration["measure"]
                if (
                    not isinstance(measure, str)
                    or measure.strip().casefold() not in measures
                ):
                    verification.reason = "conflicting GDP measure identity"
                    return
                measure_known = True
            for key in ("dataset_id", "dataset", "indicator"):
                if key not in declaration:
                    continue
                value = declaration[key]
                if not isinstance(value, str) or not value.strip():
                    verification.reason = "malformed GDP dataset identity"
                    return
                # A multi-measure survey still needs an explicit nominal
                # measure. Conflicting indicator codes cannot be rescued by
                # a nominal-GDP label elsewhere in the evidence.
                if (
                    family == "worldbank"
                    and value != _GDP_INDICATOR
                    or family == "knbs"
                    and value
                    not in {"knbs_economic_survey", "knbs_gross_county_product"}
                    or re.fullmatch(r"[A-Za-z]{2}\.[A-Za-z0-9.]+", value)
                    and value != _GDP_INDICATOR
                ):
                    verification.reason = "conflicting GDP dataset identity"
                    return
                datasets.append(value)
        source = item.get("source")
        if isinstance(source, str):
            match = re.fullmatch(
                r"World Bank Development Indicators \((\d{4})\)", source.strip(), re.I
            )
            if match and int(match[1]) != record.year:
                verification.reason = "conflicting GDP source-label year"
                return
    if doc is not None:
        codes = re.findall(r"[A-Z]{2}\.[A-Z0-9.]+", doc.title, re.I)
        # Normalize ordinary title typography before reading explicit wrong
        # measures. Survey publication years are not observation-year claims.
        title = re.sub(r"[\s\u2010-\u2015-]+", " ", doc.title)
        wrong_measure = re.search(
            r"\bpopulation\b|\bper capita\b|US\$|"
            r"\b(?:usd|dollars|eur|ugx|tzs|gbp)\b|"
            r"\b(?:gdp|gross domestic product)\b.{0,40}\b(?:growth|constant)\b|"
            r"\b(?:real|growth|constant)\b.{0,40}\b(?:gdp|gross domestic product)\b",
            title,
            re.I,
        )
        if wrong_measure or any(
            code.upper().rstrip(".") != _GDP_INDICATOR for code in codes
        ):
            verification.reason = "conflicting GDP document indicator identity"
            return
    if not measure_known or len(set(datasets)) > 1:
        verification.reason = "missing or conflicting GDP measure/dataset identity"
        return
    if doc is None and (
        family != "worldbank" or meta.get("dataset_id") != _GDP_INDICATOR
    ):
        verification.reason = "missing GDP document or supported JSON identity"
        return
    hint = {
        "record_id": record.id,
        "year": record.year,
        "quarter": record.quarter,
        "entity_id": record.entity_id,
        "country_code": "KEN",
        "currency": record.currency,
        "measure": "GDP, current KES"
        if national
        else "Gross County Product, current KES",
        "source": publisher,
        "dataset": doc.title if doc else meta["dataset_id"],
        "url": url,
    }
    if doc is not None:
        _attach_source_document(verification, db, doc.id)
        hint["source_document_id"] = doc.id
        for field in ("source_page", "page_ref", "source_hash", "extraction_id"):
            value = getattr(record, field)
            if value is not None:
                hint[field] = value
    verification.provenance_chain = [hint]


def _note_document_integrity(verification, db, source_document_id) -> None:
    """Append what CAN be said about the stored document, without fetching it.

    This does not upgrade the status and does not soften the sentence
    ``_grade_verification`` writes — it only adds a fact that sentence leaves
    open. "The document has not been fetched" is true either way; whether an
    md5 is on file decides whether a reissued document *could* ever be
    detected, and that is the difference between a chain that can be closed
    later and one that cannot.

    Measured on production 2026-09-06: 2,158 of 2,327 source documents carry an
    md5, but the four documents behind fiscal summaries, revenue by source and
    pending bills carry none — they were written by ETL code that never held
    the bytes. Saying so is cheap and true. Re-fetching the URL from inside a
    public request handler to prove it still resolves is neither, so this
    stops short of claiming it.
    """
    if not source_document_id or not verification.reason:
        return
    doc = (
        db.query(SourceDocument)
        .filter(SourceDocument.id == source_document_id)
        .first()
    )
    if doc is None:
        return
    if getattr(doc, "md5", None):
        verification.reason += (
            "; an md5 is on file for the document, so a reissue would be "
            "detectable once the file is re-fetched"
        )
    else:
        verification.reason += (
            "; no md5 is on file for the document, so a reissued or edited "
            "file could not be detected"
        )


def _fiscal_year_matches(column, year: int):
    """SQL condition: this ``FY 2024/25``-style label starts in ``year``.

    The trailing slash is load-bearing. ``LIKE '%2024%'`` would also be
    correct here, but only by accident — it happens not to collide with
    "FY 2023/24" because those digits are not adjacent. ``'%2024/%'`` says what
    is actually meant (the year the label OPENS in) and matches both stored
    shapes, "FY 2024/25" and "2024/25".
    """
    return column.like(f"%{year}/%")


@router.get(
    "/sources",
    response_model=List[DataSourceInfo],
    summary="List Supported Publisher Registry",
)
async def list_data_sources():
    """
    Return supported publisher coverage, independent of database contents.

    Registry membership does not establish active lineage, cross-validation or
    document-byte verification. Health reports the stored cohorts separately.
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
    "population_data": 3650,    # existing table-wide budget; not publisher attribution
    "budget_lines": 180,        # CoB quarterly + lag
    "audits": 550,              # OAG annual + lag
    "gdp_data": 550,            # existing annual table-wide budget
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


# Bounded aliases for registry attribution; unknown/composite labels do not
# become a supported publisher by substring or by choosing the first agency.
_PUBLISHER_ALIASES = {
    "world bank": "worldbank",
    "world bank open data": "worldbank",
    "knbs": "knbs",
    "kenya national bureau of statistics": "knbs",
    "kenya national bureau of statistics (knbs)": "knbs",
    "cbk": "cbk",
    "central bank of kenya": "cbk",
    "central bank of kenya (cbk)": "cbk",
    "oag": "oag",
    "office of the auditor general": "oag",
    "office of the auditor general (oag)": "oag",
    "cob": "cob",
    "controller of budget": "cob",
    "controller of budget (cob)": "cob",
    "office of the controller of budget": "cob",
    "office of the controller of budget (ocob)": "cob",
    "national treasury": "treasury",
    "national treasury & planning": "treasury",
    "national treasury kenya": "treasury",
    "national treasury of kenya": "treasury",
}
_PUBLISHER_HOSTS = {
    "worldbank": {"api.worldbank.org", "data.worldbank.org"},
    "knbs": {"knbs.or.ke"},
    "cbk": {"centralbank.go.ke"},
    "oag": {"oagkenya.go.ke"},
    "cob": {"cob.go.ke"},
    "treasury": {"treasury.go.ke"},
}


def _health_publisher_label(label):
    if not isinstance(label, str):
        return None
    return " ".join(re.sub(r"[\u2010-\u2015-]", " ", label.strip().casefold()).split())


def _health_publisher_id(label):
    normalized = _health_publisher_label(label)
    if normalized is None:
        return None
    if re.fullmatch(r"world bank development indicators \(\d{4}\)", normalized):
        return "worldbank"
    if re.fullmatch(r"(?:knbs|kenya) census \d{4}", normalized):
        return "knbs"
    return _PUBLISHER_ALIASES.get(normalized)


def _health_document_reason(doc):
    """Check stored identity only; no URL request, page or digest validation."""
    if doc is None:
        return "no resolvable source document"
    if (
        not isinstance(doc.title, str)
        or not doc.title.strip()
        or doc.meta is not None
        and not isinstance(doc.meta, dict)
    ):
        return "missing or malformed document identity"
    publisher_id = _health_publisher_id(doc.publisher)
    if publisher_id is None:
        return "unsupported or ambiguous document publisher"
    if not safe_source_url(doc.url):
        return "no safe source document URL"
    host = urlsplit(doc.url).hostname
    if not any(
        host == domain or host.endswith("." + domain)
        for domain in _PUBLISHER_HOSTS[publisher_id]
    ):
        return "conflicting document publisher and URL"
    meta = doc.meta or {}
    if (
        "source" in meta
        and _health_publisher_id(meta["source"]) != publisher_id
        or "source_url" in meta
        and meta["source_url"] != doc.url
    ):
        return "conflicting document publisher identity"
    return None


def _health_population_label_year_conflicts(label, year):
    normalized = _health_publisher_label(label)
    if normalized is None:
        return False  # Unsupported labels are refused by the publisher check.
    match = re.fullmatch(
        r"(?:world bank development indicators \((\d{4})\)|(?:knbs|kenya) census (\d{4}))",
        normalized,
    )
    return bool(match and int(next(v for v in match.groups() if v)) != year)


def _health_population_reason(db, row, doc):
    """Refuse malformed/contradictory declarations in the health inventory.

    This supplements the accepted selected-row helper without changing its
    verification contract. None of these stored checks validates source bytes.
    """
    if type(row.total_population) is not int or row.total_population < 0:
        return "invalid population amount"
    evidence = [row.meta]
    publisher_id = _health_publisher_id(
        doc.publisher
        if doc
        else (row.meta.get("source") if isinstance(row.meta, dict) else None)
    )
    url = (
        doc.url
        if doc
        else (row.meta.get("source_url") if isinstance(row.meta, dict) else None)
    )
    if doc is not None:
        country = db.query(Country).filter(Country.id == doc.country_id).first()
        if country is None or country.iso_code != "KEN":
            return "conflicting population country identity"
        evidence.append(doc.meta)
        if _health_population_label_year_conflicts(doc.publisher, row.year):
            return "conflicting population document publisher-label year"
        if re.search(r"\bGDP\b|gross domestic product", doc.title, re.I):
            return "conflicting population document measure"
    if row.entity_id is not None:
        entity = db.query(Entity).filter(Entity.id == row.entity_id).first()
        country = (
            db.query(Country).filter(Country.id == entity.country_id).first()
            if entity
            else None
        )
        if (
            entity is None
            or country is None
            or country.iso_code != "KEN"
            or entity.type not in {EntityType.COUNTY, EntityType.NATIONAL}
            or doc is not None
            and entity.country_id != doc.country_id
        ):
            return "conflicting population entity identity"
    if row.extraction_id is not None:
        extraction = (
            db.query(Extraction).filter(Extraction.id == row.extraction_id).first()
        )
        if (
            doc is None
            or extraction is None
            or extraction.source_document_id != doc.id
            or row.source_page is not None
            and extraction.page_number != row.source_page
            or not isinstance(extraction.extracted_json, dict)
        ):
            return "conflicting or malformed population extraction identity"
        evidence.append(extraction.extracted_json)
    supported_dataset = (
        "SP.POP.TOTL" if publisher_id == "worldbank" else f"knbs_census_{row.year}"
    )
    for item in evidence:
        if item is None:
            continue
        if not isinstance(item, dict):
            return "malformed population source metadata"
        source = item.get("source")
        if "source" in item:
            if _health_publisher_id(source) != publisher_id or publisher_id is None:
                return "conflicting or ambiguous population publisher identity"
            if _health_population_label_year_conflicts(source, row.year):
                return "conflicting population source-label year"
        if "source_url" in item and item["source_url"] != url:
            return "conflicting population source URL identity"
        for key, expected in (
            ("year", row.year),
            ("census_year", row.year),
            ("entity_id", row.entity_id),
            ("country_code", "KEN"),
        ):
            if key in item and (
                type(item[key]) is not type(expected) or item[key] != expected
            ):
                return "conflicting population observation identity"
        for key in ("total_population", "value"):
            if key in item and (
                type(item[key]) is not int or item[key] != row.total_population
            ):
                return "conflicting population amount identity"
        declarations = [item]
        for plural, singular in (
            ("datasets", "dataset_id"),
            ("indicators", "indicator"),
            ("measures", "measure"),
        ):
            if plural in item:
                values = item[plural]
                if (
                    not isinstance(values, list)
                    or not values
                    or any(not isinstance(v, str) for v in values)
                ):
                    return "malformed population evidence declarations"
                declarations.extend({singular: value} for value in values)
        for declaration in declarations:
            for key in ("dataset_id", "dataset", "indicator"):
                if key in declaration and declaration[key] != supported_dataset:
                    return "conflicting population dataset identity"
            if "measure" in declaration and (
                not isinstance(declaration["measure"], str)
                or declaration["measure"].strip().casefold()
                not in {
                    "population",
                    "total population",
                    "population, total",
                    "population census",
                }
            ):
                return "conflicting population measure identity"
    return None


def _attribute_health_cohort(table, db, model, cohort):
    """Describe counted stored lineage without changing completeness/freshness.

    GDP/population reuse their accepted observation identity helpers. Other
    tables only inventory linked documents: no claim of measure/observation
    validation. Explicit reasons account for every unattributed counted row.
    """
    counts = {}
    reasons = {}

    def add(publisher_id, reason, count=1):
        target, key = (reasons, reason) if reason else (counts, publisher_id)
        target[key] = target.get(key, 0) + count

    if model in {GDPData, PopulationData}:
        table.attribution_basis = "coherent_observation_identity"
        for row in cohort:
            reason = None
            doc = None
            if row.source_document_id is not None:
                doc = (
                    db.query(SourceDocument)
                    .filter(SourceDocument.id == row.source_document_id)
                    .first()
                )
                reason = _health_document_reason(doc)
            if reason is None and model is PopulationData:
                reason = _health_population_reason(db, row, doc)
            evidence = DataPointVerification(
                table=table.table, verification_status="unverified"
            )
            if reason is None:
                attach = (
                    _attach_gdp_evidence
                    if model is GDPData
                    else _attach_population_evidence
                )
                attach(evidence, db, row)
                reason = evidence.reason
            publisher_id = None
            if reason is None and evidence.provenance_chain:
                hint = evidence.provenance_chain[0]
                if doc is not None and hint.get("source_document_id") != doc.id:
                    reason = "conflicting observation source-document reference"
                publisher_id = _health_publisher_id(hint.get("source"))
                if publisher_id is None:
                    reason = "unsupported or ambiguous observation publisher"
            elif reason is None:
                reason = "missing observation source identity"
            add(publisher_id, reason)
    elif hasattr(model, "source_document_id"):
        table.attribution_basis = "stored_document_links"
        # One grouped SQL query and one document lookup, independent of row count.
        links = (
            cohort.with_entities(model.source_document_id, func.count(model.id))
            .group_by(model.source_document_id)
            .all()
        )
        documents = {
            doc.id: doc
            for doc in db.query(SourceDocument).filter(
                SourceDocument.id.in_([sid for sid, _ in links if sid is not None])
            )
        }
        for source_id, count in links:
            doc = documents.get(source_id)
            reason = _health_document_reason(doc)
            add(_health_publisher_id(doc.publisher) if doc else None, reason, count)
    else:
        table.attribution_basis = "unavailable"
        if table.row_count:
            add(None, "no row-level source-document attribution", table.row_count)

    table.represented_publishers = [
        RepresentedPublisher(
            source_id=key, name=OFFICIAL_SOURCES[key]["name"], row_count=count
        )
        for key, count in sorted(counts.items())
    ]
    table.attribution_reasons = reasons
    table.unresolved_source_rows = sum(reasons.values())
    table.source = None
    if table.row_count == 0:
        table.attribution_status = "empty"
    elif not counts:
        table.attribution_status = "unresolved"
    elif reasons:
        table.attribution_status = "partial"
    elif len(counts) > 1:
        table.attribution_status = "mixed_publishers"
    else:
        table.attribution_status = "single_publisher"
        table.source = table.represented_publishers[0].name


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
        status="healthy" if county_count >= 47 else "critical" if county_count == 0 else "degraded",
    ), db, Entity))

    # Budget lines
    budget_count = db.query(BudgetLine).count()
    tables.append(_apply_freshness(TableHealth(
        table="budget_lines",
        label="Budget Lines",
        row_count=budget_count,
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
        status="healthy" if econ_count >= 5 else "degraded" if econ_count > 0 else "empty",
    ), db, EconomicIndicator))

    # Poverty
    poverty_count = db.query(PovertyIndex).count()
    tables.append(_apply_freshness(TableHealth(
        table="poverty_indices",
        label="Poverty Data",
        row_count=poverty_count,
        status="healthy" if poverty_count >= 1 else "empty",
    ), db, PovertyIndex))

    # Loans / Debt
    loan_count = db.query(Loan).count()
    tables.append(_apply_freshness(TableHealth(
        table="loans",
        label="Debt Records",
        row_count=loan_count,
        status="healthy" if loan_count >= 50 else "degraded" if loan_count > 0 else "empty",
    ), db, Loan))

    # Debt timeline
    debt_tl_count = db.query(DebtTimeline).count()
    tables.append(_apply_freshness(TableHealth(
        table="debt_timeline",
        label="Debt Timeline",
        row_count=debt_tl_count,
        status="healthy" if debt_tl_count >= 5 else "degraded" if debt_tl_count > 0 else "empty",
    ), db, DebtTimeline))

    # Fiscal summaries
    fiscal_count = db.query(FiscalSummary).count()
    tables.append(_apply_freshness(TableHealth(
        table="fiscal_summaries",
        label="Fiscal Summaries",
        row_count=fiscal_count,
        status="healthy" if fiscal_count >= 3 else "degraded" if fiscal_count > 0 else "empty",
    ), db, FiscalSummary))

    # Attribute the exact counted cohorts. Audit counts exclude withheld rows;
    # county counts exclude noncounty entities. Counts/freshness never grade bytes.
    cohorts = {
        "entities": (Entity, db.query(Entity).filter(Entity.type == EntityType.COUNTY)),
        "budget_lines": (BudgetLine, db.query(BudgetLine)),
        "audits": (Audit, publishable_audits),
        "population_data": (PopulationData, db.query(PopulationData)),
        "gdp_data": (GDPData, db.query(GDPData)),
        "economic_indicators": (EconomicIndicator, db.query(EconomicIndicator)),
        "poverty_indices": (PovertyIndex, db.query(PovertyIndex)),
        "loans": (Loan, db.query(Loan)),
        "debt_timeline": (DebtTimeline, db.query(DebtTimeline)),
        "fiscal_summaries": (FiscalSummary, db.query(FiscalSummary)),
    }
    for table in tables:
        model, cohort = cohorts[table.table]
        _attribute_health_cohort(table, db, model, cohort)

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
        sources_cited=len({
            publisher.source_id
            for table in tables for publisher in table.represented_publishers
        }),
        supported_publisher_count=len(OFFICIAL_SOURCES),
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
            if year is not None:
                query = query.filter(PopulationData.year == year)
            record = query.order_by(
                desc(PopulationData.year), desc(PopulationData.id)
            ).first()
            if record is None:
                verification.reason = "no_rows_for_year" if year is not None else "no_rows"
            if record:
                verification.value = f"{record.total_population:,} (year {record.year})"
                _attach_population_evidence(verification, db, record)
                _grade_verification(verification)
                if verification.source_document:
                    _note_document_integrity(verification, db, record.source_document_id)

        elif table_name == "gdp_data":
            query = db.query(GDPData)
            if entity_id is not None:
                query = query.filter(GDPData.entity_id == entity_id)
            else:
                query = query.filter(GDPData.entity_id.is_(None))
            if year is not None:
                query = query.filter(GDPData.year == year)
            record = query.order_by(desc(GDPData.year)).first()
            if record is None:
                verification.reason = "no_rows_for_year" if year is not None else "no_rows"
            else:
                gdp_t = float(record.gdp_value) / 1e12
                verification.value = (
                    f"{record.currency} {gdp_t:.2f}T (year {record.year})"
                    if math.isfinite(gdp_t) else None
                )
                _attach_gdp_evidence(verification, db, record)
                _grade_verification(verification)
                if verification.source_document:
                    _note_document_integrity(verification, db, record.source_document_id)

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
                _note_document_integrity(verification, db, record.source_document_id)

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
                _note_document_integrity(verification, db, record.source_document_id)

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
                _note_document_integrity(verification, db, record.source_document_id)
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
                _note_document_integrity(
                    verification, db, getattr(record, "source_document_id", None)
                )
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

        elif table_name == "fiscal_summaries":
            # Every national headline on /budget — appropriated budget, total
            # revenue, debt service — reads this table, and asking where those
            # figures came from answered "Unknown table". The chain exists:
            # FiscalSummary.source_document_id is populated on all 29 rows.
            _fs_query = db.query(FiscalSummary)
            if year:
                _fs_query = _fs_query.filter(
                    _fiscal_year_matches(FiscalSummary.fiscal_year, year)
                )
            record = _fs_query.order_by(desc(FiscalSummary.fiscal_year)).first()
            if record is None:
                verification.reason = "no_rows_for_year" if year else "no_rows"
            else:
                # The money columns are nullable and correctly NULL for years
                # nobody measured — FY 2021/22 and earlier carry no
                # total_revenue. Reporting that as "KES 0 appropriated" would
                # manufacture the zero this endpoint exists to expose, so
                # absence is reported as absence.
                if record.appropriated_budget is None:
                    verification.value = None
                    verification.reason = (
                        "no appropriated budget recorded for "
                        f"{record.fiscal_year}"
                    )
                else:
                    verification.value = (
                        f"KES {float(record.appropriated_budget):,.0f} "
                        f"appropriated budget ({record.fiscal_year})"
                    )
                _attach_source_document(verification, db, record.source_document_id)
                _grade_verification(verification)
                _note_document_integrity(verification, db, record.source_document_id)

        elif table_name == "revenue_by_source":
            # One row is one tax head for one year, so identify WHICH — a
            # verification that cannot name its own data point is not one.
            _rev_query = db.query(RevenueBySource)
            if year:
                _rev_query = _rev_query.filter(
                    _fiscal_year_matches(RevenueBySource.fiscal_year, year)
                )
            record = (
                _rev_query.order_by(
                    desc(RevenueBySource.fiscal_year),
                    # Rows with a figure first. Postgres sorts NULLs FIRST on a
                    # DESC ordering, so without this the endpoint verified
                    # "Other Tax Revenue · FY 2025/26" — a projection row with
                    # no actual collected — and answered "no collection
                    # recorded" while six rows carrying real KRA figures sat
                    # behind it. Expressed as a boolean sort rather than NULLS
                    # LAST so it means the same thing on SQLite.
                    RevenueBySource.amount_billion_kes.is_(None),
                    desc(RevenueBySource.amount_billion_kes),
                    # Deterministic tiebreak. Six FY 2025/26 rows are all
                    # projections with a NULL actual; without this the endpoint
                    # can name a different one on each call, and a verification
                    # that moves is not one.
                    RevenueBySource.revenue_type,
                )
                .first()
            )
            if record is None:
                verification.reason = "no_rows_for_year" if year else "no_rows"
            else:
                _rev_id = f"{record.revenue_type} · {record.fiscal_year}"
                # amount_billion_kes is nullable BY DESIGN — the column holds
                # NULL for projection rows that have a target but no actual.
                # A zero would say the tax head collected nothing.
                if record.amount_billion_kes is None:
                    verification.value = None
                    verification.reason = f"no collection recorded for {_rev_id}"
                else:
                    verification.value = (
                        f"KES {float(record.amount_billion_kes):,.2f} billion "
                        f"collected ({_rev_id})"
                    )
                _attach_source_document(verification, db, record.source_document_id)
                _grade_verification(verification)
                _note_document_integrity(verification, db, record.source_document_id)

        elif table_name == "pending_bills":
            # Pending bills are not their own table: they are Loan rows in the
            # pending_bills category. Asking about "pending_bills" is what a
            # reader would do, so the name is answered rather than corrected.
            _pb_query = db.query(Loan).filter(
                Loan.debt_category == DebtCategory.PENDING_BILLS
            )
            if entity_id:
                _pb_query = _pb_query.filter(Loan.entity_id == entity_id)
            record = _pb_query.order_by(desc(Loan.outstanding)).first()
            if record is None:
                verification.reason = (
                    "no_pending_bill_rows_for_entity" if entity_id else "no_rows"
                )
            else:
                verification.value = (
                    f"KES {float(record.outstanding):,.0f} outstanding "
                    f"({record.lender})"
                )
                _attach_source_document(verification, db, record.source_document_id)
                if record.provenance:
                    verification.provenance_chain = (
                        record.provenance
                        if isinstance(record.provenance, list)
                        else [record.provenance]
                    )
                _grade_verification(verification)
                _note_document_integrity(verification, db, record.source_document_id)
                # The bootstrap fixture computes county pending bills as 8% of
                # a budget that is itself population x KSh 4,500. Those rows
                # resolve to a document too, and grading them on that alone
                # would call a modelled figure sourced.
                if loan_is_modelled_fixture(record):
                    verification.verification_status = "modelled"
                    _modelled = (
                        "this row is the bootstrap fixture's modelled figure "
                        "(8% of a population-derived budget), not a pending-bill "
                        "total read from a Treasury or Controller of Budget table"
                    )
                    verification.reason = (
                        f"{verification.reason}; {_modelled}"
                        if verification.reason
                        else _modelled
                    )

        elif table_name == "counties":
            # Answered, and the answer is that the chain does not exist.
            #
            # Counties are Entity rows of type COUNTY. `entities` has no
            # source_document_id and no provenance column (models.py:107-123),
            # so there is nothing to resolve — a county's name, slug and
            # metadata block cannot be traced to a document by this endpoint at
            # all. Leaving the table out of the supported list said the same
            # thing by omission, which a reader can only discover by guessing
            # the name and getting a 400.
            #
            # The figures ABOUT a county do have chains, and they are named so
            # a reader is not left at a dead end.
            _c_query = db.query(Entity).filter(Entity.type == EntityType.COUNTY)
            if entity_id:
                _c_query = _c_query.filter(Entity.id == entity_id)
            record = _c_query.order_by(Entity.canonical_name).first()
            verification.verification_status = "unverified"
            _no_chain = (
                "the counties table carries no source document: `entities` has "
                "no source_document_id and no provenance column, so a county "
                "row cannot be traced to a document by this endpoint. Figures "
                "about a county are traceable individually — try "
                "budget_lines, population_data or pending_bills with the same "
                "entity_id."
            )
            if record is None:
                # "there is no such county" and "counties have no provenance
                # chain" are different answers and both matter. An earlier
                # draft of this branch set the first and then overwrote it with
                # the second, which lost the only fact specific to the request.
                _missing = (
                    "no_county_for_entity_id" if entity_id else "no_rows"
                )
                verification.reason = f"{_missing}; {_no_chain}"
            else:
                verification.value = f"{record.canonical_name} (entity {record.id})"
                verification.reason = _no_chain

        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown table: {table_name}. Supported: population_data, "
                    "gdp_data, audits, loans, budget_lines, debt_timeline, "
                    "fiscal_summaries, revenue_by_source, pending_bills, counties"
                ),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Verification error for %s: %s", table_name, e)
        verification.verification_status = "error"

    return verification

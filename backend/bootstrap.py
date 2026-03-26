"""Database bootstrap utilities for seeding canonical county data."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from database import SessionLocal
from models import (
    Audit,
    BudgetLine,
    Country,
    DebtCategory,
    DocumentType,
    EconomicIndicator,
    Entity,
    EntityType,
    FiscalPeriod,
    GDPData,
    Loan,
    PopulationData,
    PovertyIndex,
    Severity,
    SourceDocument,
)
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

FISCAL_LABEL = "FY2025/26"
FISCAL_START = datetime(2025, 7, 1)
FISCAL_END = datetime(2026, 6, 30)
DATA_DIR = Path(__file__).resolve().parent.parent / "apis"
COUNTY_DATA_PATH = DATA_DIR / "enhanced_county_data.json"
AUDIT_DATA_PATH = DATA_DIR / "oag_audit_data.json"
NATIONAL_AUDIT_PATH = DATA_DIR / "oag_national_audit_data.json"


def _parse_decimal(value: Any) -> Decimal:
    """Convert value to Decimal safely."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _parse_kes_amount(value: Any) -> float:
    """Parse KES amount strings like 'KES 2.5B' into numeric values."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    try:
        cleaned = str(value).upper().replace("KES", "").strip()
        cleaned = cleaned.replace(",", "")
        multiplier = 1.0
        if cleaned.endswith("B"):
            multiplier = 1_000_000_000.0
            cleaned = cleaned[:-1]
        elif cleaned.endswith("M"):
            multiplier = 1_000_000.0
            cleaned = cleaned[:-1]
        elif cleaned.endswith("K"):
            multiplier = 1_000.0
            cleaned = cleaned[:-1]
        return float(cleaned or 0) * multiplier
    except Exception:
        return 0.0


def _ensure_country(session: Session) -> Country:
    """Ensure Kenya country record exists."""
    country = session.query(Country).filter(Country.iso_code == "KEN").first()
    if country:
        return country
    country = Country(
        iso_code="KEN",
        name="Kenya",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en_KE",
        meta={"fiscal_year_start": "07-01"},
    )
    session.add(country)
    session.commit()
    session.refresh(country)
    logger.info("Created base country record for Kenya")
    return country


def _ensure_fiscal_period(session: Session, country_id: int) -> FiscalPeriod:
    """Ensure current fiscal period exists for Kenya."""
    period = (
        session.query(FiscalPeriod)
        .filter(
            FiscalPeriod.country_id == country_id, FiscalPeriod.label == FISCAL_LABEL
        )
        .first()
    )
    if period:
        return period
    period = FiscalPeriod(
        country_id=country_id,
        label=FISCAL_LABEL,
        start_date=FISCAL_START,
        end_date=FISCAL_END,
    )
    session.add(period)
    session.commit()
    session.refresh(period)
    logger.info("Created fiscal period %s", FISCAL_LABEL)
    return period


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        logger.warning("Seed file missing: %s", path)
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        logger.error("Failed to load %s: %s", path, exc)
        return {}


def _ensure_source_document(
    session: Session,
    *,
    country_id: int,
    title: str,
    publisher: str,
    doc_type: DocumentType,
    fetch_date: datetime,
    metadata: Dict[str, Any],
) -> SourceDocument:
    document = (
        session.query(SourceDocument)
        .filter(SourceDocument.country_id == country_id, SourceDocument.title == title)
        .first()
    )
    if document:
        # Refresh metadata if it changed
        document.meta = {**(document.meta or {}), **metadata}
        document.fetch_date = fetch_date
        session.add(document)
        session.flush()
        return document

    document = SourceDocument(
        country_id=country_id,
        publisher=publisher,
        title=title,
        url=metadata.get("url"),
        file_path=metadata.get("file_path"),
        fetch_date=fetch_date,
        md5=metadata.get("md5"),
        doc_type=doc_type,
        meta=metadata,
    )
    session.add(document)
    session.flush()
    return document


# --- Typical Kenya county budget sector split (COB averages) ---
# These percentages approximate how county budgets are distributed
# Source: Controller of Budget county reports 2022-2024
COUNTY_BUDGET_SECTORS = [
    {"category": "Health", "development_pct": 0.08, "recurrent_pct": 0.17},
    {
        "category": "Education & Training",
        "development_pct": 0.04,
        "recurrent_pct": 0.06,
    },
    {"category": "Roads & Transport", "development_pct": 0.10, "recurrent_pct": 0.03},
    {
        "category": "Agriculture & Livestock",
        "development_pct": 0.05,
        "recurrent_pct": 0.04,
    },
    {"category": "Water & Sanitation", "development_pct": 0.06, "recurrent_pct": 0.02},
    {
        "category": "Public Administration",
        "development_pct": 0.02,
        "recurrent_pct": 0.18,
    },
    {"category": "County Assembly", "development_pct": 0.01, "recurrent_pct": 0.08},
    {"category": "Trade & Enterprise", "development_pct": 0.02, "recurrent_pct": 0.01},
    {
        "category": "Lands & Urban Planning",
        "development_pct": 0.02,
        "recurrent_pct": 0.01,
    },
]
# Remaining ~6% dev + ~1% recurrent = "Other" catch-all


def _upsert_budget_lines(
    session: Session,
    *,
    entity_id: int,
    period_id: int,
    source_document_id: int,
    total_allocated: Decimal,
    execution_rate: Decimal,
    pending_bills: Decimal,
) -> None:
    """Create multiple BudgetLine rows per county — one per sector."""
    provenance = [
        {
            "source": "bootstrap",
            "dataset": COUNTY_DATA_PATH.name,
            "period": FISCAL_LABEL,
        }
    ]

    # Development is typically ~40% of county budgets, recurrent ~60%
    dev_total = total_allocated * Decimal("0.40")
    rec_total = total_allocated * Decimal("0.60")

    allocated_so_far = Decimal("0")
    for sector in COUNTY_BUDGET_SECTORS:
        cat = sector["category"]
        alloc = (
            dev_total * Decimal(str(sector["development_pct"] / 0.40))
            + rec_total * Decimal(str(sector["recurrent_pct"] / 0.60))
        ).quantize(Decimal("0.01"))
        # Scale alloc so dev_pct + rec_pct share of total makes sense
        alloc = (
            total_allocated
            * Decimal(str(sector["development_pct"] + sector["recurrent_pct"]))
        ).quantize(Decimal("0.01"))
        actual = (alloc * execution_rate / Decimal("100")).quantize(Decimal("0.01"))
        committed = (
            (pending_bills * alloc / total_allocated).quantize(Decimal("0.01"))
            if total_allocated > 0
            else Decimal("0")
        )
        allocated_so_far += alloc

        existing = (
            session.query(BudgetLine)
            .filter(
                BudgetLine.entity_id == entity_id,
                BudgetLine.period_id == period_id,
                BudgetLine.category == cat,
            )
            .first()
        )
        if existing:
            existing.allocated_amount = alloc
            existing.actual_spent = actual
            existing.committed_amount = committed
            existing.currency = "KES"
            existing.source_document_id = source_document_id
            existing.provenance = provenance
            session.add(existing)
        else:
            session.add(
                BudgetLine(
                    entity_id=entity_id,
                    period_id=period_id,
                    category=cat,
                    allocated_amount=alloc,
                    actual_spent=actual,
                    committed_amount=committed,
                    currency="KES",
                    source_document_id=source_document_id,
                    provenance=provenance,
                )
            )

    # "Other" catch-all for the remainder
    remainder = total_allocated - allocated_so_far
    if remainder > 0:
        actual_rem = (remainder * execution_rate / Decimal("100")).quantize(
            Decimal("0.01")
        )
        existing = (
            session.query(BudgetLine)
            .filter(
                BudgetLine.entity_id == entity_id,
                BudgetLine.period_id == period_id,
                BudgetLine.category == "Other",
            )
            .first()
        )
        if existing:
            existing.allocated_amount = remainder
            existing.actual_spent = actual_rem
            existing.committed_amount = Decimal("0")
            existing.currency = "KES"
            existing.source_document_id = source_document_id
            existing.provenance = provenance
            session.add(existing)
        else:
            session.add(
                BudgetLine(
                    entity_id=entity_id,
                    period_id=period_id,
                    category="Other",
                    allocated_amount=remainder,
                    actual_spent=actual_rem,
                    committed_amount=Decimal("0"),
                    currency="KES",
                    source_document_id=source_document_id,
                    provenance=provenance,
                )
            )


def _upsert_population(
    session: Session,
    *,
    entity_id: int,
    population: int,
    source_document_id: int,
) -> None:
    """Create PopulationData row for a county (Census 2019 baseline)."""
    if not population or population <= 0:
        return
    existing = (
        session.query(PopulationData)
        .filter(
            PopulationData.entity_id == entity_id,
            PopulationData.year == 2019,
        )
        .first()
    )
    if existing:
        existing.total_population = population
        existing.source_document_id = source_document_id
        session.add(existing)
        return
    session.add(
        PopulationData(
            entity_id=entity_id,
            year=2019,
            total_population=population,
            source_document_id=source_document_id,
            confidence=Decimal("0.95"),
            meta={"source": "Kenya Census 2019", "bootstrap": True},
        )
    )


def _upsert_county_debt(
    session: Session,
    *,
    entity_id: int,
    county_name: str,
    debt_outstanding: float,
    pending_bills: float,
    source_document_id: int,
) -> None:
    """Create Loan rows for county-level debt (outstanding + pending bills)."""
    provenance = [{"source": "bootstrap", "dataset": COUNTY_DATA_PATH.name}]

    if debt_outstanding and debt_outstanding > 0:
        existing = (
            session.query(Loan)
            .filter(
                Loan.entity_id == entity_id,
                Loan.lender == "County Government Debt",
            )
            .first()
        )
        if existing:
            existing.principal = Decimal(str(debt_outstanding))
            existing.outstanding = Decimal(str(debt_outstanding))
            existing.provenance = provenance
            session.add(existing)
        else:
            session.add(
                Loan(
                    entity_id=entity_id,
                    lender="County Government Debt",
                    debt_category=DebtCategory.OTHER,
                    principal=Decimal(str(debt_outstanding)),
                    outstanding=Decimal(str(debt_outstanding)),
                    interest_rate=Decimal("0"),
                    issue_date=FISCAL_START,
                    maturity_date=None,
                    currency="KES",
                    source_document_id=source_document_id,
                    provenance=provenance,
                )
            )

    if pending_bills and pending_bills > 0:
        existing = (
            session.query(Loan)
            .filter(
                Loan.entity_id == entity_id,
                Loan.lender == "Pending Bills",
            )
            .first()
        )
        if existing:
            existing.principal = Decimal(str(pending_bills))
            existing.outstanding = Decimal(str(pending_bills))
            existing.provenance = provenance
            session.add(existing)
        else:
            session.add(
                Loan(
                    entity_id=entity_id,
                    lender="Pending Bills",
                    debt_category=DebtCategory.PENDING_BILLS,
                    principal=Decimal(str(pending_bills)),
                    outstanding=Decimal(str(pending_bills)),
                    interest_rate=Decimal("0"),
                    issue_date=FISCAL_START,
                    maturity_date=None,
                    currency="KES",
                    source_document_id=source_document_id,
                    provenance=provenance,
                )
            )


def _map_severity(level: str) -> Severity:
    mapping = {
        "high": Severity.CRITICAL,
        "medium": Severity.WARNING,
        "low": Severity.INFO,
        "critical": Severity.CRITICAL,
        "warning": Severity.WARNING,
        "info": Severity.INFO,
    }
    return mapping.get((level or "").lower(), Severity.WARNING)


def _upsert_audit_records(
    session: Session,
    *,
    entity_id: int,
    period_id: int,
    country_id: int,
    county_name: str,
    audit_entries: List[Dict[str, Any]],
) -> None:
    if not audit_entries:
        return

    audit_doc = _ensure_source_document(
        session,
        country_id=country_id,
        title=f"{county_name} County OAG Findings {FISCAL_LABEL}",
        publisher="Office of the Auditor General",
        doc_type=DocumentType.AUDIT,
        fetch_date=datetime(2024, 6, 30),
        metadata={"source": AUDIT_DATA_PATH.name, "county": county_name},
    )

    for entry in audit_entries:
        finding_text = entry.get("description", "Audit finding")
        audit_record = (
            session.query(Audit)
            .filter(Audit.entity_id == entity_id, Audit.finding_text == finding_text)
            .first()
        )

        provenance = [
            {
                "source": AUDIT_DATA_PATH.name,
                "external_id": entry.get("id"),
                "amount_involved": entry.get("amount_involved"),
                "status": entry.get("status"),
                "category": entry.get("category"),
                "query_type": entry.get("query_type"),
                "date_raised": entry.get("date_raised"),
            }
        ]

        severity = _map_severity(entry.get("severity", "medium"))
        query_type = entry.get("query_type") or entry.get("category")
        amount_value = _parse_kes_amount(entry.get("amount_involved"))
        amount = Decimal(str(amount_value)) if amount_value > 0 else None
        status = entry.get("status")
        audit_opinion = entry.get("audit_opinion", "Qualified")

        if audit_record:
            audit_record.severity = severity
            audit_record.source_document_id = audit_doc.id
            audit_record.provenance = provenance
            audit_record.query_type = query_type
            audit_record.amount = amount
            audit_record.status = status
            audit_record.audit_opinion = audit_opinion
            audit_record.audit_year = 2024
            session.add(audit_record)
            continue

        audit_record = Audit(
            entity_id=entity_id,
            period_id=period_id,
            finding_text=finding_text,
            severity=severity,
            recommended_action=None,
            source_document_id=audit_doc.id,
            provenance=provenance,
            query_type=query_type,
            amount=amount,
            status=status,
            audit_opinion=audit_opinion,
            audit_year=2024,
        )
        session.add(audit_record)


# ── National-level (Kenya) GDP + Sovereign Debt ────────────────────────
# Sources:
#   GDP — Kenya National Bureau of Statistics (KNBS) Economic Survey 2025
#   Debt — Central Bank of Kenya Public Debt CSV (April 2025)
NATIONAL_GDP_SERIES = [
    (2020, 10_751_000_000_000),  # KES — KNBS
    (2021, 12_098_000_000_000),
    (2022, 13_362_000_000_000),
    (2023, 14_088_000_000_000),
    (2024, 14_800_000_000_000),  # KNBS preliminary
    (2025, 15_400_000_000_000),  # Estimate
]

# NATIONAL_DEBT_BREAKDOWN removed — debt data now comes from the seeding
# pipeline via `python -m seeding.cli seed --domain national_debt`.
# Real data in: backend/seeding/real_data/national_debt.json
# Source: CBK Public Debt Statistical Bulletin, April 2025.

NATIONAL_POPULATION = 47_564_296  # Census 2019 (KNBS)


def _seed_economic_indicators(
    session: Session,
    *,
    source_document_id: int,
) -> None:
    """Seed key economic indicators that the /economic/summary endpoint needs."""
    # Source: KNBS Economic Survey 2025 + CBK Monthly Economic Indicators
    indicators = [
        # Inflation rates (KNBS CPI releases)
        {"type": "inflation_rate", "date": datetime(2024, 12, 31), "value": Decimal("6.6"), "unit": "percent",
         "source": "KNBS CPI December 2024"},
        {"type": "inflation_rate", "date": datetime(2024, 6, 30), "value": Decimal("4.6"), "unit": "percent",
         "source": "KNBS CPI June 2024"},
        {"type": "inflation_rate", "date": datetime(2023, 12, 31), "value": Decimal("6.6"), "unit": "percent",
         "source": "KNBS CPI December 2023"},
        {"type": "inflation_rate", "date": datetime(2023, 6, 30), "value": Decimal("7.9"), "unit": "percent",
         "source": "KNBS CPI June 2023"},
        {"type": "inflation_rate", "date": datetime(2025, 1, 31), "value": Decimal("3.3"), "unit": "percent",
         "source": "KNBS CPI January 2025"},
        # Unemployment rates (KNBS Labour Force Survey)
        {"type": "unemployment_rate", "date": datetime(2024, 12, 31), "value": Decimal("5.4"), "unit": "percent",
         "source": "KNBS QLFS Q4 2024"},
        {"type": "unemployment_rate", "date": datetime(2023, 12, 31), "value": Decimal("5.6"), "unit": "percent",
         "source": "KNBS QLFS Q4 2023"},
        {"type": "unemployment_rate", "date": datetime(2022, 12, 31), "value": Decimal("5.7"), "unit": "percent",
         "source": "KNBS QLFS Q4 2022"},
        # CPI index values
        {"type": "CPI", "date": datetime(2025, 1, 31), "value": Decimal("143.08"), "unit": "index",
         "source": "KNBS Consumer Price Index January 2025"},
        {"type": "CPI", "date": datetime(2024, 12, 31), "value": Decimal("142.47"), "unit": "index",
         "source": "KNBS Consumer Price Index December 2024"},
    ]

    for ind in indicators:
        existing = (
            session.query(EconomicIndicator)
            .filter(
                EconomicIndicator.indicator_type == ind["type"],
                EconomicIndicator.indicator_date == ind["date"],
                EconomicIndicator.entity_id.is_(None),
            )
            .first()
        )
        if existing:
            existing.value = ind["value"]
            existing.unit = ind["unit"]
            existing.source_document_id = source_document_id
            session.add(existing)
        else:
            session.add(
                EconomicIndicator(
                    indicator_type=ind["type"],
                    indicator_date=ind["date"],
                    value=ind["value"],
                    entity_id=None,
                    unit=ind["unit"],
                    source_document_id=source_document_id,
                    confidence=Decimal("0.90"),
                    meta={"source": ind["source"], "bootstrap": True},
                )
            )

    logger.info("Seeded %d economic indicator records", len(indicators))


def _seed_poverty_indices(
    session: Session,
    *,
    source_document_id: int,
) -> None:
    """Placeholder — NULL entity_id poverty rows are now handled by the seeding
    pipeline's ``national_gdp`` domain.  This function is kept as a no-op so
    callers don't need to be updated."""
    # NOTE: The actual poverty index data (World Bank, KNBS KIHBS) is seeded by
    # seeding.domains.national_gdp which uses raw SQL inserts that reliably
    # persist NULL entity_id rows in Supabase.
    logger.info("Poverty index seeding delegated to national_gdp seeding domain")


def _seed_national_data(
    session: Session,
    *,
    country: Country,
    period: FiscalPeriod,
) -> None:
    """Seed Kenya national GDP, population, and sovereign debt into normalised tables."""
    # Ensure a national-level Entity exists
    national_entity = (
        session.query(Entity)
        .filter(
            Entity.country_id == country.id,
            Entity.type == EntityType.NATIONAL,
        )
        .first()
    )
    if not national_entity:
        national_entity = Entity(
            country_id=country.id,
            type=EntityType.NATIONAL,
            canonical_name="Republic of Kenya",
            slug="republic-of-kenya",
            alt_names=["Kenya", "GOK"],
            meta={},
        )
        session.add(national_entity)
        session.flush()  # get ID

    # Source document for national data
    national_doc = _ensure_source_document(
        session,
        country_id=country.id,
        title="CBK Public Debt Report & KNBS Economic Survey 2025",
        publisher="Central Bank of Kenya / National Treasury",
        doc_type=DocumentType.LOAN,
        fetch_date=datetime(2025, 4, 30),
        metadata={
            "source": "bootstrap",
            "scope": "national",
            "cbk_csv_latest": "Apr 2025",
        },
    )

    # GDP series — clean up orphan rows from other entities (but NOT NULL rows,
    # which are intentional national-level records for /economic/summary)
    orphan_gdp = (
        session.query(GDPData)
        .filter(
            GDPData.entity_id != national_entity.id,
            GDPData.entity_id.isnot(None),
        )
        .all()
    )
    for orphan in orphan_gdp:
        session.delete(orphan)
    if orphan_gdp:
        logger.info(f"Deleted {len(orphan_gdp)} orphan GDP rows")

    for year, gdp_val in NATIONAL_GDP_SERIES:
        existing = (
            session.query(GDPData)
            .filter(GDPData.entity_id == national_entity.id, GDPData.year == year)
            .first()
        )
        if existing:
            existing.gdp_value = Decimal(str(gdp_val))
            session.add(existing)
        else:
            session.add(
                GDPData(
                    entity_id=national_entity.id,
                    year=year,
                    gdp_value=Decimal(str(gdp_val)),
                    source_document_id=national_doc.id,
                    confidence=Decimal("0.90"),
                    meta={"source": "KNBS Economic Survey", "bootstrap": True},
                )
            )

    # NOTE: NULL entity_id GDP rows (for /economic/summary) are handled by the
    # seeding pipeline's "national_gdp" domain, not here.  Bootstrap only manages
    # the entity-linked rows above.
    session.flush()

    # National population
    _upsert_population(
        session,
        entity_id=national_entity.id,
        population=NATIONAL_POPULATION,
        source_document_id=national_doc.id,
    )

    # Also seed a national population record with entity_id=None
    # This is what the /economic/population/latest and /economic/summary endpoints query for
    existing_null_pop = (
        session.query(PopulationData)
        .filter(PopulationData.entity_id.is_(None), PopulationData.year == 2019)
        .first()
    )
    if not existing_null_pop:
        session.add(
            PopulationData(
                entity_id=None,
                year=2019,
                total_population=NATIONAL_POPULATION,
                source_document_id=national_doc.id,
                confidence=Decimal("0.95"),
                meta={"source": "Kenya Census 2019", "bootstrap": True, "scope": "national"},
            )
        )
    elif existing_null_pop.total_population != NATIONAL_POPULATION:
        existing_null_pop.total_population = NATIONAL_POPULATION
        existing_null_pop.source_document_id = national_doc.id
        session.add(existing_null_pop)

    # National debt breakdown is now handled by the seeding pipeline:
    #   python -m seeding.cli seed --domain national_debt
    # Bootstrap no longer writes loan records to avoid conflicts.
    # Clean up any stale bootstrap category-summary rows that may linger
    # from earlier versions of this code.
    stale_bootstrap_loans = [
        loan
        for loan in session.query(Loan)
        .filter(Loan.entity_id == national_entity.id)
        .all()
        if any(
            isinstance(p, dict) and p.get("source") == "bootstrap"
            for p in (loan.provenance or [])
        )
    ]
    if stale_bootstrap_loans:
        for loan in stale_bootstrap_loans:
            session.delete(loan)
        logger.info(
            f"Deleted {len(stale_bootstrap_loans)} stale bootstrap loan rows "
            f"(debt data now comes from seeding pipeline)"
        )

    # Seed economic indicators and poverty indices
    _seed_economic_indicators(session, source_document_id=national_doc.id)
    _seed_poverty_indices(session, source_document_id=national_doc.id)

    logger.info(
        "National-level data seeded (GDP, population, economic indicators, poverty indices). "
        "Run 'python -m seeding.cli seed --domain national_debt' for debt records."
    )


def _seed_federal_audits(
    session: Session,
    *,
    country: Country,
    period: FiscalPeriod,
) -> None:
    """Seed national/federal government audit findings from the OAG report."""
    payload = _load_json(NATIONAL_AUDIT_PATH)
    findings = payload.get("national_audit_findings", [])
    if not findings:
        logger.warning("No national audit findings to seed")
        return

    report_meta = payload.get("metadata", {})
    opinion = payload.get("audit_opinion_summary", {})

    # Create source document for the OAG national report
    oag_doc = _ensure_source_document(
        session,
        country_id=country.id,
        title=report_meta.get(
            "report_title",
            "Report of the Auditor General on National Government FY 2023/2024",
        ),
        publisher="Office of the Auditor General",
        doc_type=DocumentType.AUDIT,
        fetch_date=datetime(2024, 12, 15),
        metadata={
            "source": NATIONAL_AUDIT_PATH.name,
            "scope": "national",
            "auditor_general": report_meta.get("auditor_general", ""),
            "fiscal_year": report_meta.get("fiscal_year", ""),
            "opinion_type": opinion.get("opinion_type", ""),
            "total_amount_questioned": opinion.get("total_amount_questioned", ""),
            "key_statistics": opinion.get("key_statistics", {}),
            "basis_for_qualification": opinion.get("basis_for_qualification", []),
            "emphasis_of_matter": opinion.get("emphasis_of_matter", []),
        },
    )

    seeded = 0
    for entry in findings:
        entity_name = entry.get("entity_name", "")

        # Find matching entity — try MINISTRY first, then NATIONAL
        entity = (
            session.query(Entity)
            .filter(
                Entity.country_id == country.id,
                Entity.canonical_name == entity_name,
            )
            .first()
        )
        if not entity:
            # Try NATIONAL entity for "Republic of Kenya"
            entity = (
                session.query(Entity)
                .filter(
                    Entity.country_id == country.id,
                    Entity.type == EntityType.NATIONAL,
                )
                .first()
            )
        if not entity:
            logger.warning(
                "Skipping national finding %s: no entity '%s'",
                entry.get("id"),
                entity_name,
            )
            continue

        finding_text = entry.get("description", "Federal audit finding")
        existing = (
            session.query(Audit)
            .filter(
                Audit.entity_id == entity.id,
                Audit.finding_text == finding_text,
            )
            .first()
        )

        severity = _map_severity(entry.get("severity", "medium"))
        provenance = [
            {
                "source": NATIONAL_AUDIT_PATH.name,
                "external_id": entry.get("id"),
                "amount_involved": entry.get("amount_involved"),
                "status": entry.get("status"),
                "category": entry.get("category"),
                "query_type": entry.get("query_type"),
                "date_raised": entry.get("date_raised"),
                "report_section": entry.get("report_section"),
                "scope": "national",
            }
        ]

        query_type = entry.get("query_type") or entry.get("category")
        amount_value = _parse_kes_amount(entry.get("amount_involved"))
        amount = Decimal(str(amount_value)) if amount_value > 0 else None
        status = entry.get("status")
        audit_opinion = entry.get("audit_opinion", "Qualified")
        audit_year = int(report_meta.get("fiscal_year", "2024").split("/")[0]) if report_meta.get("fiscal_year") else 2024

        if existing:
            existing.severity = severity
            existing.recommended_action = entry.get("recommended_action")
            existing.source_document_id = oag_doc.id
            existing.provenance = provenance
            existing.query_type = query_type
            existing.amount = amount
            existing.status = status
            existing.audit_opinion = audit_opinion
            existing.audit_year = audit_year
            session.add(existing)
        else:
            session.add(
                Audit(
                    entity_id=entity.id,
                    period_id=period.id,
                    finding_text=finding_text,
                    severity=severity,
                    recommended_action=entry.get("recommended_action"),
                    source_document_id=oag_doc.id,
                    provenance=provenance,
                    query_type=query_type,
                    amount=amount,
                    status=status,
                    audit_opinion=audit_opinion,
                    audit_year=audit_year,
                )
            )
            seeded += 1

    logger.info("Federal audit findings seeded: %d new records", seeded)


def initialize_reference_data(code_lookup: Optional[Dict[str, str]] = None) -> None:
    """Seed canonical county + audit data into the database if missing.

    Performs a fast check first: if 47 county entities already exist we
    skip the expensive per-county loop entirely.  This cuts restart time
    from ~3 min to <1 s on subsequent boots.
    """
    # ── fast path: skip if data already present ──────────────────────
    quick_session = SessionLocal()
    try:
        county_count = (
            quick_session.query(Entity).filter(Entity.type == EntityType.COUNTY).count()
        )
        if county_count >= 47:
            logger.info(
                "Reference data already present (%d county entities) — skipping bootstrap",
                county_count,
            )
            quick_session.close()
            return
    except Exception:
        pass  # table might not exist yet; fall through to full seed
    finally:
        quick_session.close()

    # ── full seed path ───────────────────────────────────────────────
    county_payload = _load_json(COUNTY_DATA_PATH)
    county_records = county_payload.get("county_data", {})
    if not county_records:
        logger.warning("No county data available for seeding")
        return

    audit_payload = _load_json(AUDIT_DATA_PATH)
    audit_by_county: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    missing_by_county: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for entry in audit_payload.get("audit_queries", []) or []:
        audit_by_county[entry.get("county", "")].append(entry)

    for entry in audit_payload.get("missing_funds_cases", []) or []:
        missing_by_county[entry.get("county", "")].append(entry)

    session = SessionLocal()
    try:
        country = _ensure_country(session)
        period = _ensure_fiscal_period(session, country.id)

        for county_name, info in county_records.items():
            county_code = None
            if code_lookup:
                county_code = code_lookup.get(county_name)
            if not county_code:
                county_code = info.get("county_code")
            canonical_name = f"{county_name} County"
            entity = (
                session.query(Entity)
                .filter(
                    Entity.country_id == country.id,
                    Entity.canonical_name == canonical_name,
                )
                .first()
            )
            if not entity:
                slug_base = county_name.lower().replace(" ", "-").replace("'", "")
                slug_suffix = (county_code or "").lower()
                slug = f"{slug_base}-{slug_suffix}".strip("-")
                entity = Entity(
                    country_id=country.id,
                    type=EntityType.COUNTY,
                    canonical_name=canonical_name,
                    slug=slug,
                    alt_names=[county_name],
                    meta={},
                )

            meta = dict(entity.meta or {})
            metrics = dict((meta.get("metrics") or {}).get(FISCAL_LABEL, {}))
            metrics.update(
                {
                    "county_code": county_code,
                    "population": info.get("population", 0),
                    "budget_2025": info.get("budget_2025", 0),
                    "revenue_2024": info.get("revenue_2024", 0),
                    "debt_outstanding": info.get("debt_outstanding", 0),
                    "pending_bills": info.get("pending_bills", 0),
                    "missing_funds": info.get("missing_funds", 0),
                    "budget_execution_rate": info.get("budget_execution_rate", 0),
                    "audit_rating": info.get("audit_rating", ""),
                    "financial_health_score": info.get("financial_health_score", 0),
                    "debt_to_budget_ratio": info.get("debt_to_budget_ratio", 0),
                    "pending_bills_ratio": info.get("pending_bills_ratio", 0),
                    "per_capita_budget": info.get("per_capita_budget", 0),
                }
            )

            meta.setdefault("metrics", {})[FISCAL_LABEL] = metrics
            meta["financial_metrics"] = {
                "budget_execution_rate": info.get("budget_execution_rate", 0),
                "pending_bills": info.get("pending_bills", 0),
                "financial_health_score": info.get("financial_health_score", 0),
                "debt_outstanding": info.get("debt_outstanding", 0),
                "missing_funds": info.get("missing_funds", 0),
                "revenue_2024": info.get("revenue_2024", 0),
            }
            meta["economic_profile"] = {
                "county_type": info.get("county_type"),
                "economic_base": info.get("economic_base"),
                "infrastructure_level": info.get("infrastructure_level"),
                "revenue_potential": info.get("revenue_potential"),
                "major_issues": info.get("major_issues", []),
            }
            if info.get("governor"):
                meta["governor"] = info["governor"]
            meta["last_updated"] = info.get("last_updated")
            if missing_by_county.get(county_name):
                meta["missing_funds_cases"] = missing_by_county[county_name]

            county_audits = audit_by_county.get(county_name, [])
            if county_audits:
                total_amount = sum(
                    _parse_kes_amount(entry.get("amount_involved"))
                    for entry in county_audits
                )
                meta["audit_summary"] = {
                    "queries_count": len(county_audits),
                    "total_amount_involved": total_amount,
                    "last_refreshed": datetime.now(timezone.utc).isoformat(),
                }

            entity.meta = meta
            session.add(entity)
            session.flush()

            last_updated = info.get("last_updated")
            fetch_dt = (
                datetime.fromisoformat(last_updated)
                if isinstance(last_updated, str)
                else datetime.now(timezone.utc)
            )

            budget_doc = _ensure_source_document(
                session,
                country_id=country.id,
                title=f"{county_name} County Budget {FISCAL_LABEL}",
                publisher="County Treasury",
                doc_type=DocumentType.BUDGET,
                fetch_date=fetch_dt,
                metadata={
                    "source": COUNTY_DATA_PATH.name,
                    "county": county_name,
                },
            )

            allocated = _parse_decimal(info.get("budget_2025"))
            execution_rate = _parse_decimal(info.get("budget_execution_rate"))
            committed = _parse_decimal(info.get("pending_bills"))
            _upsert_budget_lines(
                session,
                entity_id=entity.id,
                period_id=period.id,
                source_document_id=budget_doc.id,
                total_allocated=allocated,
                execution_rate=execution_rate,
                pending_bills=committed,
            )

            # Seed PopulationData table (Census 2019)
            _upsert_population(
                session,
                entity_id=entity.id,
                population=int(info.get("population", 0)),
                source_document_id=budget_doc.id,
            )

            # Seed Loan table (county debt + pending bills)
            _upsert_county_debt(
                session,
                entity_id=entity.id,
                county_name=county_name,
                debt_outstanding=float(info.get("debt_outstanding", 0)),
                pending_bills=float(info.get("pending_bills", 0)),
                source_document_id=budget_doc.id,
            )

            _upsert_audit_records(
                session,
                entity_id=entity.id,
                period_id=period.id,
                country_id=country.id,
                county_name=county_name,
                audit_entries=county_audits,
            )

        # --- National-level data (GDP + sovereign debt) ---
        _seed_national_data(session, country=country, period=period)

        # --- Federal/National government audit findings ---
        _seed_federal_audits(session, country=country, period=period)

        session.commit()
        logger.info(
            "Reference county data initialized (%d counties)", len(county_records)
        )
    except Exception as exc:
        session.rollback()
        logger.error("Failed to initialize reference data: %s", exc)
        raise
    finally:
        session.close()

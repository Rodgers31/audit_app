"""
Database loader for normalized financial data
Handles inserting processed data into PostgreSQL with proper relationships.

Improvements:
- Loads env from backend/.env and repo .env
- Builds DB URL via backend.database when DATABASE_URL is not provided
- Adds basic idempotency (dedup) for SourceDocument, BudgetLine, and Audit inserts
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Add backend to path to import models
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend"))

# Ensure environment variables are available from backend/.env and root .env
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # dotenv optional
    load_dotenv = None  # type: ignore

if load_dotenv:
    repo_root = os.path.dirname(os.path.dirname(__file__))
    # Load backend/.env first, then root .env (do not override existing env)
    load_dotenv(os.path.join(repo_root, "backend", ".env"), override=False)
    load_dotenv(os.path.join(repo_root, ".env"), override=False)

try:
    from database import get_db  # type: ignore
    from models import Country  # type: ignore
    from models import (
        Audit,
        Base,
        BudgetLine,
        DocumentType,
        EconomicIndicator,
        Entity,
        EntityType,
        Extraction,
        FiscalPeriod,
        GDPData,
        Loan,
        PopulationData,
        Severity,
        SourceDocument,
    )
except ImportError as e:
    logging.warning(f"Could not import backend models: {e}")

    # Mock models for testing
    class Country:
        pass

    class Entity:
        pass

    class FiscalPeriod:
        pass

    class SourceDocument:
        pass

    class BudgetLine:
        pass

    class Loan:
        pass

    class Audit:
        pass

    class Extraction:
        pass

    # Stubs for KNBS tables
    class PopulationData:
        pass

    class GDPData:
        pass

    class EconomicIndicator:
        pass


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __package__:
    from .writer_ownership import OwnedSession, check_ready, owned_write
else:
    from writer_ownership import OwnedSession, check_ready, owned_write


class DatabaseLoader:
    """
    Loads normalized financial data into PostgreSQL database
    """

    def __init__(self, database_url: Optional[str] = None):
        # Prefer explicit arg, else env DATABASE_URL, else backend.database builder
        db_url = database_url or os.getenv("DATABASE_URL")
        if not db_url:
            try:
                # Import backend.database for URL construction (supports DB_* pooler vars)
                import database as backend_database  # type: ignore

                db_url = getattr(backend_database, "DATABASE_URL", None)
                if not db_url:
                    # Fallback to internal builder if exposed
                    builder = getattr(backend_database, "_build_db_url_from_env", None)
                    if callable(builder):
                        db_url = builder()
            except Exception:
                db_url = None

        # Final fallback for local dev only
        self.database_url = (
            db_url or "postgresql://postgres:password@localhost:5432/audit_app"
        )

        try:
            # Thirteen continuity transactions must stay pinned simultaneously.
            # A small shared/default pool would starve writer/receipt sessions.
            self.engine = create_engine(self.database_url, pool_pre_ping=True, poolclass=NullPool)
            self.SessionLocal = sessionmaker(
                autocommit=False, autoflush=False, bind=self.engine, class_=OwnedSession
            )
        except Exception as e:
            logger.error(f"Could not connect to database: {e}")
            raise

    def check_ownership_ready(self):
        check_ready(self.engine)

    def get_db_session(self):
        """Get database session"""
        if not self.SessionLocal:
            raise RuntimeError("Database not connected")
        return self.SessionLocal()

    @owned_write
    async def ensure_country_exists(self, country_code: str = "KEN") -> int:
        """Ensure Kenya country record exists, return country_id"""
        if not self.engine:
            return 1  # Mock return for testing

        with self.get_db_session() as db:
            country = db.query(Country).filter(Country.iso_code == country_code).first()

            if not country:
                country = Country(
                    iso_code=country_code,
                    name="Kenya",
                    currency="KES",
                    timezone="Africa/Nairobi",
                    default_locale="en_KE",
                    meta={"fiscal_year_start": "07-01"},
                )
                db.add(country)
                db.commit()
                db.refresh(country)
                logger.info(f"Created country record for {country_code}")

            return country.id

    @owned_write
    async def ensure_entity_exists(
        self, entity_data: Dict[str, Any], country_id: int
    ) -> int:
        """Ensure entity record exists, return entity_id"""
        if not self.engine:
            return 1  # Mock return for testing

        with self.get_db_session() as db:
            canonical_name = entity_data["canonical_name"]

            # Try to find existing entity
            entity = (
                db.query(Entity)
                .filter(
                    Entity.canonical_name == canonical_name,
                    Entity.country_id == country_id,
                )
                .first()
            )

            if not entity:
                # Create slug from canonical name
                slug = canonical_name.lower().replace(" ", "-").replace("&", "and")
                slug = "".join(c for c in slug if c.isalnum() or c in "-")

                # Coerce entity type to Enum
                etype = entity_data.get("type")
                if isinstance(etype, str):
                    try:
                        etype = EntityType[etype.upper()]
                    except Exception:
                        etype = EntityType.AGENCY

                # Only include non-empty alt name
                alt = entity_data.get("raw_name")
                alt_names = [alt] if alt and str(alt).strip() else []

                entity = Entity(
                    country_id=country_id,
                    type=etype,
                    canonical_name=canonical_name,
                    slug=slug,
                    alt_names=alt_names,
                    meta={
                        "confidence": entity_data.get("confidence", 0.0),
                        "category": entity_data.get("category", "unknown"),
                    },
                )
                db.add(entity)
                db.commit()
                db.refresh(entity)
                logger.info(f"Created entity: {canonical_name}")

            return entity.id

    @owned_write
    async def ensure_fiscal_period_exists(
        self, period_data: Dict[str, Any], country_id: int
    ) -> int:
        """Ensure fiscal period record exists, return period_id"""
        if not self.engine:
            return 1  # Mock return for testing

        with self.get_db_session() as db:
            label = period_data["label"]

            # Try to find existing period
            period = (
                db.query(FiscalPeriod)
                .filter(
                    FiscalPeriod.label == label, FiscalPeriod.country_id == country_id
                )
                .first()
            )

            if not period:
                period = FiscalPeriod(
                    country_id=country_id,
                    label=label,
                    start_date=period_data["start_date"],
                    end_date=period_data["end_date"],
                )
                db.add(period)
                db.commit()
                db.refresh(period)
                logger.info(f"Created fiscal period: {label}")

            return period.id

    @owned_write
    async def load_document(
        self, document_record: Dict[str, Any], normalized_data: List[Dict[str, Any]]
    ) -> int:
        """Load document and associated normalized data"""
        if not self.engine:
            logger.info(f"Mock loading document: {document_record['title']}")
            return 1

        with self.get_db_session() as db:
            try:
                # Ensure country exists and resolve a valid country_id (default KEN)
                try:
                    country_id = await self.ensure_country_exists(
                        document_record.get("country_code", "KEN")
                    )
                except Exception:
                    # Fallback to provided country_id or default 1 if ensure failed (unlikely)
                    country_id = int(document_record.get("country_id") or 1)
                # Overwrite to guarantee FK integrity
                document_record["country_id"] = country_id

                # Idempotent insert for SourceDocument: first try to find existing
                existing = None
                try:
                    if document_record.get("md5"):
                        existing = (
                            db.query(SourceDocument)
                            .filter(SourceDocument.md5 == document_record["md5"])
                            .first()
                        )
                    if not existing and document_record.get("url"):
                        existing = (
                            db.query(SourceDocument)
                            .filter(SourceDocument.url == document_record["url"])
                            .first()
                        )
                except Exception:
                    existing = None

                if existing:
                    source_doc = existing
                    logger.info(
                        f"Reusing existing document record: {source_doc.id} (md5/url match)"
                    )
                else:
                    # Create new source document record
                    # Coerce doc_type to Enum
                    doc_type = document_record.get("doc_type")
                    if isinstance(doc_type, str):
                        key = doc_type.lower()
                        mapping = {
                            "budget": DocumentType.BUDGET,
                            "audit": DocumentType.AUDIT,
                            "report": DocumentType.REPORT,
                            "loan": DocumentType.LOAN,
                            "other": DocumentType.OTHER,
                            # Normalize common aliases
                            "debt": DocumentType.REPORT,
                            "borrowing": DocumentType.REPORT,
                        }
                        doc_type = mapping.get(key, DocumentType.OTHER)
                    source_doc = SourceDocument(
                        country_id=document_record["country_id"],
                        publisher=document_record["publisher"],
                        title=document_record["title"],
                        url=document_record["url"],
                        file_path=document_record["file_path"],
                        fetch_date=document_record["fetch_date"],
                        md5=document_record["md5"],
                        doc_type=doc_type,
                        meta=document_record["metadata"],
                    )
                    db.add(source_doc)
                    db.commit()
                    db.refresh(source_doc)

                    logger.info(f"Created document record: {source_doc.id}")

                # Load normalized data items
                await self._load_normalized_items(db, normalized_data, source_doc.id)

                return source_doc.id

            except Exception as e:
                db.rollback()
                logger.error(f"Error loading document: {e}")
                raise

    async def _load_normalized_items(
        self, db, normalized_data: List[Dict[str, Any]], source_doc_id: int
    ):
        """Load individual normalized budget line items"""
        country_id = await self.ensure_country_exists()

        for item in normalized_data:
            try:
                # Route by item kind; default to budget line
                kind = item.get("_kind", "budget_line")
                if kind == "audit_finding":
                    await self._load_audit_finding_item(
                        db, item, source_doc_id, country_id
                    )
                elif kind == "population_data":
                    await self._load_population_item(
                        db, item, source_doc_id, country_id
                    )
                elif kind == "gdp_data":
                    await self._load_gdp_item(db, item, source_doc_id, country_id)
                elif kind == "economic_indicator":
                    await self._load_indicator_item(db, item, source_doc_id, country_id)
                else:
                    await self._load_budget_line_item(
                        db, item, source_doc_id, country_id
                    )
            except Exception as e:
                logger.error(f"Error loading item {item}: {e}")
                continue

    async def _load_budget_line_item(
        self, db, item: Dict[str, Any], source_doc_id: int, country_id: int
    ):
        """Load a single budget line item"""

        # Ensure entity exists
        if "entity" not in item:
            logger.warning("No entity data in item, skipping")
            return

        entity_id = await self.ensure_entity_exists(item["entity"], country_id)

        # Ensure fiscal period exists (use default if not specified)
        period_id = 1  # Default period
        if "fiscal_period" in item:
            period_id = await self.ensure_fiscal_period_exists(
                item["fiscal_period"], country_id
            )

        # Create budget line
        # Prepare values
        category = item.get("category", "Unknown")
        subcategory = item.get("subcategory")
        allocated_amount = item.get("allocated_amount", {}).get("base_amount")
        actual_spent = item.get("actual_amount", {}).get("base_amount")
        committed_amount = item.get("committed_amount", {}).get("base_amount")

        # Deduplicate: check for an existing near-identical budget line for this document
        try:
            exists = (
                db.query(BudgetLine)
                .filter(
                    BudgetLine.entity_id == entity_id,
                    BudgetLine.period_id == period_id,
                    BudgetLine.source_document_id == source_doc_id,
                    BudgetLine.category == category,
                    (
                        BudgetLine.subcategory.is_(subcategory)
                        if subcategory is None
                        else BudgetLine.subcategory == subcategory
                    ),
                    (
                        BudgetLine.allocated_amount.is_(allocated_amount)
                        if allocated_amount is None
                        else BudgetLine.allocated_amount == allocated_amount
                    ),
                    (
                        BudgetLine.actual_spent.is_(actual_spent)
                        if actual_spent is None
                        else BudgetLine.actual_spent == actual_spent
                    ),
                )
                .first()
            )
        except Exception:
            exists = None

        if exists:
            logger.debug(
                f"Skipping duplicate budget line for entity {entity_id} / doc {source_doc_id}"
            )
            return

        budget_line = BudgetLine(
            entity_id=entity_id,
            period_id=period_id,
            category=category,
            subcategory=subcategory,
            allocated_amount=allocated_amount,
            actual_spent=actual_spent,
            committed_amount=committed_amount,
            currency="KES",  # Default to KES for Kenya
            source_document_id=source_doc_id,
            page_ref=str(item.get("source_table", {}).get("page", 1)),
            notes=f"Extracted from table {item.get('source_table', {}).get('table_index', 0)}",
            provenance=[
                {
                    "source_document_id": source_doc_id,
                    "page": item.get("source_table", {}).get("page", 1),
                    "table_index": item.get("source_table", {}).get("table_index", 0),
                    "row_index": item.get("source_table", {}).get("row_index", 0),
                    "confidence": item.get("extraction_metadata", {}).get(
                        "confidence", 0.0
                    ),
                    "extraction_date": item.get("extraction_metadata", {}).get(
                        "extraction_date"
                    ),
                }
            ],
        )

        db.add(budget_line)
        db.commit()
        logger.debug(f"Created budget line for entity {entity_id}")

    async def _load_audit_finding_item(
        self, db, item: Dict[str, Any], source_doc_id: int, country_id: int
    ):
        """Load a single audit finding into the audits table."""

        # Ensure entity exists (fallback to Unknown if missing)
        entity_info = item.get("entity") or {
            "canonical_name": "Unknown Entity",
            "type": "agency",
            "confidence": 0.0,
        }
        entity_id = await self.ensure_entity_exists(entity_info, country_id)

        # Ensure fiscal period exists if provided
        period_id = 1
        if item.get("fiscal_period"):
            period_id = await self.ensure_fiscal_period_exists(
                item["fiscal_period"], country_id
            )

        # Map severity string to enum name expected by SQLAlchemy Enum
        severity_str = (item.get("severity") or "info").upper()
        if severity_str not in {"INFO", "WARNING", "CRITICAL"}:
            severity_str = "INFO"

        # Build provenance record
        provenance = item.get("provenance") or {}
        prov = [
            {
                "source_document_id": source_doc_id,
                **provenance,
            }
        ]

        # Deduplicate audit finding by entity/period/text per document
        finding_text = item.get("finding_text", "")
        try:
            exists = (
                db.query(Audit)
                .filter(
                    Audit.entity_id == entity_id,
                    Audit.period_id == period_id,
                    Audit.source_document_id == source_doc_id,
                    Audit.finding_text == finding_text,
                )
                .first()
            )
        except Exception:
            exists = None

        if exists:
            logger.debug(
                f"Skipping duplicate audit finding for entity {entity_id} / doc {source_doc_id}"
            )
            return

        # Create audit row
        # Coerce severity to Enum value
        sev_enum = Severity[severity_str]
        audit = Audit(
            entity_id=entity_id,
            period_id=period_id,
            finding_text=finding_text,
            severity=sev_enum,
            recommended_action=item.get("recommended_action"),
            source_document_id=source_doc_id,
            provenance=prov,
        )

        db.add(audit)
        db.commit()
        logger.debug(f"Created audit finding for entity {entity_id}")

    @owned_write
    async def load_audit_findings_document(
        self,
        document_record: Dict[str, Any],
        audit_findings: List[Dict[str, Any]],
    ) -> int:
        """Persist an audit document with parsed findings."""
        # Tag items as audit kind for router
        normalized = [{"_kind": "audit_finding", **f} for f in audit_findings]
        return await self.load_document(document_record, normalized)

    # ================= KNBS loaders =================
    def _parse_period_to_date(self, period: str) -> datetime:
        """Parse period strings like '2025-05', '2025-Q2', '2025' to a representative date."""
        try:
            p = (period or "").strip()
            if not p:
                return datetime(datetime.now().year, 1, 1)
            if re := __import__("re"):
                import calendar

                m = re.match(r"^(\d{4})-(\d{2})$", p)
                if m:
                    y, mm = int(m.group(1)), int(m.group(2))
                    return datetime(y, mm, 1)
                m = re.match(r"^(\d{4})-Q([1-4])$", p, re.I)
                if m:
                    y, q = int(m.group(1)), int(m.group(2))
                    month = (q - 1) * 3 + 1
                    return datetime(y, month, 1)
                m = re.match(r"^(\d{4})$", p)
                if m:
                    y = int(m.group(1))
                    return datetime(y, 1, 1)
        except Exception:
            pass
        return datetime(datetime.now().year, 1, 1)

    async def _load_population_item(
        self, db, item: Dict[str, Any], source_doc_id: int, country_id: int
    ):
        """Insert population row if value present and > 0; dedupe on (entity, year, source_doc)."""
        total = item.get("total_population")
        year = item.get("year")
        if not total or (isinstance(total, (int, float)) and float(total) <= 0):
            logger.debug("Skipping population item with missing/zero total")
            return

        entity_info = item.get("entity") or {
            "canonical_name": "Kenya",
            "type": "NATIONAL",
        }
        entity_id = await self.ensure_entity_exists(entity_info, country_id)

        try:
            existing = (
                db.query(PopulationData)
                .filter(
                    PopulationData.entity_id == entity_id,
                    PopulationData.year == year,
                    PopulationData.source_document_id == source_doc_id,
                )
                .first()
            )
        except Exception:
            existing = None
        if existing:
            logger.debug(
                "Skipping duplicate population_data for entity %s year %s",
                entity_id,
                year,
            )
            return

        row = PopulationData(
            entity_id=entity_id,
            year=year,
            total_population=int(total),
            male_population=item.get("male_population"),
            female_population=item.get("female_population"),
            urban_population=item.get("urban_population"),
            rural_population=item.get("rural_population"),
            population_density=item.get("population_density"),
            source_document_id=source_doc_id,
            source_page=item.get("source_page"),
            confidence=item.get("confidence", 1.0),
            meta=item.get("meta", {}),
        )
        db.add(row)
        db.commit()

    async def _load_gdp_item(
        self, db, item: Dict[str, Any], source_doc_id: int, country_id: int
    ):
        """Insert an explicit finite GDP/GCP level, including reported zero; dedupe."""
        if __package__:
            from .gdp_values import reported_gdp_level
        else:
            from gdp_values import reported_gdp_level

        val = reported_gdp_level(item.get("gdp_value"))
        year = item.get("year")
        quarter = item.get("quarter")
        if val is None:
            logger.warning("Skipping GDP item with missing or invalid reported level")
            return

        entity_info = item.get("entity") or {
            "canonical_name": "Kenya",
            "type": "NATIONAL",
        }
        entity_id = await self.ensure_entity_exists(entity_info, country_id)

        try:
            existing = (
                db.query(GDPData)
                .filter(
                    GDPData.entity_id == entity_id,
                    GDPData.year == year,
                    (
                        GDPData.quarter == quarter
                        if quarter
                        else GDPData.quarter.is_(None)
                    ),
                    GDPData.source_document_id == source_doc_id,
                )
                .first()
            )
        except Exception:
            existing = None
        if existing:
            logger.debug(
                "Skipping duplicate gdp_data for entity %s year %s quarter %s",
                entity_id,
                year,
                quarter,
            )
            return

        row = GDPData(
            entity_id=entity_id,
            year=year,
            quarter=quarter,
            gdp_value=float(val),
            gdp_growth_rate=item.get("gdp_growth_rate"),
            currency=item.get("currency", "KES"),
            source_document_id=source_doc_id,
            source_page=item.get("source_page"),
            confidence=item.get("confidence", 1.0),
            meta=item.get("meta", {}),
        )
        db.add(row)
        db.commit()

    async def _load_indicator_item(
        self, db, item: Dict[str, Any], source_doc_id: int, country_id: int
    ):
        """Insert economic indicator if value present and non-zero; dedupe on (type, date, entity)."""
        val = item.get("value")
        if val is None or (isinstance(val, (int, float)) and float(val) == 0.0):
            logger.debug("Skipping indicator with missing/zero value")
            return

        itype = item.get("indicator_type") or item.get("type")
        period = item.get("period") or item.get("indicator_date")
        if not itype or not period:
            logger.debug("Skipping indicator missing type/period")
            return

        indicator_date = self._parse_period_to_date(str(period))
        entity_info = item.get("entity") or {
            "canonical_name": "Kenya",
            "type": "NATIONAL",
        }
        entity_id = await self.ensure_entity_exists(entity_info, country_id)

        try:
            existing = (
                db.query(EconomicIndicator)
                .filter(
                    EconomicIndicator.indicator_type == itype,
                    EconomicIndicator.indicator_date == indicator_date,
                    EconomicIndicator.entity_id == entity_id,
                    EconomicIndicator.source_document_id == source_doc_id,
                )
                .first()
            )
        except Exception:
            existing = None
        if existing:
            logger.debug(
                "Skipping duplicate indicator %s for %s", itype, indicator_date
            )
            return

        row = EconomicIndicator(
            indicator_type=itype,
            indicator_date=indicator_date,
            value=float(val),
            entity_id=entity_id,
            unit=item.get("unit"),
            source_document_id=source_doc_id,
            source_page=item.get("source_page"),
            confidence=item.get("confidence", 1.0),
            meta=item.get("meta", {}),
        )
        db.add(row)
        db.commit()

    @owned_write
    async def load_sample_kenya_data(self):
        """Load sample Kenya data for MVP testing"""
        logger.info("Loading sample Kenya data...")

        country_id = await self.ensure_country_exists("KEN")

        # Sample entities
        sample_entities = [
            {
                "canonical_name": "Ministry of Health",
                "type": "ministry",
                "confidence": 1.0,
            },
            {
                "canonical_name": "Ministry of Education",
                "type": "ministry",
                "confidence": 1.0,
            },
            {"canonical_name": "Nairobi County", "type": "county", "confidence": 1.0},
            {"canonical_name": "Mombasa County", "type": "county", "confidence": 1.0},
        ]

        for entity_data in sample_entities:
            await self.ensure_entity_exists(entity_data, country_id)

        # Sample fiscal period
        sample_period = {
            "label": "FY2024/25",
            "start_date": datetime(2024, 7, 1).date(),
            "end_date": datetime(2025, 6, 30).date(),
        }
        period_id = await self.ensure_fiscal_period_exists(sample_period, country_id)

        logger.info(
            f"Sample data loaded for country_id={country_id}, period_id={period_id}"
        )

    async def get_data_summary(self) -> Dict[str, Any]:
        """Get summary of loaded data"""
        if not self.engine:
            return {"status": "Database not connected"}

        # A summary is read-only and does not contend with active ingestion.
        with sessionmaker(bind=self.engine)() as db:
            try:
                summary = {}

                # Count records
                summary["countries"] = db.query(Country).count()
                summary["entities"] = db.query(Entity).count()
                summary["fiscal_periods"] = db.query(FiscalPeriod).count()
                summary["source_documents"] = db.query(SourceDocument).count()
                summary["budget_lines"] = db.query(BudgetLine).count()

                # Get latest document
                latest_doc = (
                    db.query(SourceDocument)
                    .order_by(SourceDocument.fetch_date.desc())
                    .first()
                )
                if latest_doc:
                    summary["latest_document"] = {
                        "title": latest_doc.title,
                        "publisher": latest_doc.publisher,
                        "fetch_date": latest_doc.fetch_date.isoformat(),
                    }

                return summary

            except Exception as e:
                logger.error(f"Error getting data summary: {e}")
                return {"error": str(e)}


if __name__ == "__main__":
    # Test the database loader
    async def test_loader():
        loader = DatabaseLoader()

        # Load sample data
        await loader.load_sample_kenya_data()

        # Get summary
        summary = await loader.get_data_summary()
        print("Data Summary:")
        for key, value in summary.items():
            print(f"  {key}: {value}")

    asyncio.run(test_loader())

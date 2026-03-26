"""National GDP and Poverty Index seeding domain.

Seeds national-level (entity_id=NULL) GDP and poverty index records that the
/economic/summary endpoint relies on.  These complement the entity-linked GDP
rows created by bootstrap (entity_id = national entity ID).

Data sources:
  GDP — Kenya National Bureau of Statistics (KNBS) Economic Survey 2025
  Poverty — World Bank Kenya Economic Update 2024 & KNBS KIHBS
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from models import (
    Country,
    DocumentType,
    GDPData,
    PovertyIndex,
    SourceDocument,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...registries import register_domain
from ...types import DomainRunContext, DomainRunResult

logger = logging.getLogger("seeding.national_gdp")

# ── Static data series ─────────────────────────────────────────────────
# Source: KNBS Economic Survey 2025 (GDP in KES)
NATIONAL_GDP_SERIES = [
    (2020, 10_751_000_000_000),
    (2021, 12_098_000_000_000),
    (2022, 13_362_000_000_000),
    (2023, 14_088_000_000_000),
    (2024, 14_800_000_000_000),  # KNBS preliminary
    (2025, 15_400_000_000_000),  # Estimate
]

# Source: World Bank, KNBS KIHBS
POVERTY_SERIES = [
    {
        "year": 2024,
        "headcount": Decimal("33.4"),
        "extreme": Decimal("8.6"),
        "gini": Decimal("0.408"),
        "source": "World Bank Kenya Economic Update 2024",
    },
    {
        "year": 2021,
        "headcount": Decimal("36.1"),
        "extreme": Decimal("10.2"),
        "gini": Decimal("0.410"),
        "source": "KNBS KIHBS 2021",
    },
    {
        "year": 2019,
        "headcount": Decimal("36.1"),
        "extreme": Decimal("8.5"),
        "gini": Decimal("0.408"),
        "source": "KNBS KIHBS 2015/16 (adjusted for 2019 Census)",
    },
]


def _ensure_source_document(session: Session) -> SourceDocument:
    """Get or create the source document for national GDP data."""
    url = "https://www.knbs.or.ke/economic-survey-2025/"
    stmt = select(SourceDocument).where(SourceDocument.url == url)
    doc = session.execute(stmt).scalar_one_or_none()
    if doc is None:
        country = session.execute(
            select(Country).order_by(Country.id.asc())
        ).scalar_one_or_none()
        doc = SourceDocument(
            country_id=country.id if country else None,
            publisher="KNBS / World Bank",
            title="KNBS Economic Survey 2025 & World Bank Poverty Data",
            url=url,
            file_path=None,
            fetch_date=datetime.now(timezone.utc),
            doc_type=DocumentType.REPORT,
            md5=None,
            meta={"seeding_domain": "national_gdp"},
        )
        session.add(doc)
        session.flush()
    return doc


@register_domain("national_gdp")
def run(
    session: Session, settings: SeedingSettings, context: DomainRunContext
) -> DomainRunResult:
    started_at = datetime.now(timezone.utc)
    created = 0
    updated = 0
    errors: list[str] = []

    try:
        doc = _ensure_source_document(session)

        # ── GDP records with entity_id=NULL ──────────────────────────
        for year, gdp_val in NATIONAL_GDP_SERIES:
            existing = (
                session.query(GDPData)
                .filter(GDPData.entity_id.is_(None), GDPData.year == year)
                .first()
            )
            value = Decimal(str(gdp_val))
            if existing is None:
                session.execute(
                    GDPData.__table__.insert().values(
                        entity_id=None,
                        year=year,
                        gdp_value=value,
                        source_document_id=doc.id,
                        confidence=Decimal("0.90"),
                        currency="KES",
                        metadata={
                            "source": "KNBS Economic Survey",
                            "seeding_domain": "national_gdp",
                            "scope": "national",
                        },
                    )
                )
                created += 1
                logger.info("Created NULL-entity GDP row for %d", year)
            elif existing.gdp_value != value:
                existing.gdp_value = value
                existing.source_document_id = doc.id
                session.add(existing)
                updated += 1

        # ── Poverty index records with entity_id=NULL ────────────────
        for data in POVERTY_SERIES:
            existing = (
                session.query(PovertyIndex)
                .filter(
                    PovertyIndex.entity_id.is_(None),
                    PovertyIndex.year == data["year"],
                )
                .first()
            )
            if existing is None:
                session.execute(
                    PovertyIndex.__table__.insert().values(
                        entity_id=None,
                        year=data["year"],
                        poverty_headcount_rate=data["headcount"],
                        extreme_poverty_rate=data["extreme"],
                        gini_coefficient=data["gini"],
                        source_document_id=doc.id,
                        confidence=Decimal("0.85"),
                        metadata={
                            "source": data["source"],
                            "seeding_domain": "national_gdp",
                        },
                    )
                )
                created += 1
                logger.info(
                    "Created poverty index row for %d", data["year"]
                )
            else:
                changed = False
                if existing.poverty_headcount_rate != data["headcount"]:
                    existing.poverty_headcount_rate = data["headcount"]
                    changed = True
                if existing.extreme_poverty_rate != data["extreme"]:
                    existing.extreme_poverty_rate = data["extreme"]
                    changed = True
                if existing.gini_coefficient != data["gini"]:
                    existing.gini_coefficient = data["gini"]
                    changed = True
                if changed:
                    existing.source_document_id = doc.id
                    session.add(existing)
                    updated += 1

    except Exception as exc:
        logger.exception("national_gdp seeding failed: %s", exc)
        errors.append(str(exc))

    processed = len(NATIONAL_GDP_SERIES) + len(POVERTY_SERIES)
    logger.info(
        "national_gdp complete: %d created, %d updated, %d processed",
        created,
        updated,
        processed,
    )

    return DomainRunResult(
        domain="national_gdp",
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        items_processed=processed,
        items_created=created,
        items_updated=updated,
        dry_run=context.dry_run,
        errors=errors,
        metadata={},
    )


__all__ = ["run"]

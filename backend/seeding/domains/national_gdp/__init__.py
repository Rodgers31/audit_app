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
from ...http_client import create_http_client
from ...registries import register_domain
from ...types import DomainRunContext, DomainRunResult
from . import fetcher

logger = logging.getLogger("seeding.national_gdp")

# GDP is fetched live from the World Bank (NY.GDP.MKTP.CN), with an in-repo
# World Bank-sourced fixture as the last-known-good fallback. There is
# intentionally NO hardcoded GDP series here: a wrong/low GDP constant
# (previously 2025 = 15.4T vs the real ~16-18T) is exactly what inflated
# the headline debt-to-GDP ratio to 82%. See national_gdp/fetcher.py and
# seeding/real_data/national_gdp.json.

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


def _ensure_gdp_source_document(session: Session) -> SourceDocument:
    """Get or create the World Bank source document for national GDP."""
    url = "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN"
    stmt = select(SourceDocument).where(SourceDocument.url == url)
    doc = session.execute(stmt).scalar_one_or_none()
    if doc is None:
        country = session.execute(
            select(Country).order_by(Country.id.asc())
        ).scalar_one_or_none()
        doc = SourceDocument(
            country_id=country.id if country else None,
            publisher="World Bank",
            title="World Bank — Kenya GDP, current LCU (NY.GDP.MKTP.CN)",
            url=url,
            file_path=None,
            fetch_date=datetime.now(timezone.utc),
            doc_type=DocumentType.REPORT,
            md5=None,
            meta={"seeding_domain": "national_gdp", "indicator": "NY.GDP.MKTP.CN"},
        )
        session.add(doc)
        session.flush()
    return doc


def _ensure_source_document(session: Session) -> SourceDocument:
    """Get or create the source document for national poverty data."""
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

    gdp_years = 0
    try:
        doc = _ensure_source_document(session)
        gdp_doc = _ensure_gdp_source_document(session)

        # ── GDP records (entity_id=NULL) — fetched from the World Bank ─
        # Live World Bank NY.GDP.MKTP.CN, with the World Bank-sourced
        # fixture as the last-known-good fallback. On total fetch failure
        # we keep whatever GDP rows already exist — never overwrite real
        # data with a guess, never inject a hardcoded estimate.
        try:
            with create_http_client(settings) as client:
                gdp_by_year = fetcher.fetch_national_gdp_kes(client, settings)
        except Exception as exc:
            logger.warning(
                "national_gdp: GDP fetch failed (%s); keeping existing rows", exc
            )
            gdp_by_year = {}
            errors.append(f"GDP fetch failed: {exc}")

        gdp_years = len(gdp_by_year)
        # Record the data vintage (latest covered year) on the source doc so
        # downstream endpoints can report an honest "as of", not the request
        # time. See backend/provenance.py.
        if gdp_by_year and isinstance(gdp_doc.meta, dict):
            latest_gdp_year = max(gdp_by_year)
            gdp_doc.meta = {
                **gdp_doc.meta,
                "publication_date": f"{latest_gdp_year}-12-31",
                "covers_through_year": latest_gdp_year,
            }
            session.add(gdp_doc)
        for year, gdp_kes in sorted(gdp_by_year.items()):
            value = Decimal(str(gdp_kes))
            existing = (
                session.query(GDPData)
                .filter(GDPData.entity_id.is_(None), GDPData.year == year)
                .first()
            )
            if existing is None:
                session.execute(
                    GDPData.__table__.insert().values(
                        entity_id=None,
                        year=year,
                        gdp_value=value,
                        source_document_id=gdp_doc.id,
                        confidence=Decimal("0.95"),
                        currency="KES",
                        metadata={
                            "source": "World Bank NY.GDP.MKTP.CN",
                            "seeding_domain": "national_gdp",
                            "scope": "national",
                            "data_quality": "official",
                        },
                    )
                )
                created += 1
                logger.info("Created NULL-entity GDP row for %d", year)
            elif existing.gdp_value != value:
                existing.gdp_value = value
                existing.source_document_id = gdp_doc.id
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

    processed = gdp_years + len(POVERTY_SERIES)
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

"""Live county population, from the census itself.

Replaces the county half of this domain, which had three routes to a figure
and no route to a source:

* ``enhanced_county_data.json`` — bootstrap's fixture, 377 days old, whose own
  metadata calls its contents "realistic estimates". It supplied all 47
  counties and cited nothing.
* ``real_data_fetcher._get_2019_census_data()`` — a dict typed into a module
  that advertises fetching from KNBS.
* one live PDF read that produced twelve rows, all labelled Samburu, with
  years 130 through 897.

This module reads Table 2.2 of the census volume, gates it on the table's own
arithmetic, and writes rows that carry the document, the page and the
extraction they came from.

WHAT CHANGES, IN FIGURES
------------------------
46 of the 47 populations are unchanged — the fixture's numbers were the census
numbers, they simply could not be shown to be. The exception is Mandera, which
the fixture put at 1,200,890 against the census's 867,457 (434,976 male +
432,444 female + 37 intersex, Table 2.2). So this also corrects a county the
fixture had wrong by a third of a million people while labelling it
"Kenya Census 2019".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from models import DocumentType, Entity, Extraction, PopulationData, SourceDocument
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import SeedingSettings
from ...extractors.knbs_census_population import (
    CENSUS_YEAR,
    EXTRACTOR_ID,
    CensusPopulation,
    CensusPopulationError,
    extract_census_population,
)
from ...fetch_documents import fetch_document
from ...http_client import SeedingHttpClient

logger = logging.getLogger("seeding.population.census_counties")

#: 2019 Kenya Population and Housing Census, Volume I: Population by County
#: and Sub-County (KNBS, November 2019). Linked from the census landing page
#: at knbs.or.ke/reports/kenya-census-2019/.
CENSUS_VOLUME_I_URL = (
    "https://www.knbs.or.ke/wp-content/uploads/2023/09/"
    "2019-Kenya-population-and-Housing-Census-Volume-1-"
    "Population-By-County-And-Sub-County.pdf"
)
CENSUS_TITLE = (
    "2019 Kenya Population and Housing Census Volume I: "
    "Population by County and Sub-County"
)
PUBLISHER = "Kenya National Bureau of Statistics"

#: A census is decennial. Re-downloading a document that cannot change for
#: years is bandwidth spent to learn nothing, so the cache holds it for a
#: month; ``fetch_document`` still notices if the publisher re-issues it.
CACHE_TTL_SECONDS = 30 * 24 * 3600


@dataclass
class CensusLoadStats:
    processed: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    quarantine_reason: Optional[str] = None
    errors: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def _slug_for(county: str) -> str:
    """The slug this project stores county entities under."""
    return county.lower().replace(" ", "-").replace("'", "") + "-county"


def read_census_counties(path: Path) -> CensusPopulation:
    """Extract Table 2.2 from the downloaded volume."""
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        return extract_census_population(pdf)


def load_census_population(
    session: Session,
    client: SeedingHttpClient,
    settings: SeedingSettings,
    *,
    country_id: int,
    dry_run: bool = False,
) -> CensusLoadStats:
    """Fetch, extract and persist the county populations.

    Every failure quarantines: the reason is recorded and NO row is written.
    Half a census is not a census — a partial write would leave some counties
    on derived figures and the rest on the fixture, with nothing saying which
    is which.
    """
    stats = CensusLoadStats()

    doc = fetch_document(
        session,
        client,
        settings,
        url=CENSUS_VOLUME_I_URL,
        country_id=country_id,
        publisher=PUBLISHER,
        title=CENSUS_TITLE,
        doc_type=DocumentType.REPORT,
        dataset_id="knbs_census_2019",
    )
    if not doc.file_path or not Path(doc.file_path).exists():
        stats.quarantine_reason = "census_pdf_not_downloaded"
        stats.errors.append(f"{CENSUS_VOLUME_I_URL} produced no local file")
        return stats

    try:
        result = read_census_counties(Path(doc.file_path))
    except CensusPopulationError as exc:
        stats.quarantine_reason = exc.reason
        stats.errors.append(str(exc))
        logger.warning("census population quarantined: %s", exc)
        return stats

    # One extraction row per run of the table, so every population row can
    # point at the parse it came from and the checks that parse passed.
    extraction = Extraction(
        source_document_id=doc.id,
        page_number=result.page,
        extractor=EXTRACTOR_ID,
        extracted_json={
            "table": "2.2 Distribution of Population by Sex and County",
            "census_year": CENSUS_YEAR,
            "national_total": result.national_total,
            "checks": result.checks,
            "counties": [
                {
                    "county": c.county,
                    "male": c.male,
                    "female": c.female,
                    "intersex": c.intersex,
                    "total": c.total,
                }
                for c in result.counties
            ],
        },
        confidence=1.0,
    )
    session.add(extraction)
    session.flush()

    slugs = [_slug_for(c.county) for c in result.counties]
    entities = {
        e.slug: e
        for e in session.execute(select(Entity).where(Entity.slug.in_(slugs)))
        .scalars()
        .all()
    }
    unresolved = sorted({s for s in slugs if s not in entities})
    if unresolved:
        # Refuse rather than write a partial census.
        stats.quarantine_reason = "county_entities_unresolved"
        stats.errors.append(
            f"{len(unresolved)} county slug(s) match no entity: "
            f"{', '.join(unresolved)}"
        )
        return stats

    existing = {
        (row.entity_id, row.year): row
        for row in session.execute(
            select(PopulationData).where(
                PopulationData.entity_id.in_([e.id for e in entities.values()]),
                PopulationData.year == CENSUS_YEAR,
            )
        )
        .scalars()
        .all()
    }

    for county in result.counties:
        stats.processed += 1
        entity = entities[_slug_for(county.county)]
        row = existing.get((entity.id, CENSUS_YEAR))
        values = {
            "total_population": county.total,
            "male_population": county.male,
            "female_population": county.female,
            "source_document_id": doc.id,
            "source_page": result.page,
            "extraction_id": extraction.id,
            "page_ref": f"p. {result.page}",
            "confidence": 1.0,
            "meta": {
                "census_year": CENSUS_YEAR,
                "intersex_population": county.intersex,
                "table": "2.2",
                "source_url": CENSUS_VOLUME_I_URL,
            },
        }
        if row is None:
            session.add(
                PopulationData(entity_id=entity.id, year=CENSUS_YEAR, **values)
            )
            stats.created += 1
        else:
            changed = False
            for attr, value in values.items():
                if getattr(row, attr) != value:
                    setattr(row, attr, value)
                    changed = True
            if changed:
                stats.updated += 1
            else:
                stats.skipped += 1

    session.flush()
    logger.info(
        "census population: %d counties (%d created, %d updated, %d unchanged) "
        "from doc %s p.%d",
        stats.processed, stats.created, stats.updated, stats.skipped,
        doc.id, result.page,
    )
    return stats

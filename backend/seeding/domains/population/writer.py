"""Persist normalized population records."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, List

from models import PopulationData
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...types import DomainRunContext
from .parser import PopulationRecord

logger = logging.getLogger("seeding.population.writer")


@dataclass
class PersistenceStats:
    processed: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)


def _apply_record(model: PopulationData, record: PopulationRecord) -> bool:
    """Replace the observation and its evidence as one source-owned unit."""
    values = {
        "total_population": record.total_population,
        "male_population": record.male_population,
        "female_population": record.female_population,
        "meta": dict(record.meta),
        # The World Bank JSON series has no census PDF/page/extraction.
        "source_document_id": None,
        "source_page": None,
        "page_ref": None,
        "extraction_id": None,
        "source_hash": None,
        # This accepted publisher observation has its own confidence; do not
        # retain the previous census/fixture value used by the API filter.
        "confidence": 1.0,
        "basis": None,
        "confidence_score": None,
        "publishable": False,
        "quarantine_reason": None,
        "rural_population": None,
        "urban_population": None,
        "population_density": None,
    }
    updated = False
    for attr, value in values.items():
        if getattr(model, attr) != value:
            setattr(model, attr, value)
            updated = True
    return updated


def persist_population_records(
    session: Session,
    records: Iterable[PopulationRecord],
    context: DomainRunContext,
) -> PersistenceStats:
    stats = PersistenceStats()

    for record in records:
        stats.processed += 1

        if record.level != "national":
            stats.skipped += 1
            stats.errors.append("County population is owned by the census table loader")
            continue
        if (
            type(record.year) is not int
            or not 1900 <= record.year <= 2100
            or type(record.total_population) is not int
            or record.total_population < 5_000_000
            or any(
                value is not None
                and (
                    type(value) is not int
                    or value < 0
                    or value > record.total_population
                )
                for value in (record.male_population, record.female_population)
            )
            or sum(
                value
                for value in (record.male_population, record.female_population)
                if type(value) is int
            )
            > record.total_population
        ):
            stats.skipped += 1
            stats.errors.append("Invalid national population observation")
            continue
        if (
            not isinstance(record.meta, dict)
            or record.meta.get("dataset_id") != "SP.POP.TOTL"
            or record.meta.get("source_url")
            != "https://data.worldbank.org/indicator/SP.POP.TOTL?locations=KE"
        ):
            stats.skipped += 1
            stats.errors.append(
                "National population requires World Bank observation provenance"
            )
            continue
        entity_id = None

        stmt = select(PopulationData).where(
            PopulationData.year == record.year,
            PopulationData.entity_id == entity_id,
        )
        existing = session.execute(stmt).scalar_one_or_none()

        if existing is None:
            model = PopulationData(
                entity_id=entity_id,
                year=record.year,
                total_population=record.total_population,
                male_population=record.male_population,
                female_population=record.female_population,
                confidence=1.0,
                meta=record.meta or {},
            )
            session.add(model)
            stats.created += 1
        else:
            if _apply_record(existing, record):
                stats.updated += 1

    return stats


__all__ = ["PersistenceStats", "persist_population_records"]

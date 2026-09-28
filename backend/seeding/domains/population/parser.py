"""Normalize population payloads into structured records."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class PopulationRecord:
    level: str
    entity_slug: Optional[str]
    entity_name: str
    year: int
    total_population: int
    male_population: Optional[int] = None
    female_population: Optional[int] = None
    meta: Dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.meta is None:
            self.meta = {}


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and (
        not math.isfinite(value) or not value.is_integer()
    ):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _iter_payload_records(payload: Any) -> Iterable[Dict[str, Any]]:
    # Handle direct list (real KNBS data format)
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return

    # Handle wrapped format with "records" key (fixture format)
    if not isinstance(payload, dict):
        return

    records = payload.get("records")
    if isinstance(records, list):
        for item in records:
            if isinstance(item, dict):
                fields = item.get("fields")
                if isinstance(fields, dict):
                    yield fields
                    continue
                yield item
    elif isinstance(payload, dict):
        yield payload


def parse_population_payload(payload: Any) -> List[PopulationRecord]:
    """
    Parse raw payload into population records.

    Supports two formats:
    1. Direct list (real KNBS data): [{"county": "Nairobi", "year": 2019, ...}, ...]
    2. Wrapped format (fixtures): {"records": [{...}]}
    """

    normalized: List[PopulationRecord] = []

    for item in _iter_payload_records(payload):
        # Support both fixture format and real KNBS data format
        level = str(item.get("level") or item.get("admin_level") or "county").lower()

        # Real KNBS data uses "county" field, fixtures use "entity" or "name"
        entity_name = str(
            item.get("county") or item.get("entity") or item.get("name") or "Kenya"
        )

        entity_slug = (
            item.get("entity_slug")
            or item.get("county_slug")
            or item.get("slug")
            or entity_name.lower().replace(" ", "-")  # Generate slug from name
        )

        year = _coerce_int(item.get("year"))
        total_population = _coerce_int(item.get("total_population", item.get("total")))
        if year is None or total_population is None:
            continue

        record = PopulationRecord(
            level=level,
            entity_slug=str(entity_slug).lower() if entity_slug else None,
            entity_name=entity_name,
            year=year,
            total_population=total_population,
            male_population=_coerce_int(item.get("male_population", item.get("male"))),
            female_population=_coerce_int(
                item.get("female_population", item.get("female"))
            ),
            meta={
                "source": item.get("source"),
                "source_url": item.get("source_url"),
                "dataset_id": item.get("dataset_id"),
            },
        )
        normalized.append(record)

    return normalized


__all__ = ["PopulationRecord", "parse_population_payload"]

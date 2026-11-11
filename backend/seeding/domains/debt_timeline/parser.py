"""Parser for debt timeline data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from decimal import Decimal, InvalidOperation
from datetime import date

logger = logging.getLogger("seeding.debt_timeline.parser")


@dataclass
class DebtTimelineRecord:
    """One year of public debt composition."""

    year: int
    external: float  # Billions KES
    domestic: float  # Billions KES
    total: float  # Billions KES
    gdp: Decimal | None  # Billions KES, exact denominator precision
    gdp_ratio: float | None  # e.g. 77.6
    #: The row's OWN source. 2013-2021 come from CBK's /public-debt/ table and
    #: 2022-2025 from the Statistical Bulletin; the payload-level source names
    #: only one of them, so dropping this made every year trace to the wrong
    #: document.
    source: str | None = None
    source_evidence: list | None = None
    source_url: str | None = None


def parse_debt_timeline_payload(payload: dict[str, Any]) -> list[DebtTimelineRecord]:
    """Parse debt timeline JSON payload into records."""
    from .fetcher import _timeline
    timeline = _timeline(payload)
    records = []
    for entry in timeline:
        if entry["year"] > date.today().year:
            raise ValueError("Future calendar year is not an observed debt year")
        values = {}
        for key in ("external", "domestic", "total", "gdp", "gdp_ratio"):
            value = entry.get(key)
            if value is None and key in ("gdp", "gdp_ratio"):
                values[key] = None
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
                raise ValueError(f"Invalid debt timeline {key}")
            try:
                number = Decimal(str(value))
            except InvalidOperation as exc:
                raise ValueError(f"Invalid debt timeline {key}") from exc
            if not number.is_finite() or number < 0 or key == "gdp" and number <= 0:
                raise ValueError(f"Invalid debt timeline {key}")
            values[key] = number
        if values["total"] <= 0:
            raise ValueError("Debt stock total must be positive")
        evidence = entry.get("source_evidence")
        if evidence is not None and (type(evidence) is not list or any(not isinstance(item, dict) for item in evidence)):
            raise ValueError("Debt evidence must be a list of objects")
        records.append(DebtTimelineRecord(year=entry["year"], **values,
            source=entry.get("source") or None, source_evidence=evidence,
            source_url=entry.get("source_url")))
    logger.info("Parsed %d debt timeline records", len(records))
    return records

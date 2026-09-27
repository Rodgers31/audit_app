"""Parse national budget execution records."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger("seeding.national_budget.parser")


@dataclass
class NationalBudgetRecord:
    entity_slug: str
    entity_name: str
    period_label: str
    start_date: date
    end_date: date
    category: str
    subcategory: Optional[str]
    allocated_amount: Optional[Decimal]
    actual_spent: Optional[Decimal]
    committed_amount: Optional[Decimal]
    currency: str
    source: Optional[str]
    source_url: Optional[str]
    data_quality: Optional[str]
    notes: Optional[str]
    page_ref: Optional[str] = None
    # Declared provenance merged into the BudgetLine's provenance entry —
    # e.g. ``{"measure": "expenditure", …}`` from the annual NG-BIRR. The
    # execution panel reads the declaration; it never infers the measure.
    provenance_extra: Dict[str, Any] = field(default_factory=dict)


def _to_decimal(val: Any) -> Optional[Decimal]:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


def parse_national_budget_payload(
    raw: list[dict[str, Any]],
) -> list[NationalBudgetRecord]:
    records: list[NationalBudgetRecord] = []

    for item in raw:
        entity_slug = item.get("entity_slug", "")
        if not entity_slug:
            continue

        record = NationalBudgetRecord(
            entity_slug=entity_slug,
            entity_name=item.get("entity", ""),
            period_label=item.get("fiscal_year", ""),
            start_date=date.fromisoformat(item["start_date"]),
            end_date=date.fromisoformat(item["end_date"]),
            category=item.get("category", ""),
            subcategory=item.get("subcategory"),
            allocated_amount=_to_decimal(item.get("allocated_amount")),
            actual_spent=_to_decimal(item.get("actual_spent")),
            committed_amount=_to_decimal(item.get("committed_amount")),
            currency="KES",
            source=item.get("source"),
            source_url=item.get("source_url"),
            data_quality=item.get("data_quality"),
            notes=item.get("notes"),
            page_ref=item.get("page_ref"),
            provenance_extra=dict(item.get("provenance_extra") or {}),
        )
        records.append(record)

    logger.info("Parsed %d national budget execution records", len(records))
    return records

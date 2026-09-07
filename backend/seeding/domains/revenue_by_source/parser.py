"""Normalize revenue-by-source payloads into structured records."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional


# What a row's figure actually is. Declared per row in the fixture rather than
# sniffed out of the ``notes`` prose, because the live KRA overlay rewrites
# amounts and leaves notes untouched — so the note can outlive the number it
# describes, while ``basis`` is re-stamped by whatever last set the amount.
#
#   published — the cited source states this figure for this year.
#   derived   — back-computed from a published growth rate or ratio.
#   residual  — a subtraction: a total less the heads that were identified.
#   projected — a target or forecast; nothing has been collected yet.
VALID_BASES = frozenset({"published", "derived", "residual", "projected"})


def _basis(value: Any) -> Optional[str]:
    """Normalise a declared basis, or return None.

    An absent or unrecognised value yields ``None`` — the row is served as
    having no recorded provenance. Defaulting the unknown case to "published"
    would turn a fixture omission into a sourcing claim, which is the same
    defect shape as publishing a zero for a figure nobody measured.
    """
    if not isinstance(value, str):
        return None
    normalised = value.strip().lower()
    return normalised if normalised in VALID_BASES else None


@dataclass
class RevenueBySourceRecord:
    fiscal_year: str
    revenue_type: str
    category: str
    amount_billion_kes: Optional[Decimal]
    target_billion_kes: Optional[Decimal]
    performance_pct: Optional[Decimal]
    share_of_total_pct: Optional[Decimal]
    yoy_growth_pct: Optional[Decimal]
    source_url: Optional[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    """Row provenance carried through to the database and on to the API.

    ``notes`` is the human explanation; ``basis`` is the machine-readable one
    the page reads to caption the figure. A key is omitted rather than set to
    None so a row that declares nothing is served as declaring nothing.
    """
    meta: Dict[str, Any] = {}
    notes = item.get("notes")
    if notes:
        meta["notes"] = notes
    basis = _basis(item.get("basis"))
    if basis:
        meta["basis"] = basis
    return meta


def parse_revenue_payload(payload: List[Dict[str, Any]]) -> List[RevenueBySourceRecord]:
    """Parse raw JSON records into typed dataclass records."""
    records: List[RevenueBySourceRecord] = []

    for item in payload:
        if not isinstance(item, dict):
            continue

        fiscal_year = item.get("fiscal_year")
        revenue_type = item.get("revenue_type")

        if not fiscal_year or not revenue_type:
            continue

        record = RevenueBySourceRecord(
            fiscal_year=str(fiscal_year).strip(),
            revenue_type=str(revenue_type).strip(),
            category=str(item.get("category", "tax")).strip(),
            amount_billion_kes=_to_decimal(item.get("amount_billion_kes")),
            target_billion_kes=_to_decimal(item.get("target_billion_kes")),
            performance_pct=_to_decimal(item.get("performance_pct")),
            share_of_total_pct=_to_decimal(item.get("share_of_total_pct")),
            yoy_growth_pct=_to_decimal(item.get("yoy_growth_pct")),
            source_url=item.get("source_url"),
            metadata=_metadata(item),
        )
        records.append(record)

    return records

"""Normalize budgets payloads into structured records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class BudgetRecord:
    entity_slug: str
    entity_name: str
    period_label: str
    start_date: date
    end_date: date
    category: str
    subcategory: Optional[str]
    allocated_amount: Optional[Decimal]
    actual_amount: Optional[Decimal]
    # committed_amount stands in for CoB "Exchequer Releases" — the
    # amount released to the county during the fiscal year. The
    # Follow-the-Money waterfall treats this as the "Released" stage.
    committed_amount: Optional[Decimal]
    currency: str
    dataset_id: Optional[str]
    source_url: Optional[str]
    # April-2026 credibility pipeline fields:
    #   data_quality: one of {"official","estimated","projected",
    #     "historical","mixed","unknown"}. "official" is reserved for
    #     COB/COB-equivalent sources; fixtures default to "estimated".
    #   source_label: free-text attribution ("Controller of Budget
    #     County BIRR FY2024/25 Annual", "CRA Equitable Share formula",
    #     etc.). Persisted to SourceDocument.title when present.
    #   notes: free-text notes from the source (e.g. "Q3 report uses
    #     preliminary figures"). Persisted to BudgetLine.notes.
    data_quality: str = "unknown"
    source_label: Optional[str] = None
    notes: Optional[str] = None
    # Who published ``source_url``, when the payload declares it. Labels the
    # SourceDocument; undeclared rows are filed under the CoB (issue #276).
    publisher: Optional[str] = None
    page_ref: Optional[str] = None
    artifact_sha256: Optional[str] = None
    revenue_coverage: Optional[Dict[str, Any]] = None
    source_evidence: list = field(default_factory=list)


def _iter_records(payload: Any) -> Iterable[Dict[str, Any]]:
    # Handle direct list (real budget data format)
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
                fields = (
                    item.get("fields") if isinstance(item.get("fields"), dict) else item
                )
                if isinstance(fields, dict):
                    yield fields
    elif isinstance(payload, dict):
        yield payload


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).replace(",", "").strip())
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _to_date(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, (datetime, date)):
        return value.date() if isinstance(value, datetime) else value
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _declared(value: Any) -> Optional[str]:
    """A declared label, or None when the row declares nothing usable."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _amount(raw: Dict[str, Any], *keys: str) -> Optional[Decimal]:
    """An explicit zero or withdrawal wins over legacy alias fields."""
    for key in keys:
        if key in raw:
            return _to_decimal(raw[key])
    return None


def parse_budget_payload(payload: Dict[str, Any]) -> List[BudgetRecord]:
    normalized: List[BudgetRecord] = []

    for raw in _iter_records(payload):
        slug = raw.get("entity_slug") or raw.get("slug")
        name = raw.get("entity") or raw.get("name")
        period_label = raw.get("period_label") or raw.get("fiscal_year")
        start = _to_date(raw.get("start_date"))
        end = _to_date(raw.get("end_date"))
        category = raw.get("category")

        if (
            not slug
            or not name
            or not period_label
            or not category
            or not start
            or not end
        ):
            continue

        record = BudgetRecord(
            entity_slug=str(slug).lower(),
            entity_name=str(name),
            period_label=str(period_label),
            start_date=start,
            end_date=end,
            category=str(category),
            subcategory=(str(raw["subcategory"]) if raw.get("subcategory") else None),
            allocated_amount=_amount(raw, "allocated_amount", "allocated"),
            # Accept "actual_spent" too — both the fixture
            # (seeding/real_data/budgets.json) and the DB column
            # (BudgetLine.actual_spent) use that name, so older or
            # externally-authored payloads often emit it.
            actual_amount=_amount(raw, "actual_amount", "actual", "actual_spent"),
            committed_amount=_amount(
                raw, "committed_amount", "committed", "released", "exchequer_releases"
            ),
            currency=str(raw.get("currency") or "KES"),
            dataset_id=raw.get("dataset_id"),
            source_url=raw.get("source_url") or raw.get("url"),
            # April-2026: propagate credibility fields if present. Real
            # COB payloads should set data_quality="official"; CRA/fixture
            # payloads should set "estimated". Unknown falls back so the
            # trust badge can still render.
            data_quality=str(raw.get("data_quality") or "unknown").lower(),
            source_label=(
                raw.get("source_label")
                or raw.get("source")
                or raw.get("source_title")
            ),
            notes=raw.get("notes"),
            publisher=_declared(raw.get("publisher")),
            page_ref=_declared(raw.get("page_ref")),
            artifact_sha256=_declared(raw.get("artifact_sha256")),
            revenue_coverage=(
                raw["revenue_coverage"] if isinstance(raw.get("revenue_coverage"), dict) else None
            ),
            source_evidence=raw.get("source_evidence") or [],
        )
        normalized.append(record)

    return normalized


__all__ = ["BudgetRecord", "parse_budget_payload"]

"""Parser for pending bills data.

Converts raw extraction payload into typed PendingBillRecord objects
that the writer can persist to the database.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

logger = logging.getLogger("seeding.pending_bills.parser")


@dataclass
class PendingBillRecord:
    """Represents a parsed pending bills record for one entity."""

    entity_name: str
    entity_type: str  # "national" or "county"
    category: str  # "mda", "county", "state_corporation"
    fiscal_year: str
    total_pending: Decimal
    eligible_pending: Optional[Decimal] = None
    ineligible_pending: Optional[Decimal] = None
    notes: Optional[str] = None
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    #: ISO date the figure is a stock on, as the publication states it.
    as_at: Optional[str] = None
    source_table: Optional[str] = None
    source_page: Optional[int] = None
    #: What the report says about this figure, as ``{"code": ..., ...}``.
    reader_notes: list = field(default_factory=list)


def parse_pending_bills_payload(
    payload: dict[str, Any],
) -> list[PendingBillRecord]:
    """
    Parse pending bills payload into structured records.

    Accepts two payload formats:

    Format A — From the live ETL extractor:
    {
        "pending_bills": [
            {
                "entity_name": "Ministry of Health",
                "entity_type": "national",
                "category": "mda",
                "fiscal_year": "FY2024/25",
                "total_pending": 45000000000.0,
                "eligible_pending": 30000000000.0,
                "ineligible_pending": 15000000000.0,
            }
        ],
        "summary": {"grand_total": ..., "total_national": ..., "total_county": ...},
        "source_url": "...",
        "source_title": "..."
    }

    Format B — From a fixture/API (structured as loans-like records):
    {
        "pending_bills": [
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": "Pending Bills — MDAs",
                "lender_type": "pending_bills",
                "principal": "397000000000",
                "outstanding": "397000000000",
                "fiscal_year": "FY2024/25",
            }
        ],
        "source_url": "...",
        "source_title": "..."
    }
    """
    if not isinstance(payload, dict):
        raise ValueError("Pending bills payload must be an object")
    bills_data = payload.get("pending_bills", [])
    summary = payload.get("summary", {})
    if not isinstance(bills_data, list) or not isinstance(summary, dict):
        raise ValueError("Pending bills require a records list and summary object")
    source_url = payload.get("source_url")
    source_title = payload.get("source_title", "Controller of Budget Reports")
    _require_kes(payload)
    _require_kes(summary)
    # Validate declared summaries even alongside detail rows: malformed data
    # must not be silently salvaged as a successful smaller ingestion.
    totals = {
        key: require_pending_amount(summary.get(key), f"summary.{key}", optional=True)
        for key in ("total_national", "total_county", "grand_total")
    }
    records: list[PendingBillRecord] = []
    for idx, item in enumerate(bills_data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Pending bills record {idx} must be an object")
        _require_kes(item)
        entity_name = item.get("entity_name")
        if not isinstance(entity_name, str) or not entity_name.strip():
            raise ValueError(f"Pending bills record {idx} requires an entity name")
        # The first declared field is authoritative; never substitute a
        # principal for an explicitly missing/invalid outstanding figure.
        total = require_pending_amount(
            next(
                (
                    item[key]
                    for key in ("total_pending", "outstanding", "principal")
                    if key in item
                ),
                None,
            ),
            f"record {idx}.total_pending",
            optional=True,
        )
        eligible = require_pending_amount(
            item.get("eligible_pending"),
            f"record {idx}.eligible_pending",
            optional=True,
        )
        ineligible = require_pending_amount(
            item.get("ineligible_pending"),
            f"record {idx}.ineligible_pending",
            optional=True,
        )
        if total is None or (total == 0 and item.get("printed_zero") is not True):
            logger.info(
                "Pending bills record %d withheld: %s",
                idx,
                "amount_not_reported" if total is None else "zero_not_declared_printed",
            )
            continue
        reader_notes = item.get("reader_notes", [])
        if not isinstance(reader_notes, list) or any(
            not isinstance(n, dict) for n in reader_notes
        ):
            raise ValueError(f"Pending bills record {idx} reader notes must be objects")
        records.append(
            PendingBillRecord(
                entity_name=entity_name.strip(),
                entity_type=item.get("entity_type", "national"),
                category=item.get("category", "mda"),
                fiscal_year=item.get("fiscal_year", ""),
                total_pending=total,
                eligible_pending=eligible,
                ineligible_pending=ineligible,
                notes=item.get("notes"),
                source_url=source_url,
                source_title=source_title,
                as_at=item.get("as_at"),
                source_table=item.get("table"),
                source_page=item.get("page"),
                reader_notes=reader_notes,
            )
        )

    # A deliberately missing/withheld detail row is not an invitation to
    # replace it with an aggregate. This fallback is only for summary payloads.
    if not bills_data:
        for key, entity_name, entity_type, category in (
            ("total_national", "National Government — All MDAs", "national", "mda"),
            ("total_county", "County Governments — All Counties", "county", "county"),
        ):
            amount = totals[key]
            if amount is None or (
                amount == 0 and summary.get("printed_zero") is not True
            ):
                if key in summary:
                    logger.info(
                        "Pending bills %s withheld: %s",
                        key,
                        "amount_not_reported"
                        if amount is None
                        else "zero_not_declared_printed",
                    )
                continue
            records.append(
                PendingBillRecord(
                    entity_name=entity_name,
                    entity_type=entity_type,
                    category=category,
                    fiscal_year=summary.get("fiscal_year", ""),
                    total_pending=amount,
                    notes=f"Aggregate figure from declared source. As at: {summary.get('as_at_date', 'not stated')}",
                    source_url=source_url,
                    source_title=source_title,
                    as_at=summary.get("as_at_date"),
                )
            )
    return records


def require_pending_amount(
    value: Any, field: str, *, optional: bool = False
) -> Optional[Decimal]:
    """Validate a declared raw-KES amount without treating invalid as missing.

    None is an optional unreported component; boolean and malformed values
    are refusals. A zero is numeric evidence whose printed status the parser
    checks separately. The writer repeats this check for direct calls.
    """
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"Invalid pending bills {field}: monetary amount required")
    raw = str(value).strip()
    if "," in raw:
        if not re.fullmatch(r"[+]?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?", raw):
            raise ValueError(
                f"Invalid pending bills {field}: malformed monetary grouping"
            )
        raw = raw.replace(",", "")
    if not re.fullmatch(
        r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", raw
    ):
        raise ValueError(f"Invalid pending bills {field}: malformed monetary amount")
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(
            f"Invalid pending bills {field}: monetary amount required"
        ) from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(
            f"Invalid pending bills {field}: finite nonnegative amount required"
        )
    return amount


def _require_kes(item):
    # Absence does not declare another currency; explicit conflict does.
    if (
        "currency" in item
        and item["currency"] is not None
        and item["currency"] != "KES"
    ):
        raise ValueError("Pending bills amounts must be declared in KES")

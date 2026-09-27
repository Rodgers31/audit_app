"""Parser for pending bills data.

Converts raw extraction payload into typed PendingBillRecord objects
that the writer can persist to the database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
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
    records: list[PendingBillRecord] = []
    source_url = payload.get("source_url")
    source_title = payload.get("source_title", "Controller of Budget Reports")

    bills_data = payload.get("pending_bills", [])
    summary = payload.get("summary", {})

    logger.info(f"Parsing {len(bills_data)} pending bills entries")

    for idx, item in enumerate(bills_data, start=1):
        try:
            entity_name = item.get("entity_name", "").strip()
            if not entity_name:
                logger.warning(f"Skipping record {idx}: no entity_name")
                continue

            entity_type = item.get("entity_type", "national")
            category = item.get("category", "mda")
            fiscal_year = item.get("fiscal_year", "")

            # Support both extractor format and loans-like format
            total = _to_decimal(next(
                (item[key] for key in ("total_pending", "outstanding", "principal") if key in item),
                None,
            ))
            eligible = _to_decimal(item.get("eligible_pending"))
            ineligible = _to_decimal(item.get("ineligible_pending"))

            if total is None or (total <= 0 and item.get("printed_zero") is not True):
                logger.debug(
                    f"Skipping record {idx} ({entity_name}): " f"zero or missing amount"
                )
                continue

            record = PendingBillRecord(
                entity_name=entity_name,
                entity_type=entity_type,
                category=category,
                fiscal_year=fiscal_year,
                total_pending=total,
                eligible_pending=eligible,
                ineligible_pending=ineligible,
                notes=item.get("notes"),
                source_url=source_url,
                source_title=source_title,
                as_at=item.get("as_at"),
                source_table=item.get("table"),
                source_page=item.get("page"),
                reader_notes=list(item.get("reader_notes") or []),
            )
            records.append(record)

        except Exception as exc:
            logger.warning(f"Failed to parse record {idx}: {exc}")

    # If no individual records but we have summary data, create aggregate records
    if not records and summary:
        if summary.get("total_national"):
            records.append(
                PendingBillRecord(
                    entity_name="National Government — All MDAs",
                    entity_type="national",
                    category="mda",
                    fiscal_year=summary.get("fiscal_year", ""),
                    total_pending=Decimal(str(summary["total_national"])),
                    notes=(
                        f"Aggregate figure extracted from COB report. "
                        f"As at: {summary.get('as_at_date', 'N/A')}"
                    ),
                    source_url=source_url,
                    source_title=source_title,
                )
            )

        if summary.get("total_county"):
            records.append(
                PendingBillRecord(
                    entity_name="County Governments — All Counties",
                    entity_type="county",
                    category="county",
                    fiscal_year=summary.get("fiscal_year", ""),
                    total_pending=Decimal(str(summary["total_county"])),
                    notes=(
                        f"Aggregate figure extracted from COB report. "
                        f"As at: {summary.get('as_at_date', 'N/A')}"
                    ),
                    source_url=source_url,
                    source_title=source_title,
                )
            )
        logger.info(f"Created {len(records)} aggregate records from summary data")

    return records


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Safely convert a value to Decimal."""
    if value is None or isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value).replace(",", "").strip())
        return d if d.is_finite() and d >= 0 else None
    except Exception:
        return None

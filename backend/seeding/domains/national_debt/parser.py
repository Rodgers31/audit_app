"""Parser for National Treasury debt bulletin data."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger("seeding.national_debt.parser")


class DebtRecord:
    """Represents a parsed debt/loan record."""

    def __init__(
        self,
        entity_name: str,
        entity_type: str,
        lender: str,
        principal: Decimal,
        outstanding: Decimal,
        issue_date: datetime,
        maturity_date: datetime | None,
        currency: str,
        source_url: str | None = None,
        source_title: str | None = None,
        publisher: str | None = None,
        debt_category: str | None = None,
        interest_rate: Decimal | None = None,
        notes: str | None = None,
    ):
        self.entity_name = entity_name
        self.entity_type = entity_type
        self.lender = lender
        self.principal = principal
        self.outstanding = outstanding
        self.issue_date = issue_date
        self.maturity_date = maturity_date
        self.currency = currency
        self.source_url = source_url
        self.source_title = source_title
        #: Who published THIS row. The national-debt payload is a CBK/Treasury
        #: bulletin, but the IDS creditor rows merged into it are World Bank
        #: data — attributing them to the Treasury would be a false citation.
        self.publisher = publisher
        self.debt_category = debt_category
        self.interest_rate = interest_rate
        self.notes = notes


def parse_debt_payload(payload: dict[str, Any]) -> list[DebtRecord]:
    """
    Parse debt payload into structured records.

    Expected payload format:
    {
        "loans": [
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": "World Bank",
                "principal": "50000000000.00",
                "outstanding": "45000000000.00",
                "issue_date": "2020-01-15",
                "maturity_date": "2030-01-15",
                "currency": "KES"
            }
        ],
        "source_url": "https://treasury.go.ke/...",
        "source_title": "Public Debt Bulletin Q3 2024"
    }

    Args:
        payload: Raw JSON payload from fetcher

    Returns:
        List of parsed DebtRecord objects
    """
    records: list[DebtRecord] = []
    loans_data = payload.get("loans", [])
    source_url = payload.get("source_url")
    source_title = payload.get("source_title", "National Treasury Debt Bulletin")

    logger.info(f"Parsing {len(loans_data)} debt records")

    for idx, loan_data in enumerate(loans_data, start=1):
        try:
            # Parse dates
            issue_date = datetime.fromisoformat(loan_data["issue_date"])
            maturity_date = None
            if loan_data.get("maturity_date"):
                maturity_date = datetime.fromisoformat(loan_data["maturity_date"])

            # Parse amounts
            principal = Decimal(str(loan_data["principal"]))
            outstanding = Decimal(str(loan_data["outstanding"]))

            # Parse optional interest rate
            interest_rate = None
            if loan_data.get("interest_rate"):
                interest_rate = Decimal(str(loan_data["interest_rate"]))

            record = DebtRecord(
                entity_name=loan_data["entity_name"],
                entity_type=loan_data["entity_type"],
                lender=loan_data["lender"],
                principal=principal,
                outstanding=outstanding,
                issue_date=issue_date,
                maturity_date=maturity_date,
                currency=loan_data.get("currency", "KES"),
                # A row's own source wins over the payload's. The IDS creditor
                # rows are World Bank data merged into a CBK-sourced payload;
                # without this they persisted as if CBK had published them.
                source_url=loan_data.get("source_url") or source_url,
                source_title=loan_data.get("source_title") or source_title,
                publisher=loan_data.get("publisher"),
                debt_category=loan_data.get("debt_category"),
                interest_rate=interest_rate,
                notes=loan_data.get("notes"),
            )

            records.append(record)

        except (KeyError, ValueError, TypeError) as exc:
            logger.warning(
                f"Skipping malformed debt record #{idx}: {exc}",
                extra={"record": loan_data, "error": str(exc)},
            )
            continue

    logger.info(f"Successfully parsed {len(records)} debt records")
    return records

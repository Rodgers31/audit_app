"""Recheck one exact CoB annual PDF against the prior county receipt.

This is offline source evidence only. It neither reads nor changes a database,
and its output must not be interpreted as production publication acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from seeding.domains.pending_bills.fetcher import county_payables_payload
from seeding.pdf_parsers import (
    KENYAN_COUNTIES,
    CoBQuarterlyReportParser,
    cbirr_year_end_trade_payables,
)


SOURCE_URL = (
    "https://cob.go.ke/download/county-governments-budget-implementation-"
    "review-report-for-the-financial-year-2025-26/?wpdmdl=16482"
)


def _checked_digest(path: Path, expected: str) -> None:
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"CoB PDF checksum mismatch: {path}")


def _positive_amount(value: object, context: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"Invalid {context}: {value!r}") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"Invalid {context}: {value!r}")
    return amount


def _validate_prior_coverage(rows: list[dict]) -> dict[str, dict]:
    counties = set(KENYAN_COUNTIES)
    if len(rows) != 47 or {r["county"] for r in rows} != counties:
        raise ValueError("Prior receipt cannot account for all 47 counties exactly once")
    for row in rows:
        county = row["county"]
        if row["period"] != "FY2025/26":
            raise ValueError(f"Prior period is not FY2025/26 for {county}")
        _positive_amount(row["budget_allocation_million_kes"], f"{county} budget allocation")
        _positive_amount(row["budget_expenditure_million_kes"], f"{county} budget spending")
        status = row["revenue"]["status"]
        if status not in {"reconciled", "withheld"}:
            raise ValueError(f"Invalid prior revenue status for {county}: {status}")
        if status == "reconciled":
            _positive_amount(row["revenue"]["total_kes"], f"{county} cash receipts")
        pending = row["pending_bills"]
        if pending["county"] != county or pending["status"] not in {"reported", "not_reported"}:
            raise ValueError(f"Invalid prior pending status for {county}")
        if pending["status"] == "reported":
            _positive_amount(pending["total_millions"], f"{county} pending bills")
        elif pending["total_millions"] is not None:
            raise ValueError(f"Unreported prior pending bills have an amount for {county}")
    return {row["county"]: row for row in rows}


def recheck(pdf_path: Path, expected_sha256: str, prior_path: Path) -> dict:
    _checked_digest(pdf_path, expected_sha256)
    prior = json.loads(prior_path.read_text())
    if prior.get("cbirr_sha256") != expected_sha256:
        raise ValueError("Prior receipt describes a different CoB artifact")
    prior_by_county = _validate_prior_coverage(prior["coverage"])
    counties = set(KENYAN_COUNTIES)

    parser = CoBQuarterlyReportParser(pdf_path)
    records = parser.parse()
    totals = [r for r in records if r["category"] == "Total"]
    cash = [
        r for r in records
        if r["category"] == "Revenue Receipts" and r["subcategory"] == "Total"
    ]
    if len(totals) != 47 or {r["county"] for r in totals} != counties:
        raise ValueError("Current parse has incomplete or duplicate budget totals")
    if len(cash) != len({r["county"] for r in cash}):
        raise ValueError("Current parse repeats a county cash total")
    for row in totals:
        _positive_amount(row["allocated"], f"{row['county']} budget allocation")
        _positive_amount(row["absorbed"], f"{row['county']} budget spending")
    for row in cash:
        _positive_amount(row["absorbed"], f"{row['county']} cash receipts")
    total_by_county = {r["county"]: r for r in totals}
    cash_by_county = {r["county"]: r for r in cash}
    if set(parser.revenue_coverage) != counties:
        raise ValueError("Current revenue coverage omits a county")
    if set(cash_by_county) != {
        county for county, state in parser.revenue_coverage.items()
        if state["status"] == "reconciled"
    }:
        raise ValueError("Current cash totals disagree with reconciliation status")
    prior_reconciled = {
        county for county in counties
        if prior_by_county[county]["revenue"]["status"] == "reconciled"
    }
    for county in counties:
        old = prior_by_county[county]
        current = total_by_county[county]
        if (
            Decimal(str(current["allocated"])) != Decimal(str(old["budget_allocation_million_kes"]))
            or Decimal(str(current["absorbed"])) != Decimal(str(old["budget_expenditure_million_kes"]))
        ):
            raise ValueError(f"Budget total changed for {county} on the same artifact")
        if county in prior_reconciled and (
            county not in cash_by_county
            or Decimal(str(cash_by_county[county]["absorbed"]))
            != Decimal(str(old["revenue"]["total_kes"]))
        ):
            raise ValueError(f"Previously reconciled cash total changed for {county}")

    payables = cbirr_year_end_trade_payables(pdf_path)
    if len(payables) != 47 or {r["county"] for r in payables} != counties:
        raise ValueError("Current payable parse cannot account for all 47 counties")
    for row in payables:
        if row["status"] not in {"reported", "not_reported"}:
            raise ValueError(f"Invalid payable status for {row['county']}")
        if row["status"] == "reported":
            _positive_amount(row["total_millions"], f"{row['county']} pending bills")
        elif row["total_millions"] is not None:
            raise ValueError(f"Unreported pending bills have an amount for {row['county']}")
    pending_by_county = {r["county"]: r for r in payables}
    for county in counties:
        if pending_by_county[county] != prior_by_county[county]["pending_bills"]:
            raise ValueError(f"Pending-bill source evidence changed for {county}")
    payload = county_payables_payload(payables, SOURCE_URL)
    qualified = {
        r["entity_name"].removesuffix(" County"): r["reader_notes"]
        for r in payload["pending_bills"] if r["reader_notes"]
    }
    _checked_digest(pdf_path, expected_sha256)

    coverage = []
    for county in KENYAN_COUNTIES:
        budget = total_by_county[county]
        pending = pending_by_county[county]
        revenue = parser.revenue_coverage[county]
        coverage.append({
            "county": county,
            "budget_allocated_million_kes": str(budget["allocated"]),
            "budget_spent_million_kes": str(budget["absorbed"]),
            "revenue_status": revenue["status"],
            "revenue_reason": revenue.get("reason"),
            "revenue_total_kes": (
                str(cash_by_county[county]["absorbed"])
                if county in cash_by_county else None
            ),
            "revenue_pdf_pages": revenue["pages"],
            "pending_status": pending["status"],
            "pending_million_kes": pending["total_millions"],
            "pending_pdf_page": pending["page"],
            "pending_reader_notes": qualified.get(county, []),
        })
    return {
        "kind": "offline_county_finance_source_recheck",
        "generated_by": "backend/scripts/recheck_county_finance_source.py",
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "PARTIAL_SOURCE_COVERAGE",
        "target_commit": None,
        "production_published": False,
        "source_url": SOURCE_URL,
        "sha256": expected_sha256,
        "periods": sorted({
            f"FY{r['fiscal_year']}" + (f" {r['quarter']}" if r.get("quarter") else "")
            for r in totals
        }),
        "as_at": sorted({r["as_at"] for r in payables}),
        "budget_records": len(records),
        "budget_total_counties": len(totals),
        "revenue_reconciled": len(cash),
        "revenue_recovered_vs_prior": sorted(set(cash_by_county) - prior_reconciled),
        "prior_reconciled_preserved": len(prior_reconciled),
        "pending_status_counts": dict(Counter(r["status"] for r in payables)),
        "pending_qualified_count": len(qualified),
        "pending_note_counts": dict(Counter(
            note["code"] for notes in qualified.values() for note in notes
        )),
        "pending_reported_sum_kes": str(sum(
            (Decimal(r["total_pending"]) for r in payload["pending_bills"]), Decimal(0)
        )),
        "pending_complete_total_kes": None,
        "coverage": coverage,
    }


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--cbirr-pdf", type=Path, required=True)
    cli.add_argument("--expected-sha256", required=True)
    cli.add_argument("--prior-receipt", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    receipt = recheck(args.cbirr_pdf, args.expected_sha256, args.prior_receipt)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    saved = json.loads(args.output.read_text())
    if (saved.get("generator_sha256") != receipt["generator_sha256"]
            or saved.get("verdict") != receipt["verdict"]):
        raise ValueError(f"Recheck receipt provenance did not survive write: {args.output}")
    print(
        f"CoB source recheck: {receipt['budget_total_counties']} budgets, "
        f"{receipt['revenue_reconciled']} cash totals, "
        f"{receipt['pending_status_counts']}, "
        f"{receipt['pending_qualified_count']} qualified. No production write."
    )


if __name__ == "__main__":
    main()

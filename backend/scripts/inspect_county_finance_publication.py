"""Offline source preflight, never a seed or production acceptance certificate.

Run from backend with PYTHONPATH=. This reads the exact PDF artifacts supplied
by the operator and writes a county-by-period receipt. No DB/network is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from seeding.domains.pending_bills.brop_parser import parse_brop_pdf
from seeding.domains.stalled_projects.cob_parser import CbirrStalledProjectsParser
from seeding.pdf_parsers import (
    KENYAN_COUNTIES,
    CoBQuarterlyReportParser,
    cbirr_year_end_trade_payables,
)


def checked_pdf(path: Path, expected: str) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise ValueError(f"Artifact checksum mismatch: {path.name}")
    return digest


def inspect(cbirr: Path, brop: Path, cbirr_sha256: str, brop_sha256: str) -> dict:
    checked_pdf(cbirr, cbirr_sha256)
    checked_pdf(brop, brop_sha256)
    parser = CoBQuarterlyReportParser(cbirr)
    budgets = parser.parse()
    pending = cbirr_year_end_trade_payables(cbirr)
    projects = CbirrStalledProjectsParser(cbirr).parse()
    national = parse_brop_pdf(brop, counties=False)
    totals = {r["county"]: r for r in budgets if r["category"] == "Total"}
    cash = {r["county"]: r for r in budgets if r["category"] == "Revenue Receipts" and r["subcategory"] == "Total"}
    payables = {r["county"]: r for r in pending}
    stalled = {r["county"]: r for r in projects if r.get("kind") == "county"}
    if set(totals) != set(KENYAN_COUNTIES) or set(payables) != set(KENYAN_COUNTIES):
        raise ValueError("Preflight cannot account for all 47 counties")
    coverage = []
    for county in KENYAN_COUNTIES:
        row = totals[county]
        payable = payables[county]
        project = stalled.get(county, {})
        coverage.append({
            "county": county,
            "period": "FY" + row["fiscal_year"] + (" " + row["quarter"] if row.get("quarter") else ""),
            "budget_allocation_million_kes": row["allocated"],
            "budget_expenditure_million_kes": row["absorbed"],
            "revenue": {**parser.revenue_coverage[county],
                        "total_kes": cash.get(county, {}).get("absorbed")},
            "pending_bills": payable,
            "stalled_projects": {
                "tables": [{k: t.get(k) for k in ("table_no", "caption_page", "as_of", "reported_by")}
                           for t in project.get("tables", [])],
                "reconciliation": project.get("reconciliation"),
            },
        })
    # Refuse an artifact modified during extraction, rather than certifying
    # one checksum against amounts read from another version.
    checked_pdf(cbirr, cbirr_sha256)
    checked_pdf(brop, brop_sha256)
    return {
        "kind": "offline_source_preflight", "production_published": False,
        "cbirr_sha256": cbirr_sha256, "brop_sha256": brop_sha256,
        "budget_records": len(budgets),
        "revenue_counties_reconciled": len(cash),
        "county_count": len(coverage),
        "national_pending_bills": asdict(national.national),
        "county_pending_reported_sum_kes": sum(
            (Decimal(p["total_millions"]) * 1_000_000 for p in pending if p["status"] == "reported"), Decimal(0)),
        "county_pending_count": sum(p["status"] == "reported" for p in pending),
        "combined_pending_total_kes": None,
        "combined_pending_absent_reason": (
            "county_amounts_incomplete" if any(p["status"] != "reported" for p in pending)
            else "requires_writer_and_api_edition_verification"
        ),
        "projects_edition": next(p for p in projects if p.get("kind") == "edition"),
        "coverage": coverage,
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--cbirr-pdf", type=Path, required=True)
    cli.add_argument("--brop-pdf", type=Path, required=True)
    cli.add_argument("--cbirr-sha256", required=True)
    cli.add_argument("--brop-sha256", required=True)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    receipt = inspect(args.cbirr_pdf, args.brop_pdf, args.cbirr_sha256, args.brop_sha256)
    args.output.write_text(json.dumps(receipt, default=str, indent=2) + "\n")
    print(f"Source preflight: {receipt['county_count']} counties; "
          f"{receipt['revenue_counties_reconciled']} cash tables reconciled; "
          f"{receipt['county_pending_count']} county pending-bill amounts. No production write.")


if __name__ == "__main__":
    main()

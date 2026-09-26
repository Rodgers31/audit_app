"""National-government budget execution by sector, for /budget/enhanced.

What this publishes, and why it is chosen the way it is (#241)
--------------------------------------------------------------
The panel says how much of each sector's approved budget was SPENT by
year-end. So it publishes only rows that DECLARE that measure — BudgetLine
provenance ``measure: "expenditure"``, written by the annual NG-BIRR Sector
Summary parser (``seeding/domains/national_budget/sector_expenditure.py``) —
from ANNUAL periods only.

What it replaced selected rows by sniffing ``committed_amount IS NOT NULL``.
Only the git fixture set that column, so the panel showed fixture figures
while they were the newest period and nothing at all once a live period was
newer: production served ``execution_by_sector: []`` for FY 2025/26. Dropping
the sniff without a declaration would have been worse — the live rows then
held Exchequer Issues (cash released) against Net Estimates, which is not
spending — and a quarterly period would have been framed as year-end
"unspent" money.

Absence is absence: no rows means an empty list with ``fiscal_year`` None,
never a sector at 0.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_ANNUAL_LABEL_RE = re.compile(r"^FY\d{4}/\d{2}$")


def _declaration(line: Any) -> Dict[str, Any]:
    provenance = line.provenance or []
    if isinstance(provenance, list) and provenance and isinstance(provenance[-1], dict):
        return provenance[-1]
    return {}


def execution_by_sector(db) -> Dict[str, Any]:
    """The newest annual period's declared-expenditure rows, per sector.

    Returns ``{"rows", "fiscal_year", "source", "coverage", "excludes",
    "measure"}``. Every value but ``rows`` is None when there is nothing to
    publish.
    """
    from models import BudgetLine, Entity, FiscalPeriod, SourceDocument
    from seeding.domains.national_budget.sector_expenditure import (
        EXPENDITURE_MEASURE,
        SECTORS,
    )

    empty: Dict[str, Any] = {
        "rows": [],
        "fiscal_year": None,
        "source": None,
        "coverage": None,
        "excludes": None,
        "measure": None,
    }
    entity_id = db.query(Entity.id).filter(Entity.slug == "national-government").scalar()
    if not entity_id:
        return empty

    candidates = (
        db.query(BudgetLine, FiscalPeriod)
        .join(FiscalPeriod, BudgetLine.period_id == FiscalPeriod.id)
        .filter(BudgetLine.entity_id == entity_id)
        .all()
    )
    by_period: Dict[int, List[Any]] = {}
    periods: Dict[int, Any] = {}
    for line, period in candidates:
        decl = _declaration(line)
        if decl.get("measure") != EXPENDITURE_MEASURE:
            continue
        # Annual only: a quarter's spending is not a year-end absorption gap.
        if not _ANNUAL_LABEL_RE.match(period.label or "") or decl.get("period") != "annual":
            continue
        by_period.setdefault(period.id, []).append(line)
        periods[period.id] = period
    if not by_period:
        return empty

    newest_id = max(periods, key=lambda pid: (periods[pid].start_date, pid))
    lines = by_period[newest_id]
    period = periods[newest_id]

    order = {name: i for i, (_, name) in enumerate(SECTORS)}
    rows: List[Dict[str, Any]] = []
    for line in sorted(lines, key=lambda l: (order.get(l.category, 99), l.category)):
        if line.allocated_amount is None or line.actual_spent is None:
            continue  # a sector without both figures is not published at all
        allocated = float(line.allocated_amount)
        spent = float(line.actual_spent)
        if allocated <= 0:
            continue
        decl = _declaration(line)
        rows.append(
            {
                "sector": line.category,
                "allocated": allocated,
                "spent": spent,
                "unspent": allocated - spent,
                "execution_rate": round(spent / allocated * 100, 1),
                "page_ref": line.page_ref,
                "table": decl.get("table"),
                # Development/Recurrent — only where the report's own rows
                # reproduce its Total; null otherwise, with the reason in notes.
                "split": decl.get("split"),
                "notes": decl.get("notes"),
            }
        )
    if not rows:
        return empty

    decl = _declaration(lines[0])
    source = None
    doc_id = lines[0].source_document_id
    if doc_id:
        doc = db.query(SourceDocument).filter(SourceDocument.id == doc_id).first()
        if doc is not None:
            source = {
                "publisher": doc.publisher,
                "title": doc.title,
                "url": doc.url,
            }
    coverage = decl.get("coverage")
    excludes = None
    if isinstance(coverage, dict) and coverage.get("cfs_expenditure_bn"):
        excludes = {
            "label": "Consolidated Fund Services",
            "description": (
                "public debt, pensions and constitutional office holders' "
                "salaries — charged directly to the Consolidated Fund, not "
                "to any sector"
            ),
            "expenditure_bn": coverage["cfs_expenditure_bn"],
        }
    return {
        "rows": rows,
        "fiscal_year": period.label,
        "source": source,
        "coverage": coverage,
        "excludes": excludes,
        "measure": {
            "spent": decl.get("measure"),
            "allocated": decl.get("allocated_measure"),
        },
    }


__all__ = ["execution_by_sector"]
